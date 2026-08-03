## 1. Xác minh tiền đề (spike ngắn, làm trước khi code)

- [x] 1.1 Query `mw_audit_log` (live 2026-07-25): 13 model distinct. Đối chiếu `/model/info` (24 model): unmatched → `other` gồm `gemini-embedding-002` ($0.167, cost cao thứ 2 — lệch tên vs `gemini-embedding-2` trong config), `chat-deepseek-v3`, `text-embedding-004`, `gemini-embedding-004`, `gemini-2.5-flash`. Xác nhận nhánh `other` cần thật; tổng vẫn khớp. (dev-data drift, không phải lỗi logic)
- [x] 1.2 Xác nhận `litellm_params.model = <provider>/<...>` cho cả 24 entry; 6 billing account thật = openai/gemini/vertex_ai/xai/anthropic/openrouter (khớp thiết kế). `/model/info` KHÔNG chứa `*-auto` → Total Models=24 không trừ.
- [x] 1.3 Xác nhận `_get_provider_spend`/`_check_provider_budget_alerts` chỉ gọi ở CHECK 2 (`alerting.py:310,421,480`); CHECK 1 (quota-user, `alerts_sent`, email user) độc lập — không đụng.

## 2. Attribution dùng chung — `core/provider_attribution.py`

- [x] 2.1 `build_model_provider_map()`: gọi LiteLLM `/model/info` (httpx sync + master key `LITELLM_KEY`), parse `litellm_params.model` → `{alias→account}`; cache TTL 300s; lỗi → giữ map cũ, không crash. (test live: 24 model)
- [x] 2.2 `resolve_account(model, mapping)`: lookup, không khớp → `OTHER_ACCOUNT="other"`.
- [x] 2.3 `spend_since_funding(funded_at_by_account)` (per-account từ funded_at riêng) + `spend_by_account_uniform(start,end)` (đối soát); reuse `db_conn`/`_pool` như `_get_provider_spend`.
- [x] 2.4 Test đối soát (live 2026-07-25): `Σ by account (kể cả other) = grand_total = 0.447909`, match=True.

## 3. Migrate config credit trả trước — `data/alert_config.json`

- [x] 3.1 Migrate DB `mw_config.alert_config` + file host: `api_budgets` → 6 account (openai 150, gemini/vertex_ai/anthropic/xai/openrouter 100), mỗi cái `{enabled, deposited, funded_at, thresholds}`; bỏ `model_prefixes`/`budget_usd`. deposited từ budget brand cũ (placeholder — admin set thật qua Settings).
- [x] 3.2 `funded_at = now` (2026-07-24T17:29Z); backup `alert_config.db-backup.*.json` + `.file-backup.*.json` trước khi ghi.
- [x] 3.3 Giữ nguyên smtp/per_user_quota/user_alerts (load→replace api_budgets→save); dọn 2 key `provider_deepseek_*` cũ khỏi `system_alerts`.

## 4. Backend endpoint — `api/providers.py` + `main.py`

- [x] 4.1 `compute_providers(now)` (test live): 6 account tính `deposited/spent/remaining/used_percent/runway_days/status`; totals `provider_count/total_remaining/total_spent`; `other` chỉ `spent`.
- [x] 4.2 Runway `_runway_days`: `days<MIN_DAYS_FOR_RUNWAY(2)` **hoặc** `burn==0` → `null`; `remaining<=0` → 0. Test: near-exhaust→1.0/critical, burn=0→None. ✓
- [x] 4.3 `total_models` reuse map `/model/info`, lọc `_AUTO_MODEL_NAMES` → 24 (không trừ). Lỗi → `null`.
- [x] 4.4 `get_providers(request)`: `require_admin_or_session`; route `GET /v1/_mw/providers` trong `main.py`. (route phục vụ sau khi rebuild container)
- [x] 4.5 Đối soát uniform-window `Σ=grand_total` đã pass (2.4); auth reuse `require_admin_or_session` như adoption. (spent per-account theo funded_at nên KHÔNG bằng total — đúng thiết kế prepaid)

