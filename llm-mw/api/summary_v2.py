"""
Enhanced summary endpoint with time range, breakdown, and timeseries support.
Primary: queries mw_audit_log DB table. Fallback: reads audit.jsonl file.
"""

import os
import json
import datetime as dt
from typing import Dict, Any, Optional, List, Tuple
from zoneinfo import ZoneInfo
from fastapi import Request, HTTPException
from collections import defaultdict

from config import AUDIT_LOG_FILE, LOG_DIR


def _db_available() -> bool:
    try:
        from core.db import _pool
        return _pool is not None
    except Exception:
        return False


def _get_global_pending_count() -> int:
    """Get the count of all active pending requests from DB or fallback file."""
    if _db_available():
        try:
            from core.db import db_conn
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT count(*) FROM mw_pending")
                count = cur.fetchone()[0]
                cur.close()
            return count or 0
        except Exception:
            pass
            
    # Fallback to pending.csv
    import csv
    from config import PENDING_CSV
    if not os.path.exists(PENDING_CSV):
        return 0
    try:
        with open(PENDING_CSV, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        # Exclude header
        return max(0, len(rows) - 1)
    except Exception:
        return 0


def _load_entries_from_db(cutoff, end_time) -> List[Dict[str, Any]]:
    """Load audit entries from mw_audit_log table as dicts."""
    from core.db import db_conn
    entries = []
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ts, rid, user_id, endpoint, model, purpose, status,
                   status_code, latency_ms, tokens_in, tokens_out, tokens_total,
                   cost_usd, image_count, tts_chars, stt_seconds, video_count,
                   error_type, error_message
            FROM mw_audit_log WHERE ts >= %s AND ts <= %s
            ORDER BY ts ASC
        """, (cutoff, end_time))
        for r in cur.fetchall():
            entries.append({
                "ts": r[0].isoformat() if r[0] else "",
                "rid": r[1] or "", "user_id": r[2] or "unknown",
                "endpoint": r[3] or "", "model": r[4] or "unknown",
                "purpose": r[5], "status": r[6] or "ok",
                "status_code": r[7], "latency_ms": r[8],
                "tokens_in": r[9] or 0, "tokens_out": r[10] or 0,
                "tokens_total": r[11] or 0, "cost_usd": float(r[12] or 0),
                "image_count": r[13], "tts_chars": r[14],
                "stt_seconds": r[15], "video_count": r[16],
                "error_type": r[17], "error_message": r[18],
            })
        cur.close()
    return entries


def _load_entries_from_files(cutoff, end_time) -> List[Dict[str, Any]]:
    """Load audit entries from audit.jsonl files."""
    entries = []
    for log_file in _get_audit_log_files():
        if not os.path.exists(log_file):
            continue
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    ts_str = entry.get("ts", "")
                    if not ts_str:
                        continue
                    entry_time = dt.datetime.fromisoformat(ts_str)
                    if entry_time < cutoff or entry_time > end_time:
                        continue
                    entries.append(entry)
                except Exception:
                    continue
    return entries


def get_summary_v2(
    request: Request,
    minutes: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    bucket: str = "auto"
):
    """
    Enhanced admin endpoint: Aggregate usage statistics with time range support.
    Uses DB if available, falls back to audit.jsonl files.
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    
    # Determine time range
    now_utc = dt.datetime.now(tz=dt.timezone.utc)
    
    if start and end:
        # Parse custom range - normalize 'Z' to '+00:00' for fromisoformat
        try:
            start_normalized = start.replace('Z', '+00:00') if start.endswith('Z') else start
            end_normalized = end.replace('Z', '+00:00') if end.endswith('Z') else end
            
            cutoff = dt.datetime.fromisoformat(start_normalized)
            end_time = dt.datetime.fromisoformat(end_normalized)
            
            # Ensure timezone aware
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=dt.timezone.utc)
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=dt.timezone.utc)
            
            # Validate: start < end
            if cutoff >= end_time:
                raise HTTPException(400, "Start time must be before end time")
        except ValueError as e:
            raise HTTPException(400, f"Invalid datetime format: {e}")
    else:
        # Fallback to minutes
        if minutes is None:
            minutes = 60
        cutoff = now_utc - dt.timedelta(minutes=minutes)
        end_time = now_utc
    
    # DEBUG: Log time range for troubleshooting
    print(f"[SUMMARY_V2] Time range: {cutoff.isoformat()} to {end_time.isoformat()} (minutes={minutes})")
    
    # Auto-determine bucket size if "auto"
    time_range_seconds = (end_time - cutoff).total_seconds()
    if bucket == "auto":
        if time_range_seconds <= 3600:  # <= 1 hour
            bucket_size = "minute"
        elif time_range_seconds <= 86400 * 2:  # <= 2 days
            bucket_size = "hour"
        else:
            bucket_size = "day"
    else:
        bucket_size = bucket
    
    # Define LLM endpoints
    LLM_ENDPOINTS = {
        "/v1/chat/completions": "chat",
        "/v1/embeddings": "embedding",
        "/v1/images/generations": "image",
        "/v1/audio/transcriptions": "audio",
        "/v1/audio/speech": "audio",
        "/v1/video/generations": "video",
    }
    
    # Data structures for rid-based tracking (control-grade)
    rid_status: Dict[str, Tuple[float, str]] = {}  # rid -> (timestamp, status)
    rid_data: Dict[str, Dict[str, Any]] = {}  # rid -> {last event data}
    
    # Timeseries buckets
    timeseries_data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "requests": set(),  # Use set for distinct rids
        "tokens_total": 0,
        "cost_total": 0.0,
        "errors": 0
    })
    
    # Breakdown data (use sets for distinct rid counting)
    user_data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "requests": set(),
        "requests_ok": set(),
        "errors": 0,
        "tokens_total": 0,
        "cost_total": 0.0,
        "latencies": []
    })
    
    model_data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "requests": set(),
        "requests_ok": set(),
        "errors": 0,
        "tokens_total": 0,
        "cost_total": 0.0,
        "latencies": []
    })
    
    # Breakdown by LLM type
    llm_type_counts = {"chat": 0, "embedding": 0, "image": 0, "audio": 0, "video": 0}
    
    # Load entries from DB or file
    try:
        if _db_available():
            raw_entries = _load_entries_from_db(cutoff, end_time)
            source = "database"
        else:
            raw_entries = _load_entries_from_files(cutoff, end_time)
            source = "file"
    except Exception:
        raw_entries = _load_entries_from_files(cutoff, end_time)
        source = "file"
    
    try:
        for entry in raw_entries:
            timestamp_str = entry.get("ts", "")
            if not timestamp_str:
                continue

            # Parse timestamp
            try:
                entry_time = dt.datetime.fromisoformat(timestamp_str)
            except Exception:
                continue

            rid = entry.get("rid", "")
            if not rid:
                continue

            endpoint = entry.get("endpoint", "")
            status = entry.get("status", "ok")
            user_id = entry.get("user_id", "unknown")
            model = entry.get("model", "unknown")

            # Track last status per rid (control-grade)
            entry_ts = entry_time.timestamp()
            if rid not in rid_status or entry_ts > rid_status[rid][0]:
                rid_status[rid] = (entry_ts, status)
                rid_data[rid] = entry

            # Timeseries bucketing
            bucket_key = _get_bucket_key(entry_time, bucket_size)
            timeseries_data[bucket_key]["requests"].add(rid)

            # Only aggregate tokens/cost from final status (ok/reconciled)
            if status in ["ok", "reconciled"]:
                tokens = entry.get("tokens_total", 0)
                cost = entry.get("cost_usd", 0.0)
                latency = entry.get("latency_ms")

                timeseries_data[bucket_key]["tokens_total"] += tokens
                timeseries_data[bucket_key]["cost_total"] += cost

                # User breakdown
                user_data[user_id]["requests"].add(rid)
                user_data[user_id]["requests_ok"].add(rid)
                user_data[user_id]["tokens_total"] += tokens
                user_data[user_id]["cost_total"] += cost
                if latency:
                    user_data[user_id]["latencies"].append(latency)

                # Model breakdown
                model_data[model]["requests"].add(rid)
                model_data[model]["requests_ok"].add(rid)
                model_data[model]["tokens_total"] += tokens
                model_data[model]["cost_total"] += cost
                if latency:
                    model_data[model]["latencies"].append(latency)

            elif status == "error":
                timeseries_data[bucket_key]["errors"] += 1
                user_data[user_id]["requests"].add(rid)
                user_data[user_id]["errors"] += 1
                model_data[model]["requests"].add(rid)
                model_data[model]["errors"] += 1


        # Calculate totals from rid_status (control-grade: last status per rid)
        requests_total = len(rid_status)
        pending_open_count = _get_global_pending_count()
        error_count = sum(1 for _, (_, status) in rid_status.items() if status == "error")
        requests_ok = sum(1 for _, (_, status) in rid_status.items() if status in ["ok", "reconciled"])
        
        # Calculate billable metrics (requests with actual usage)
        billable_calls = 0
        nonbillable_calls = 0
        usage_missing_calls = 0
        
        for rid, data in rid_data.items():
            status = rid_status.get(rid, (0, ""))[1]
            
            # Only check completed requests
            if status not in ["ok", "reconciled"]:
                continue
            
            endpoint = data.get("endpoint", "")
            tokens = data.get("tokens_total", 0)
            cost = data.get("cost_usd", 0.0)
            model = data.get("model", "")
            
            # Determine if billable
            is_image_model = "dall-e" in model.lower() or "imagen" in model.lower() or "stable-diffusion" in model.lower()
            is_audio_model = "whisper" in model.lower() or "tts" in model.lower()
            is_video_model = "sora" in model.lower() or "gen-" in model.lower()
            is_chat_model = endpoint == "/v1/chat/completions" or "gpt" in model.lower() or "claude" in model.lower() or "gemini" in model.lower()
            
            # Billable if:
            # 1. Has cost OR tokens (actual usage recorded)
            # 2. For image models: cost > 0 (images don't have tokens)
            has_usage = cost > 0 or tokens > 0
            
            if has_usage:
                billable_calls += 1
            else:
                nonbillable_calls += 1
                
                # Flag missing usage for chat models (images/audio might legitimately have 0 cost)
                if is_chat_model:
                    usage_missing_calls += 1
        
        # Calculate LLM type breakdown
        for rid, data in rid_data.items():
            endpoint = data.get("endpoint", "")
            status = rid_status.get(rid, (0, ""))[1]
            if status in ["ok", "reconciled"] and endpoint in LLM_ENDPOINTS:
                call_type = LLM_ENDPOINTS[endpoint]
                llm_type_counts[call_type] += 1
        
        # Calculate totals from final events
        total_tokens = sum(d["tokens_total"] for d in user_data.values())
        total_cost = sum(d["cost_total"] for d in user_data.values())
        
        # Calculate P95 latency from all final events
        all_latencies = []
        for user_stats in user_data.values():
            all_latencies.extend(user_stats["latencies"])
        
        p95_latency = None
        if all_latencies:
            all_latencies.sort()
            p95_idx = int(len(all_latencies) * 0.95)
            p95_latency = all_latencies[p95_idx] if p95_idx < len(all_latencies) else all_latencies[-1]
        
        # Calculate error rate
        error_rate = (error_count / requests_total * 100) if requests_total > 0 else 0.0
        
        # Format breakdown by user
        breakdown_by_user = []
        for user_id, stats in user_data.items():
            user_requests_total = len(stats["requests"])
            user_requests_ok = len(stats["requests_ok"])
            user_error_rate = (stats["errors"] / user_requests_total * 100) if user_requests_total > 0 else 0.0
            
            user_p95 = None
            if stats["latencies"]:
                sorted_lat = sorted(stats["latencies"])
                p95_idx = int(len(sorted_lat) * 0.95)
                user_p95 = sorted_lat[p95_idx] if p95_idx < len(sorted_lat) else sorted_lat[-1]
            
            breakdown_by_user.append({
                "user_id": user_id,
                "requests_total": user_requests_total,
                "requests_ok": user_requests_ok,
                "errors": stats["errors"],
                "error_rate_percent": round(user_error_rate, 2),
                "tokens_total": stats["tokens_total"],
                "cost_usd": round(stats["cost_total"], 6),
                "p95_latency_ms": round(user_p95, 2) if user_p95 else None
            })
        
        # Sort by cost descending
        breakdown_by_user.sort(key=lambda x: x["cost_usd"], reverse=True)
        
        # Format breakdown by model
        breakdown_by_model = []
        for model, stats in model_data.items():
            model_requests_total = len(stats["requests"])
            model_requests_ok = len(stats["requests_ok"])
            model_error_rate = (stats["errors"] / model_requests_total * 100) if model_requests_total > 0 else 0.0
            
            model_p95 = None
            if stats["latencies"]:
                sorted_lat = sorted(stats["latencies"])
                p95_idx = int(len(sorted_lat) * 0.95)
                model_p95 = sorted_lat[p95_idx] if p95_idx < len(sorted_lat) else sorted_lat[-1]
            
            breakdown_by_model.append({
                "model": model,
                "requests_total": model_requests_total,
                "requests_ok": model_requests_ok,
                "errors": stats["errors"],
                "error_rate_percent": round(model_error_rate, 2),
                "tokens_total": stats["tokens_total"],
                "cost_usd": round(stats["cost_total"], 6),
                "p95_latency_ms": round(model_p95, 2) if model_p95 else None
            })
        
        # Sort by cost descending
        breakdown_by_model.sort(key=lambda x: x["cost_usd"], reverse=True)
        
        # Format timeseries
        timeseries = []
        for bucket_key in sorted(timeseries_data.keys()):
            data = timeseries_data[bucket_key]
            timeseries.append({
                "ts": bucket_key,
                "requests_total": len(data["requests"]),
                "tokens_total": data["tokens_total"],
                "cost_usd": round(data["cost_total"], 6),
                "errors": data["errors"]
            })
        


        return {
            "time_range": {
                "start": cutoff.isoformat(),
                "end": end_time.isoformat(),
                "bucket_size": bucket_size
            },
            "totals": {
                "requests_total": requests_total,
                "requests_ok": requests_ok,
                "pending_open_count": pending_open_count,
                "error_count": error_count,
                "error_rate_percent": round(error_rate, 2),
                "tokens_total": total_tokens,
                "cost_total_usd": round(total_cost, 6),
                "p95_latency_ms": round(p95_latency, 2) if p95_latency else None,
                "chat_calls": llm_type_counts["chat"],
                "embedding_calls": llm_type_counts["embedding"],
                "image_calls": llm_type_counts["image"],
                "audio_calls": llm_type_counts["audio"],
                "video_calls": llm_type_counts["video"],
                # NEW: Billable metrics
                "billable_calls": billable_calls,
                "nonbillable_calls": nonbillable_calls,
                "usage_missing_calls": usage_missing_calls
            },
            "breakdown_by_user": breakdown_by_user[:20],  # Top 20
            "breakdown_by_model": breakdown_by_model[:20],  # Top 20
            "timeseries": timeseries
        }
    
    except Exception as e:
        return {"error": str(e)}


