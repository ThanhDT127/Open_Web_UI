# 📊 Dashboard Admin - Hướng Dẫn Chi Tiết

## 🌐 Truy Cập Dashboard

### Từ Máy Local (Máy chạy server)
```
http://localhost:5000/dashboard
http://127.0.0.1:5000/dashboard
```

### Từ Máy Khác Trong Mạng LAN
```
http://192.168.154.61:5000/dashboard
```
*(Thay `192.168.154.61` bằng IP của máy chủ - xem trong output khi chạy `start.ps1`)*

### Yêu Cầu Hệ Thống
- ✅ Middleware phải đang chạy (port 5000)
- ✅ Firewall đã mở port 5000 (đã tự động tạo khi chạy lần đầu)
- ✅ Services bind vào `0.0.0.0` (cho phép truy cập từ mạng)

---

## Overview

Dashboard admin giúp giám sát realtime toàn bộ hoạt động của LLM Gateway với giao diện đẹp, metrics chi tiết, và authentication bảo mật.

---

## 🎨 Giao Diện Dashboard - Chi Tiết Từng Thành Phần

### 1. **Màn Hình Đăng Nhập (Auth Prompt)**

**Khi mở dashboard lần đầu, hiển thị:**

```
┌─────────────────────────────────────┐
│  🔐 Admin Authentication            │
│                                     │
│  Enter your admin key to access    │
│  the dashboard                      │
│                                     │
│  [________________]  (password)     │
│                                     │
│  [   Access Dashboard   ] (button) │
└─────────────────────────────────────┘
```

**Chức năng:**
- Input password field để nhập `ADMIN_KEY`
- Nhấn Enter hoặc click button để login
- Nếu sai key → hiển thị "Invalid admin key" màu đỏ
- Nếu đúng → set cookie session (4 giờ) và vào dashboard

**Bảo mật:**
- Cookie `mw_admin_session` - HttpOnly (chặn XSS)
- JWT token signed bằng `JWT_SECRET`
- Auto-refresh nếu session còn valid
- Tự động redirect về login nếu session hết hạn

---

### 2. **Header Section**

```
╔═══════════════════════════════════════════════════╗
║  📊 LLM Middleware Dashboard                      ║
║  Realtime monitoring and usage analytics          ║
╚═══════════════════════════════════════════════════╝
```

**Thiết kế:**
- Background gradient tím (purple): `#667eea` → `#764ba2`
- Responsive design
- Shadow effect với depth

**Hiển thị:**
- Title: "LLM Middleware Dashboard"
- Subtitle: "Realtime monitoring and usage analytics"

---

### 3. **Metrics Grid - 7 Thẻ Chỉ Số Chính**

**Layout:** Grid responsive, tối thiểu 200px mỗi card, auto-fit

#### **Card 1: LLM Calls** 🤖
```
┌─────────────────┐
│ LLM CALLS       │ ← Label
│ 156             │ ← Số lượng (lớn, màu xanh)
│ Chat: 120       │ ← Breakdown
│ Image: 30       │
│ Audio: 6        │
└─────────────────┘
```

**Hiển thị:**
- Label: "LLM Calls" (chữ hoa, opacity 0.7)
- Value: Số lượng request LLM (chat + image + audio + video)
- Breakdown nhỏ: Chi tiết từng loại
- **Ý nghĩa**: Tổng số lần gọi đến các LLM model (endpoints thực sự xử lý AI)

**Cách tính:**
- Chỉ đếm status: `ok`, `error`, `reconciled` (KHÔNG pending)
- Chỉ đếm endpoints: `/v1/chat/completions`, `/v1/images/generations`, `/v1/audio/*`, `/v1/video/*`
- **KHÔNG** đếm admin ops, health checks

---

#### **Card 2: Admin Ops** 🛠️
```
┌─────────────────┐
│ ADMIN OPS       │
│ 12              │
└─────────────────┘
```

**Hiển thị:**
- Label: "Admin Ops"
- Value: Số lượng operations quản trị
- **Ý nghĩa**: Các thao tác admin (reconcile, reset quota, get usage)

**Cách tính:**
- Đếm endpoints: `/admin/reconcile`, `/admin/reset`, `/admin/usage`
- Giúp phân biệt giữa LLM calls và admin operations

---

#### **Card 3: Pending** ⏳
```
┌─────────────────┐
│ PENDING         │
│ 5               │
└─────────────────┘
```

**Hiển thị:**
- Label: "Pending"
- Value: Số requests đang pending (open)
- Màu vàng warning
- **Ý nghĩa**: Requests đang xử lý và chưa được reconcile

**Cách tính (Control-Grade):**
- Track **last status per rid** từ audit.jsonl
- Đếm số rid có `last_status = "pending"`
- Với streaming: có cả pending → reconciled, chỉ đếm pending cuối cùng
- Cần reconcile để có data đầy đủ
- Nếu quá cao → cần check LiteLLM logs

---

#### **Card 4: Error Rate** ⚠️
```
┌─────────────────┐
│ ERROR RATE      │
│ 2.5%            │
└─────────────────┘
```

**Hiển thị:**
- Label: "Error Rate"
- Value: % requests bị lỗi (1 chữ số thập phân)
- **Ý nghĩa**: Tỷ lệ lỗi trong time window

**Cách tính:**
```
error_rate = (error_count / requests_total) * 100
```
- Chỉ đếm status `error`
- Nếu > 5% → cần điều tra ngay

---

#### **Card 5: P95 Latency** ⚡
```
┌─────────────────┐
│ P95 LATENCY     │
│ 1234ms          │
└─────────────────┘
```

**Hiển thị:**
- Label: "P95 Latency"
- Value: Latency phân vị 95 (ms)
- **Ý nghĩa**: 95% requests hoàn thành trong thời gian này

**Cách tính:**
- Sort tất cả latency_ms (exclude pending)
- Lấy giá trị tại index = 95% * length
- Metric quan trọng cho performance

---

#### **Card 6: Total Tokens** 🎫
```
┌─────────────────┐
│ TOTAL TOKENS    │
│ 1,250,000       │
└─────────────────┘
```

**Hiển thị:**
- Label: "Total Tokens"
- Value: Tổng tokens (format với dấu phẩy)
- **Ý nghĩa**: Tổng tokens xử lý trong time window

**Cách tính:**
- Chỉ cộng từ status `ok` + `reconciled`
- KHÔNG cộng `pending` (chưa biết tokens)
- KHÔNG cộng `error` (cost = 0)

---

#### **Card 7: Total Cost** 💰
```
┌─────────────────┐
│ TOTAL COST      │
│ $0.4525         │
└─────────────────┘
```

**Hiển thị:**
- Label: "Total Cost"
- Value: Tổng chi phí USD (4 chữ số thập phân)
- **Ý nghĩa**: Tổng tiền đã chi trong time window

**Cách tính:**
- Chỉ cộng từ status `ok` + `reconciled`
- Format: `$0.XXXX`
- Metric quan trọng nhất cho billing

---

### 4. **Top Users Table** 🏆

```
╔════════════════════════════════════╗
║  🏆 Top Users by Cost              ║
╠════════════════════════════════════╣
║ User ID          │ Cost (USD)      ║
╟──────────────────┼─────────────────╢
║ admin            │ $0.353453       ║
║ user1            │ $0.125000       ║
║ user2            │ $0.045000       ║
║ ...              │ ...             ║
╚════════════════════════════════════╝
```

**Hiển thị:**
- Top 10 users tiêu tốn nhiều cost nhất
- Sắp xếp theo cost giảm dần
- 6 chữ số thập phân cho cost

**Cách tính:**
- Aggregate từ audit.jsonl trong time window
- Group by `user_id`
- Sum `cost_usd` từ status `ok` + `reconciled`

**Use case:**
- Xác định user nào sử dụng nhiều nhất
- Phát hiện abuse
- Billing report

---

### 5. **Top Models Table** 🤖

```
╔════════════════════════════════════╗
║  🤖 Top Models by Cost             ║
╠════════════════════════════════════╣
║ Model                 │ Cost (USD) ║
╟───────────────────────┼────────────╢
║ gpt-4o                │ $0.250000  ║
║ gpt-4o-mini           │ $0.100000  ║
║ gemini-2.5-flash      │ $0.050000  ║
║ ...                   │ ...        ║
╚════════════════════════════════════╝
```

**Hiển thị:**
- Top 10 models có tổng cost cao nhất
- Sắp xếp theo cost giảm dần
- 6 chữ số thập phân

**Cách tính:**
- Aggregate từ audit.jsonl trong time window
- Group by `model`
- Sum `cost_usd` từ status `ok` + `reconciled`

**Use case:**
- Model nào tốn kém nhất
- Optimize bằng cách dùng model rẻ hơn
- Cost breakdown by model

---

### 6. **Recent Events Stream** 📡

