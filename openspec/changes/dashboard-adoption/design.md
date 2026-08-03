## Context

Phase 4 trả câu hỏi adoption của hệ nội bộ. Nó chạm hai miền dữ liệu khác bản chất, và **nhầm lẫn ranh giới này là nguồn lỗi lớn nhất**:

```
MIỀN HOẠT ĐỘNG (activity)          MIỀN DANH SÁCH (roster)
nguồn: mw_audit_log                 nguồn: mw_users
scope: THEO CỬA SỔ [start,end]      scope: SNAPSHOT toàn bảng
→ compute_usage_summary() gom sẵn   → chưa hàm nào gom cho dashboard

• ai active trong kỳ                • ai đã được cấp (deleted_at IS NULL)
• DAU/WAU                            • created_at → cấp mới trong kỳ
• Pareto (đã có top10 share)         • quota JSONB → histogram mức dùng
```

Hạ tầng sẵn có để reuse: `compute_usage_summary` (`summary_v2.py`) trả `breakdown_by_user` (full, đã bỏ cắt `[:20]` sau `unify-audit-aggregation`) + `top10_pct_cost_share` + `cost_total_usd`; `get_user_quota_status` (`alerting.py`) có công thức `used/limit%`; `metrics_registry.js` + `renderDelta()` (Phase 2) lo badge so kỳ. Số dòng đã trôi sau refactor — mọi tham chiếu bám **tên hàm/biến**, không bám số dòng.

**Context vòng đời user (chi phối mọi query roster):** middleware **chỉ xóa mềm trong vận hành** ([[middleware-soft-delete-only]]) — `deleted_at` set, dòng `mw_users` được giữ để phục vụ dữ liệu lịch sử. Xóa cứng (`?purge`) chỉ dành cho erasure pháp lý, không phải luồng thường; dòng đã xóa cứng hiện có là dữ liệu rác lúc thử nghiệm. Vì vậy: "đã cấp" = `deleted_at IS NULL`; "cấp mới trong kỳ" không lọc `deleted_at` (D4b); và audit có thể chứa user không còn trong roster (đã purge lúc test) → phép giao ở D3 tự xử lý.

## Goals / Non-Goals

**Goals:**

- Một endpoint `/adoption` trả trọn miền roster + chỉ tiêu adoption, REUSE `compute_usage_summary` cho miền hoạt động.
- Gỡ 2 placeholder Overview của Phase 1 bằng số thật.
- Badge so kỳ chạy "miễn phí" cho chỉ tiêu windowed; chỉ tiêu snapshot khai `compare:false`.
- Không bảng mới, không migration, **không đổi `compute_usage_summary`**.

**Non-Goals:**

- Nút "nhắc đào tạo"/gửi thông báo cho tài khoản ngủ — bảng read-only, để phase sau.
- WAU/MAU ở độ phân giải khác ngày; DAU/WAU trên range < 1 ngày.
- Việt hoá nhãn (Phase 11); sửa nợ timezone Cost MTD (Phase 6).
- Phân tích nội dung/chất lượng câu hỏi người dùng ([[dashboard-scope-no-nlp-content-analysis]]).

## Decisions

### D1 — Phương án B: module roster riêng, reuse `compute_usage_summary` cho activity

`api/adoption.py` mới. Nó **gọi** `compute_usage_summary(cutoff, end, ...)` để lấy miền hoạt động (tử số adoption, cost để tính chi phí/người dùng thật, dữ liệu Pareto), rồi query `mw_users` cho miền roster, rồi merge.

*Vì sao không nhồi `mw_users` vào `compute_usage_summary`:* docstring hàm đó ghi rõ *"single aggregation implementation for mw_audit_log"* — thuần audit, thuần theo cửa sổ. Thêm JOIN roster vào đó là phá hợp đồng và bắt **mọi** caller Usage/Chat gánh thêm một truy vấn không liên quan. Tách module giữ mỗi bên đúng scope.

### D2 — DAU/WAU lấy từ query gom `(ngày, user)` riêng, KHÔNG thêm field vào `compute_usage_summary`

**Đây là chỗ lệch có chủ đích so với plan gốc.** Plan Phase 4 viết *"cần thêm một set user/bucket (field mới thật)"* vào `timeseries_data`. Sau khi đọc code, quyết định **không** làm vậy:

- WAU là **hợp distinct trượt 7 ngày** — *không cộng được từ DAU*. Một người vào cả T2 lẫn T3: DAU đếm 2 (mỗi ngày 1), WAU chỉ đếm 1. Nên WAU buộc phải có nguồn theo **tập** ngày, không phải số đếm/bucket.
- Nếu để `compute_usage_summary` emit set user/bucket đủ cho WAU thì hoặc (a) trả **danh sách user/bucket** (payload phồng theo user×ngày), hoặc (b) nhồi khái niệm "cửa sổ trượt" vào hàm gom dùng chung — cả hai đều làm nặng/bẩn hot path Usage+Chat.
- Một query `SELECT ts::date AS d, user_id FROM mw_audit_log WHERE ts ∈ [start−6d, end] GROUP BY d, user_id` cho ra **cặp (ngày,user) đã dedupe ở SQL** (nhỏ). Từ đó Python dựng: DAU = đếm theo ngày, WAU = |hợp 7 tập ngày gần nhất|. Lùi biên trái 6 ngày để ngày hiển thị đầu tiên vẫn đủ cửa sổ 7 ngày.

*Đánh đổi (ghi rõ):* một lần quét `mw_audit_log` thêm, thay vì bám vòng lặp của `compute_usage_summary`. Chấp nhận vì: query trả cặp đã dedupe (nhẹ ở quy mô nội bộ), và **giữ `compute_usage_summary` bất biến** — hàm mà cả Usage lẫn Chat Analytics phụ thuộc — là hàng rào rủi ro đáng giá hơn việc tiết kiệm một scan.

### D3 — Adoption rate: giao với roster hiện tại, mẫu số snapshot (Q1a)

`adoption_rate = |active_trong_kỳ ∩ roster_hiện_tại| / |roster_hiện_tại|`. Mẫu số = `COUNT(*) FROM mw_users WHERE deleted_at IS NULL` (snapshot). Tử số = user active trong kỳ (từ `breakdown_by_user`) **giao** với tập `user_id` của roster đó.

*Vì sao phải giao, không lấy thẳng `len(breakdown_by_user)`:* theo [[audit_log_immutability_preference]], `compute_usage_summary` **không** lọc user đã xóa — `breakdown_by_user` gồm cả user đã bị xóa nhưng còn hoạt động lịch sử. Nếu tử số gồm họ mà mẫu số (`deleted_at IS NULL`) lại loại họ thì **tỷ lệ có thể vượt 100%**. Lấy giao giữ cả hai vế trên cùng một tập "nhân sự hiện tại" → rate luôn ∈ [0,100]. Phép giao làm trong Python trên tập roster vốn đã query cho mẫu số → **không thêm query**.

*Không nhầm với leaderboard hiển thị:* `get_summary_v2` cắt `breakdown_by_user[:20]` nên bảng leaderboard tab Users chỉ hiện tối đa 20 dòng. Tử số adoption tính trên **toàn** population (full list từ `compute_usage_summary`, trước cắt) — cùng *định nghĩa* "user có hoạt động trong kỳ", không phải "bằng số dòng leaderboard hiển thị".

*Hệ quả so kỳ (trung thực):* tử số theo cửa sổ nên **badge KT/CK vẫn có nghĩa** (active kỳ này vs kỳ trước), nhưng mẫu số dùng chung một snapshot cho cả hai kỳ. Đây là định nghĩa đơn giản anh Tuấn đã chọn ("bao nhiêu % nhân sự hiện tại đang dùng"). Bản cohort (mẫu số `created_at ≤ end`) để ngỏ, đổi sau chỉ là thêm một điều kiện `WHERE`.

*Tử số đếm cả user chỉ-lỗi:* nhánh `error` trong `compute_usage_summary` vẫn `user_data[user_id]...add(rid)`, nên `breakdown_by_user` gồm cả người có hoạt động nhưng toàn lỗi. Điều này ĐÚNG với "đã dùng hệ thống" (họ có gọi, dù thất bại). Ghi rõ để không ai coi là bug.

