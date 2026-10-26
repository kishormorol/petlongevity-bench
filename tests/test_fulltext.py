from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path

import pytest

from petlongevity_bench.fulltext import extract_pmc_fulltext, fulltext_inventory, validate_fulltext_draft_submission, validate_fulltext_receipts, write_fulltext_annotation_worksheet, write_fulltext_queue
from petlongevity_bench.io import write_jsonl
from petlongevity_bench.review_portal import build_fulltext_review_portal


def _registry(path: Path) -> Path:
    registry = path / "registry.jsonl"
    write_jsonl(registry, [
        {"paper_id": "PMID:1", "pmid": "1", "pmcid": "PMC1", "title": "Open paper", "publication_date": "2020-01-01", "species": ["dog"], "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/1/", "license": "CC BY", "full_text_available": False, "local_source_path": None},
        {"paper_id": "PMID:2", "pmid": "2", "pmcid": None, "title": "Restricted paper", "publication_date": "2021-01-01", "species": ["cat"], "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/2/", "license": None, "full_text_available": False, "local_source_path": None},
    ])
    return registry


def test_fulltext_queue_distinguishes_access_paths(tmp_path: Path):
    registry = _registry(tmp_path)
    rows = fulltext_inventory(registry)
    assert [row["fulltext_status"] for row in rows] == ["pmc_access_to_confirm", "lawful_source_required"]
    result = write_fulltext_queue(registry, tmp_path / "queue")
    assert result == {"paper_count": 2, "local_rights_cleared": 0, "needs_access_confirmation": 1, "lawful_source_required": 1}
    assert (tmp_path / "queue" / "README.md").exists()


