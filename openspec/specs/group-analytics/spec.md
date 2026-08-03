# group-analytics Specification

## Purpose
TBD - created by archiving change 2026-07-02-group-analytics-dashboard. Update Purpose after archive.
## Requirements
### Requirement: Cross-database Group Analytics Aggregation

Backend SHALL cung cấp API endpoint `/v1/_mw/admin/analytics/groups` tổng hợp chi phí, lượng tokens, độ trễ, và số lượng request theo Primary Group của các users. Số liệu SHALL đến từ `compute_usage_summary` (`api/summary_v2.py`) — endpoint này **KHÔNG** được tự duyệt `mw_audit_log`. Hệ quả bắt buộc của việc dùng nguồn gom chung:

- Đơn vị đếm request SHALL là **rid duy nhất**, không phải số dòng audit. Một request sinh nhiều dòng (`pending` → `reconciled`) SHALL được đếm một lần.
- Chi phí và tokens SHALL chỉ được cộng từ các request có trạng thái cuối là `ok` hoặc `reconciled`. Request `error` và `pending` SHALL KHÔNG cộng tiền hay tokens, nhưng SHALL được đếm vào số lượng request.
- Tổng số request của tất cả các nhóm SHALL bằng `totals.requests_total` của cùng cửa sổ thời gian.
- Tổng chi phí của tất cả các nhóm SHALL bằng `totals.cost_total_usd` của cùng cửa sổ thời gian, vì tử số và mẫu số đến từ cùng một lời gọi hàm.
- Chi phí SHALL được cộng dồn từ giá trị **chưa làm tròn**, và làm tròn **đúng một lần** ở tầng hiển thị. Payload SHALL KHÔNG làm tròn chi phí của từng người hay từng nhóm trước khi cộng. Lý do là sai số **tăng theo số phần tử được cộng**: làm tròn 6 chữ số cho mỗi người rồi cộng 200+ người (quy mô hệ thống này được thiết kế cho) dồn tới chữ số thập phân thứ 4 — đúng chữ số cuối mà dashboard hiển thị — trong khi trên tập dev 13 người thì sai số nằm ở chữ số thứ 6 và không nhìn thấy được.

Logic gộp SHALL nằm trong một hàm thuần `compute_group_analytics(cutoff, end_time, bucket_size)` — không nhận `Request`, không thực hiện xác thực, không raise lỗi HTTP. Mọi caller cần số liệu nhóm (endpoint dashboard, Excel export) SHALL gọi hàm thuần này; KHÔNG caller nào được gọi hàm handler của endpoint khác.

#### Scenario: Fetching group analytics data

- **WHEN** Admin gửi request GET tới `/v1/_mw/admin/analytics/groups` (có mang thông tin xác thực)
- **THEN** Backend trả về danh sách các Group kèm theo tổng số request, chi phí USD, tokens và tỷ lệ sử dụng model của mỗi Group

#### Scenario: A request logged across multiple audit rows is counted once

- **WHEN** một request có `rid` xuất hiện hai dòng trong `mw_audit_log` (`pending` rồi `reconciled`) trong cửa sổ đang xem
- **THEN** nhóm của user đó được cộng đúng **1** vào `total_requests`, và chi phí chỉ được cộng từ dòng `reconciled`

#### Scenario: Failed requests do not add cost or tokens

- **WHEN** một user có request với trạng thái cuối là `error`
- **THEN** request đó được tính vào số lượng request của nhóm nhưng KHÔNG cộng vào `total_cost` hay `total_tokens`

#### Scenario: A request still pending is attributed to the user who sent it

- **WHEN** một request có trạng thái cuối là `pending` trong cửa sổ đang xem
- **THEN** request đó được đếm vào `total_requests` của nhóm của user đã gửi nó, và KHÔNG cộng vào `total_cost` hay `total_tokens`

#### Scenario: Group totals reconcile with the system total

