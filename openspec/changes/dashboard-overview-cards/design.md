## Context

Phase 1 của kế hoạch chỉ tiêu dashboard (`docs/dashboard_metrics_implementation_plan.md`). Mục tiêu: dựng tab Overview cấp lãnh đạo để leader thấy hình dạng thật sớm, cộng vài thẻ inventory ở tab Users. Đã đối chiếu trực tiếp với code thật (`docs/dashboard_frontend_harvest.md`):

- Frontend dashboard theo pattern module: mỗi tab có JS riêng, import trong `main.js`, gắn `window.<name>API`, chuyển tab qua `tabs.js:switchTab` (`window.dashboardAPI.switchTab(event, name)`), panel `id="<name>Tab"`.
- `usage.js` giữ response summary global-range trong biến private `_lastSummaryData` (`usage.js:8`), đã export `refreshTables` dùng nó — chỉ cần export thêm accessor.
- `summary_v2.py` gom `user_data` theo user rồi sort `breakdown_by_user` theo cost (`:383`) và cắt `[:20]` (`:451`). P95 dựng từ `all_latencies.sort()` (`:345-353`). Endpoint nhận `start/end` hoặc `minutes` (`:127-152`).
- CSAT sẵn ở `get_satisfaction_analytics.totals.csat_percent` (`analytics.py:207`).
- Tab bar thật có 11 tab gồm `📚 Knowledge` (`index.html:104`) — prototype thiếu Knowledge, KHÔNG áp danh sách prototype.
- Badge Users: `totalUserCount`=`users.length`, `activeUserCount`=`filter(active!==false)` (`users.js:29-32`).

Ba quyết định phạm vi đã chốt với leader: (1) Total Models + tab Providers dời Phase 6; (2) badge chỉ Việt hóa, giữ nghĩa non-disabled; (3) thẻ Overview theo range global, riêng Cost MTD cố định tháng. Thẻ Total Users được giữ theo yêu cầu leader ([[total-users-card-keep]]).

## Goals / Non-Goals

**Goals:**
- Tab Overview với 6 thẻ (4 số thật + 2 placeholder) theo đúng convention frontend hiện có.
- Backend chỉ thêm 1 chỉ tiêu: `top10_pct_cost_share` trong `totals`, tính trên toàn population.
- Tối đa tái sử dụng: không endpoint mới, không fetch trùng, không copy khối HTML/CSS/JS của prototype.
- Bổ sung tab Users: thẻ Total Users, badge Việt hóa.

**Non-Goals:**
- Tab Providers và thẻ Total Models (Phase 6).
- Logic adoption/active-by-usage và Cost/active user (Phase 4) — chỉ để placeholder.
- Chuỗi DAU + đường tham chiếu "tổng đã cấp" (Phase 4 — tab Users chưa có DAU chart, chuỗi DAU cần field backend mới).
- Uptime/health endpoint (`/health`) — dòng uptime để trống tới Phase 10.
- Hạ tầng so sánh kỳ CK/KT (Phase 2) — không thêm `.delta-badge` ở phase này.
- Đổi id/tên biến JS hiện có; áp `Chart.defaults` global.

## Decisions

### D1 — Concentration tính server-side trước khi cắt `[:20]`
Thêm khối tính top-10% cost share ngay sau khi có `total_cost` và trước dòng `breakdown_by_user[:20]`, đọc thẳng `user_data` (đã gom, `:269`). Bổ sung vào `totals` dưới key `top10_pct_cost_share`.
- **Vì sao:** con số phải phản ánh toàn bộ user; suy từ list 20 dòng ở frontend sẽ sai. Cùng con số này Phase 4 (Pareto) sẽ reuse — tính 1 lần.
- **Thuật toán:** sort cost giảm dần → lấy `k = ceil(n * 0.10)` (tối thiểu 1 khi n>0) → `sum(top_k_cost) / total_cost * 100`. Trường hợp biên: n=0 hoặc total_cost=0 → 0; 1 user có cost → 100.
- **Loại bỏ:** thêm endpoint riêng cho concentration (thừa, cùng dữ liệu summary).

### D2 — Reuse summary qua accessor thay vì fetch trùng
Export `getLastSummary()` từ `usage.js` trả `_lastSummaryData`. Overview đọc nó cho thẻ Health (error rate + P95) và Concentration.
- **Vì sao:** `loadSummary` chạy sẵn định kỳ 15s (`main.js:134`) cho global range; Overview dùng lại tránh gọi API 2 lần cùng range.
- **Cost MTD** không nằm trong range global nên phải fetch riêng `summary_v2?start=<đầu tháng>&end=<now>`.
- **CSAT** gọi `get_satisfaction_analytics` (range global) — thẻ CSAT ở Overview và tab Satisfaction cùng nguồn.
- **Loại bỏ:** đẩy toàn bộ số Overview vào 1 endpoint tổng hợp mới — trái nguyên tắc reuse, đẻ code trùng.

