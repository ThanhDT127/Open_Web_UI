## Context

Mọi số trong tài liệu này đo trực tiếp trên `openwebui-postgres` và các container đang chạy ngày **31/07/2026**, không phải ước lượng.

```
mw_request_log — 104.191 dòng
  outbound                51.328      ← nguồn của tab Access
  status 200              46.685
  status 503               1.981      ← 100% là /health tự báo
  status 429               1.375
  status 404                 292
  status 502                 242
  status 401                 157
  status 403                 142
  status 400 · 500 · 405 · 402 · 422   107
  tổng status ≥ 400        4.296
  giá trị `client` phân biệt   11      ← không giá trị nào là người
```

`mw_request_log` là bảng **đang ghi**, nên các con số trên là ảnh chụp lúc khảo sát. Bất biến nghiệm thu vì vậy phát biểu theo **quan hệ giữa các con số**, không theo giá trị tuyệt đối — giống Phase 7b và Phase 9.

### Một sự thật về môi trường phải ghi lại trước

Trước ngày 31/07/2026, **nginx chưa từng chạy trên dev**: `nginx/ssl/` rỗng nên container `[emerg]` rồi chết sau 0,6 giây, `RestartCount = 47`, **0 dòng access log**. `docker-compose.override.yml` mở `5000:5000` nên trình duyệt đi thẳng vào middleware.

```
DEV (trước 31/07)                    PRODUCTION
Trình duyệt → middleware:5000        Trình duyệt → nginx → middleware
             (không có proxy)                     (có proxy)
```

Hệ quả: **bug `/health` không tái hiện được trên dev**, vì dev vốn không có tầng nginx để định tuyến sai. Nghiệm thu Phase 7 (28/07) và Phase 9 (31/07) đều làm ở `localhost:5000`, tức đi cửa sau — đó là lý do khoảng mù này sống sót qua ba phase.

Đã dựng chứng chỉ tự ký cho dev (`CN=localhost`, SAN `DNS:localhost,IP:127.0.0.1`, hạn 31/07/2027) và nginx nay chạy. **Từ change này trở đi, nghiệm thu trình duyệt phải dùng `https://localhost:3000/dashboard`**, không phải `:5000` — nếu không, mọi lỗi liên quan proxy vẫn vô hình.

## Goals / Non-Goals

**Goals**

- Không thẻ nào trên dashboard được phép hiển thị câu trả lời của **một dịch vụ khác** như thể là của mình.
- Không cột nào được phép in một hằng số và trình bày nó như một phép đo.
- Mỗi tỷ lệ lỗi phải ứng với **đúng một loại hành động sửa chữa**.
- Chỉ tiêu bảo mật không được lấy nhiễu từ chính công cụ đang hiển thị nó.

**Non-Goals**

- Không dựng thẻ đếm IP (xem `proposal.md`). Việc *ghi* IP thì có làm.
- Không đụng nhật ký thao tác admin.
- Không thêm cảnh báo tự động / gửi email. Change này chỉ hiển thị; kênh cảnh báo là việc riêng.
- Không vá dữ liệu lịch sử. 11 giá trị `client` cũ vĩnh viễn là IP container.
- Không đổi tên cột bảng sang tiếng Việt (quy tắc Phase 11: đổi thì đổi cho cả 12 tab cùng lúc).

## Decisions

### 1. Route mới `/v1/_mw/health` thay vì sửa nginx

| | Thêm `location = /health` vào nginx | Route `/v1/_mw/health` ✅ |
|:--|:--|:--|
| File phải đụng | `nginx.conf` + reload nginx riêng | 1 dòng `main.py` |
| Xác thực | `/health` không có guard → phơi `disk_free_gb`, `active_users` ra Internet | `/v1/_mw/` đã nằm sau `require_admin_or_session` |
| `/health` cũ | phải cẩn thận không hỏng Docker `HEALTHCHECK` | không đụng |
| Rủi ro triển khai | nginx sai cú pháp = cả hệ thống mất mặt tiền | sai thì chỉ 1 route 404 |

Route cũ `/health` **giữ nguyên** — `HEALTHCHECK` trong `Dockerfile` gọi nó qua `localhost` trong container, không đi qua nginx, nên vốn vẫn đúng.

### 2. Thẻ Sức khỏe **không** hiển thị `active_users`

`/health` trả `active_users` từ `load_users()` — đếm tài khoản chưa bị khoá. Trên dashboard đã có hai con số khác cùng tên gọi:

```
Users tab badge   "Đang bật: X · Tổng: Y"   ← tài khoản chưa bị khoá
Overview          "Tỷ lệ áp dụng 83,3%"     ← có dùng thật trong kỳ  (Phase 4)
/health           active_users: 12          ← lại là "chưa bị khoá"
```

Ba chỗ, hai định nghĩa, một cách gọi. Đây đúng con lỗi Phase 0 và Phase 8 đã đi dọn. Rẻ nhất là **không hiện** — tab Users đã lo con số đó. Payload vẫn trả, tầng hiển thị bỏ qua.

