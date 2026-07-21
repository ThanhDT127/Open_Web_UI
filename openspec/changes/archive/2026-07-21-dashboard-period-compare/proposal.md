## Why

Leader yêu cầu dashboard "có so sánh cùng kỳ/kỳ trước" cho "tất cả các chỉ tiêu nếu tính được". Hiện tại **toàn hệ thống có 0 dòng logic so sánh kỳ** — không có param, không có field, không có CSS `.delta-badge`. Đây là Phase 2 của `docs/dashboard_metrics_implementation_plan.md`, và là nền cho gần như mọi phase sau (mọi thẻ có trục thời gian đều cần badge này), nên phải đứng sớm dù không phải chỉ tiêu "nhìn thấy" đầu tiên.

## What Changes

**Luật kỳ thống nhất — 2 dòng, không ngoại lệ**

- `KT` (kỳ trước) = `[start − Δ, start)` với `Δ = end − start`. Số học thuần trên timestamp.
- `CK` (cùng kỳ) = `[start − 1 năm, end − 1 năm]`, kẹp `29/02 → 28/02`.
- Áp cho **mọi** khoảng: 5 nút preset, khoảng tuỳ ý từ 2 ô `datetime-local`, và cả thẻ neo lịch (Cost MTD).
- ⚠️ **Thay thế luật trong plan/addendum v2.** Plan cũ ghi `CK: 1h→lùi 24h · 1d→lùi 7d · 7d→lùi 28d`. Luật đó (a) không phủ nút `6h`/`30d`, (b) không có câu trả lời cho khoảng tuỳ ý, (c) dùng sai thuật ngữ — trong nghiệp vụ Việt Nam **"cùng kỳ" mặc định là cùng kỳ năm trước (YoY)**, còn "kỳ trước" là kỳ liền kề. Neo theo ngày lịch + kẹp 29/02 là cách Power BI (`SAMEPERIODLASTYEAR`), GA4 và Adobe Analytics đều dùng.

**Kiến trúc: phép tính cửa sổ nằm ở frontend, backend không đổi 1 dòng**

- Đã xác minh: **cả 6 module API dashboard đều nhận sẵn `start`/`end` tuyệt đối** (`summary_v2`, `analytics` ×2, `group_analytics` ×2, `access_logs`, `rag_health` ×3, `knowledge_analytics` ×3). Hỏi backend về một kỳ quá khứ hôm nay đã làm được.
- Nên frontend tự tính 3 cửa sổ rồi gọi song song 3 lần (1 lần đã có sẵn + 2 lần mới), tính delta ở client.
- Đổi lại: **không** thêm param `compare=1`, **không** tách hàm gom khỏi `analytics.py`/`group_analytics.py`, **không** phải hợp nhất 5 resolver range phân kỳ trước, **không** chạm `export_report.py` (consumer thứ 3 của summary shape).

**Hạ tầng frontend mới**

- Module giữ luật kỳ (một nguồn chân lý duy nhất cho "kỳ trước/cùng kỳ là từ đâu đến đâu").
- `buildRangeParams()` — gom **11 chỗ** đang tự dựng `URLSearchParams` từ `currentTimeRange`, và ghim **một mốc `now` cho mỗi chu kỳ refresh** để mọi tab dùng chung đúng một cửa sổ (checklist v2: "thẻ trùng chỉ tiêu giữa 2 tab phải trùng số").
- **Metric registry** — bảng khai báo duy nhất cho mỗi chỉ tiêu: nhãn, định dạng (`$`/`%`/`ms`/số), kiểu delta (tương đối / điểm % / tuyệt đối), cực tính (tăng=tốt / tăng=xấu / trung tính), và cờ **chặn so sánh** cho field snapshot.
- `renderDelta()` sinh markup `.delta-badge` (2 dòng CK/KT + giá trị tuyệt đối trong ngoặc).

**Hiển thị**

