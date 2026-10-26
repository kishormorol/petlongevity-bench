# M4 Biomarker Forecasting Prompt

Using only pre-cutoff evidence, rank candidate biomarkers/pathways for later association with dog/cat biological aging, mortality, or healthspan.

For each feature output:
- feature_id
- score in [0,1]
- direction: increase | decrease | mixed | unknown
- cross_species_concordant: boolean or null
- concise rationale grounded in supplied evidence
