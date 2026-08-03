#!/usr/bin/env python3
# ==============================================================================
# Script: seed_department_access.py
# Description: Seed bộ group phòng ban mẫu + phân quyền tool theo group/user cho
#              Open WebUI (OpenSpec change: department-plugin-access).
#
# Mô hình phân quyền: quyền dùng tool nằm ở bảng `access_grant` của Open WebUI,
# cấp theo GROUP (phòng ban) + override theo USER. Model KHÔNG gate tool —
# user chọn model gốc bất kỳ rồi tự bật tool trong tool picker, danh sách tool
# đã được Open WebUI lọc theo grant của họ (utils/tools.py: get_tools).
#
# Cách dùng:
#   python scripts/seed_department_access.py                # seed tất cả các phần
#   python scripts/seed_department_access.py --phase groups # chỉ seed groups
#   python scripts/seed_department_access.py --dry-run      # chỉ in thao tác dự kiến
#   python scripts/seed_department_access.py --rollback     # xóa dữ liệu đã seed
#   python scripts/seed_department_access.py --rollback --force  # xóa cả group có thành viên
#
# Xác thực: dùng OPENWEBUI_ADMIN_TOKEN nếu có, nếu không đăng nhập bằng
# TEST_ADMIN_EMAIL / TEST_ADMIN_PASSWORD (đọc từ môi trường hoặc file .env).
# Mọi thao tác đi qua Admin API — không chạm SQL trực tiếp.
# ==============================================================================

import argparse
import ast
import os
import sys

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SEED_TAG = "department-plugin-access"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")

# Đánh dấu "public cho mọi user đã đăng nhập" trong ma trận phân quyền
PUBLIC = "__public__"
# Đánh dấu "cấp cho cả 8 group phòng ban" (khác public: user chưa vào group nào sẽ không thấy)
ALL_GROUPS = "__all_groups__"

# 8 group phòng ban mẫu theo cơ cấu công ty điển hình (design.md D6)
DEPARTMENT_GROUPS = {
    "ban-lanh-dao": "Ban lãnh đạo — định hướng chiến lược, phê duyệt và giám sát toàn công ty",
    "kinh-doanh": "Phòng Kinh doanh — bán hàng, chăm sóc khách hàng, hợp đồng",
    "marketing": "Phòng Marketing — truyền thông, nội dung, thương hiệu",
    "ke-toan-tai-chinh": "Phòng Kế toán – Tài chính — sổ sách, báo cáo tài chính, ngân sách",
    "hcns": "Phòng Hành chính – Nhân sự — tuyển dụng, chế độ, văn thư",
    "ky-thuat-rd": "Phòng Kỹ thuật / R&D — phát triển sản phẩm, nghiên cứu công nghệ",
    "san-xuat": "Phòng Sản xuất — vận hành sản xuất, chất lượng, kế hoạch",
    "it": "Phòng IT — hạ tầng, hệ thống nội bộ, hỗ trợ kỹ thuật",
}


# ------------------------------------------------------------------------------
# Ma trận phân quyền mặc định (specs/department-tool-access)
#   - Tool dùng chung (fetch, sequential-thinking, export) → public mọi user
#   - postgres, playwright → chỉ `it` và `ky-thuat-rd`
#   - office365 (MCP) → mọi group phòng ban (admin có thể thu hẹp sau)
#   - Tool per-user: github → `it`, `ky-thuat-rd`; gmail/drive → mọi group
#
# Office365 KHÔNG có tool per-user: bản `office365_tool.py` đã gỡ, mảng Office365 do
# MCP server `office365` (bên mentor) phụ trách và sẽ được thay bằng bản thật sau.
# ------------------------------------------------------------------------------

# 5 mcpo server: tool server connection tại http://mcpo:8015/<name>
MCPO_URL_BASE = os.environ.get("MCPO_URL_BASE", "http://mcpo:8015")
MCPO_SERVER_MATRIX = {
    "office365": {"name": "Office 365 (MCP)", "groups": ALL_GROUPS},
    "playwright": {"name": "Playwright (MCP)", "groups": ["it", "ky-thuat-rd"]},
    "fetch": {"name": "Fetch (MCP)", "groups": PUBLIC},
    "postgres": {"name": "Postgres (MCP)", "groups": ["it", "ky-thuat-rd"]},
    "sequential-thinking": {"name": "Sequential Thinking (MCP)", "groups": PUBLIC},
}

