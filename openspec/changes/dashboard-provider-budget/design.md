## Context

Chi phí LLM là khoản chi lớn nhất của hệ thống nội bộ. Cách vận hành thật là **credit trả trước**: admin nạp tiền vào một tài khoản provider, chia cho nhiều người dùng, cạn thì nạp thêm — không có chu kỳ tháng. Hạ tầng hiện có:

- `mw_audit_log(ts, user_id, model, cost_usd, …)` — nguồn chi tiêu (model = alias client gửi, đã resolve khỏi `*-auto`).
- `core/alerting.py::_get_provider_spend()` — gán chi phí theo `model_prefixes`, cửa sổ `date_trunc('month')`; nuôi CHECK 2 (`_check_provider_budget_alerts`) gửi email admin theo % ngân sách tháng.
- `data/alert_config.json::admin_alerts.api_budgets` — 5 provider theo brand, mỗi cái `{budget_usd, thresholds, model_prefixes}`.
- Settings tab: 5 ô nhập `budget_usd` (`dashboard/js/settings.js`).
- `litellm/litellm_config.yaml` — mỗi `model_name` (alias) → `litellm_params.model` dạng `<provider>/<model>`.
- `api/adoption.py` (Phase 4) — khuôn endpoint chuẩn để bắt chước.

Hai lỗi bản chất phát hiện khi explore: (1) mô hình "ngân sách tháng có reset" sai với vận hành trả-trước; (2) gán chi phí theo prefix alias vừa sót (embedding) vừa sai nơi-trả-tiền (deepseek qua OpenRouter, gemini qua Vertex AI).

## Goals / Non-Goals

**Goals:**
- Gán 100% chi phí về đúng **billing account** (nơi thật sự trả tiền), đối soát khớp tổng với mọi dữ liệu production.
- Cho admin thấy, theo từng account: đã nạp / đã tiêu từ lần nạp / còn lại / **bao giờ cạn (runway)** → chủ động nạp trước khi gián đoạn.
- Một nguồn sự thật cho attribution, dùng chung bởi dashboard và cảnh báo provider (CHECK 2).
- Bám logic production, không gọt theo số dev ([[design-for-production-logic-not-dev-data]]).

**Non-Goals:**
- ❌ Không chạm CHECK 1 (email quota theo user admin cấp): `per_user_quota`, `user_alerts`, `get_user_quota_status`, `mw_users.quota`, `alerts_sent`.
- ❌ Không bảng ledger đầy đủ lịch sử nạp — chỉ 1 mốc `funded_at` gần nhất/account.
- ❌ Không hiện cột burn-rate thô (chỉ dùng ngầm).
- ❌ Không đổi cách `mw_audit_log` được ghi; không migration DB.

## Decisions

### D1 — Provider = billing account, lấy map từ LiteLLM `/model/info` (KHÔNG đọc file yaml)
Billing account = segment đầu của `litellm_params.model` (vd `openrouter/deepseek/…` → `openrouter`). Map `alias → account` dựng lúc chạy bằng cách gọi **LiteLLM `/model/info`** — endpoint admin trả `model_name` + `litellm_params.model` cho mọi model đã deploy.
- **Vì sao KHÔNG đọc `litellm_config.yaml`:** file này **chỉ mount vào container `litellm`** (`docker-compose.yml:64`), **KHÔNG** vào container middleware (volumes `:112-117`) → tiến trình MW không có file để đọc. `/model/info` là nguồn runtime tương đương, phản ánh đúng config đang chạy.
- **Khả thi auth:** MW giữ **master key** của LiteLLM (`LITELLM_MASTER_KEY=${LITELLM_KEY}` và MW nhận `LITELLM_KEY`) → gọi được `/model/info`. Gọi qua `request.app.state.http_client` như `list_models`.
- **Reuse kép:** cùng một call `/model/info` phục vụ cả attribution (D1) lẫn Total Models (D6) — 1 request, 2 việc.
- **Vì sao billing account:** đó là nơi hóa đơn thật gửi về; tự cập nhật khi thêm/bớt model. Prefix tên alias không đáng tin (embedding sót, brand ≠ nơi trả tiền).
- **Thay vì:** (a) prefix `model_prefixes` — đang sai; (b) đọc yaml — file không mount cho MW; (c) map cứng trong code — dễ lệch; (d) `PROVIDER_TIERS` — chỉ phủ 5 chat-auto.
- **Chịu lỗi:** `/model/info` lỗi/timeout → map rỗng → mọi cost rơi `other` (vẫn đối soát đúng, chỉ mất phân tách), không crash.

### D2 — Phân hoạch toàn phần + nhánh catch-all `other`
Mọi `model` không map được rơi vào `other` → `Σ account (kể cả other) ≡ tổng cost`.
- **Vì sao:** alias cũ trong lịch sử audit, model mới chưa kịp phân loại, đều không được làm lệch tổng. Đây là nhánh catch-all bắt buộc theo [[design-for-production-logic-not-dev-data]].

### D3 — Credit trả trước: state `{deposited, funded_at}`/account, không reset lịch
`spent = SUM(cost) WHERE ts >= funded_at`; `remaining = deposited − spent`. Lưu trong `api_budgets[account]` (JSON config đã có GET/POST) — **không bảng mới**.
- **Nạp thêm:** `deposited := remaining_hiện_tại + amount; funded_at := now` (tiền cũ chưa tiêu không mất; đồng hồ tiêu về 0 tự nhiên vì cửa sổ `ts >= funded_at`).
- **Sửa:** `deposited := giá_trị_mới; funded_at` giữ nguyên.
- **Reuse persistence:** dùng `load_alert_config`/`save_alert_config` (core.alerting) đã có. Nút **Sửa** = set thuần → reuse thẳng `update_alert_config` (`/v1/_mw/admin/alerts/config`, **đã deep-merge**, `quota_status.py:88`) gửi partial `{admin_alerts:{api_budgets:{<acct>:{deposited}}}}` — **không route mới, không mất field khác**. Nút **Nạp thêm** cần tính `remaining` server-side (đọc spent) nên là handler mỏng, vẫn reuse `provider_spend` + `load/save_alert_config`.
- **Thay vì:** (a) ledger đầy đủ — nặng, chưa cần; (b) chỉ số tĩnh không mốc — không tính được remaining khi tổng tiêu vượt 1 lần nạp.

