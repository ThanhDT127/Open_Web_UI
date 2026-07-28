# Design — unify-group-aggregation (Phase 7a)

## Context

`api/group_analytics.py` là mã còn lại từ change `2026-07-02-group-analytics-dashboard`, viết **trước khi** `compute_usage_summary` trở thành nguồn gom duy nhất cho `mw_audit_log`. Đợt `unify-audit-aggregation` (2026-07-20) chuẩn hóa Chat Analytics nhưng không nhắc tới groups, nên file này giữ nguyên bốn khác biệt so với chuẩn:

| Điểm                | Groups hiện tại                                            | Chuẩn (`compute_usage_summary`)                        |
|---------------------|------------------------------------------------------------|--------------------------------------------------------|
| Đơn vị đếm request  | `+= 1` mỗi **dòng** (`group_analytics.py:78`)              | `len(rid_status)` — **rid duy nhất**                   |
| Lọc trạng thái      | **không có** — `error`/`pending` đều cộng tiền/token        | chỉ `ok`/`reconciled` mới cộng                         |
| Avg latency         | `Σ latency ÷ Σ dòng` (`:92`) — mẫu số gồm dòng không latency | gom list latency riêng, bỏ giá trị rỗng               |
| Resolver thời gian  | `analytics._time_boundaries` — nuốt lỗi, rơi về 30 ngày     | `_resolve_range` — `raise HTTPException(400)`          |

Ba dòng đầu cùng họ với lỗi D5 phát hiện ở Phase 6 (`spend_since_funding` thiếu lọc status). Dòng cuối là nợ kỹ thuật #1 trong `docs/dashboard_metrics_implementation_plan.md`.

**Đường tái dùng đã có sẵn, chỉ chưa ai nối.** Docstring của `compute_usage_summary` ghi rõ *"Breakdown lists are returned UNTRUNCATED; callers decide whether to cap them"* — tức `breakdown_by_user` đầy đủ đã được thiết kế cho đúng loại caller này:

```
   compute_usage_summary(cutoff, end, bucket)
        │
        ├── totals.cost_total_usd ──────────────┐  mẫu số chuẩn (7b sẽ dùng)
        │                                        │
        └── breakdown_by_user[]                  │
              user_id (email) · cost · requests  │
              tokens · p95 · top_model           │
                    │                            │
                    │  ánh xạ email → nhóm chính │
                    │  (OW: group_member ⋈ user) │
                    ▼                            ▼
              gộp theo nhóm  ──────────►  Σ nhóm = totals, bảo đảm bằng cấu trúc
```

**Định danh không phải vấn đề ở tab này.** `group_analytics.py:33-37` đã join `group_member → user` lấy `u.email`, khớp thẳng `mw_audit_log.user_id` (email). Bẫy `chat-analytics-id-mismatch` (MW dùng email, OW dùng UUID) **không áp vào đây**.

## Goals / Non-Goals

**Goals:**

- Tab Groups và tab Usage trả cùng một con số cho cùng một cửa sổ thời gian — kể cả `totals` và tổng bảng breakdown (xem D14).
- `Σ (chi phí các nhóm) == totals.cost_total_usd`, bảo đảm bằng việc tử số và mẫu số cùng đến từ một lời gọi hàm — không phải bằng đối chiếu thủ công.
- `Σ (drill-down của một nhóm) == dòng của nhóm đó ở bảng cha`, bảo đảm bằng việc cả hai dùng cùng một map nhóm chính.
- Một hàm thuần duy nhất phục vụ cả endpoint dashboard và Excel export.
- Mỗi bước triển khai xong thì hệ thống vẫn chạy được; bước làm đổi số nằm riêng một mình.

**Non-Goals:**

- Không thêm chỉ tiêu mới nào (toàn bộ danh sách ở `proposal.md` § Non-goals thuộc 7b).
- Không sửa việc **báo cáo quá khứ đổi số khi có người chuyển phòng** — xem D9 và Open Questions; sửa thật cần thêm cột vào `mw_audit_log`.
- Không đổi logic cấp quyền tool, không đụng CHECK 1 (quota per-user).
- Không đổi quy tắc xác định nhóm chính.

## Decisions