# Workspace tool: id trong bảng `tool` của Open WebUI.
# ĐÂY LÀ TRỤC PHÂN QUYỀN DUY NHẤT cho tool: mỗi tool được cấp cho group phòng ban
# (principal_type=group), cộng override theo user ở USER_TOOL_OVERRIDES bên dưới.
# Tool không có dòng access_grants nào = private (chỉ admin thấy) — default-deny.
# Lưu ý: chức năng "Xuất file" (tool_export_all.py) là Action FUNCTION (class Action),
# không phải workspace tool — không mang access_grants; nó bật cho mọi người bằng is_global.
WORKSPACE_TOOL_MATRIX = {
    "google_gmail_tool": ALL_GROUPS,
    "code_interpreter": ["it", "ky-thuat-rd"],
    "github_tool": ["it", "ky-thuat-rd"],
    "google_drive_tool": ALL_GROUPS,
}

# Override theo USER: ngoại lệ cho cá nhân nằm ngoài chính sách group ở trên.
# Khai báo bằng email; script tự đổi sang openwebui user_id.
#
# Không bắt buộc dùng map này: admin cấp quyền cho cá nhân ngay trong Open WebUI
# (Workspace → Tools → Access Control → chọn user). seed_grants GIỮ NGUYÊN các grant
# user cấp bằng tay đó khi chạy lại — xem preserved_user_grants() — nên hai đường
# không giẫm chân nhau. Map này chỉ dành cho ngoại lệ muốn versioned trong repo.
USER_TOOL_OVERRIDES = {
    # "github_tool": ["an.nv@oppen.vn"],
}


# ------------------------------------------------------------------------------
# Phase: tools — đồng bộ source từ repo `tools/` vào Open WebUI (bảng `tool`/`function`)
#
# Open WebUI KHÔNG nạp tool từ thư mục: source Python nằm trong DB (cột `content`).
# Phase này đẩy file trong repo lên qua Admin API, nên repo là nguồn sự thật duy nhất
# — không phải copy-paste qua UI, và sửa file rồi chạy lại là tool được cập nhật.
#
# tool id = tên file (không .py) → phải khớp WORKSPACE_TOOL_MATRIX.
# ------------------------------------------------------------------------------

# class Tools → workspace tool (mang access_grants)
WORKSPACE_TOOL_FILES = {
    "google_gmail_tool": "google_gmail_tool.py",
    "code_interpreter": "code_interpreter.py",
    "github_tool": "github_tool.py",
    "google_drive_tool": "google_drive_tool.py",
}

# class Action/Filter/Pipe → function (không có access_grants; bật/tắt bằng is_active).
# `global`: chạy cho MỌI model thay vì phải gắn tay vào từng model.
# tool_export_all phải global: trước đây nó hiện ra nhờ meta.actionIds của preset trợ lý;
# preset đã bị gỡ nên không còn model nào tham chiếu → không global thì nút Xuất file biến mất.
FUNCTION_FILES = {
    "filter_approval_handler": {"file": "filter_approval_handler.py", "global": True},
    "action_approval_ui": {"file": "action_approval_ui.py", "global": False},
    "tool_export_all": {"file": "tool_export_all.py", "global": True},
    "deep_research_pipe": {"file": "deep_research_pipe.py", "global": False},
}

# Valves bơm từ .env để tool tự xác thực được với middleware (khỏi điền tay trong UI)
VALVES_FROM_ENV = {
    "SUBKEY_ADMIN": lambda: os.environ.get("SUBKEY_ADMIN"),
    "MW_BASE_URL": lambda: os.environ.get("MW_INTERNAL_URL", "http://middleware:5000/v1"),
    "MW_PUBLIC_URL": lambda: os.environ.get("MW_PUBLIC_URL", "https://localhost:3000"),
    # tên valve khác dùng trong filter_approval_handler
    "middleware_url": lambda: os.environ.get("MW_INTERNAL_URL", "http://middleware:5000/v1"),
    "admin_token": lambda: os.environ.get("SUBKEY_ADMIN"),
}