### D4 — Runway thay cho "projected cuối tháng"
`burn = spent / days_since_funded_at` (giờ VN); `runway_days = remaining / burn`. Dưới `MIN_DAYS_FOR_RUNWAY` (đề xuất 2) → trả `null` ("chưa đủ dữ liệu") thay vì số phóng đại.
- **Vì sao:** mô hình trả-trước quan tâm "bao giờ cạn để nạp", không phải "cuối tháng vượt bao nhiêu". Burn-rate hồi sinh nhưng chỉ là động cơ nội bộ, không phải cột hiển thị.

### D5 — Một hàm attribution dùng chung (`core/provider_attribution.py`)
`build_model_provider_map()` + `provider_spend(funded_at_by_account, now)` → dùng bởi cả `api/providers.py` và `_check_provider_budget_alerts` (đọc `funded_at` từ `api_budgets`). CHECK 2 đổi điều kiện sang "sắp cạn credit"; bỏ `date_trunc('month')`.
- **Vì sao:** khi đã chuyển sang billing account, config `api_budgets` (nguồn của alert) buộc đổi theo → không tồn tại phương án "chỉ dashboard". Chung hàm ⇒ alert và dashboard không bao giờ lệch số.
- **Ranh giới:** chỉ ruột CHECK 2 đổi; CHECK 1 (quota-user) không đụng một dòng.

### D6 — Total Models reuse chính call `/model/info` của D1
Đếm số `model_name` trả về từ `/model/info` (đã gọi cho attribution). **KHÔNG trừ 5 auto:** grep `auto` trong `litellm_config.yaml` = trống → LiteLLM **không** chứa model `*-auto`, chúng do MW `list_models` inject cho user. Nguồn admin thật không có auto để trừ; vẫn dùng `_AUTO_MODEL_NAMES` làm bộ lọc phòng thủ (loại nếu tình cờ xuất hiện). KHÔNG dùng `list_models` (nó `require_user` + lọc `allowed_models` → số theo user).

### D7 — Tab Providers không theo bộ lọc thời gian
Cả tab đo credit hiện tại (trả-trước), như thẻ Cost MTD. Ghi hint rõ để không tưởng lệch là bug. Không badge KT/CK v1 (theo tiền lệ Phase 5: cột bảng ≠ scorecard).

## Risks / Trade-offs

- **[Đổi tên provider brand→billing làm dedup key `provider_<tên>_<ngưỡng>` cũ thành rác]** → dọn `system_alerts` các key `provider_*` một lần khi deploy; alert mới tự tạo key mới.
- **[Migrate `api_budgets` 5 brand → 6 billing account]** → cung cấp bước migrate config có kiểm soát (map openai→openai, gemini→gemini, thêm vertex_ai/openrouter, bỏ deepseek-brand); giữ backup `alert_config.json`.
- **[Phụ thuộc LiteLLM `/model/info` + master key]** → nếu key/endpoint đổi, map rỗng → mọi cost rơi `other` (vẫn đối soát đúng, chỉ mất phân tách), không crash; log cảnh báo để phát hiện.
- **[Runway nhiễu đầu kỳ / cuối tuần nội bộ tụt tải]** → chặn `MIN_DAYS_FOR_RUNWAY` và `burn==0`, nhãn "ước tính"; đây là tín hiệu cảnh báo sớm, không phải dự toán kế toán.
- **[Nạp thêm khi tiền cũ chưa cạn]** → công thức `deposited := remaining + amount` giữ đúng phần chưa tiêu; test kịch bản nạp-khi-còn-dư.

*(Đã loại rủi ro "Save Settings ghi đè mất field": `update_alert_config` **deep-merge** `quota_status.py:88` nên partial update KHÔNG rơi field khác.)*

## Migration Plan

1. Thêm `core/provider_attribution.py` (map + spend), có test đối soát Σ=total trên dữ liệu hiện có.
2. Migrate `data/alert_config.json::api_budgets` sang 6 billing account, thêm `funded_at` (mặc định = thời điểm migrate), giữ backup.
3. Sửa `_get_provider_spend`/`_check_provider_budget_alerts` gọi hàm chung, bỏ `date_trunc('month')`, dọn dedup key cũ.
4. Thêm `api/providers.py` + route `main.py`; nghiệm thu Σ khớp `/v1/_mw/summary` total cost.
5. Dashboard: tab + `js/providers.js`; Settings 6 ô + nút Nạp/Sửa; sửa Overview thẻ #1.
6. **Rollback:** khôi phục `alert_config.json` backup; gỡ route + tab (file mới độc lập, không đụng đường ghi audit). CHECK 1 không liên quan nên không có rủi ro hồi quy quota-user.

## Open Questions

- Ngưỡng cảnh báo cạn credit theo % còn lại (vd ≤10%) hay theo runway (vd ≤3 ngày), hay cả hai? (chốt khi apply)
- `MIN_DAYS_FOR_RUNWAY` = 2 có hợp lý cho nhịp dùng nội bộ không? (kiểm chứng khi có dữ liệu thật)
- Có cần cột "đã tiêu tháng này" phụ cho báo cáo, hay thuần trả-trước là đủ? (mặc định: thuần trả-trước)