- Badge **luôn in kèm mốc thật** của cửa sổ đang so (`KT: 20/02–05/03/2026`), thay cho luật ẩn ngầm.
- Ẩn CK **chỉ khi không có dữ liệu** → `CK: —` màu mờ (`d-dim`). Dữ liệu năm trước hiện rỗng (`mw_audit_log` có dòng đầu tiên **04/05/2026**, đã đo trên DB 2026-07-20) nên CK sẽ là `—` tới ~05/2027; test bằng mock.
- ⚠️ **Bỏ luật "chồng lấn KT > 80% → ẩn CK"** trong plan dòng 60: nó suy ra từ mô hình shift cũ đã bị thay, và không công cụ BI lớn nào (GA4, Adobe) có luật chặn tương tự.
- Gắn dấu ⚠️ khi độ dài 2 cửa sổ lệch nhau (ca năm nhuận, 4 năm/lần).

**Phạm vi wiring**

- Trong change này: 6 thẻ tab **Usage** (Requests, Cost, Tokens, P95, Error Rate, Billable) → **chốt hình dạng với leader tại đây**, rồi tab **Overview** (khớp số với Usage) và **Chat Analytics**.
- **Không nằm trong phạm vi**: các tab phụ thuộc phase chưa làm (Providers/Phase 6, Groups/Phase 7, Satisfaction/Phase 8, RAG Health/Phase 9, Access & Logs/Phase 10); CK/KT trong file export; hợp nhất 5 resolver range ở backend (dọn nợ riêng, không còn chặn change này); Việt hoá nhãn (Phase 11 — registry ở đây làm việc đó rẻ đi, nhưng không thực hiện).

## Capabilities

### New Capabilities

- `dashboard-period-compare`: Luật xác định cửa sổ kỳ trước/cùng kỳ cho mọi khoảng thời gian của dashboard, quy tắc ghim cửa sổ dùng chung giữa các tab, và hiển thị `.delta-badge` (2 dòng, mốc tường minh, trạng thái không-có-dữ-liệu).
- `dashboard-metric-registry`: Bảng khai báo tập trung cho chỉ tiêu scorecard — nhãn, định dạng giá trị, kiểu delta, cực tính màu, và cờ chặn so sánh cho field không thuộc phạm vi khoảng thời gian.

### Modified Capabilities

<!-- Không có. `analytics-date-filtering` vẫn giữ nguyên yêu cầu (endpoint nhận và tuân thủ `minutes`/`start`/`end`); change này chỉ thêm cửa sổ so sánh ở tầng gọi, không đổi hợp đồng của endpoint. -->

## Impact

- **Backend** — **0 dòng**. Không thêm endpoint, không thêm param, không đổi response shape, không đụng schema DB. `export_report.py` (đang gọi `get_summary_v2`) an toàn tuyệt đối.
- **Frontend mới** — module luật kỳ + `buildRangeParams()` + metric registry + `renderDelta()`.
- **Frontend sửa** — `filters.js` (ghim khoảng tuyệt đối theo chu kỳ refresh); 11 chỗ dựng param chuyển sang dùng `buildRangeParams()`: `access.js`, `analytics.js`, `export.js`, `group_analytics.js`, `knowledge.js`, `logs.js`, `overview.js`, `raghealth.js`, `satisfaction.js`, `usage.js`; `usage.js` + `overview.js` + `analytics.js` gắn badge.
- **CSS** — `dashboard.css`: thêm `.delta-badge` / `.delta-line` / `.d-green` / `.d-red` / `.d-dim` / `.d-neutral` / `.delta-abs` theo snippet đã chuẩn bị ở `docs/dashboard_frontend_harvest.md` §2E. Xác minh: các class này **chưa tồn tại**.
- **Tải hệ thống** — mỗi lần đổi khoảng/mở tab phát sinh thêm 2 request song song/tab. `mw_audit_log` ~4,2k dòng (mốc 17/07/2026) nên không đáng kể; badge **không** gọi lại theo nhịp poll 15s vì CK/KT là số của kỳ đã đóng.
- **Tài liệu** — cần cập nhật `docs/dashboard_metrics_implementation_plan.md` (Phase 2) và `docs/dashboard_prototype_prompt_addendum_v2.md` (quyết định #9) vì luật kỳ ở đó đã bị thay.
