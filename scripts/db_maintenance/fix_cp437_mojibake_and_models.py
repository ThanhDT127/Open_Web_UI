#!/usr/bin/env python3
"""
Idempotent PostgreSQL maintenance utility for Open WebUI Enterprise:
1. Losslessly repairs UTF-8 -> CP437 Mojibake across text, JSON, and JSONB columns
   (caused by Windows PowerShell '>' redirection during pg_dump).
2. Normalizes model metadata (capabilities, toolIds, defaultFeatureIds, profile_image_url)
   and wildcard read access_grants for all active chat and smart-routing models.
3. Aligns PersistentConfig (rag.docling_server_url) and admin role in mw_users.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Signature patterns that ONLY appear when 2/3/4-byte UTF-8 sequences (Vietnamese + Emoji + punctuation)
# are decoded as Code Page 437 (DOS OEM). Never present in valid Vietnamese or English prose.
_MOJIBAKE_MARKER_RE = re.compile(
    r"(?:"
    r"ß[╗║]"  # 0xE1 (ß) + 0xBB/0xBA (╗/║) -> Vietnamese 3-byte vowels (ạ..ự)
    r"|├[íàảãạéèẻẽẹìíòóôõùúýăđĩũơư░▒▓│┤╡╢╖╕╣║╗╝╜╛┐ÇüéâäàåçêëèïîìÄÅÉæÆôöòûùÿÖÜ¢£¥₧ƒ]"
    r"|─[Ééàảãạăâêôơư░▒▓│┤]"  # 0xC4 (─) -> Đ, đ, ă, Ă, etc.
    r"|╞[░▒▓│┤¡º]"  # 0xC6 (╞) -> ư, ơ, Ư, Ơ
    r"|≡ƒ"  # 0xF0 0x9F -> 4-byte Emoji lead
    r"|Γ[¢£Ç¥₧ƒ]"  # 0xE2 -> 3-byte symbols/dingbats/punctuation (⛽, ✅, —, •)
    r")"
)

# Contiguous run of characters that are valid in CP437 and contain at least one non-ASCII char
_NON_ASCII_RUN_RE = re.compile(r"[^\x00-\x7f]+")

DEFAULT_MODEL_CAPABILITIES: Dict[str, bool] = {
    "file_context": True,
    "vision": True,
    "file_upload": True,
    "web_search": True,
    "image_generation": True,
    "code_interpreter": True,
    "citations": True,
    "status_updates": True,
    "builtin_tools": True,
}

DEFAULT_TOOL_IDS: List[str] = [
    "google_gmail_tool",
    "code_interpreter",
    "server:0",
    "server:1",
    "server:2",
    "server:3",
    "server:4",
    "server:5",
    "server:6",
    "server:7",
    "server:8",
    "server:9",
    "server:10",
    "server:11",
]

NON_CHAT_MODEL_PREFIXES = ("gemini-embedding", "cohere/rerank", "rerank-", "stt-", "tts-", "img-")


def _try_cp437_to_utf8(segment: str) -> Optional[str]:
    try:
        raw = segment.encode("cp437")
        decoded = raw.decode("utf-8")
        return decoded
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None


def repair_cp437_mojibake(text: str) -> Tuple[str, bool]:
    """
    Losslessly restore UTF-8 strings that were misinterpreted as CP437.
    Returns (repaired_text, was_modified). Idempotent on clean UTF-8 strings.
    """
    if not text or not isinstance(text, str):
        return text, False
    if not _MOJIBAKE_MARKER_RE.search(text):
        return text, False

    # Fast path: entire string is pure CP437-encoded UTF-8
    whole = _try_cp437_to_utf8(text)
    if whole is not None and whole != text:
        return whole, True

    # Fallback: mixed string containing both already-clean Unicode and CP437 mojibake runs
    changed = False

    def _replace_run(match: re.Match[str]) -> str:
        nonlocal changed
        chunk = match.group(0)
        if not _MOJIBAKE_MARKER_RE.search(chunk):
            return chunk
        fixed = _try_cp437_to_utf8(chunk)
        if fixed is not None and fixed != chunk:
            changed = True
            return fixed
        return chunk

    out = _NON_ASCII_RUN_RE.sub(_replace_run, text)
    return out, changed


def repair_json_value(value: Any) -> Tuple[Any, bool]:
    """Recursively repair CP437 mojibake inside parsed JSON structures (dicts, lists, strings)."""
    if isinstance(value, str):
        return repair_cp437_mojibake(value)
    if isinstance(value, list):
        any_changed = False
        new_list = []
        for item in value:
            fixed_item, c = repair_json_value(item)
            any_changed = any_changed or c
            new_list.append(fixed_item)
        return (new_list if any_changed else value), any_changed
    if isinstance(value, dict):
        any_changed = False
        new_dict: Dict[Any, Any] = {}
        for k, v in value.items():
            fk, ck = repair_cp437_mojibake(k) if isinstance(k, str) else (k, False)
            fv, cv = repair_json_value(v)
            any_changed = any_changed or ck or cv
            new_dict[fk] = fv
        return (new_dict if any_changed else value), any_changed
    return value, False


def is_chat_or_auto_model(model_id: str) -> bool:
    if not model_id:
        return False
    low = model_id.lower()
    return not any(low.startswith(pfx) for pfx in NON_CHAT_MODEL_PREFIXES)


def build_enriched_model_meta(
    model_id: str,
    existing_meta: Optional[Dict[str, Any]],
    available_tool_ids: Optional[Sequence[str]] = None,
) -> Tuple[Dict[str, Any], bool]:
    """
    Ensure chat / auto models have complete capabilities, toolIds, defaultFeatureIds,
    and profile_image_url without clobbering existing custom fields (like knowledge).
    """
    meta: Dict[str, Any] = dict(existing_meta) if isinstance(existing_meta, dict) else {}
    changed = False

    # First repair any mojibake inside meta
    meta, c_moji = repair_json_value(meta)
    changed = changed or c_moji

    if not is_chat_or_auto_model(model_id):
        return meta, changed

    if not meta.get("profile_image_url"):
        meta["profile_image_url"] = "/static/favicon.png"
        changed = True

    caps = meta.get("capabilities")
    if not isinstance(caps, dict) or not caps:
        meta["capabilities"] = dict(DEFAULT_MODEL_CAPABILITIES)
        changed = True
    else:
        for k, v in DEFAULT_MODEL_CAPABILITIES.items():
            if k not in caps:
                caps[k] = v
                changed = True

    tools_target = list(available_tool_ids) if available_tool_ids else list(DEFAULT_TOOL_IDS)
    cur_tools = meta.get("toolIds")
    if not isinstance(cur_tools, list) or not cur_tools:
        meta["toolIds"] = tools_target
        changed = True

    cur_feats = meta.get("defaultFeatureIds")
    if not isinstance(cur_feats, list) or not cur_feats:
        meta["defaultFeatureIds"] = ["web_search"]
        changed = True

    return meta, changed


def _repair_text_or_json_string(raw: str) -> Tuple[str, bool]:
    """Repair a TEXT/VARCHAR cell that may hold either plain text or serialized JSON."""
    if not raw or not isinstance(raw, str):
        return raw, False
    stripped = raw.strip()
    if (stripped.startswith("{") and stripped.endswith("}")) or (
        stripped.startswith("[") and stripped.endswith("]")
    ):
        try:
            parsed = json.loads(raw)
            fixed_obj, c = repair_json_value(parsed)
            if c:
                return json.dumps(fixed_obj, ensure_ascii=False), True
            return raw, False
        except Exception:
            pass
    return repair_cp437_mojibake(raw)


def run_postgres_maintenance(dsn: str, middleware_dsn: Optional[str] = None) -> Dict[str, Any]:
    """Connect to PostgreSQL and execute CP437 mojibake repair + model metadata sync."""
    import psycopg2
    import psycopg2.extras

    stats: Dict[str, Any] = {
        "tables_repaired": {},
        "models_enriched": [],
        "access_grants_added": 0,
        "config_updated": [],
    }

    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    try:
        cur = conn.cursor()

        # 1. Discover all tables with primary key 'id' (or 'key' for config) and text/json/jsonb columns
        cur.execute(
            """
            SELECT c.table_name, c.column_name, c.data_type
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON c.table_schema = t.table_schema AND c.table_name = t.table_name
            WHERE c.table_schema = 'public'
              AND t.table_type = 'BASE TABLE'
              AND c.data_type IN ('text', 'character varying', 'json', 'jsonb')
              AND c.table_name NOT IN ('alembic_version', 'migratehistory')
            ORDER BY c.table_name, c.ordinal_position;
            """
        )
        table_cols: Dict[str, List[Tuple[str, str]]] = {}
        for tbl, col, dtype in cur.fetchall():
            table_cols.setdefault(tbl, []).append((col, dtype))

        for tbl, cols in table_cols.items():
            pk_col = "key" if tbl == "config" else "id"
            col_names = [c for c, _ in cols]
            if pk_col not in col_names and tbl != "config":
                # Check if 'id' exists as non-text (e.g. integer/uuid)
                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s AND column_name = 'id'
                    """,
                    (tbl,),
                )
                if not cur.fetchone():
                    continue

            TargetCols = [c for c, _ in cols if c != pk_col]
            if not TargetCols:
                continue

            quoted_tbl = f'"{tbl}"'
            select_cols = ", ".join([f'"{pk_col}"'] + [f'"{c}"' for c in TargetCols])
            cur.execute(f"SELECT {select_cols} FROM public.{quoted_tbl}")
            rows = cur.fetchall()

            updated_rows = 0
            for row in rows:
                row_pk = row[0]
                updates: Dict[str, Any] = {}
                for idx, (col_name, dtype) in enumerate(
                    [(c, d) for c, d in cols if c != pk_col], start=1
                ):
                    val = row[idx]
                    if val is None:
                        continue
                    if dtype in ("json", "jsonb"):
                        if isinstance(val, str):
                            try:
                                parsed = json.loads(val)
                                fixed_val, c = repair_json_value(parsed)
                                if c:
                                    updates[col_name] = psycopg2.extras.Json(
                                        fixed_val,
                                        dumps=lambda o: json.dumps(o, ensure_ascii=False),
                                    )
                            except Exception:
                                pass
                        else:
                            fixed_val, c = repair_json_value(val)
                            if c:
                                updates[col_name] = psycopg2.extras.Json(
                                    fixed_val,
                                    dumps=lambda o: json.dumps(o, ensure_ascii=False),
                                )
                    else:
                        if isinstance(val, str):
                            fixed_str, c = _repair_text_or_json_string(val)
                            if c:
                                updates[col_name] = fixed_str

                if updates:
                    set_clause = ", ".join(f'"{k}" = %s' for k in updates.keys())
                    params = list(updates.values()) + [row_pk]
                    cur.execute(
                        f'UPDATE public.{quoted_tbl} SET {set_clause} WHERE "{pk_col}" = %s',
                        params,
                    )
                    updated_rows += 1

            if updated_rows > 0:
                stats["tables_repaired"][tbl] = updated_rows

        # 2. Enrich model meta (capabilities, toolIds, defaultFeatureIds, profile_image_url)
        cur.execute('SELECT id, meta FROM public."model" WHERE id = %s', ("chat-gpt-5",))
        ref_row = cur.fetchone()
        ref_tools: List[str] = list(DEFAULT_TOOL_IDS)
        if ref_row and ref_row[1]:
            ref_meta = json.loads(ref_row[1]) if isinstance(ref_row[1], str) else ref_row[1]
            if isinstance(ref_meta, dict) and isinstance(ref_meta.get("toolIds"), list):
                for tid in ref_meta["toolIds"]:
                    if tid not in ref_tools:
                        ref_tools.append(tid)

        cur.execute('SELECT id, name, meta, is_active FROM public."model"')
        for mid, mname, mmeta_raw, is_active in cur.fetchall():
            parsed_meta: Dict[str, Any] = {}
            if isinstance(mmeta_raw, str) and mmeta_raw.strip():
                try:
                    parsed_meta = json.loads(mmeta_raw)
                except Exception:
                    parsed_meta = {}
            elif isinstance(mmeta_raw, dict):
                parsed_meta = mmeta_raw

            enriched_meta, m_changed = build_enriched_model_meta(mid, parsed_meta, ref_tools)
            if m_changed:
                cur.execute(
                    'UPDATE public."model" SET meta = %s WHERE id = %s',
                    (json.dumps(enriched_meta, ensure_ascii=False), mid),
                )
                stats["models_enriched"].append(mid)

            # Ensure wildcard read grant exists for all active models (except private group preset 'demo')
            if is_active and mid != "demo":
                cur.execute(
                    """
                    SELECT 1 FROM public.access_grant
                    WHERE resource_type = 'model' AND resource_id = %s AND permission = 'read'
                    """,
                    (mid,),
                )
                if not cur.fetchone():
                    cur.execute(
                        """
                        INSERT INTO public.access_grant (id, resource_type, resource_id, principal_type, principal_id, permission, created_at)
                        VALUES (%s, 'model', %s, 'user', '*', 'read', EXTRACT(EPOCH FROM NOW())::bigint)
                        """,
                        (str(uuid.uuid4()), mid),
                    )
                    stats["access_grants_added"] += 1

        # 3. Align PersistentConfig docling proxy & ui.model_order_list
        config_Desired = {
            "rag.docling_server_url": "http://middleware:5000/docling-proxy",
            "rag.docling_params": {"image_export_mode": "referenced"},
        }
        for cfg_key, cfg_val in config_Desired.items():
            cur.execute('SELECT value FROM public."config" WHERE key = %s', (cfg_key,))
            row = cur.fetchone()
            if row is not None and row[0] != cfg_val:
                cur.execute(
                    'UPDATE public."config" SET value = %s WHERE key = %s',
                    (json.dumps(cfg_val, ensure_ascii=False), cfg_key),
                )
                stats["config_updated"].append(cfg_key)

        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # 4. Also ensure adminrd@gmail.com has role='admin' in middleware DB
    if middleware_dsn:
        mconn = psycopg2.connect(middleware_dsn)
        try:
            mcur = mconn.cursor()
            mcur.execute(
                "UPDATE mw_users SET role = 'admin', active = true WHERE user_id IN ('adminrd@gmail.com', 'adminrd') AND role <> 'admin'"
            )
            stats["mw_admin_updated"] = mcur.rowcount
            mconn.commit()
            mcur.close()
        finally:
            mconn.close()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix CP437 mojibake and enrich Open WebUI models.")
    parser.add_argument(
        "--dsn",
        default=os.getenv("OPENWEBUI_DATABASE_URL") or os.getenv("DATABASE_URL", ""),
        help="PostgreSQL DSN for openwebui database",
    )
    parser.add_argument(
        "--middleware-dsn",
        default=os.getenv("MIDDLEWARE_DATABASE_URL", ""),
        help="Optional PostgreSQL DSN for middleware database",
    )
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("Error: --dsn or OPENWEBUI_DATABASE_URL is required")

    result = run_postgres_maintenance(args.dsn, args.middleware_dsn or None)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
