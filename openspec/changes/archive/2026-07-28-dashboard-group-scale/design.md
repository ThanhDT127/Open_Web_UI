# Design — dashboard-group-scale (Phase 7b)

## Context

7a (`unify-group-aggregation`, archive 2026-07-27) đã đưa tab Groups về chung nguồn gom với tab Usage. Kết quả kiểm chứng: `Σ nhóm == totals.requests_total` và `Σ chi phí nhóm == totals.cost_total_usd` **tuyệt đối trên 10 cửa sổ** khác nhau, đo bằng 3 nguồn độc lập (SQL thô · `totals` · Σ nhóm).

Điều đó biến mọi phần trăm của 7b thành phép chia trên số đã đúng, thay vì một con số phải đi đối chiếu tay:

```
   compute_group_analytics(cutoff, end, bucket)
        │
        ├── groups[].total_cost              (chưa làm tròn)
        ├── groups[].primary_member_count    ← 7a đã đưa vào payload
        ├── department_count                 ← 7a đã đưa vào payload
        └── multi_group_user_count
                    │
                    │  cùng một lời gọi hàm với totals
                    ▼
        cost_share_% · cost/member · scorecard   ⇒  0 truy vấn mới
```

**Dữ liệu hiện trạng (dev, cửa sổ trượt 30 ngày, 2026-07-27):**

| Nhóm                    | Chi phí | Share  | Thành viên (nhóm chính) |
|-------------------------|--------:|-------:|------------------------:|
| Chưa quy được phòng ban |  0.0324 | 48,3 % |                       — |
| Admin                   |  0.0241 | 36,0 % |                       1 |
| R&D                     |  0.0084 | 12,6 % |                       2 |
| DataCenter              |  0.0018 |  2,6 % |                       1 |
| DevOps                  |  0.0003 |  0,4 % |                       1 |
| Marketing               |  0.0000 |  0,0 % |                       0 |

Con số `48,3%` là điều quan trọng nhất trong bảng này và nó định hình phần lớn thiết kế bên dưới.

## Goals / Non-Goals

**Goals:**

- Trả lời được *"phòng nào tiêu **nhiều**"*, không chỉ *"phòng nào tiêu bao nhiêu"* — tức chuẩn hoá theo đầu người.
- Mọi tỷ lệ phần trăm cộng lại đúng 100%, bảo đảm bằng cấu trúc (cùng nguồn gom) chứ không bằng đối chiếu.
- Mọi mẫu số mô tả **cùng tập người** với tử số của nó.
- Chỉ tiêu không tính được thì nói rõ là không tính được, và nói **vì sao**.

**Non-Goals:**

- Không sửa lại cách gom (7a đã xong và đã archive).
- Không đổi quy tắc nhóm chính (`created_at` cũ nhất).
- Không đụng `core/tool_access.py`, cột "Thành viên" hiện có, hay CHECK 1 (quota alert).
- Không đổi cột latency sang percentile — xem Open Questions.

## Decisions

### D1 — Mẫu số của cost share là tổng hệ thống, không phải tổng các dòng hiển thị

`cost_share_of_system_percent` tính trên **tổng của toàn bộ population**, cộng từ chính những giá trị `cost_usd_raw` **chưa làm tròn** mà tử số cũng lấy từ đó. Tiền lệ Phase 5 (`dashboard-model-metrics`): *"share uses the global total_cost so the value is correct even after the list is capped"*.

**Không dùng `totals.cost_total_usd`** — con số đó đã `round(..., 6)` để hiển thị. Mẫu số đã làm tròn chia cho tử số chưa làm tròn khiến tổng share **lệch 100 khoảng 5×10⁻⁴** (đo thật: `100.000537` trên cửa sổ 30 ngày). Đây là cùng một cái bẫy với chi phí ở 7a D15, chỉ ở một tầng nữa: **mỗi lần làm tròn sớm là một lần góp sai số**.

