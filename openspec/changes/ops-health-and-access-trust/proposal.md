## Why

Tab **🌐 Access** và thẻ **🩺 Sức khỏe hệ thống** là hai chỗ duy nhất trên dashboard trả lời câu hỏi của người trực máy — *"hệ thống còn sống không, có gì bất thường không"*. Khảo sát ngày 31/07/2026 cho thấy cả hai đều chưa dùng được, và lý do không phải thiếu chỉ tiêu.

**Thẻ Sức khỏe không lấy được dữ liệu, nhưng không báo lỗi.** `api/health.py` trả đủ `uptime_seconds` · `litellm` · `disk_free_gb`, đăng ký tại `main.py:178`. Nhưng `nginx.conf` **không có `location /health`**, nên request từ trình duyệt rơi vào `location /` (dòng 137) và được đưa sang Open WebUI. Đo trực tiếp sau khi dựng nginx trên dev:

```
qua nginx  :3000/health  →  {"status":true}                        ← Open WebUI
thẳng mw   :5000/health  →  {"ok":true,"uptime_seconds":3738,…}    ← đúng
```

Open WebUI trả **200**, nên `res.ok` là `true` và không có gì trên màn hình lộ ra. Dòng uptime ở thẻ `ovCardHealth` (Overview) đã để trống từ Phase 1 chờ đúng mục này.

**Tab Access hiện hai cột bịa.** `_format_access_result` trả `{"path", "count"}`, còn `access.js:31-34` đọc `p.error_rate_percent` rồi rơi về `p.errors || 0` — cả hai đều `undefined` nên luôn in `0`. Bảng có 4 cột, cột *Errors* và *Error rate* chưa bao giờ khác `0`, trong khi cùng cửa sổ có **4.296 request ≥ 400**. Người đọc kết luận "không đường nào lỗi".

**Một thẻ "Error Rate" gộp ba loại lỗi khác bản chất.** Đo trên 51.328 dòng `outbound`:

| Nhóm | Mã | Số lượt | Bản chất |
|:-----|:---|--------:|:---------|
| Vận hành | 502 · 500 | 265 | hệ thống hỏng |
| Quá tải | 429 | 1.375 | chạm rate-limit |
| Từ chối | 401 · 403 | 302 | chính sách truy cập |
| Riêng `/health` | 503 | 1.981 | healthcheck tự báo, **toàn bộ 503 của hệ thống** |

Trộn `429` (quá tải) với `403` (từ chối) vào một tỷ lệ thì không con số nào hành động được. Đây đúng ranh giới Phase 3 đã cố ý hoãn sang đây.

**Chỉ tiêu 401/403 nếu dựng bây giờ sẽ đo chính dashboard.** Trong 302 lượt, **89** là các tab tự bắn request vào `/v1/_mw/*` trước khi phiên được khôi phục — hậu quả của **nợ kỹ thuật #4**: `initAuth()` đăng ký `document.addEventListener('DOMContentLoaded', …)` (`auth.js:145`) sau 4 lần `await`, mà sự kiện đó đã bắn từ lúc script chạm `await` đầu tiên và **không bao giờ bắn lại**.

**IP ghi trong log không phải của người dùng.** Cùng một máy, cùng một lệnh `curl`:

```
đi thẳng   →  client = 172.18.0.1    (máy thật)
qua nginx  →  client = 172.18.0.9    (container nginx)
```

`nginx.conf` **có** gửi `X-Forwarded-For`, nhưng `uvicorn` chạy không có `--proxy-headers` nên không đọc. Kiểm chứng: gửi `X-Forwarded-For: 203.0.113.55` → ghi lại `172.18.0.1`. Toàn bộ `mw_request_log` có **11 giá trị `client` phân biệt, không giá trị nào là người** — đều là IP container hoặc localhost. Hệ thống này **phơi ra Internet** (`nginx.conf:36` — `NAT 51122 → 3000`), nên đây là một khoảng mù thật, và **dữ liệu không ghi thì không dựng lại được**.

## What Changes

**Sửa cho đúng — số đang hiển thị sẽ ĐỔI:**

- Route mới `GET /v1/_mw/health` gọi lại chính `health_check`. Chọn cách này thay vì thêm `location = /health` vào nginx: đường `/v1/_mw/` đã nằm sau `require_admin_or_session`, nên không phơi `disk_free_gb` và `active_users` ra Internet, và không cần deploy nginx riêng. `/health` giữ nguyên cho Docker `HEALTHCHECK`.
- Bỏ fail-open `access_logs.py:62` — `try: _access_summary_db() except: pass` rồi lặng lẽ đọc file log. DB hỏng thì tab Access hiện số từ một nguồn khác mọi tab còn lại, không dấu hiệu gì. Nay raise, và tầng hiển thị dựng banner đỏ **kèm xoá số cũ**.
- Bảng Top Paths trả `errors` và `error_rate_percent` **thật cho từng đường**, bất biến `Σ errors từng path == totals.error_count`.
- Tách `error_rate_percent` thành **ba nhóm không chồng lấn**: `failures` (5xx trừ `/health`) · `denied` (401/403) · `throttled` (429). Bất biến: ba nhóm **cộng phần 4xx còn lại cộng số 503 của `/health`** bằng đúng số ≥ 400 cũ — không dòng nào đếm hai lần, không dòng nào rơi ra ngoài.
- `access_logs.py:41` là **bản sao thứ năm** của bộ giải mã thời gian → gọi `summary_v2._resolve_range`, truyền `minutes=60` tường minh để giữ mặc định cũ. Đóng nốt **nợ kỹ thuật #1**.
- `p95_latency_ms` dùng `round(v, 2) if p95_latency else None` — P95 bằng `0` thật sẽ thành `None`. Sửa thành `is not None`, và trả thêm `latency_sample_count` vì `if ms:` bỏ qua dòng thiếu `ms` (đúng bài học `latency_sum_ms` của Phase 7a).
- **Nợ kỹ thuật #4**: bỏ hẳn listener `DOMContentLoaded` trong `initAuth()`, gọi thẳng `checkAuthStatus()`. Sửa tại gốc rẻ hơn và sạch hơn lọc nhiễu ở tầng đếm — và làm cookie 4 giờ hết vô dụng.
- **Ghi đúng địa chỉ người gọi**: `--proxy-headers --forwarded-allow-ips` cho `uvicorn`. Dải tin cậy phải khai tường minh; để `*` thì bất kỳ ai cũng tự khai IP giả được, biến một chỗ ghi log thành lỗ hổng.

