"""
RAG health monitoring queries.

Three independent layers, all read-only:

  * Ingestion  — embedding-call failures mined from ``mw_audit_log`` (pooled
                 middleware DB via :func:`core.db.db_conn`).
  * Retrieval  — citation hit-rate re-derived from ``mw_request_log`` JSONB
                 (``chat.request`` / ``chat.response`` event pairs, joined by
                 request id). Independent of ``MW_RAG_IMAGE_INJECT``.
  * Storage    — zero-chunk KBs, orphaned chunks and chunk-count outliers,
                 queried directly against the OpenWebUI database using the same
                 unpooled ``psycopg2.connect()`` pattern as
                 :func:`core.identity.load_openwebui_users`. Cached for a short
                 TTL to keep the connection frequency low.

See ``openspec/changes/rag-health-monitor/design.md`` for the join-key and
grouping decisions (spikes 1.1 / 1.2).
"""

import re
import time
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import psycopg2

from config import DATABASE_URL

logger = logging.getLogger("llm_mw")

# Ported from api/chat.py so retrieval detection stays decoupled from the
# runtime image-injection path (design decision 1).
#   - source tag: <source id="N"> optionally carrying name="..." and resource-type="...".
#   - citation marker: [N] or [N, M, ...].
#
# `resource-type` separates the shared knowledge bases (``collection``) from a file the
# user dragged into one chat (``file``). Coverage counts only the former: a personal PDF
# is not the corpus the company invested in, and folding the two together inflates the
# figure with something it does not measure.
_SOURCE_RE = re.compile(
    r'<source\s+id="(\d+)"(?:\s+name="([^"]*)")?(?:\s+resource-type="([^"]*)")?',
    re.IGNORECASE,
)
_KB_SOURCE_KIND = "collection"
_CITATION_RE = re.compile(r'\[(\d+(?:\s*,\s*\d+)*)\]')

# Rough characters-per-chunk estimate used only for the heuristic chunk-count
# outlier check (OpenWebUI default chunk_size is 1500 chars, see
# docs/06-rag-architecture.md). Kept deliberately loose.
_CHARS_PER_CHUNK = 1500


# ─── Ingestion health (mw_audit_log, pooled middleware DB) ───────────────────

def query_ingestion_summary(start, end) -> Dict[str, Any]:
    """Embedding call count, failure rate, avg latency + a per-day timeseries.

    A call is a *failure* when ``status = 'error'`` or ``status_code >= 400``.
    """
    from core.db import db_conn

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                count(*) AS total,
                count(*) FILTER (WHERE status = 'error' OR status_code >= 400) AS failures,
                avg(latency_ms) FILTER (WHERE latency_ms IS NOT NULL) AS avg_latency
            FROM mw_audit_log
            WHERE ts >= %s AND ts <= %s AND endpoint ILIKE %s
            """,
            (start, end, "%embeddings%"),
        )
        total, failures, avg_latency = cur.fetchone()

        cur.execute(
            """
            SELECT date_trunc('day', ts) AS bucket,
                   count(*) AS total,
                   count(*) FILTER (WHERE status = 'error' OR status_code >= 400) AS failures
            FROM mw_audit_log
            WHERE ts >= %s AND ts <= %s AND endpoint ILIKE %s
            GROUP BY bucket
            ORDER BY bucket
            """,
            (start, end, "%embeddings%"),
        )
        series_rows = cur.fetchall()
        cur.close()

    total = int(total or 0)
    failures = int(failures or 0)
    timeseries = [
        {
            "ts": r[0].isoformat() if r[0] else None,
            "total": int(r[1] or 0),
            "failures": int(r[2] or 0),
            "failure_rate": (int(r[2] or 0) / r[1] * 100.0) if r[1] else 0.0,
        }
        for r in series_rows
    ]
    return {
        "total_calls": total,
        "failures": failures,
        "failure_rate": (failures / total * 100.0) if total else 0.0,
        "avg_latency_ms": round(float(avg_latency), 1) if avg_latency is not None else None,
        "timeseries": timeseries,
    }


def query_recent_embedding_failures(start, end, limit: int = 50) -> List[Dict[str, Any]]:
    """Most recent failed embedding calls (timestamp, user, error type/message)."""
    from core.db import db_conn

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts, user_id, error_type, error_message, status_code
            FROM mw_audit_log
            WHERE ts >= %s AND ts <= %s AND endpoint ILIKE %s
              AND (status = 'error' OR status_code >= 400)
            ORDER BY ts DESC
            LIMIT %s
            """,
            (start, end, "%embeddings%", limit),
        )
        rows = cur.fetchall()
        cur.close()

    return [
        {
            "ts": r[0].isoformat() if r[0] else None,
            "user_id": r[1],
            "error_type": r[2],
            "error_message": r[3],
            "status_code": r[4],
        }
        for r in rows
    ]