```
╔═══════════════════════════════════════════════════╗
║  📡 Recent Events (Last 50)                       ║
╠═══════════════════════════════════════════════════╣
║ 15:23:45  OK          admin | gpt-4o | 1,234...  ║
║ 15:23:42  PENDING     user1 | gpt-4o-mini | 0... ║
║ 15:23:40  ERROR       user2 | gemini | 0 tokens  ║
║ 15:23:38  RECONCILED  admin | gpt-4o | 2,500...  ║
║ ...                                               ║
╚═══════════════════════════════════════════════════╝
```

**Hiển thị:**
- Scroll box (max-height: 400px)
- Font monospace (Courier New) cho dễ đọc
- Mỗi dòng có 3 phần:
  1. **Timestamp** (HH:MM:SS) - màu xám
  2. **Status** (OK/ERROR/PENDING/RECONCILED) - màu coded
  3. **Detail** (user | model | tokens | cost)

**Màu status:**
- `OK` → Xanh lá (#10b981)
- `ERROR` → Đỏ (#ef4444)
- `PENDING` → Vàng (#f59e0b)
- `RECONCILED` → Xanh dương (#3b82f6)

**Cách hoạt động:**
- **SSE (Server-Sent Events)** stream từ `/v1/_mw/stream`
- Realtime: Event mới tự động xuất hiện ở top
- Giữ tối đa 50 events (auto-remove old ones)
- Auto-reconnect nếu disconnect (retry sau 5s)

**Event data structure:**
```json
{
  "ts": "2025-12-27T15:23:45+07:00",
  "rid": "mw_abc123",
  "user_id": "admin",
  "model": "gpt-4o",
  "status": "ok",
  "tokens_total": 1234,
  "cost_usd": 0.012340
}
```

**Use case:**
- Giám sát realtime
- Debug issues
- Xem request flow
- Phát hiện pending/error ngay lập tức

---

## 🔐 Authentication & Security

### Flow Đăng Nhập

```
┌──────┐                  ┌────────────┐
│ User │                  │ Dashboard  │
└──┬───┘                  └─────┬──────┘
   │                            │
   │ 1. Mở /dashboard           │
   │──────────────────────────>│
   │                            │
   │ 2. Show login prompt       │
   │<──────────────────────────│
   │                            │
   │ 3. Nhập admin_key + Enter  │
   │──────────────────────────>│
   │                            │
   │ 4. POST /v1/_mw/dashboard/login
   │    Body: {admin_key: "..."}│
   │──────────────────────────>│
   │                            │
   │ 5. Verify key              │
   │    Create JWT token        │
   │    Set cookie (4h expiry)  │
   │                            │
   │ 6. Return 200 OK           │
   │    Set-Cookie: mw_admin... │
   │<──────────────────────────│
   │                            │
   │ 7. Hide login, show dash   │
   │    Start polling + SSE     │
   │                            │
```

### Cookie Session Details

**Cookie name:** `mw_admin_session`

**Cookie attributes:**
- `HttpOnly=True` - Chặn JavaScript access (chống XSS)
- `SameSite=Lax` - CSRF protection
- `Max-Age=14400` - 4 giờ (4 * 60 * 60 seconds)
- `Path=/` - Valid cho toàn bộ domain

**JWT payload:**
```json
{
  "iat": 1735290225,           // Issued at (timestamp)
  "exp": 1735304625,           // Expiry (iat + 4 hours)
  "key_hash": "a1b2c3d4..."    // SHA256 hash của admin_key (16 chars)
}
```

**Security features:**
- HMAC-SHA256 signature với `JWT_SECRET`
- Constant-time signature verification
- Auto-expiry sau 4 giờ
- No admin_key trong URL/localStorage

### Authentication Methods

Dashboard sử dụng **Cookie Session** (tự động sau login).

Các endpoint admin hỗ trợ 3 methods:

#### 1. **Cookie Session** (Dashboard default)
```javascript
fetch('/v1/_mw/summary?minutes=30', {
  credentials: 'include'  // Tự động gửi cookie
})
```

#### 2. **X-Admin-Key Header** (Curl/scripts)
```bash
curl http://localhost:5000/v1/_mw/summary \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

#### 3. **Authorization Bearer** (Backward compat)
```bash
curl http://localhost:5000/v1/_mw/summary \
  -H "Authorization: Bearer YOUR_ADMIN_KEY"
```

### Session Expiry Handling

**Khi session hết hạn:**
1. Dashboard gọi `/v1/_mw/summary` → trả 403
2. JavaScript detect 403 → `window.location.reload()`
3. Page reload → không có valid session → hiện login prompt
4. User nhập lại admin_key → login mới

**Auto-check on load:**
```javascript
window.addEventListener('load', () => {
  // Try fetch summary
  fetch('/v1/_mw/summary?minutes=5', {credentials: 'include'})
    .then(res => {
      if (res.ok) {
        // Đã login → skip auth prompt
        showDashboard();
      }
      // Nếu 403 → ở màn login
    });
});
```

---

## 📊 Metrics Logic - Chi Tiết Cách Tính

### Time Window

**Default:** 30 phút (có thể customize)

**Query parameter:**
```
GET /v1/_mw/summary?minutes=30
GET /v1/_mw/summary?minutes=60   # 1 giờ
GET /v1/_mw/summary?minutes=1440 # 24 giờ
```

**Cách tính cutoff:**
```python
cutoff = datetime.now(Asia/Ho_Chi_Minh) - timedelta(minutes=N)
```

Chỉ đếm entries trong `audit.jsonl` có `ts >= cutoff`.

---

### LLM Calls Total

**Endpoints được đếm:**
- `/v1/chat/completions` → "chat"
- `/v1/embeddings` → "embedding"
- `/v1/images/generations` → "image"
- `/v1/audio/transcriptions` → "audio"
- `/v1/audio/speech` → "audio"
- `/v1/video/generations` → "video"

**Status được đếm:**
- ✅ `ok` - Thành công
- ✅ `error` - Lỗi (đếm vào calls nhưng không cost)
- ✅ `reconciled` - Đã reconcile
- ❌ `pending` - KHÔNG đếm (chưa hoàn thành)

**Logic:**
```python
llm_calls_total = 0
for entry in audit_entries:
  if entry['endpoint'] in LLM_ENDPOINTS:
    if entry['status'] in ['ok', 'error', 'reconciled']:
      llm_calls_total += 1
```

---

### Admin Ops Total

**Endpoints được đếm:**
- `/admin/reconcile` - Reconcile pending stream
- `/admin/usage` - Get all users usage
- `/admin/reset` - Reset quota

**Tất cả status đều đếm** (admin ops không có pending).

**Ý nghĩa:**
- Tách biệt admin operations khỏi LLM calls
- Giúp dashboard rõ ràng hơn
- Admin ops không tốn cost

---

### Pending Count

**Đếm theo rid với last status = `pending`** trong time window.

**Cách hoạt động:**
- Track last status per rid: `rid_status[rid] = (timestamp, status)`
- Chỉ đếm rid có last status = "pending"
- Với streaming pattern: pending → reconciled, chỉ reconciled được đếm

**Khi nào có pending:**
- Streaming requests chưa hoàn thành
- Chưa reconcile từ LiteLLM logs

**Khi nào cần reconcile:**
- Pending count cao và không giảm
- Sau khi stream đã kết thúc nhưng vẫn pending

---

### Error Rate

**Formula:**
```
error_rate_percent = (error_count / requests_total) * 100
```

**Chỉ đếm requests có status `ok`, `error`, `reconciled`** (exclude pending).

**Thresholds:**
- < 1% → Tốt (xanh)
- 1-5% → Cảnh báo (vàng)
- > 5% → Nghiêm trọng (đỏ) - cần điều tra

---

### P95 Latency

**Cách tính:**
1. Collect tất cả `latency_ms` từ entries (exclude pending)
2. Sort array tăng dần
3. Index = `0.95 * length`
4. Return value tại index đó

**Ý nghĩa:**
- 95% requests hoàn thành trong thời gian này
- Metric quan trọng cho SLA
- Phát hiện slow requests

---

### Tokens & Cost

**Chỉ tính từ status `ok` + `reconciled`.**

**Không tính:**
- ❌ `pending` - Chưa biết chính xác
- ❌ `error` - Cost = 0 (không charge)

**Aggregate:**
```python
tokens_total = 0
cost_total = 0.0

for entry in audit_entries:
  if entry['status'] in ['ok', 'reconciled']:
    tokens_total += entry.get('tokens_total', 0)
    cost_total += entry.get('cost_usd', 0.0)
```

---

## 🔄 Realtime Updates

### Polling Mechanism

**Summary endpoint polling:**
```javascript
// Initial load
updateSummary();

// Poll every 5 seconds
setInterval(updateSummary, 5000);
```

**Fetches:**
- `/v1/_mw/summary?minutes=30`
- Credentials: include (cookie)
- Auto-reload nếu 403

**Updates:**
- Tất cả 7 metrics cards
- Top users table
- Top models table

---

### SSE Stream

**EventSource connection:**
```javascript
eventSource = new EventSource('/v1/_mw/stream', {
  withCredentials: true  // Gửi cookie
});
```

**Event types:**
- `audit` - Audit log entry mới

**Auto-reconnect:**
- Detect `EventSource.CLOSED`
- Reconnect sau 5 seconds
- Show "Reconnecting..." status

**Event handling:**
```javascript
eventSource.addEventListener('audit', (e) => {
  const data = JSON.parse(e.data);
  addEvent(data);  // Insert vào top
});
```

---

## 🎯 Use Cases - Admin Có Thể Làm Gì

### 1. **Giám Sát Realtime**
- Xem requests đang chạy (Recent Events)
- Theo dõi pending streams
- Phát hiện lỗi ngay lập tức

### 2. **Performance Monitoring**
- Kiểm tra P95 latency
- Xác định slow requests
- Optimize model selection

### 3. **Cost Tracking**
- Tổng chi phí trong time window
- Top users tiêu tốn nhiều nhất
- Top models đắt nhất
- Dự đoán billing

### 4. **Usage Analytics**
- LLM calls breakdown (chat/image/audio)
- User activity patterns
- Model popularity

### 5. **Error Detection**
- Error rate tracking
- Recent error events
- Debug với rid trong logs

### 6. **Capacity Planning**
- Total tokens processed
- Request volume trends
- Peak usage times

---

## 📚 Knowledge Analytics Tab

Tab **📚 Knowledge** biến kho tri thức (OpenWebUI `knowledge` + `file`) thành tín hiệu *áp dụng & giá trị* cho admin — khác với tab **🧬 RAG Health** (chuyên phát hiện sự cố vận hành). Toàn bộ **chỉ đọc**, chỉ admin.

**Endpoints** (`/v1/_mw/knowledge-analytics/`): `inventory`, `kb-value`, `governance`. Kết nối OpenWebUI DB dùng `psycopg2` không pool (giống `core/identity.py`, `core/rag_health.py`), có cache TTL ngắn (`_get_corpus`, mặc định 60s) dùng chung cho cả 3 panel.

### 1. Inventory & Growth
Tổng số KB / file / chunk / dung lượng, biểu đồ tăng trưởng KB & file theo thời gian, và phân bố loại file (`content_type`) — tất cả lấy từ `file.meta`.

### 2. KB Value Matrix
Mỗi KB được phân loại từ 4 tín hiệu: **demand** (số lần tài liệu của KB được đính vào chat, lấy từ `mw_request_log`), **quality** (tỉ lệ trích dẫn `[N]`), **supply** (file/chunk/dung lượng), **freshness** (tạo/sửa/lần dùng gần nhất):

| Nhãn | Điều kiện | Ý nghĩa |
|------|-----------|---------|
| ⭐ **Star** | demand ≥ `MIN_SAMPLE_ATTACHMENTS` (5) và hit-rate ≥ `GOOD_HIT_RATE` (60%) | Dùng nhiều, trích dẫn tốt |
| 🛠️ **Needs Tuning** | demand đủ nhưng hit-rate thấp | Dùng nhiều nhưng RAG trích kém → nên re-chunk |
| 💀 **Dead Knowledge** | có chunk nhưng ~0 lần dùng | Tốn công tạo mà không ai dùng |
| 🌱 **Unproven** | quá ít lần dùng để đánh giá | Chưa đủ dữ liệu |

Ngưỡng là hằng số trong `core/knowledge_analytics.py`, chỉnh khi dữ liệu lớn dần.

### 3. Governance
- **Duplicate files** — nhóm theo cột `file.hash`, ước tính dung lượng có thể thu hồi.
- **Ad-hoc files** (upload ngoài mọi KB) và **Dangling files** (`knowledge_id` trỏ tới KB đã xoá).
- **Owner concentration** — số KB/file/dung lượng theo chủ sở hữu (tên lấy từ bảng `"user"`).

### ⚠️ Giới hạn đã biết (từ spike dữ liệu thật)
- **Usage chỉ phản ánh chat đã log** trong `mw_request_log`; link KB↔chat suy ra bằng cách khớp marker `Filename:`/`Source:` nhúng trong `<source>` với `file.filename` theo **stem** (bỏ đuôi — log có thể mang đuôi khác file gốc).
- Một filename tồn tại ở **nhiều KB** → usage được đánh dấu **Ambiguous** (không quy về 1 KB) thay vì gán bừa.
- **Membership divergence**: feature này dùng `file.meta.data.knowledge_id` (nguồn đáng tin) làm liên kết KB↔file, **không** dùng bảng join `knowledge_file` (quan sát thấy stale — 4 dòng so với 121 file có `knowledge_id`). `core/rag_health.py` hiện vẫn join `knowledge_file`; nên có change riêng để hoà giải.
- Dữ liệu ít (vài KB) khiến số liệu còn thưa; nhãn **Unproven** và ngưỡng mẫu tối thiểu tránh kết luận sai.

---

## 🛠️ Troubleshooting

### Dashboard không mở được

**Check 1: Middleware có chạy không?**
```powershell
netstat -ano | Select-String ":5000" | Select-String "LISTENING"
```
Expected: `0.0.0.0:5000 ... LISTENING`

**Check 2: Firewall có mở không?**
```powershell
Get-NetFirewallRule -DisplayName "Middleware-5000"
```
Expected: Enabled=True, Direction=Inbound, Action=Allow

**Check 3: Từ máy khác ping được không?**
```bash
ping 192.168.154.61
curl http://192.168.154.61:5000/health
```

---

### Login không được (Invalid admin key)

**Check 1: ADMIN_KEY đúng không?**
```powershell
# Trong .env file
Get-Content .env | Select-String "ADMIN_KEY"
```

**Check 2: JWT_SECRET có set không?**
```powershell
Get-Content .env | Select-String "JWT_SECRET"
```

Nếu dùng default → có warning trong logs.

---

### Metrics không update

**Check 1: Có data trong audit.jsonl không?**
```powershell
Get-Content logs\audit.jsonl | Select-Object -Last 5
```

**Check 2: Time window có data không?**
```powershell
# Test với time window lớn hơn
curl http://localhost:5000/v1/_mw/summary?minutes=1440 `
  -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

---

### SSE stream không kết nối

**Check 1: EventSource support?**
- Modern browsers hỗ trợ SSE
- Check browser console có lỗi không

**Check 2: Network tab**
- Open DevTools → Network
- Filter "stream"
- Status phải là 200 (Pending)

**Check 3: Cookie có gửi không?**
- Network → Headers → Cookie
- Phải có `mw_admin_session`

---

---

## 🚀 Quick Start Guide

### Bước 1: Khởi chạy services

```powershell
cd d:\Works\Oppen_Web_UI_fresh
.\scripts\start.ps1
```

Output hiển thị IP và ports:
```
========================================
  CÁC ĐỊA CHỈ TRUY CẬP
========================================

  IP máy này: 192.168.154.61

  LiteLLM:    http://192.168.154.61:4000
  Middleware: http://192.168.154.61:5000
  Dashboard:  http://192.168.154.61:5000/dashboard
  OpenWebUI:  http://192.168.154.61:3000
```

### Bước 2: Mở firewall (chỉ cần 1 lần)

```powershell
# Tự động tạo rules cho cả 3 ports
New-NetFirewallRule -DisplayName "LiteLLM-4000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 4000
New-NetFirewallRule -DisplayName "Middleware-5000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5000
New-NetFirewallRule -DisplayName "OpenWebUI-3000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3000
```

### Bước 3: Truy cập Dashboard

**Từ máy local:**
```
http://localhost:5000/dashboard
```

**Từ máy khác:**
```
http://192.168.154.61:5000/dashboard
```
*(Thay IP tương ứng)*

### Bước 4: Đăng nhập

Nhập `ADMIN_KEY` từ file `.env`:
```
YOUR_ADMIN_KEY
```

✅ **Done!** Dashboard hiển thị metrics realtime.

---

## 📱 Responsive Design

Dashboard tối ưu cho nhiều thiết bị:

### Desktop (> 1200px)
- 7 metrics cards trên 1 hàng
- Tables full width
- Events stream bên phải

### Tablet (768px - 1200px)
- 3-4 cards mỗi hàng
- Tables scrollable
- Events stream dưới tables

### Mobile (< 768px)
- 1-2 cards mỗi hàng
- Stacked layout
- Touch-friendly buttons

---

## 🎨 UI Theme Customization

### Color Scheme

**Background:**
- Page: `#0f172a` (dark navy)
- Cards: `#1e293b` (lighter navy)
- Header gradient: `#667eea` → `#764ba2` (purple)

**Text:**
- Primary: `#e2e8f0` (light gray)
- Labels: `#94a3b8` (muted gray)
- Values: `#60a5fa` (blue)

**Status Colors:**
- OK: `#10b981` (green)
- Error: `#ef4444` (red)
- Pending: `#f59e0b` (yellow)
- Reconciled: `#3b82f6` (blue)

**Accent:**
- Border: `#667eea` (purple)
- Hover: `#5568d3` (darker purple)

### Typography

**Fonts:**
- Sans-serif: `-apple-system, BlinkMacSystemFont, 'Segoe UI'`
- Monospace: `'Courier New', monospace` (events)

**Sizes:**
- Title: `32px`
- Card value: `28px`
- Card label: `12px` uppercase
- Table: `14px`

---

## 🔧 Configuration

### Environment Variables Required

```bash
# .env file (root directory)
ADMIN_KEY=YOUR_ADMIN_KEY                    # Admin authentication
JWT_SECRET=your-strong-jwt-secret-min-32-chars    # Session signing

# Optional (có defaults)
LITELLM_BASE=http://127.0.0.1:4000/v1
AUDIT_LOG_FILE=../logs/audit.jsonl
```

**⚠️ Production Security:**
- Đặt `JWT_SECRET` mạnh (32+ ký tự random)
- Đổi `ADMIN_KEY` định kỳ
- Enable HTTPS và set `secure=True` cho cookies
- Whitelist IPs nếu cần

---

## 📊 API Endpoints Used

### GET /v1/_mw/summary

**Purpose:** Lấy aggregate metrics

**Auth:** Required (cookie hoặc X-Admin-Key)

**Query params:**
- `minutes` (optional, default=60): Time window

**Response:**
```json
{
  "time_window_minutes": 30,
  "cutoff_time": "2025-12-27T15:00:00+07:00",
  
  "requests_total": 156,
  "llm_calls_total": 150,
  "admin_ops_total": 5,
  "pending_count": 8,
  "error_count": 3,
  "error_rate_percent": 2.0,
  
  "chat_calls": 120,
  "image_calls": 25,
  "audio_calls": 5,
  "video_calls": 0,
  
  "p95_latency_ms": 1234.56,
  "tokens_total": 250000,
  "cost_total_usd": 0.4525,
  
  "top_users": [
    {"user_id": "admin", "cost_usd": 0.353453},
    {"user_id": "user1", "cost_usd": 0.099047}
  ],
  "top_models": [
    {"model": "gpt-4o", "cost_usd": 0.250000},
    {"model": "gpt-4o-mini", "cost_usd": 0.100000}
  ]
}
```

---

### GET /v1/_mw/stream

**Purpose:** SSE stream cho realtime events

**Auth:** Required (cookie hoặc X-Admin-Key)

**Response:** SSE format
```
event: audit
data: {"ts":"2025-12-27T15:23:45+07:00","rid":"mw_abc","user_id":"admin",...}

event: audit
data: {"ts":"2025-12-27T15:23:42+07:00","rid":"mw_def","user_id":"user1",...}
```

**Event data:**
```json
{
  "ts": "2025-12-27T15:23:45+07:00",
  "rid": "mw_abc123def456",
  "user_id": "admin",
  "endpoint": "/v1/chat/completions",
  "model": "gpt-4o",
  "status": "ok",
  "status_code": 200,
  "latency_ms": 1234,
  "tokens_in": 100,
  "tokens_out": 200,
  "tokens_total": 300,
  "cost_usd": 0.012340,
  "error_type": null,
  "error_message": null
}
```

---

### POST /v1/_mw/dashboard/login

**Purpose:** Authentication và set session cookie

**Auth:** None (public endpoint)

**Request:**
```json
{
  "admin_key": "YOUR_ADMIN_KEY"
}
```

**Response:**
```json
{
  "ok": true,
  "expires_in_hours": 4
}
```

**Sets cookie:**
```
Set-Cookie: mw_admin_session=eyJ...jwt_token...;
            HttpOnly; Path=/; Max-Age=14400; SameSite=Lax
```

---

### POST /v1/_mw/dashboard/logout

**Purpose:** Clear session cookie

**Auth:** None

**Response:**
```json
{
  "ok": true
}
```

**Clears cookie:**
```
Set-Cookie: mw_admin_session=; Max-Age=0
```

---

## 🧪 Testing Dashboard

### Manual Test Checklist

**✅ Authentication:**
- [ ] Login với đúng key → success
- [ ] Login với sai key → error message
- [ ] Session persist sau refresh (trong 4h)
- [ ] Session expire sau 4h → redirect login

**✅ Metrics Display:**
- [ ] LLM Calls hiển thị đúng số
- [ ] Breakdown (Chat/Image/Audio) đúng
- [ ] Admin Ops đếm riêng
- [ ] Pending count update
- [ ] Error rate tính đúng
- [ ] P95 latency hiển thị
- [ ] Tokens format với dấu phẩy
- [ ] Cost format $X.XXXX

**✅ Tables:**
- [ ] Top Users sort by cost
- [ ] Top Models sort by cost
- [ ] 6 decimal places for cost
- [ ] "No data" nếu empty

**✅ Realtime Stream:**
- [ ] Events hiển thị ngay khi có request
- [ ] Status colors đúng (OK=green, ERROR=red, etc)
- [ ] Max 50 events (auto-trim)
- [ ] Auto-reconnect khi disconnect

**✅ Responsive:**
- [ ] Desktop: cards trên 1 hàng
- [ ] Tablet: 3-4 cards
- [ ] Mobile: 1-2 cards, scrollable

**✅ Cross-machine:**
- [ ] Truy cập từ máy khác trong LAN
- [ ] Dashboard load được
- [ ] Login thành công
- [ ] Metrics update

---

### Automated Tests

```bash
cd llm-mw
python -m pytest tests/test_dashboard_improvements.py -v
```

**Coverage:**
- Auth enforcement (summary + stream)
- Auth methods (X-Admin-Key + cookie)
- Summary breakdown fields
- Math validation (llm_calls = sum)
- HTML labels

**Results:** 9/9 tests PASSED ✅

---

## 📈 Performance Considerations

### Frontend Optimization

**Polling interval:** 5 seconds
- Không quá frequent (save CPU)
- Update đủ nhanh cho realtime

**SSE stream:**
- Lightweight (chỉ gửi khi có event)
- No periodic keep-alive needed
- Browser auto-reconnect

**DOM updates:**
- Only update changed values
- No full re-render
- Smooth animations

### Backend Optimization

**Summary endpoint:**
- Scan audit.jsonl once
- In-memory aggregation
- No database queries

**Stream endpoint:**
- Async generator
- Push only when có event mới
- Auto-cleanup connections

**Audit log:**
- RotatingFileHandler (50MB max)
- 5 backup files
- Auto-rotate

---

## 🔐 Security Best Practices

### Production Checklist

**✅ Secrets:**
- [ ] Set strong `JWT_SECRET` (32+ chars)
- [ ] Set strong `ADMIN_KEY` (16+ chars)
- [ ] Store trong `.env`, không commit git
- [ ] Rotate keys định kỳ (6 months)

**✅ Network:**
- [ ] Enable HTTPS (Let's Encrypt)
- [ ] Set `secure=True` cho cookies
- [ ] Whitelist IPs nếu cần
- [ ] Rate limiting trên login endpoint

**✅ Monitoring:**
- [ ] Alert nếu error_rate > 5%
- [ ] Alert nếu pending_count > 100
- [ ] Log failed login attempts
- [ ] Monitor session creation rate

**✅ Compliance:**
- [ ] GDPR: Don't log PII
- [ ] Audit logs retention policy
- [ ] Backup audit.jsonl định kỳ

---

## 🎯 Feature Roadmap (Out of Scope)

**Không implement trong phase hiện tại:**
- ❌ Prometheus/Grafana integration
- ❌ Multi-admin với roles
- ❌ API key rotation UI
- ❌ Advanced alerting
- ❌ Database backend
- ❌ Historical charts
- ❌ Export to CSV/Excel

**Scope hiện tại:** Realtime monitoring + basic auth + metrics display

---

---

## 🔄 RECONCILE - Cơ Chế Đồng Bộ Chi Phí

### Reconcile Là Gì?

**Reconcile** là quá trình đồng bộ hóa usage data (tokens, cost) từ LiteLLM logs vào middleware khi streaming requests hoàn thành.

### Tại Sao Cần Reconcile?

**Vấn đề với Streaming:**
```
┌─────────────────────────────────────────────┐
│  Client  │  Middleware  │  LiteLLM         │
├──────────┼──────────────┼──────────────────┤
│  Start   →  Forward     →  Stream chunks   │
│  Stream  ←  Stream back ←  (ongoing...)     │
│          │              │                   │
│  [Middleware chưa biết total tokens/cost]  │
│  [Audit: status="pending", tokens=0]       │
│          │              │                   │
│  Done    │  Stream end  │  Write to log    │
│          │              │  (tokens, cost)  │
│          │              │                   │
│  [Cần reconcile để lấy tokens/cost thực]  │
└─────────────────────────────────────────────┘
```

**Vấn đề:**
- Streaming response không biết total tokens cho đến khi hoàn thành
- Middleware forward stream ngay → không đợi LiteLLM finish
- Audit log ghi `status="pending"` với `tokens=0, cost=0`
- LiteLLM ghi tokens/cost vào log riêng sau khi stream kết thúc

**Giải pháp: Reconcile**
- Admin xem pending requests trong dashboard
- Gọi reconcile endpoint với `request_id` + `user_id`
- Middleware đọc LiteLLM log → lấy tokens/cost thực
- Update user quota + ghi lại audit với `status="reconciled"`

---

### Flow Reconcile Chi Tiết

```
┌───────────────────────────────────────────────────────────┐
│  1. STREAMING REQUEST (Chat Completions)                  │
├───────────────────────────────────────────────────────────┤
│  POST /v1/chat/completions                                │
│  Body: {model: "gpt-4o", stream: true, ...}              │
│                                                           │
│  Middleware:                                              │
│  - Generate rid: "mw_abc123def456"                       │
│  - Write audit: status="pending", tokens=0               │
│  - Add to pending.csv: rid,user_id,timestamp             │
│  - Forward to LiteLLM with X-Request-ID                  │
│  - Stream response back to client                         │
│                                                           │
│  LiteLLM:                                                 │
│  - Stream chunks to client                                │
│  - Sau khi done: ghi vào litellm.log                     │
│    {request_id: "mw_abc123", tokens: 1234, cost: 0.012} │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│  2. ADMIN XEM PENDING (Dashboard)                         │
├───────────────────────────────────────────────────────────┤
│  GET /v1/_mw/summary?minutes=30                           │
│                                                           │
│  Response:                                                │
│  {                                                        │
│    "pending_count": 5,  ← Có 5 requests chưa reconcile  │
│    ...                                                    │
│  }                                                        │
│                                                           │
│  Dashboard hiển thị: "Pending: 5" (màu vàng warning)     │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│  3. ADMIN RECONCILE REQUEST                               │
├───────────────────────────────────────────────────────────┤
│  POST /admin/reconcile                                    │
│  Body: {                                                  │
│    "request_id": "mw_abc123def456",                      │
│    "user_id": "admin"                                     │
│  }                                                        │
│                                                           │
│  Middleware xử lý:                                        │
│                                                           │
│  Step 1: Check idempotent                                │
│  - Scan audit.jsonl tìm rid + status="reconciled"       │
│  - Nếu có → return "Already reconciled"                 │
│                                                           │
│  Step 2: Tìm usage trong LiteLLM log                     │
│  - Search litellm.log với request_id                     │
│  - Parse: prompt_tokens, completion_tokens, cost         │
│                                                           │
│  Step 3: Update user quota                               │
│  - Load users.json                                        │
│  - user["used_tokens"] += total_tokens                   │
│  - user["used_cost_usd"] += cost_usd                     │
│  - quota["used_tokens"] += total_tokens (period)         │
│  - quota["used_cost_usd"] += cost_usd (period)           │
│  - Save users.json                                        │
│                                                           │
│  Step 4: Remove from pending                             │
│  - Xóa dòng trong pending.csv                            │
│                                                           │
│  Step 5: Write reconciled audit                          │
│  - Ghi audit.jsonl với status="reconciled"              │
│  - Bao gồm tokens, cost đầy đủ                           │
│                                                           │
│  Return:                                                  │
│  {                                                        │
│    "ok": true,                                            │
│    "request_id": "mw_abc123def456",                      │
│    "total_tokens": 1234,                                  │
│    "cost_usd": 0.012340                                   │
│  }                                                        │
└───────────────────────────────────────────────────────────┘
```

---

### Pending.csv - Tracking File

**Location:** `llm-mw/data/pending.csv`

**Format:**
```csv
request_id,user_id,ts
mw_abc123def456,admin,2025-12-27T14:30:00+07:00
mw_def789ghi012,user1,2025-12-27T14:31:00+07:00
```

**Chức năng:**
- Track streaming requests chưa reconcile
- Cho phép bulk reconcile (loop through file)
- Cleanup sau khi reconcile thành công

**Khi nào thêm vào:**
- Chat completions với `stream=true`
- Khi middleware write audit với `status="pending"`

**Khi nào xóa:**
- Sau reconcile thành công
- Hoặc manual cleanup nếu request failed

---

### Idempotent Reconcile

**Vấn đề:** Nếu reconcile 2 lần → double-charge?

**Giải pháp: Idempotent Check**
```python
# Trước khi reconcile, check trong audit.jsonl
for line in audit.jsonl:
    entry = json.loads(line)
    if entry["rid"] == request_id and entry["status"] == "reconciled":
        return {"message": "Already reconciled"}

# Chỉ reconcile nếu chưa có entry "reconciled"
```

**Result:**
- Reconcile lần 1 → Update quota + write audit
- Reconcile lần 2 → Skip, return "Already reconciled"
- An toàn, không double-charge

---

### Khi Nào Cần Manual Reconcile?

**Scenarios:**
1. **Streaming requests** (chat completions với `stream=true`)
2. **Network issues** - Client disconnect nhưng LiteLLM vẫn xử lý
3. **Middleware restart** - Pending requests chưa kịp reconcile
4. **Cost audit** - Verify billing accuracy

**Không cần reconcile:**
- Non-streaming requests (đã có tokens/cost ngay)
- Image/audio requests (cost tính trước)
- Error requests (cost=0)

---

## 🛠️ OPERATIONS - Admin Endpoints

### Admin Operations Là Gì?

**Operations (Admin Ops)** là các thao tác quản trị hệ thống, không phải LLM calls.

### 3 Admin Endpoints Chính

#### 1. **GET /admin/usage** - Xem Usage Tất Cả Users

**Chức năng:**
- Hiển thị usage của tất cả users
- Scrub sensitive data (subkey, subkey_hash)
- Cho phép audit billing

**Request:**
```bash
curl http://localhost:5000/admin/usage \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

**Response:**
```json
[
  {
    "user_id": "admin",
    "active": true,
    "allowed_models": ["*"],
    "used_tokens": 135467,
    "used_cost_usd": 0.353453,
    "quota": {
      "period": "monthly",
      "timezone": "Asia/Bangkok",
      "limit_tokens": 0,
      "limit_cost_usd": 0,
      "period_start": 1764522000000,
      "used_tokens": 135467,
      "used_cost_usd": 0.353453,
      "used_image_requests": 1
    }
  },
  {
    "user_id": "user1",
    "active": true,
    "used_tokens": 0,
    "used_cost_usd": 0.0,
    ...
  }
]
```

**Use cases:**
- Billing report
- User activity audit
- Quota monitoring

---

#### 2. **POST /admin/reset** - Reset Quota

**Chức năng:**
- Reset period quota cho user hoặc tất cả users
- Chỉ reset quota["used_*"], giữ lifetime data

**Request (Reset 1 user):**
```bash
curl -X POST http://localhost:5000/admin/reset \
  -H "X-Admin-Key: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user1"}'
```

**Request (Reset ALL users):**
```bash
curl -X POST http://localhost:5000/admin/reset \
  -H "X-Admin-Key: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Response:**
```json
{
  "ok": true
}
```

**Behavior:**
```python
# Chỉ reset quota period data
quota["used_tokens"] = 0
quota["used_cost_usd"] = 0.0
quota["used_image_requests"] = 0

# KHÔNG reset lifetime data
user["used_tokens"]    # Giữ nguyên
user["used_cost_usd"]  # Giữ nguyên
```

**Use cases:**
- Manual quota reset giữa period
- Fix quota issues
- Testing

---

#### 3. **POST /admin/reconcile** - Reconcile Pending

**Đã giải thích chi tiết ở phần Reconcile trên.**

**Request:**
```bash
curl -X POST http://localhost:5000/admin/reconcile \
  -H "X-Admin-Key: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "mw_abc123def456",
    "user_id": "admin"
  }'
```

**Use cases:**
- Reconcile streaming requests
- Fix pending count
- Billing accuracy

---

### Dashboard Hiển Thị Admin Ops

**Metric Card:**
```
┌─────────────────┐
│ ADMIN OPS       │
│ 12              │
└─────────────────┘
```

**Tính từ audit.jsonl:**
```python
if endpoint in ["/admin/reconcile", "/admin/usage", "/admin/reset"]:
    admin_ops_total += 1
```

**Ý nghĩa:**
- Tách biệt admin operations khỏi LLM calls
- Tracking admin activity
- Admin ops không tốn cost

---

## 📝 LOGGING SYSTEM - Hệ Thống Ghi Log Chi Tiết

### Tổng Quan

Middleware có **6 loại logs** khác nhau, mỗi loại phục vụ mục đích riêng:

```
logs/
├── audit.jsonl              ← JSONL: Audit trail (billing, usage)
├── middleware.log           ← Text: General info (requests, errors)
├── middleware.requests.log  ← JSON: Detailed requests (debug)
├── middleware.stdout.log    ← Text: Console output
├── middleware.stderr.log    ← Text: Error output
├── litellm.log              ← Text: LiteLLM proxy logs
├── litellm.stdout.log
├── litellm.stderr.log
└── mw_media/                ← Folder: Uploaded media files
```

---

### 1. **audit.jsonl** - Audit Trail (Quan Trọng Nhất)

**Purpose:** Ghi lại toàn bộ requests để audit, billing, analytics

**Format:** JSONL (JSON Lines) - mỗi dòng là 1 JSON object

**Location:** `logs/audit.jsonl`

**File size:** Max 50MB (auto-rotate, giữ 5 backups)

**Sample Entry:**
```json
{
  "ts": "2025-12-27T15:23:45.123456+07:00",
  "rid": "mw_843ef9b738434b42",
  "user_id": "admin",
  "endpoint": "/v1/chat/completions",
  "model": "gemini-2.5-flash",
  "status": "ok",
  "status_code": 200,
  "latency_ms": 1234.5,
  "tokens_in": 100,
  "tokens_out": 200,
  "tokens_total": 300,
  "cost_usd": 0.012340,
  "image_count": null,
  "tts_chars": null,
  "stt_seconds": null,
  "video_count": null,
  "error_type": null,
  "error_message": null
}
```

**Fields Chi Tiết:**

| STT | Field           | Type        | Mô tả                                  | Ví dụ                                  |
| --- | --------------- | ----------- | -------------------------------------- | -------------------------------------- |
| 01  | `ts`            | string      | Timestamp (ISO 8601, Asia/Ho_Chi_Minh) | `2025-12-27T15:23:45+07:00`            |
| 02  | `rid`           | string      | Request ID (unique)                    | `mw_843ef9b738434b42`                  |
| 03  | `user_id`       | string      | User identifier                        | `admin`, `user1`                       |
| 04  | `endpoint`      | string      | API endpoint path                      | `/v1/chat/completions`                 |
| 05  | `model`         | string/null | LLM model name                         | `gpt-4o-mini`, `gemini-2.5-flash`      |
| 06  | `status`        | string      | Request status                         | `ok`, `error`, `pending`, `reconciled` |
| 07  | `status_code`   | int         | HTTP status code                       | 200, 403, 500                          |
| 08  | `latency_ms`    | float/null  | Response time (milliseconds)           | 1234.5                                 |
| 09  | `tokens_in`     | int         | Input/prompt tokens                    | 100                                    |
| 10  | `tokens_out`    | int         | Output/completion tokens               | 200                                    |
| 11  | `tokens_total`  | int         | Total tokens (in + out)                | 300                                    |
| 12  | `cost_usd`      | float       | Cost in USD (6 decimals)               | 0.012340                               |
| 13  | `image_count`   | int/null    | Image generation requests              | 1, null                                |
| 14  | `tts_chars`     | int/null    | Text-to-speech characters              | 150, null                              |
| 15  | `stt_seconds`   | float/null  | Speech-to-text duration                | 30.5, null                             |
| 16  | `video_count`   | int/null    | Video generation requests              | 1, null                                |
| 17  | `error_type`    | string/null | Error category                         | `auth`, `quota`, `provider`, `system`  |
| 18  | `error_message` | string/null | Error message (truncated 500 chars)    | `Invalid API key`                      |

**Status Values:**
- `ok` - Request thành công
- `error` - Request lỗi (4xx/5xx)
- `pending` - Streaming chưa hoàn thành
- `reconciled` - Đã reconcile từ LiteLLM logs

**Use Cases:**
- **Billing**: Aggregate cost_usd by user_id
- **Usage analytics**: Count by model, endpoint
- **Error tracking**: Filter status="error"
- **Performance**: Analyze latency_ms (P95, P99)
- **Audit**: Compliance, security review
- **Reconcile**: Find pending requests

**Query Examples:**
```bash
# Total cost của admin trong 30 phút
jq -r 'select(.user_id=="admin" and .status!="pending") | .cost_usd' audit.jsonl | awk '{sum+=$1} END {print sum}'

# Top 10 slowest requests
jq -r '[.rid, .latency_ms, .model] | @tsv' audit.jsonl | sort -k2 -rn | head -10

# Error rate
total=$(wc -l < audit.jsonl)
errors=$(grep '"status":"error"' audit.jsonl | wc -l)
echo "scale=2; $errors * 100 / $total" | bc
```

---

### 2. **middleware.log** - General Application Log

**Purpose:** General info, warnings, errors

**Format:** Plain text với timestamp

**Location:** `logs/middleware.log`

**File size:** Max 5MB (auto-rotate, 5 backups)

**Sample Entries:**
```
2025-12-27 14:28:37,491 INFO startup: http_client created
2025-12-27 14:28:52,391 INFO req rid=- method=GET path=/v1/models status=200 ms=16.9
2025-12-27 14:32:58,744 INFO req rid=- method=GET path=/v1/_mw/summary status=200 ms=7.4
2025-12-27 14:35:12,123 WARNING JWT_SECRET is using default value - CHANGE IN PRODUCTION!
2025-12-27 14:36:00,000 ERROR Failed to load users.json: [Errno 2] No such file
```

**Log Levels:**
- `INFO` - Normal operations (request, startup)
- `WARNING` - Security warnings, config issues
- `ERROR` - Errors (file not found, etc.)

**Use Cases:**
- Debug application issues
- Monitor startup/shutdown
- Security audit (warnings)
- General troubleshooting

---

### 3. **middleware.requests.log** - Detailed Request Log

**Purpose:** Chi tiết inbound/outbound requests để debug

**Format:** JSON (1 line per event)

**Location:** `logs/middleware.requests.log`

**File size:** Max 20MB (auto-rotate, 5 backups)

**Sample Entries:**
```json
{"ts": "2025-12-27T14:33:28.726441+07:00", "event": "inbound", "method": "GET", "path": "/v1/_mw/summary", "client": "192.168.154.51"}
{"ts": "2025-12-27T14:33:28.729398+07:00", "event": "outbound", "method": "GET", "path": "/v1/_mw/summary", "client": "192.168.154.51", "status": 200, "ms": 2.7}
```

**Fields:**
- `ts` - Timestamp
- `event` - `inbound` (request in) hoặc `outbound` (response out)
- `method` - HTTP method (GET, POST)
- `path` - Request path
- `client` - Client IP
- `status` - HTTP status (outbound only)
- `ms` - Duration (outbound only)

**Use Cases:**
- Debug specific requests
- Network troubleshooting
- Performance profiling
- Client IP tracking

**Enable/Disable:**
```bash
# Trong .env
MW_DETAILED_LOG=true   # Enable (default)
MW_DETAILED_LOG=false  # Disable
```

---

### 4. **users.json** - User Data & Quota

**Purpose:** Lưu user credentials, quota, usage

**Format:** JSON array

**Location:** `llm-mw/data/users.json`

**Sample:**
```json
[
  {
    "user_id": "admin",
    "subkey": "YOUR_SUBKEY_ADMIN",
    "subkey_hash": "7e897aa34d3d75e54eb74797aaba6e9e...",
    "active": true,
    "allowed_models": ["*"],
    "used_tokens": 135467,
    "used_cost_usd": 0.353453,
    "quota": {
      "period": "monthly",
      "timezone": "Asia/Bangkok",
      "limit_tokens": 0,
      "limit_cost_usd": 0,
      "period_start": 1764522000000,
      "used_tokens": 135467,
      "used_cost_usd": 0.353453,
      "used_image_requests": 1
    }
  }
]
```

**Fields:**
- `user_id` - Unique identifier
- `subkey` - Plaintext API key (hashed on load)
- `subkey_hash` - HMAC-SHA256 hash
- `active` - Enabled/disabled
- `allowed_models` - Whitelist (`["*"]` = all)
- `used_tokens` - **Lifetime total** tokens
- `used_cost_usd` - **Lifetime total** cost
- `quota` - Period-based quota object
  - `period` - `"weekly"` hoặc `"monthly"`
  - `timezone` - Timezone for period calculation
  - `limit_tokens` - Max tokens per period (0 = unlimited)
  - `limit_cost_usd` - Max cost per period (0 = unlimited)
  - `period_start` - Period start timestamp (ms)
  - `used_tokens` - **Period** tokens (reset khi qua period)
  - `used_cost_usd` - **Period** cost (reset khi qua period)

**Auto-Update:**
- Sau mỗi request thành công → update `used_tokens`, `used_cost_usd`
- Khi qua period boundary → reset `quota.used_*`
- Reconcile → update cả lifetime và period

**Security:**
- File chứa plaintext subkeys → **KHÔNG commit git**
- Hashed khi load vào memory
- Admin API scrub `subkey` và `subkey_hash` trước return

---

### 5. **prices.json** - Model Pricing Data

**Purpose:** Pricing table cho tính cost

**Format:** JSON object

**Location:** `llm-mw/data/prices.json`

**Sample:**
```json
{
  "gpt-4o": {
    "input": 0.00001,
    "output": 0.00003
  },
  "gpt-4o-mini": {
    "input": 0.00000015,
    "output": 0.0000006
  },
  "gemini-2.5-flash": {
    "input": 0.0000001,
    "output": 0.0000004
  }
}
```

**Format:**
- Key: Model name
- Value: `{input: $/token, output: $/token}`

**Usage:**
```python
cost_usd = (prompt_tokens * prices[model]["input"]) + \
           (completion_tokens * prices[model]["output"])
```

**Fallback:**
- Nếu model không có trong prices → cost = 0
- LiteLLM trả cost trong header → dùng đó thay vì tính

---

### 6. **pending.csv** - Pending Requests Tracker

**Đã giải thích ở phần Reconcile.**

---

### Logging Flow - Từ Request → Log Files

```
┌───────────────────────────────────────────────┐
│  1. REQUEST ARRIVES                           │
├───────────────────────────────────────────────┤
│  POST /v1/chat/completions                    │
│  Authorization: Bearer YOUR_SUBKEY_ADMIN       │
│                                               │
│  Middleware:                                  │
│  - Authenticate user                          │
│  - Generate rid: "mw_abc123"                  │
│  - init_audit_state(request, user, endpoint)│
│                                               │
│  Log: middleware.requests.log                 │
│  {"event": "inbound", "path": "/v1/chat/..."}│
└───────────────────────────────────────────────┘

┌───────────────────────────────────────────────┐
│  2. PROCESS REQUEST                           │
├───────────────────────────────────────────────┤
│  Endpoint (chat.py):                          │
│  - Forward to LiteLLM                         │
│  - Get response                               │
│  - set_usage_state(tokens_in, tokens_out)    │
│  - set_counters(cost_usd)                    │
│                                               │
│  Log: middleware.requests.log                 │
│  {"event": "upstream.request", "body": ...}   │
│  {"event": "upstream.response", "data": ...}  │
└───────────────────────────────────────────────┘

┌───────────────────────────────────────────────┐
│  3. UPDATE QUOTA                              │
├───────────────────────────────────────────────┤
│  enforce_and_bump_quota():                    │
│  - Check quota limits                         │
│  - Update user["used_tokens"]                 │
│  - Update quota["used_tokens"]                │
│  - Save users.json                            │
│                                               │
│  Log: middleware.log                          │
│  INFO req rid=mw_abc123 method=POST ...       │
└───────────────────────────────────────────────┘

┌───────────────────────────────────────────────┐
│  4. RESPONSE SENT (Middleware)                │
├───────────────────────────────────────────────┤
│  Middleware (after endpoint returns):         │
│  - Calculate latency                          │
│  - Collect audit state from request.state    │
│  - audit_from_request()                       │
│                                               │
│  Log: audit.jsonl                             │
│  {"ts": "...", "rid": "mw_abc123",           │
│   "status": "ok", "tokens_total": 300,       │
│   "cost_usd": 0.012340, ...}                 │
│                                               │
│  Log: middleware.requests.log                 │
│  {"event": "outbound", "status": 200, ...}    │
└───────────────────────────────────────────────┘
```

---

### Log Rotation & Retention

**Auto-Rotation:**
```python
from logging.handlers import RotatingFileHandler

# audit.jsonl: 50MB max, 5 backups
RotatingFileHandler(AUDIT_LOG_FILE, 
    maxBytes=50_000_000, 
    backupCount=5)

# middleware.log: 5MB max, 5 backups
RotatingFileHandler(MW_LOG_FILE, 
    maxBytes=5_000_000, 
    backupCount=5)

# middleware.requests.log: 20MB max, 5 backups
RotatingFileHandler(MW_DETAIL_LOG_FILE, 
    maxBytes=20_000_000, 
    backupCount=5)
```

**Backup Files:**
```
audit.jsonl          ← Current
audit.jsonl.1        ← Previous (oldest in use)
audit.jsonl.2
audit.jsonl.3
audit.jsonl.4
audit.jsonl.5        ← Oldest backup
```

**Retention:**
- 6 files total (current + 5 backups)
- audit.jsonl: 50MB × 6 = **300MB max**
- middleware.log: 5MB × 6 = **30MB max**
- requests.log: 20MB × 6 = **120MB max**

**Manual Cleanup:**
```bash
# Archive old logs
cd logs
tar -czf audit_backup_$(date +%Y%m%d).tar.gz audit.jsonl.*
rm audit.jsonl.*

# Or rotate manually
mv audit.jsonl audit.jsonl.old
touch audit.jsonl
```

---

### Logging Best Practices

**✅ Do's:**
- Use audit.jsonl for billing/analytics
- Monitor file sizes (rotation thresholds)
- Backup audit.jsonl định kỳ (billing evidence)
- Filter sensitive data (passwords, full API keys)
- Use structured logging (JSON) cho machine parsing

**❌ Don'ts:**
- Không log plaintext passwords
- Không log full API keys (chỉ last 4 chars)
- Không log PII nếu GDPR applies
- Không disable audit logging (billing requirement)
- Không commit logs vào git

**Security:**
```python
# Auto-redact sensitive fields
SENSITIVE_KEYS = {
    "authorization", "api_key", "apikey", "secret",
    "password", "token", "bearer"
}

def redact(data):
    # Redact sensitive values trong logs
    # "Authorization: sk-abc123..." → "Authorization: sk-***123"
```

---

## ✅ Changes Implemented

### 1. **Enforce Auth cho Admin Endpoints** (BẮT BUỘC)

**Endpoints được bảo vệ:**
- `GET /v1/_mw/summary` - Aggregate usage statistics
- `GET /v1/_mw/stream` - SSE realtime audit stream

**Phương thức authentication cho phép:**
- ✅ **Cookie session** (`mw_admin_session`) - cho dashboard
- ✅ **X-Admin-Key header** - cho curl/ops
- ✅ **Authorization: Bearer** - backward compatibility

**Cách login dashboard:**
```bash
# 1. Call login endpoint (chỉ 1 lần)
POST /v1/_mw/dashboard/login
Body: {"admin_key": "YOUR_ADMIN_KEY"}

# 2. Cookie được set tự động (4 giờ expiry)
# 3. Tất cả requests sau dùng cookie, không cần key trong JS/URL
```

**Cách dùng curl/ops:**
```bash
# X-Admin-Key header (khuyến nghị)
curl http://localhost:5000/v1/_mw/summary?minutes=30 \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"

# Hoặc Authorization Bearer (backward compat)
curl http://localhost:5000/v1/_mw/summary?minutes=30 \
  -H "Authorization: Bearer YOUR_ADMIN_KEY"
```

**Bảo mật:**
- ❌ KHÔNG cho phép `?key=` trong URL
- ✅ Cookie HttpOnly (prevent XSS)
- ✅ JWT_SECRET không dùng default (log warning nếu thiếu)
- ✅ Session expiry 4 giờ

---

### 2. **Sửa logic Summary - Tách loại request**

**Endpoint:** `GET /v1/_mw/summary?minutes=<N>`

**Response mới có thêm breakdown:**

```json
{
  "time_window_minutes": 30,
  
  // Overall counts
  "requests_total": 10,       // Tổng requests (ok + error + reconciled)
  "llm_calls_total": 8,       // Chỉ LLM endpoints (chat/image/audio/video)
  "admin_ops_total": 1,       // Admin operations (reconcile, etc)
  "pending_count": 2,         // Streaming chưa reconcile
  "error_count": 0,
  
  // LLM breakdown
  "chat_calls": 6,            // /v1/chat/completions
  "image_calls": 1,           // /v1/images/generations
  "audio_calls": 1,           // /v1/audio/transcriptions + speech
  "video_calls": 0,           // /v1/video/generations
  
  // Performance
  "error_rate_percent": 0.0,
  "p95_latency_ms": 1234.56,
  "tokens_total": 15000,      // Chỉ từ ok + reconciled
  "cost_total_usd": 0.0225,   // Chỉ từ ok + reconciled
  
  // Top lists
  "top_users": [...],
  "top_models": [...]
}
```

**Quy tắc tính toán:**

- **`llm_calls_total`**: Đếm endpoint thuộc:
  - `/v1/chat/completions`
  - `/v1/images/generations`
  - `/v1/audio/transcriptions`
  - `/v1/audio/speech`
  - `/v1/video/generations`
  - Chỉ status `ok`, `error`, `reconciled` (KHÔNG pending)

- **`admin_ops_total`**: Đếm:
  - `/admin/reconcile`
  - `/admin/usage`
  - `/admin/reset`

- **`pending_count`**: Đếm status `pending` (streaming chưa reconcile)

- **`tokens_total` & `cost_total_usd`**: 
  - ✅ Chỉ cộng từ status `ok` + `reconciled`
  - ❌ KHÔNG cộng từ `pending` (chưa biết tokens)
  - ❌ KHÔNG cộng từ `error` (cost = 0)

- **Breakdown chi tiết**:
  - `chat_calls` = đếm `/v1/chat/completions` (ok/error/reconciled only)
  - `image_calls` = đếm `/v1/images/generations`
  - `audio_calls` = đếm `/v1/audio/*`
  - `video_calls` = đếm `/v1/video/generations`

---

### 3. **Sửa Dashboard UI**

**URL dashboard:** http://localhost:5000/dashboard

**Metrics hiển thị (6 chỉ số chính):**

| STT | Label           | Nguồn                | Ý nghĩa                                     |
| --- | --------------- | -------------------- | ------------------------------------------- |
| 01  | **LLM Calls**   | `llm_calls_total`    | Tổng calls đến LLM (chat/image/audio/video) |
| 02  | **Admin Ops**   | `admin_ops_total`    | Operations quản trị (reconcile, etc)        |
| 03  | **Pending**     | `pending_count`      | Streaming chưa reconcile                    |
| 04  | **Error Rate**  | `error_rate_percent` | % request lỗi                               |
| 05  | **P95 Latency** | `p95_latency_ms`     | Latency phân vị 95                          |
| 06  | **Tokens**      | `tokens_total`       | Tổng tokens (ok + reconciled)               |
| 07  | **Cost**        | `cost_total_usd`     | Tổng cost USD                               |

**Breakdown LLM Calls:**
- Hiển thị: `Chat: X | Image: Y | Audio: Z`

**Polling:**
- Gọi `/v1/_mw/summary?minutes=15` mỗi 5 giây
- Hiển thị Top Users và Top Models

**SSE Stream:**
- Kết nối `/v1/_mw/stream` với cookie
- Hiển thị 50 events gần nhất

---

### 4. **Idempotent Reconcile** (ĐÃ CÓ TRƯỚC)

Đã implement từ trước:
- Reconcile cùng `rid` 2 lần → lần 2 trả "Already reconciled"
- Không double-charge quota
- Không ghi audit line thứ 2

---

## 📊 Ý nghĩa các chỉ số

### Phân biệt các loại request

**LLM Calls** (`llm_calls_total`):
- Là requests thực sự gọi đến LLM model
- Chat, Image, Audio, Video generation
- Đây là metrics chính để track usage

**Admin Ops** (`admin_ops_total`):
- Operations quản trị hệ thống
- Reconcile pending streams
- Get usage, reset quota
- KHÔNG phải LLM calls

**Pending** (`pending_count`):
- Streaming requests chưa được reconcile
- Chưa biết tokens/cost chính xác
- Cần reconcile để có data đầy đủ

**Total Requests** (`requests_total`):
- Tổng tất cả (LLM + Admin + ...)
- Có thể gây hiểu nhầm nên ẨN trong UI
- Chỉ hiện `llm_calls_total` để rõ ràng

---

## 🧪 Testing

### Run automated tests:

```bash
cd llm-mw
python -m pytest tests/test_dashboard_improvements.py -v
```

**Test coverage:**
- ✅ Auth enforcement (summary + stream require auth)
- ✅ Auth methods work (X-Admin-Key + cookie session)
- ✅ Summary breakdown fields exist
- ✅ LLM calls = sum of breakdown
- ✅ Dashboard HTML có labels mới

**Results:** 9/9 tests PASSED

### Manual testing:

#### 1. Test Auth Protection

```bash
# Should return 403
curl http://localhost:5000/v1/_mw/summary

# Should return 200
curl http://localhost:5000/v1/_mw/summary \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

#### 2. Test Summary Breakdown

```bash
curl http://localhost:5000/v1/_mw/summary?minutes=30 \
  -H "X-Admin-Key: YOUR_ADMIN_KEY" | jq
```

Verify response có:
- `llm_calls_total`
- `admin_ops_total`
- `pending_count`
- `chat_calls`, `image_calls`, `audio_calls`, `video_calls`

#### 3. Test Dashboard UI

1. Mở: http://localhost:5000/dashboard
2. Login với admin key: `YOUR_ADMIN_KEY`
3. Verify:
   - Có label "LLM Calls" (không phải "Total Requests")
   - Có label "Admin Ops"
   - Có label "Pending"
   - Breakdown hiển thị: Chat/Image/Audio
   - Metrics update mỗi 5s

---

## 🔧 Configuration

### Environment Variables

```bash
# Required
ADMIN_KEY=your-strong-admin-key-here        # Admin authentication
JWT_SECRET=your-strong-jwt-secret-here      # Session signing (32+ chars)

# Optional (có defaults)
AUDIT_LOG_FILE=../logs/audit.jsonl
```

⚠️ **Production notes:**
- Đặt `JWT_SECRET` mạnh (32+ ký tự random)
- Đổi `ADMIN_KEY` định kỳ
- Enable HTTPS và set `secure=True` cho cookies

---

## 📝 Summary of Changes

### Files Modified:

1. **`api/summary.py`** - Added breakdown logic
   - Added LLM_ENDPOINTS mapping
   - Added counters: `llm_calls_total`, `admin_ops_total`, breakdown
   - Modified aggregation logic to classify by endpoint
   - Added breakdown fields to response

2. **`dashboard/index.html`** - Updated UI labels
   - Changed "Total Requests" → "LLM Calls"
   - Added "Admin Ops" metric card
   - Added breakdown display (Chat/Image/Audio)
   - Updated metric IDs and display logic

### Files Created:

3. **`tests/test_dashboard_improvements.py`** - Comprehensive tests
   - TestAuth: 4 tests (auth enforcement + methods)
   - TestSummaryBreakdown: 3 tests (fields + math)
   - TestDashboardUI: 2 tests (HTML + labels)

### Files Already OK (No changes needed):

- ✅ `utils/auth_guard.py` - Auth already implemented
- ✅ `api/stream.py` - Auth already enforced
- ✅ `api/admin.py` - Idempotent reconcile already done
- ✅ `utils/jwt_auth.py` - JWT utilities already complete

---

## 🎯 Verification Checklist

- [x] Summary endpoint requires auth (403 without key)
- [x] Stream endpoint requires auth (403 without key)
- [x] X-Admin-Key header works
- [x] Cookie session works (dashboard login)
- [x] Summary returns breakdown fields
- [x] `llm_calls_total` = sum of breakdown
- [x] Pending không cộng vào llm_calls_total
- [x] Tokens/cost chỉ từ ok + reconciled
- [x] Dashboard shows "LLM Calls" label
- [x] Dashboard shows "Admin Ops" label
- [x] Dashboard shows breakdown (Chat/Image/Audio)
- [x] All tests pass (9/9)

---

## 🚀 Next Steps (Out of Scope)

Những gì KHÔNG làm trong bước này (theo yêu cầu):
- ❌ Prometheus/Grafana integration
- ❌ Create/rotate admin key API
- ❌ Multi-user với roles khác nhau
- ❌ Advanced alerting
- ❌ Database backend

Scope hiện tại: **Chỉ sửa metrics + auth + UI labels**

---

## 📚 API Reference

### GET /v1/_mw/summary

**Auth:** Required (X-Admin-Key or cookie)

**Query params:**
- `minutes` (optional, default=60): Time window

**Response:**
```json
{
  "time_window_minutes": 30,
  "cutoff_time": "2025-12-20T15:00:00+07:00",
  "requests_total": 10,
  "llm_calls_total": 8,
  "admin_ops_total": 1,
  "pending_count": 2,
  "error_count": 0,
  "error_rate_percent": 0.0,
  "chat_calls": 6,
  "image_calls": 1,
  "audio_calls": 1,
  "video_calls": 0,
  "p95_latency_ms": 1234.56,
  "tokens_total": 15000,
  "cost_total_usd": 0.0225,
  "top_users": [...],
  "top_models": [...]
}
```

### GET /v1/_mw/stream

**Auth:** Required (X-Admin-Key or cookie)

**Response:** SSE stream
```
event: audit
data: {"ts":"...","rid":"...","status":"ok",...}

event: audit
data: {"ts":"...","rid":"...","status":"pending",...}
```

### POST /v1/_mw/dashboard/login

**Auth:** None (public login endpoint)

**Body:**
```json
{"admin_key": "YOUR_ADMIN_KEY"}
```

**Response:**
```json
{"ok": true, "expires_in_hours": 4}
```

**Sets cookie:** `mw_admin_session` (HttpOnly, 4h expiry)

---

**Document Version:** 1.0  
**Last Updated:** 2025-12-20  
**Status:** ✅ Production Ready