**Thêm chỉ tiêu — số chỉ có THÊM:**

- Thẻ **Sức khỏe hệ thống** ở Overview hết placeholder: LiteLLM · dung lượng đĩa · thời gian chạy.
- **P95 tầng HTTP** (đã tính sẵn ở `access_logs.py:185`), kèm số mẫu. ⚠️ Trường payload giữ tên `p95_latency_ms`, nhưng **khoá registry phải khác** — entry `p95_latency_ms` sẵn có đang đo thời gian model trả lời cho tab Usage, dùng chung là tái tạo con "Total Requests" của Phase 0.
- **Tỷ lệ bị từ chối** (401/403) — sạch nhờ sửa nợ #4 trước.
- **Số lần đăng nhập dashboard thất bại** — `/v1/_mw/dashboard/login` trả 403, đo được 37 lượt.
- **Cảnh báo chi phí bất thường** (> 2× trung bình ngày), tính thuần frontend từ `timeseries_data` đã có (`summary_v2.py:318` cộng `cost_total` theo bucket).
- Badge so kỳ cho tab Access.

**BREAKING (đối với người đọc, không phải API):** cột *Errors* và *Error rate* của bảng Top Paths đổi từ `0` sang số thật. Thẻ "Error Rate" tách làm ba, nên con số cũ không còn xuất hiện nguyên dạng ở đâu. Payload thêm khoá, không xoá khoá nào.

## Non-goals

Hai mục dưới đây **có trong kế hoạch Phase 10 ban đầu và bị loại sau khi đo**, không phải vì khó.

- **Thẻ "Số IP truy cập".** Việc *ghi* đúng IP vẫn làm (mục trên) vì dữ liệu không ghi thì mất vĩnh viễn. Nhưng *hiển thị* thì không: không có cảnh báo tự động, không có mốc so sánh để biết con số hôm nay là nhiều hay ít, và dashboard chỉ 1–2 người thỉnh thoảng mở. Một con số không ai theo dõi tạo cảm giác an toàn mà không tạo ra an toàn. Phòng thủ thật nằm ở `limit_req` của nginx. Dữ liệu vẫn nằm sẵn trong `mw_request_log`, truy vấn lúc nào cũng được.
- **Nhật ký thao tác admin.** `actor="admin_session"` gán cứng ở 8 chỗ **không phải bug** — `dashboard_login.py` chỉ nhận trường `admin_key`, và cả hai tài khoản `role = admin` đăng nhập bằng cùng một `ADMIN_KEY`. Hệ thống không phân biệt được họ, nên `admin_session` là mô tả trung thực. Ghi được tên thật đòi hỏi **cấp danh tính riêng cho từng admin** — một thay đổi về xác thực, không phải sửa log. Bốn trường còn lại (`ts` · `action` · `target_user` · `changes`) vốn đã đúng và trả lời được câu hỏi vận hành thật *"cuối tuần có ai đụng vào tài khoản này không"*; với 95 dòng trong 10 ngày thì một tab riêng là quá tay.

## Impact

- Specs: `ops-health-signals` (mới) · `http-access-analytics` (mới) · `auth-diagnostics` · `dashboard-metric-registry` · `dashboard-period-compare`
- Code: `main.py` · `api/access_logs.py` · `llm-mw/Dockerfile` · `dashboard/index.html` · `dashboard/js/{access,auth,overview,metrics_registry}.js`
- Tài liệu: `docs/dashboard_metrics_implementation_plan.md` §Phase 10 + hai khoản nợ được đóng
- Đóng **nợ kỹ thuật #1** (bản resolver cuối cùng) và **nợ kỹ thuật #4** (cookie không khôi phục).
- `--proxy-headers` làm **đổi giá trị** ở 3 chỗ khác ngoài phạm vi tab Access: `user_admin.py:59` (`ip` trong nhật ký admin), `core/auth.py:377`, `api/auth_test.py:29`. Cả ba đang ghi IP container; sau thay đổi ghi IP thật.
- Đụng `Dockerfile` nên **bắt buộc `docker compose build middleware`**, không `docker cp` được (`uvicorn --workers 4` không có `--reload`).