# ─── Retrieval health (mw_request_log JSONB) ─────────────────────────────────

def _message_text(messages: Any) -> str:
    """Concatenate all textual content from an OpenAI-style messages array."""
    if not isinstance(messages, list):
        return ""
    parts: List[str] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
    return "\n".join(parts)


def _sources_from_body(body: Any) -> List[Dict[str, str]]:
    """Return the ``<source id="N" name="...">`` tags found in the request body.

    ``name`` is the source-document label when OpenWebUI emits it, else a
    synthetic ``source #N`` (see spike 1.1 — the id is a per-request index,
    not a KB identifier).
    """
    if not isinstance(body, dict):
        return []
    text = _message_text(body.get("messages"))
    # A named tag beats a bare one carrying the same id. OpenWebUI emits its citation
    # *instruction template* — a bare ``<source id="1">`` — ahead of the real attachment
    # tags, so keeping the first match per id labelled every document in the corpus
    # ``source #1`` and collapsed the whole By-Source table into one meaningless row.
    # core/knowledge_analytics.py documents the same trap and sidesteps it by matching
    # ``Filename:`` / ``Source:`` markers instead of the tag.
    found: Dict[str, Dict[str, str]] = {}
    for sid, name, kind in _SOURCE_RE.findall(text):
        entry = found.setdefault(sid, {"name": "", "kind": ""})
        # Each attribute is filled by whichever occurrence actually carries it; the bare
        # template tag carries neither, so it can no longer shadow the real one.
        if (name or "").strip():
            entry["name"] = name.strip()
        if (kind or "").strip():
            entry["kind"] = kind.strip().lower()
    return [
        {"id": sid, "name": e["name"] or f"source #{sid}", "kind": e["kind"] or "unknown"}
        for sid, e in found.items()
    ]


def _has_citation(content: Optional[str]) -> bool:
    return bool(content) and bool(_CITATION_RE.search(content))