- **WHEN** so sánh tổng chi phí các nhóm với `totals.cost_total_usd` từ `/v1/_mw/summary` trên cùng `start`/`end`
- **THEN** hai giá trị bằng nhau, không có sai số làm tròn

#### Scenario: Group request counts reconcile with the system total

- **WHEN** so sánh tổng số request các nhóm với `totals.requests_total` trên cùng `start`/`end`
- **THEN** hai giá trị bằng nhau, kể cả khi trong cửa sổ có request đang ở trạng thái `pending`

#### Scenario: Excel export reuses the pure function

- **WHEN** `export_report.py` cần số liệu nhóm cho sheet "Phòng ban"
- **THEN** nó gọi `compute_group_analytics(...)` trực tiếp, không gọi hàm handler `get_group_analytics(request, ...)`, và không bọc lời gọi trong `except Exception: pass`

### Requirement: Automatic Primary Group Resolution

Khi thực hiện tổng hợp dữ liệu, API Backend SHALL tự động xác định Primary Group của một user dựa trên lịch sử gia nhập nhóm từ Open WebUI DB mà không yêu cầu cấu hình. Quy tắc `created_at` **nhỏ nhất** SHALL được giữ nguyên: vì bảng `group` của Open WebUI kiêm cả vai trò đơn vị cấp quyền tool, việc một user được thêm vào nhóm thứ hai thường là cấp quyền tool chứ không phải chuyển phòng ban, nên quy tắc "gia nhập sớm nhất" giữ chi phí ở phòng gốc.

Khi phát hiện có user thuộc nhiều hơn một nhóm, hệ thống SHALL hiển thị cảnh báo cho Admin thay vì đổi quy tắc — để trường hợp admin chuyển phòng nhưng quên xóa khỏi phòng cũ không còn là lỗi im lặng.

#### Scenario: User is in multiple Open WebUI groups

- **WHEN** user thuộc nhiều hơn 1 group trong bảng `group_member` của Open WebUI
- **THEN** Primary Group được lấy là group có giá trị `created_at` nhỏ nhất (nhóm gia nhập sớm nhất)

#### Scenario: User is in exactly one group

- **WHEN** user thuộc duy nhất 1 group
- **THEN** Group đó trở thành Primary Group

#### Scenario: User has no groups

- **WHEN** user không có bản ghi nào trong bảng `group_member`
- **THEN** chi phí của user đó được quy về dòng có nhãn **"Chưa quy được phòng ban"**

#### Scenario: Multi-group membership is surfaced to the admin

- **WHEN** trong cửa sổ đang xem có ít nhất một user thuộc nhiều hơn một nhóm
- **THEN** tab Groups hiển thị cảnh báo nêu số người thuộc nhiều nhóm và nói rõ chi phí được tính vào nhóm gia nhập sớm nhất

#### Scenario: Department transfer moves the whole history

- **WHEN** Admin xóa một user khỏi phòng ban cũ rồi thêm vào phòng ban mới bên Open WebUI
- **THEN** toàn bộ chi phí lịch sử của user đó chuyển sang phòng ban mới ở mọi cửa sổ thời gian, và tab Groups hiển thị chú thích nêu rõ chi phí được phân bổ theo cơ cấu tổ chức hiện tại

### Requirement: Group Analytics Dashboard UI
Hệ thống SHALL cung cấp tab "Group Analytics" trên Admin Dashboard để trực quan hóa dữ liệu chi phí và hành vi sử dụng model của các phòng ban.

#### Scenario: Viewing Top Spenders by Department
- **WHEN** Admin truy cập tab Group Analytics
- **THEN** Bảng xếp hạng chi phí theo phòng ban (Top Spenders) được hiển thị, sắp xếp theo tổng chi phí USD từ cao đến thấp

#### Scenario: Viewing Model Preferences by Department
- **WHEN** Admin xem thông tin phân tích
- **THEN** Tỷ lệ phân bổ phần trăm của các Model (vd: 60% GPT, 40% Claude) cho từng nhóm được hiển thị dưới dạng biểu đồ hoặc thanh bar CSS

