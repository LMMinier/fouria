#!/usr/bin/env python3
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus"


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python scripts/ingest_folder.py <folder-or-file>")
    src = Path(sys.argv[1])
    if not src.exists():
        raise SystemExit(f"not found: {src}")
    CORPUS.mkdir(parents=True, exist_ok=True)
    paths = [src] if src.is_file() else [p for p in src.rglob("*") if p.is_file()]
    copied = 0
    for p in paths:
        if p.suffix.lower() not in {".txt", ".md", ".jsonl"}:
            continue
        dest = CORPUS / p.name
        if dest.exists():
            dest = CORPUS / f"{p.stem}_{copied}{p.suffix}"
        shutil.copy2(p, dest)
        copied += 1
    print(f"copied {copied} files into {CORPUS}")
    print("run: python -m server.fouria_api then POST /api/reindex, or restart FOURIA")


if __name__ == "__main__":
    main()

