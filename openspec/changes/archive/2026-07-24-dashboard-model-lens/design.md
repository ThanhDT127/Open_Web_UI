## Context

Phase 5 trả câu hỏi "tiền đi đâu theo model" ở mức đủ cho quản lý, không phải mức phân tích sâu. Khác Phase 4 (chạm hai miền dữ liệu, cần module + endpoint mới), Phase 5 nằm **trọn trong một hàm đã có**:

```
compute_usage_summary()  (summary_v2.py)
  └─ model_data: Dict[model → {requests, requests_ok, errors,
                               tokens_total, cost_total, latencies}]   ← đã gom sẵn
  └─ breakdown_by_model: [{model, requests_total, requests_ok, errors,
                           error_rate_percent, tokens_total, cost_usd,
                           p95_latency_ms}]                            ← đã xuất sẵn 8 field
  └─ get_summary_v2() cắt breakdown_by_model[:20] cho endpoint
```

Bảng frontend `_renderModelsTable` (`usage.js`) render 8 cột; trong đó **`$/req` đã được tính client-side** (`avgCost = cost_usd / requests_total`). Nghĩa là một trong các `[+]` của plan Phase 5 (đơn giá per request) **đã xong**, làm scope thật co lại còn 2 field.

## Goals / Non-Goals

**Goals:**

- Thêm đúng 2 field vào `breakdown_by_model`: `cost_share_percent`, `unique_users`.
- Render 2 cột tương ứng vào bảng Top Models tab Usage.
- Giữ mọi cột hiện có và `totals` bất biến; không endpoint/tab/bảng/migration mới; không đụng registry/so-kỳ.

**Non-Goals:**

- `$/req` per model (đã có), `blended cost/1k` (bỏ — jargon trùng `$/req`), `request_share_percent` (fast-follow tùy chọn).
- CSAT × chi phí per model (rủi ro cross-DB, chờ leader — quyết định riêng).
- Nâng bảng model 3-cột ở Chat Analytics.
- Badge so kỳ cho cột bảng (Phase 2 chỉ wire scorecard).
- Việt hoá nhãn cột (Phase 11).

## Decisions

### D1 — Tính server-side trên `total_cost` global, KHÔNG suy ra ở frontend từ list đã cắt

`cost_share_percent[model] = stats["cost_total"] / total_cost × 100`, với `total_cost` là **biến local tổng chi phí toàn population** (`summary_v2.py:396` — `sum(d["cost_total"] for d in user_data.values())`), chính biến dùng cho `top10_pct_cost_share` ngay phía trên chỗ dựng `breakdown_by_model`. (Lưu ý phân biệt: `total_cost` là biến local; `cost_total_usd` là *tên field* trong dict `totals`; `stats["cost_total"]` là chi phí tích luỹ của riêng model đó, xuất ra row dưới tên `cost_usd`.)

*Vì sao không tính ở frontend:* `get_summary_v2` trả `breakdown_by_model[:20]`. Nếu frontend lấy `cost_usd / Σ(cost_usd của 20 dòng)` thì mẫu số **thiếu phần đuôi** → share bị thổi phồng. Tính per-row trên `total_cost` global **trước khi cắt** cho mỗi row đúng tỷ trọng thật; 20 dòng hiển thị sẽ không cộng đủ 100% (đúng và mong đợi — phần còn lại là đuôi model nhỏ). Đây chính là cảnh báo `[:20]` mà plan Phase 5 (mục Reuse) đã dặn.

### D2 — `unique_users` per model: thêm `set` vào accumulator, chấp nhận tổng > số user active

`model_data` hiện **không** theo dõi user (chỉ `user_data` mới có). Thêm `"users": set()`; chèn `model_data[model]["users"].add(user_id)` ở **cả hai nhánh** — sau `model_data[model]["requests"].add(rid)` trong nhánh `ok/reconciled` (`:324`) *và* trong nhánh `error` (`:339`). `user_id` đã trong scope (vòng lặp dùng nó cho `user_data`). Emit `unique_users = len(stats["users"])`.

*Vì sao cả nhánh error:* `model_data[model]["requests"]` được nạp ở cả hai nhánh, nên `requests_total` per model đã gồm request lỗi. Để `unique_users` nhất quán với `requests_total` (những người tạo ra chính các request đó), phải đếm người ở cả hai nhánh → **user chỉ-lỗi trên một model vẫn tính là đã chạm model**. Đúng nghĩa "có bao nhiêu người gọi tới model này", song song quyết định "user chỉ-lỗi vẫn là active" ở Phase 4 (adoption D3).

