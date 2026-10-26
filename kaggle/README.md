# Kaggle

Everything published on Kaggle is rebuilt from here.

| Kaggle | source |
|---|---|
| Dataset [kishormorol/petlongevity-bench](https://www.kaggle.com/datasets/kishormorol/petlongevity-bench) | `dataset/` (card, metadata, cover) + `build_dataset.py` |
| Notebook [petlongevity-bench-getting-started](https://www.kaggle.com/code/kishormorol/petlongevity-bench-getting-started) | `notebook/` |
| Benchmark task [petlongevity-bench-species-transfer](https://www.kaggle.com/benchmarks/tasks/kishormorol/petlongevity-bench-species-transfer) | `species_transfer_task.py` |

The dataset is public and Kaggle does not allow making it private again.

## Dataset

```bash
python scripts/export_release.py \
  --annotations data/gold/drafts/abstracts_300/claim_evidence.jsonl --output release/
python kaggle/build_dataset.py --release release/ --output kaggle_upload/
kaggle datasets version -p kaggle_upload/ -m "<message>"
kaggle datasets metadata --update -p kaggle_upload/ kishormorol/petlongevity-bench
```

`export_release.py` withholds every verbatim field (abstract, quote, claim, span
text) for papers that are not CC BY. Check the manifest counts before uploading.

## Notebook

```bash
kaggle kernels push -p kaggle/notebook
```

## Species-transfer task

Items are built from the CC BY abstracts only, because the task runs on Kaggle and
can only show the model text the dataset ships. Gold labels come from construction
(the studied species is `supported`, the other companion species is `insufficient`),
not from the placeholder pair labels.

```bash
kaggle b init -y                                  # once; writes .env with proxy credentials
PETBENCH_DATA=kaggle_upload python kaggle/species_transfer_task.py   # local check
kaggle b t push petlongevity-bench-species-transfer -f kaggle/species_transfer_task.py \
  -d kishormorol/petlongevity-bench --wait
kaggle b t run petlongevity-bench-species-transfer -m <model> -m <model>
```

Always repeat `-d kishormorol/petlongevity-bench` on push, or the dataset is detached.