### 3. `uptime_seconds` phải mang nhãn nói đúng nó là gì

Nó là *"bao lâu kể từ lần khởi động gần nhất"*, không phải độ sẵn sàng. Mỗi lần deploy nó về `0` — dự án này build lại ở Phase 6, 7, 9. Sau mỗi lần deploy thẻ sẽ hiện **"3 phút"** trên một hệ hoàn toàn khoẻ và đọc như vừa có sự cố.

Nhãn chốt: **"Chạy liên tục từ lần khởi động gần nhất"**. Không dùng chữ "Uptime" trống.

Thêm nữa `uvicorn --workers 4` nghĩa là **4 tiến trình, mỗi cái giữ `app.state.start_time` riêng**. Bình thường chúng gần bằng nhau, nhưng nếu một worker chết và tự sinh lại thì hai lần F5 liên tiếp ra hai số khác nhau. Chấp nhận được với một chú thích, vì lấy `min` đòi hỏi chia sẻ trạng thái giữa worker — quá đắt cho một dòng chú thích.

### 4. Ba nhóm lỗi, không chồng lấn, và `/health` đứng riêng

```
                    tổng status ≥ 400
   ┌──────────────┬──────────────┬──────────────┬──────────────┐
   │  failures    │  denied      │  throttled   │  còn lại     │
   │  5xx         │  401 · 403   │  429         │  404 · 400…  │
   │  TRỪ /health │              │              │              │
   └──────────────┴──────────────┴──────────────┴──────────────┘
      hệ hỏng        chính sách      quá tải        khách gõ sai
      → gọi người    → xem ai        → nâng hạn     → thường bỏ qua
```

Ba nhóm ứng với ba hành động sửa chữa khác nhau, nên chúng là ba con số. Bất biến nghiệm thu: **bốn nhóm cộng lại đúng bằng số ≥ 400 cũ** — không dòng nào bị đếm hai lần, không dòng nào rơi ra ngoài.

`/health` bị trừ khỏi `failures` vì **1.981/1.981 số 503 của hệ thống đến từ nó**, và đó là container tự thăm dò chính mình, không phải người dùng gặp lỗi. Để nguyên thì nhóm `failures` bị nó át hoàn toàn (1.981 so với 265 lỗi thật) và thẻ sẽ vô dụng. Số lượt 503 của `/health` **vẫn trả trong payload** dưới khoá riêng, vì nó là tín hiệu sức khoẻ thật — chỉ không thuộc nhóm "người dùng gặp lỗi".

### 5. Sửa nợ #4 tại gốc, không lọc nhiễu ở tầng đếm

Trong 302 lượt 401/403 thì **89** đến từ chính dashboard:

```
/v1/_mw/* trừ dashboard/login        403 × 89   ← tab tự gọi khi chưa auth
   trong đó  admin/notifications/unread   53
             admin/alerts/config          17
             19 đường khác                19
/v1/_mw/dashboard/login              403 × 37   ← đăng nhập sai (đúng thật)
401 (chủ yếu /v1/embeddings, /v1/models)  157   ← subkey sai, không phải dashboard
```

| | Lọc nhiễu ở tầng đếm | Sửa nợ #4 ✅ |
|:--|:--|:--|
| Cỡ | ~15 dòng + một allowlist đường dẫn phải bảo trì mãi | ~5 dòng, xong hẳn |
| Kết quả | sạch hơn, không sạch hẳn | nhiễu **biến mất tại nguồn** |
| Tác dụng phụ | không | cookie 4 giờ hết vô dụng: F5 không bắt đăng nhập lại |

Gốc rễ: `index.html` gọi `initAuth()` sau **4 lần `await`** (3 `import()` động + `await initAPI()`), bên trong `initAuth()` mới đăng ký `document.addEventListener('DOMContentLoaded', …)` ở `auth.js:145`. Nhưng `DOMContentLoaded` đã bắn từ lúc script module chạm `await` đầu tiên và **không bao giờ bắn lại**. Chính comment ngay trên nó (`auth.js:144`) viết *"a valid HttpOnly cookie should be enough to restore the dashboard"* — ý định đúng, code hỏng lặng lẽ.

### 6. `--forwarded-allow-ips` phải khai dải tường minh

`--proxy-headers` bảo `uvicorn` tin `X-Forwarded-For`. Nhưng tin **của ai** thì do `--forwarded-allow-ips` quyết. Để `*` nghĩa là bất kỳ client nào cũng tự khai địa chỉ của mình — biến một chỗ ghi log thành chỗ giả mạo.

**Không được ghim dải mạng cụ thể của compose.** Docker cấp subnet động, và dự án này đã trôi thật:

```
hôm nay   openwebui-network          172.18.0.0/16    ← nginx + middleware
          openwebui-sandbox-network  172.19.0.0/16
trước đây 172.19.0.1 từng gọi thẳng middleware  ← mạng chính lúc đó là 172.19
```

