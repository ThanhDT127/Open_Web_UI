## Why

Phase 3 của `docs/dashboard_metrics_implementation_plan.md` — **lăng kính Request/Call**. Sau Phase 1 (tổng requests/cost/tokens/P95/error rate) và Phase 2 (so kỳ KT/CK), dashboard vẫn thiếu các lăng kính chi tiết của một request để leader trả lời được: *chậm ở nhóm nào (không chỉ P95)? đơn giá thực mỗi request/mỗi 1k token là bao nhiêu? tải nặng vào lúc nào? có request nào kẹt lâu không?*

Điểm mấu chốt: **toàn bộ nguyên liệu đã có sẵn trong `compute_usage_summary` (`summary_v2.py`)** — mảng latency đã sort để tính P95, `total_cost`/`total_tokens`/`requests_total`, `timeseries_data` theo bucket, và `_get_global_pending_count()`. Change này chỉ **expose** chúng ra, không tính lại và không thêm nguồn dữ liệu.

## What Changes

- **Thêm field vào `totals` của `compute_usage_summary`** (server-side, không bảng mới, không param mới, không đổi response shape):
  - `p50_latency_ms`, `p99_latency_ms`, `max_latency_ms` — thêm index trên mảng `all_latencies` **đã `.sort()` sẵn** cạnh P95.
  - `cost_per_request`, `cost_per_1k_tokens` — chia trên `total_cost`/`total_tokens`, **mẫu số là `requests_ok`** (không phải `requests_total` — tử số chỉ gồm request thành công, xem design D7).
  - `avg_tokens_per_request`, `tokens_in_out_ratio` — cần **thêm 2 accumulator** `total_tokens_in`/`total_tokens_out` trong vòng lặp (row đã có `tokens_in`/`tokens_out` nhưng loop hiện chỉ cộng `tokens_total`); avg chia `requests_ok`.
  - `rpm_avg`, `rpm_peak`, `rpm_peak_bucket` — **cả avg lẫn peak đều là req/phút** (peak = bucket bận nhất chuẩn hoá về phút) để so được với nhau; `rpm_peak_bucket` báo độ phân giải.
  - `pending_open_count` (đã có) **+** `pending_oldest_age_sec` — thêm một truy vấn `min(ts)` trên `mw_pending`.
- **Frontend (đúng khuôn Phase 2):** khai báo các chỉ tiêu mới trong `metrics_registry.js`, thêm thẻ trên **tab Usage**, render qua `renderDelta()`. Badge so kỳ **tự chạy** cho các chỉ tiêu thuộc cửa sổ thời gian; `pending_oldest_age_sec` khai `compare: false` (snapshot toàn bảng, giống `pending_open_count`).
- **Không nằm trong phạm vi (ghi rõ lý do ở Impact):** Admin Ops và Error breakdown theo `error_type` — hai mục này thuộc nguồn/lăng kính khác.

## Capabilities

### New Capabilities

- `dashboard-request-metrics`: Tập chỉ tiêu lăng kính Request/Call mà endpoint summary tính server-side và expose trong `totals` — phân vị độ trễ (P50/P99/max), đơn giá (cost/request, cost/1k tokens), cường độ token (avg tokens/request, tỷ lệ in:out), throughput (RPM trung bình + đỉnh, cùng đơn vị req/phút), và sức khỏe hàng đợi (số pending + tuổi request kẹt lâu nhất). Quy tắc: mọi chỉ tiêu dẫn xuất tính ở server và đặt vào `totals` để tái dùng được cho so kỳ và export; chỉ tiêu snapshot toàn bảng bị chặn so kỳ.

### Modified Capabilities

<!-- Không có. `dashboard-metric-registry` và `dashboard-period-compare` được TÁI DÙNG nguyên vẹn: change này thêm khai báo chỉ tiêu vào registry và để badge chạy qua cơ chế sẵn có, không đổi yêu cầu của hai capability đó. -->

## Impact

- **Backend** — chỉ `compute_usage_summary` trong `summary_v2.py` (tra theo **tên hàm**, không theo số dòng — số dòng đã trôi sau refactor `unify-audit-aggregation`): thêm 2 accumulator token in/out, thêm các field dẫn xuất vào `totals`, và một truy vấn `SELECT min(ts) FROM mw_pending`. **0 bảng mới, 0 param mới, 0 đổi shape.** `export_report.py` đọc key cố định trong `totals` nên thêm field là additive-an-toàn (xác nhận ở task 1.2).
- **Frontend** — `metrics_registry.js` (khai báo chỉ tiêu mới), `usage.js` (`_renderMetrics` + `_COMPARE_CARDS`), `index.html` (thẻ mới trên tab Usage), `dashboard.css` nếu cần định dạng mới (tỷ lệ in:out, tuổi hàng đợi).
- **Tải hệ thống** — badge đọc từ `/summary` sẵn có, **không phát thêm request** ngoài cặp KT/CK mà Phase 2 đã có; thêm đúng một truy vấn nhẹ `min(ts)`.
- **Non-goal — Admin Ops (`/admin/*`):** không nằm trong `mw_audit_log` (chỉ 5 handler AI gọi `init_audit_state`, có allowlist), nên **không thể** làm từ nguồn của change này. Thuộc lăng kính Access/Ops (Phase 10), nguồn `mw_request_log` (đã có `access_logs.py` aggregate sẵn).
- **Non-goal — Error breakdown theo `error_type`:** lỗi có hai bản chất khác nguồn — *lỗi vận hành provider-side* nằm trong `mw_audit_log` (cùng tập với Error Rate %), còn *lỗi chính sách* (auth/quota/validation) bị chặn **trước** `init_audit_state` hoặc không gắn `error_type`, nên thuộc `mw_request_log`/lăng kính Access. Trộn hai loại vào một thẻ là sai bản chất; để dành làm đúng chỗ.
