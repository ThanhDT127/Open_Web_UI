"""
Knowledge-base analytics queries for the dashboard.

Adoption / value / governance over the OpenWebUI knowledge corpus — distinct from
:mod:`core.rag_health`, which covers operational anomalies. Three read-only layers:

  * Inventory  — corpus totals, growth timeseries and type/size distributions,
                 read directly from the OpenWebUI ``knowledge`` / ``file`` /
                 ``document_chunk`` tables (unpooled ``psycopg2`` connection, same
                 pattern as :func:`core.identity.load_openwebui_users`). Cached for
                 a short TTL — the "corpus snapshot" is shared by all three layers.
  * KB value   — per-KB demand (attach count mined from ``mw_request_log``),
                 quality (citation hit-rate, same ``[N]``-marker logic as
                 ``core.rag_health``), supply (files/chunks/bytes) and freshness,
                 combined into a Star / Needs-tuning / Dead-knowledge / Unproven
                 classification.
  * Governance — duplicate files (by ``file.hash``), orphaned / ad-hoc files, and
                 per-owner concentration.

Spike-driven decisions (see ``openspec/changes/add-knowledge-analytics-dashboard/design.md``):
  * KB membership is ``file.meta.data.knowledge_id`` INNER-JOINed to the live
    ``knowledge`` table — the ``knowledge_file`` join table is stale, and many
    files carry ``knowledge_id`` values whose KB has since been deleted.
  * Usage is linked by extracting ``Filename:`` / ``Source:`` document markers
    embedded in ``<source>`` content and matching on filename *stem* (the log may
    carry a different extension than the stored file). A bare ``<source id=`` is
    NOT evidence of an attachment (it also appears in the citation template).
  * Dedup uses the ``file.hash`` column, not ``meta.file_hash`` (mostly null).
"""

import re
import time
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import psycopg2

from config import DATABASE_URL

logger = logging.getLogger("llm_mw")

# ─── Classification thresholds (documented constants, tune as data grows) ────
MIN_SAMPLE_ATTACHMENTS = 5   # below this a KB is "Unproven", not judged
GOOD_HIT_RATE = 60.0         # citation hit-rate (%) separating Star / Needs-tuning

# Document-identity markers OpenWebUI embeds inside <source> content, plus the
# citation marker reused from core.rag_health for the quality signal.
_FILENAME_MARKER_RE = re.compile(r'(?:Filename|Source):\s*([^\s<\\"]+\.[A-Za-z0-9]{2,5})')
_CITATION_RE = re.compile(r'\[(\d+(?:\s*,\s*\d+)*)\]')

_CACHE_TTL_SECONDS = 60.0


# ─── OpenWebUI corpus snapshot (unpooled, cached) ────────────────────────────

def _openwebui_database_url() -> str:
    parsed = urlparse(DATABASE_URL)
    return DATABASE_URL.replace(parsed.path, "/openwebui")


def _stem(filename: Optional[str]) -> str:
    """Normalized match key: lowercase, whitespace-trimmed, extension stripped."""
    if not filename:
        return ""
    name = str(filename).strip().lower()
    return re.sub(r"\.[^.]+$", "", name)


