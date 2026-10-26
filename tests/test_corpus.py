from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from petlongevity_bench import corpus
from petlongevity_bench.corpus import _download_pmc_package, acquire_corpus, parse_pubmed_xml, validate_corpus
from petlongevity_bench.io import load_jsonl, sha256_file, write_json, write_jsonl


ARTICLE = b"""<?xml version='1.0' encoding='UTF-8'?>
<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>12345</PMID><Article>
<Journal><JournalIssue><PubDate><Year>2020</Year><Month>04</Month><Day>02</Day></PubDate></JournalIssue><Title>Journal of Canine Science</Title></Journal>
<ArticleTitle>Canine aging biomarker study</ArticleTitle><Abstract><AbstractText>Older dogs had a measured biomarker endpoint.</AbstractText></Abstract>
<AuthorList><Author><ForeName>Ada</ForeName><LastName>Researcher</LastName></Author></AuthorList>
<PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList></Article></MedlineCitation>
<PubmedData><ArticleIdList><ArticleId IdType='pubmed'>12345</ArticleId><ArticleId IdType='pmc'>PMC12345</ArticleId><ArticleId IdType='doi'>10.1000/example</ArticleId></ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>"""


def _network(oa: bool = True):
    def opener(url: str) -> bytes:
        if "esearch.fcgi" in url:
            return b'{"esearchresult":{"idlist":["12345"]}}'
        if "efetch.fcgi" in url:
            return ARTICLE
        if "oa.fcgi" in url:
            return (b"<OA><records><record license='CC BY 4.0' href='https://example.test/PMC12345.tar.gz'/></records></OA>" if oa else b"<OA><records/></OA>")
        if url == "https://example.test/PMC12345.tar.gz":
            return b"rights-cleared-pmc-package"
        raise AssertionError(url)
    return opener


def _network_oai_fallback():
    def opener(url: str) -> bytes:
        if "esearch.fcgi" in url:
            return b'{"esearchresult":{"idlist":["12345"]}}'
        if "efetch.fcgi" in url:
            return ARTICLE
        if "oa.fcgi" in url:
            raise urllib.error.HTTPError(url, 404, "retired", {}, None)
        if "api/oai/v1/mh/" in url:
            return b"""<OAI-PMH><GetRecord><record><metadata><article>
            <front><article-meta><permissions><license><license-p>CC BY test license</license-p></license></permissions></article-meta></front>
            <body><sec><title>Results</title><p>Reusable article text.</p></sec></body>
            </article></metadata></record></GetRecord></OAI-PMH>"""
        raise AssertionError(url)
    return opener


def _network_oai_unavailable():
    def opener(url: str) -> bytes:
        if "esearch.fcgi" in url:
            return b'{"esearchresult":{"idlist":["12345"]}}'
        if "efetch.fcgi" in url:
            return ARTICLE
        if "oa.fcgi" in url:
            raise urllib.error.HTTPError(url, 404, "retired", {}, None)
        if "api/oai/v1/mh/" in url:
            raise urllib.error.URLError("offline")
        raise AssertionError(url)
    return opener


def _target(monkeypatch: pytest.MonkeyPatch, count: int = 1) -> None:
    monkeypatch.setattr(corpus, "TARGETS", (("test_dog", count, "dog", "dog aging"),))


def test_pmcid_metadata_parsing() -> None:
    row = parse_pubmed_xml(ARTICLE, "test", "dog", "dog aging", "2026-08-19")[0]
    assert row["pmid"] == "12345"
    assert row["pmcid"] == "PMC12345"
    assert row["doi"] == "10.1000/example"
    assert row["publication_date"] == "2020-04-02"
    assert row["species"] == ["dog"]