def test_fulltext_receipts_require_lawful_access_and_exact_text_checksum(tmp_path: Path):
    registry = _registry(tmp_path)
    source_root = tmp_path / "sources"; source_root.mkdir()
    source = source_root / "paper.txt"; source.write_text("reviewed full paper", encoding="utf-8")
    receipt = {"paper_id": "PMID:1", "lawful_access_basis": "pmc_open_access", "license_or_permission": "CC BY", "source_text_path": "paper.txt", "source_text_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "review_ready": True, "notes": "lawful source"}
    receipts = tmp_path / "receipts.jsonl"; write_jsonl(receipts, [receipt])
    assert validate_fulltext_receipts(receipts, registry, source_root) == []
    receipt["review_ready"] = False; write_jsonl(receipts, [receipt])
    assert any(error["path"] == "review_ready" for error in validate_fulltext_receipts(receipts, registry, source_root))
    write_jsonl(receipts, [])
    assert any(error["path"] == "receipts" for error in validate_fulltext_receipts(receipts, registry, source_root))
    receipt["review_ready"] = True; receipt["source_text_path"] = "../outside.txt"; write_jsonl(receipts, [receipt])
    assert any(error["path"] == "source_text_path" for error in validate_fulltext_receipts(receipts, registry, source_root))


def test_fulltext_draft_submission_requires_file(tmp_path: Path):
    with pytest.raises(ValueError, match="submission file is missing"):
        validate_fulltext_draft_submission(tmp_path / "missing.jsonl", tmp_path / "receipts.jsonl", tmp_path)


def test_extract_pmc_fulltext_writes_checksum_bound_receipt(tmp_path: Path):
    corpus = tmp_path / "corpus"; package_dir = corpus / "sources" / "pmc"; package_dir.mkdir(parents=True)
    nxml = tmp_path / "article.nxml"; nxml.write_text("<article><front><journal-meta><journal-title>Journal metadata</journal-title></journal-meta><article-meta><contrib>Author affiliation</contrib></article-meta></front><body><sec><title>Results</title><p>Exact result text. </p><table-wrap><label>Table 1</label><caption><p>Result counts</p></caption><table><tr><th>Group</th><th>Count</th></tr><tr><td>Dogs</td><td>12</td></tr></table></table-wrap></sec></body><back><ref-list><ref>Reference metadata</ref></ref-list></back></article>", encoding="utf-8")
    package = package_dir / "PMC1.tar.gz"
    with tarfile.open(package, "w:gz") as archive: archive.add(nxml, arcname="PMC1/article.nxml")
    registry = corpus / "registry.jsonl"
    write_jsonl(registry, [{"paper_id":"PMID:1","title":"Open paper","species":["dog"],"full_text_available":True,"local_source_path":"sources/pmc/PMC1.tar.gz","license":"CC BY","source_sha256":hashlib.sha256(package.read_bytes()).hexdigest()}])
    result = extract_pmc_fulltext(registry, corpus, tmp_path / "review")
    assert result == {"extracted": 1, "skipped_without_local_fulltext": 0}
    extracted = (tmp_path / "review" / "sources" / "PMID_1.txt").read_text(encoding="utf-8")
    assert extracted == "Results\n\nExact result text.\n\nTable 1 Result counts\nGroup | Count\nDogs | 12\n"
    assert "Journal metadata" not in extracted and "Author affiliation" not in extracted and "Reference metadata" not in extracted
    assert validate_fulltext_receipts(tmp_path / "review" / "fulltext_receipts.jsonl", registry, tmp_path / "review") == []
    assert write_fulltext_annotation_worksheet(registry, tmp_path / "review" / "fulltext_receipts.jsonl", tmp_path / "review", tmp_path / "review") == {"paper_rows": 1}
    worksheet = (tmp_path / "review" / "fulltext_annotation_worksheet.csv").read_text(encoding="utf-8")
    assert "Exact result text." not in worksheet and "PMID:1" in worksheet
    portal = tmp_path / "portal" / "index.html"
    assert build_fulltext_review_portal(registry, tmp_path / "review" / "fulltext_receipts.jsonl", tmp_path / "review", portal) == {"paper_count": 1}
    portal_html = portal.read_text(encoding="utf-8")
    assert "Exact result text." in portal_html
    assert "Use selected evidence" in portal_html and "Local-first: nothing is uploaded" in portal_html
    assert "How to annotate" in portal_html and "Pick a finding" in portal_html
    assert "Clean article body" in portal_html
    assert "Your only job: record what the paper says" in portal_html
    assert "annotation_walkthrough.mp4" in portal_html
    assert "Insufficient” is correct" in portal_html
    assert "The evidence location is captured automatically" in portal_html
    assert "Yes — the exact text says this" in portal_html
    assert "Ready to save this finding" in portal_html
    assert "join('\\n')+'\\n'" in portal_html
    submission = tmp_path / "clinician.jsonl"
    evidence_quote = "Exact result text."
    start = extracted.index(evidence_quote)
    draft = {"paper_id":"PMID:1","paper_title":"Open paper","species":"dog","source_text_path":"sources/PMID_1.txt","source_text_sha256":hashlib.sha256((tmp_path / "review" / "sources" / "PMID_1.txt").read_bytes()).hexdigest(),"reviewer_id":"clinician_01","source_section":"Results","start_char":start,"end_char":start + len(evidence_quote),"exact_evidence_quote":evidence_quote,"claim_text":"A result was reported.","draft_label":"supported","study_design":"controlled trial","outcome":"reported result","causal_interpretation":"not assessed","reviewer_notes":""}
    write_jsonl(submission, [draft])
    assert validate_fulltext_draft_submission(submission, tmp_path / "review" / "fulltext_receipts.jsonl", tmp_path / "review") == []
    draft["exact_evidence_quote"] = "invented quote"
    write_jsonl(submission, [draft])
    assert any(error["path"] == "exact_evidence_quote" for error in validate_fulltext_draft_submission(submission, tmp_path / "review" / "fulltext_receipts.jsonl", tmp_path / "review"))


def test_extract_pmc_fulltext_accepts_oai_article_xml(tmp_path: Path):
    corpus = tmp_path / "corpus"; package_dir = corpus / "sources" / "pmc"; package_dir.mkdir(parents=True)
    source = package_dir / "PMC1.nxml"
    source.write_text("<article><body><sec><title>Results</title><p>Direct reusable text.</p></sec></body></article>", encoding="utf-8")
    registry = corpus / "registry.jsonl"
    write_jsonl(registry, [{"paper_id":"PMID:1","title":"Open paper","species":["dog"],"full_text_available":True,"local_source_path":"sources/pmc/PMC1.nxml","license":"CC BY","source_sha256":hashlib.sha256(source.read_bytes()).hexdigest()}])
    assert extract_pmc_fulltext(registry, corpus, tmp_path / "review") == {"extracted": 1, "skipped_without_local_fulltext": 0}
    assert (tmp_path / "review" / "sources" / "PMID_1.txt").read_text(encoding="utf-8") == "Results\n\nDirect reusable text.\n"
