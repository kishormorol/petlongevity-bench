from __future__ import annotations
import json, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from .io import write_jsonl
BASE="https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

def _get(endpoint, params, api_key=None, tool="petlongevity_bench", email=None):
    p=dict(params); p["tool"]=tool
    if email: p["email"]=email
    if api_key: p["api_key"]=api_key
    url=f"{BASE}/{endpoint}?{urllib.parse.urlencode(p)}"
    with urllib.request.urlopen(url,timeout=60) as r: return r.read()

def search_pmids(query, cutoff, retmax=1000, api_key=None, email=None):
    term=f'({query}) AND ("0001/01/01"[Date - Publication] : "{cutoff}"[Date - Publication])'
    raw=_get("esearch.fcgi",{"db":"pubmed","term":term,"retmode":"json","retmax":retmax,"sort":"pub date"},api_key,email=email)
    return json.loads(raw)["esearchresult"]["idlist"]

def fetch_records(pmids, api_key=None, email=None):
    if not pmids: return []
    raw=_get("efetch.fcgi",{"db":"pubmed","id":",".join(pmids),"retmode":"xml"},api_key,email=email)
    root=ET.fromstring(raw); out=[]
    for art in root.findall(".//PubmedArticle"):
        pmid=art.findtext(".//PMID")
        title="".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else ""
        abstract=" ".join("".join(x.itertext()) for x in art.findall(".//Abstract/AbstractText"))
        year=art.findtext(".//PubDate/Year") or art.findtext(".//ArticleDate/Year") or ""
        month=art.findtext(".//PubDate/Month") or "01"; day=art.findtext(".//PubDate/Day") or "01"
        # Conservative ISO date. If PubMed has only year, Jan 1 avoids falsely flagging a post-cutoff leak within the same year.
        try:
            m=int(month) if month.isdigit() else 1; d=int(day) if day.isdigit() else 1; pubdate=f"{int(year):04d}-{m:02d}-{d:02d}" if year else None
        except Exception: pubdate=f"{year}-01-01" if year else None
        doi=None
        for aid in art.findall(".//ArticleId"):
            if aid.attrib.get("IdType")=="doi": doi=aid.text
        out.append({"source_id":f"PMID:{pmid}","pmid":pmid,"doi":doi,"publication_date":pubdate,"provenance_url":f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/","title":title,"abstract":abstract})
    return out

def snapshot(query, cutoff, output, retmax=1000, api_key=None, email=None):
    pmids=search_pmids(query,cutoff,retmax,api_key,email); rows=[]
    for i in range(0,len(pmids),200):
        rows.extend(fetch_records(pmids[i:i+200],api_key,email));
        if i+200<len(pmids): time.sleep(0.34 if not api_key else 0.12)
    write_jsonl(output,rows)
    meta={"query":query,"cutoff":cutoff,"retrieved":date.today().isoformat(),"n":len(rows),"source":"NCBI PubMed E-utilities"}
    Path(str(output)+".meta.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    return meta
