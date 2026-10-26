from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from .io import export_jsonl_csv, import_csv_jsonl, load_jsonl, write_json
from .schema import validate_records
from .metrics import score_m1, score_m2, score_m3, score_m4
from .leakage import audit_sources
from .pubmed import snapshot
from .datasets import agreement_m2, validate_dataset, validate_research_dataset
from .temporal import audit_snapshot, freeze_snapshot
from .runner import run_offline
from .kg import load_graph
from .agent import run_b3_offline
from .annotations_v01 import validate_annotations
from .review import freeze_gate
from .llm_review import assemble_llm_review_submission, build_llm_review_prompts
from .fulltext import extract_pmc_fulltext, validate_fulltext_receipts, write_fulltext_annotation_worksheet, write_fulltext_queue
from .research_review import (
    adjudicate_llm_review,
    adjudicate_research_review,
    build_llm_adjudication_queue,
    build_research_adjudication_queue,
    export_m2_baseline_splits,
    import_research_review,
    llm_review_status,
    prepare_research_review,
    promote_research_gold,
    promote_research_silver,
    research_review_status,
    validate_llm_adjudication_submission,
    validate_research_adjudication_submission,
    validate_research_review_submission,
)

def _emit(obj,out=None):
    txt=json.dumps(obj,indent=2,sort_keys=True)
    if out: Path(out).write_text(txt+"\n",encoding="utf-8")
    print(txt)

