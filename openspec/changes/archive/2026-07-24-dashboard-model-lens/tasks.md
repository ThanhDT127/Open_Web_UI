## 1. Xác minh tiền đề (spike ngắn, làm trước khi code)

- [x] 1.1 Khóa gộp `model` (live 2026-07-24): **không có NULL**; tên là **model đã resolve** (`chat-deepseek-v4-flash`, `gemini-embedding-002`…), KHÔNG phải alias `*-auto` → nhãn dùng thẳng, không map. Ghi vào design D4.
- [x] 1.2 Xác nhận `total_cost` (`summary_v2.py:396`) còn scope tại `breakdown_by_model` (`:464`), `user_id` có ở nhánh ok (`:315`) + error (`:333`) — reuse trực tiếp, 0 query mới. ✓
- [x] 1.3 `user_id` trong `mw_audit_log` là email/username (mẫu: `bear@gmail.com`, `admin`…) — cùng namespace `user_data`, không UUID mismatch ([[chat-analytics-id-mismatch]]). ✓

## 2. Backend — `summary_v2.py` (thêm field, 0 endpoint/query mới)

- [x] 2.1 Accumulator `model_data`: thêm khóa `"users": set()`.
- [x] 2.2 Chèn `model_data[model]["users"].add(user_id)` ở **cả 2 nhánh** (ok + error) sau `requests.add(rid)`.
- [x] 2.3 Row `breakdown_by_model`: thêm `"unique_users": len(stats["users"])`.
- [x] 2.4 Thêm `"cost_share_percent": round(stats["cost_total"] / total_cost * 100, 1) if total_cost > 0 else 0.0` (guard chia 0).
- [x] 2.5 Không đổi `totals` / field cũ / `get_summary_v2` — chỉ append 2 field mới.
- [x] 2.6 Nghiệm thu backend (live 2026-07-24, cửa sổ 120d): `Σ cost_share_percent` = 100.10 ✓; mọi `unique_users ≤` 14 active ✓; field cũ nguyên vẹn ✓. Số hợp lý: 2 model embedding = 80% chi phí/2 người (service RAG); `deepseek-flash` 17%/13 người.

## 3. Frontend — bảng Top Models tab Usage (`usage.js`, `index.html`)

- [x] 3.1 `index.html`: thêm 2 `<th>` (`Tỷ trọng CP`, `Người dùng`) ngay sau cột Cost.
- [x] 3.2 `usage.js::_renderModelsTable`: thêm 2 `<td>` (`cost_share_percent` `%` 1 chữ số, `unique_users` `toLocaleString`); no-data `colspan` 8→10 (cả loading trong index.html).
- [x] 3.3 Thêm option `👥 Người dùng` (`users`) vào `topModelsSortBy` + sortFn `users` trong `_getSortedSlice`.
- [x] 3.4 KHÔNG khai `metrics_registry.js`, KHÔNG wire period-compare cho 2 cột — giữ nguyên (D3).

## 4. Nghiệm thu UI

- [x] 4.1 Header 10 `<th>` ↔ template `_renderModelsTable` xuất 10 `<td>`; payload có 2 field (verify live compute 2.6); cột `$/req` (`avgCost`) **không đổi công thức**. File đã deploy trong container (grep xác nhận).
- [x] 4.2 Sort cũ (cost/requests/tokens/latency/errors) giữ nguyên; thêm sort `users` map `unique_users`.
- [x] 4.3 No-data `colspan=10` ở cả `index.html` (loading) và `usage.js` (no model data).
- [x] 4.4 JS syntax hợp lệ (`node --check`); 2 field mới đọc qua `|| 0` nên không throw. *(Console trực tiếp trên trình duyệt: chưa mở phiên live — anh eyeball khi reload dashboard.)*
- [x] 4.5 Cập nhật `docs/dashboard_metrics_implementation_plan.md` Phase 5: tick `cost_share`+`unique_users`, ghi `$/req` đã có sẵn + Non-Goal (blended/1k, request share, CSAT×cost).
