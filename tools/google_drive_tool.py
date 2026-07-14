"""
title: Google Drive Tool
author: Antigravity
version: 1.0.0
requirements: requests
"""

import os
import re

import requests
from pydantic import BaseModel, Field

API = "https://www.googleapis.com/drive/v3"
PROVIDER = "google_drive"

# ID hợp lệ của Drive: chỉ gồm chữ, số, gạch ngang, gạch dưới
FILE_ID_RE = re.compile(r"[a-zA-Z0-9_-]{20,}")
# Model hay dán nguyên link thay vì id — bóc id ra từ /d/<id> hoặc /folders/<id>
FILE_ID_IN_URL_RE = re.compile(r"/(?:d|folders)/([a-zA-Z0-9_-]{20,})")

# Link kết nối đã được emit thẳng vào khung chat, nên model chỉ cần nhắc người dùng bấm.
# Cấm model tự dựng lại URL: nó sẽ bịa ra link sai.
NEED_CONNECT_FOR_MODEL = (
    "Tài khoản Google Drive của người dùng chưa được liên kết. Liên kết kết nối ĐÃ được hiển "
    "thị sẵn ngay trong khung chat phía trên. Hãy trả lời thật ngắn gọn rằng người dùng cần "
    "bấm vào liên kết phía trên để kết nối rồi thử lại. TUYỆT ĐỐI không tự tạo lại URL."
)

# Google Docs/Sheets/Slides không tải thô được — phải export sang định dạng văn bản
EXPORT_AS = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


