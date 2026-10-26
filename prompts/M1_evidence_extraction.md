# M1 Evidence Extraction Prompt

You are extracting evidence for a scientific benchmark. Use ONLY the supplied source text.

Return exactly one JSON object conforming to `schemas/evidence_schema.json`.

Rules:
1. Never infer dog evidence from another species.
2. A protocol/design paper is not an efficacy result.
3. Association is not causation.
4. Use `null` when a field is not supported by the supplied text.
5. `supporting_span` must be a short verbatim span from the supplied text that supports the principal result classification.
6. Do not invent identifiers, sample sizes, effects, adverse events, or mechanisms.
