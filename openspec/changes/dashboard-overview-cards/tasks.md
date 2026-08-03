## 1. Backend — chỉ tiêu concentration

- [x] 1.1 Trong `llm-mw/api/summary_v2.py`, sau khi có `total_cost` và trước dòng cắt `breakdown_by_user[:20]`, tính top-10% cost share trên toàn `user_data`: sort cost giảm dần, `k = ceil(n*0.10)` (≥1 khi n>0), `share = sum(top_k)/total_cost*100`.
- [x] 1.2 Xử lý biên: n=0 hoặc `total_cost==0` → 0; 1 user có cost → 100. Trả về số làm tròn hợp lý.
- [x] 1.3 Thêm `top10_pct_cost_share` vào dict `totals` của response (backward-compatible, chỉ thêm field).
- [x] 1.4 Kiểm thử nhanh: range >20 user (số phản ánh toàn bộ, không chỉ top 20), range 0/1 user (không lỗi).

## 2. Frontend — accessor tái sử dụng summary

- [x] 2.1 Trong `llm-mw/dashboard/js/usage.js`, export `getLastSummary()` trả `_lastSummaryData`.

## 3. Frontend — module & wiring tab Overview

- [x] 3.1 Tạo `llm-mw/dashboard/js/overview.js`: hàm load + render, export + `window.overviewAPI` (theo mẫu `raghealth`/`groupAnalytics`).
- [x] 3.2 Import `overview.js` trong `main.js` và gắn `window.overviewAPI` cạnh các namespace tab khác.
- [x] 3.3 Thêm case `overview` trong `tabs.js:switchTab` để gọi load khi mở tab.
- [x] 3.4 Thêm nút tab `🎯 Overview` (gọi `switchTab(event,'overview')`) và panel `<div id="overviewTab" class="tab-content">` trong `index.html`, cạnh Usage — GIỮ nguyên 11 tab hiện có gồm Knowledge.

## 4. Frontend — 6 thẻ Overview

- [x] 4.1 Thẻ **Cost MTD**: fetch `summary_v2?start=<đầu tháng UTC>&end=<now>`, hiển thị cost, nhãn "tháng này".
- [x] 4.2 Thẻ **CSAT**: gọi `get_satisfaction_analytics` (range global), lấy `totals.csat_percent`.
- [x] 4.3 Thẻ **System Health**: đọc `getLastSummary()`, hiển thị `error_rate_percent` + `p95_latency_ms`; dòng uptime để trống/ẩn.
- [x] 4.4 Thẻ **Cost Concentration**: đọc `getLastSummary().totals.top10_pct_cost_share`.
- [x] 4.5 Hai thẻ placeholder **Adoption rate** và **Cost / active user**: hiển thị `—` + hint "chờ Phase 4".
- [x] 4.6 Mỗi thẻ ghi rõ khung thời gian ở dòng phụ (Cost MTD "tháng này" vs 3 thẻ kia "khoảng đang xem"); áp ngưỡng màu (CSAT/error rate có ngưỡng catalog; Cost MTD/Concentration để neutral vì chưa có ngưỡng chốt).

## 5. Frontend — CSS

- [x] 5.1 Thêm cuối `dashboard.css` (theo harvest §2): `.metric-card.warn/.danger/.ok`, `.metric-q/.metric-unit/.metric-hint`, `.metrics-lg`. Không tạo trùng class đã có.

## 6. Frontend — tab Users (inventory)

- [x] 6.1 Thêm thẻ **Total Users** vào panel Users, đếm `mw_users` chưa xóa từ data `loadUsers` đã fetch (không endpoint mới).
- [x] 6.2 Đổi text badge trong `users.js` sang `Đang bật: X · Tổng: Y`, giữ nguyên công thức `X`=non-disabled, `Y`=total.
- [~] 6.3 HOÃN sang Phase 4 (quyết định anh Tuấn): tab Users chưa có DAU chart để gắn reference line, và chuỗi DAU thật cần field user-set/bucket mới ở backend (thuộc Phase 4). Không thuộc phạm vi change này.

## 7. Kiểm chứng

Verify ở tầng API + asset (middleware rebuild, healthy) — 2026-07-19:
- Backend field live: `GET /v1/_mw/summary` trả `totals.top10_pct_cost_share = 61.2` (13 user, không lỗi).
- Nguồn dữ liệu 4 thẻ thật đều sống: CSAT `csat_percent=80`, summary có `error_rate_percent`/`p95_latency_ms`/`cost_total_usd`.
- Asset phục vụ đúng bản mới: `/dashboard` chứa nút+panel `overview`, `ovConcentrationValue`, `metricTotalUsers`, badge "Đang bật:"; `/dashboard/js/overview.js` HTTP 200.

- [x] 7.1 (API/asset) Tab Overview có markup 6 thẻ + data 4 thẻ thật khớp endpoint nguồn. ⏳ Còn lại: xác nhận RENDER trực quan trên trình duyệt (Ctrl+F5).
- [x] 7.2 (API) Cost MTD dùng range tháng riêng; CSAT/Health/Concentration đọc range global. ⏳ Còn lại: xác nhận đổi range trên UI.
- [x] 7.3 (API/asset) Thẻ Total Users (`metricTotalUsers`) + badge "Đang bật/Tổng" có trong HTML phục vụ; 11 tab cũ nguyên vẹn. ⏳ Còn lại: xác nhận trực quan.