def query_retrieval_health(
    start,
    end,
    model: Optional[str] = None,
    user_id: Optional[str] = None,
    zero_citation_limit: int = 100,
) -> Dict[str, Any]:
    """Citation hit-rate over KB-attached chats, broken down by model and source.

    KB attachment is detected by ``<source id="N">`` tags in the logged
    ``chat.request`` body; a "hit" is at least one ``[N]`` marker in the paired
    ``chat.response`` content (joined by request id ``rid``).

    A request whose answer was never logged is reported as ``unpaired`` and kept out
    of the rate entirely — it is evidence of nothing. Streamed answers only began
    emitting ``chat.response`` on 2026-07-01 (``api/chat.py``), so every earlier
    streamed chat lands there; counting them as misses is what made this function
    report a 0.0% hit-rate for the whole of June, which reads as "the model never
    cites" when the truth was "we never recorded the answer".
    """
    from core.db import db_conn

    # Split deliberately: the coverage denominator must carry the SAME model/user filters
    # as the numerator, or filtering the tab would divide a filtered count by an
    # unfiltered one. Only the `<source>` condition separates the two.
    base_conditions = [
        "ts >= %s", "ts <= %s",
        "payload->>'event' = 'chat.request'",
        "payload->>'rid' IS NOT NULL",
    ]
    base_params: List[Any] = [start, end]
    if model:
        base_conditions.append("payload->>'model' = %s")
        base_params.append(model)
    if user_id:
        base_conditions.append("payload->>'user' = %s")
        base_params.append(user_id)

    where_base = " AND ".join(base_conditions)
    where_req = where_base + r" AND (payload->'body')::text ~* '<source\s+id\s*='"
    params_req = list(base_params)

    with db_conn() as conn:
        cur = conn.cursor()
        # Coverage denominator: every question asked in the window, attachment or not.
        # Counting rows (not DISTINCT rid) on purpose — the numerator counts rows from the
        # same base filter, so the ratio cannot exceed 100% by construction.
        cur.execute(f"SELECT count(*) FROM mw_request_log WHERE {where_base}", tuple(base_params))
        total_requests = int(cur.fetchone()[0] or 0)

        cur.execute(
            f"""
            WITH req AS (
                SELECT payload->>'rid'                AS rid,
                       ts,
                       payload->>'user'               AS user_id,
                       payload->>'model'              AS model,
                       payload->>'prompt'             AS prompt,
                       payload#>'{{body,messages}}'   AS messages
                FROM mw_request_log
                WHERE {where_req}
            ),
            resp AS (
                SELECT DISTINCT ON (payload->>'rid')
                       payload->>'rid'     AS rid,
                       payload->>'content' AS content
                FROM mw_request_log
                WHERE ts >= %s AND ts <= %s
                  AND payload->>'event' = 'chat.response'
                  AND payload->>'rid' IS NOT NULL
                ORDER BY payload->>'rid', ts DESC
            )
            SELECT req.rid, req.ts, req.user_id, req.model, req.prompt,
                   req.messages, resp.content
            FROM req
            LEFT JOIN resp ON resp.rid = req.rid
            ORDER BY req.ts DESC
            """,
            (*params_req, start, end),
        )
        rows = cur.fetchall()
        cur.close()

    attached = 0
    evaluated = 0
    hits = 0
    # Coverage numerator, and the ad-hoc figure kept beside it so the difference between
    # "the corpus was used" and "someone uploaded their own file" stays visible.
    kb_requests = 0
    adhoc_requests = 0
    by_model: Dict[str, Dict[str, int]] = {}
    by_source: Dict[str, Dict[str, int]] = {}
    # Feeds the tab's user filter. It used to be populated from the zero-citation list,
    # which only ever contained users who had a miss — and once unpaired requests stopped
    # being counted as misses, that list (and the filter with it) emptied out.
    by_user: Dict[str, Dict[str, int]] = {}
    zero_citation: List[Dict[str, Any]] = []

    def _bucket(store: Dict[str, Dict[str, int]], key: str) -> Dict[str, int]:
        return store.setdefault(key, {"attached": 0, "evaluated": 0, "cited": 0})

    for rid, ts, r_user, r_model, prompt, messages, content in rows:
        attached += 1
        # NULL content means the LEFT JOIN found no chat.response row, not that the
        # answer cited nothing. The two must never collapse into the same counter.
        readable = content is not None
        cited = readable and _has_citation(content)
        if readable:
            evaluated += 1
            if cited:
                hits += 1

        sources = _sources_from_body({"messages": messages})
        if any(s["kind"] == _KB_SOURCE_KIND for s in sources):
            kb_requests += 1
        elif sources:
            adhoc_requests += 1

        buckets = [_bucket(by_model, r_model or "unknown")]
        if r_user:
            buckets.append(_bucket(by_user, r_user))
        buckets += [_bucket(by_source, src["name"]) for src in sources]
        for b in buckets:
            b["attached"] += 1
            if readable:
                b["evaluated"] += 1
                if cited:
                    b["cited"] += 1

        # Only an answer we actually read can be said to have cited nothing. Listing an
        # unpaired request here sends the reader off to investigate a question that may
        # well have been answered perfectly.
        if readable and not cited and len(zero_citation) < zero_citation_limit:
            preview = (prompt or "").strip().replace("\n", " ")
            zero_citation.append({
                "rid": rid,
                "ts": ts.isoformat() if ts else None,
                "user_id": r_user,
                "model": r_model,
                "question_preview": preview[:200],
            })

    # None, not 0.0: with no answer to read there is no rate, and 0.0 is a verdict.
    # Rounding happens once, in the display layer (see metrics_registry.js).
    def _rate(d: Dict[str, int]) -> Optional[float]:
        return (d["cited"] / d["evaluated"] * 100.0) if d["evaluated"] else None

    def _row(key_name: str, key: str, v: Dict[str, int]) -> Dict[str, Any]:
        return {
            key_name: key,
            "attached": v["attached"],
            "evaluated": v["evaluated"],
            "unpaired": v["attached"] - v["evaluated"],
            "cited": v["cited"],
            "hit_rate": _rate(v),
        }

    return {
        "kb_attached": attached,
        "evaluated": evaluated,
        "unpaired": attached - evaluated,
        "cited": hits,
        "hit_rate": (hits / evaluated * 100.0) if evaluated else None,
        "by_model": sorted(
            [_row("model", k, v) for k, v in by_model.items()],
            key=lambda x: x["attached"], reverse=True,
        ),
        "by_source": sorted(
            [_row("source", k, v) for k, v in by_source.items()],
            key=lambda x: x["attached"], reverse=True,
        ),
        "by_user": sorted(
            [_row("user_id", k, v) for k, v in by_user.items()],
            key=lambda x: x["attached"], reverse=True,
        ),
        "zero_citation_messages": zero_citation,
        # Coverage — "of everything asked, how much reached the shared corpus". Both
        # sides come from chat.request in this same window under the same filters, so
        # the ratio cannot exceed 100%.
        #
        # It deliberately does NOT reuse `kb_attached` as its numerator: that figure
        # counts any <source> tag, including a file the user dragged into one chat.
        "coverage": {
            "total_requests": total_requests,
            "kb_requests": kb_requests,
            "adhoc_requests": adhoc_requests,
            "coverage_percent": (kb_requests / total_requests * 100.0) if total_requests else None,
        },
    }