def _get_audit_log_files() -> List[str]:
    """
    Get list of audit log files to read (main + rotated).
    Returns up to 10 most recent files.
    """
    files = [AUDIT_LOG_FILE]
    
    # Check for rotated files: audit.jsonl.1, audit.jsonl.2, etc.
    for i in range(1, 11):  # Check up to 10 rotated files
        rotated_file = f"{AUDIT_LOG_FILE}.{i}"
        if os.path.exists(rotated_file):
            files.append(rotated_file)
    
    # Sort by modification time (newest first)
    files.sort(key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0, reverse=True)
    
    return files[:10]  # Return up to 10 most recent


def _get_bucket_key(dt_obj: dt.datetime, bucket_size: str) -> str:
    """
    Generate bucket key for timeseries grouping.
    
    Args:
        dt_obj: datetime object
        bucket_size: "minute" | "hour" | "day"
        
    Returns:
        ISO format string truncated to bucket granularity
    """
    if bucket_size == "minute":
        return dt_obj.strftime("%Y-%m-%dT%H:%M:00")
    elif bucket_size == "hour":
        return dt_obj.strftime("%Y-%m-%dT%H:00:00")
    elif bucket_size == "day":
        return dt_obj.strftime("%Y-%m-%dT00:00:00")
    else:
        return dt_obj.strftime("%Y-%m-%dT%H:00:00")
