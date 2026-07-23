## Context

Phase 2 (`dashboard-period-compare`, đã archive) đã dựng xong hạ tầng: `metrics_registry.js` (khai báo chỉ tiêu + `renderDelta()`), `compare_data.js` (nạp cửa sổ KT/CK), và `buildRangeParams()` (một cửa sổ dùng chung). Badge so kỳ đọc thẳng `totals[key]` cho cả ba cửa sổ. Phase 3 **không dựng cơ chế mới** — chỉ thêm chỉ tiêu vào đúng bộ máy đó.

Nguồn dữ liệu là `compute_usage_summary` trong `summary_v2.py` (hàm gom duy nhất cho `mw_audit_log` sau refactor `unify-audit-aggregation`). Nó đã có sẵn: mảng `all_latencies` **đã `.sort()`**, `total_cost`/`total_tokens`/`requests_total`, `timeseries_data` theo bucket, `_get_global_pending_count()`. Đa số chỉ tiêu Phase 3 chỉ là đọc lại các thứ này ở góc khác.

> Số dòng trong `summary_v2.py` đã trôi sau các refactor — mọi tham chiếu trong change này bám **tên hàm/biến**, không bám số dòng.

## Goals / Non-Goals

**Goals:**

- Expose 5 nhóm chỉ tiêu lăng kính Request/Call trong `totals`, tính hoàn toàn server-side.
- Badge so kỳ chạy "miễn phí" nhờ tái dùng registry + `renderDelta()` của Phase 2.
- Không thêm bảng, param, hay endpoint; không đổi response shape.

**Non-Goals:**

- **Admin Ops** (`/admin/*`): không có trong `mw_audit_log` (chỉ 5 handler AI gọi `init_audit_state`, có allowlist). Thuộc Access/Ops (Phase 10), nguồn `mw_request_log`.
- **Error breakdown theo `error_type`**: lỗi provider-side (audit_log) và lỗi chính sách (auth/quota/validation, ngoài audit_log) khác bản chất/khác nguồn — không gộp một thẻ.
- Không đổi `export_report.py`, không việt hoá nhãn (Phase 11).

## Decisions

### D1 — Chỉ tiêu dẫn xuất tính server-side, đặt vào `totals`

Cost/req, cost/1k, avg tokens/req, in:out, RPM… đều tính trong `compute_usage_summary` và đặt vào `totals`, **không** tính ở frontend.

*Vì sao:* badge so kỳ (Phase 2) đọc `totals[key]` cho cả cửa sổ KT/CK. Nếu tính ratio ở frontend thì cửa sổ quá khứ không có field đó → badge trắng. Đặt server-side thì so kỳ và export sau này đều dùng lại được. (Cùng nguyên tắc D8 của Phase 2.)

### D2 — Tái dùng registry + `renderDelta()`, không thêm cơ chế

Mỗi chỉ tiêu mới = **một dòng khai báo** trong `METRICS` (nhãn, formatter, kiểu delta, cực tính, cờ compare). Wiring ở `usage.js` theo đúng khuôn `_COMPARE_CARDS`.

*Hệ quả formatter:* cần thêm 1–2 formatter nhỏ vào `FORMATTERS` — tỷ lệ in:out (vd `2.0x`) và tuổi hàng đợi (vd `3g 20p`). Đây là mở rộng bảng formatter, không đổi yêu cầu của `dashboard-metric-registry`.

### D3 — Percentile độ trễ dùng lại mảng đã sort

P50/P99/max lấy index trên chính `all_latencies` **đã `.sort()`** để tính P95 — không quét lại, không sort lại. Dùng đúng guard `idx < len else [-1]` như P95 để không tràn mảng.

*Vì sao:* rẻ nhất, và bảo đảm 4 phân vị nhất quán trên cùng một tập.

### D4 — Hai accumulator token mới là aggregation THẬT duy nhất

Vòng lặp hiện chỉ cộng `tokens_total`. Để có in:out phải cộng thêm `total_tokens_in`/`total_tokens_out` (row đã có sẵn 2 cột). Đây là thay đổi vòng lặp duy nhất; các item khác chỉ là phép chia hậu-vòng-lặp.

### D5 — Peak throughput chuẩn hoá về req/phút, cùng đơn vị với avg

`rpm_avg` và `rpm_peak` đứng cạnh nhau trên scorecard nên **phải cùng đơn vị** — nếu avg là req/phút mà peak là req/ngày thì hai số trông so được nhưng thực ra không. `rpm_peak` = số request của bucket bận nhất ÷ số phút của bucket đó → luôn là req/phút, so thẳng với `rpm_avg`. Expose thêm `rpm_peak_bucket` (độ phân giải: minute/hour/day) để người đọc biết mức làm mượt.