def _epoch_to_iso(value) -> Optional[str]:
    """OpenWebUI stores created_at/updated_at as bigint epoch seconds."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def _meta_size(meta: Any) -> int:
    """Byte size from file.meta JSON, tolerating shape variations. 0 if unknown."""
    if not isinstance(meta, dict):
        return 0
    size = meta.get("size")
    if isinstance(size, (int, float)) and size > 0:
        return int(size)
    inner = meta.get("meta")
    if isinstance(inner, dict) and isinstance(inner.get("size"), (int, float)):
        return int(inner["size"])
    return 0


def _meta_content_type(meta: Any, filename: str) -> str:
    """content_type from file.meta, falling back to the filename extension."""
    if isinstance(meta, dict):
        ct = meta.get("content_type")
        if isinstance(ct, str) and ct:
            return ct
    m = re.search(r"\.([A-Za-z0-9]{1,6})$", filename or "")
    return f"application/{m.group(1).lower()}" if m else "unknown"


def _meta_knowledge_id(meta: Any) -> Optional[str]:
    """The KB a file was uploaded into (``meta.data.knowledge_id``)."""
    if not isinstance(meta, dict):
        return None
    data = meta.get("data")
    if isinstance(data, dict):
        kid = data.get("knowledge_id")
        return kid or None
    return None


def _meta_collection(meta: Any) -> Optional[str]:
    if isinstance(meta, dict):
        col = meta.get("collection_name")
        return col or None
    return None


def _compute_corpus() -> Dict[str, Any]:
    """Read-only snapshot of the OpenWebUI knowledge corpus. Unpooled connection."""
    conn = psycopg2.connect(_openwebui_database_url(), connect_timeout=5)
    try:
        cur = conn.cursor()

        cur.execute("SELECT id, name, user_id, created_at, updated_at FROM knowledge")
        kb_rows = cur.fetchall()

        cur.execute("SELECT id, filename, user_id, meta, hash, created_at FROM file")
        file_rows = cur.fetchall()

        cur.execute("SELECT collection_name, count(*) FROM document_chunk GROUP BY collection_name")
        chunks_by_collection: Dict[str, int] = {r[0]: int(r[1]) for r in cur.fetchall()}

        cur.execute('SELECT id, name, email FROM "user"')
        users = {r[0]: {"name": r[1], "email": r[2]} for r in cur.fetchall()}
        cur.close()
    finally:
        conn.close()

    knowledge = {
        kid: {
            "id": kid,
            "name": name,
            "owner": user_id,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        for kid, name, user_id, created_at, updated_at in kb_rows
    }
    live_kb_ids = set(knowledge.keys())

    files: List[Dict[str, Any]] = []
    for fid, filename, user_id, meta, file_hash, created_at in file_rows:
        kid = _meta_knowledge_id(meta)
        files.append({
            "id": fid,
            "filename": filename,
            "stem": _stem(filename),
            "owner": user_id,
            "size": _meta_size(meta),
            "content_type": _meta_content_type(meta, filename),
            "hash": file_hash,
            "knowledge_id": kid if kid in live_kb_ids else None,
            "dangling_kb_id": kid if (kid and kid not in live_kb_ids) else None,
            "collection_name": _meta_collection(meta),
            "created_at": created_at,
        })

    return {
        "knowledge": knowledge,
        "files": files,
        "chunks_by_collection": chunks_by_collection,
        "users": users,
    }


_corpus_cache: Dict[str, Any] = {"ts": 0.0, "data": None}


def _get_corpus(force_refresh: bool = False) -> Dict[str, Any]:
    """Cached corpus snapshot shared by inventory / value / governance layers."""
    now = time.monotonic()
    if (not force_refresh and _corpus_cache["data"] is not None
            and now - _corpus_cache["ts"] < _CACHE_TTL_SECONDS):
        return _corpus_cache["data"]
    data = _compute_corpus()
    _corpus_cache["ts"] = now
    _corpus_cache["data"] = data
    return data


def _owner_label(users: Dict[str, Any], user_id: Optional[str]) -> str:
    if not user_id:
        return "(unknown)"
    u = users.get(user_id)
    return (u.get("name") or u.get("email") or user_id) if u else user_id


def _kb_chunk_count(kb_id: str, files: List[Dict[str, Any]], chunks: Dict[str, int]) -> int:
    """Sum chunks across the collections of a KB's files (+ the KB id itself)."""
    total = chunks.get(kb_id, 0)
    for f in files:
        if f["knowledge_id"] == kb_id and f["collection_name"]:
            total += chunks.get(f["collection_name"], 0)
    return total


# ─── Layer 1: Inventory ──────────────────────────────────────────────────────

def _in_range(epoch, start: datetime, end: datetime) -> bool:
    if epoch is None:
        return False
    try:
        ts = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return False
    return start <= ts <= end