### D1 — Tách hàm thuần, KHÔNG để endpoint gọi endpoint

`export_report.py:148-160` hiện `import get_group_analytics` rồi gọi nó với `request`, để hàm kia tự check auth lần nữa. Đây là anti-pattern mà D1 của `unify-audit-aggregation` đã chốt tránh.

Tách `compute_group_analytics(cutoff, end_time, bucket_size)` — không nhận `Request`, không auth, không raise HTTP. Endpoint bọc auth + `_resolve_range` quanh nó; export gọi thẳng hàm.

**Thay vì:** để export tiếp tục gọi endpoint. Bị loại vì sau D12, `_resolve_range` sẽ raise `400`, mà export đang bọc `except Exception: pass` — kết quả là sheet "Phòng ban" ghi *"Dữ liệu nhóm không khả dụng"* rồi file Excel **vẫn xuất bình thường**, người nhận không biết là thiếu.

### D2 — Giữ nguyên tên field trong response, map lại ở backend

Frontend đọc `total_requests` / `total_cost` / `total_tokens` / `avg_latency_ms` / `model_preferences`; `breakdown_by_user` dùng `requests_total` / `cost_usd`. Map lại ở backend, **không đổi frontend** — theo tiền lệ D2 của `unify-audit-aggregation`.

Lý do không phải tiếc công sửa JS: bước "thay vòng gom" (D13 bước 4) là bước làm số tụt 264→189, nên diff của nó phải **chỉ chứa thay đổi cách tính**. Lẫn thêm việc đổi tên biến thì lúc soát lại không tách được nguyên nhân nào làm số đổi.

### D3 — Giữ quy tắc nhóm chính = `created_at` **cũ nhất**

Đã cân nhắc đổi sang `DESC` (nhóm mới nhất) để chịu được trường hợp admin chuyển phòng mà quên xóa khỏi phòng cũ. **Bị loại.**

`group` của Open WebUI **kiêm hai việc**: vừa là phòng ban, vừa là đơn vị cấp quyền tool (`core/tool_access.py` cấp `access_grant` theo group). Nên "được thêm vào nhóm thứ hai" thường là **cấp quyền tool**, không phải chuyển phòng — và việc đó xảy ra thường xuyên hơn chuyển phòng:

| Tình huống                                        | `ASC` (cũ nhất)        | `DESC` (mới nhất)          |
|---------------------------------------------------|------------------------|----------------------------|
| Thêm vào nhóm 2 để **cấp quyền tool** (hay xảy ra) | chi phí ở phòng gốc ✅  | nhảy sang nhóm quyền ❌     |
| Chuyển phòng **đúng cách** (xóa cũ + thêm mới)     | phòng mới ✅            | phòng mới ✅                |
| Chuyển phòng **thiếu bước** (chỉ thêm mới)         | phòng cũ ❌ (im lặng)   | phòng mới ✅                |

`ASC` sai ở ca ít xảy ra, `DESC` sai ở ca hay xảy ra. Bù cho ca thứ ba bằng cảnh báo hiển thị (D10), không bằng đổi quy tắc.

**Ghi chú vận hành đã xác minh trên source Open WebUI trong container:** `models/groups.py:627` dùng `delete(GroupMember)` — **xóa cứng** dòng membership. Nên một người chuyển phòng đúng cách chỉ còn **đúng một** dòng, và "cũ nhất" cũng là dòng duy nhất. Thứ tự hai lần bấm không ảnh hưởng kết quả cuối.

### D4 — Khung danh sách nhóm lấy từ bảng `group`, không suy ra từ audit

`group_stats` hiện là `defaultdict` chỉ sinh khoá khi gặp dòng audit, nên nhóm không có traffic **không có dòng nào** — `Marketing` (0 thành viên) chưa bao giờ xuất hiện trong bảng.

```
   Sai:   audit rows ──► suy ra có nhóm nào     (số nhóm đổi theo khoảng thời gian)
   Đúng:  bảng "group" ──LEFT JOIN── audit agg  (5 nhóm luôn đủ; không có data → "—")
```