**Cũng không dùng `Σ` các dòng cuối cùng trả về.** Hôm nay danh sách đủ nên hai cách trùng nhau, nhưng `breakdown_by_user` **là** population theo định nghĩa, nên suy từ nó thì mỗi dòng vẫn báo đúng tỷ lệ thật kể cả khi bảng bị cắt sau này.

Và trả **chưa làm tròn**: làm tròn 1 chữ số từng dòng rồi cộng ra `99,9`. Làm tròn đúng một lần, ở tầng hiển thị.

### D2 — Dòng "Chưa quy được phòng ban": giữ trong bảng, loại khỏi mọi mẫu số

Trên dev nó chiếm **48% tổng chi tiêu**. Ba lựa chọn đã cân nhắc ở 7a:

| Cách                                             | Đánh giá                                                        |
|--------------------------------------------------|------------------------------------------------------------------|
| Coi là một đơn vị                                 | "Số đơn vị: 6" trong khi công ty có 5 phòng — sai bản chất       |
| Ẩn khỏi bảng                                      | Giấu 48% chi tiêu. Tệ nhất                                       |
| **Chọn:** giữ trong bảng, loại khỏi mẫu số       | Đúng cả hai mặt, nhưng bảng cộng ≠ mẫu số nên **phải giải thích** |

Hệ quả bắt buộc: `Chi phí bình quân mỗi phòng ban = 0.034606 / 5 = 0.006921` chỉ chia phần của 5 phòng ban thật. Lãnh đạo cộng cột chi phí trong bảng (`0.0670`) rồi chia 5 sẽ ra `0.0134` — **gấp đôi**. Nên chú thích không phải trang trí, nó là điều kiện để con số đọc được:

- Dòng dưới cụm thẻ: *"Hệ thống có N phòng ban. Ba số trên chỉ tính người đã được gán phòng ban — phần còn lại nằm ở dòng **Chưa quy được phòng ban** trong bảng dưới. ⓘ"*
- Tooltip: *"Dòng đó gồm ba loại: nhân viên chưa được thêm vào phòng ban nào · tài khoản đã bị xóa khỏi Open WebUI (lịch sử chi phí vẫn được giữ) · định danh hệ thống không phải người dùng (ví dụ `admin`). Vì vậy tổng chi phí trong bảng sẽ lớn hơn N phòng ban cộng lại."*

### D3 — "Thành viên hoạt động" là phép giao, không phải phép đếm

```
   active_members = { người có ≥1 request trong khoảng }  ∩  { người có nhóm chính là nhóm này }
```

**Thay vì** chỉ đếm người có request trong khoảng và gán theo nhóm chính — nghe tương đương, nhưng không phải: một người **đã rời phòng** (bị xoá khỏi `group_member`) vẫn còn lịch sử request trong `mw_audit_log`, nên vế trái có họ mà vế phải không. Không giao thì `active` có thể **vượt** `total`.

Đây đúng là lỗi Phase 4 đã gặp — tỷ lệ áp dụng ra 108% — và phép giao là thứ đã sửa nó. Bất biến phải kiểm: `active_member_count <= primary_member_count` cho **mọi** nhóm, **mọi** cửa sổ.

### D4 — Hai mẫu số, hai chỉ tiêu, không chọn một

Giữ **cả** `cost / total_members` và `cost / active_members`, vì chúng trả lời hai câu khác nhau:

| Chỉ tiêu | Trả lời | Dùng khi |
|---|---|---|
| `cost / total_members` | *"Trung bình mỗi nhân sự phòng này tốn bao nhiêu"* | So sánh phòng ban, lập ngân sách |
| `cost / active_members` | *"Người thực sự dùng thì tốn bao nhiêu"* | Đánh giá cường độ dùng, tách khỏi chuyện bao nhiêu người chưa dùng |

Chênh lệch giữa hai số **chính là tín hiệu adoption** của phòng đó: `total` cao mà `active` thấp nghĩa là nhiều người được cấp nhưng không dùng.

### D5 — Quota: ba trạng thái, ba cách hiện khác nhau