def read_tool_source(filename: str):
    """Đọc source + rút title/description từ docstring đầu file. None nếu file không có."""
    path = os.path.join(TOOLS_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        content = f.read()

    title, description = os.path.splitext(filename)[0], ""
    try:
        doc = ast.get_docstring(ast.parse(content)) or ""
    except SyntaxError:
        doc = ""
    for line in doc.splitlines():
        key, _, val = line.partition(":")
        if key.strip().lower() == "title" and val.strip():
            title = val.strip()
        elif key.strip().lower() == "description" and val.strip():
            description = val.strip()

    return {"content": content, "name": title, "description": description}


def load_env_file(path: str) -> None:
    """Nạp biến từ file .env vào os.environ (không ghi đè biến đã có)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


class OpenWebUIAdmin:
    """Client mỏng cho Admin API của Open WebUI."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.verify = False  # nginx nội bộ dùng chứng chỉ tự ký

    def login(self) -> None:
        token = os.environ.get("OPENWEBUI_ADMIN_TOKEN")
        if not token:
            email = os.environ.get("TEST_ADMIN_EMAIL")
            password = os.environ.get("TEST_ADMIN_PASSWORD")
            if not email or not password:
                sys.exit(
                    "Thiếu thông tin xác thực: đặt OPENWEBUI_ADMIN_TOKEN "
                    "hoặc TEST_ADMIN_EMAIL/TEST_ADMIN_PASSWORD (trong .env)."
                )
            res = self.session.post(
                f"{self.base_url}/api/v1/auths/signin",
                json={"email": email, "password": password},
                timeout=15,
            )
            if res.status_code != 200:
                sys.exit(f"Đăng nhập admin thất bại ({res.status_code}): {res.text[:200]}")
            token = res.json()["token"]
        self.session.headers["Authorization"] = f"Bearer {token}"

    def request(self, method: str, path: str, **kwargs):
        res = self.session.request(method, f"{self.base_url}{path}", timeout=30, **kwargs)
        if res.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {res.status_code}: {res.text[:300]}")
        return res.json() if res.text else None

    # --- Users ---
    def list_users(self) -> list:
        # /api/v1/users/ phân trang; /all trả toàn bộ để map email → id.
        res = self.request("GET", "/api/v1/users/all")
        return res.get("users", res) if isinstance(res, dict) else res

    # --- Groups ---
    def list_groups(self) -> list:
        return self.request("GET", "/api/v1/groups/")

    def create_group(self, name: str, description: str) -> dict:
        return self.request(
            "POST",
            "/api/v1/groups/create",
            json={
                "name": name,
                "description": description,
                "data": {"seeded-by": SEED_TAG},
            },
        )

    def delete_group(self, group_id: str) -> None:
        self.request("DELETE", f"/api/v1/groups/id/{group_id}/delete")

    # --- Tool server connections (mcpo) ---
    def get_tool_server_connections(self) -> list:
        return self.request("GET", "/api/v1/configs/tool_servers")["TOOL_SERVER_CONNECTIONS"]

    def set_tool_server_connections(self, connections: list) -> None:
        self.request(
            "POST",
            "/api/v1/configs/tool_servers",
            json={"TOOL_SERVER_CONNECTIONS": connections},
        )

    # --- Workspace tools ---
    def list_tools(self) -> list:
        return self.request("GET", "/api/v1/tools/list")

    def update_tool_access(self, tool_id: str, access_grants: list) -> None:
        self.request(
            "POST",
            f"/api/v1/tools/id/{tool_id}/access/update",
            json={"access_grants": access_grants},
        )

    def get_tool(self, tool_id: str) -> dict:
        return self.request("GET", f"/api/v1/tools/id/{tool_id}")

    def create_tool(self, form: dict) -> dict:
        return self.request("POST", "/api/v1/tools/create", json=form)

    def update_tool(self, tool_id: str, form: dict) -> dict:
        return self.request("POST", f"/api/v1/tools/id/{tool_id}/update", json=form)

    def delete_tool(self, tool_id: str) -> None:
        self.request("DELETE", f"/api/v1/tools/id/{tool_id}/delete")

    def get_tool_valves_spec(self, tool_id: str) -> dict:
        return self.request("GET", f"/api/v1/tools/id/{tool_id}/valves/spec") or {}

    def get_tool_valves(self, tool_id: str) -> dict:
        return self.request("GET", f"/api/v1/tools/id/{tool_id}/valves") or {}

    def update_tool_valves(self, tool_id: str, valves: dict) -> None:
        self.request("POST", f"/api/v1/tools/id/{tool_id}/valves/update", json=valves)

    # --- Functions (Action / Filter / Pipe) ---
    def list_functions(self) -> list:
        return self.request("GET", "/api/v1/functions/")

    def get_function(self, fn_id: str) -> dict:
        # danh sách không kèm `content` → phải lấy từng cái để so sánh source
        return self.request("GET", f"/api/v1/functions/id/{fn_id}") or {}

    def create_function(self, form: dict) -> dict:
        return self.request("POST", "/api/v1/functions/create", json=form)

    def update_function(self, fn_id: str, form: dict) -> dict:
        return self.request("POST", f"/api/v1/functions/id/{fn_id}/update", json=form)

    def toggle_function(self, fn_id: str) -> dict:
        return self.request("POST", f"/api/v1/functions/id/{fn_id}/toggle")

    def toggle_function_global(self, fn_id: str) -> dict:
        return self.request("POST", f"/api/v1/functions/id/{fn_id}/toggle/global")

    def get_function_valves(self, fn_id: str) -> dict:
        return self.request("GET", f"/api/v1/functions/id/{fn_id}/valves") or {}

    def get_function_valves_spec(self, fn_id: str) -> dict:
        return self.request("GET", f"/api/v1/functions/id/{fn_id}/valves/spec") or {}

    def update_function_valves(self, fn_id: str, valves: dict) -> None:
        self.request("POST", f"/api/v1/functions/id/{fn_id}/valves/update", json=valves)

    # --- Model gốc từ connection (không nằm trong bảng `model` cho tới khi được cấu hình) ---
    def get_all_models(self) -> list:
        body = self.request("GET", "/api/models")
        return body.get("data", []) if isinstance(body, dict) else (body or [])

    # --- Workspace models (preset) ---
    def list_models(self) -> list:
        # /models/list có PHÂN TRANG → dùng /export (admin, trả toàn bộ kèm access_grants),
        # nếu không sẽ tưởng model ở trang sau là chưa tồn tại rồi tạo trùng.
        # Lưu ý: /export chỉ trả preset (Models.get_models lọc base_model_id != None).
        return self.request("GET", "/api/v1/models/export") or []

    def list_base_model_configs(self) -> list:
        """Dòng cấu hình của model GỐC (base_model_id = NULL) — không có trong /export."""
        return self.request("GET", "/api/v1/models/base") or []

    def create_model(self, form: dict) -> dict:
        return self.request("POST", "/api/v1/models/create", json=form)

    def update_model(self, form: dict) -> dict:
        return self.request("POST", "/api/v1/models/model/update", json=form)

    def delete_model(self, model_id: str) -> None:
        self.request("POST", "/api/v1/models/model/delete", json={"id": model_id})


# ------------------------------------------------------------------------------
# Phase: groups
# ------------------------------------------------------------------------------

def seed_groups(api: OpenWebUIAdmin, dry_run: bool) -> None:
    existing = {g["name"]: g for g in api.list_groups()}
    created, skipped = [], []

    for name, description in DEPARTMENT_GROUPS.items():
        if name in existing:
            skipped.append(name)
            continue
        if dry_run:
            print(f"[DRY-RUN] Sẽ tạo group '{name}' — {description}")
            created.append(name)
            continue
        group = api.create_group(name, description)
        print(f"✓ Đã tạo group '{name}' (id={group['id']})")
        created.append(name)

    print(f"\nGroups: tạo mới {len(created)}, bỏ qua (đã tồn tại) {len(skipped)}")
    if created:
        print("  Tạo mới:", ", ".join(created))
    if skipped:
        print("  Bỏ qua :", ", ".join(skipped))


def rollback_groups(api: OpenWebUIAdmin, dry_run: bool, force: bool) -> None:
    seeded = [
        g for g in api.list_groups()
        if (g.get("data") or {}).get("seeded-by") == SEED_TAG
    ]
    if not seeded:
        print("Không tìm thấy group nào mang tag seeded-by để rollback.")
        return

    for group in seeded:
        member_count = group.get("member_count") or 0
        label = f"'{group['name']}' (id={group['id']}, {member_count} thành viên)"
        if member_count > 0 and not force:
            print(f"⚠ Bỏ qua group {label} — đã có thành viên. Dùng --force nếu vẫn muốn xóa.")
            continue
        if dry_run:
            print(f"[DRY-RUN] Sẽ xóa group {label}")
            continue
        api.delete_group(group["id"])
        print(f"✓ Đã xóa group {label}")


# ------------------------------------------------------------------------------
# Phase: tools — đẩy source từ repo lên Open WebUI
# ------------------------------------------------------------------------------

def sync_valves(api: OpenWebUIAdmin, kind: str, res_id: str, dry_run: bool) -> str:
    """Bơm valves từ .env (SUBKEY_ADMIN, MW_BASE_URL...) cho những valve mà tool có khai."""
    get_spec = api.get_tool_valves_spec if kind == "tool" else api.get_function_valves_spec
    get_cur = api.get_tool_valves if kind == "tool" else api.get_function_valves
    update = api.update_tool_valves if kind == "tool" else api.update_function_valves

    try:
        spec = get_spec(res_id)
    except RuntimeError:
        return ""  # tool không khai Valves
    declared = set((spec or {}).get("properties", {}))
    wanted = {
        name: fn()
        for name, fn in VALVES_FROM_ENV.items()
        if name in declared and fn()
    }
    if not wanted:
        return ""

    current = get_cur(res_id) or {}
    if all(current.get(k) == v for k, v in wanted.items()):
        return ""
    if not dry_run:
        update(res_id, {**current, **wanted})
    return f" (valves: {', '.join(sorted(wanted))})"


def seed_tools(api: OpenWebUIAdmin, dry_run: bool) -> None:
    existing_tools = {t["id"]: t for t in api.list_tools()}
    existing_fns = {f["id"]: f for f in api.list_functions()}

    # --- Workspace tools (class Tools) ---
    for tool_id, filename in WORKSPACE_TOOL_FILES.items():
        src = read_tool_source(filename)
        if not src:
            print(f"⚠ Bỏ qua '{tool_id}' — không thấy file tools/{filename}")
            continue

        form = {
            "id": tool_id,
            "name": src["name"],
            "content": src["content"],
            "meta": {"description": src["description"]},
        }

        if tool_id not in existing_tools:
            if dry_run:
                print(f"[DRY-RUN] Sẽ import tool '{tool_id}' ({src['name']}) từ tools/{filename}")
                continue
            api.create_tool(form)
            note = sync_valves(api, "tool", tool_id, dry_run)
            print(f"✓ Đã import tool '{tool_id}' ({src['name']}){note}")
            continue

        # Đã có: chỉ ghi đè khi source trong repo khác bản trong DB
        current = api.get_tool(tool_id)
        if (current.get("content") or "") == src["content"]:
            note = sync_valves(api, "tool", tool_id, dry_run)
            print(f"• Tool '{tool_id}' — source không đổi{note or ''}")
            continue
        if dry_run:
            print(f"[DRY-RUN] Sẽ cập nhật source tool '{tool_id}' (repo mới hơn bản trong DB)")
            continue
        api.update_tool(tool_id, form)
        note = sync_valves(api, "tool", tool_id, dry_run)
        print(f"✓ Đã cập nhật source tool '{tool_id}'{note}")

    # --- Functions (class Action / Filter / Pipe) ---
    for fn_id, cfg in FUNCTION_FILES.items():
        src = read_tool_source(cfg["file"])
        if not src:
            print(f"⚠ Bỏ qua function '{fn_id}' — không thấy file tools/{cfg['file']}")
            continue

        form = {
            "id": fn_id,
            "name": src["name"],
            "content": src["content"],
            "meta": {"description": src["description"]},
        }
        current = api.get_function(fn_id) if fn_id in existing_fns else None

        if current is None:
            if dry_run:
                print(f"[DRY-RUN] Sẽ import function '{fn_id}' ({src['name']})")
                continue
            api.create_function(form)
            api.toggle_function(fn_id)  # function tạo mới mặc định is_active = false
            if cfg["global"]:
                api.toggle_function_global(fn_id)
            note = sync_valves(api, "function", fn_id, dry_run)
            state = "bật, global" if cfg["global"] else "bật"
            print(f"✓ Đã import function '{fn_id}' ({src['name']}) — {state}{note}")
            continue

        changed = (current.get("content") or "") != src["content"]
        if changed and not dry_run:
            api.update_function(fn_id, form)
        elif changed and dry_run:
            print(f"[DRY-RUN] Sẽ cập nhật source function '{fn_id}'")
            continue

        # Bảo đảm trạng thái bật/global đúng dù admin có lỡ tắt
        actions = []
        if not current.get("is_active") and not dry_run:
            api.toggle_function(fn_id)
            actions.append("bật lại")
        if cfg["global"] and not current.get("is_global") and not dry_run:
            api.toggle_function_global(fn_id)
            actions.append("đặt global")
        note = sync_valves(api, "function", fn_id, dry_run)
        label = "cập nhật source" if changed else "source không đổi"
        extra = f", {', '.join(actions)}" if actions else ""
        print(f"{'✓' if changed or actions else '•'} Function '{fn_id}' — {label}{extra}{note}")


def rollback_tools(api: OpenWebUIAdmin, dry_run: bool) -> None:
    existing = {t["id"] for t in api.list_tools()}
    for tool_id in WORKSPACE_TOOL_FILES:
        if tool_id not in existing:
            continue
        if dry_run:
            print(f"[DRY-RUN] Sẽ xóa tool '{tool_id}' khỏi workspace")
        else:
            api.delete_tool(tool_id)
            print(f"✓ Đã xóa tool '{tool_id}'")
    print("(function không bị xóa — chúng là hạ tầng chung, không thuộc phạm vi seed)")


# ------------------------------------------------------------------------------
# Phase: models — mở model AI gốc cho user thường
#
# Open WebUI 0.9.6 (utils/models.py: get_filtered_models): model KHÔNG có dòng trong
# bảng `model` thì "chỉ admin thấy". Model gốc đến từ connection (middleware) nên
# không có dòng nào → user thường mất sạch model, không còn gì để chat.
# Phase này tạo dòng cấu hình cho từng model gốc kèm access_grants để user thấy.
#
# Model KHÔNG gate tool: user chọn model gốc rồi tự bật tool trong tool picker,
# danh sách tool đã được lọc theo access_grants của group/user họ.
# ------------------------------------------------------------------------------

# Model cho user chat: 5 auto (smart-routing) + các chat-*. Loại img-*/embedding/rerank
# vì chúng không dùng để chat.
def is_chat_base_model(model_id: str) -> bool:
    return model_id.endswith("-auto") or model_id.startswith("chat-")


BASE_MODEL_GROUPS = PUBLIC  # mọi user đã đăng nhập đều chọn được model AI gốc


def seed_base_models(api: OpenWebUIAdmin, dry_run: bool) -> None:
    group_ids = get_group_id_map(api)
    grants = build_grants(BASE_MODEL_GROUPS, group_ids)

    configured = {m["id"]: m for m in api.list_base_model_configs()}
    base_models = [
        m for m in api.get_all_models()
        if is_chat_base_model(m.get("id", "")) and not m.get("base_model_id")
    ]
    if not base_models:
        print("⚠ Không thấy model gốc nào từ connection — kiểm tra middleware/LiteLLM còn sống không.")
        return

    created = updated = unchanged = 0
    for model in base_models:
        mid = model["id"]
        cur = configured.get(mid)

        if cur is None:
            if not dry_run:
                api.create_model({
                    "id": mid,
                    "base_model_id": None,  # dòng cấu hình cho model gốc, KHÔNG phải preset
                    "name": model.get("name") or mid,
                    "meta": {"description": None, "seeded-by": SEED_TAG},
                    "params": {},
                    "access_grants": grants,
                    "is_active": True,
                })
            created += 1
            continue

        cur_grants = [
            {k: g.get(k) for k in ("principal_type", "principal_id", "permission")}
            for g in cur.get("access_grants") or []
        ]
        if grants_equal(cur_grants, grants):
            unchanged += 1
            continue
        if not dry_run:
            api.update_model({
                "id": mid,
                "base_model_id": cur.get("base_model_id"),
                "name": cur.get("name") or mid,
                "meta": cur.get("meta") or {},
                "params": cur.get("params") or {},
                "access_grants": grants,
                "is_active": cur.get("is_active", True),
            })
        updated += 1

    prefix = "[DRY-RUN] " if dry_run else ""
    print(
        f"{prefix}Model gốc ({grants_label(BASE_MODEL_GROUPS)}): "
        f"mở mới {created}, cập nhật quyền {updated}, không đổi {unchanged}"
    )
    print(f"  Danh sách: {', '.join(sorted(m['id'] for m in base_models))}")


def rollback_base_models(api: OpenWebUIAdmin, dry_run: bool) -> None:
    seeded = [
        m for m in api.list_models()
        if (m.get("meta") or {}).get("seeded-by") == SEED_TAG and not m.get("base_model_id")
    ]
    for model in seeded:
        if dry_run:
            print(f"[DRY-RUN] Sẽ gỡ cấu hình model gốc '{model['id']}' (về admin-only)")
        else:
            api.delete_model(model["id"])
            print(f"✓ Đã gỡ cấu hình model gốc '{model['id']}'")
    if not seeded:
        print("Không có model gốc nào do script cấu hình.")


# ------------------------------------------------------------------------------
# Phase: grants — access_grants cho tool server connections (mcpo) + workspace tools
# ------------------------------------------------------------------------------

def build_grants(spec, group_ids: dict, user_ids=()) -> list:
    """Chuyển spec trong ma trận (PUBLIC / ALL_GROUPS / [slug...]) thành access_grants.

    user_ids: openwebui user_id được cấp thêm theo cá nhân (override ngoài group).
    """
    if spec == PUBLIC:
        grants = [{"principal_type": "user", "principal_id": "*", "permission": "read"}]
    else:
        slugs = list(DEPARTMENT_GROUPS) if spec == ALL_GROUPS else spec
        grants = [
            {"principal_type": "group", "principal_id": group_ids[slug], "permission": "read"}
            for slug in slugs
        ]
    grants += [
        {"principal_type": "user", "principal_id": uid, "permission": "read"}
        for uid in user_ids
    ]
    return dedupe_grants(grants)


def dedupe_grants(grants: list) -> list:
    seen, out = set(), []
    for g in grants:
        key = (g.get("principal_type"), g.get("principal_id"), g.get("permission"))
        if key not in seen:
            seen.add(key)
            out.append(g)
    return out


def preserved_user_grants(current: list) -> list:
    """Grant theo user do admin cấp tay trong Open WebUI — phải giữ lại khi seed lại.

    update_tool_access gọi set_access_grants: XÓA SẠCH rồi ghi lại. Không giữ các grant
    này thì mỗi lần chạy --phase grants sẽ âm thầm thu hồi mọi ngoại lệ admin đã cấp
    trong UI. Wildcard "*" không tính: nó do ma trận (PUBLIC) quản.
    """
    return [
        g for g in current or []
        if g.get("principal_type") == "user" and g.get("principal_id") != "*"
    ]


def grants_label(spec, n_users: int = 0) -> str:
    if spec == PUBLIC:
        base = "public (mọi user)"
    elif spec == ALL_GROUPS:
        base = "mọi group phòng ban"
    else:
        base = ", ".join(spec)
    return f"{base} + {n_users} user" if n_users else base


def grants_equal(a: list, b: list) -> bool:
    key = lambda g: (g.get("principal_type"), g.get("principal_id"), g.get("permission"))
    return sorted(map(key, a or [])) == sorted(map(key, b or []))


def get_user_id_map(api: OpenWebUIAdmin) -> dict:
    """email (lower) → openwebui user_id. Chỉ gọi API khi có override cần dịch."""
    if not any(USER_TOOL_OVERRIDES.values()):
        return {}
    return {
        (u.get("email") or "").lower(): u["id"]
        for u in api.list_users()
        if u.get("email")
    }


def resolve_override_user_ids(tool_id: str, user_id_map: dict) -> list:
    ids = []
    for email in USER_TOOL_OVERRIDES.get(tool_id, []):
        uid = user_id_map.get(email.lower())
        if uid is None:
            print(f"⚠ USER_TOOL_OVERRIDES[{tool_id}]: không tìm thấy user '{email}' — bỏ qua")
            continue
        ids.append(uid)
    return ids


def get_group_id_map(api: OpenWebUIAdmin) -> dict:
    group_ids = {g["name"]: g["id"] for g in api.list_groups()}
    missing = [slug for slug in DEPARTMENT_GROUPS if slug not in group_ids]
    if missing:
        sys.exit(
            f"Thiếu group phòng ban: {', '.join(missing)}. "
            "Chạy phase groups trước (python scripts/seed_department_access.py --phase groups)."
        )
    return group_ids


def seed_grants(api: OpenWebUIAdmin, dry_run: bool) -> None:
    group_ids = get_group_id_map(api)
    user_id_map = get_user_id_map(api)
    table_rows = []  # (loại, tên, quyền, trạng thái)

    # --- 1. Tool server connections (mcpo) ---
    connections = api.get_tool_server_connections()
    conn_by_id = {(c.get("info") or {}).get("id"): c for c in connections}
    changed = False

    for server, cfg in MCPO_SERVER_MATRIX.items():
        grants = build_grants(cfg["groups"], group_ids)
        conn = conn_by_id.get(server)
        if conn is None:
            conn = {
                "url": f"{MCPO_URL_BASE}/{server}",
                "path": "openapi.json",
                "type": "openapi",
                "auth_type": "none",
                "key": "",
                "headers": None,
                "info": {
                    "id": server,
                    "name": cfg["name"],
                    "description": f"Kết nối mcpo '{server}' (seeded-by: {SEED_TAG})",
                },
                "config": {"enable": True, "seeded-by": SEED_TAG, "access_grants": grants},
            }
            connections.append(conn)
            changed = True
            status = "tạo connection mới"
        else:
            conn.setdefault("config", {})
            if grants_equal(conn["config"].get("access_grants"), grants):
                status = "không đổi"
            else:
                conn["config"]["access_grants"] = grants
                changed = True
                status = "cập nhật grants"
        table_rows.append(("mcpo", server, grants_label(cfg["groups"]), status))

    if changed and not dry_run:
        api.set_tool_server_connections(connections)

    # --- 2. Workspace tools ---
    existing_tools = {t["id"]: t for t in api.list_tools()}

    for tool_id, spec in WORKSPACE_TOOL_MATRIX.items():
        tool = existing_tools.pop(tool_id, None)
        if tool is None:
            table_rows.append(("tool", tool_id, grants_label(spec), "⚠ CHƯA CÓ trong workspace — bỏ qua"))
            continue
        current = [
            {k: g.get(k) for k in ("principal_type", "principal_id", "permission")}
            for g in tool.get("access_grants") or []
        ]
        # Quyền cuối = group (ma trận) + override khai báo trong repo + override admin
        # đã cấp tay trong UI (giữ lại, nếu không set_access_grants sẽ xóa mất).
        override_ids = resolve_override_user_ids(tool_id, user_id_map)
        kept = preserved_user_grants(current)
        grants = dedupe_grants(
            build_grants(spec, group_ids, override_ids) + kept
        )
        n_users = sum(1 for g in grants if g["principal_type"] == "user" and g["principal_id"] != "*")
        if grants_equal(current, grants):
            status = "không đổi"
        else:
            if not dry_run:
                api.update_tool_access(tool_id, grants)
            status = "cập nhật grants"
        table_rows.append(("tool", tool_id, grants_label(spec, n_users), status))

    # Tool ngoài ma trận: giữ nguyên nhưng cảnh báo để admin rà soát
    for tool_id in existing_tools:
        table_rows.append(("tool", tool_id, "(ngoài ma trận)", "⚠ không thay đổi — admin tự rà soát"))

    # --- 3. Bảng đối chiếu tool → groups ---
    prefix = "[DRY-RUN] " if dry_run else ""
    print(f"\n{prefix}Bảng đối chiếu phân quyền (tool → groups):")
    w1 = max(len(r[1]) for r in table_rows) + 2
    w2 = max(len(r[2]) for r in table_rows) + 2
    print(f"  {'LOẠI':<6} {'TOOL':<{w1}} {'QUYỀN (read)':<{w2}} TRẠNG THÁI")
    for kind, name, perm, status in table_rows:
        print(f"  {kind:<6} {name:<{w1}} {perm:<{w2}} {status}")


def rollback_grants(api: OpenWebUIAdmin, dry_run: bool) -> None:
    # Gỡ các tool server connection do script tạo (tag seeded-by trong config)
    connections = api.get_tool_server_connections()
    keep, removed = [], []
    for conn in connections:
        if (conn.get("config") or {}).get("seeded-by") == SEED_TAG:
            removed.append((conn.get("info") or {}).get("id") or conn.get("url"))
        else:
            keep.append(conn)
    if removed:
        if dry_run:
            print(f"[DRY-RUN] Sẽ gỡ tool server connections: {', '.join(removed)}")
        else:
            api.set_tool_server_connections(keep)
            print(f"✓ Đã gỡ tool server connections: {', '.join(removed)}")
    else:
        print("Không có tool server connection nào do script tạo.")

    # Đưa workspace tool trong ma trận về private (access_grants rỗng)
    existing_tools = {t["id"] for t in api.list_tools()}
    for tool_id in WORKSPACE_TOOL_MATRIX:
        if tool_id not in existing_tools:
            continue
        if dry_run:
            print(f"[DRY-RUN] Sẽ đưa tool '{tool_id}' về private (xóa access_grants)")
        else:
            api.update_tool_access(tool_id, [])
            print(f"✓ Đã đưa tool '{tool_id}' về private")


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------

PHASES = ["groups", "tools", "models", "grants"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed group phòng ban + phân quyền tool cho Open WebUI"
    )
    parser.add_argument(
        "--phase",
        choices=PHASES + ["all"],
        default="all",
        help="Chỉ chạy một phần (mặc định: all)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in thao tác dự kiến, không ghi thay đổi")
    parser.add_argument("--rollback", action="store_true", help="Xóa dữ liệu đã seed (theo tag seeded-by)")
    parser.add_argument("--force", action="store_true", help="Kèm --rollback: xóa cả group đã có thành viên")
    parser.add_argument(
        "--url",
        default=os.environ.get("OPENWEBUI_URL", "https://localhost:3000"),
        help="Base URL của Open WebUI (mặc định: https://localhost:3000)",
    )
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_env_file(os.path.join(repo_root, ".env"))

    api = OpenWebUIAdmin(args.url)
    api.login()

    phases = PHASES if args.phase == "all" else [args.phase]

    if args.rollback:
        # Rollback theo thứ tự ngược để tránh phụ thuộc (grant → model → tool → group)
        if "grants" in phases:
            rollback_grants(api, args.dry_run)
        if "models" in phases:
            rollback_base_models(api, args.dry_run)
        if "tools" in phases:
            rollback_tools(api, args.dry_run)
        if "groups" in phases:
            rollback_groups(api, args.dry_run, args.force)
        return

    if "groups" in phases:
        print("=== Phase: groups ===")
        seed_groups(api, args.dry_run)
    if "tools" in phases:
        print("\n=== Phase: tools (đẩy source từ repo lên Open WebUI) ===")
        seed_tools(api, args.dry_run)
    if "models" in phases:
        print("\n=== Phase: models (mở model AI gốc cho user) ===")
        seed_base_models(api, args.dry_run)
    if "grants" in phases:
        print("\n=== Phase: grants ===")
        seed_grants(api, args.dry_run)


if __name__ == "__main__":
    main()
