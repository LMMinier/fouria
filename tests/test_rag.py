"""Unit tests for rag module."""
import json, sys, os, tempfile, shutil, importlib.util
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))


def _make_rag(corpus_dir, index_dir):
    spec = importlib.util.spec_from_file_location(
        "rag_test",
        os.path.join(os.path.dirname(__file__), "..", "server", "rag.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.CORPUS_DIR = corpus_dir
    mod.INDEX_DIR  = index_dir
    mod.INDEX_FILE = index_dir / "fouria_rag.json"
    return mod


def test_build_and_search_basic():
    tmp = tempfile.mkdtemp()
    try:
        from pathlib import Path
        corpus, index = Path(tmp) / "corpus", Path(tmp) / "index"
        corpus.mkdir(); index.mkdir()
        (corpus / "mixing.txt").write_text(
            "Use sidechain compression on the kick to create space for the 808. "
            "Low-end management is critical in trap production. "
            "High-pass filter melodic instruments above 80 Hz to reduce mud.",
            encoding="utf-8",
        )
        rag = _make_rag(corpus, index)
        idx = rag.build_index()
        assert len(idx["docs"]) >= 1
        assert "kick" in idx["doc_freq"]
        results = rag.search("kick sidechain compression")
        assert results and results[0]["score"] > 0
        assert "FOURIA KNOWLEDGE CONTEXT" in rag.context_block("low end mud")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_empty_corpus_returns_no_results():
    tmp = tempfile.mkdtemp()
    try:
        from pathlib import Path
        corpus, index = Path(tmp) / "corpus", Path(tmp) / "index"
        corpus.mkdir(); index.mkdir()
        rag = _make_rag(corpus, index)
        rag.build_index()
        assert rag.search("anything") == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_tfidf_prefers_specific_over_common():
    tmp = tempfile.mkdtemp()
    try:
        from pathlib import Path
        corpus, index = Path(tmp) / "corpus", Path(tmp) / "index"
        corpus.mkdir(); index.mkdir()
        (corpus / "a.txt").write_text("transient shaping is important for punchy drums", encoding="utf-8")
        (corpus / "b.txt").write_text("the the the the the the the the", encoding="utf-8")
        rag = _make_rag(corpus, index)
        rag.build_index()
        results = rag.search("transient")
        assert results[0]["source"] == "a.txt"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