### Requirement: Group list is framed by the Open WebUI group table

Danh sách nhóm SHALL được lấy từ bảng `group` của Open WebUI làm khung, rồi ghép số liệu sử dụng vào (LEFT JOIN). Hệ thống SHALL KHÔNG suy ra danh sách nhóm từ các dòng `mw_audit_log`, vì như vậy nhóm không có lưu lượng sẽ biến mất và số lượng nhóm sẽ thay đổi theo cửa sổ thời gian đang xem.

Nhóm không có dữ liệu sử dụng trong cửa sổ SHALL hiển thị `—` cho các chỉ số dẫn xuất, KHÔNG hiển thị `0`.

#### Scenario: A group with no members still appears

- **WHEN** một nhóm tồn tại trong bảng `group` nhưng không có thành viên nào và không có dòng audit nào
- **THEN** nhóm đó vẫn xuất hiện trong bảng với các chỉ số dẫn xuất hiển thị `—`

#### Scenario: Group count is independent of the time window

- **WHEN** Admin đổi cửa sổ thời gian từ 30 ngày xuống 1 giờ
- **THEN** số lượng nhóm trong bảng không đổi, chỉ số liệu sử dụng của từng nhóm đổi

### Requirement: Unresolvable-department bucket is labelled by cause, not by omission

Dòng gom các chi phí không quy được về phòng ban nào SHALL mang nhãn **"Chưa quy được phòng ban"**, và SHALL bao gồm ba loại định danh khác nhau: (a) nhân viên có tài khoản Open WebUI nhưng chưa được thêm vào nhóm nào, (b) tài khoản đã bị xóa khỏi Open WebUI — khoá ngoại `ON DELETE CASCADE` đã xóa các dòng `group_member` nên không còn đường tra, nhưng lịch sử chi phí trong `mw_audit_log` vẫn được giữ, (c) định danh hệ thống không phải người dùng và không phải email (ví dụ `admin`), vốn không bao giờ gán được phòng ban.

Nhãn SHALL KHÔNG dùng từ ngữ hàm ý chỉ cần gán thêm là xong (ví dụ "Chưa gán phòng ban"), vì phần lớn rổ này không thể gán được.

Dòng này SHALL được giữ hiển thị trong bảng — KHÔNG được ẩn — vì nó là tín hiệu quản trị về phần chi tiêu chưa quy được trách nhiệm.

#### Scenario: A deleted Open WebUI account keeps its spending history

- **WHEN** một user từng phát sinh chi phí rồi bị xóa khỏi Open WebUI
- **THEN** chi phí lịch sử của user đó vẫn xuất hiện, được quy về dòng "Chưa quy được phòng ban", không bị loại khỏi tổng

#### Scenario: A non-user system identity is bucketed, not dropped

- **WHEN** `mw_audit_log` chứa các dòng với `user_id` không phải email và không có bản ghi tương ứng trong bảng `user` của Open WebUI
- **THEN** chi phí đó được quy về dòng "Chưa quy được phòng ban"

#### Scenario: The label is consistent across dashboard and Excel export

- **WHEN** so sánh nhãn của dòng này trên tab Groups với sheet "Phòng ban" của báo cáo Excel
- **THEN** hai nơi dùng cùng một nhãn

### Requirement: Group average latency is a weighted mean with visible coverage

Độ trễ trung bình của một nhóm SHALL được tính là `Σ(latency_sum_ms_i) / Σ(latency_sample_count_i)` trên các thành viên `i` của nhóm, trong đó `latency_sample_count` là số request thực sự có giá trị `latency_ms`. Mẫu số SHALL KHÔNG bao gồm các dòng không ghi `latency_ms`.

