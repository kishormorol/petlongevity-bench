from petlongevity_bench.io import load_jsonl
from petlongevity_bench.metrics import score_m1,score_m2,score_m3,score_m4
from petlongevity_bench.leakage import audit_sources
from pathlib import Path
BASE=Path(__file__).parents[1]/"data"/"demo"
def test_m1_perfect():
    s=score_m1(load_jsonl(BASE/"m1_gold.jsonl"),load_jsonl(BASE/"m1_pred_perfect.jsonl")); assert s["field_macro_f1"]==1 and s["species_accuracy"]==1

def test_m2_perfect():
    s=score_m2(load_jsonl(BASE/"m2_gold.jsonl"),load_jsonl(BASE/"m2_pred_perfect.jsonl")); assert s["macro_f1"]==1 and s["risk_weighted_unsupported_claim_rate"]==0

def test_m3():
    s=score_m3(load_jsonl(BASE/"m3_gold.jsonl"),load_jsonl(BASE/"m3_pred.jsonl")); assert s["recall_at_10"]==1 and s["mrr"]==1

def test_m4():
    s=score_m4(load_jsonl(BASE/"m4_gold.jsonl"),load_jsonl(BASE/"m4_pred.jsonl")); assert s["recall_at_10"]==1 and s["direction_agreement"]>0.6

def test_leakage():
    s=audit_sources(load_jsonl(BASE/"sources.jsonl"),"2016-12-31"); assert s["n_leaks"]==1 and s["post_cutoff_leakage_detected"]