# ─── Storage health (OpenWebUI DB, unpooled) ─────────────────────────────────

def _openwebui_database_url() -> str:
    parsed = urlparse(DATABASE_URL)
    return DATABASE_URL.replace(parsed.path, "/openwebui")


def _collection_candidates(file_id: str) -> List[str]:
    """Collection names a file's chunks may live under across OpenWebUI versions."""
    return [file_id, f"file-{file_id}"]


def _compute_storage_health() -> Dict[str, Any]:
    """Read-only OpenWebUI queries for storage anomalies. Unpooled connection."""
    conn = psycopg2.connect(_openwebui_database_url(), connect_timeout=5)
    try:
        cur = conn.cursor()

        # Chunk counts per collection.
        cur.execute("SELECT collection_name, count(*) FROM document_chunk GROUP BY collection_name")
        chunks_by_collection: Dict[str, int] = {r[0]: int(r[1]) for r in cur.fetchall()}

        # Knowledge bases with their attached files.
        cur.execute(
            """
            SELECT k.id, k.name, k.user_id, k.created_at,
                   array_remove(array_agg(kf.file_id), NULL) AS file_ids
            FROM knowledge k
            LEFT JOIN knowledge_file kf ON kf.knowledge_id = k.id
            GROUP BY k.id, k.name, k.user_id, k.created_at
            """
        )
        kb_rows = cur.fetchall()

        # Files with size metadata (for the outlier heuristic).
        cur.execute("SELECT id, filename, user_id, meta FROM file")
        file_rows = cur.fetchall()

        # All known collection identifiers, for orphan detection.
        cur.execute("SELECT id FROM knowledge")
        knowledge_ids = {r[0] for r in cur.fetchall()}
        cur.close()
    finally:
        conn.close()

    # --- Zero-chunk knowledge bases ---
    zero_chunk_kbs = []
    for kid, name, user_id, created_at, file_ids in kb_rows:
        file_ids = file_ids or []
        candidates = [kid]
        for fid in file_ids:
            candidates.extend(_collection_candidates(fid))
        chunk_total = sum(chunks_by_collection.get(c, 0) for c in candidates)
        if len(file_ids) > 0 and chunk_total == 0:
            zero_chunk_kbs.append({
                "id": kid,
                "name": name,
                "owner": user_id,
                "created_at": _epoch_to_iso(created_at),
                "file_count": len(file_ids),
            })

    # --- Valid collection set + orphan detection ---
    valid_collections = set(knowledge_ids)
    file_meta: Dict[str, tuple] = {}
    for fid, filename, user_id, meta in file_rows:
        for c in _collection_candidates(fid):
            valid_collections.add(c)
        file_meta[fid] = (filename, user_id, meta)

    orphaned = [
        {"collection_name": col, "chunk_count": cnt}
        for col, cnt in sorted(chunks_by_collection.items(), key=lambda x: x[1], reverse=True)
        if col not in valid_collections
    ]

    # --- Chunk-count outliers (heuristic) ---
    outliers = []
    for fid, (filename, user_id, meta) in file_meta.items():
        chunk_count = sum(chunks_by_collection.get(c, 0) for c in _collection_candidates(fid))
        if chunk_count == 0:
            continue  # zero-chunk is reported at KB level, not here
        size_bytes = _meta_size(meta)
        if not size_bytes:
            continue
        expected = max(1, round(size_bytes / _CHARS_PER_CHUNK))
        if chunk_count < expected * 0.5:
            outliers.append({
                "file_id": fid,
                "filename": filename,
                "owner": user_id,
                "size_bytes": size_bytes,
                "chunk_count": chunk_count,
                "expected_count": expected,
            })
    outliers.sort(key=lambda x: x["expected_count"] - x["chunk_count"], reverse=True)

    return {
        "zero_chunk_kbs": zero_chunk_kbs,
        "orphaned_chunks": orphaned,
        "chunk_count_outliers": outliers,
    }


