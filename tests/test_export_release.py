import csv
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_release.py"
spec = importlib.util.spec_from_file_location("export_release", SCRIPT)
export_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_release)

OPEN_TEXT = "Open abstract. Cats lived longer on diet A."
CLOSED_TEXT = "Closed abstract. Dogs given drug B walked further."


def _registry(path: Path) -> None:
    fields = ["pmid", "abstract", "license", "open_access_status", "title"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fields)
        writer.writeheader()
        writer.writerow({"pmid": "1", "abstract": OPEN_TEXT, "license": "CC BY 4.0", "open_access_status": "oa", "title": "a"})
        writer.writerow({"pmid": "2", "abstract": CLOSED_TEXT, "license": "", "open_access_status": "unknown", "title": "b"})


def _export(tmp_path: Path, annotations: list[dict], monkeypatch) -> list[dict]:
    registry = tmp_path / "registry.csv"
    ann_file = tmp_path / "annotations.jsonl"
    out = tmp_path / "release"
    _registry(registry)
    ann_file.write_text("".join(json.dumps(a) + "\n" for a in annotations), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["export_release.py", "--registry", str(registry), "--annotations", str(ann_file), "--output", str(out)])
    assert export_release.main() == 0
    return [json.loads(line) for line in (out / "annotations.jsonl").open(encoding="utf-8")]


def test_v01_quote_follows_licence(tmp_path, monkeypatch):
    rows = _export(tmp_path, [
        {"pmid": "1", "evidence_quote": "Cats lived longer on diet A.", "claim_text": "Cats lived longer on diet A."},
        {"pmid": "2", "evidence_quote": "Dogs given drug B walked further.", "claim_text": "Dogs given drug B walked further."},
    ], monkeypatch)
    assert rows[0]["evidence_quote"] == "Cats lived longer on diet A."
    assert rows[1]["evidence_quote"] is None
    assert rows[1]["claim_text"] is None


def test_draft_pairs_withhold_claim_and_span_text(tmp_path, monkeypatch):
    span = {"text": "Dogs given drug B walked further.", "start_char": 17, "end_char": 50}
    rows = _export(tmp_path, [
        {"paper_id": "PMID:1", "claim_text": "Cats lived longer on diet A.", "supporting_span": {"text": "Cats lived longer on diet A.", "start_char": 15, "end_char": 43}, "source_text_path": "../x.txt"},
        {"paper_id": "PMID:2", "claim_text": "Dogs given drug B walked further.", "supporting_span": span, "source_text_path": "../y.txt"},
    ], monkeypatch)
    assert rows[0]["claim_text"] == "Cats lived longer on diet A."
    assert rows[1]["claim_text"] is None
    assert rows[1]["supporting_span"] == {"text": None, "start_char": 17, "end_char": 50}
    assert all("source_text_path" not in r for r in rows)
    released = "".join(json.dumps(r) for r in rows)
    assert "walked further" not in released