Bắt buộc phải làm ở 7a dù scorecard thuộc 7b: nếu vẫn đếm nhóm từ audit thì thẻ *"Số đơn vị"* của 7b sẽ **đổi số mỗi khi đổi range** — chọn "1 giờ qua" có thể ra "Số đơn vị: 1". Nhóm 0 dữ liệu hiện `—`, theo tiền lệ `runway_days` của Phase 6: không tính được thì nói không tính được, đừng hiện `0`.

### D5 — Latency: xuất `latency_sum_ms` + `latency_sample_count`, không xuất `avg`

`breakdown_by_user` chỉ xuất `p95_latency_ms`; list `latencies` bị giữ lại trong hàm (`summary_v2.py:431-435`).

**Thay vì** đổi cột Groups sang P95 để dùng field có sẵn — **bị loại vì bất khả thi:** P95 không cộng lại được từ P95 của từng thành viên. Muốn P95 của nhóm phải có lại toàn bộ list latency, tức vẫn phải mở hàm ra. Trung bình thì cộng được.

**Thay vì** xuất `avg_latency_ms` + `latency_sample_count` rồi tính `Σ(avg_i × n_i) / Σ(n_i)` — **bị loại vì làm tròn hai lần:** `avg_i` được `round(..., 2)` khi serialize, nhân lại với `n_i` là dựng lại tổng từ số đã làm tròn. Xuất thẳng tổng thì phép chia chính xác tuyệt đối và công thức đơn giản hơn:

```
   avg_nhóm = Σ(latency_sum_ms_i) / Σ(latency_sample_count_i)
```

Nếu tab nào cần `avg_latency_ms` của từng user để hiển thị thì tính tại chỗ từ hai field này — đừng thêm field thứ ba dẫn xuất được.

`latency_sample_count` **phải được hiện lên UI**, không chỉ dùng để tính: latency chỉ phủ ~62% request thành công vì toàn bộ dòng `reconciled` không ghi `latency_ms`. Một con số trung bình không kèm độ phủ là một cái nhãn sai kiểu khác.

### D6 — Thống kê model đếm rid duy nhất; chấp nhận `top_model` của tab Usage đổi

`user_data[user_id]["models"][model] += 1` đếm mỗi **entry** (`summary_v2.py:320` và `:340`), nên một rid đi `error → reconciled` được đếm hai lần. Đổi thành `Dict[str, set]` chứa rid rồi lấy `len()`.

**Đây là sửa bên trong hàm dùng chung**, nên `top_model` của `breakdown_by_user` (tab Usage đọc) có thể đổi với một số user. Chấp nhận có chủ ý:

**Thay vì** chỉ đếm theo rid riêng cho Groups và để hàm dùng chung nguyên trạng. Bị loại vì bảng Groups sẽ có cột Requests đếm rid nằm **ngay cạnh** cột Model % đếm dòng — tái tạo đúng loại lệch mà change này đang đi dọn, chỉ ở ô nhỏ hơn.

Đã kiểm: `openspec/specs/dashboard-model-metrics/spec.md` có requirement *"Existing model columns and totals are unchanged"*, nhưng requirement đó phạm vi ở `breakdown_by_model`, còn `top_model` nằm ở `breakdown_by_user`. Không xung đột spec.

### D7 — Drill-down dùng cùng map nhóm chính với bảng cha

Bug đang ngủ, hai định nghĩa khác nhau trong cùng một file:

```
  Bảng cha   :33-37   DISTINCT ON (u.email) ... ORDER BY created_at ASC   → NHÓM CHÍNH
  Drill-down :136-141 SELECT u.email WHERE gm.group_id = %s               → MỌI MEMBERSHIP

  User X ∈ {R&D, DevOps}, nhóm chính R&D:
     bảng cha    → chi phí X vào R&D
     drill-down  → X hiện ở CẢ HAI nhóm, kèm chi phí
     ⇒ Σ drill-down DevOps ≠ dòng DevOps, và cost share % thành viên của 7b ra >100%
```

Dev chưa ai thuộc 2 nhóm nên chưa lộ, nhưng lệch đã có trong code. Sửa ở 7a chứ không để sang 7b, vì 7a phải chọn **một** định nghĩa cho cả hai endpoint dùng chung.