class Tools:
    class Valves(BaseModel):
        MW_BASE_URL: str = Field(
            default="http://middleware:5000/v1",
            description="Base URL of the Middleware API (internal container address)"
        )
        SUBKEY_ADMIN: str = Field(
            default="YOUR_SUBKEY_ADMIN",
            description="Admin key for authenticating with the Middleware API"
        )
        MW_PUBLIC_URL: str = Field(
            default="https://localhost:3000",
            description="Public face URL of the application for oauth redirection"
        )

    def __init__(self):
        self.valves = self.Valves()
        if os.getenv("SUBKEY_ADMIN"):
            self.valves.SUBKEY_ADMIN = os.getenv("SUBKEY_ADMIN")
        if os.getenv("MW_PUBLIC_URL"):
            self.valves.MW_PUBLIC_URL = os.getenv("MW_PUBLIC_URL")

    # --------------------------------------------------------------------------
    # Helpers dùng chung
    # --------------------------------------------------------------------------

    def _connect_hint(self) -> str:
        # Không truyền openwebui_user_id: middleware lấy danh tính từ phiên đăng nhập Open WebUI
        # của trình duyệt khi bấm link (chống CSRF token-binding).
        connect_url = (
            f"{self.valves.MW_PUBLIC_URL.rstrip('/')}/v1/_mw/oauth/connect"
            f"?provider={PROVIDER}"
        )
        return (
            "⚠️ Tài khoản Google Drive của bạn chưa được liên kết.\n\n"
            "Vui lòng click vào liên kết dưới đây để kết nối:\n"
            f"👉 [**Kết nối Google Drive của bạn**]({connect_url})\n\n"
            "Sau khi hoàn tất kết nối, hãy thử lại yêu cầu.\n\n"
        )

    async def _emit(self, emitter, content: str) -> None:
        # Giá trị tool trả về chỉ hiện trong panel "nguồn chi tiết"; muốn link bấm được
        # ngay trong câu trả lời thì phải emit thẳng vào body của message.
        if emitter:
            await emitter({"type": "message", "data": {"content": content}})

    def _get_token(self, __user__: dict):
        """Trả về (access_token, thong_bao_loi, can_ket_noi)."""
        if not __user__ or not __user__.get("id"):
            return None, "Lỗi: Không tìm thấy thông tin định danh người dùng OpenWebUI.", False

        user_id = __user__["id"]
        url = f"{self.valves.MW_BASE_URL.rstrip('/')}/_mw/integrations/get_token"
        try:
            res = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.valves.SUBKEY_ADMIN}"},
                params={"provider": PROVIDER, "openwebui_user_id": user_id},
                timeout=10,
            )
        except Exception as e:
            return None, f"Lỗi khi kết nối tới Middleware: {e}", False

        if res.status_code == 404:
            return None, self._connect_hint(), True
        if res.status_code != 200:
            return None, f"Lỗi từ Middleware API ({res.status_code}): {res.text}", False

        token = res.json().get("access_token")
        if not token:
            return None, "Lỗi: Không nhận được access token từ Middleware.", False
        return token, None, False

    async def _require_token(self, __user__: dict, emitter):
        """Lấy token; nếu chưa liên kết thì đẩy link kết nối thẳng vào khung chat.

        Trả về (token, thong_bao_tra_ve_cho_model).
        """
        token, err, need_connect = self._get_token(__user__)
        if err and need_connect:
            await self._emit(emitter, err)
            return None, NEED_CONNECT_FOR_MODEL
        return token, err

    def _api(self, path: str, token: str, params: dict = None, raw: bool = False):
        """Gọi Google Drive API bằng token của user. Trả về (kết quả, thong_bao_loi)."""
        try:
            res = requests.get(
                f"{API}{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=20,
            )
        except Exception as e:
            return None, f"Lỗi khi gọi Google Drive API: {e}"

        if res.status_code == 401:
            return None, (
                "❌ Phiên kết nối Google Drive đã hết hạn. Vui lòng kết nối lại tài khoản "
                "rồi thử lại."
            )
        if res.status_code == 404:
            return None, "❌ Không tìm thấy file, hoặc bạn không có quyền xem file này."
        if res.status_code >= 400:
            return None, f"❌ Google Drive API trả lỗi {res.status_code}: {res.text[:300]}"

        if raw:
            # Google trả "text/plain" không kèm charset, nên requests đoán ISO-8859-1 và
            # băm nát tiếng Việt. Export của Drive luôn là UTF-8 (kèm BOM) -> decode tường minh.
            return res.content.decode("utf-8-sig", errors="replace"), None
        return res.json(), None

    # --------------------------------------------------------------------------
    # Tool functions
    # --------------------------------------------------------------------------

    async def search_drive_files(
        self, query: str, limit: int = 10, __user__: dict = None, __event_emitter__=None
    ) -> str:
        """
        Tìm file trong Google Drive của người dùng theo tên hoặc nội dung (chỉ đọc).
        Trả về kèm file_id để dùng tiếp với công cụ đọc nội dung file.

        :param query: Từ khóa tìm kiếm (tên file hoặc nội dung bên trong file).
        :param limit: Số kết quả tối đa (mặc định 10, tối đa 30).
        :param __user__: Thông tin người dùng hiện tại từ OpenWebUI (được tự động tiêm vào).
        :return: Danh sách file kèm file_id, loại file, thời điểm sửa đổi và link mở file.
        """
        token, err = await self._require_token(__user__, __event_emitter__)
        if err:
            return err

        limit = max(1, min(int(limit or 10), 30))
        escaped = (query or "").replace("'", "\\'")
        data, err = self._api(
            "/files",
            token,
            {
                "q": f"(name contains '{escaped}' or fullText contains '{escaped}') and trashed = false",
                "pageSize": limit,
                "orderBy": "modifiedTime desc",
                "fields": "files(id,name,mimeType,modifiedTime,webViewLink,size)",
            },
        )
        if err:
            return err

        files = data.get("files", [])
        if not files:
            return f"Không tìm thấy file nào khớp với '{query}' trong Google Drive của bạn."

        lines = [f"📁 {len(files)} file khớp với '{query}':"]
        for f in files:
            kind = (f.get("mimeType") or "").replace("application/vnd.google-apps.", "Google ")
            lines.append(
                f"\n**{f.get('name')}** ({kind})\n"
                f"file_id: `{f.get('id')}` | Sửa đổi: {(f.get('modifiedTime') or '')[:10]}\n"
                f"Link: {f.get('webViewLink')}"
            )
        return "\n".join(lines)

    async def read_drive_file(
        self, file_id: str, __user__: dict = None, __event_emitter__=None
    ) -> str:
        """
        Đọc nội dung văn bản của một file trong Google Drive (chỉ đọc).
        Google Docs/Sheets/Slides sẽ được tự động chuyển sang văn bản; file nhị phân
        (ảnh, PDF quét, zip...) không đọc trực tiếp được và chỉ trả về link.

        :param file_id: ID của file, lấy từ công cụ tìm file Google Drive.
        :param __user__: Thông tin người dùng hiện tại từ OpenWebUI (được tự động tiêm vào).
        :return: Nội dung file dạng văn bản, hoặc link mở file nếu định dạng không đọc được.
        """
        token, err = await self._require_token(__user__, __event_emitter__)
        if err:
            return err

        # file_id rỗng sẽ biến /files/{id} thành endpoint files.list, khiến Google trả
        # 400 "Invalid field selection id" — chặn từ đây và nói rõ cho model biết.
        file_id = (file_id or "").strip().strip("`").strip()
        in_url = FILE_ID_IN_URL_RE.search(file_id)
        if in_url:
            file_id = in_url.group(1)
        if not FILE_ID_RE.fullmatch(file_id):
            return (
                "⚠️ Thiếu hoặc sai `file_id`. Hãy dùng công cụ tìm file Google Drive trước "
                "để lấy `file_id`, rồi truyền đúng chuỗi id đó (không phải tên file hay link)."
            )

        info, err = self._api(
            f"/files/{file_id}", token, {"fields": "id,name,mimeType,webViewLink,size"}
        )
        if err:
            return err

        name = info.get("name")
        mime = info.get("mimeType") or ""

        if mime in EXPORT_AS:
            text, err = self._api(
                f"/files/{file_id}/export", token, {"mimeType": EXPORT_AS[mime]}, raw=True
            )
        elif mime.startswith("text/") or mime in ("application/json", "application/xml"):
            text, err = self._api(f"/files/{file_id}", token, {"alt": "media"}, raw=True)
        else:
            return (
                f"File **{name}** có định dạng `{mime}`, không đọc trực tiếp dưới dạng "
                f"văn bản được.\nBạn có thể mở file tại: {info.get('webViewLink')}"
            )

        if err:
            return err

        truncated = len(text) > 8000
        return (
            f"📄 Nội dung file **{name}**"
            f"{' (đã cắt bớt, hiển thị 8000 ký tự đầu)' if truncated else ''}:\n\n"
            f"{text[:8000]}"
        )
