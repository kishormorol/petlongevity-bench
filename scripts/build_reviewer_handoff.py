#!/usr/bin/env python3
"""Build local reviewer handoff ZIP packets from blinded abstract-review files."""
from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path


def _write_readme(path: Path, reviewer_slot: str) -> None:
    output_name = f"{reviewer_slot}.jsonl"
    lane = "LLM-assisted silver benchmark" if reviewer_slot == "llm_reviewer" else "human review"
    path.write_text(
        f"""# PetLongevity-Bench Abstract Review Handoff

Reviewer slot: `{reviewer_slot}`
Benchmark lane: {lane}

Open `reviewer_abstracts.html` in a browser, complete every item, then click `Download JSONL`.
Rename the downloaded file to `{output_name}` before returning it to the coordinator.

Rules:

- Work independently.
- Do not view the other reviewer's submission.
- Use only the evidence shown in the blinded review page.
- Mark `Exact Quote Verified` as `yes` only when the quote matches the displayed source text.
- This is research annotation only, not veterinary advice.
- The `llm_reviewer` slot can promote a `silver` benchmark with one human reviewer, but cannot promote `gold`.

Coordinator validation command:

```bash
petbench validate-research-review --submission {output_name} --review-dir review/abstracts_300
petbench import-research-review --submission {output_name} --reviewer-slot {reviewer_slot} --review-dir review/abstracts_300
```
""",
        encoding="utf-8",
        newline="\n",
    )


def build(review_dir: Path, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    required = ["reviewer_abstracts.html", "reviewer_packet_blinded.jsonl", "reviewer_packet_blinded.csv"]
    missing = [name for name in required if not (review_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"missing blinded review files: {', '.join(missing)}")
    packets: dict[str, str] = {}
    for slot in ("reviewer_a", "reviewer_b", "llm_reviewer"):
        work = output_dir / slot
        if work.exists():
            shutil.rmtree(work)
        work.mkdir()
        for name in required:
            shutil.copy2(review_dir / name, work / name)
        _write_readme(work / "README.md", slot)
        zip_path = output_dir / f"{slot}_packet.zip"
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(work.iterdir()):
                archive.write(file, arcname=file.name)
        shutil.rmtree(work)
        packets[slot] = str(zip_path)
    return packets


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-dir", default="review/abstracts_300")
    parser.add_argument("--output-dir", default="review/abstracts_300/handoff")
    args = parser.parse_args()
    for slot, path in build(Path(args.review_dir), Path(args.output_dir)).items():
        print(f"{slot}: {path}")
