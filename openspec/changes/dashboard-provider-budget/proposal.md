## Why

Phase 6 của `docs/dashboard_metrics_implementation_plan.md` — **Provider: ngân sách chủ động**. Câu hỏi quản lý: *mỗi nhà cung cấp còn bao nhiêu credit, provider nào sắp cạn để nạp thêm trước khi gián đoạn?* Chi phí gọi LLM là khoản chi lớn nhất của hệ thống nội bộ, nhưng dashboard hiện **không có** chỗ nào nhìn được credit/chi tiêu theo provider — chỉ có cảnh báo email khi chạm ngưỡng (reactive), không có cái nhìn tổng chủ động.

Khi đào code, lộ ra hai vấn đề bản chất buộc phải xử lý đúng ngay từ đầu:

1. **Mô hình sai:** ngân sách provider hiện được hiểu là "trần theo tháng, reset đầu tháng" (`_get_provider_spend` dùng `date_trunc('month')`, Settings ghi "monthly budget"). Thực tế vận hành là **credit trả trước**: admin nạp tiền vào một tài khoản provider, chia cho nhiều người dùng, cạn thì nạp thêm — **không có chu kỳ reset**.
2. **Gán chi phí sai:** provider hiện gán theo prefix tên alias (`model_prefixes` như `chat-gemini`), nhưng tên model không theo một quy tắc prefix duy nhất (`gemini-embedding-002` không khớp `chat-gemini`) và không phản ánh **nơi thật sự trả tiền** (deepseek chạy qua OpenRouter, gemini có model qua Vertex AI). Nguồn sự thật là `litellm/litellm_config.yaml` (segment đầu của `litellm_params.model` = billing account).

Thiết kế bám logic production, không gọt theo dữ liệu dev ([[design-for-production-logic-not-dev-data]]).

## What Changes

- **BREAKING (khái niệm):** Ngân sách provider chuyển từ *trần-theo-tháng-reset* sang **credit trả trước, không reset**. Metric đổi theo: `Số dư nạp` / `Đã tiêu (từ lần nạp gần nhất)` / `Còn lại (%)` / `Dự kiến cạn (runway)`.
- **Attribution dùng chung:** thêm `core/provider_attribution.py` — dựng map `alias → billing account` từ **LiteLLM `/model/info`** (MW giữ master key; `litellm_config.yaml` không mount vào MW nên không đọc trực tiếp), có **nhánh catch-all "Khác"** để Σ mọi provider luôn bằng tổng chi phí với bất kỳ dữ liệu production nào. Dùng chung bởi cả dashboard **và** cảnh báo ngân sách provider (CHECK 2) → hai nơi không bao giờ lệch số.
- **6 billing account** thay cho 5 brand: `openai · gemini · vertex_ai · anthropic · xai · openrouter`.
- **Endpoint mới** `GET /v1/_mw/providers` — trả credit/chi tiêu/runway theo provider + `total_models`.
- **Tab Providers mới** trong dashboard: hàng scorecard (Số provider · Tổng còn lại · Tổng đã tiêu · **Total Models**) + bảng credit theo provider. Cả tab đo theo credit hiện tại, không theo bộ lọc thời gian.
- **Total Models** (chuyển từ Phase 1): đếm server-side, **reuse chính call `/model/info`** của attribution (LiteLLM không chứa model `*-auto` — chúng do MW inject — nên không trừ 5).
- **Settings:** migrate 5 ô ngân sách brand → 6 ô billing account, mỗi ô có **nút "Nạp thêm"** (đóng dấu `funded_at = now`, cộng credit) và **nút "Sửa"** (chỉnh số nhập nhầm, GIỮ `funded_at`).
- **Cảnh báo CHECK 2** (`_check_provider_budget_alerts`) đổi nghĩa: từ "% ngân sách tháng" → "sắp cạn credit → nạp thêm"; bỏ `date_trunc('month')`; dọn dedup key cũ khi đổi tên provider.
- **Fix nhất quán:** thẻ Overview #1 dùng số thật, bỏ mock projected $800/$644.

**Non-Goals (ghi rõ để không phá nhầm):**
- ❌ **KHÔNG đụng CHECK 1** — email cảnh báo khi người dùng vượt hạn mức quota admin cấp (tab User & Quota Status): `per_user_quota`, `user_alerts`, `get_user_quota_status`, `mw_users.quota`, `alerts_sent` giữ nguyên hoàn toàn. Đây là hệ tách biệt, chỉ tình cờ nằm chung `check_and_send_alerts`.
- ❌ Không dựng bảng ledger đầy đủ lịch sử nạp — chỉ lưu 1 mốc `funded_at` gần nhất/provider.
- ❌ Không hiện cột burn-rate thô — chỉ dùng ngầm để suy runway.

## Capabilities

### New Capabilities
- `dashboard-provider-budget`: Cái nhìn credit trả trước theo billing account trên dashboard — attribution alias→provider từ LiteLLM `/model/info` (có catch-all), endpoint `/v1/_mw/providers`, các chỉ tiêu số dư nạp / đã tiêu-từ-nạp / còn lại / runway, Total Models, và ngữ nghĩa mới của cảnh báo ngân sách provider (CHECK 2).

### Modified Capabilities
- `system-settings-ui`: Mục "provider API budgets" đổi từ *monthly USD budget theo brand* sang *credit trả trước theo billing account* với thao tác Nạp thêm (đóng dấu `funded_at`) vs Sửa (giữ `funded_at`); danh sách provider đổi sang 6 billing account.

## Impact

- **Code mới:** `core/provider_attribution.py`, `api/providers.py`, `dashboard/js/providers.js`.
- **Code sửa:** `core/alerting.py` (`_get_provider_spend`, `_check_provider_budget_alerts` — chỉ nhánh CHECK 2), `data/alert_config.json` (cấu trúc `api_budgets` theo billing account + `funded_at`), `dashboard/index.html` (tab + nút tab Providers), `dashboard/js/settings.js` (6 ô + nút Nạp/Sửa), `main.py` (route `/v1/_mw/providers`), `dashboard/js/overview.js` (thẻ #1).
- **Nguồn sự thật:** LiteLLM `/model/info` (phản ánh `litellm_config.yaml` đang chạy) là nguồn map provider — thêm/bớt model tự phản ánh vào attribution, không cần mount file vào MW.
- **Không migration DB** (dùng lại `mw_audit_log.cost_usd`/`model`/`ts`); state credit lưu trong `api_budgets` (JSON config, đã có sẵn cơ chế GET/POST).
- **Không đụng** CHECK 1 quota-user, `mw_users`, Open WebUI DB.