def main(argv=None):
    p=argparse.ArgumentParser(prog="petbench",description="PetLongevity-Bench v0.2")
    sp=p.add_subparsers(dest="cmd",required=True)
    v=sp.add_parser("validate"); v.add_argument("--data",required=True); v.add_argument("--schema",required=True)
    d=sp.add_parser("validate-dataset"); d.add_argument("--manifest",required=True); d.add_argument("--records")
    rd=sp.add_parser("validate-research-dataset"); rd.add_argument("--manifest",required=True)
    av=sp.add_parser("validate-annotations-v01"); av.add_argument("--annotations",required=True); av.add_argument("--registry",required=True)
    rs=sp.add_parser("review-status"); rs.add_argument("--annotations",default="data/gold/v0_1/annotations.jsonl"); rs.add_argument("--registry",default="data/corpus/registry.jsonl"); rs.add_argument("--review-dir",default="review")
    rr=sp.add_parser("prepare-research-review"); rr.add_argument("--manifest",required=True); rr.add_argument("--output-dir",required=True); rr.add_argument("--corpus-registry",default="data/corpus/registry.jsonl"); rr.add_argument("--split-seed")
    rrs=sp.add_parser("research-review-status"); rrs.add_argument("--review-dir",required=True)
    lrs=sp.add_parser("llm-review-status"); lrs.add_argument("--review-dir",required=True); lrs.add_argument("--human-slot",choices=["reviewer_a","reviewer_b"],default="reviewer_a")
    vrr=sp.add_parser("validate-research-review"); vrr.add_argument("--submission",required=True); vrr.add_argument("--review-dir",required=True)
    irr=sp.add_parser("import-research-review"); irr.add_argument("--submission",required=True); irr.add_argument("--reviewer-slot",choices=["reviewer_a","reviewer_b","llm_reviewer"],required=True); irr.add_argument("--review-dir",required=True)
    bra=sp.add_parser("build-research-adjudication-queue"); bra.add_argument("--review-dir",required=True)
    bla=sp.add_parser("build-llm-adjudication-queue"); bla.add_argument("--review-dir",required=True); bla.add_argument("--human-slot",choices=["reviewer_a","reviewer_b"],default="reviewer_a")
    blp=sp.add_parser("build-llm-review-prompts"); blp.add_argument("--review-dir",default="review/abstracts_300"); blp.add_argument("--output-dir",default="review/abstracts_300/llm_prompts"); blp.add_argument("--max-pairs-per-prompt",type=int,default=20); blp.add_argument("--reviewer-id",default="llm-reviewer")
    alp=sp.add_parser("assemble-llm-review-submission"); alp.add_argument("--review-dir",default="review/abstracts_300"); alp.add_argument("--responses-dir",default="review/abstracts_300/llm_prompts/responses"); alp.add_argument("--response",action="append",default=[]); alp.add_argument("--output",default="review/abstracts_300/llm_reviewer.jsonl"); alp.add_argument("--reviewer-id",default="llm-reviewer")
    vra=sp.add_parser("validate-research-adjudication"); vra.add_argument("--submission",required=True); vra.add_argument("--review-dir",required=True)
    vla=sp.add_parser("validate-llm-adjudication"); vla.add_argument("--submission",required=True); vla.add_argument("--review-dir",required=True); vla.add_argument("--human-slot",choices=["reviewer_a","reviewer_b"],default="reviewer_a")
    ara=sp.add_parser("adjudicate-research-review"); ara.add_argument("--submission",required=True); ara.add_argument("--review-dir",required=True)
    ala=sp.add_parser("adjudicate-llm-review"); ala.add_argument("--submission",required=True); ala.add_argument("--review-dir",required=True); ala.add_argument("--human-slot",choices=["reviewer_a","reviewer_b"],default="reviewer_a")
    prg=sp.add_parser("promote-research-gold"); prg.add_argument("--manifest",required=True); prg.add_argument("--review-dir",required=True); prg.add_argument("--output-dir",required=True); prg.add_argument("--dataset-id",default="petlongevity-abstract-gold-v0.4")
    prs=sp.add_parser("promote-research-silver"); prs.add_argument("--manifest",required=True); prs.add_argument("--review-dir",required=True); prs.add_argument("--output-dir",required=True); prs.add_argument("--dataset-id",default="petlongevity-abstract-silver-v0.4"); prs.add_argument("--human-slot",choices=["reviewer_a","reviewer_b"],default="reviewer_a")
    em2=sp.add_parser("export-m2-splits"); em2.add_argument("--claim-evidence",required=True); em2.add_argument("--splits",required=True); em2.add_argument("--output-dir",required=True)
    fr=sp.add_parser("prepare-fulltext-review"); fr.add_argument("--registry",default="data/corpus/registry.jsonl"); fr.add_argument("--output-dir",default="review/fulltext")
    vf=sp.add_parser("validate-fulltext-receipts"); vf.add_argument("--receipts",required=True); vf.add_argument("--registry",default="data/corpus/registry.jsonl"); vf.add_argument("--base-dir",required=True)
    ep=sp.add_parser("extract-pmc-fulltext"); ep.add_argument("--registry",default="data/corpus/registry.jsonl"); ep.add_argument("--corpus-dir",default="data/corpus"); ep.add_argument("--output-dir",default="review/fulltext")
    aw=sp.add_parser("prepare-fulltext-worksheet"); aw.add_argument("--registry",default="data/corpus/registry.jsonl"); aw.add_argument("--receipts",default="review/fulltext/fulltext_receipts.jsonl"); aw.add_argument("--base-dir",default="review/fulltext"); aw.add_argument("--output-dir",default="review/fulltext")
    convert=sp.add_parser("convert-dataset"); convert.add_argument("--input",required=True); convert.add_argument("--output",required=True); convert.add_argument("--from-format",choices=["jsonl","csv"],required=True); convert.add_argument("--to-format",choices=["jsonl","csv"],required=True)
    g=sp.add_parser("agreement-m2"); g.add_argument("--data",required=True); g.add_argument("--out")
    for name in ["m1","m2","m3","m4"]:
        s=sp.add_parser(f"score-{name}"); s.add_argument("--gold",required=True); s.add_argument("--pred",required=True); s.add_argument("--out")
    a=sp.add_parser("audit-leakage"); a.add_argument("--sources",required=True); a.add_argument("--cutoff",required=True); a.add_argument("--date-field",default="publication_date"); a.add_argument("--out")
    fs=sp.add_parser("freeze-snapshot"); fs.add_argument("--records",required=True); fs.add_argument("--output",required=True); fs.add_argument("--snapshot-id",required=True); fs.add_argument("--source",required=True); fs.add_argument("--query",required=True); fs.add_argument("--cutoff",required=True); fs.add_argument("--version-registry",required=True); fs.add_argument("--retrieved-at")
    ts=sp.add_parser("audit-snapshot"); ts.add_argument("--manifest",required=True); ts.add_argument("--prompt"); ts.add_argument("--non-strict",action="store_true"); ts.add_argument("--out")
    ro=sp.add_parser("run-offline"); ro.add_argument("--module",required=True); ro.add_argument("--baseline",required=True); ro.add_argument("--inputs",required=True); ro.add_argument("--responses",required=True); ro.add_argument("--predictions",required=True); ro.add_argument("--manifest",required=True); ro.add_argument("--response-cache",required=True); ro.add_argument("--prompt",required=True); ro.add_argument("--generation-settings"); ro.add_argument("--snapshot-manifest"); ro.add_argument("--model-name"); ro.add_argument("--model-version"); ro.add_argument("--run-date")
    kg=sp.add_parser("query-kg"); kg.add_argument("--nodes",required=True); kg.add_argument("--edges",required=True); kg.add_argument("--node-id",required=True); kg.add_argument("--species"); kg.add_argument("--direct-species-evidence",action="store_true"); kg.add_argument("--cutoff"); kg.add_argument("--max-hops",type=int,default=1); kg.add_argument("--out")
    b3=sp.add_parser("run-b3-offline"); b3.add_argument("--module",required=True); b3.add_argument("--inputs",required=True); b3.add_argument("--responses",required=True); b3.add_argument("--predictions",required=True); b3.add_argument("--manifest",required=True); b3.add_argument("--trace",required=True); b3.add_argument("--prompt",required=True); b3.add_argument("--snapshot-manifest",required=True); b3.add_argument("--kg-nodes",required=True); b3.add_argument("--kg-edges",required=True); b3.add_argument("--kg-node-id",required=True); b3.add_argument("--species"); b3.add_argument("--run-date")
    f=sp.add_parser("snapshot-pubmed"); f.add_argument("--query",required=True); f.add_argument("--cutoff",required=True); f.add_argument("--output",required=True); f.add_argument("--retmax",type=int,default=1000); f.add_argument("--email")
    args=p.parse_args(argv)
    if args.cmd=="validate":
        errs=validate_records(load_jsonl(args.data),args.schema); _emit({"valid":not errs,"n_errors":len(errs),"errors":errs}); return 1 if errs else 0
    if args.cmd=="validate-dataset":
        errs=validate_dataset(args.manifest,args.records); _emit({"valid":not errs,"n_errors":len(errs),"errors":errs}); return 1 if errs else 0
    if args.cmd=="validate-research-dataset":
        errs=validate_research_dataset(args.manifest); _emit({"valid":not errs,"n_errors":len(errs),"errors":errs}); return 1 if errs else 0
    if args.cmd=="validate-annotations-v01":
        errs=validate_annotations(args.annotations,args.registry); _emit({"valid":not errs,"n_errors":len(errs),"errors":errs}); return 1 if errs else 0
    if args.cmd=="review-status":
        report=freeze_gate(args.annotations,args.review_dir,args.registry); _emit(report); return 0 if report["READY_TO_FREEZE"] else 1
    if args.cmd=="prepare-research-review":
        report=prepare_research_review(args.manifest,args.output_dir,args.corpus_registry,args.split_seed); _emit(report); return 0 if report["validation_errors"] == 0 else 1
    if args.cmd=="research-review-status":
        report=research_review_status(args.review_dir); _emit(report); return 0 if report["READY_TO_FREEZE"] else 1
    if args.cmd=="llm-review-status":
        report=llm_review_status(args.review_dir,args.human_slot); _emit(report); return 0 if report["READY_FOR_SILVER"] else 1
    if args.cmd=="validate-research-review":
        errs=validate_research_review_submission(args.submission,args.review_dir); _emit({"valid":not errs,"n_errors":len(errs),"errors":errs}); return 1 if errs else 0
    if args.cmd=="import-research-review":
        try: report=import_research_review(args.submission,args.reviewer_slot,args.review_dir)
        except ValueError as exc: p.error(str(exc))
        _emit(report); return 0
    if args.cmd=="build-research-adjudication-queue":
        rows=build_research_adjudication_queue(args.review_dir); _emit({"conflicts":len(rows)}); return 0
    if args.cmd=="build-llm-adjudication-queue":
        rows=build_llm_adjudication_queue(args.review_dir,args.human_slot); _emit({"conflicts":len(rows),"human_slot":args.human_slot}); return 0
    if args.cmd=="build-llm-review-prompts":
        try: report=build_llm_review_prompts(args.review_dir,args.output_dir,args.max_pairs_per_prompt,args.reviewer_id)
        except (OSError, ValueError) as exc: p.error(str(exc))
        _emit(report); return 0
    if args.cmd=="assemble-llm-review-submission":
        response_paths=args.response or sorted(str(path) for path in Path(args.responses_dir).glob("*.jsonl"))
        try: report=assemble_llm_review_submission(response_paths,args.review_dir,args.output,args.reviewer_id)
        except (OSError, ValueError) as exc: p.error(str(exc))
        _emit(report); return 0 if report["valid"] else 1
    if args.cmd=="validate-research-adjudication":
        errs=validate_research_adjudication_submission(args.submission,args.review_dir); _emit({"valid":not errs,"n_errors":len(errs),"errors":errs}); return 1 if errs else 0
    if args.cmd=="validate-llm-adjudication":
        errs=validate_llm_adjudication_submission(args.submission,args.review_dir,args.human_slot); _emit({"valid":not errs,"n_errors":len(errs),"errors":errs}); return 1 if errs else 0
    if args.cmd=="adjudicate-research-review":
        try: report=adjudicate_research_review(args.submission,args.review_dir)
        except ValueError as exc: p.error(str(exc))
        _emit(report); return 0
    if args.cmd=="adjudicate-llm-review":
        try: report=adjudicate_llm_review(args.submission,args.review_dir,args.human_slot)
        except ValueError as exc: p.error(str(exc))
        _emit(report); return 0
    if args.cmd=="promote-research-gold":
        try: report=promote_research_gold(args.manifest,args.review_dir,args.output_dir,args.dataset_id)
        except ValueError as exc: p.error(str(exc))
        _emit(report); return 0
    if args.cmd=="promote-research-silver":
        try: report=promote_research_silver(args.manifest,args.review_dir,args.output_dir,args.dataset_id,args.human_slot)
        except ValueError as exc: p.error(str(exc))
        _emit(report); return 0
    if args.cmd=="export-m2-splits":
        _emit(export_m2_baseline_splits(args.claim_evidence,args.splits,args.output_dir)); return 0
    if args.cmd=="prepare-fulltext-review":
        _emit(write_fulltext_queue(args.registry,args.output_dir)); return 0
    if args.cmd=="validate-fulltext-receipts":
        errs=validate_fulltext_receipts(args.receipts,args.registry,args.base_dir); _emit({"valid":not errs,"n_errors":len(errs),"errors":errs}); return 1 if errs else 0
    if args.cmd=="extract-pmc-fulltext":
        try: _emit(extract_pmc_fulltext(args.registry,args.corpus_dir,args.output_dir))
        except ValueError as exc: p.error(str(exc))
        return 0
    if args.cmd=="prepare-fulltext-worksheet":
        try: _emit(write_fulltext_annotation_worksheet(args.registry,args.receipts,args.base_dir,args.output_dir))
        except ValueError as exc: p.error(str(exc))
        return 0
    if args.cmd=="convert-dataset":
        if args.from_format==args.to_format: p.error("source and destination formats must differ")
        if args.from_format=="jsonl": export_jsonl_csv(args.input,args.output)
        else: import_csv_jsonl(args.input,args.output)
        _emit({"input":args.input,"output":args.output,"from_format":args.from_format,"to_format":args.to_format}); return 0
    if args.cmd=="agreement-m2":
        try: result=agreement_m2(load_jsonl(args.data))
        except ValueError as exc: p.error(str(exc))
        _emit(result,args.out); return 0
    if args.cmd.startswith("score-"):
        gold,pred=load_jsonl(args.gold),load_jsonl(args.pred); mod=args.cmd[-2:]
        fn={"m1":score_m1,"m2":score_m2,"m3":score_m3,"m4":score_m4}[mod]; _emit(fn(gold,pred),args.out); return 0
    if args.cmd=="audit-leakage": _emit(audit_sources(load_jsonl(args.sources),args.cutoff,args.date_field),args.out); return 0
    if args.cmd=="freeze-snapshot":
        registry=Path(args.version_registry)
        try: versions=json.loads(registry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: p.error(f"invalid version registry: {exc}")
        _emit(freeze_snapshot(args.records,args.output,args.snapshot_id,args.source,args.query,args.cutoff,versions,args.retrieved_at)); return 0
    if args.cmd=="audit-snapshot":
        report=audit_snapshot(args.manifest,strict=not args.non_strict,prompt_path=args.prompt); _emit(report,args.out); return 0 if report["leakage_free"] else 1
    if args.cmd=="run-offline":
        settings={}
        if args.generation_settings:
            try: settings=json.loads(Path(args.generation_settings).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc: p.error(f"invalid generation settings: {exc}")
        try:
            manifest=run_offline(args.module,args.baseline,args.inputs,args.responses,args.predictions,args.manifest,args.response_cache,args.prompt,settings,args.snapshot_manifest,args.model_name,args.model_version,args.run_date)
        except ValueError as exc: p.error(str(exc))
        _emit(manifest); return 0
    if args.cmd=="query-kg":
        try: result=load_graph(args.nodes,args.edges).retrieve(args.node_id,args.species,args.direct_species_evidence,args.cutoff,args.max_hops)
        except ValueError as exc: p.error(str(exc))
        _emit(result,args.out); return 0
    if args.cmd=="run-b3-offline":
        try: result=run_b3_offline(args.module,args.inputs,args.responses,args.predictions,args.manifest,args.trace,args.prompt,args.snapshot_manifest,args.kg_nodes,args.kg_edges,args.kg_node_id,args.species,run_date=args.run_date)
        except ValueError as exc: p.error(str(exc))
        _emit(result); return 0
    if args.cmd=="snapshot-pubmed":
        meta=snapshot(args.query,args.cutoff,args.output,args.retmax,os.getenv("NCBI_API_KEY"),args.email); _emit(meta); return 0
    return 2
if __name__=="__main__": raise SystemExit(main())
