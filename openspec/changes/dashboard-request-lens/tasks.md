## 1. Xác minh tiền đề (spike ngắn, làm trước khi code)

- [x] 1.1 Xác minh đơn vị `mw_pending.ts`: `_append_pending_db` (`cost.py:154`) ghi `int(time.time())` = **epoch giây**. Trừ thẳng, không lệch 1000. (Bảng đang rỗng nên xác định từ code ghi.)
- [x] 1.2 `export_report.py` đọc `totals` bằng `.get("key", default)` cho từng key cố định (dòng 276-284) → thêm field mới **additive-an-toàn**, không validate shape.
- [x] 1.3 Anchor trong `compute_usage_summary`: `all_latencies` (đã `.sort()` ở block P95), `total_cost`/`total_tokens` (sum từ `user_data`), `requests_total`/`requests_ok` (từ `rid_status`), `timeseries_data` (set rid/bucket), `cutoff`/`end_time` + `bucket_size` (params), `_get_global_pending_count()`.

## 2. Backend — thêm field dẫn xuất vào `totals` (`summary_v2.py::compute_usage_summary`)

- [x] 2.1 P50/P99/Max latency: `_pct(p)` dùng lại `all_latencies` đã `.sort()` + guard `idx<n else [-1]`. Field `p50/p99/max_latency_ms`, null khi không mẫu.
- [x] 2.2 Đơn giá: `cost_per_request = total_cost/requests_ok`, `cost_per_1k_tokens = total_cost/total_tokens×1000`; guard mẫu 0.
- [x] 2.3 Token: accumulator `total_tokens_in/out` trong nhánh ok/reconciled; `avg_tokens_per_request = total_tokens/requests_ok`; `tokens_in_out_ratio` (null khi out=0).
- [x] 2.4 Throughput: `rpm_avg` + `rpm_peak` **cùng req/phút** (peak = bucket bận nhất ÷ số phút bucket); `rpm_peak_bucket` = nhãn độ phân giải. Round 3 chữ số để không mất tín hiệu ở window dài.
- [x] 2.5 Queue health: hàm `_get_oldest_pending_age_sec()` (mirror `_get_global_pending_count`), `now − min(ts)` giây; `null` khi rỗng.
- [x] 2.6 Nghiệm thu backend (live, sau `docker cp`+restart): 7/7 field ra số, `p50≤p95≤p99≤max` ✓, `cost_per_request=cost/requests_ok` khớp (183≠189), `pending_oldest_age_sec=null` (bảng rỗng) ✓.

## 3. Frontend — registry + formatter (`metrics_registry.js`)

- [x] 3.1 Formatter mới: `ratio` (`1.82:1`), `age` humanize (`3g 20p`/`2n 3g`), `rpm` (`/ph`), `usd6`, `num1`.
- [x] 3.2 Khai báo `METRICS` cho 9 chỉ tiêu windowed (down-good cho cost/latency, neutral cho tokens/rpm/ratio) + `pending_oldest_age_sec` `compare:false`. Verify Node: 20/20 (formatter, isComparable, computeDelta).

## 4. Frontend — thẻ + wiring tab Usage (`index.html`, `usage.js`, `dashboard.css`)

- [x] 4.1 Thêm section "Lăng kính Request/Call" trên tab Usage với 10 thẻ (`metricP50/P99/MaxLatency`, `metricCostPerReq/CostPer1k/AvgTokens/InOutRatio`, `metricRpmAvg/RpmPeak`, `metricPendingAge`); thẻ peak có `metricRpmPeakDetail` cho nhãn bucket.
- [x] 4.2 `usage.js::_renderMetrics`: import `formatValue`, đổ 10 thẻ; detail của peak in độ phân giải bucket (phút/giờ/ngày).
- [x] 4.3 `usage.js::_COMPARE_CARDS`: thêm 9 chỉ tiêu windowed (badge tự chạy) + `metricPendingAge` (chứng minh `compare:false` chặn, không badge).
- [x] 4.4 Không cần CSS mới — thẻ dùng lại `.metric-card`, badge dùng `.delta-badge` của Phase 2.

## 5. Nghiệm thu & tài liệu

- [ ] 5.1 Nghiệm thu UI (Last 30d): badge so kỳ hiện đúng cho các chỉ tiêu windowed; thẻ pending age **không** có badge.
- [x] 5.2 Kiểm chéo (live API): `cost_per_request=0.000367=cost/requests_ok` (183≠189) ✓; `p50≤p95≤p99≤max` ✓; các số khớp tính tay.
- [x] 5.3 Cập nhật `docs/dashboard_metrics_implementation_plan.md` Phase 3: tick 5 mục đã lên (kèm ghi chú kỹ thuật), ghi rõ Admin Ops & Error breakdown là non-goal + lý do.
- [ ] 5.4 (Tuỳ chọn) Test Playwright cho phép tính thuần tách được (thứ tự percentile, guard mẫu 0, đổi đơn vị bucket) theo mẫu `tests/dashboard-period-compare.spec.ts`.
