## 1. Xác minh tiền đề (spike ngắn, làm trước khi code)

- [x] 1.1 JOIN định danh (live 2026-07-23): roster=12, audit distinct=13, **matched=10** — `user_id` cả 2 bảng là email/username, cùng namespace ✓. 3 user audit ngoài roster = rác test đã purge → phép giao loại đúng (adoption raw 13/12=108% → giao 10/12=83.3%).
- [x] 1.1b Biên ngày: **xử lý phòng thủ** — query DAU/WAU ép `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date` vô điều kiện, đúng UTC+7 bất kể session TimeZone. (Verify session tz vẫn nên chạy khi có DB nhưng không còn là điều kiện chặn.)
- [x] 1.2 `mw_users` có `created_at` (TIMESTAMPTZ, `db.py:229`) và `deleted_at` (ALTER `db.py:331`) — xác nhận. Nhãn "cấp mới". Context xóa mềm ([[middleware-soft-delete-only]]) — phép giao D3 tự loại user rác-test.
- [x] 1.3 Field `quota`: xác nhận `get_current_quota_user`/`get_user_quota_status` đọc `limit_cost_usd`/`used_cost_usd` **trong `quota` JSONB**; histogram bulk-read `quota` + áp công thức inline (KHÔNG gọi `get_current_quota_user` per-user vì nó reset kỳ = side-effect). `quota={}` → bucket "không giới hạn" (đã guard).
- [x] 1.4 Anchor reuse: `breakdown_by_user` (`summary_v2.py:567`, full), `top10_pct_cost_share` (`:551`), `cost_total_usd` (`:539`) — đọc được từ dict `compute_usage_summary`.

## 2. Backend — module `api/adoption.py` (mới) + route `main.py`

- [x] 2.1 Khung endpoint `GET /v1/_mw/adoption` (`api/adoption.py::get_adoption`): `require_admin_or_session` + `_resolve_range` như `get_summary_v2`.
- [x] 2.2 Adoption + roster (`compute_adoption`): `roster` từ `_roster_rows` (`deleted_at IS NULL`); `active_users` = set user_id của `breakdown_by_user` (raw); `active_provisioned = active ∩ roster`; `adoption_rate_percent` (giao ⇒ ≤100, guard 0); `new_accounts_in_period` không lọc `deleted_at` (D4b); `cost_per_active_user = cost_total_usd/|active_users|` (guard 0).
- [x] 2.3 Chuỗi DAU/WAU (`_build_activity_series`/`_daily_user_pairs`): gom `(ngày UTC+7, user)` trên `[start−6d, end]`; DAU đếm/ngày + WAU hợp 7 ngày trượt; cắt về [start,end]; range < 1 ngày → rỗng.
- [x] 2.4 Tài khoản ngủ (`_dormant_accounts` + `_last_seen_per_user`): `max(ts)/user` đối chiếu roster; *chưa bao giờ* (NULL) / *ngừng > 30* (`DORMANT_THRESHOLD_DAYS`); dòng email/created_at/last_seen/days_silent/active; sắp giảm dần; trả 3 count.
- [x] 2.5 Histogram quota (`_quota_histogram`): bucket `used/limit%` + *không giới hạn* (`limit ≤ 0`), công thức inline như `get_user_quota_status`, bulk-read (không side-effect).
- [x] 2.6 Pareto (reuse thuần): trả `top10_pct_cost_share` + `breakdown_by_user` full — không tính lại.
- [x] 2.7 Đăng ký route `main.py`: import `get_adoption` + `app.add_api_route("/v1/_mw/adoption", ...)`.
- [x] 2.8 Nghiệm thu backend (live 2026-07-23, `docker cp`+restart, HTTP 200): 7/7 bất biến PASS — `adoption_rate=83.3≤100`, `active_provisioned(10)≤provisioned(12)`, histogram sum=12=provisioned, mọi ngày `DAU≤WAU`, `dormant=never(2)+stopped(0)`. WAU dedup xác nhận (28/06 DAU5→29/06 DAU1 nhưng WAU5→6).

## 3. Frontend — registry (`metrics_registry.js`)

- [x] 3.1 Formatter: `pct1`/`int`/`usd4` (đã có) + thêm `days` ("N ngày") cho cột im lặng.
- [x] 3.2 Khai báo `METRICS`: `adoption_rate_percent` (up-good, pp), `new_accounts_in_period` (neutral, abs), `cost_per_active_user` (neutral, rel) — windowed; `provisioned_total` + `dormant_count` `compare:false`.

## 4. Frontend — tab Users: chỉ tiêu + chart + bảng (`index.html`, `dashboard/js/adoption.js`, `charts.js`, `dashboard.css`)

- [x] 4.1 Module `dashboard/js/adoption.js` export `loadAdoption`, dispatch từ `tabs.js` nhánh `users` — **theo pattern thật của `overview.js`** (export hàm + tabs.js gọi), không phải `window.adoptionAPI` (namespace đó không tồn tại trong code thật). Fetch `/adoption` theo `buildRangeParams()`.
- [x] 4.2 Thẻ tab Users: `metricAdoptionRate` (+detail X/Y), `metricNewAccounts`, `metricCostPerUser`, `metricProvisioned` — HTML chèn sau thẻ Total Users.
- [x] 4.3 Line chart DAU/WAU (`adoptionActivityChart`): WAU đậm + DAU nét đứt mờ + **đường tham chiếu ngang "Đã cấp: N"** (plugin `_provisionedLinePlugin` inline `afterDatasetsDraw`, không cần thư viện).
- [x] 4.4 Chart Pareto (`adoptionParetoChart`): bar chi phí/user (top 15, `breakdown_by_user` đã sort) + line luỹ kế % (trục y phải).
- [x] 4.5 Bảng "💤 Tài khoản ngủ": email/ngày cấp/dùng lần cuối/im lặng/trạng thái, tô tầng 🔴(chưa dùng)/🟠(≥60)/🟡, badge tổng never/stopped. Read-only.
- [x] 4.6 Wiring compare: `renderCompare` gọi `loadCompare('/v1/_mw/adoption', pickAdoptionMetrics)` + `renderDelta` cho 3 chỉ tiêu windowed; snapshot (`provisioned_total`/`dormant`/histogram) không badge (không wire).

## 5. Gỡ placeholder Overview & tài liệu

- [x] 5.1 `overview.js`: thêm `loadAdoptionCards` đổ `ovAdoptionValue`/`ovAdoptionDetail` = adoption rate, `ovCpuValue` = cost/người dùng thật; badge qua `pickAdoptionMetrics` reuse; bỏ hint "chờ Phase 4" trong `index.html`.
- [x] 5.2 Nghiệm thu UI (live 2026-07-23, Chrome, Last 30d): thẻ adoption 83.3%/11/$0.0052/12 khớp API; badge KT/CK đúng cho 3 windowed (▲+75đ%, ▲+11, ▼−97%), **Tổng đã cấp không badge**; chart DAU/WAU có **đường "Đã cấp _12"**; Pareto + histogram (11+1) + bảng ngủ (nikki 18n, caovanha 16n) đúng; 2 thẻ Overview hết "—" (83.3% / $0.0052). **Console: 0 lỗi JS.**
- [x] 5.3 Cập nhật `docs/dashboard_metrics_implementation_plan.md` Phase 4 (đã unstash): tick 7 mục + ghi deviation D2 + non-goal nút nhắc + kết quả nghiệm thu live.
