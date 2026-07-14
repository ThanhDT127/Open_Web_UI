"""
title: GitHub Tool
author: Antigravity
version: 1.0.0
requirements: requests
"""

import base64
import os

import requests
from pydantic import BaseModel, Field

API = "https://api.github.com"
PROVIDER = "github"

# Link kết nối được emit thẳng vào khung chat, nên model chỉ cần nhắc người dùng bấm.
NEED_CONNECT_FOR_MODEL = (
    "Tài khoản GitHub của người dùng chưa được liên kết. Liên kết kết nối ĐÃ được hiển thị "
    "sẵn ngay trong khung chat phía trên. Hãy trả lời thật ngắn gọn rằng người dùng cần bấm "
    "vào liên kết phía trên để kết nối rồi thử lại. TUYỆT ĐỐI không tự tạo lại URL."
)


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
            "⚠️ Tài khoản GitHub của bạn chưa được liên kết.\n\n"
            "Vui lòng click vào liên kết dưới đây để kết nối:\n"
            f"👉 [**Kết nối tài khoản GitHub của bạn**]({connect_url})\n\n"
            "Sau khi hoàn tất kết nối, hãy thử lại yêu cầu."
        )

    async def _emit(self, emitter, content: str) -> None:
        # Giá trị tool trả về chỉ hiện trong panel "nguồn chi tiết"; muốn link bấm được ngay
        # trong câu trả lời thì phải emit thẳng vào body của message.
        if emitter:
            await emitter({"type": "message", "data": {"content": content}})

    async def _require_token(self, __user__: dict, emitter):
        """Lấy token; chưa liên kết thì đẩy link kết nối thẳng vào khung chat."""
        token, err, need_connect = self._get_token(__user__)
        if err and need_connect:
            await self._emit(emitter, err)
            return None, NEED_CONNECT_FOR_MODEL
        return token, err

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

    def _api(self, path: str, token: str, params: dict = None, accept: str = None):
        """
        Gọi GitHub REST API bằng token của user. Trả về (kết quả, thong_bao_loi).
        `accept` khác mặc định (ví dụ .diff) → trả về text thô thay vì JSON.
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": accept or "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            res = requests.get(f"{API}{path}", headers=headers, params=params, timeout=20)
        except Exception as e:
            return None, f"Lỗi khi gọi GitHub API: {e}"

        if res.status_code == 401:
            return None, (
                "❌ Phiên kết nối GitHub đã hết hạn. Vui lòng kết nối lại tài khoản rồi thử lại."
            )
        if res.status_code == 404:
            return None, (
                "❌ Không tìm thấy (repo/issue/file không tồn tại, hoặc tài khoản GitHub của bạn "
                "không có quyền truy cập)."
            )
        if res.status_code >= 400:
            return None, f"❌ GitHub API trả lỗi {res.status_code}: {res.text[:300]}"

        return (res.text if accept else res.json()), None

    # --------------------------------------------------------------------------
    # Tool functions
    # --------------------------------------------------------------------------

    async def list_my_repos(self, limit: int = 10, __user__: dict = None, __event_emitter__=None) -> str:
        """
        Liệt kê các repository GitHub mà người dùng có quyền truy cập (chỉ thấy repo của chính họ).

        :param limit: Số repo cần lấy (mặc định 10, tối đa 50).
        :param __user__: Thông tin người dùng hiện tại từ OpenWebUI (được tự động tiêm vào).
        :return: Danh sách repo kèm mô tả, ngôn ngữ chính và thời điểm cập nhật.
        """
        token, err = await self._require_token(__user__, __event_emitter__)
        if err:
            return err

        limit = max(1, min(int(limit or 10), 50))
        data, err = self._api(
            "/user/repos", token, {"per_page": limit, "sort": "updated", "affiliation": "owner,collaborator,organization_member"}
        )
        if err:
            return err
        if not data:
            return "Tài khoản GitHub của bạn chưa có repository nào."

        lines = [f"📦 {len(data)} repository gần đây nhất:"]
        for r in data:
            lines.append(
                f"\n**{r.get('full_name')}**{' 🔒' if r.get('private') else ''}\n"
                f"{r.get('description') or '(không có mô tả)'}\n"
                f"Ngôn ngữ: {r.get('language') or '—'} | Cập nhật: {(r.get('updated_at') or '')[:10]}"
            )
        return "\n".join(lines)

    async def list_issues(
        self,
        repo: str = "",
        state: str = "open",
        assigned_to_me: bool = False,
        limit: int = 10,
        __user__: dict = None, __event_emitter__=None,
    ) -> str:
        """
        Liệt kê issue và pull request. Dùng được theo hai cách:
        - Nêu tên repo: liệt kê issue/PR của repo đó.
        - Bỏ trống repo và đặt assigned_to_me = true: liệt kê những việc đang được giao
          cho chính người dùng trên TẤT CẢ repo (dùng cho câu hỏi kiểu "tôi đang có việc gì").

        :param repo: Tên repo đầy đủ dạng chu-so-huu/ten-repo; để trống nếu muốn xem việc được giao trên mọi repo.
        :param state: Trạng thái cần lọc: open, closed hoặc all (mặc định open).
        :param assigned_to_me: Đặt true để chỉ lấy issue/PR được giao cho người dùng.
        :param limit: Số issue cần lấy (mặc định 10, tối đa 50).
        :param __user__: Thông tin người dùng hiện tại từ OpenWebUI (được tự động tiêm vào).
        :return: Danh sách issue/PR kèm số hiệu, tiêu đề, người tạo, nhãn và repo.
        """
        token, err = await self._require_token(__user__, __event_emitter__)
        if err:
            return err

        limit = max(1, min(int(limit or 10), 50))
        state = state if state in ("open", "closed", "all") else "open"

        if repo:
            params = {"state": state, "per_page": limit}
            if assigned_to_me:
                params["filter"] = "assigned"
            data, err = self._api(f"/repos/{repo}/issues", token, params)
            tieu_de = f"issue/PR ({state}) của {repo}"
        else:
            if not assigned_to_me:
                return (
                    "Cần nêu tên repo (dạng chu-so-huu/ten-repo), hoặc đặt assigned_to_me = true "
                    "để xem việc đang được giao cho bạn trên mọi repo."
                )
            # /issues (không kèm repo) = việc được giao cho chính user, gộp mọi repo
            data, err = self._api(
                "/issues", token, {"filter": "assigned", "state": state, "per_page": limit}
            )
            tieu_de = f"việc ({state}) đang được giao cho bạn"

        if err:
            return err
        if not data:
            return f"Không có {tieu_de}."

        lines = [f"🐛 {len(data)} {tieu_de}:"]
        for i in data:
            kind = "PR" if i.get("pull_request") else "Issue"
            labels = ", ".join(l.get("name") for l in i.get("labels") or []) or "—"
            where = (i.get("repository") or {}).get("full_name")
            lines.append(
                f"\n**#{i.get('number')} — {i.get('title')}** ({kind}"
                f"{f', repo: {where}' if where and not repo else ''})\n"
                f"Người tạo: {(i.get('user') or {}).get('login')} | Nhãn: {labels}\n"
                f"Link: {i.get('html_url')}"
            )
        return "\n".join(lines)

    async def read_issue(self, repo: str, number: int, __user__: dict = None, __event_emitter__=None) -> str:
        """
        Đọc chi tiết một issue hoặc pull request, kèm bình luận gần nhất.
        Nếu là pull request, tự động lấy luôn phần diff (nội dung thay đổi) để tóm tắt/review code.

        :param repo: Tên repo đầy đủ dạng chu-so-huu/ten-repo.
        :param number: Số hiệu của issue hoặc PR, ví dụ 42.
        :param __user__: Thông tin người dùng hiện tại từ OpenWebUI (được tự động tiêm vào).
        :return: Nội dung issue/PR, diff nếu là PR, và tối đa 10 bình luận gần nhất.
        """
        token, err = await self._require_token(__user__, __event_emitter__)
        if err:
            return err

        issue, err = self._api(f"/repos/{repo}/issues/{number}", token)
        if err:
            return err

        is_pr = bool(issue.get("pull_request"))
        kind = "Pull Request" if is_pr else "Issue"
        out = [
            f"**{kind} #{issue.get('number')}: {issue.get('title')}**",
            f"Trạng thái: {issue.get('state')} | Người tạo: {(issue.get('user') or {}).get('login')}",
            f"Link: {issue.get('html_url')}",
            "",
            (issue.get("body") or "(không có nội dung mô tả)")[:3000],
        ]

        if is_pr:
            pr, err = self._api(f"/repos/{repo}/pulls/{number}", token)
            if not err and pr:
                out.insert(
                    2,
                    f"Nhánh: {(pr.get('head') or {}).get('ref')} → {(pr.get('base') or {}).get('ref')} | "
                    f"+{pr.get('additions', 0)} −{pr.get('deletions', 0)} trên {pr.get('changed_files', 0)} file",
                )
            diff, err = self._api(
                f"/repos/{repo}/pulls/{number}", token, accept="application/vnd.github.diff"
            )
            if not err and diff:
                cut = len(diff) > 12000
                out.append(
                    f"\n--- Diff{' (đã cắt bớt, 12000 ký tự đầu)' if cut else ''} ---\n"
                    f"```diff\n{diff[:12000]}\n```"
                )

        comments, err = self._api(f"/repos/{repo}/issues/{number}/comments", token, {"per_page": 10})
        if not err and comments:
            out.append(f"\n--- {len(comments)} bình luận gần nhất ---")
            for c in comments:
                author = (c.get("user") or {}).get("login")
                out.append(f"\n**{author}**: {(c.get('body') or '')[:800]}")

        return "\n".join(out)

    async def search_code(self, query: str, repo: str = "", limit: int = 10, __user__: dict = None, __event_emitter__=None) -> str:
        """
        Tìm kiếm đoạn code trong các repository mà người dùng có quyền truy cập.

        :param query: Từ khóa cần tìm trong code, ví dụ "def send_email".
        :param repo: Giới hạn tìm trong một repo dạng chu-so-huu/ten-repo; để trống để tìm mọi repo của người dùng.
        :param limit: Số kết quả tối đa (mặc định 10, tối đa 30).
        :param __user__: Thông tin người dùng hiện tại từ OpenWebUI (được tự động tiêm vào).
        :return: Danh sách file khớp kèm đường dẫn và link tới code.
        """
        token, err = await self._require_token(__user__, __event_emitter__)
        if err:
            return err

        limit = max(1, min(int(limit or 10), 30))
        q = f"{query} repo:{repo}" if repo else query
        data, err = self._api("/search/code", token, {"q": q, "per_page": limit})
        if err:
            return err

        items = data.get("items", [])
        if not items:
            return f"Không tìm thấy code nào khớp với '{query}'."

        lines = [f"🔍 {len(items)} file khớp với '{query}':"]
        for it in items:
            lines.append(
                f"\n**{it.get('path')}** — {(it.get('repository') or {}).get('full_name')}\n"
                f"Link: {it.get('html_url')}"
            )
        lines.append("\n(Dùng công cụ đọc file với đường dẫn ở trên để xem nội dung.)")
        return "\n".join(lines)

    async def read_file(self, repo: str, path: str, ref: str = "", __user__: dict = None, __event_emitter__=None) -> str:
        """
        Đọc nội dung một file trong repository GitHub — dùng để giải thích, tóm tắt hoặc review code.

        :param repo: Tên repo đầy đủ dạng chu-so-huu/ten-repo.
        :param path: Đường dẫn file trong repo, ví dụ src/utils/auth.py.
        :param ref: Nhánh, tag hoặc commit SHA; để trống để đọc nhánh mặc định.
        :param __user__: Thông tin người dùng hiện tại từ OpenWebUI (được tự động tiêm vào).
        :return: Nội dung file dạng văn bản, hoặc link nếu file nhị phân/quá lớn.
        """
        token, err = await self._require_token(__user__, __event_emitter__)
        if err:
            return err

        data, err = self._api(
            f"/repos/{repo}/contents/{path.lstrip('/')}",
            token,
            {"ref": ref} if ref else None,
        )
        if err:
            return err

        if isinstance(data, list):
            names = ", ".join(f"{d.get('name')}{'/' if d.get('type') == 'dir' else ''}" for d in data[:40])
            return f"'{path}' là một thư mục. Nội dung: {names}"

        if data.get("encoding") != "base64" or not data.get("content"):
            # File > 1MB: GitHub không trả content inline
            return (
                f"File **{data.get('name')}** quá lớn hoặc ở định dạng không đọc trực tiếp được "
                f"({data.get('size')} bytes).\nXem tại: {data.get('html_url')}"
            )

        try:
            text = base64.b64decode(data["content"]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return (
                f"File **{data.get('name')}** là file nhị phân, không đọc dưới dạng văn bản được.\n"
                f"Xem tại: {data.get('html_url')}"
            )

        cut = len(text) > 10000
        return (
            f"📄 `{repo}/{path}`{f' @ {ref}' if ref else ''}"
            f"{' (đã cắt bớt, 10000 ký tự đầu)' if cut else ''}:\n\n"
            f"```\n{text[:10000]}\n```"
        )

    async def list_commits(
        self, repo: str, limit: int = 10, author: str = "", since: str = "", __user__: dict = None, __event_emitter__=None
    ) -> str:
        """
        Xem các commit gần đây của một repository — dùng để tổng hợp "tuần này team đã làm gì".

        :param repo: Tên repo đầy đủ dạng chu-so-huu/ten-repo.
        :param limit: Số commit cần lấy (mặc định 10, tối đa 50).
        :param author: Lọc theo username GitHub của tác giả; để trống để lấy mọi tác giả.
        :param since: Chỉ lấy commit từ mốc thời gian này, định dạng ISO ví dụ 2026-07-01T00:00:00Z; để trống để bỏ lọc.
        :param __user__: Thông tin người dùng hiện tại từ OpenWebUI (được tự động tiêm vào).
        :return: Danh sách commit kèm tác giả, thời gian và tiêu đề.
        """
        token, err = await self._require_token(__user__, __event_emitter__)
        if err:
            return err

        params = {"per_page": max(1, min(int(limit or 10), 50))}
        if author:
            params["author"] = author
        if since:
            params["since"] = since

        data, err = self._api(f"/repos/{repo}/commits", token, params)
        if err:
            return err
        if not data:
            return f"Không có commit nào khớp điều kiện trong {repo}."

        lines = [f"📝 {len(data)} commit gần nhất của {repo}:"]
        for c in data:
            commit = c.get("commit") or {}
            who = ((commit.get("author") or {}).get("name")) or "?"
            when = ((commit.get("author") or {}).get("date") or "")[:10]
            title = (commit.get("message") or "").split("\n")[0]
            lines.append(f"\n`{(c.get('sha') or '')[:7]}` **{title}**\n{who} — {when}")
        return "\n".join(lines)

    async def list_ci_runs(self, repo: str, only_failed: bool = False, limit: int = 10, __user__: dict = None, __event_emitter__=None) -> str:
        """
        Xem trạng thái các lần chạy CI/CD (GitHub Actions) gần đây của repository —
        dùng để trả lời "build có xanh không", "CI hỏng ở đâu".

        :param repo: Tên repo đầy đủ dạng chu-so-huu/ten-repo.
        :param only_failed: Đặt true để chỉ lấy các lần chạy thất bại.
        :param limit: Số lần chạy cần lấy (mặc định 10, tối đa 30).
        :param __user__: Thông tin người dùng hiện tại từ OpenWebUI (được tự động tiêm vào).
        :return: Danh sách workflow run kèm kết quả, nhánh, thời gian và link xem log.
        """
        token, err = await self._require_token(__user__, __event_emitter__)
        if err:
            return err

        params = {"per_page": max(1, min(int(limit or 10), 30))}
        if only_failed:
            params["status"] = "failure"

        data, err = self._api(f"/repos/{repo}/actions/runs", token, params)
        if err:
            return err

        runs = (data or {}).get("workflow_runs", [])
        if not runs:
            return (
                f"Không có lần chạy CI nào{' thất bại' if only_failed else ''} trong {repo} "
                f"(hoặc repo chưa bật GitHub Actions)."
            )

        icon = {"success": "✅", "failure": "❌", "cancelled": "⚪", "skipped": "⏭️"}
        lines = [f"⚙️ {len(runs)} lần chạy CI gần nhất của {repo}:"]
        for r in runs:
            result = r.get("conclusion") or r.get("status") or "?"
            lines.append(
                f"\n{icon.get(result, '🔄')} **{r.get('name')}** — {result}\n"
                f"Nhánh: {r.get('head_branch')} | {(r.get('created_at') or '')[:16].replace('T', ' ')}\n"
                f"Log: {r.get('html_url')}"
            )
        return "\n".join(lines)
