import json
import math
import os
import re
from pathlib import Path


ROOT = Path(os.environ.get("FOURIA_ROOT", Path(__file__).resolve().parents[1]))
CORPUS_DIR = ROOT / "data" / "corpus"
INDEX_DIR = ROOT / "data" / "index"
INDEX_FILE = INDEX_DIR / "fouria_rag.json"


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_']+", text.lower())


def _chunk(text: str, size: int = 1400, overlap: int = 180) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += max(1, size - overlap)
    return chunks


def build_index() -> dict:
    docs = []
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    for path in CORPUS_DIR.rglob("*"):
        if path.suffix.lower() not in {".txt", ".md", ".jsonl"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, ch in enumerate(_chunk(text)):
            toks = _tokens(ch)
            if not toks:
                continue
            docs.append({
                "id": f"{path.relative_to(CORPUS_DIR)}#{i}",
                "source": str(path.relative_to(CORPUS_DIR)),
                "text": ch,
                "tokens": sorted(set(toks)),
            })
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    index = {"docs": docs}
    INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


def load_index() -> dict:
    if not INDEX_FILE.exists():
        return build_index()
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return build_index()


def search(query: str, limit: int = 5) -> list[dict]:
    q = set(_tokens(query))
    if not q:
        return []
    idx = load_index()
    scored = []
    for doc in idx.get("docs", []):
        toks = set(doc.get("tokens", []))
        if not toks:
            continue
        overlap = len(q & toks)
        if not overlap:
            continue
        score = overlap / math.sqrt(len(toks))
        scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"score": round(score, 4), "source": doc["source"], "text": doc["text"]}
        for score, doc in scored[:limit]
    ]


def context_block(query: str, limit: int = 4) -> str:
    hits = search(query, limit=limit)
    if not hits:
        return ""
    lines = ["FOURIA KNOWLEDGE CONTEXT (trusted local notes/reference):"]
    for i, hit in enumerate(hits, 1):
        lines.append(f"[{i}] {hit['source']}")
        lines.append(hit["text"][:1200])
    return "\n\n".join(lines)

