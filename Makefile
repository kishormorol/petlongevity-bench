.PHONY: install test smoke package
install:
	python -m pip install -e .
test:
	pytest -q
smoke:
	petbench validate --data data/demo/m1_gold.jsonl --schema schemas/evidence_schema.json
	petbench score-m1 --gold data/demo/m1_gold.jsonl --pred data/demo/m1_pred_perfect.jsonl
	petbench score-m2 --gold data/demo/m2_gold.jsonl --pred data/demo/m2_pred_perfect.jsonl
	petbench score-m3 --gold data/demo/m3_gold.jsonl --pred data/demo/m3_pred.jsonl
	petbench score-m4 --gold data/demo/m4_gold.jsonl --pred data/demo/m4_pred.jsonl
	petbench audit-leakage --sources data/demo/sources.jsonl --cutoff 2016-12-31
package:
	cd .. && zip -qr petlongevity_bench_v0_2.zip petlongevity_bench_v0_2