Không được gộp *"không biết"* với *"vô hạn"* — hai nghĩa ngược nhau:

| Tình huống | Hiện | Vì sao |
|---|---|---|
| Không có dòng `mw_users` (`admin`, tài khoản đã xoá khỏi OW) | `—` + tooltip *"không phải tài khoản người dùng"* / *"tài khoản đã xoá"* | Không tra được |
| `deleted_at IS NOT NULL` (xoá mềm) | `—` + tooltip *"tài khoản đã xoá"* | Hạn mức chỉ có nghĩa khi còn hiệu lực. Khác chi phí — chi phí đã xảy ra thì vĩnh viễn có nghĩa, nên **vẫn hiện** |
| `limit_cost_usd <= 0` | **"Không giới hạn"** | Tra được, và câu trả lời là vô hạn. Hiện `—` ở đây là mislabel |

Bucket `unlimited` cho `limit <= 0` đã là tiền lệ ở Phase 4 (`adoption.py:_quota_histogram`), dùng lại đúng ngưỡng đó.

### D6 — Đọc quota theo lô, KHÔNG gọi hàm quota per-user

`get_current_quota_user` (`core/alerting.py`) **reset kỳ quota như side-effect**. Gọi nó cho từng dòng drill-down nghĩa là một lần render trang có thể **sửa dữ liệu** của tới 200 người.

Dùng mẫu bulk-read của Phase 4: một `SELECT user_id, quota, deleted_at FROM mw_users`, tính phần trăm bằng đúng công thức của `get_user_quota_status` nhưng không chạm vào state. `adoption.py:_quota_histogram` đã làm y hệt và ghi rõ lý do trong comment.

### D7 — Hai cột cạnh nhau, hai trục thời gian — phải dán nhãn

Trong drill-down, cột *Chi tiêu* theo **khoảng đang xem** còn cột *% hạn mức* theo **kỳ quota hiện tại**. Hai trục khác nhau đứng cạnh nhau mà không nói ra thì người đọc mặc định chúng cùng kỳ.

Nhãn phải mang mốc thời gian: *"Chi tiêu (khoảng đang xem)"* và *"% hạn mức (kỳ quota hiện tại)"* — không để trống là "Chi tiêu" và "Quota".

### D8 — Cột nhân sự phải mang tên khác cột "Thành viên"

Chi tiết và ví dụ số ở `proposal.md` § Impact. Tóm tắt: section Tool Access cùng tab đã có cột "Thành viên" đếm **mọi** membership; cột mới đếm **nhóm chính**. Trùng chữ thì người đọc chia nhầm mẫu số. Ràng buộc "phải khác chữ" chốt ở 7a (Open Question 1); **chữ cụ thể** thì xem D12 — 7a đề xuất *"Thuộc phòng này"*, D12 đổi thành **"Nhân sự phòng"** vì dễ đọc hơn mà vẫn khác biệt.

Không đụng cột hiện có ở Tool Access: đếm mọi membership ở đó là **đúng**, vì nó trả lời *"bật tool thì bao nhiêu người thấy"*.

### D9 — Scorecard vào registry, cột bảng thì không

`metrics_registry.js` chỉ khai báo **3 thẻ scorecard**. Cột trong bảng breakdown **không** khai báo — spec `dashboard-model-metrics` đã chốt: *"breakdown-table columns, not scorecards. They SHALL NOT be declared in metrics_registry.js"*. Cột dùng formatter `usd4` mà 7a đã export sẵn.

Ranh giới này cũng quyết định cái gì có badge KT/CK: **chỉ scorecard**.

### D10 — Cơ chế 3 cửa sổ: dựng mới, theo khuôn Usage/Overview

Plan ghi việc này là *"🟢 chỉ khai báo thêm một dòng registry"* — **sai, và phải sửa lại plan**. Registry chỉ mô tả *cách hiển thị* một chỉ tiêu; nó không đi lấy dữ liệu. Tab Usage và Overview có sẵn đoạn gọi song song 3 cửa sổ (hiện tại · KT · CK) rồi ghép vào badge; tab Groups **chưa có gì**.