def test_acquisition_serializes_registry_and_downloads_pmc_oa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _target(monkeypatch)
    manifest = acquire_corpus(tmp_path, opener=_network(), sleep_seconds=0)
    row = load_jsonl(tmp_path / "registry.jsonl")[0]
    assert manifest["selected_count"] == 1
    assert row["open_access_status"] == "oa"
    assert row["local_source_path"] == "sources/pmc/PMC12345.tar.gz"
    assert (tmp_path / row["local_source_path"]).read_bytes() == b"rights-cleared-pmc-package"
    assert row["source_sha256"] == sha256_file(tmp_path / row["local_source_path"])
    assert b"\r\n" not in (tmp_path / "registry.csv").read_bytes()
    assert not validate_corpus(tmp_path)


def test_acquisition_uses_pmc_oai_when_legacy_oa_service_is_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _target(monkeypatch)
    acquire_corpus(tmp_path, opener=_network_oai_fallback(), sleep_seconds=0)
    row = load_jsonl(tmp_path / "registry.jsonl")[0]
    assert row["open_access_status"] == "oa"
    assert row["license"] == "CC BY test license"
    assert row["source_access_url"].startswith("https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/")
    assert row["local_source_path"] == "sources/pmc/PMC12345.nxml"
    assert (tmp_path / row["local_source_path"]).read_text(encoding="utf-8").startswith("<?xml")
    assert not validate_corpus(tmp_path)


def test_acquisition_does_not_link_stale_pmc_source_after_current_lookup_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _target(monkeypatch)
    stale = tmp_path / "sources" / "pmc" / "PMC12345.nxml"
    stale.parent.mkdir(parents=True)
    stale.write_text("<article><body><p>old text</p></body></article>", encoding="utf-8")
    acquire_corpus(tmp_path, opener=_network_oai_unavailable(), sleep_seconds=0)
    row = load_jsonl(tmp_path / "registry.jsonl")[0]
    assert row["local_source_path"] is None
    assert not row["full_text_available"]
    assert not stale.exists()
    assert not validate_corpus(tmp_path)


def test_non_oa_record_keeps_metadata_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _target(monkeypatch)
    acquire_corpus(tmp_path, opener=_network(oa=False), sleep_seconds=0)
    row = load_jsonl(tmp_path / "registry.jsonl")[0]
    assert row["open_access_status"] == "not_oa"
    assert not row["full_text_available"]
    assert row["local_source_path"] is None
    assert (tmp_path / row["metadata_path"]).exists()


def test_pmc_package_download_uses_documented_deprecated_path_after_404() -> None:
    old = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_package/ba/5b/PMC1.tar.gz"
    current = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/oa_package/ba/5b/PMC1.tar.gz"
    def opener(url: str) -> bytes:
        if url == old:
            raise urllib.error.HTTPError(url, 404, "gone", {}, None)
        assert url == current
        return b"current package"
    url, package = _download_pmc_package(old.replace("https://", "ftp://"), opener)
    assert url == current and package == b"current package"


def test_validation_detects_duplicate_provenance_cutoff_and_checksum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _target(monkeypatch)
    acquire_corpus(tmp_path, cutoff="2021-01-01", opener=_network(), sleep_seconds=0)
    row = load_jsonl(tmp_path / "registry.jsonl")[0]
    duplicate = dict(row)
    duplicate["paper_id"] = "PMID:duplicate"
    duplicate["publication_date"] = "2022-01-01"
    duplicate["pubmed_url"] = "https://untrusted.example/paper"
    write_jsonl(tmp_path / "registry.jsonl", [row, duplicate])
    source = tmp_path / row["local_source_path"]
    source.write_bytes(b"tampered")
    errors = validate_corpus(tmp_path)
    messages = {error["message"] for error in errors}
    assert "duplicate identifier" in messages
    assert "unknown source provenance" in messages
    assert "after temporal cutoff" in messages
    assert "downloaded source lacks valid checksum" in messages


def test_validation_rejects_missing_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _target(monkeypatch)
    acquire_corpus(tmp_path, opener=_network(oa=False), sleep_seconds=0)
    row = load_jsonl(tmp_path / "registry.jsonl")[0]
    row["metadata_path"] = None
    write_jsonl(tmp_path / "registry.jsonl", [row])
    assert any(error["message"] == "missing original PubMed metadata provenance" for error in validate_corpus(tmp_path))