*Số học phải hiểu đúng (không phải bug):* `Σ unique_users` trên mọi model **có thể lớn hơn** tổng số user active trong kỳ, vì một người dùng 3 model được đếm ở cả 3. Đây là đặc tính của "distinct theo từng model" — giống WAU dedup trong Phase 4. Cột này trả lời "model X có bao nhiêu người chạm tới", không phải một phân hoạch của population.

### D3 — KHÔNG chạm `metrics_registry.js` / so kỳ

Hai field là **cột trong bảng breakdown**, không phải scorecard. Cơ chế `renderDelta`/`metrics_registry` (Phase 2) chỉ gắn badge KT/CK cho thẻ scorecard qua `valueElementId`. Bảng Top Models không đi qua đường đó — thêm khai báo registry sẽ là code chết. Vì vậy change này **không mở** `metrics_registry.js`, giữ ranh giới "bảng ≠ thẻ" mà Phase 2 đã đặt.

### D4 — Khóa gộp là field `model` thô, xác minh trước khi tin

`model_data` gộp theo `mw_audit_log.model` nguyên trạng. Trước khi code cần chốt (spike): (a) field `model` có null/rỗng không (→ key `None`/`"unknown"`?); (b) audit ghi **model đã resolve** hay **alias `*-auto`** — nếu ghi alias thì share/user sẽ gộp theo alias, cần biết để dán nhãn đúng và không làm leader hiểu nhầm "model" là "cổng routing". Đây là rủi ro *ý nghĩa*, không phải rủi ro kỹ thuật — quyết định hiển thị bám kết quả spike.

**Kết quả spike (live 2026-07-24, `mw_audit_log`, 13 model):** (a) **không có** dòng `model` NULL/rỗng → không cần key `"unknown"` (vẫn giữ guard phòng thủ). (b) Tên là **model đã resolve** (`chat-deepseek-v4-flash`, `gemini-embedding-002`, `chat-claude-opus-4.6`…), **KHÔNG phải alias `*-auto`** → nhãn cột dùng thẳng, không map. `unique_users` phân hoá thật (deepseek-flash 13 người; các model embedding/thử nghiệm 1 người). Rủi ro D4 **không hiện thực hoá**.

## Risks / Trade-offs

- **Khóa `model` bẩn/alias (D4).** *Mitigation:* spike đọc mẫu `DISTINCT model FROM mw_audit_log` trước khi code; nếu toàn alias `*-auto`, ghi rõ nhãn cột hoặc cân nhắc map — nhưng không mở rộng scope trong change này.
- **Hiểu nhầm `Σ unique_users` (D2).** *Mitigation:* không đặt cột này cạnh một "tổng" gợi ý phân hoạch; nếu cần chú thích tooltip "distinct theo model, cộng chéo được".
- **Tính share trên population đầy nhưng hiển thị top 20** — 20 dòng không cộng đủ 100%. *Mitigation:* đúng thiết kế; nếu muốn minh bạch có thể thêm dòng "còn lại N model / M% chi phí" (không bắt buộc, để ngoài scope).
- **Regression cột `$/req` cũ.** *Mitigation:* không đụng công thức `avgCost`; nghiệm thu so trước/sau một model.

## Migration Plan

Thuần thêm mới; không migrate dữ liệu, không đổi schema, không đổi shape `totals`.

1. Spike: `DISTINCT model` (null? alias `*-auto`?); xác nhận `total_cost` và `user_id` trong scope tại chỗ dựng `breakdown_by_model`.
2. Backend: thêm `set` + 2 field. Nghiệm thu: `Σ cost_share_percent` mọi model (trước cắt) ≈ 100; `unique_users[model] ≤` tổng active users; cột cũ không đổi.
3. Frontend: 2 cột + header + colspan. Nghiệm thu: bảng render đủ 10 cột, sort cũ vẫn chạy, console sạch.

*Rollback:* gỡ 2 field backend + 2 cột frontend; bảng trở về 8 cột, không dữ liệu nào bị đụng.

## Open Questions

- **`request_share_percent`** — thêm cột thứ 3 để lộ contrast "model rẻ-mà-nặng lượt" (nhiều request, ít tiền), hay giữ 2 cột? Mặc định: 2 cột.
- **Nhãn khi `model` là alias `*-auto`** — hiển thị thô hay map về model resolve? Chờ kết quả spike D4.
- **Dòng "đuôi" (model ngoài top 20)** — có thêm dòng tổng "còn lại" để share cộng đủ 100% không? Mặc định: không.
