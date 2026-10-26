# Architecture

PetLongevity-Bench separates **generation** from **evaluation**.

```text
source snapshots / paper excerpts / candidate universe
                    |
                    v
          B0/B1/B2/B3 system under test
                    |
                    v
        prediction JSONL + run manifest
                    |
                    v
       schema validation + leakage audit
                    |
                    v
          M1/M2/M3/M4 deterministic scores
                    |
                    v
             reproducible report
```

## Modules

### M1 Evidence extraction
Input: a paper or licensed excerpt.
Output: structured evidence record.
Primary risks: hallucinated fields, species mistakes, incorrect result direction, unsupported citation spans.

### M2 Evidence judgment
Input: a claim plus evidence context.
Output: supported / contradicted / insufficient plus direct-species and endpoint/protocol flags.
Primary risks: species transfer, surrogate-to-lifespan causal leaps, trial-protocol-to-efficacy claims.

### M3 Temporal prioritization
Input: cutoff-constrained corpus + frozen candidate universe.
Output: ranked candidates.
Primary risks: future leakage, treating unknown candidates as negatives, popularity bias.

### M4 Biomarker forecasting
Input: pre-cutoff omics/clinical evidence and candidate features.
Output: ranked future biomarkers with direction and cross-species fields.
Primary risks: post-hoc leakage, correlation/causation confusion, feature aliasing.

## Baselines
- B0: plain model.
- B1: model + cutoff-constrained literature retrieval.
- B2: B1 + species-aware knowledge graph.
- B3: B2 + deterministic tools + evidence verifier.

Core scoring must not know or care which provider produced the predictions.
