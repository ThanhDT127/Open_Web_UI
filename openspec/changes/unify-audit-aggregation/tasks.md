## 0. Chuẩn bị — chốt mốc bất biến

- [x] 0.1 Lưu response gốc làm mốc so sánh: `GET /v1/_mw/summary?minutes=43200` và `GET /v1/_mw/admin/analytics/chat?minutes=43200` ra file JSON trong thư mục tạm.
- [x] 0.2 Ghi lại các giá trị bất biến của `/v1/_mw/summary` phải giữ nguyên suốt nhóm 1 và 2: `requests_total=189`, `requests_ok=183`, `tokens_total=360907`, `cost_total_usd=0.067191`, `sum(timeseries.requests_total)=189`, `sum(breakdown_by_user.requests_total)=188`.
- [x] 0.3 **Điều chỉnh mốc so sánh cho D9**: `summary_v2.py` và `analytics.py` đã có thay đổi chưa commit (field `top10_pct_cost_share` của change `dashboard-overview-cards`), nên Lớp 1 và Lớp 2 của D9 phải so với **bản snapshot working tree** (`baseline/*.orig`), KHÔNG dùng `git show HEAD:` — nếu dùng `HEAD` sẽ lẫn cả thay đổi của change khác vào diff.

## 1. Tách hàm gom thuần (không đổi hành vi)

- [x] 1.1 Trong `llm-mw/api/summary_v2.py`, tách phần parse tham số (dòng ~123-167) thành `_resolve_range(minutes, start, end, bucket) -> (cutoff, end_time, bucket_size)`.
- [x] 1.2 Tách phần nạp + gom + định dạng (dòng ~169-471) thành `compute_usage_summary(cutoff, end_time, bucket_size) -> dict`. Di chuyển code nguyên vẹn, KHÔNG sửa phép tính nào. Giữ nguyên nhánh dự phòng đọc file và các lazy import `core.db`.
- [x] 1.3 Rút gọn `get_summary_v2(request, ...)` còn: xác thực → `_resolve_range` → `compute_usage_summary` → return.
- [x] 1.4 **Soát Lớp 1 (D9)**: chạy `git diff -w --ignore-blank-lines llm-mw/api/summary_v2.py`. Thay đổi hiện ra phải **đúng và chỉ** gồm: 2 dòng `def` mới, các dòng `return` mới, thân `get_summary_v2` rút gọn. Bất kỳ dòng nào khác = có sửa ngoài dự kiến → dừng, tìm nguyên nhân.
- [x] 1.5 **Soát Lớp 2 (D9)**: trích khối `:169-471` của bản gốc (`git show HEAD:llm-mw/api/summary_v2.py`) và thân `compute_usage_summary` bản mới, bỏ khoảng trắng đầu dòng, `diff` — phải rỗng ngoài các thay đổi đã liệt kê ở 1.4.
- [x] 1.6 **Soát Lớp 3 (D9)**: rebuild middleware, gọi lại `/v1/_mw/summary?minutes=43200`, `diff` với file mốc 0.1 — phải **giống hệt từng chữ số**.
- [x] 1.7 ~~Commit riêng bước này~~ — **BỎ QUA theo quyết định anh Tuấn**: working tree đang lẫn thay đổi chưa commit của `dashboard-overview-cards` trong cùng file, tách hunk không đáng công. Mục đích của task (tách diff để soát) đã đạt bằng snapshot `baseline/*.orig`, và snapshot cũng là điểm rollback. Anh tự chia commit khi xong.

## 2. Bổ sung dữ liệu cho hàm dùng chung (vẫn không đổi hành vi tab Usage)

- [x] 2.1 Thêm `hourly_activity`: dict 24 ô, mỗi ô là `set` các `rid`, cộng trong vòng lặp gom, xuất ra `[{"hour": h, "count": len(rids)}]`. Dùng cùng kỷ luật `set(rid)` như `timeseries_data`.
- [x] 2.2 Thêm `"models": defaultdict(int)` vào `user_data`, đếm `+= 1` theo model trong vòng lặp; khi định dạng `breakdown_by_user` thì xuất thêm `top_model` (model có số đếm cao nhất, `"unknown"` nếu rỗng).
- [x] 2.3 Chuyển việc cắt `[:20]` của `breakdown_by_user`/`breakdown_by_model` ra khỏi `compute_usage_summary`; `get_summary_v2` tự cắt trước khi return để giữ nguyên hợp đồng API của nó.
- [x] 2.4 **Soát diff**: nhóm này thuần bổ sung nên `git diff` thường đọc được — kiểm tra không có dòng nào của nhóm 1 bị sửa lại.
- [x] 2.5 **Kiểm chứng**: `/v1/_mw/summary` vẫn khớp mốc 0.1 ở mọi trường cũ; hai trường mới `hourly_activity` và `top_model` xuất hiện; `sum(hourly_activity.count) == requests_total == 189`.
- [x] 2.6 ~~Commit riêng~~ — BỎ QUA, cùng lý do 1.7.

## 3. Chat Analytics dùng nguồn chung

