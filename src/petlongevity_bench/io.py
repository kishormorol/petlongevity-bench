from __future__ import annotations
import csv, json, hashlib
from pathlib import Path
from typing import Any, Iterable


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    out=[]
    with open(path, encoding="utf-8") as f:
        for n,line in enumerate(f,1):
            line=line.strip()
            if not line: continue
            try: out.append(json.loads(line))
            except json.JSONDecodeError as e: raise ValueError(f"{path}:{n}: {e}") from e
    return out


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    with open(path,"w",encoding="utf-8") as f:
        for row in rows: f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")


def load_json(path: str | Path) -> Any:
    with open(path,encoding="utf-8") as f: return json.load(f)


def write_json(path: str | Path, obj: Any) -> None:
    with open(path,"w",encoding="utf-8") as f: json.dump(obj,f,indent=2,sort_keys=True)


def load_csv(path: str | Path) -> list[dict[str,str]]:
    with open(path,encoding="utf-8",newline="") as f: return list(csv.DictReader(f))


def export_jsonl_csv(jsonl_path: str | Path, csv_path: str | Path) -> None:
    """Export JSONL rows to CSV, preserving non-string fields as JSON values."""
    rows=load_jsonl(jsonl_path)
    fields=sorted({key for row in rows for key in row})
    with open(csv_path,"w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value,ensure_ascii=False,sort_keys=True) for key,value in row.items()})


def import_csv_jsonl(csv_path: str | Path, jsonl_path: str | Path) -> None:
    """Import a CSV created by :func:`export_jsonl_csv` into JSONL records."""
    rows=[]
    for row in load_csv(csv_path):
        parsed={}
        for key,value in row.items():
            if value == "": continue
            try: parsed[key]=json.loads(value)
            except json.JSONDecodeError: parsed[key]=value
        rows.append(parsed)
    write_jsonl(jsonl_path,rows)


def sha256_file(path: str | Path) -> str:
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""): h.update(chunk)
    return h.hexdigest()
