"""Reproducible, rights-aware PubMed acquisition for the unannotated research corpus."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable

from .io import load_jsonl, sha256_file, write_json, write_jsonl


EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PMC_OA = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
PMC_OAI = "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"
TARGETS = (
    ("dog_longevity_aging", 15, "dog", "(11991408[PMID] OR 37229711[PMID] OR 30937823[PMID] OR 22005424[PMID] OR 1391181[PMID] OR 16046720[PMID] OR 27747924[PMID] OR 32835231[PMID] OR 38302530[PMID] OR 35110758[PMID] OR 33057125[PMID] OR 37740140[PMID] OR 38394961[PMID] OR 29457329[PMID] OR 36066765[PMID])"),
    ("dog_biomarkers", 10, "dog", "(28373601[PMID] OR 32619550[PMID] OR 41429575[PMID] OR 41121965[PMID] OR 41929108[PMID] OR 35580182[PMID] OR 38263575[PMID] OR 35502722[PMID] OR 34132979[PMID] OR 37372311[PMID])"),
    ("dog_pharmacology", 10, "dog", "(34565678[PMID] OR 37541934[PMID] OR 40302160[PMID] OR 38811634[PMID] OR 28374166[PMID] OR 39951177[PMID] OR 40434930[PMID] OR 40072052[PMID] OR 37789403[PMID] OR 24859353[PMID])"),
    ("dog_nutrition_cognition", 8, "dog", "(29316985[PMID] OR 30619873[PMID] OR 18582445[PMID] OR 37073246[PMID] OR 31252640[PMID] OR 41817417[PMID] OR 26481404[PMID] OR 32936808[PMID])"),
    ("dog_cognitive_aging", 5, "dog", "(36008509[PMID] OR 36129565[PMID] OR 39106023[PMID] OR 31685716[PMID] OR 35077771[PMID])"),
    ("cat_aging_biomarkers", 15, "cat", "(34463900[PMID] OR 29393723[PMID] OR 24217707[PMID] OR 37991462[PMID] OR 31560478[PMID] OR 23254237[PMID] OR 34941841[PMID] OR 39752925[PMID] OR 37133704[PMID] OR 31568615[PMID] OR 36699321[PMID] OR 40622820[PMID] OR 39745207[PMID] OR 40011503[PMID] OR 39474931[PMID])"),
    ("cat_nutrition_aging", 10, "cat", "(34359256[PMID] OR 33463789[PMID] OR 38084870[PMID] OR 40728602[PMID] OR 31635090[PMID] OR 10879400[PMID] OR 38952053[PMID] OR 34789346[PMID] OR 38415620[PMID] OR 41534199[PMID])"),
    ("cat_health_screening", 6, "cat", "(38967102[PMID] OR 42561144[PMID] OR 40182825[PMID] OR 40965234[PMID] OR 37246725[PMID] OR 37548534[PMID])"),
    ("cat_cognitive_aging", 4, "cat", "(3600956[PMID] OR 41268300[PMID] OR 40790741[PMID] OR 31273784[PMID])"),
    ("cat_ckd_survival", 14, "cat", "(11215911[PMID] OR 16478432[PMID] OR 34730466[PMID] OR 18691369[PMID] OR 39724773[PMID] OR 39481914[PMID] OR 26948860[PMID] OR 16734085[PMID] OR 32445217[PMID] OR 32594827[PMID] OR 40399101[PMID] OR 42121739[PMID] OR 33215950[PMID] OR 32456516[PMID])"),
    ("falsification_or_null", 3, "cat", "(38987749[PMID] OR 37495229[PMID] OR 41630014[PMID])"),
)
_EXCLUDED_PUBLICATION_TYPES = {"review", "editorial", "comment", "letter", "news"}


def _portable_relative(path: Path, root: Path) -> str:
    """Return a platform-independent relative path for JSON/CSV contracts."""
    return path.relative_to(root).as_posix()


def _get(url: str, params: dict[str, Any], email: str | None = None, opener: Callable[[str], bytes] | None = None) -> bytes:
    """Fetch an NCBI resource with bounded retries for transient service errors."""
    query = urllib.parse.urlencode({**params, "tool": "petlongevity_bench", **({"email": email} if email else {})})
    request_url = f"{url}?{query}"
    request = opener or (lambda value: urllib.request.urlopen(value, timeout=60).read())
    for attempt in range(3):
        try:
            return request(request_url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise
            if opener is not None or attempt == 2:
                raise
            time.sleep(attempt + 1)
        except (urllib.error.URLError, TimeoutError):
            if opener is not None or attempt == 2:
                raise
            time.sleep(attempt + 1)
    raise RuntimeError("unreachable")


def _text(element: ET.Element | None) -> str:
    return "".join(element.itertext()).strip() if element is not None else ""


def _publication_date(article: ET.Element) -> str | None:
    value = article.find(".//ArticleDate")
    if value is None:
        value = article.find(".//JournalIssue/PubDate")
    if value is None:
        return None
    year = value.findtext("Year")
    if not year or not year.isdigit():
        return None
    month = value.findtext("Month") or "01"; day = value.findtext("Day") or "01"
    try: return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    except ValueError: return f"{int(year):04d}-01-01"


def _species(text: str) -> list[str]:
    lower = text.lower(); out=[]
    if re.search(r"\b(dog|dogs|canine|canines)\b", lower): out.append("dog")
    if re.search(r"\b(cat|cats|feline|felines)\b", lower): out.append("cat")
    return out


def _pmcid(value: str | None) -> str | None:
    """Normalize PubMed's numeric PMC ArticleId to the public PMCID form."""
    if not value:
        return None
    return value if value.upper().startswith("PMC") else f"PMC{value}"