Kèm bỏ **fail-open** ở `:203-217`: nhánh uncategorized query OW lần hai rồi `except: pass`, nên query lỗi thì không lọc ai và drill-down trả về **toàn bộ user hệ thống**. Sau khi có map nhóm trong tay, query lần hai biến mất hoàn toàn — vừa hết lỗi vừa bớt code.

### D8 — Nhãn "Chưa quy được phòng ban", không phải "Chưa gán phòng ban"

Đo trên dev, rổ `Uncategorized` (155/264 dòng) gồm **ba loại khác nhau**:

| Thực chất                                                        | Định danh                                        | Dòng | %   |
|------------------------------------------------------------------|--------------------------------------------------|-----:|----:|
| Nhân viên **có** tài khoản OW, chưa được gán phòng ban            | `donk` `bear` `tranduyhung` `hamanhthe`          |   20 | 13% |
| Tài khoản **đã bị xóa** khỏi OW (FK `ON DELETE CASCADE` xóa luôn membership) | `dinhthinhan18111971@gmail.com`        |   62 | 40% |
| **Định danh hệ thống**, không phải email, không có dòng trong `user` | `admin` `testuser` `pvt123`                     |   72 | 47% |

Nhãn *"chưa gán"* ngụ ý sẽ gán được nếu admin siêng hơn — sai với 87% của con số, và `admin` thì **không bao giờ gán được** vì không có tài khoản OW để thêm vào nhóm. *"Chưa quy được"* đúng cho cả ba loại.

`user_id = "unknown"` (audit không ghi được người dùng — `summary_v2.py:286` có default này) gộp vào cùng rổ. Dev hiện không có dòng nào như vậy; gộp và ghi rõ trong tooltip, tách ra thành dòng riêng khi nào thực tế cần.

### D9 — Ghi nhãn "cơ cấu hiện tại" thay vì cố sửa việc lịch sử bị gán lại

`mw_audit_log` là lịch sử bất biến, còn `group_member` chỉ lưu **trạng thái hiện tại** — không nhớ hôm 05/07 ai thuộc phòng nào. Hệ quả cấu trúc:

```
   An ở R&D tháng 1→7, tiêu $50; ngày 01/08 chuyển sang DevOps

   Xem báo cáo tháng 7 vào 31/07:  R&D $50 · DevOps $0
   Xem CÙNG báo cáo đó vào 02/08:  R&D  $0 · DevOps $50

   Audit log không đổi một dòng nào. Chỉ group_member đổi.
```

| Cách                                                    | Đánh giá                                                          |
|---------------------------------------------------------|-------------------------------------------------------------------|
| **Chọn:** ghi nhãn *"theo cơ cấu tổ chức hiện tại"*      | Rẻ, trung thực, không khoá đường về; làm được trong 7a            |
| Chụp `group_id` vào `mw_audit_log` lúc gọi API           | Đúng về lịch sử, nhưng **đổi schema** và chỉ đúng từ ngày triển khai — quá khứ không cứu được |

Chọn cách một. Một dòng chú thích ngăn được đúng cái hiểu sai nguy hiểm, và không chặn việc làm cách hai sau này. Xem Open Questions.

### D10 — Cảnh báo đa nhóm, không đổi quy tắc

Khi phát hiện có người thuộc >1 nhóm, hiện *"⚠️ N người thuộc nhiều nhóm — chi phí tính vào nhóm vào sớm nhất"*. Dữ liệu đã có sẵn: query hiện tại dùng `DISTINCT ON`, chỉ cần thêm một `COUNT(*)` để biết N.

Đây là phần bù cho ca "chuyển phòng thiếu bước" ở D3 — biến lỗi im lặng thành lỗi nhìn thấy được, mà không phải hy sinh ca hay xảy ra hơn.

### D11 — Doughnut: màu xám gán theo danh tính, không theo vị trí trong palette

Bảng sort theo chi phí giảm dần, mà dòng "chưa quy được phòng ban" chiếm 59% chi phí trên dev ⇒ nó nằm **index 0** và sẽ ăn màu đầu tiên của mảng (`#3b82f6` xanh — màu trông như "phòng ban chính"). Phải nhận diện `group_id === null` rồi override sang xám, đồng thời đẩy xuống **cuối legend** để 4 phòng ban thật đọc thành một bộ.

