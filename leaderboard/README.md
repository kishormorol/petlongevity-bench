# Leaderboard portal

`index.html` is a static, dependency-free portal built from `submissions.jsonl` and the current human-review status.

```bash
PYTHONPATH=src python scripts/build_leaderboard.py
```

One JSON object per line must include `submission_id`, `system_name`, `system_version`, `baseline`, `modules`, `primary_metric`, `primary_score`, `dataset_version`, `run_manifest_sha256`, `evaluated_at`, and `status`.

Valid statuses are `pending`, `verified`, and `rejected`. Only `verified` rows receive a rank; do not upload synthetic demo scores as benchmark results. A verified submission needs a reproducible run manifest and completed provenance/leakage review.
