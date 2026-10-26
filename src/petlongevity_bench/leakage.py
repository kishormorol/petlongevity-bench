from __future__ import annotations
from datetime import date, datetime
from .io import sha256_file

def _d(x):
    if isinstance(x,date): return x
    return datetime.strptime(str(x)[:10],"%Y-%m-%d").date()

def audit_sources(rows, cutoff, date_field="publication_date", strict=False):
    """Audit source dates and provenance without changing legacy non-strict behavior."""
    c=_d(cutoff); leaks=[]; missing=[]; missing_provenance=[]
    for i,r in enumerate(rows):
        source_id=r.get("source_id",i)
        raw=r.get("effective_date") or r.get(date_field)
        if not raw: missing.append(r.get("source_id",i)); continue
        try: d=_d(raw)
        except Exception: missing.append(r.get("source_id",i)); continue
        if not (r.get("provenance") or r.get("provenance_url") or r.get("source_url")):
            missing_provenance.append(source_id)
        if d>c: leaks.append({"source_id":source_id,"effective_date":str(d),"cutoff":str(c),"kind":"post_cutoff_source","severity":"error"})
    issues=list(leaks)
    severity="error" if strict else "warning"
    for source_id in missing:
        issues.append({"source_id":source_id,"kind":"missing_or_invalid_date","severity":severity})
    for source_id in missing_provenance:
        issues.append({"source_id":source_id,"kind":"missing_provenance","severity":severity})
    strict_failure=bool(leaks or (strict and (missing or missing_provenance)))
    return {"cutoff":str(c),"n_sources":len(rows),"strict":bool(strict),
      "post_cutoff_leakage_detected":bool(leaks),"n_leaks":len(leaks),"leaks":leaks,
      "missing_or_invalid_dates":missing,"missing_provenance":missing_provenance,
      "issues":issues,"leakage_free":not strict_failure}

def make_run_metadata(model_name, model_version, run_date, prompt_file, corpus_snapshot_date, candidate_file, database_versions, internet_access, leakage_report, closed_model_pretraining_risk="unknown"):
    return {"model_name":model_name,"model_version":model_version,"run_date":run_date,
      "prompt_hash":sha256_file(prompt_file) if prompt_file else None,
      "corpus_snapshot_date":corpus_snapshot_date,
      "candidate_universe_hash":sha256_file(candidate_file) if candidate_file else None,
      "database_versions":database_versions,"internet_access":bool(internet_access),
      "post_cutoff_leakage_detected":bool(leakage_report.get("post_cutoff_leakage_detected",False)),
      "temporal_leakage_status":"leakage_free" if leakage_report.get("leakage_free") else "leakage_detected",
      "closed_model_pretraining_risk":closed_model_pretraining_risk}