Chỉ dựng cho **một** thẻ (*Chi phí bình quân mỗi phòng ban*) trong change này. Hai thẻ còn lại (*Số phòng ban*, *Nhân sự đã có phòng ban*) là **snapshot cơ cấu tổ chức**, không có trục thời gian — so kỳ với chúng là vô nghĩa, giống các thẻ roster đã bị chặn so sánh ở Phase 4.

### D11 — Không tính được thì hiện `—` kèm lý do

Áp cho: nhóm 0 thành viên (`cost/member`), nhóm 0 người hoạt động (`cost/active`), quota không tra được. Theo tiền lệ `runway_days` của Phase 6.

`—` trơ thì đọc ra như lỗi dữ liệu; `—` kèm tooltip thì đọc ra như một câu trả lời. Chênh lệch đó là toàn bộ giá trị của quy tắc này.

### D12 — Bảng nhãn: một nguồn chân lý cho mọi tên hiển thị

Nhãn được chốt ở đây để mọi nơi (bảng, thẻ, Excel) dùng cùng một chữ. Nguyên tắc chọn: **danh từ** (không phải cụm tính từ), **tự nói ra mẫu số**, và các chỉ tiêu chia cho nhau thì **dùng chung một chữ** để người đọc thấy quan hệ mà không cần đoán.

| Vị trí | Nhãn | Nội dung |
|---|---|---|
| Bảng — cột | **Tỷ trọng chi phí** | chi phí nhóm / tổng hệ thống |
| Bảng — cột | **Nhân sự phòng** | số người có nhóm này là nhóm chính |
| Bảng — cột | **Chi phí / nhân sự** | chia cho cột *Nhân sự phòng* |
| Bảng — cột | **Chi phí / người có dùng** | chia cho số người có ≥1 request trong khoảng |
| Thẻ | **Số phòng ban** | `department_count` |
| Thẻ | **Nhân sự đã có phòng ban** | dạng `N / M` — xem D13 |
| Thẻ | **Chi phí bình quân mỗi phòng ban** | có badge KT/CK |
| Drill-down — cột | **Tỷ trọng trong phòng** | chi phí người / tổng nhóm |
| Drill-down — cột | **Chi tiêu (khoảng đang xem)** | mốc thời gian nằm trong nhãn (D7) |
| Drill-down — cột | **Đã dùng hạn mức (kỳ này)** | mốc thời gian nằm trong nhãn (D7) |

**Bị loại:** *"Thuộc phòng này"* (chốt ở 7a) — nó được đặt để tránh trùng chữ với "Thành viên", chứ không phải để dễ đọc; là cụm tính từ nên làm tiêu đề cột thì lấn cấn với người chưa theo dõi Phase 7. *"Nhân sự phòng"* đạt cả hai: vẫn khác hẳn "Thành viên", và đọc được ngay.

**Bị loại:** *"Số đơn vị"* (chữ trong plan) — cả tab dùng chữ "phòng ban", riêng thẻ dùng "đơn vị" là bắt người đọc tự ánh xạ.

### D13 — Thẻ nhân sự phải hiện cả mẫu số

Thẻ đếm người **đã được gán phòng ban**. Nhãn *"Tổng thành viên"* (dự định ban đầu) đọc ra là **tổng nhân sự công ty** — sai. Dev: 12 tài khoản trong `mw_users` chưa xoá, nhưng chỉ **5** người có phòng ban; 7 người (58%) không thuộc phòng nào.

Hiện `5` trơ thì giấu mất chuyện đó, và giấu luôn mối liên hệ với con số 48% chi phí chưa quy được — **hai con số là cùng một câu chuyện nhìn từ hai phía**: 7 người không có phòng ban chính là lý do gần một nửa chi tiêu không quy được về đâu.