Thêm màu xám vào cuối mảng palette **không có tác dụng** — nó sẽ không bao giờ rơi đúng vào dòng đó.

### D12 — Đổi sang `_resolve_range`, chấp nhận export có thể lỗi rõ

`_time_boundaries` (`analytics.py:11-21`) bọc parse trong `try/except: pass` rồi rơi về `now - 43200 phút`. Một range sai cú pháp hiện cho ra "30 ngày qua" mà không ai biết. `_resolve_range` raise `400`.

Trade-off có chủ ý: sau D1, export sẽ **lỗi rõ** thay vì xuất file Excel thiếu sheet trong im lặng. Thà báo lỗi hơn giao báo cáo khuyết.

### D13 — Thứ tự triển khai: bước làm đổi số nằm riêng

```
  1. Mở rộng compute_usage_summary (avg latency + sample_count + model theo rid)
     → chưa ai đọc field mới; tab Usage chỉ đổi top_model. An toàn nhất, làm trước.

  2. _time_boundaries → _resolve_range
     → range xấu báo 400 thay vì lặng lẽ 30 ngày. Số KHÔNG đổi.

  3. Khung nhóm lấy từ bảng "group" (LEFT JOIN)
     → Marketing xuất hiện với "—". Nhóm cũ không đổi số.

  4. ⚠️ Thay vòng gom bằng compute_usage_summary
     → ĐÂY là bước Requests tụt 264→189. Một bước duy nhất, một commit duy nhất.
       Dễ báo trước, dễ revert, dễ chỉ ra nguyên nhân khi ai thắc mắc.

  5. Drill-down dùng cùng map nhóm chính + bỏ fail-open (D7)
     → tách khỏi bước 4 để nó có dòng riêng, không bị coi là hệ quả phụ.

  6. Export: gọi hàm thuần, bỏ except: pass, sửa nhãn sheet (D1, D8)

  7. Frontend: colspan ×7 · nhãn · độ phủ latency · cảnh báo đa nhóm · xám doughnut
```

Bước 4 và 5 **không gộp**: bước 5 mới là cái sửa D7, và nó đáng có dòng riêng trong `tasks.md`.

### D14 — Request `pending` được đếm vào sổ theo người

Vòng lặp trong `compute_usage_summary` chỉ gán rid vào `user_data` ở nhánh `if status in ["ok","reconciled"]` và `elif status == "error"` (`summary_v2.py:305-343`) — **không có `else`**. Nên một request có trạng thái cuối là `pending` **không thuộc về ai**:

```
   totals.requests_total = len(rid_status)   = 189   ← có rid pending
   Σ breakdown_by_user                        = 188   ← không có
```

Đo trên dev, cửa sổ nghiệm thu: `ok 113` · `reconciled 70` · `error 5` · `pending 1` = 189.

Lệch này **đã tồn tại trước change này** và đang hiện ra ở tab Usage: thẻ *Total Requests* hiện `189` trong khi cộng bảng Top Users bên dưới ra `188` — hai con số trên cùng một trang.

| Cách                                              | Đánh giá                                                                                          |
|---------------------------------------------------|---------------------------------------------------------------------------------------------------|
| Nhận `188` cho tab Groups, ghi rõ lý do            | Không phình phạm vi, nhưng để lại lệch 1 giữa hai con số cùng hiển thị — đúng loại bệnh mà change này đi chữa |
| **Chọn:** đếm rid `pending` vào người gọi nó       | Mọi tab cộng ra cùng một số. Đúng bản chất: người đó **có** gửi request                            |

`pending` **chỉ được cộng vào `requests`**, KHÔNG cộng `cost_total`/`tokens_total`/`latencies` — chưa có số thì không có gì để cộng. `requests_ok` giữ nguyên nghĩa cũ.

**Ba tác dụng lan phải đo trước/sau:**

1. Số request của user trong bảng Top Users tăng đúng bằng số request `pending` của họ.
2. `error_rate_percent` của từng user giảm nhẹ, vì mẫu số `len(stats["requests"])` giờ gồm cả `pending`.
3. `adoption.py:253` lấy `active_user_ids` từ `breakdown_by_user`, nên người trong kỳ **chỉ có** request `pending` giờ được tính là có hoạt động ⇒ tỷ lệ áp dụng nhích lên. Theo bản chất thì đúng (họ đã dùng hệ thống), nhưng đây là con số đã báo cáo nên phải có số liệu trước/sau, không chỉ khẳng định.

