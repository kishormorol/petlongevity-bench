from __future__ import annotations
import math
from collections import Counter
from .text import norm, token_f1

TEXT_FUZZY_FIELDS={"age_description","intervention_or_exposure","comparator","endpoint","effect_size_text","adverse_events_text","mechanism_claimed","funding_or_conflict","supporting_span","notes","breed"}


def _index(rows,key): return {r[key]:r for r in rows}

def safe_div(a,b): return a/b if b else 0.0

def macro_f1_labels(y_true,y_pred,labels):
    vals=[]
    for lab in labels:
        tp=sum(t==lab and p==lab for t,p in zip(y_true,y_pred))
        fp=sum(t!=lab and p==lab for t,p in zip(y_true,y_pred))
        fn=sum(t==lab and p!=lab for t,p in zip(y_true,y_pred))
        pr=safe_div(tp,tp+fp); rc=safe_div(tp,tp+fn)
        vals.append(safe_div(2*pr*rc,pr+rc))
    return sum(vals)/len(vals) if vals else 0.0


def score_m1(gold,pred, id_key="record_id"):
    G,P=_index(gold,id_key),_index(pred,id_key)
    ids=sorted(G.keys() & P.keys())
    if not ids: raise ValueError("No overlapping record_id values")
    required_fields=[k for k in gold[0].keys() if k not in {id_key,"notes"}]
    f_scores=[]; hallucinated=0; possible_hall=0
    species_ok=direction_ok=0
    span_scores=[]
    per_record=[]
    for rid in ids:
        g,p=G[rid],P[rid]; fields=[]
        for k in required_fields:
            gv,pv=g.get(k),p.get(k)
            if k in TEXT_FUZZY_FIELDS: s=token_f1(gv,pv)
            else: s=float(norm(gv)==norm(pv))
            f_scores.append(s); fields.append(s)
            if gv in (None,"",[]) and pv not in (None,"",[]): hallucinated+=1
            if gv in (None,"",[]): possible_hall+=1
        species_ok += int(norm(g.get("species"))==norm(p.get("species")))
        direction_ok += int(norm(g.get("result_direction"))==norm(p.get("result_direction")))
        span_scores.append(token_f1(g.get("supporting_span"),p.get("supporting_span")))
        per_record.append({"record_id":rid,"field_mean":sum(fields)/len(fields)})
    return {
      "n_gold":len(G),"n_pred":len(P),"n_scored":len(ids),"coverage":len(ids)/len(G),
      "field_macro_f1":sum(f_scores)/len(f_scores),
      "species_accuracy":species_ok/len(ids),
      "outcome_direction_accuracy":direction_ok/len(ids),
      "citation_span_support":sum(span_scores)/len(span_scores),
      "hallucinated_field_rate":safe_div(hallucinated,possible_hall),
      "per_record":per_record,
    }


def score_m2(gold,pred,id_key="item_id"):
    G,P=_index(gold,id_key),_index(pred,id_key); ids=sorted(G.keys()&P.keys())
    if not ids: raise ValueError("No overlapping item_id values")
    labels=["supported","contradicted","insufficient"]
    yt=[G[i]["label"] for i in ids]; yp=[P[i]["label"] for i in ids]
    fp_species=species_traps=0; overclaim=surrogate_traps=0; risk_num=risk_den=0.0
    for i in ids:
        g,p=G[i],P[i]
        if g.get("trap_type")=="species_transfer":
            species_traps+=1; fp_species+=int(p["label"]=="supported" and g["label"]!="supported")
        if g.get("trap_type")=="surrogate_overclaim":
            surrogate_traps+=1; overclaim+=int(p["label"]=="supported" and g["label"]!="supported")
        w=float(g.get("risk_weight",1.0)); risk_den+=w
        risk_num += w*int(p["label"]=="supported" and g["label"]!="supported")
    return {"n_scored":len(ids),"coverage":len(ids)/len(G),"macro_f1":macro_f1_labels(yt,yp,labels),
      "species_transfer_false_positive_rate":safe_div(fp_species,species_traps),
      "surrogate_overclaim_rate":safe_div(overclaim,surrogate_traps),
      "risk_weighted_unsupported_claim_rate":safe_div(risk_num,risk_den)}


def dcg(rels): return sum((2**r-1)/math.log2(i+2) for i,r in enumerate(rels))
def score_ranking(gold_positive_ids, ranked_ids, ks=(10,20,50)):
    pos=set(gold_positive_ids); ranked=list(ranked_ids); out={}
    for k in ks:
        out[f"recall_at_{k}"]=safe_div(len(pos & set(ranked[:k])),len(pos))
    rr=0.0
    for i,x in enumerate(ranked,1):
        if x in pos: rr=1/i; break
    rel=[1 if x in pos else 0 for x in ranked]
    ideal=sorted(rel,reverse=True)
    out["mrr"]=rr; out["ndcg"]=safe_div(dcg(rel),dcg(ideal)) if ideal else 0.0
    return out


def expected_calibration_error(rows,bins=10):
    buckets=[[] for _ in range(bins)]
    for r in rows:
        c=max(0.0,min(1.0,float(r["confidence"]))); y=int(bool(r["is_positive"]))
        idx=min(bins-1,int(c*bins)); buckets[idx].append((c,y))
    n=max(1,len(rows)); e=0.0
    for b in buckets:
        if b:
            conf=sum(x for x,_ in b)/len(b); acc=sum(y for _,y in b)/len(b)
            e += len(b)/n*abs(acc-conf)
    return e


def score_m3(gold,pred,id_key="candidate_id"):
    positives=[r[id_key] for r in gold if bool(r.get("future_positive"))]
    ranked=sorted(pred,key=lambda r:float(r.get("score",0)),reverse=True)
    out=score_ranking(positives,[r[id_key] for r in ranked])
    if all("confidence" in r for r in ranked):
        G=_index(gold,id_key)
        cal=[{"confidence":r["confidence"],"is_positive":bool(G.get(r[id_key],{}).get("future_positive",False))} for r in ranked if r[id_key] in G]
        out["calibration_error"]=expected_calibration_error(cal)
    out["n_candidates_ranked"]=len(ranked); out["n_future_positives"]=len(positives)
    return out


def score_m4(gold,pred,id_key="feature_id"):
    positives=[r[id_key] for r in gold if bool(r.get("future_reported"))]
    ranked=sorted(pred,key=lambda r:float(r.get("score",0)),reverse=True)
    out=score_ranking(positives,[r[id_key] for r in ranked])
    G=_index(gold,id_key); dirs=[]; cross=[]
    for r in ranked:
        g=G.get(r[id_key]);
        if not g: continue
        if g.get("direction") and r.get("direction"): dirs.append(norm(g["direction"])==norm(r["direction"]))
        if "cross_species_concordant" in g and "cross_species_concordant" in r: cross.append(bool(g["cross_species_concordant"])==bool(r["cross_species_concordant"]))
    out["direction_agreement"]=safe_div(sum(dirs),len(dirs)); out["cross_species_concordance_accuracy"]=safe_div(sum(cross),len(cross))
    return out