def parse_pubmed_xml(raw: bytes, target: str, target_species: str, query: str, retrieved_at: str) -> list[dict[str, Any]]:
    """Parse original PubMed EFetch XML into unannotated bibliographic registry rows."""
    root = ET.fromstring(raw); rows=[]
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID") or ""
        ids = {item.attrib.get("IdType"): (item.text or "") for item in article.findall("./PubmedData/ArticleIdList/ArticleId")}
        title = _text(article.find(".//ArticleTitle"))
        abstract = "\n".join(_text(item) for item in article.findall(".//Abstract/AbstractText") if _text(item))
        authors=[]
        for author in article.findall(".//Author"):
            name=" ".join(filter(None,[author.findtext("ForeName"),author.findtext("LastName")])).strip()
            if name: authors.append(name)
        publication_types=[_text(item) for item in article.findall(".//PublicationType") if _text(item)]
        body=" ".join([title,abstract]); species=_species(body)
        rows.append({
            "paper_id": f"PMID:{pmid}", "pmid": pmid, "pmcid": _pmcid(ids.get("pmc")), "doi": ids.get("doi") or None,
            "title": title, "authors": authors, "journal": _text(article.find(".//Journal/Title")),
            "publication_date": _publication_date(article), "publication_year": int((_publication_date(article) or "0000")[:4]) or None,
            "species": species, "breed": None, "study_type_reported": publication_types,
            "intervention_category": target, "abstract": abstract or None,
            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "source_retrieval_date": retrieved_at,
            "search_query": query, "target_category": target, "target_species": target_species,
            "open_access_status": "unknown", "license": None, "full_text_available": False,
            "local_source_path": None, "source_sha256": None, "source_access_url": None, "metadata_path": None, "metadata_sha256": None,
        })
    return rows


def _primary(row: dict[str, Any], target_species: str) -> bool:
    types={value.lower() for value in row["study_type_reported"]}
    return bool(row["title"] and row["publication_date"] and row["species"] and not types & _EXCLUDED_PUBLICATION_TYPES and (target_species == "other" or target_species in row["species"]))


