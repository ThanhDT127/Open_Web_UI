"""
TDD suite for:
1. Lossless & idempotent CP437 -> UTF-8 Mojibake repair (strings + nested JSON).
2. Model metadata enrichment (capabilities, toolIds, defaultFeatureIds) for seeded models.
3. LiteLLM config routing for chat-gemini-2.5-flash and active GPT/Gemini models.
4. Dockerfile.openwebui v0.13.3 base image check.
"""

from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.mark.parametrize(
    ("corrupted", "expected"),
    [
        ("Connect Gmail Account ≡ƒôº", "Connect Gmail Account 📧"),
        ("Hß╗ù trß╗ú Gß╗¡i Email ≡ƒôº", "Hỗ trợ Gửi Email 📧"),
        ("Trß╗ú l├╜ ß║úo Hß╗úp ─Éß╗ông", "Trợ lý ảo Hợp Đồng"),
        ("Γ¢╜ Gi├í x─âng s├íng nay", "⛽ Giá xăng sáng nay"),
        ("≡ƒÉÖ GitHub Access and ...", "🐙 GitHub Access and ..."),
        ("≡ƒô░ VNExpress Website ...", "📰 VNExpress Website ..."),
        ("≡ƒÆ░ Today's Gold Prices", "💰 Today's Gold Prices"),
        ("Hello & Help ≡ƒÆ¼", "Hello & Help 💬"),
    ],
)
def test_cp437_mojibake_repair_and_idempotency(corrupted: str, expected: str):
    from scripts.db_maintenance.fix_cp437_mojibake_and_models import repair_cp437_mojibake

    repaired, changed = repair_cp437_mojibake(corrupted)
    assert changed is True
    assert repaired == expected

    # Second pass on already-clean Vietnamese + Emoji text must be a no-op
    repaired_again, changed_again = repair_cp437_mojibake(repaired)
    assert changed_again is False
    assert repaired_again == expected


def test_cp437_mojibake_json_recursive_repair():
    from scripts.db_maintenance.fix_cp437_mojibake_and_models import repair_json_value

    payload = {
        "title": "Hß╗ù trß╗ú Gß╗¡i Email ≡ƒôº",
        "messages": [
            {"role": "user", "content": "Cho t├┤i xem Gi├í x─âng s├íng nay Γ¢╜"},
            {"role": "assistant", "content": "Chuỗi tiếng Việt chuẩn không bị lỗi"},
        ],
    }
    fixed, changed = repair_json_value(payload)
    assert changed is True
    assert fixed["title"] == "Hỗ trợ Gửi Email 📧"
    assert fixed["messages"][0]["content"] == "Cho tôi xem Giá xăng sáng nay ⛽"
    assert fixed["messages"][1]["content"] == "Chuỗi tiếng Việt chuẩn không bị lỗi"

    fixed2, changed2 = repair_json_value(fixed)
    assert changed2 is False
    assert fixed2 == fixed


def test_build_enriched_model_meta_populates_capabilities_and_tools():
    from scripts.db_maintenance.fix_cp437_mojibake_and_models import build_enriched_model_meta

    sparse_meta = {
        "profile_image_url": None,
        "description": None,
        "capabilities": None,
        "knowledge": None,
        "seeded-by": "department-plugin-access",
    }
    tool_ids = ["google_gmail_tool", "code_interpreter", "server:0", "server:1"]
    enriched, changed = build_enriched_model_meta("chat-gpt-5.4", sparse_meta, tool_ids)
    assert changed is True
    assert enriched["profile_image_url"] == "/static/favicon.png"
    assert enriched["capabilities"]["vision"] is True
    assert enriched["capabilities"]["web_search"] is True
    assert enriched["capabilities"]["file_upload"] is True
    assert enriched["capabilities"]["code_interpreter"] is True
    assert enriched["defaultFeatureIds"] == ["web_search"]
    assert set(tool_ids).issubset(set(enriched["toolIds"]))


def test_litellm_config_routes_gemini_25_flash_via_api_key_and_includes_gpt_models():
    cfg_path = REPO_ROOT / "litellm" / "litellm_config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    by_name = {m["model_name"]: m["litellm_params"] for m in cfg.get("model_list", [])}

    assert "chat-gemini-2.5-flash" in by_name
    g25 = by_name["chat-gemini-2.5-flash"]
    assert g25["model"] == "gemini/gemini-2.5-flash"
    assert g25["api_key"] == "os.environ/GEMINI_API_KEY"

    for expected_gpt in (
        "chat-gpt-5.4",
        "chat-gpt-5.2",
        "chat-gpt-5",
        "chat-gpt-5-mini",
        "chat-gpt-4.1",
        "chat-gpt-4.1-mini",
        "chat-gpt-4o",
        "chat-gpt-4o-mini",
    ):
        assert expected_gpt in by_name, f"Missing {expected_gpt} in litellm_config.yaml"


def test_dockerfile_openwebui_uses_v0133():
    dockerfile = (REPO_ROOT / "Dockerfile.openwebui").read_text(encoding="utf-8")
    first_from = next(line.strip() for line in dockerfile.splitlines() if line.strip().startswith("FROM "))
    assert first_from == "FROM ghcr.io/open-webui/open-webui:v0.13.3"


def test_docker_compose_openwebui_configures_redis_url_for_multiworker_tether():
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    env_list = compose["services"]["open-webui"]["environment"]
    env_map = {}
    for entry in env_list:
        if isinstance(entry, str) and "=" in entry:
            k, v = entry.split("=", 1)
            env_map[k] = v
    assert int(env_map.get("UVICORN_WORKERS", "1")) > 1
    assert env_map.get("WEBSOCKET_REDIS_URL") == "redis://redis:6379/1"
    assert env_map.get("REDIS_URL") == "redis://redis:6379/1"


def test_dashboard_served_on_port_5000_and_redirected_from_3000():
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    nginx_ports = compose["services"]["nginx"]["ports"]
    assert "3000:3000" in nginx_ports
    assert "5000:5000" in nginx_ports

    nginx_conf = (REPO_ROOT / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    assert "listen 5000 ssl;" in nginx_conf
    assert "return 302 https://$host:5000$request_uri;" in nginx_conf
