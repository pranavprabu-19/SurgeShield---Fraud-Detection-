"""Import a login, network, or ATM log. Raw ids are tokenized before anything is stored."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from pathlib import Path

from backend.app.governance.privacy import tokenize
from ml.schema import ROOT

PII_PATTERN = re.compile(
    r"^(first|last|name|full_?name|street|address|addr_line|job|email|phone|mobile|ssn|aadhaar|pan|trans_num|zip|pincode)$",
    re.I,
)
REQUIRED = {
    "login": ("user_id", "time", "success"),
    "network": ("src", "dst", "bytes", "time"),
    "atm": ("terminal_id", "event", "time"),
}
TOKEN_COLUMNS = {"user_id", "src", "dst", "terminal_id"}


def secret() -> bytes:
    return hashlib.sha256(os.environ.get("SURGESHIELD_SECRET", "surgeshield-demo-secret").encode()).digest()


def import_file(kind: str, path: Path, dest: Path | None = None) -> dict:
    if kind not in REQUIRED:
        raise SystemExit(f"kind must be one of {', '.join(REQUIRED)}")
    needed = REQUIRED[kind]
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        missing = [name for name in needed if name not in columns]
        if missing:
            raise SystemExit(f"missing columns: {', '.join(missing)}")
        dropped = [name for name in columns if PII_PATTERN.match(str(name))]
        rows = []
        key = secret()
        for raw in reader:
            row = {}
            for name in needed:
                value = raw.get(name) or ""
                row[name] = tokenize(value, key) if name in TOKEN_COLUMNS and value else value
            rows.append(row)
    out = Path(dest) if dest else ROOT / "data" / "logs" / kind
    out.mkdir(parents=True, exist_ok=True)
    with (out / "events.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(needed))
        writer.writeheader()
        writer.writerows(rows)
    report = {"kind": kind, "rows": len(rows), "dropped_pii": dropped, "columns": list(needed)}
    (out / "report.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True, choices=sorted(REQUIRED))
    parser.add_argument("--path", required=True)
    args = parser.parse_args()
    report = import_file(args.kind, Path(args.path))
    print(f"{report['kind']}: {report['rows']} rows, dropped {len(report['dropped_pii'])} pii columns")


if __name__ == "__main__":
    main()