## 5. Cảnh báo CHECK 2 đổi nghĩa (giữ nguyên CHECK 1)

- [x] 5.1 `_get_provider_spend` giờ delegate `spend_since_funding` (bỏ `date_trunc('month')` + `model_prefixes`). Cập nhật kèm `notification.py` digest (dùng `deposited/remaining`, bỏ "tháng này").
- [x] 5.2 `_check_provider_budget_alerts`: prepaid `used_percent=spent/deposited`; title "Credit X đã dùng N%", message "→ nạp thêm"; dedup key kèm funding epoch (nạp mới re-arm). Test fire 80%/100% ✓.
- [x] 5.3 Diff review: chỉ vùng `_check_provider_budget_alerts`+`_get_provider_spend` đổi; CHECK 1 (`alerts_sent`, `per_user_quota`, `get_user_quota_status`, email user, `mw_users.quota`) nguyên vẹn (15 markers còn đủ).

## 6. Frontend — tab Providers

- [x] 6.1 `index.html`: nút tab `🏭 Providers` + `#providersTab` (4 scorecard + bảng 6 cột). Syntax OK.
- [x] 6.2 `js/providers.js`: fetch `/v1/_mw/providers`, render scorecard + bảng; reuse `.quota-gauge`/`.quota-gauge-fill` cho thanh %, `.metric-card` cho scorecard, `.badge` cho status.
- [x] 6.3 Hint "luôn theo credit hiện tại, KHÔNG theo bộ lọc"; dòng `other` "không có credit cấp"; runway `null` → "chưa đủ dữ liệu".
- [x] 6.4 Đăng ký trong `tabs.js` (import + case `providers`).

## 7. Frontend — Settings 6 ô + nút Nạp/Sửa

- [x] 7.1 `settings.js`: `_renderProviderCredits` render động 6 account từ config, hiện `deposited` + `funded_at` (định dạng VN); HTML section đổi thành container `#providerCreditRows`.
- [x] 7.2 Nút **Nạp thêm** → `POST /v1/_mw/providers/topup` → `topup_provider` set `deposited=remaining+amount`+`funded_at=now` (test dry-run carry-forward: 99.9979+20=119.9979 ✓). Nút **Sửa** → set `deposited` thẳng, giữ `funded_at`.
- [x] 7.3 **Sửa** reuse `_savePartialConfig`→`update_alert_config` (deep-merge, giữ funded_at). **Nạp thêm** handler mỏng reuse `spend_since_funding`+`load/save_alert_config`. main.js exposure cập nhật (`topUpProvider`/`correctProviderCredit`).

## 8. Fix nhất quán Overview

- [x] 8.1 Kiểm tra `overview.js`: thẻ #1 (`ovSpendValue`) **đã dùng cost thật** (`$${cost.toFixed(2)}`), KHÔNG có mock $800/$644 — mock chỉ tồn tại trong prototype HTML, chưa vào code thật. No-op, không cần sửa.

## 9. Nghiệm thu tổng & cập nhật plan

- [x] 9.1 Nghiệm thu: rebuild container OK, healthy, không lỗi import. End-to-end `GET /v1/_mw/providers` (auth 403 unauth / 200 + payload 6 account với admin key) ✓; `POST /topup` openrouter +10 → deposited 110 + funded_at mới ✓; Σ đối soát khớp (2.4). Còn lại: anh eyeball UI tab trên trình duyệt.
- [x] 9.2 CHECK 1 không hồi quy: diff chỉ đụng CHECK 2 (`_check_provider_budget_alerts`/`_get_provider_spend`); `alerts_sent`/`per_user_quota`/`get_user_quota_status`/email user nguyên vẹn (5.3).
- [x] 9.3 Cập nhật `docs/dashboard_metrics_implementation_plan.md` Phase 6: ghi mô hình trả-trước + billing account, tick mục đã làm, Non-Goals, dòng "chờ deploy".