*Hai định nghĩa "active" cùng tồn tại trong endpoint (cố ý):* `active_provisioned` = giao roster (tử số adoption, ≤ mẫu số); `active_users` = raw từ audit, gồm cả user đã xóa (dùng cho chuỗi DAU/WAU và `cost_per_active_user` — xem D8). Chart hoạt động và chi phí/người dùng bám audit immutability; tỷ lệ adoption bám roster hiện tại. Trả cả hai số kèm nhãn rõ.

### D4 — Chuỗi luôn theo NGÀY, độc lập bucket auto của Usage

Endpoint `/adoption` dựng chuỗi DAU/WAU ở độ phân giải **ngày cố định**, bất kể tab Usage đang auto-bucket minute/hour/day. Range < 1 ngày → chuỗi rỗng, frontend ẩn chart (không vẽ WAU vô nghĩa trên vài giờ).

*Biên ngày theo giờ Việt Nam:* ranh giới "ngày" phải khớp lịch UTC+7 như Phase 2, nếu không DAU sẽ cắt sai chỗ (một ngày làm việc bị tách đôi qua nửa đêm UTC). Container Postgres chạy `TZ: Asia/Ho_Chi_Minh` nên `ts::date` đã ra ngày địa phương — spike task 1 xác nhận session TimeZone trước khi tin.

### D4b — Cấp mới trong kỳ: không lọc `deleted_at` (chống xói mòn)

`new_accounts_in_period = COUNT(*) WHERE created_at ∈ [start,end]`, **không** thêm `deleted_at IS NULL` (cũng không lọc `active`). Một sự kiện cấp tài khoản đã xảy ra trong kỳ thì việc xóa/disable về sau không nên làm co lại con số của kỳ quá khứ — đúng nguyên tắc [[audit_log_immutability_preference]] và cái bẫy xói mòn Phase 2 nêu (dữ liệu quá khứ nghiêng thấp một cách hệ thống khi so kỳ).

*Vì sao KHÔNG còn "giới hạn hard-delete":* middleware **chỉ xóa mềm trong vận hành** ([[middleware-soft-delete-only]]) — `delete_user_endpoint` mặc định gọi `soft_delete_user` (`SET deleted_at=now()`, **giữ dòng**). Đường `?purge=true` → `DELETE FROM mw_users` chỉ dành cho erasure pháp lý, **không phải luồng vận hành**; các dòng đã xóa cứng đang tồn tại chỉ là **dữ liệu rác lúc thử nghiệm** khi implement tính năng xóa mềm. Vì dòng xóa mềm còn nguyên, `COUNT(created_at)` đếm đủ ở **mọi kỳ** và con số quá khứ ổn định theo thời gian → so kỳ trung thực.

*Mốc cohort ổn định:* `created_at` set một lần lúc lazy-provision; conflict re-provision chỉ `DO UPDATE SET active/updated_at`, **không đụng `created_at`** (`auth.py`) → không trôi.

### D5 — Tài khoản ngủ: hai loại từ một query `max(ts)/user`, snapshot, chặn so kỳ

`SELECT user_id, max(ts) AS last_seen FROM mw_audit_log GROUP BY user_id`, LEFT-đối chiếu roster `mw_users (deleted_at IS NULL)`:

- `last_seen IS NULL` (không khớp) → **chưa bao giờ dùng**.
- `last_seen < now − N ngày` → **ngừng dùng lâu** (N mặc định **30**, hằng số cấu hình được).

Bảng trả về: email, `created_at`, `last_seen` (hoặc "chưa bao giờ"), số ngày im lặng (`now − last_seen`, hoặc `now − created_at` nếu chưa bao giờ), `active`. Sắp xếp im-lặng giảm dần. Là snapshot roster → **`compare:false`** (giống `pending_open_count` Phase 3).

*Ngưỡng 30 ngày:* một chu kỳ tháng, đủ để lọc người thật sự bỏ dùng khỏi người dùng-khi-cần. Để hằng số backend, đổi không cần re-deploy logic.

### D6 — Histogram quota: reuse công thức `used/limit`, tách bucket "không giới hạn"

`SELECT user_id, quota FROM mw_users WHERE deleted_at IS NULL`; mỗi user tính `percent = used_cost_usd / limit_cost_usd × 100` theo đúng `get_user_quota_status` (`alerting.py`). Bucket: `0–25 / 25–50 / 50–75 / 75–90 / >90`. User `limit_cost_usd ≤ 0` = **không giới hạn** → bucket riêng, **không** ép vào 0–25 (nếu không histogram sẽ bị thổi phồng nhóm thấp bởi người vốn không có trần). Snapshot → `compare:false`.