### D15 — Chi phí trả 6 chữ số thập phân, làm tròn ở tầng hiển thị

`group_analytics.py:107` trả `round(stats["total_cost"], 4)` cho **từng nhóm**. Cộng các giá trị đã làm tròn thì tổng không khớp `totals.cost_total_usd`, nên **không kiểm chứng được bằng phép so bằng** — mà phép so bằng đó chính là tiêu chí nghiệm thu chính của change này.

Đây cũng là nguồn của con số `$0.0672` từng bị hiểu là bằng chứng lệch nguồn gom. Đo bằng SQL: cộng mọi dòng và cộng chỉ dòng `ok`/`reconciled` **đều cho `0.067191`** — hai cách gom hiện khớp tuyệt đối, chênh lệch chỉ đến từ làm tròn hiển thị.

Trả 6 chữ số như `breakdown_by_user` vẫn làm (`round(stats["cost_total"], 6)`), để frontend định dạng.

### D16 — `bucket_size` truyền tường minh

Theo tiền lệ D3 của `unify-audit-aggregation` (*"`bucket_size` truyền tường minh, không dùng `auto`"*). Tab Groups không dùng `timeseries` của `compute_usage_summary`, nên truyền một giá trị cố định (`"day"`) thay vì để `_resolve_range` suy ra theo độ dài cửa sổ. Như vậy kết quả gộp theo nhóm không phụ thuộc độ dài cửa sổ qua một đường vòng không ai chủ ý.

## Risks / Trade-offs

| Risk                                                                                              | Mitigation                                                                                                     |
|---------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|
| Requests tab Groups tụt 264→189; người xem tưởng mất dữ liệu                                       | Tách riêng bước 4 (D13) thành một commit; thông báo trước khi deploy; ghi con số trước/sau vào biên bản nghiệm thu |
| Sửa hàm dùng chung `compute_usage_summary` lan sang Chat Analytics, Adoption, Usage                 | Phần lớn là **thêm** field. Hai ngoại lệ có chủ ý — `top_model` (D6) và việc đếm `pending` (D14) — đều phải đo trước/sau |
| `top_model` tab Usage đổi giá trị với một số user                                                  | D6 ghi rõ; không có spec nào phủ `top_model` nên không vi phạm; đổi theo hướng đúng hơn                          |
| D14 làm tỷ lệ áp dụng ở tab Users nhích lên (người chỉ có request `pending` giờ tính là hoạt động)   | Đo trước/sau và ghi vào biên bản nghiệm thu; nêu rõ với leader là con số cũ **thiếu** người đã dùng hệ thống, không phải con số mới thổi phồng |
| D14 làm `error_rate_percent` của từng user giảm nhẹ do mẫu số gồm cả `pending`                       | Đúng nghĩa "tỷ lệ lỗi trên tổng request đã gửi"; đo trước/sau                                                    |
| Bỏ `except: pass` ở export ⇒ range xấu làm export lỗi thay vì xuất file khuyết                      | Có chủ ý (D12). Lỗi rõ tốt hơn báo cáo thiếu trong im lặng                                                     |
| Trung bình latency chỉ dựa trên ~62% request thành công                                            | Xuất và hiển thị `latency_sample_count` cạnh giá trị (D5); không hiện số trung bình trơ                          |
| Báo cáo quá khứ đổi số khi có người chuyển phòng — **không sửa được ở change này**                  | Ghi nhãn "cơ cấu hiện tại" (D9); ghi vào Open Questions để quyết riêng                                          |
| Nhóm chính sai khi admin quên xóa khỏi phòng cũ                                                    | Cảnh báo đa nhóm (D10) + quán triệt thao tác; không đổi quy tắc vì sẽ hỏng ca hay xảy ra hơn (D3)               |
| `colspan="7"` rải 7 chỗ trong `group_analytics.js`, sót một chỗ là bảng lệch                       | Liệt kê đủ 7 vị trí thành một task riêng trong `tasks.md`, không gộp vào task "sửa frontend"                     |
| Nếu sau này bật SCIM, `set_group_user_ids_by_id` xóa sạch rồi thêm lại **cùng** `created_at` ⇒ nhóm chính không xác định | Ngoài phạm vi (deployment hiện chưa bật SCIM — đã xác minh không có biến môi trường nào). Ghi vào Open Questions |