Ghim `172.18.0.0/16` thì sau một lần `docker compose down && up` cấp lại subnet khác, nginx **thôi được tin** — và hỏng **im lặng**: hệ thống quay về ghi IP socket, đúng con bug đang sửa, không thông báo gì. Nên khai `172.16.0.0/12` (trọn dải riêng RFC1918 mà Docker cấp phát), hoặc ghim subnet trong `docker-compose.yml` rồi mới ghim ở đây — **không được chọn cách thứ ba là ghim một bên**.

Lưu ý phạm vi tin cậy: trên production cổng `5000` **không publish** nên chỉ container tới được. Trên dev thì `docker-compose.override.yml` mở `5000:5000`, nghĩa là máy dev tự khai `X-Forwarded-For` được — chấp nhận, vì đó là máy của chính người phát triển.

Bài test đã chạy được đầu-cuối trên dev sau khi nginx sống:

```
curl -sk https://localhost:3000/v1/_mw/probe
  ĐẠT    payload.client = 172.18.0.1     (máy thật)
  TRƯỢT  payload.client = 172.18.0.9     (nginx)
```

Và test chống giả mạo: gửi `X-Forwarded-For` từ nguồn **ngoài** dải tin cậy, giá trị đó phải bị bỏ qua.

### 7. P95 của tab Access **không** được dùng chung khoá với P95 tab Usage

Cả hai payload đều trả một trường tên `p95_latency_ms`, nhưng chúng đo hai thứ khác nhau:

```
tab Usage   ← mw_audit_log    ← thời gian MODEL trả lời
tab Access  ← mw_request_log  ← thời gian MỌI request HTTP, kể cả tải file tĩnh dashboard
```

Registry hiện có đúng một entry `p95_latency_ms` với nhãn `P95 Latency`, đang phục vụ tab Usage và Overview. Nối thẳng P95 của Access vào entry đó thì hai tab hiện cùng một nhãn cho hai đại lượng khác nhau — **đúng con "Total Requests" mà Phase 0 sinh ra để dọn**, chỉ khác chỗ.

Chốt: khoá riêng `http_p95_latency_ms`, nhãn phải nói rõ đây là tầng HTTP chứ không phải thời gian model trả lời.

> **Phát hiện ngoài phạm vi, cố ý không sửa:** `summary_v2.py:471` và `:520` mắc đúng lỗi `if p95 else None` mà mục 6 của tasks đang sửa cho `access_logs.py:185` — P95 bằng `0` thật của một user hoặc một model bị biến thành `None`. Không gộp vào change này vì đó là bảng breakdown của tab Usage, sửa cùng lúc sẽ làm số tab Usage đổi trong một change mang tên Access. Ghi lại để phase sau khỏi điều tra lại.

### 8. Cảnh báo chi phí bất thường tính ở frontend

`timeseries_data` (khai ở `summary_v2.py:217`, cộng `cost_total` ở `:318`) đã gom chi phí theo bucket. So bucket cuối với trung bình chuỗi là số học thuần — không cần endpoint mới, không cần query lại, cùng lý do Phase 2 chọn làm CK/KT ở frontend.

**Phải có ngưỡng mẫu tối thiểu.** Chuỗi 3 ngày thì "gấp 2 lần trung bình" là chuyện thường; cảnh báo sẽ kêu mỗi ngày và người ta sẽ học cách bỏ qua nó. Ngưỡng khai ở `metrics_registry.js` cùng chỗ với `minSample` của `csat_percent` và `citation_hit_rate` — cùng cơ chế, không dựng cái mới.

Và **không tô màu khi bucket cuối chưa đóng**: ngày hôm nay mới chạy được 3 tiếng thì chi phí của nó đương nhiên thấp, so với trung bình cả ngày là so hai thứ khác đơn vị.

## Risks

| Rủi ro | Mức | Xử lý |
|:-------|:----|:------|
| `--forwarded-allow-ips` khai sai dải → client tự khai IP giả | cao nếu sai | Test chống giả mạo bắt buộc nằm trong tasks, không phải kiểm tuỳ ý |
| Sửa `CMD` trong `Dockerfile` sai cú pháp → container không lên | trung bình | Nay test được trên dev trước khi lên production; trước đây thì không |
| Ba nhóm lỗi cộng không khớp tổng cũ | trung bình | Bất biến bắt buộc trong nghiệm thu, đo trên ≥ 4 cửa sổ |
| Sửa `auth.js` làm hỏng luồng đăng nhập | trung bình | Nghiệm thu cả 3 đường: cookie còn hạn · cookie hết hạn · chưa từng đăng nhập |
| Nhãn "Chạy liên tục…" vẫn bị đọc thành uptime | thấp | Chú thích in kèm mốc khởi động thật |
| Nghiệm thu lại làm ở `:5000` → khoảng mù cũ tái diễn | **cao** | Ghi vào tasks: mọi kiểm tra định tuyến phải qua `:3000` |
