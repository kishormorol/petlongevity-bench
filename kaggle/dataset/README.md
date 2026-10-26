# PetLongevity-Bench (petbench) — v0.2 corpus and draft pairs

PetLongevity-Bench tests evidence-grounded reasoning about healthy aging in dogs and cats: can a model extract evidence with exact spans, judge whether a claim is supported, and avoid transferring findings across species or overclaiming from surrogate, correlational or protocol-only evidence?

This release is the **corpus and the review workspace**, not a finished gold set.

## What is here

- **100 PubMed papers** on dog and cat aging, longevity, nutrition, pharmacology, cognition and kidney disease, retrieved by fixed queries with a recorded cutoff and per-paper SHA-256.
- **300 candidate claim/evidence pairs**, three per paper. Each claim is a verbatim abstract sentence chosen by a keyword heuristic (findings and conclusions are preferred over background), anchored by exact character offsets.

## Important: the pair fields are placeholders

Every pair has `review_status = draft`. The annotation fields were filled **automatically from the paper's search category**, not by a person or a model reading the paper:

- `label` is `supported` for every pair and `evidence_strength` is `low` for every pair.
- `study_design`, `intervention_type`, `outcome`, `correlation_vs_causation` and `protocol_vs_results` are category defaults.

They exist so the schema and tooling can be exercised. **Do not train on them or score models against them as ground truth.** Blinded double human review and adjudication are in progress; reviewed pairs will ship in a later version.

What *is* reliable now: paper metadata, species from the registry, abstract text (where licensed), exact offsets and hashes.

## Files

| file | contents |
|---|---|
| `registry.csv` / `registry.jsonl` | one row per paper: PMID, DOI, title, journal, date, species, category, licence, `abstract_sha256`, and `abstract` where the licence allows |
| `claim_evidence_pairs.csv` / `.jsonl` | one row per candidate pair; JSONL keeps the nested review record |
| `manifest.json` | licence counts and the release policy |

## Licensing

PubMed abstracts belong to their publishers or authors. Abstract and claim text ship only for the **34 papers whose recorded licence is CC BY (102 pairs)**. For the other 66 papers (198 pairs) the abstract, `claim_text` and span text are withheld (`text_withheld = true`); offsets and `abstract_sha256` are kept, so you can fetch each abstract from PubMed by PMID and verify byte-for-byte that you have the same text. Each CC BY paper keeps its own licence and attribution (PMID/DOI in the registry). Metadata and annotation fields created for this release: CC0.

## Provenance

Papers were retrieved from PubMed through NCBI E-utilities using fixed category queries (stored per paper in the source repository's registry), with licence and open-access status captured at retrieval.

## Planned modules

M1 evidence extraction, M2 evidence judgment, M3 temporal prioritization under a pre-cutoff firewall, M4 biomarker forecasting.