### D3 — Overview là module tab mới đúng convention
Tạo `js/overview.js` export hàm load + render; import vào `main.js`; gắn `window.overviewAPI`; thêm case `overview` trong `tabs.js:switchTab` để gọi load khi mở tab; thêm nút tab + panel `overviewTab` trong `index.html` cạnh Usage.
- **Vì sao:** khớp mẫu `raghealth`/`groupAnalytics`/`knowledge`; không phá bootstrap `<script>` cuối `index.html`.
- **Loại bỏ:** copy `section.panel`/`data-tab`/`activate()` của prototype (hệ DOM khác, sẽ lệch).

### D4 — Badge chỉ đổi chữ, giữ số
Sửa text render badge trong `users.js` sang `Đang bật: X · Tổng: Y`; `X`,`Y` giữ đúng công thức cũ.
- **Vì sao:** `X` là non-disabled, KHÔNG phải "đã dùng". Đổi nhãn thành "đã dùng" sẽ tái tạo đúng lỗi mislabel `Total Requests` mà Phase 0 đang sửa. Con số "đã dùng" thật cần logic adoption của Phase 4.

### D5 — DAU reference line: HOÃN sang Phase 4
Khi implement, grep xác nhận tab Users **không có DAU chart** nào (không canvas trong `usersTab`). Đường tham chiếu cần một chart chủ để gắn; mà chuỗi DAU thật lại cần field user-set theo bucket mới ở `summary_v2` — đúng phần việc Phase 4 (`timeseries_data` hiện chỉ gom set `rid`, chưa gom set user). Dựng chart bây giờ là kéo scope Phase 4 lên.
- **Quyết định (anh Tuấn):** hoãn reference line sang Phase 4, làm trọn gói cùng chuỗi DAU. Không thuộc change này.
- Snippet plugin `afterDatasetsDraw` (`docs/dashboard_frontend_harvest.md` §3b) vẫn để dành cho Phase 4.

### D6 — CSS: thêm class mới theo harvest §2, không tạo trùng
Thêm cuối `dashboard.css`: `.metric-card.warn/.danger/.ok`, `.metric-q/.metric-unit/.metric-hint`, `.metrics-lg`. Thẻ dùng lại `.metric-card`/`.metric-label`/`.metric-value`/`.metric-detail` sẵn có.
- **Vì sao:** nhiều class prototype đã có dưới tên thật; chỉ thêm cái thật sự thiếu (harvest §1 vs §2). Text tiếng Việt + ngưỡng màu lấy theo `data-od-id` trong `index_exaple.html`.

## Risks / Trade-offs

- **Lệch số Overview vs tab nguồn** (Cost/CSAT/Health) → dùng chung đúng nguồn dữ liệu (accessor + cùng endpoint), không tự tính lại ở frontend.
- **Cost MTD fetch riêng có thể chậm/khác cutoff với tab Usage** → chấp nhận 1 request phụ; ghi rõ nhãn "tháng này" trên thẻ để không nhầm với range global.
- **Concentration ở population nhỏ (n<10)** → `k=ceil(n*0.1)` đảm bảo ≥1; test riêng biên n=0/1.
- **Badge dễ bị hiểu nhầm "Đang bật" = "đã dùng"** → giữ đúng nhãn "Đang bật", tài liệu hóa; số "đã dùng" thật để Phase 4.
- **Thẻ Total Users trùng thông tin badge** → chấp nhận theo yêu cầu leader; tách vai trò (thẻ = điểm nhấn, badge = trạng thái), cùng nguồn `loadUsers`.
- **Placeholder card gây hiểu nhầm "đang lỗi"** → hiển thị `—` + hint "chờ Phase 4" rõ ràng.

## Migration Plan

Thuần bổ sung, không migration DB, không breaking. Thứ tự triển khai:
1. Backend: thêm `top10_pct_cost_share` vào `summary_v2.totals` (backward-compatible — chỉ thêm field).
2. `usage.js`: export `getLastSummary()`.
3. `overview.js` + wiring (`main.js`, `tabs.js`, `index.html` tab + panel) + CSS.
4. `users.js`: thẻ Total Users, badge.

Rollback: gỡ nút/panel Overview và field mới; các tab hiện có không phụ thuộc thay đổi nào ở trên.

## Open Questions

- Ngưỡng màu cụ thể (warn/danger) cho từng thẻ Overview: lấy theo `data-od-id` trong `index_exaple.html` khi implement; nếu prototype chưa chốt ngưỡng nào thì hỏi lại leader trước khi tự đặt.
