## Context

Dashboard hiện có 10 tabs (Usage, Access, Users, Logs, RAG Health, Groups, Chat Analytics, Satisfaction, Prices, Settings) với dữ liệu từ 2 databases:
- **MW DB**: `mw_audit_log`, `mw_users`, `mw_prices`, `mw_pending`
- **OW DB**: `chat`, `message`, `feedback`, `group`, `group_member`, `user` (qua read-only pool, Option A đã implement)

Export hiện tại chỉ có `logs.js:exportLogsToExcel()` — CSV client-side, chỉ export page hiện tại của audit log (max 50 rows), 8 cột cơ bản.

Các API data đã sẵn sàng:
- `summary.py` / `summary_v2.py` → aggregated usage metrics
- `analytics.py` → chat analytics + satisfaction analytics (query OW DB)
- `group_analytics.py` → group-level breakdown (query OW DB)
- `audit_query.py` → audit log with filters

## Goals / Non-Goals

**Goals:**
- 1 nút "📥 Export Report" trên dashboard header → 1 file chứa toàn bộ thông tin
- Hỗ trợ Excel (.xlsx) multi-sheet: Summary, Users, Models, Groups, Chat Analytics, Satisfaction, Raw Audit
- Hỗ trợ CSV: export raw audit log dạng streaming (cho nhu cầu import data)
- Time range theo dashboard time filter đang chọn
- Admin-only access (dùng `require_admin_or_session` hiện có)

**Non-Goals:**
- PDF generation — không cần cho internal tool
- Scheduled email reports — chưa cần, admin tải thủ công
- End-user self-service export — chỉ admin
- Per-tab export buttons — dùng 1 nút global duy nhất
- Thay thế export CSV hiện có ở Logs tab — giữ nguyên

## Decisions

### 1. Server-side generation (openpyxl) thay vì client-side

**Chọn**: Server-side Python generate file → browser download

**Lý do**: Client-side JS không thể tạo Excel multi-sheet có formatting. Server-side cho phép:
- openpyxl tạo .xlsx với headers styled, auto-width columns, freeze panes
- Aggregate data từ cả MW + OW DB trong 1 request
- Streaming CSV cho large audit log exports

**Thay thế đã xét**: Client-side SheetJS (xlsx) — tăng bundle size frontend, không truy cập DB trực tiếp, formatting hạn chế.

### 2. Single endpoint cho cả Excel và CSV

**Chọn**: `GET /v1/_mw/export/report?format=xlsx|csv&start=...&end=...`

**Lý do**: Cùng auth flow, cùng time range parsing. Format chỉ thay đổi serialization layer. Giữ API surface nhỏ.

### 3. Direct response (không background job)

**Chọn**: Trả file trực tiếp trong HTTP response

**Lý do**: Với 200 users, audit log ~4,000 records/ngày, export 1 tháng ≈ 120K rows. openpyxl xử lý 120K rows trong ~3-5 giây. CSV streaming không cần buffer toàn bộ.

Nếu sau này scale lên, có thể chuyển sang background job + download link mà không thay đổi frontend.

### 4. Reuse existing query logic, không duplicate

**Chọn**: Import và gọi lại các function từ `summary.py`, `analytics.py`, `group_analytics.py`

**Lý do**: Tránh duplicate SQL queries. Các function đã handle edge cases, timezone, fallbacks. Export chỉ là layer format khác (Excel thay vì JSON).

**Trade-off**: Một số function nhận `Request` object → cần refactor nhẹ để tách logic query ra khỏi HTTP handler, hoặc construct mock request.

### 5. Excel sheet structure

**Chọn**: 7 sheets cố định

| Sheet | Data Source | Rows ước tính |
|-------|------------|--------------|
| Tổng quan | summary aggregation | ~15 rows |
| Top Users | mw_audit_log GROUP BY user_id | ≤200 rows |
| Top Models | mw_audit_log GROUP BY model | ~20 rows |
| Phòng ban | group_analytics | ~10-20 rows |
| Chat Analytics | OW chat + message | ~200 rows |
| Satisfaction | OW feedback | ≤100 rows |
| Audit Log | mw_audit_log full | ≤50,000 rows (capped) |

## Risks / Trade-offs

- **[openpyxl memory cho large sheets]** → Audit Log sheet capped 50,000 rows. Với ~800 bytes/row = ~40MB memory peak. Acceptable cho server 2GB.
  → Mitigation: Cap rows, sort by timestamp DESC (mới nhất trước)

- **[Request timeout cho large exports]** → Excel generation 120K rows ≈ 3-5 giây. Nginx default timeout 60s là đủ.
  → Mitigation: Set `Content-Type` header early để browser không timeout. Thêm progress comment nếu cần.

- **[OW DB schema change]** → Export queries OW tables (chat, feedback, group). Nếu OW upgrade đổi schema, export sẽ fail.
  → Mitigation: Wrap OW queries trong try/except, gracefully skip sheet nếu fail. `check_ow_schema()` đã có tại startup.

- **[Concurrent exports]** → Nhiều admin export cùng lúc có thể dùng nhiều DB connections.
  → Mitigation: Pool đã có max=10, mỗi export dùng 2 connections (MW + OW) trong ~5s. Với 1-2 admin thực tế, không phải vấn đề.