def _write_article_metadata(article: ET.Element, path: Path) -> None:
    """Write one original PubMed article record, not its unrelated EFetch batch."""
    path.write_bytes(_normalized_xml_bytes(article))


def _oa_info(pmcid: str, email: str | None, opener: Callable[[str], bytes] | None) -> tuple[str, str | None, str | None]:
    raw = _get(PMC_OA, {"id": pmcid}, email, opener); root=ET.fromstring(raw); record=root.find(".//record")
    if record is None: return "not_oa", None, None
    link = record.find("./link[@format='tgz']") or record.find("./link")
    return "oa", record.attrib.get("license"), (link.attrib.get("href") if link is not None else record.attrib.get("href"))


def _pmc_package_urls(href: str) -> tuple[str, ...]:
    """Return current HTTPS package URLs for an OA API link.

    PMC moved legacy individual article packages below ``deprecated/`` in August 2026
    while its legacy OA API continued to emit the prior FTP path during the transition.
    """
    https = href.replace("ftp://ftp.ncbi.nlm.nih.gov/", "https://ftp.ncbi.nlm.nih.gov/", 1)
    marker = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_package/"
    if https.startswith(marker):
        return (https, https.replace(marker, "https://ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/oa_package/", 1))
    return (https,)


def _download_pmc_package(href: str, opener: Callable[[str], bytes] | None) -> tuple[str, bytes]:
    """Download an authorized PMC package, including the documented legacy-path fallback."""
    request = opener or (lambda value: urllib.request.urlopen(value, timeout=60).read())
    last_error: Exception | None = None
    for url in _pmc_package_urls(href):
        try:
            return url, request(url)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _pmcid_number(pmcid: str) -> str:
    return pmcid[3:] if pmcid.upper().startswith("PMC") else pmcid