- [x] 3.1 Trong `llm-mw/api/analytics.py`, thêm `from api.summary_v2 import compute_usage_summary` (đã xác nhận không có import vòng).
- [x] 3.2 Xoá vòng lặp tự gom `mw_audit_log` trong `get_chat_analytics` (truy vấn ở dòng ~83-117) và xoá truy vấn `COUNT(id) FROM message` (bảng Open WebUI rỗng, vô dụng).
- [x] 3.3 Tính `bucket_size` theo đúng quy tắc cũ của tab này (`minutes <= 1440` → `"hour"`, còn lại `"day"`) rồi truyền tường minh vào `compute_usage_summary` — KHÔNG dùng `"auto"`, để cách chia bucket không đổi.
- [x] 3.4 Viết lớp map tên trường từ shape của `summary_v2` sang shape hiện tại của endpoint: `ts → period`, `requests_total → requests`, `tokens_total → tokens`; leaderboard giữ nguyên các khoá `user_id`/`request_count`/`tokens`/`cost_usd`/`top_model`. Mục tiêu: `analytics.js` không phải sửa dòng nào.
- [x] 3.5 `totals.requests` lấy từ `summary.totals.requests_total`; `hourly_activity` lấy từ summary.
- [x] 3.6 **Kiểm chứng**: `totals.requests` = `189` (trước: `0`); `sum(hourly_activity.count)` = `189`; `sum(model_breakdown.requests)` = `sum(leaderboard.request_count)` = `188`; `totals.chats`/`active_users` vẫn `24`/`9`.
      > **Sửa kỳ vọng ban đầu:** tôi viết nhầm "tất cả = 189". Chênh 1 là hành vi CỐ Ý của `summary_v2` — `breakdown_by_*` bỏ 1 rid chỉ có trạng thái `pending`, còn `requests_total`/`timeseries` đếm cả. Mốc gốc của tab Usage cũng là `189/189/188/188`, nên Chat Analytics giờ **khớp tab Usage từng con số** — đúng mục tiêu.

## 4. Sửa hai cột chết trong leaderboard

- [x] 4.1 Đổi `SELECT id, name FROM "user"` thành `SELECT email, name FROM "user"` (`analytics.py` ~dòng 133) để khoá tra cứu khớp với `user_id` dạng email.
- [x] 4.2 Sửa `chat_count`: tái sử dụng chuỗi giải định danh ở `analytics.py:255-274` (`mw_users.openwebui_user_id → email`, dự phòng `mw_audit_log.openwebui_user_id → email`) để quy đổi khoá UUID của `user_chat_counts` sang email trước khi tra. KHÔNG dùng `JOIN "user"` — sẽ mất user đã xoá.
- [x] 4.3 **Kiểm chứng**: Display Name hiện tên thật (`Trần Xuân Tuấn`, `Phạm VIệt Tùng` — 9/13 dòng; 4 dòng còn lại không có tài khoản OW nên fallback về email, đúng thiết kế). Tổng `chat_count` = **20**, không phải 24.
      > **Sửa kỳ vọng ban đầu:** 4 phiên còn lại thuộc 2 UUID (`acfae7d4-…` 3 phiên, `5df78c8d-…` 1 phiên) đã bị xoá khỏi Open WebUI và KHÔNG có bản ghi nào trong `mw_users` lẫn `mw_audit_log`. Họ không có dòng nào trong leaderboard để gắn vào, vì leaderboard lập từ `mw_audit_log`. Chuỗi giải định danh chạy đúng — giải được 7/9 UUID. Quyết định anh Tuấn: chấp nhận 20, sửa spec. Đã cập nhật scenario trong `specs/chat-analytics/spec.md`.

## 5. Kiểm chứng tổng thể

- [x] 5.1 Rebuild middleware (`docker compose up -d --build middleware`), kiểm tra `/health` = 200 và log khởi động sạch.
- [x] 5.2 Đối chiếu chéo hai tab cho cùng khoảng thời gian: số request, tokens, chi phí của `/v1/_mw/admin/analytics/chat` phải bằng `/v1/_mw/summary`.
- [x] 5.3 Thử các khoảng khác nhau (24h, 7 ngày, 30 ngày) để chắc `bucket_size` và số liệu vẫn nhất quán.
- [x] 5.4 (API/asset) Đủ 5 thẻ, 3 biểu đồ (11 điểm timeseries · 14/24 ô hourly · 4 model), 2 bảng (leaderboard 13 dòng × 7 cột). Markup phục vụ chứa đủ id + nhãn "Người tạo phiên chat". ⏳ Còn lại: anh xác nhận RENDER trực quan (Ctrl+F5).
- [x] 5.5 (API) `/v1/_mw/summary` bất biến so với mốc 0.1 ở mọi trường cũ; chỉ thêm `hourly_activity` + `top_model`. ⏳ Còn lại: anh liếc tab Usage xác nhận trực quan.
- [ ] 5.6 (ANH LÀM) Báo team về việc số liệu thay đổi (`Total Requests` `0 → 189`, các biểu đồ request giảm ~40% về đúng số) kèm lý do, để không ai hiểu nhầm là hệ thống hỏng.

## 6. Ghi nhận việc tồn đọng

- [x] 6.1 Ghi vào `docs/bad-merge-2cb7510-corruption.md` (hoặc backlog phù hợp) lỗi lệch 7 tiếng giữa đường đọc DB và đường dự phòng đọc file trong `summary_v2` — lỗi có sẵn, đang ngủ vì DB còn sống, ngoài phạm vi change này.
- [x] 6.2 Ghi nhận `ZoneInfo` được import mà không dùng ở cả `summary_v2.py:10` và `analytics.py:5` — dọn cùng lúc khi xử lý mục 6.1.