def query_inventory(start: datetime, end: datetime, force_refresh: bool = False) -> Dict[str, Any]:
    """Corpus totals, KB/file growth timeseries, and type/size distributions."""
    corpus = _get_corpus(force_refresh)
    knowledge = corpus["knowledge"]
    files = corpus["files"]
    chunks = corpus["chunks_by_collection"]

    total_bytes = sum(f["size"] for f in files)
    total_chunks = sum(chunks.values())

    # Growth: KB & file creations bucketed by day within range.
    day_buckets: Dict[str, Dict[str, int]] = defaultdict(lambda: {"kbs": 0, "files": 0})
    for kb in knowledge.values():
        if _in_range(kb["created_at"], start, end):
            day = _epoch_to_iso(kb["created_at"])[:10]
            day_buckets[day]["kbs"] += 1
    for f in files:
        if _in_range(f["created_at"], start, end):
            day = _epoch_to_iso(f["created_at"])[:10]
            day_buckets[day]["files"] += 1
    growth = [
        {"ts": day, "kbs": v["kbs"], "files": v["files"]}
        for day, v in sorted(day_buckets.items())
    ]

    # Distributions across the whole corpus (not range-limited).
    by_type: Dict[str, Dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    for f in files:
        t = by_type[f["content_type"]]
        t["count"] += 1
        t["bytes"] += f["size"]
    type_distribution = sorted(
        [{"content_type": k, "count": v["count"], "bytes": v["bytes"]} for k, v in by_type.items()],
        key=lambda x: x["count"], reverse=True,
    )

    size_buckets = {"<100KB": 0, "100KB–1MB": 0, "1–10MB": 0, ">10MB": 0}
    for f in files:
        s = f["size"]
        if s < 100_000:
            size_buckets["<100KB"] += 1
        elif s < 1_000_000:
            size_buckets["100KB–1MB"] += 1
        elif s < 10_000_000:
            size_buckets["1–10MB"] += 1
        else:
            size_buckets[">10MB"] += 1

    return {
        "totals": {
            "knowledge_bases": len(knowledge),
            "files": len(files),
            "chunks": total_chunks,
            "storage_bytes": total_bytes,
        },
        "growth": growth,
        "type_distribution": type_distribution,
        "size_distribution": [{"bucket": k, "count": v} for k, v in size_buckets.items()],
    }


# ─── Usage mining from mw_request_log (demand + quality) ─────────────────────

def _has_citation(content: Optional[str]) -> bool:
    return bool(content) and bool(_CITATION_RE.search(content))


def _query_stem_usage(start: datetime, end: datetime) -> Dict[str, Dict[str, Any]]:
    """Per source-document usage keyed by filename *stem*.

    Only ``chat.request`` payloads carrying a ``Filename:``/``Source:`` document
    marker count as attachments; the paired ``chat.response`` (by ``rid``) decides
    whether it was cited.
    """
    from core.db import db_conn

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            WITH req AS (
                SELECT payload->>'rid'          AS rid,
                       ts,
                       (payload->'body')::text  AS body
                FROM mw_request_log
                WHERE ts >= %s AND ts <= %s
                  AND payload->>'event' = 'chat.request'
                  AND payload->>'rid' IS NOT NULL
                  AND ((payload->'body')::text LIKE '%%Filename:%%'
                       OR (payload->'body')::text LIKE '%%Source:%%')
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
            SELECT req.rid, req.ts, req.body, resp.content
            FROM req LEFT JOIN resp ON resp.rid = req.rid
            """,
            (start, end, start, end),
        )
        rows = cur.fetchall()
        cur.close()

    usage: Dict[str, Dict[str, Any]] = {}
    for rid, ts, body, content in rows:
        stems = {_stem(m) for m in _FILENAME_MARKER_RE.findall(body or "")}
        stems.discard("")
        if not stems:
            continue
        cited = _has_citation(content)
        for stem in stems:
            u = usage.setdefault(stem, {"attach": 0, "cited": 0, "last_ts": None})
            u["attach"] += 1
            if cited:
                u["cited"] += 1
            iso = ts.isoformat() if ts else None
            if iso and (u["last_ts"] is None or iso > u["last_ts"]):
                u["last_ts"] = iso
    return usage


def _stems_to_kbs(files: List[Dict[str, Any]]) -> Dict[str, set]:
    """Map a filename stem to the set of live KB ids that contain a file with it."""
    mapping: Dict[str, set] = defaultdict(set)
    for f in files:
        if f["stem"] and f["knowledge_id"]:
            mapping[f["stem"]].add(f["knowledge_id"])
    return mapping


def _classify(attach: int, hit_rate: float, chunk_count: int) -> str:
    if attach == 0:
        return "dead" if chunk_count > 0 else "unproven"
    if attach < MIN_SAMPLE_ATTACHMENTS:
        return "unproven"
    return "star" if hit_rate >= GOOD_HIT_RATE else "needs_tuning"


def query_kb_value(start: datetime, end: datetime, force_refresh: bool = False) -> Dict[str, Any]:
    """Per-KB value matrix + the ambiguous / unattributed usage disclosures."""
    corpus = _get_corpus(force_refresh)
    knowledge = corpus["knowledge"]
    files = corpus["files"]
    chunks = corpus["chunks_by_collection"]
    users = corpus["users"]

    usage = _query_stem_usage(start, end)
    stem_kbs = _stems_to_kbs(files)

    # Aggregate unambiguous usage per KB; hold ambiguous stems aside (design #7).
    per_kb: Dict[str, Dict[str, Any]] = {
        kid: {"attach": 0, "cited": 0, "last_ts": None} for kid in knowledge
    }
    ambiguous: List[Dict[str, Any]] = []
    unattributed: List[Dict[str, Any]] = []
    for stem, u in usage.items():
        kids = stem_kbs.get(stem)
        if not kids:
            unattributed.append({"source": stem, "attach": u["attach"]})
            continue
        if len(kids) > 1:
            ambiguous.append({"source": stem, "attach": u["attach"], "kb_count": len(kids)})
            continue
        kid = next(iter(kids))
        agg = per_kb[kid]
        agg["attach"] += u["attach"]
        agg["cited"] += u["cited"]
        if u["last_ts"] and (agg["last_ts"] is None or u["last_ts"] > agg["last_ts"]):
            agg["last_ts"] = u["last_ts"]

    rows = []
    counts = {"star": 0, "needs_tuning": 0, "dead": 0, "unproven": 0}
    for kid, kb in knowledge.items():
        kb_files = [f for f in files if f["knowledge_id"] == kid]
        chunk_count = _kb_chunk_count(kid, files, chunks)
        size_bytes = sum(f["size"] for f in kb_files)
        u = per_kb[kid]
        hit_rate = (u["cited"] / u["attach"] * 100.0) if u["attach"] else 0.0
        category = _classify(u["attach"], hit_rate, chunk_count)
        counts[category] += 1
        rows.append({
            "id": kid,
            "name": kb["name"],
            "owner": _owner_label(users, kb["owner"]),
            "file_count": len(kb_files),
            "chunk_count": chunk_count,
            "size_bytes": size_bytes,
            "attach_count": u["attach"],
            "cited": u["cited"],
            "hit_rate": round(hit_rate, 1),
            "last_attached": u["last_ts"],
            "created_at": _epoch_to_iso(kb["created_at"]),
            "updated_at": _epoch_to_iso(kb["updated_at"]),
            "category": category,
        })

    rows.sort(key=lambda r: (r["attach_count"], r["chunk_count"]), reverse=True)
    return {
        "knowledge_bases": rows,
        "category_counts": counts,
        "ambiguous_sources": sorted(ambiguous, key=lambda x: x["attach"], reverse=True),
        "unattributed_sources": sorted(unattributed, key=lambda x: x["attach"], reverse=True),
    }


# ─── Layer 3: Governance ─────────────────────────────────────────────────────

def query_governance(force_refresh: bool = False) -> Dict[str, Any]:
    """Duplicate files, orphan/ad-hoc files, and per-owner concentration."""
    corpus = _get_corpus(force_refresh)
    knowledge = corpus["knowledge"]
    files = corpus["files"]
    users = corpus["users"]

    # Duplicates by file.hash (skip null hashes).
    by_hash: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for f in files:
        if f["hash"]:
            by_hash[f["hash"]].append(f)
    duplicates = []
    reclaimable = 0
    for h, group in by_hash.items():
        if len(group) < 2:
            continue
        size = max((g["size"] for g in group), default=0)
        kbs = {g["knowledge_id"] for g in group if g["knowledge_id"]}
        waste = size * (len(group) - 1)
        reclaimable += waste
        duplicates.append({
            "hash": h,
            "filename": group[0]["filename"],
            "copies": len(group),
            "size_bytes": size,
            "kb_count": len(kbs),
            "reclaimable_bytes": waste,
        })
    duplicates.sort(key=lambda x: x["reclaimable_bytes"], reverse=True)

    # Orphans: ad-hoc (no knowledge_id at all) vs dangling (KB deleted).
    adhoc = [f for f in files if not f["knowledge_id"] and not f["dangling_kb_id"]]
    dangling = [f for f in files if f["dangling_kb_id"]]

    # Owner concentration.
    owner: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"kbs": 0, "files": 0, "bytes": 0})
    for kb in knowledge.values():
        owner[kb["owner"]]["kbs"] += 1
    for f in files:
        o = owner[f["owner"]]
        o["files"] += 1
        o["bytes"] += f["size"]
    owners = sorted(
        [{"owner": _owner_label(users, uid), "knowledge_bases": v["kbs"],
          "files": v["files"], "storage_bytes": v["bytes"]} for uid, v in owner.items()],
        key=lambda x: x["storage_bytes"], reverse=True,
    )

    return {
        "duplicates": duplicates,
        "reclaimable_bytes": reclaimable,
        "orphans": {
            "adhoc_count": len(adhoc),
            "adhoc_bytes": sum(f["size"] for f in adhoc),
            "dangling_count": len(dangling),
            "dangling_bytes": sum(f["size"] for f in dangling),
        },
        "owners": owners,
    }