def _epoch_to_iso(value) -> Optional[str]:
    """OpenWebUI stores created_at as bigint epoch seconds."""
    if value is None:
        return None
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def _meta_size(meta: Any) -> Optional[int]:
    """Extract a byte size from file.meta JSON, tolerating shape variations."""
    if not isinstance(meta, dict):
        return None
    size = meta.get("size")
    if isinstance(size, (int, float)) and size > 0:
        return int(size)
    inner = meta.get("meta")
    if isinstance(inner, dict) and isinstance(inner.get("size"), (int, float)):
        return int(inner["size"]) or None
    return None


# Short-TTL cache: storage queries are heavier and hit an unpooled connection,
# so a dashboard refresh/poll should not re-run them every time (design Risk 4).
_storage_cache: Dict[str, Any] = {"ts": 0.0, "data": None}
_STORAGE_TTL_SECONDS = 60.0


def query_storage_health(force_refresh: bool = False) -> Dict[str, Any]:
    """Cached storage-health snapshot. Returns ``{"error": ...}`` on DB failure."""
    now = time.monotonic()
    if (not force_refresh and _storage_cache["data"] is not None
            and now - _storage_cache["ts"] < _STORAGE_TTL_SECONDS):
        return {**_storage_cache["data"], "cached": True}

    try:
        data = _compute_storage_health()
    except Exception as e:  # pragma: no cover - defensive
        logger.error("query_storage_health failed: %s", str(e))
        if _storage_cache["data"] is not None:
            return {**_storage_cache["data"], "cached": True, "stale": True}
        return {
            "zero_chunk_kbs": [],
            "orphaned_chunks": [],
            "chunk_count_outliers": [],
            "error": str(e),
        }

    _storage_cache["ts"] = now
    _storage_cache["data"] = data
    return {**data, "cached": False}