Nên thẻ SHALL hiện dạng **`5 / 12`** dưới nhãn **"Nhân sự đã có phòng ban"**. Khác với 48% chi phí — vốn là hệ quả — con số `7 người chưa gán` là việc **làm được ngay**, nên đáng hiện thành hành động.

### D14 — Tên field trong payload phải nói rõ mẫu số

`cost_share_percent` xuất hiện ở hai payload với hai mẫu số khác nhau (tổng hệ thống ở bảng nhóm, tổng nhóm ở drill-down). Không đụng nhau trên màn hình vì khác payload, nhưng với người đọc API thì đó là đúng cái bẫy trùng chữ mà change này đi tránh ở tầng UI.

Đặt tên tường minh: **`cost_share_of_system_percent`** và **`cost_share_of_group_percent`**.

### D15 — Dòng "chưa quy được phòng ban" không có chỉ tiêu theo đầu người

Dòng đó có `primary_member_count = None` vì nó không phải phòng ban — nhưng nó **có** người hoạt động (8 người trên dev). Nếu trả `active_member_count = 8` thì bất biến `active <= total` mất nghĩa (`8 <= None`).

Trả **`None`** cho cả `active_member_count`, `cost_per_member` và `cost_per_active_member` của dòng này. Nó không phải một đơn vị, nên mọi chỉ tiêu "trên đầu người của đơn vị" đều không áp dụng. Bất biến chỉ kiểm trên các nhóm có `group_id`.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Thẻ *Chi phí bình quân mỗi phòng ban* không khớp với việc cộng tay cột chi phí (48% nằm ngoài mẫu số) | D2: chú thích + tooltip là **bắt buộc**, không phải tuỳ chọn. Nghiệm thu phải kiểm chú thích có hiện, không chỉ kiểm con số |
| `active_members` vượt `total_members` nếu quên phép giao | D3: bất biến `active <= total` kiểm trên mọi nhóm × mọi cửa sổ, kể cả cửa sổ rỗng |
| Gọi nhầm `get_current_quota_user` → reset kỳ quota của 200 người khi render trang | D6: ghi cảnh báo ngay trong task, và trong comment tại chỗ đọc quota |
| Thêm cột nhưng sót `colspan` → bảng lệch | Liệt kê đủ **10 vị trí** thành task riêng, không gộp |
| Số phòng ban nhỏ nên sai số làm tròn khó lộ trên dev | Giữ payload chưa làm tròn, làm tròn một lần ở `usd4()` — bài học 7a D15: sai số tăng theo số phần tử được cộng, dev 13 user không thấy còn production 200 user thì chạm chữ số thứ 4 |
| Người chuyển phòng làm mọi chỉ tiêu/đầu người đổi hồi tố | Kế thừa từ 7a D9: đã có chú thích *"theo cơ cấu tổ chức hiện tại"* trên tab. Không sửa được nếu không chụp `group_id` vào `mw_audit_log` |

## Open Questions

1. **Cột latency của tab Groups có nên đổi sang percentile không?** Trung bình không phải thống kê chuẩn cho latency (đuôi dài), và tab Usage của chính dashboard này dùng p95. Giữ trung bình vì p95 **không cộng lại được** từ p95 của từng người (7a D5) — muốn p95 theo nhóm thì `compute_usage_summary` phải xuất danh sách latency thô, tức thêm một mảng có thể dài vào payload. Ngoài phạm vi 7b; cần quyết riêng.
2. **`cost/active_members` có nên hiện khi `active = 0` nhưng `total > 0` không?** Tức phòng có người mà không ai dùng trong kỳ. `—` là đúng về toán, nhưng chính trường hợp đó lại là tín hiệu adoption đáng chú ý nhất — có thể đáng làm nổi bật thay vì làm mờ.
3. **Ngưỡng cảnh báo cho tỷ lệ "chưa quy được phòng ban"?** Trên dev là 48%. Nếu production cũng cao thì đó là việc cần xử lý về vận hành, không phải việc của dashboard — nhưng dashboard có nên chủ động cảnh báo khi vượt một ngưỡng nào đó không?
