"""
TDD verification suite for LLM Middleware & Proxy concurrency hardening:
1. Bounded DB pool sizing per worker (DB_POOL_MIN=2, DB_POOL_MAX=10).
2. Non-blocking asyncio event loop for Docling ZIP/WebP extraction and DB/file logging.
3. Single-leader daily digest execution across multiple Uvicorn workers.
4. Multi-process safe rotating file handler across concurrent writers.
5. Corporate NAT-safe Nginx login rate-limit + upstream keepalive.
6. Strict YAML duplicate-key check for litellm/litellm_config.yaml.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import pathlib
import sys
import threading
import time
import zipfile
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
import yaml
from PIL import Image

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LLM_MW_DIR = REPO_ROOT / "llm-mw"
if str(LLM_MW_DIR) not in sys.path:
    sys.path.insert(0, str(LLM_MW_DIR))


# ---------------------------------------------------------------------------
# 1. DB Pool Sizing
# ---------------------------------------------------------------------------

def test_config_db_pool_defaults_bounded_to_10():
    """config.py must default DB_POOL_MIN=2 and DB_POOL_MAX=10 instead of hardcoded maxconn=30."""
    config_src = (LLM_MW_DIR / "config.py").read_text(encoding="utf-8")
    assert "maxconn=30" not in config_src, "config.py still hardcodes maxconn=30"
    assert "DB_POOL_MAX" in config_src, "config.py must support DB_POOL_MAX env var"
    assert "DB_POOL_MIN" in config_src, "config.py must support DB_POOL_MIN env var"

    import config as mw_config
    assert getattr(mw_config, "DB_POOL_MIN", None) == 2
    assert getattr(mw_config, "DB_POOL_MAX", None) == 10


# ---------------------------------------------------------------------------
# 2. Non-Blocking Event Loop (Docling ZIP + Logging Dual-Write)
# ---------------------------------------------------------------------------

def _make_sample_docling_zip() -> bytes:
    img = Image.new("RGB", (64, 64), color=(20, 120, 220))
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.md", "# Hợp đồng\n\n![Ảnh](figures/fig1.png)\n")
        zf.writestr("figures/fig1.png", img_buf.getvalue())
    return zip_buf.getvalue()


def test_docling_zip_extraction_runs_off_event_loop(tmp_path):
    """docling_proxy ZIP extraction + WebP compression must execute off the main event loop thread."""
    import api.docling as docling_mod
    import utils.media as media_mod

    main_thread_id = threading.get_ident()
    observed_worker_threads: list[int] = []
    original_convert = media_mod.convert_bytes_to_webp

    def slow_convert(image_bytes: bytes, quality: int = 80) -> bytes:
        observed_worker_threads.append(threading.get_ident())
        time.sleep(0.12)
        return original_convert(image_bytes, quality=quality)

    zip_payload = _make_sample_docling_zip()

    async def _run():
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.headers = {"content-type": "application/zip"}
        fake_resp.content = zip_payload

        fake_client = MagicMock()

        async def _fake_request(*args, **kwargs):
            return fake_resp

        fake_client.request = _fake_request

        fake_req = MagicMock()
        fake_req.url.path = "/docling-proxy/v1/convert/file"
        fake_req.method = "POST"
        fake_req.headers = {"host": "openwebui.rangdong.com.vn:51122", "x-forwarded-proto": "https"}
        fake_req.query_params = {}
        fake_req.app.state.http_client = fake_client

        async def _empty_body():
            return b"raw"

        fake_req.body = _empty_body

        ticks = 0

        async def _heartbeat():
            nonlocal ticks
            for _ in range(5):
                await asyncio.sleep(0.02)
                ticks += 1

        with patch.object(media_mod, "MW_MEDIA_DIR", str(tmp_path)), \
             patch.object(media_mod, "convert_bytes_to_webp", side_effect=slow_convert):
            resp, _ = await asyncio.gather(
                docling_mod.docling_proxy(fake_req),
                _heartbeat(),
            )
        return resp, ticks

    resp, ticks = asyncio.run(_run())
    assert resp.status_code == 200
    assert observed_worker_threads, "WebP conversion was never invoked"
    assert all(tid != main_thread_id for tid in observed_worker_threads), (
        "Docling WebP compression ran on the main asyncio event loop thread!"
    )
    assert ticks >= 3, f"Event loop was blocked during Docling ZIP conversion (ticks={ticks})"


def test_logging_dual_write_runs_off_event_loop():
    """detail_log and write_audit_line must offload blocking DB writes to a worker thread when loop is active."""
    import core.db as db_mod
    import utils.logging as log_mod

    main_thread_id = threading.get_ident()
    db_threads: list[int] = []

    def slow_insert_audit(data: dict):
        db_threads.append(threading.get_ident())
        time.sleep(0.08)

    def slow_insert_req(payload: dict):
        db_threads.append(threading.get_ident())
        time.sleep(0.08)

    async def _run():
        t0 = time.perf_counter()
        with patch.object(db_mod, "_pool", object()), \
             patch.object(db_mod, "insert_audit_log", side_effect=slow_insert_audit), \
             patch.object(db_mod, "insert_request_log", side_effect=slow_insert_req):
            log_mod.detail_log("unit_test_event", status=200)
            log_mod.write_audit_line({"rid": "r1", "user_id": "u1", "endpoint": "/v1/chat/completions"})
            call_elapsed = time.perf_counter() - t0
            if hasattr(log_mod, "flush_log_executor"):
                await asyncio.to_thread(log_mod.flush_log_executor)
            else:
                await asyncio.sleep(0.25)
        return call_elapsed

    elapsed = asyncio.run(_run())
    assert elapsed < 0.05, f"Logging blocked the event loop for {elapsed:.3f}s"
    assert len(db_threads) == 2
    assert all(tid != main_thread_id for tid in db_threads), (
        "psycopg2 log dual-write executed on the main event loop thread!"
    )


# ---------------------------------------------------------------------------
# 3. Single-Leader Daily Digest Across Multiple Workers
# ---------------------------------------------------------------------------

def test_daily_digest_sends_only_once_across_two_workers():
    """Two workers firing send_daily_digest on the same VN day must send exactly 1 SMTP email."""
    import core.alerting as alerting_mod
    import core.auth as auth_mod
    import core.db as db_mod
    import core.notification as notif_mod

    state_lock = threading.Lock()
    advisory_held = False
    config_store: dict[str, dict] = {}
    sent_emails: list[tuple] = []
    now_dt = notif_mod.datetime.now()

    class FakeCursor:
        def __init__(self):
            self._rows = []

        def execute(self, query: str, params=None):
            q = " ".join(query.split())
            if "pg_try_advisory_lock" in q:
                nonlocal advisory_held
                with state_lock:
                    if advisory_held:
                        self._rows = [(False,)]
                    else:
                        advisory_held = True
                        self._rows = [(True,)]
            elif "pg_advisory_unlock" in q:
                with state_lock:
                    advisory_held = False
                self._rows = [(True,)]
            elif "FROM mw_config" in q and "daily_digest_state" in (str(params) + q):
                with state_lock:
                    val = config_store.get("daily_digest_state")
                    self._rows = [(val,)] if val is not None else []
            elif "INSERT INTO mw_config" in q and params:
                import json as _json
                with state_lock:
                    raw = params[0] if len(params) == 1 else params[-1]
                    config_store["daily_digest_state"] = _json.loads(raw) if isinstance(raw, str) else raw
                self._rows = []
            elif "FROM mw_notifications" in q:
                self._rows = [
                    (1, now_dt, "alice", "quota_warning", "warning", "Sắp hết hạn mức", "80%", {}),
                ]
            elif "UPDATE mw_notifications" in q:
                self._rows = []

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return list(self._rows)

        def close(self):
            pass

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

        def rollback(self):
            pass

    @contextmanager
    def fake_db_conn():
        yield FakeConn()

    fake_alert_cfg = {
        "smtp": {"enabled": True, "host": "smtp.example.com"},
        "admin_alerts": {"emails": ["ops@example.com"], "api_budgets": {}},
    }

    def fake_smtp_send(smtp_cfg, recipients, subject, body):
        time.sleep(0.05)
        sent_emails.append((tuple(recipients), subject))

    async def _run_two_workers():
        with patch.object(notif_mod, "_db_available", return_value=True), \
             patch.object(db_mod, "db_conn", fake_db_conn), \
             patch.object(db_mod, "get_conn", side_effect=lambda: FakeConn()), \
             patch.object(db_mod, "put_conn", side_effect=lambda c: None), \
             patch.object(alerting_mod, "load_alert_config", return_value=fake_alert_cfg), \
             patch.object(alerting_mod, "_smtp_send", side_effect=fake_smtp_send), \
             patch.object(alerting_mod, "_get_provider_spend", return_value={}), \
             patch.object(auth_mod, "load_users", return_value=[]):
            # Simultaneous trigger across Worker 1 and Worker 2
            await asyncio.gather(
                notif_mod.send_daily_digest(),
                notif_mod.send_daily_digest(),
            )
            # Staggered second trigger 1s later on Worker 2
            await notif_mod.send_daily_digest()

    asyncio.run(_run_two_workers())
    assert len(sent_emails) == 1, f"Expected exactly 1 daily digest email, got {len(sent_emails)}"


# ---------------------------------------------------------------------------
# 4. Multi-Process Safe RotatingFileHandler
# ---------------------------------------------------------------------------

def test_multiprocess_rotating_file_handler_concurrent_rollover(tmp_path):
    """Concurrent handlers writing to the same file across rollover must not raise or lose lines."""
    from utils.file_lock_handler import MultiProcessRotatingFileHandler

    log_path = tmp_path / "audit.jsonl"
    h1 = MultiProcessRotatingFileHandler(str(log_path), maxBytes=2048, backupCount=5, encoding="utf-8")
    h2 = MultiProcessRotatingFileHandler(str(log_path), maxBytes=2048, backupCount=5, encoding="utf-8")
    fmt = logging.Formatter("%(message)s")
    h1.setFormatter(fmt)
    h2.setFormatter(fmt)

    errors: list[Exception] = []

    def _writer(handler: logging.Handler, prefix: str):
        for i in range(60):
            try:
                rec = logging.LogRecord(
                    name="test", level=logging.INFO, pathname=__file__, lineno=1,
                    msg=f'{{"worker":"{prefix}","seq":{i},"pad":"{"x"*40}"}}',
                    args=(), exc_info=None,
                )
                handler.emit(rec)
            except Exception as exc:
                errors.append(exc)

    t1 = threading.Thread(target=_writer, args=(h1, "w1"))
    t2 = threading.Thread(target=_writer, args=(h2, "w2"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    h1.close()
    h2.close()

    assert not errors, f"Concurrent log rotation raised errors: {errors}"
    all_lines = []
    for candidate in [log_path, *(pathlib.Path(f"{log_path}.{i}") for i in range(1, 6))]:
        if candidate.exists():
            all_lines.extend(candidate.read_text(encoding="utf-8").splitlines())
    assert len(all_lines) == 120, f"Expected all 120 lines preserved across rotated files, got {len(all_lines)}"


# ---------------------------------------------------------------------------
# 5. Nginx Corporate NAT Rate-Limit & Keepalive + LiteLLM YAML Uniqueness
# ---------------------------------------------------------------------------

def test_nginx_conf_nat_safe_login_and_keepalive():
    """nginx.conf must scope login rate-limit to POST only (>=60r/m, 429) and enable upstream keepalive."""
    nginx_conf = (REPO_ROOT / "nginx" / "nginx.conf").read_text(encoding="utf-8")

    assert "keepalive " in nginx_conf, "nginx.conf upstreams must configure keepalive"
    assert "limit_req_status 429;" in nginx_conf, "nginx.conf should return HTTP 429 instead of 503 on rate-limit"
    assert "rate=10r/m" not in nginx_conf, "nginx.conf still has tight 10r/m login limit that blocks office NAT"
    assert "$login_limit_key" in nginx_conf, "nginx.conf should map POST-only key for login rate limiting"


def test_litellm_config_has_no_duplicate_yaml_keys():
    """litellm_config.yaml must parse with zero duplicate keys at every mapping level."""
    yaml_path = REPO_ROOT / "litellm" / "litellm_config.yaml"
    raw_text = yaml_path.read_text(encoding="utf-8")

    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise ValueError(f"Duplicate YAML key detected: {key!r}")
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping,
    )

    parsed = yaml.load(raw_text, Loader=UniqueKeyLoader)
    assert "general_settings" in parsed
    assert "logging" in parsed
    assert parsed["general_settings"]["master_key"] == "os.environ/LITELLM_KEY"