`breakdown_by_user` của `compute_usage_summary` SHALL xuất `latency_sum_ms` và `latency_sample_count`. Hệ thống SHALL KHÔNG dựng lại tổng thời gian bằng cách nhân một giá trị trung bình đã làm tròn với số mẫu, vì như vậy làm tròn hai lần.

Giá trị độ trễ trung bình SHALL được hiển thị kèm số mẫu, vì `latency_ms` không phủ toàn bộ request thành công (các dòng `reconciled` không ghi trường này).

#### Scenario: Rows without latency do not dilute the average

- **WHEN** một nhóm có 3 dòng audit với `latency_ms` lần lượt là `500`, `NULL`, `NULL`
- **THEN** độ trễ trung bình của nhóm là `500`, không phải `167`

#### Scenario: Coverage is shown next to the value

- **WHEN** tab Groups hiển thị độ trễ trung bình của một nhóm
- **THEN** số mẫu latency được hiển thị kèm, để người đọc biết giá trị đó dựa trên bao nhiêu request

#### Scenario: A group with no latency samples reports no average

- **WHEN** một nhóm không có request nào ghi `latency_ms`
- **THEN** ô độ trễ trung bình hiển thị `—`, không hiển thị `0`

### Requirement: Model distribution percentages count distinct requests

Tỷ lệ phần trăm sử dụng model của một nhóm SHALL được tính trên **số request duy nhất** (rid), không trên số dòng audit. Thống kê model bên trong `compute_usage_summary` SHALL đếm rid duy nhất cho mỗi model, để cột phần trăm model và cột số lượng request trên cùng một bảng dùng cùng một đơn vị đếm.

#### Scenario: A request retried through error then reconciled counts once per model

- **WHEN** một request có `rid` được ghi hai dòng cho cùng một model (một `error`, một `reconciled`)
- **THEN** model đó được đếm 1 lần cho user đó, không phải 2

#### Scenario: Each request contributes at most once per model

- **WHEN** một nhóm hiển thị danh sách phần trăm model
- **THEN** với mỗi cặp (request, model), request đó góp tối đa 1 vào số đếm của model đó — bất kể request được ghi bao nhiêu dòng audit

> Bất biến này phát biểu theo từng request thay vì theo tổng, vì một request **có thể** hợp lệ mang hai model khác nhau (retry hoặc fallback sang model khác). Trên dữ liệu dev hiện chưa có request nào như vậy, nhưng một tiêu chí dạng "tổng số đếm model ≤ tổng request" sẽ vỡ ngay khi có.

### Requirement: Invalid time range is rejected instead of silently defaulted

Endpoint group analytics SHALL dùng `_resolve_range` (`api/summary_v2.py`) để phân giải tham số thời gian, và SHALL trả `HTTP 400` khi `start`/`end` không hợp lệ hoặc `start >= end`. Endpoint SHALL KHÔNG âm thầm rơi về một cửa sổ mặc định khi tham số sai.

#### Scenario: Malformed start parameter returns 400

- **WHEN** Admin gọi endpoint với `start` không phải định dạng ISO hợp lệ
- **THEN** hệ thống trả `HTTP 400` kèm thông báo lỗi, không trả dữ liệu của một cửa sổ mặc định

#### Scenario: Reversed range returns 400

- **WHEN** Admin gọi endpoint với `start` lớn hơn hoặc bằng `end`
- **THEN** hệ thống trả `HTTP 400`

### Requirement: The unresolvable-department slice is visually distinguished in the cost chart

Trong biểu đồ tỷ trọng chi phí theo nhóm, phần "Chưa quy được phòng ban" SHALL được nhận diện theo danh tính của nó (không có `group_id`) và gán màu trung tính tách biệt khỏi bảng màu dùng cho các phòng ban thật, đồng thời SHALL được xếp cuối trong chú giải. Việc gán màu SHALL KHÔNG dựa vào vị trí trong mảng màu, vì bảng được sắp theo chi phí giảm dần nên phần này thường đứng đầu và sẽ nhận màu dành cho phòng ban.

