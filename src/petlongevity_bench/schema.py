from __future__ import annotations
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from .io import load_json


def validator(schema_path: str | Path) -> Draft202012Validator:
    schema=load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_records(records, schema_path):
    v=validator(schema_path)
    errors=[]
    for i,record in enumerate(records):
        for e in sorted(v.iter_errors(record), key=lambda x:list(x.path)):
            errors.append({"row":i,"record_id":record.get("record_id"),"path":".".join(map(str,e.path)),"message":e.message})
    return errors