### D7 — Cực tính & registry

- `adoption_rate_percent` — **up-good** (dùng nhiều hơn là tốt cho hệ nội bộ).
- `new_accounts_in_period` — **neutral** (`d-neutral`; cấp nhiều/ít không tự nó tốt-xấu).
- `dormant_count` — **down-good** (ít người ngủ hơn là tốt) nhưng snapshot nên **không** so kỳ; chỉ dùng cực tính cho màu tĩnh nếu cần.
- `cost_per_active_user` — **neutral**.

Mỗi chỉ tiêu = một dòng khai báo trong `METRICS`, wiring theo khuôn `_COMPARE_CARDS`.

### D8 — Gỡ 2 placeholder Overview bằng số reuse

`ovCardAdoption` = `adoption_rate_percent` (reuse). `ovCardCpu` (`Chi phí / người dùng thật`) = `cost_total_usd / active_users` — mẫu số là **`active_users` raw** (mọi người thực sự đã dùng, kể cả user đã xóa vẫn tốn chi phí thật; không phải `active_provisioned` của tỷ lệ adoption, xem D3), tử số `cost_total_usd` từ `compute_usage_summary`. Guard mẫu 0. Cả hai đọc từ cùng response `/adoption`, không thêm nguồn.

## Risks / Trade-offs

- **Định danh roster↔audit** — nếu `mw_users.user_id` không phải cùng email `mw_audit_log.user_id` cho mọi user thì phép hiệu/chia lệch. *Mitigation:* spike task 1.1 — kiểm một mẫu JOIN trước khi code; đây chính là chỗ [[chat-analytics-id-mismatch]] cảnh báo (nhưng ở đây cả hai là email nên kỳ vọng khớp).
- **`created_at` ≠ ngày tuyển** — nó là ngày lazy-provision (auth đầu). *Mitigation:* nhãn "Tài khoản cấp mới trong kỳ", không phải "Nhân viên mới" ([[design-for-production-logic-not-dev-data]]).
- **Một scan audit thêm cho DAU/WAU** (D2). *Mitigation:* query trả cặp đã dedupe; đo thật trên range 30d trước khi chốt; nếu nặng bất ngờ thì mới cân nhắc chuyển vào `compute_usage_summary`.
- **Histogram quota lệ thuộc chất lượng field `quota`** — nếu nhiều user `quota={}` thì phần lớn rơi "không giới hạn". *Mitigation:* đó là hiện trạng thật, hiển thị trung thực; không bịa trần.
- **Adoption mẫu số snapshot** làm badge KT/CK hơi bất đối xứng (D3). *Mitigation:* chấp nhận theo Q1a; ghi chú rõ; đường nâng cấp cohort để ngỏ.

## Migration Plan

Thuần thêm mới; không migrate dữ liệu, không đổi schema.

1. Spike: xác minh JOIN email roster↔audit, đơn vị/`created_at`, field `quota`.
2. Backend: module `api/adoption.py` + route `main.py`. Nghiệm thu: `/adoption` trả đủ khối, số khớp tính tay trên một cửa sổ; tử số adoption = `|active ∩ roster|` (≤ mẫu số, rate ≤ 100%).
3. Frontend: registry + `adoption.js` (namespace `adoptionAPI`), chart DAU/WAU + Pareto + bảng ngủ trên tab Users, gỡ 2 placeholder Overview. Nghiệm thu: badge windowed đúng; ngủ/histogram không badge; 2 thẻ Overview hết "—".

*Rollback:* gỡ route + file mới; tab Users/Overview trở lại trạng thái trước, không dữ liệu nào bị đụng.

## Open Questions

- **WAU vs chỉ DAU** — chốt WAU làm đường chính, DAU phụ mờ; nếu chỉ cần DAU thì bỏ luôn phần cửa sổ trượt (rẻ hơn).
- **Ngưỡng ngủ 30 ngày** — để hằng số; có cần đưa lên UI cho leader chỉnh không (mặc định: không, để sau).
- **Adoption cohort** — có nâng lên mẫu số `created_at ≤ end` cho so kỳ chuẩn hơn không, hay giữ snapshot Q1a?