#### Scenario: The bucket does not take a department colour

- **WHEN** dòng "Chưa quy được phòng ban" là dòng có chi phí cao nhất
- **THEN** phần tương ứng trong biểu đồ mang màu trung tính, không mang màu đầu tiên của bảng màu phòng ban, và nằm cuối chú giải

### Requirement: Each department reports its share of total system cost

Mỗi dòng nhóm SHALL mang `cost_share_of_system_percent` — chi phí của nhóm trên **tổng chi phí toàn hệ thống** của cùng cửa sổ, tức `totals.cost_total_usd`. Mẫu số SHALL là tổng hệ thống, KHÔNG phải tổng các dòng đang hiển thị, để mỗi dòng báo đúng tỷ lệ thật của nó kể cả khi danh sách bị cắt.

Vì tử số và mẫu số đến từ cùng một lời gọi `compute_usage_summary`, tổng các tỷ lệ SHALL bằng 100% mà không cần hiệu chỉnh.

#### Scenario: Shares add up to the whole

- **WHEN** Admin xem tab Groups trên một cửa sổ có dữ liệu
- **THEN** tổng `cost_share_of_system_percent` của tất cả các dòng (kể cả dòng "Chưa quy được phòng ban") bằng 100%, sai lệch không quá sai số hiển thị của một chữ số thập phân

#### Scenario: Zero total cost is guarded

- **WHEN** cửa sổ đang xem không có chi phí nào
- **THEN** `cost_share_of_system_percent` của mọi nhóm là 0, không phát sinh lỗi chia cho 0

### Requirement: Department member count is labelled distinctly from tool-access membership

Bảng Groups SHALL hiển thị `primary_member_count` dưới nhãn **"Nhân sự phòng"**. Nhãn này SHALL KHÔNG dùng lại chữ **"Thành viên"**, vì section phân quyền tool nằm cùng tab và ngay bên dưới đã dùng chữ đó cho một phép đếm khác — **mọi** membership thay vì chỉ nhóm chính.

Cột "Thành viên" hiện có ở section phân quyền tool SHALL giữ nguyên: đếm mọi membership là đúng ở đó, vì nó trả lời "bật tool cho phòng này thì bao nhiêu người thấy".

#### Scenario: The two counts diverge when someone belongs to two groups

- **WHEN** một user thuộc nhóm A (gia nhập sớm hơn) và nhóm B
- **THEN** cột "Nhân sự phòng" của nhóm B KHÔNG đếm user đó, trong khi cột "Thành viên" ở section phân quyền tool CÓ đếm — và hai cột mang hai nhãn khác nhau nên không thể đọc nhầm là cùng một số

#### Scenario: The unresolved row has no member count

- **WHEN** bảng hiển thị dòng "Chưa quy được phòng ban"
- **THEN** ô "Nhân sự phòng" của dòng đó hiển thị `—`, vì dòng đó không phải một phòng ban và không có danh sách thành viên

### Requirement: Cost is normalised by department size

Mỗi dòng nhóm SHALL mang hai chỉ tiêu trên đầu người, giữ **cả hai** vì chúng trả lời hai câu hỏi khác nhau:

- `cost_per_member` = chi phí nhóm ÷ số người có nhóm này là nhóm chính — *"trung bình mỗi nhân sự phòng này tốn bao nhiêu"*.
- `cost_per_active_member` = chi phí nhóm ÷ số người **hoạt động** — *"người thực sự dùng thì tốn bao nhiêu"*.

Cả hai SHALL hiển thị `—` khi mẫu số bằng 0, KHÔNG hiển thị `0`.

#### Scenario: A department with no members reports no per-head cost

- **WHEN** một phòng ban có 0 thành viên
- **THEN** cả hai ô chi phí trên đầu người hiển thị `—` kèm chú giải, không hiển thị `0` và không phát sinh lỗi chia cho 0

