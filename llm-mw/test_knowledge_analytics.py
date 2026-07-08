"""
Unit tests for the pure helpers in core/knowledge_analytics.py.

These cover the spike-driven logic (filename extraction, stem normalization,
membership/ambiguity resolution, and value classification) without touching a
database — the query_* functions that hit Postgres are exercised separately.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.knowledge_analytics import (
    _stem, _FILENAME_MARKER_RE, _has_citation, _meta_size, _meta_content_type,
    _meta_knowledge_id, _meta_collection, _classify, _stems_to_kbs,
    MIN_SAMPLE_ATTACHMENTS, GOOD_HIT_RATE,
)


def _markers(text):
    return {_stem(m) for m in _FILENAME_MARKER_RE.findall(text)}


def test_stem_normalizes_extension_case_and_space():
    # The spike saw a .docx in the log for a .pdf on disk — stems must match.
    assert _stem("TCVN7722-2-3_2007_904224.docx") == _stem("TCVN7722-2-3_2007_904224.pdf")
    assert _stem("  Report.PDF  ") == "report"
    assert _stem(None) == ""
    assert _stem("no_extension") == "no_extension"


def test_marker_extracts_filenames():
    text = ("... nội dung ... Filename: ITviec-Bao-Cao.pdf ITviec Bao Cao "
            "Source: ITviec-Bao-Cao.pdf </source>")
    assert _markers(text) == {"itviec-bao-cao"}


def test_marker_ignores_bare_source_template():
    # A bare/template <source id="1"> with no document marker is NOT an attachment.
    template = ('Chỉ bao gồm trích dẫn dưới dạng [id] khi thẻ <source id="1"> '
                'có thuộc tính name')
    assert _markers(template) == set()


def test_marker_handles_multiple_documents():
    text = "Source: a-report.pdf ... Filename: b-notes.docx ..."
    assert _markers(text) == {"a-report", "b-notes"}


def test_has_citation():
    assert _has_citation("theo báo cáo [1] và [2, 3]")
    assert not _has_citation("no citation here")
    assert not _has_citation(None)


def test_meta_helpers_tolerate_shapes():
    meta = {
        "size": 921581, "content_type": "application/pdf",
        "data": {"knowledge_id": "kb-1"}, "collection_name": "kb-1",
    }
    assert _meta_size(meta) == 921581
    assert _meta_content_type(meta, "x.pdf") == "application/pdf"
    assert _meta_knowledge_id(meta) == "kb-1"
    assert _meta_collection(meta) == "kb-1"


def test_meta_content_type_falls_back_to_extension():
    assert _meta_content_type({}, "report.docx") == "application/docx"
    assert _meta_content_type(None, "noext") == "unknown"


def test_meta_size_defaults_zero():
    assert _meta_size(None) == 0
    assert _meta_size({}) == 0
    assert _meta_knowledge_id({"data": {}}) is None


def test_classify_dead_vs_unproven():
    # Has chunks but zero demand -> dead; no chunks and zero demand -> unproven.
    assert _classify(attach=0, hit_rate=0.0, chunk_count=100) == "dead"
    assert _classify(attach=0, hit_rate=0.0, chunk_count=0) == "unproven"


def test_classify_unproven_below_sample_floor():
    assert _classify(attach=MIN_SAMPLE_ATTACHMENTS - 1, hit_rate=100.0, chunk_count=10) == "unproven"


def test_classify_star_vs_needs_tuning():
    assert _classify(attach=MIN_SAMPLE_ATTACHMENTS, hit_rate=GOOD_HIT_RATE, chunk_count=10) == "star"
    assert _classify(attach=20, hit_rate=GOOD_HIT_RATE - 1, chunk_count=10) == "needs_tuning"


def test_stems_to_kbs_detects_ambiguity():
    files = [
        {"stem": "shared", "knowledge_id": "kb-1"},
        {"stem": "shared", "knowledge_id": "kb-2"},
        {"stem": "unique", "knowledge_id": "kb-1"},
        {"stem": "orphan", "knowledge_id": None},   # not in any live KB
    ]
    mapping = _stems_to_kbs(files)
    assert mapping["shared"] == {"kb-1", "kb-2"}   # ambiguous
    assert mapping["unique"] == {"kb-1"}           # unambiguous
    assert "orphan" not in mapping


def test_empty_corpus_is_safe():
    # Inventory / value / governance must not error on an empty corpus.
    import core.knowledge_analytics as ka
    from datetime import datetime, timezone

    empty = {"knowledge": {}, "files": [], "chunks_by_collection": {}, "users": {}}
    orig_compute, orig_usage = ka._compute_corpus, ka._query_stem_usage
    ka._compute_corpus = lambda: empty
    ka._query_stem_usage = lambda s, e: {}
    ka._corpus_cache["data"] = None
    try:
        now = datetime.now(timezone.utc)
        inv = ka.query_inventory(now, now)
        val = ka.query_kb_value(now, now)
        gov = ka.query_governance()
    finally:
        ka._compute_corpus, ka._query_stem_usage = orig_compute, orig_usage
        ka._corpus_cache["data"] = None

    assert inv["totals"] == {"knowledge_bases": 0, "files": 0, "chunks": 0, "storage_bytes": 0}
    assert val["knowledge_bases"] == []
    assert val["category_counts"] == {"star": 0, "needs_tuning": 0, "dead": 0, "unproven": 0}
    assert gov["duplicates"] == [] and gov["reclaimable_bytes"] == 0


def test_corpus_cache_reuses_within_ttl():
    import core.knowledge_analytics as ka

    calls = {"n": 0}

    def fake_compute():
        calls["n"] += 1
        return {"knowledge": {}, "files": [], "chunks_by_collection": {}, "users": {}}

    orig = ka._compute_corpus
    ka._compute_corpus = fake_compute
    ka._corpus_cache["data"] = None
    try:
        ka._get_corpus()
        ka._get_corpus()            # within TTL -> served from cache
        assert calls["n"] == 1
        ka._get_corpus(force_refresh=True)   # bypasses cache
        assert calls["n"] == 2
    finally:
        ka._compute_corpus = orig
        ka._corpus_cache["data"] = None


if __name__ == "__main__":
    import traceback
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"PASS {name}")
            except Exception:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
