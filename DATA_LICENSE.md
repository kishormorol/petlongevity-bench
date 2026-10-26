# Data terms

The MIT licence in `LICENSE` covers the code. It does not cover the corpus,
because we do not own it.

## The corpus is third-party text

`data/corpus/` (in the working repository, not in this public one) holds verbatim PubMed abstracts. PubMed *citation metadata* is
freely redistributable; the **abstracts are not** — copyright rests with the
publisher or the authors, and it varies per paper. At retrieval the pipeline
records each paper's `license` string and `open_access_status` in
`data/corpus/registry.csv`, which is what lets a release make this distinction
per record rather than guessing for the whole set.

For the v0.2 corpus of 100 papers:

| licence family | papers | text redistributable |
|---|---|---|
| CC BY | 34 | yes |
| CC BY-NC | 11 | only under NonCommercial terms |
| CC BY-NC-ND | 12 | only under NonCommercial, NoDerivatives terms |
| none recorded | 39 | **no** |
| other (publisher permission notice) | 4 | **no** |

## What a release ships

`scripts/export_release.py` builds the redistributable bundle. By default it
ships abstract text and verbatim `evidence_quote` values **only** for CC BY
papers. Everything else carries the PMID, DOI, retrieval metadata and
`abstract_sha256` instead, so a user re-fetches the text themselves and can
verify byte-for-byte that they scored what we scored. Character offsets are
kept for every record, so annotations stay reproducible without the text.

`--allow-nc-nd` additionally ships NC/ND text. Think before using it: those
terms then bind everyone who downloads the benchmark, which is not what a
permissively licensed dataset implies.

## Attribution

Papers are attributed by PMID and DOI in the registry. Where a CC licence
applies, attribution is a condition of that licence, not a courtesy.