#### Scenario: Per-head cost separates spend from headcount

- **WHEN** phòng A chi nhiều hơn phòng B về số tuyệt đối nhưng có nhiều thành viên hơn theo tỷ lệ lớn hơn
- **THEN** `cost_per_member` của phòng A nhỏ hơn phòng B, phản ánh đúng rằng phòng A tiêu ít hơn trên mỗi đầu người

### Requirement: Active members are the intersection of activity and membership

`active_member_count` của một nhóm SHALL là **giao** của hai tập: người có ít nhất một request trong cửa sổ đang xem, và người có nhóm này là nhóm chính. Hệ thống SHALL KHÔNG chỉ đếm người có hoạt động rồi gán theo nhóm.

Phép giao là bắt buộc vì `mw_audit_log` giữ lịch sử của cả người đã rời phòng ban: không giao thì một người đã bị xoá khỏi `group_member` vẫn được tính là đang hoạt động của nhóm, và số người hoạt động có thể **vượt** tổng số thành viên.

Hệ quả kiểm chứng được: `active_member_count <= primary_member_count` với **mọi** nhóm và **mọi** cửa sổ.

#### Scenario: Active never exceeds total

- **WHEN** tính chỉ tiêu cho bất kỳ nhóm nào trên bất kỳ cửa sổ nào
- **THEN** số thành viên hoạt động nhỏ hơn hoặc bằng số thành viên của nhóm đó

#### Scenario: Someone who left the department is not counted as active

- **WHEN** một user từng phát sinh request trong cửa sổ rồi bị xoá khỏi mọi nhóm bên Open WebUI
- **THEN** user đó không được tính vào `active_member_count` của bất kỳ phòng ban nào; chi phí của họ vẫn xuất hiện ở dòng "Chưa quy được phòng ban"

### Requirement: The department scorecard excludes unattributable spending from every denominator

Tab Groups SHALL hiển thị ba thẻ ở **đầu tab**: *Số phòng ban*, *Nhân sự đã có phòng ban*, *Chi phí bình quân mỗi phòng ban*. Dòng "Chưa quy được phòng ban" SHALL bị loại khỏi **mọi mẫu số** của ba thẻ này — nó không phải một phòng ban — nhưng SHALL vẫn hiển thị trong bảng bên dưới.

Vì tổng chi phí trong bảng do đó **lớn hơn** phần được chia trong thẻ *Chi phí bình quân mỗi phòng ban*, hệ thống SHALL hiển thị chú thích ngay dưới cụm thẻ, nêu số phòng ban và chỉ ra phần chi phí nằm ngoài. Chú thích này là **bắt buộc**, không phải trang trí: thiếu nó thì người đọc cộng cột chi phí rồi chia cho số phòng ban sẽ ra một con số khác hẳn mà không ai giải thích được.

Chú thích SHALL kèm giải thích ba loại định danh nằm trong dòng đó: nhân viên chưa được gán phòng ban, tài khoản đã bị xoá khỏi Open WebUI, và định danh hệ thống không phải người dùng.

Section "🔧 Phân quyền Tool theo phòng ban" SHALL giữ nguyên vị trí và nội dung; scorecard chỉ được chèn thêm lên đầu tab.

#### Scenario: Scorecard denominators ignore the unresolved row

- **WHEN** dòng "Chưa quy được phòng ban" có chi phí lớn hơn 0
- **THEN** thẻ *Số phòng ban* không đếm nó, và thẻ *Chi phí bình quân mỗi phòng ban* không cộng chi phí của nó vào tử số

#### Scenario: The gap between table and scorecard is explained on screen

- **WHEN** Admin xem cụm scorecard
- **THEN** ngay dưới cụm thẻ có chú thích nêu số phòng ban và cho biết phần chi phí còn lại nằm ở dòng "Chưa quy được phòng ban" trong bảng, kèm giải thích ba loại định danh của dòng đó

#### Scenario: Department count does not follow the time window

