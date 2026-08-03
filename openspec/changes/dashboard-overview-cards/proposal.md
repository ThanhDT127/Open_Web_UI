## Why

Dashboard hiện chưa có màn hình tổng quan cấp lãnh đạo: người quản lý phải nhảy qua nhiều tab (Usage, Satisfaction, Users) để ghép lại bức tranh "tốn bao nhiêu, ai dùng, chất lượng và sức khỏe ra sao". Đây là Phase 1 của kế hoạch chỉ tiêu dashboard (`docs/dashboard_metrics_implementation_plan.md`) — dựng tab Overview để leader thấy hình dạng thật sớm, đồng thời bổ sung vài thẻ inventory còn thiếu ở tab Users. Ưu tiên tái sử dụng dữ liệu đã có; backend chỉ thêm đúng 1 chỉ tiêu mới.

## What Changes

- **Tab `🎯 Overview` mới** với 6 thẻ tầng lãnh đạo:
  - 4 thẻ có số thật ngay: **Cost MTD** (chi phí từ đầu tháng), **CSAT** (mức hài lòng), **System Health** (error rate + P95), **Cost Concentration** (top 10% user chiếm ?% chi phí).
  - 2 thẻ placeholder `—` chờ Phase 4: **Adoption rate**, **Cost / active user**.
- **Chỉ tiêu backend mới duy nhất**: `top10_pct_cost_share` — thêm vào `totals` của summary API, tính trên **toàn bộ** population user (trước bước cắt `[:20]`). Overview và Phase 4 dùng chung con số này.
- **Tab Users bổ sung inventory**:
  - Thẻ **Total Users** (đếm `mw_users` chưa xóa) — giữ theo yêu cầu leader, song song với badge.
  - **Việt hóa badge** trạng thái: `Active: X` → `Đang bật: X · Tổng: Y` (đổi chữ, giữ nguyên nghĩa số non-disabled — KHÔNG đổi thành "đã dùng" để tránh lặp lỗi mislabel).
- **Không nằm trong phạm vi**: tab Providers + thẻ Total Models (dời Phase 6); đường tham chiếu ngang trên DAU chart (dời Phase 4 — tab Users chưa có DAU chart và chuỗi DAU cần field backend mới của Phase 4). **Giữ nguyên** 11 tab hiện có, gồm `📚 Knowledge`.

## Capabilities

### New Capabilities
- `dashboard-overview`: Tab Overview cấp lãnh đạo với 6 thẻ tổng hợp (Cost MTD, CSAT, System Health, Cost Concentration + 2 placeholder), và chỉ tiêu `top10_pct_cost_share` bổ sung vào summary API để phục vụ thẻ Concentration.
- `users-tab-inventory`: Các thẻ/nhãn inventory ở tab Users — thẻ Total Users và badge trạng thái Việt hóa. (Đường tham chiếu DAU dời Phase 4.)

### Modified Capabilities
<!-- Không có capability hiện hữu nào thay đổi ở cấp requirement. -->

## Impact

- **Backend** — `llm-mw/api/summary_v2.py`: thêm field `top10_pct_cost_share` vào `totals` (tính trước dòng cắt `breakdown_by_user[:20]`). Không thêm endpoint.
- **Frontend mới** — `llm-mw/dashboard/js/overview.js` + `window.overviewAPI`; wiring trong `main.js` (import) và `tabs.js` (case `overview`); nút tab + panel `overviewTab` trong `index.html`.
- **Frontend reuse** — export `getLastSummary()` từ `usage.js` để Overview dùng lại response summary (global range) cho thẻ Health + Concentration, tránh fetch trùng. Cost MTD gọi summary với range tháng; CSAT gọi `get_satisfaction_analytics`.
- **Frontend sửa** — `users.js`: thêm thẻ Total Users, đổi text badge.
- **CSS** — `dashboard.css`: thêm `.metric-card.warn/.danger/.ok`, `.metric-q/.metric-unit/.metric-hint`, `.metrics-lg` (theo `docs/dashboard_frontend_harvest.md` §2).
- **Không** thay đổi schema DB, không endpoint mới, không đụng 11 tab hiện có.
