## MODIFIED Requirements

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

## ADDED Requirements

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