- **WHEN** Admin đổi cửa sổ thời gian
- **THEN** thẻ *Số phòng ban* không đổi giá trị, vì nó mô tả cơ cấu tổ chức chứ không mô tả cửa sổ

### Requirement: Only scorecards carry period comparison

Badge so kỳ KT/CK SHALL chỉ gắn cho thẻ *Chi phí bình quân mỗi phòng ban*. Hai thẻ còn lại (*Số phòng ban*, *Nhân sự đã có phòng ban*) là snapshot cơ cấu tổ chức, không có trục thời gian, nên SHALL KHÔNG có badge so kỳ.

Các cột trong bảng breakdown SHALL KHÔNG được khai báo trong `metrics_registry.js` và SHALL KHÔNG mang badge so kỳ, nhất quán với luật đã có: chỉ scorecard mới vào registry.

Để badge hoạt động, tab Groups SHALL có cơ chế lấy dữ liệu của ba cửa sổ (hiện tại, kỳ trước, cùng kỳ năm trước). Cơ chế này chưa tồn tại ở tab Groups và phải được dựng; khai báo trong registry là điều kiện cần nhưng không đủ.

#### Scenario: Structure cards have no comparison badge

- **WHEN** cụm scorecard hiển thị
- **THEN** chỉ thẻ *Chi phí bình quân mỗi phòng ban* có badge KT/CK; *Số phòng ban* và *Nhân sự đã có phòng ban* không có

#### Scenario: Table columns are not registry metrics

- **WHEN** bảng Groups render các cột mới
- **THEN** không cột nào được tra trong `metrics_registry.js`, và không cột nào mang badge so kỳ

### Requirement: The headcount card shows how many staff still have no department

Thẻ nhân sự SHALL hiển thị **cả tử số và mẫu số**: số người đã được gán phòng ban trên tổng số tài khoản đang hoạt động, dưới nhãn **"Nhân sự đã có phòng ban"**.

Nhãn SHALL KHÔNG là "Tổng thành viên" hay bất kỳ chữ nào đọc ra thành *tổng nhân sự của tổ chức* — con số này chỉ đếm người **đã có phòng ban**. Trên dev có 12 tài khoản đang hoạt động nhưng chỉ 5 người có phòng ban; hiện `5` trơ dưới nhãn "Tổng thành viên" sẽ khiến người đọc tin tổ chức có 5 người.

Hiện cả mẫu số là bắt buộc vì phần chênh chính là **nguyên nhân** của chi phí không quy được: người chưa có phòng ban thì chi phí của họ không thể quy về đâu. Khác với chi phí chưa quy được — vốn là hệ quả — số người chưa gán là việc xử lý được ngay.

#### Scenario: The card exposes the unassigned gap

- **WHEN** hệ thống có nhiều tài khoản đang hoạt động hơn số người đã được gán phòng ban
- **THEN** thẻ hiển thị dạng `N / M` với `N` là số người đã có phòng ban và `M` là tổng tài khoản đang hoạt động, dưới nhãn không hàm ý `N` là toàn bộ nhân sự

### Requirement: The unresolved row carries no per-head metrics

Dòng "Chưa quy được phòng ban" SHALL trả `None` cho `primary_member_count`, `active_member_count`, `cost_per_member` và `cost_per_active_member`. Dòng này không phải một đơn vị nên mọi chỉ tiêu "trên đầu người của đơn vị" đều không áp dụng, dù nó **có** người phát sinh chi phí.

Bất biến `active_member_count <= primary_member_count` SHALL chỉ được kiểm trên các nhóm có `group_id`.

#### Scenario: Active count is absent, not zero, for the unresolved row

- **WHEN** dòng "Chưa quy được phòng ban" có nhiều người phát sinh request trong cửa sổ
- **THEN** các ô chỉ tiêu trên đầu người của dòng đó hiển thị `—`, không hiển thị số người hoạt động và không hiển thị `0`