def _normalized_xml_bytes(element: ET.Element) -> bytes:
    """Serialize PMC XML with stable line endings and no trailing whitespace."""
    raw = ET.tostring(element, encoding="utf-8", xml_declaration=True).decode("utf-8")
    lines = [line.rstrip() for line in raw.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return ("\n".join(lines) + "\n").encode("utf-8")


def _oai_fulltext(pmcid: str, email: str | None, opener: Callable[[str], bytes] | None) -> tuple[str, bytes, str]:
    """Fetch reusable PMC full text through the current OAI-PMH endpoint."""
    params = {"verb": "GetRecord", "identifier": f"oai:pubmedcentral.nih.gov:{_pmcid_number(pmcid)}", "metadataPrefix": "pmc"}
    source_url = f"{PMC_OAI}?{urllib.parse.urlencode(params)}"
    request = opener or (lambda value: urllib.request.urlopen(value, timeout=60).read())
    raw = request(source_url)
    root = ET.fromstring(raw)
    error = next((element for element in root.iter() if element.tag.endswith("error")), None)
    if error is not None:
        raise OSError(_text(error) or "PMC OAI-PMH did not return reusable full text")
    article = next((element for element in root.iter() if element.tag.endswith("article")), None)
    if article is None:
        raise OSError("PMC OAI-PMH response did not include article XML")
    license_text = next((_text(element) for element in article.iter() if element.tag.endswith("license-p") and _text(element)), "")
    license_name = license_text or "PMC OAI-PMH reusable full text; see source XML permissions"
    return source_url, _normalized_xml_bytes(article), license_name


def acquire_corpus(output_dir: str | Path, email: str | None = None, cutoff: str | None = None, opener: Callable[[str], bytes] | None = None, sleep_seconds: float = 0.34) -> dict[str, Any]:
    """Acquire the fixed metadata corpus and rights-cleared PMC packages only."""
    root=Path(output_dir); sources=root/"sources"/"pmc"; metadata=root/"metadata"; sources.mkdir(parents=True,exist_ok=True); metadata.mkdir(parents=True,exist_ok=True)
    retrieved=date.today().isoformat(); selected=[]; used=set(); queries=[]; rejected=[]
    for target,count,target_species,query in TARGETS:
        term=f"({query}) NOT (review[Publication Type] OR editorial[Publication Type] OR comment[Publication Type])"
        ids=json.loads(_get(f"{EUTILS}/esearch.fcgi",{"db":"pubmed","term":term,"retmax":20,"retmode":"json","sort":"relevance"},email,opener))["esearchresult"]["idlist"]
        queries.append({"target_category":target,"target_count":count,"species":target_species,"query":term,"candidate_pmids":ids})
        if ids:
            raw=_get(f"{EUTILS}/efetch.fcgi",{"db":"pubmed","id":",".join(ids),"retmode":"xml"},email,opener)
            candidates=parse_pubmed_xml(raw,target,target_species,term,retrieved)
            articles = {article.findtext(".//PMID") or "": article for article in ET.fromstring(raw).findall(".//PubmedArticle")}
        else:
            candidates=[]
            articles = {}
        for row in candidates:
            if len([item for item in selected if item["target_category"]==target]) >= count: break
            if row["pmid"] in used: continue
            if not _primary(row,target_species):
                rejected.append({"pmid":row["pmid"],"target_category":target,"reason":"not a primary species-established candidate"}); continue
            if cutoff and row["publication_date"] > cutoff:
                rejected.append({"pmid":row["pmid"],"target_category":target,"reason":"after temporal cutoff"}); continue
            metadata_file=metadata/f"pubmed_{row['pmid']}.xml"; _write_article_metadata(articles[row["pmid"]], metadata_file)
            row["metadata_path"]=_portable_relative(metadata_file, root); row["metadata_sha256"]=sha256_file(metadata_file)
            if row["pmcid"]:
                try:
                    status,license_name,href=_oa_info(row["pmcid"],email,opener); row["open_access_status"]=status; row["license"]=license_name
                except (ET.ParseError, OSError, urllib.error.URLError):
                    status,license_name,href="unknown",None,None
                    row["open_access_status"]="unknown"
                if status=="oa" and href:
                    path=sources/f"{row['pmcid']}.tar.gz"
                    source_written = False
                    try:
                        download_url, payload = _download_pmc_package(href, opener)
                        row["source_access_url"] = download_url
                        path.write_bytes(payload)
                        source_written = True
                    except (OSError, urllib.error.URLError):
                        row["source_access_url"] = _pmc_package_urls(href)[-1]
                    if source_written:
                        row["license"] = license_name or "PMC Open Access Subset (license not supplied by OA service)"
                        row["full_text_available"]=True; row["local_source_path"]=_portable_relative(path, root); row["source_sha256"]=sha256_file(path)
                elif status=="unknown":
                    path=sources/f"{row['pmcid']}.nxml"
                    source_written = False
                    try:
                        source_url, payload, license_name = _oai_fulltext(row["pmcid"], email, opener)
                        row["open_access_status"]="oa"; row["license"]=license_name; row["source_access_url"]=source_url
                        path.write_bytes(payload)
                        source_written = True
                    except (ET.ParseError, OSError, urllib.error.URLError):
                        pass
                    if source_written:
                        row["full_text_available"]=True; row["local_source_path"]=_portable_relative(path, root); row["source_sha256"]=sha256_file(path)
            selected.append(row); used.add(row["pmid"])
        if sleep_seconds: time.sleep(sleep_seconds)
    selected_counts={target:sum(row["target_category"]==target for row in selected) for target,_,_,_ in TARGETS}
    registry_jsonl=root/"registry.jsonl"; write_jsonl(registry_jsonl,selected)
    with open(root/"registry.csv","w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=sorted({key for row in selected for key in row}),lineterminator="\n"); writer.writeheader()
        for row in selected: writer.writerow({key:json.dumps(value,ensure_ascii=False) for key,value in row.items()})
    manifest={"retrieved_at":retrieved,"source":"NCBI PubMed E-utilities","targets":queries,"selected_count":len(selected),"selected_counts":selected_counts,"rejected":rejected,"temporal_cutoff":cutoff}
    documented={row.get("local_source_path") for row in selected if row.get("local_source_path")}
    for file in sources.glob("*"):
        if _portable_relative(file, root) not in documented:
            file.unlink()
    write_json(root/"search_manifest.json",manifest)
    expected=sum(count for _,count,_,_ in TARGETS)
    if len(selected)!=expected:
        raise RuntimeError(f"corpus acquisition incomplete: selected {len(selected)} of required {expected} papers")
    return manifest


def validate_corpus(root: str | Path) -> list[dict[str, Any]]:
    """Return QC findings for registry provenance, eligibility, and downloaded-source integrity."""
    root=Path(root); rows=load_jsonl(root/"registry.jsonl"); errors=[]
    for field in ("pmid","doi"):
        values=[row.get(field) for row in rows if row.get(field)]
        if len(values)!=len(set(values)): errors.append({"field":field,"message":"duplicate identifier"})
    cutoff=json.loads((root/"search_manifest.json").read_text(encoding="utf-8")).get("temporal_cutoff")
    expected_total = sum(count for _, count, _, _ in TARGETS)
    if len(rows) != expected_total:
        errors.append({"field":"registry", "message":f"corpus does not contain the required {expected_total} papers"})
    for target, expected, _, _ in TARGETS:
        if sum(row.get("target_category") == target for row in rows) != expected:
            errors.append({"field":"target_category", "message":f"incorrect count for {target}"})
    for row in rows:
        paper_id=row.get("paper_id",row.get("pmid"))
        if not row.get("title"): errors.append({"paper_id":paper_id,"field":"title","message":"missing title"})
        if not row.get("publication_date"): errors.append({"paper_id":paper_id,"field":"publication_date","message":"missing publication date"})
        if not row.get("species"): errors.append({"paper_id":paper_id,"field":"species","message":"species cannot be established"})
        if not row.get("pubmed_url","" ).startswith("https://pubmed.ncbi.nlm.nih.gov/"): errors.append({"paper_id":paper_id,"field":"pubmed_url","message":"unknown source provenance"})
        if cutoff and row.get("publication_date") and row["publication_date"]>cutoff: errors.append({"paper_id":paper_id,"field":"publication_date","message":"after temporal cutoff"})
        path=row.get("local_source_path")
        if row.get("full_text_available") and not path:
            errors.append({"paper_id":paper_id,"field":"local_source_path","message":"full text is marked available without a local source"})
        if path:
            file=root/path
            if not row.get("full_text_available") or row.get("open_access_status")!="oa" or not row.get("license"): errors.append({"paper_id":paper_id,"field":"local_source_path","message":"local file lacks documented access/license status"})
            if not file.exists() or row.get("source_sha256")!=sha256_file(file): errors.append({"paper_id":paper_id,"field":"source_sha256","message":"downloaded source lacks valid checksum"})
        metadata_path=row.get("metadata_path")
        if not metadata_path:
            errors.append({"paper_id":paper_id,"field":"metadata_path","message":"missing original PubMed metadata provenance"})
        else:
            metadata_file=root/metadata_path
            if not metadata_file.exists() or row.get("metadata_sha256") != sha256_file(metadata_file):
                errors.append({"paper_id":paper_id,"field":"metadata_sha256","message":"metadata lacks valid checksum"})
    documented={row.get("local_source_path") for row in rows if row.get("local_source_path")}
    source_dir=root/"sources"/"pmc"
    if source_dir.exists():
        for file in source_dir.glob("*"):
            if file.relative_to(root).as_posix() not in documented:
                errors.append({"field":"local_source_path","message":"local source is not linked to a registry record"})
    return errors