*Đánh đổi (ghi rõ):* với bucket thô (giờ/ngày ở range dài), `rpm_peak` là trung bình-trong-bucket nên **làm mượt** đỉnh dưới-bucket — nó là "phút bận nhất tính trung bình theo bucket", không phải đỉnh tức thời.

*Vì sao đảo quyết định ban đầu (in kèm đơn vị bucket, giữ đỉnh thô):* phương án đó khiến avg/peak khác đơn vị — hai số cạnh nhau không so được là kiểu sai tệ hơn việc làm mượt. Và "giờ nào bận nhất" đã có sẵn ở dữ liệu hour-of-day, không cần nhồi vào con số peak.

### D6 — Pending oldest age: query `min(ts)`, snapshot, chặn so kỳ

Tuổi kẹt lâu nhất = `now − min(ts)` trên `mw_pending`. Là snapshot toàn bảng (giống `_get_global_pending_count()`), **không** thuộc cửa sổ thời gian → khai `compare: false` trong registry (như `pending_open_count`).

*Bắt buộc trước khi trừ:* xác minh đơn vị `mw_pending.ts` (BIGINT — giây hay ms). Frontend `pending.js` dùng `Date.now()/1000` ⇒ nhiều khả năng giây, nhưng phải kiểm thật rồi mới trừ.

### D7 — Đơn giá chia theo `requests_ok`, không phải `requests_total`

`cost_per_request` và `avg_tokens_per_request` chia cho `requests_ok` (request thành công), **không** `requests_total`.

*Vì sao:* tử số `total_cost`/`total_tokens` chỉ cộng ở nhánh `status in [ok, reconciled]` — tức chỉ request thành công. `requests_total = len(rid_status)` lại đếm **mọi** rid kể cả lỗi/pending. Chia tử-số-thành-công cho mẫu-số-toàn-bộ là **trộn hai tập**, làm đơn giá bị pha loãng bởi request lỗi (vốn tốn 0đ). Dùng `requests_ok` cho tử/mẫu cùng một tập → đọc đúng nghĩa "một request thành công tốn bao nhiêu". `requests_ok` đã có sẵn trong `totals`.

*Nhất quán cả cụm:* P50/P95/P99/max, cost, token đều đang tính trên tập request thành công — cả khối "đơn giá/độ trễ" kể một câu chuyện về cùng một tập, không lẫn.

## Risks / Trade-offs

- **Đơn vị `mw_pending.ts` (s vs ms)** → nếu đoán sai, tuổi lệch 1000 lần. *Mitigation:* D6 — kiểm bằng một dòng query mẫu trước khi code.
- **in:out ratio lệch bản chất giữa loại request** — ảnh/audio có `tokens_out=0`, chat mới có tỷ lệ ý nghĩa. Ratio tổng gộp mọi loại có thể khó đọc. *Mitigation:* tính trên tổng toàn cửa sổ + guard mẫu 0; nếu leader muốn tách theo loại thì để phase model/loại sau.
- **Peak trên range dài mất độ phân giải** — bucket ngày làm mượt đỉnh dưới-bucket (peak vẫn là req/phút, nhưng là trung bình trong bucket bận nhất). *Mitigation:* D5 — expose `rpm_peak_bucket` để lộ độ phân giải; ai cần đỉnh/phút thật thì chọn range ngắn (bucket phút).
- **Thêm field vào `totals`** — `export_report.py` đọc key cố định nên additive an toàn, nhưng phải xác nhận nó không validate shape chặt. *Mitigation:* đọc lại consumer trước khi merge.
- **Cực tính gây tranh cãi (tokens/req, RPM)** — không rõ tăng là tốt hay xấu. *Mitigation:* khai `neutral`, để màu không phán xét; đổi sau chỉ là sửa một dòng registry.

## Migration Plan

Thuần thêm mới; không migrate dữ liệu, không đổi schema.

1. Backend: thêm accumulator token in/out + field dẫn xuất vào `totals` (D3/D4), thêm query `min(ts)` (D6). Nghiệm thu: `/summary` trả các field mới, số đúng với tính tay trên một cửa sổ.
2. Frontend: khai báo registry (+ formatter mới), thêm thẻ tab Usage, wiring `usage.js`. Nghiệm thu: badge so kỳ hiện đúng cho chỉ tiêu windowed; pending age không có badge.

*Rollback:* gỡ khai báo registry + lời gọi render là xong ở frontend; field thừa trong `totals` vô hại nếu để lại.

## Open Questions

- **Định dạng tuổi hàng đợi** — số giây thô, hay humanize ("3g 20p")? Nghiêng humanize cho leader dễ đọc; chốt khi làm registry.
- **in:out** — gộp toàn bộ hay chỉ chat? Mặc định gộp toàn cửa sổ; tách theo loại để dành phase Model.