## Migration Plan

**Triển khai:** 7 bước theo D13, mỗi bước một commit. Bước 1-3 có thể deploy độc lập mà không ai thấy khác biệt; bước 4 là mốc cần thông báo.

**Nghiệm thu bước 4** — cửa sổ phải ghi tường minh cả mũi giờ và biên cuối, vì `"16/06/2026 → 15/07/2026"` là mơ hồ: đo với biên cuối `2026-07-15T00:00` ra `255/183` (cắt mất cả ngày 15/07), với biên cuối cuối ngày ra `264/189`.

**Cửa sổ nghiệm thu:** `2026-06-16T00:00:00+07:00` → `2026-07-15T23:59:59+07:00`

| Nguồn                                    | Trước | Sau (mong đợi) |
|------------------------------------------|------:|---------------:|
| Tab Groups (Σ các nhóm)                  |   264 |            189 |
| Tab Usage (`/v1/_mw/summary` → `totals`)  |   189 |            189 |
| Tab Usage (Σ bảng Top Users)             |   188 |            189 |
| `SELECT count(DISTINCT rid)` trực tiếp   |   189 |            189 |

Dòng thứ ba là hệ quả của D14: trước change, Σ bảng Top Users lệch `totals` đúng 1 vì có 1 rid `pending`. Sau change cả bốn nguồn bằng nhau.

Và kiểm `Σ chi phí các nhóm == totals.cost_total_usd` — phép so **bằng tuyệt đối**, khả thi được nhờ D15 (trả 6 chữ số thập phân). Giá trị hiện tại: `0.067191`.

**Rollback:** mỗi bước là một commit độc lập, revert được riêng. Bước 1 (thêm field) không cần revert kể cả khi các bước sau bị lùi — field mới không ai đọc thì vô hại.

## Open Questions

1. ~~**Đổi nhãn cột "Thành viên" ở phía nào?**~~ — **ĐÃ CHỐT 2026-07-27: giữ nguyên "Thành viên" ở section Tool Access, cột mới của 7b đặt là "Thuộc phòng này".**

   Cột "Thành viên" hiện có (`index.html:593`, số từ `core/tool_access.py:85` = `count(*) FROM group_member`) đếm **mọi** membership. Trong ngữ cảnh phân quyền tool thì đúng: nó trả lời *"bật tool cho phòng này thì bao nhiêu người thấy"*. Không đụng nó — đang chạy, đúng nghĩa, và người dùng không phải học lại.

   Cột 7b sắp thêm đếm **nhóm chính**, trả lời câu khác: *"chi phí này chia cho bao nhiêu người"*. Cả hai đúng trong ngữ cảnh của nó; vấn đề chỉ là dùng chung một chữ. Nếu trùng chữ, người đọc lấy số ở bảng dưới chia chi phí ở bảng trên sẽ ra sai — ví dụ DevOps `$0.000281` với 1 người thật nhưng 2 membership sẽ đọc thành `$0.00014/người`, rẻ đi một nửa.

   **7a không phải làm gì** — đây thuần tuý là chốt tên cho cột của 7b. Đã ghi vào `docs/dashboard_metrics_implementation_plan.md` §7b.
2. **Có chụp `group_id` vào `mw_audit_log` để báo cáo quá khứ tái lập được không?** Đổi schema, chỉ đúng từ ngày triển khai. Ngoài phạm vi 7a; cần quyết riêng vì liên quan nguyên tắc lịch sử bất biến của dự án.
3. **Nếu công ty đồng bộ nhân sự từ AD/Okta qua SCIM về sau**, `set_group_user_ids_by_id` (`models/groups.py:365-386`) xóa sạch cả nhóm rồi thêm lại với **cùng** `created_at`, làm quy tắc "cũ nhất" mất căn cứ và nhóm chính của người đa nhóm thành không xác định. Bẫy đang ngủ — cần luật riêng trước khi bật SCIM.
