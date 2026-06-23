import json
import math
import os
import re
from pathlib import Path


ROOT       = Path(os.environ.get("FOURIA_ROOT", Path(__file__).resolve().parents[1]))
CORPUS_DIR = ROOT / "data" / "corpus"
INDEX_DIR  = ROOT / "data" / "index"
INDEX_FILE = INDEX_DIR / "fouria_rag.json"

_INDEX_CACHE: dict | None = None


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_']+", text.lower())


def _chunk(text: str, size: int = 1400, overlap: int = 180) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += max(1, size - overlap)
    return chunks


def build_index() -> dict:
    """Scan corpus, chunk every document, build TF-IDF-ready index."""
    raw_docs = []
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
            raw_docs.append({
                "id":     f"{path.relative_to(CORPUS_DIR)}#{i}",
                "source": str(path.relative_to(CORPUS_DIR)),
                "text":   ch,
                "tokens": sorted(set(toks)),
                "tf":     {},
            })

    total = len(raw_docs)

    # Document frequency: how many chunks contain each token
    doc_freq: dict[str, int] = {}
    for doc in raw_docs:
        for tok in doc["tokens"]:
            doc_freq[tok] = doc_freq.get(tok, 0) + 1

    # Compute TF for each chunk (raw count / total tokens in chunk)
    for doc in raw_docs:
        all_toks = _tokens(doc["text"])
        n = len(all_toks)
        tf: dict[str, float] = {}
        for tok in all_toks:
            tf[tok] = tf.get(tok, 0) + 1
        doc["tf"] = {tok: count / n for tok, count in tf.items()}

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    index = {"docs": raw_docs, "doc_freq": doc_freq, "total_docs": total}
    INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")
    global _INDEX_CACHE
    _INDEX_CACHE = index
    return index


def load_index() -> dict:
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE
    if not INDEX_FILE.exists():
        _INDEX_CACHE = build_index()
        return _INDEX_CACHE
    try:
        _INDEX_CACHE = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        return _INDEX_CACHE
    except (json.JSONDecodeError, OSError):
        _INDEX_CACHE = build_index()
        return _INDEX_CACHE


def search(query: str, limit: int = 5) -> list[dict]:
    """TF-IDF ranked retrieval. Falls back gracefully on empty corpus."""
    q_tokens = _tokens(query)
    if not q_tokens:
        return []

    idx       = load_index()
    docs      = idx.get("docs", [])
    doc_freq  = idx.get("doc_freq", {})
    total     = max(idx.get("total_docs", 1), 1)

    scored = []
    for doc in docs:
        tf_map = doc.get("tf") or {}
        score  = 0.0
        for tok in q_tokens:
            tf  = tf_map.get(tok, 0.0)
            df  = doc_freq.get(tok, 0)
            if tf > 0 and df > 0:
                idf    = math.log((total + 1) / (df + 1)) + 1.0   # smoothed IDF
                score += tf * idf
        if score > 0:
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
        lines.append(f"[{i}] {hit['source']}  (score {hit['score']})")
        lines.append(hit["text"][:1200])
    return "\n\n".join(lines)
