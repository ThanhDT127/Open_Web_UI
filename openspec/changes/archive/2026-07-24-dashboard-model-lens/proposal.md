## Why

Phase 5 của `docs/dashboard_metrics_implementation_plan.md` — **Model: tỷ trọng & đơn giá**. Câu hỏi quản lý: *model nào ngốn phần lớn chi phí, và model đó phục vụ cả team hay chỉ một power-user?* Bảng "Top Models" (tab Usage) đã trả lời "dùng nhiều / tốn / chậm-lỗi" (requests, cost, **`$/req` đã có sẵn**, P95, error%), nhưng thiếu đúng hai lát: **tỷ trọng chi phí** (đòn tập trung, song song Pareto-theo-user) và **số người dùng riêng** (một model 60% chi phí do cả team hay do một người?).

Điểm mấu chốt về chi phí implement: đây là phase **nhẹ nhất** — `model_data` (`summary_v2.py`, dict gom theo model) đã tích sẵn `requests/cost/tokens/latencies`; `breakdown_by_model` đã xuất sẵn requests/tokens/cost/P95/error mỗi model. Hai chỉ tiêu mới **chỉ là thêm field vào row đã có** (một phép chia trên `total_cost` global + một `set` user). **Không endpoint mới, không tab mới, không bảng mới, không migration, không đụng hạ tầng so kỳ.**

Cố ý giữ scope hẹp (2 cột) thay vì bê nguyên §3.3 catalog: các `[+]` còn lại là analyst-tier hoặc đã tồn tại — `$/req` per model **đã hiển thị** (`usage.js`, `avgCost = cost/requests`), `blended cost/1k` là jargon trùng công dụng `$/req`, `CSAT × $/req per model` mang rủi ro khớp sai tên model giữa hai DB. Chúng nằm ở Non-Goals.

## What Changes

- **Backend `summary_v2.py` — thuần thêm field vào `breakdown_by_model` (0 endpoint mới):**
  - Thêm `"users": set()` vào accumulator `model_data`; chèn `model_data[model]["users"].add(user_id)` vào **cả hai nhánh** nạp entry — nhánh `ok/reconciled` và nhánh `error` — vì `model_data[model]["requests"]` cũng được nạp ở cả hai (`requests_total` per model đã tính cả request lỗi). Hệ quả cố ý: **user chỉ-lỗi trên một model vẫn được đếm là đã chạm model đó**, nhất quán với `requests_total`. `user_id` đã trong scope vòng lặp, là email, cùng namespace audit.
  - Mỗi row `breakdown_by_model` thêm 2 field:
    - `unique_users` = `len(stats["users"])`.
    - `cost_share_percent` = `stats["cost_total"] / total_cost × 100`, với `total_cost` là **biến local tổng chi phí toàn population** trong `compute_usage_summary` (chính biến đã tính `top10_pct_cost_share`), KHÔNG phải tổng của list hiển thị. Vì tính per-row trên tổng global, phép cắt `[:20]` ở `get_summary_v2` **an toàn** — mỗi row giữ đúng tỷ trọng thật của nó.
- **Frontend `usage.js` + `index.html` — thêm 2 cột vào bảng Top Models:**
  - `_renderModelsTable`: thêm 2 `<td>` (`cost_share_percent` định dạng `%`, `unique_users` số nguyên), sửa `colspan` no-data 8 → 10.
  - Thêm 2 `<th>` tương ứng vào header bảng trong `index.html`.
- **KHÔNG chạm** `metrics_registry.js`, `period_compare.js`, `charts.js` — bảng breakdown không mang badge so kỳ (đúng luật Phase 2: chỉ scorecard mới wire KT/CK).

## Capabilities

### New Capabilities

- `dashboard-model-metrics`: Hai chỉ tiêu lát-cắt-theo-model bổ sung cho bảng Top Models — **tỷ trọng chi phí** (`cost_share_percent`, chi phí model / tổng chi phí toàn population) và **số người dùng riêng** (`unique_users`, distinct `user_id` đã gọi model đó trong kỳ). Cả hai tính server-side trên `model_data` đã gom sẵn, trước khi cắt `[:20]`, nên số đúng với toàn population dù bảng chỉ hiển thị top 20. Là cột bảng breakdown, không phải scorecard → không đủ điều kiện so kỳ.

### Modified Capabilities

<!-- Không sửa capability nào. `breakdown_by_model` có thêm 2 field nhưng mọi field/hành vi cũ (requests/cost/tokens/$req/P95/error) giữ nguyên — 2 field mới thuộc capability MỚI `dashboard-model-metrics`, không phải một spec-delta lên `dashboard-request-metrics`. Không đụng `dashboard-metric-registry` / `dashboard-period-compare`. -->

## Impact

- **Backend** — `summary_v2.py`: 1 field `set` vào `model_data`, `.add(user_id)` ở 2 nhánh vòng lặp (ok + error), 2 field vào mỗi row `breakdown_by_model`. **Không đổi shape của `totals`, không đổi endpoint, không query mới** (dùng lại đúng vòng lặp và `total_cost` đã tính). Hot path Usage/Chat Analytics không thêm chi phí đáng kể (một `set.add` mỗi entry — mỗi entry chỉ vào một nhánh).
- **Frontend** — `usage.js` (`_renderModelsTable`) + `index.html` (header bảng Top Models). Tùy chọn: thêm `cost_share`/`users` vào dropdown sort `topModelsSortBy`.
- **Non-goal — `$/request` per model:** ĐÃ CÓ (`usage.js` tính `avgCost = cost_usd / requests_total` và hiển thị). Không làm lại; không regression cột này.
- **Non-goal — `blended cost/1k tokens` per model:** jargon trùng công dụng với `$/req` đã có. Bỏ.
- **Non-goal — `request_share_percent`:** rẻ như hai cột kia nhưng giá trị cận biên thấp cạnh cost share; để lại làm fast-follow nếu leader muốn contrast "model rẻ-mà-nặng". Không đưa vào change này để giữ bảng gọn.
- **Non-goal — CSAT × $/req per model:** rủi ro khớp sai tên model giữa `mw_audit_log` (model middleware) và feedback Open WebUI. Là quyết định riêng cần leader chốt, tách khỏi change này.
- **Non-goal — bảng model 3-cột ở Chat Analytics** (`analytics.js`, `analyticsTopModelsTable`): giữ nguyên; change này chỉ nâng bảng giàu ở tab Usage.
- **Non-goal — so kỳ KT/CK cho 2 cột mới:** bảng breakdown không wire badge (Phase 2). Không khai `metrics_registry.js`.
