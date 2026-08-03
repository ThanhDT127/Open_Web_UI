# group-drill-down Specification

## Purpose
TBD - created by archiving change 2026-07-02-group-analytics-drilldown. Update Purpose after archive.
## Requirements
### Requirement: Admin có thể click vào một nhóm để xem chi tiết (drill-down) hạn mức sử dụng của người dùng trong nhóm đó
Hệ thống SHALL cung cấp một API và giao diện UI cho phép quản trị viên xem chi tiết hạn mức (quota) đã sử dụng của từng người dùng thuộc một nhóm cụ thể. Dữ liệu này phải được áp dụng cùng bộ lọc thời gian đang được thiết lập trên toàn cục của dashboard. Bảng dữ liệu phụ (chứa danh sách users) SHALL tái sử dụng cơ chế cuộn chuột (scroll) giống với bảng User Quota Management để tránh làm giao diện bị kéo giãn quá mức khi một nhóm có quá nhiều thành viên.

#### Scenario: Xem chi tiết (drill-down) thành công qua giao diện UI
- **WHEN** admin click vào một dòng nhóm (group row) trong bảng Group Analytics
- **THEN** hệ thống gọi API lấy dữ liệu phân tích từng người dùng cho nhóm đó và mở rộng một bảng phụ (dạng accordion) hiển thị các chỉ số sử dụng của từng người dùng trong khoảng thời gian đã chọn.

#### Scenario: Cuộn chuột trên danh sách user đông đúc
- **WHEN** bảng phụ mở ra một danh sách chứa rất nhiều người dùng (users)
- **THEN** bảng phụ sẽ hiển thị thanh cuộn chuột (scroll bar) bên trong một vùng không gian giới hạn chiều cao (max-height), tái sử dụng class CSS của bảng User Quota Management.

### Requirement: Drill-down uses the same membership definition as the parent row

Bảng drill-down của một nhóm SHALL xác định tập thành viên bằng **cùng một định nghĩa** mà bảng cha dùng để gộp chi phí, tức Primary Group (`created_at` nhỏ nhất). Drill-down SHALL KHÔNG liệt kê theo toàn bộ membership của nhóm, vì khi một user thuộc nhiều nhóm thì user đó sẽ xuất hiện trong drill-down của mọi nhóm kèm chi phí, trong khi bảng cha chỉ cộng chi phí đó vào một nhóm.

Hệ quả kiểm chứng được: tổng chi phí các dòng trong drill-down của một nhóm SHALL bằng chi phí của nhóm đó ở bảng cha.

#### Scenario: Drill-down total matches the parent row

- **WHEN** Admin mở drill-down của một nhóm
- **THEN** tổng chi phí các thành viên trong bảng phụ bằng chi phí của nhóm đó ở dòng bảng cha, trên cùng cửa sổ thời gian

#### Scenario: A user in two groups appears in only one drill-down

- **WHEN** một user thuộc cả nhóm A (gia nhập sớm hơn) và nhóm B, và Admin mở drill-down của nhóm B
- **THEN** user đó KHÔNG xuất hiện trong drill-down của nhóm B; user đó chỉ xuất hiện trong drill-down của nhóm A

#### Scenario: Member share of the group never exceeds the whole

- **WHEN** tính tỷ lệ chi phí của từng thành viên trên tổng chi phí của nhóm
- **THEN** tổng các tỷ lệ đó không vượt quá 100%

### Requirement: Unresolvable-department drill-down must not fail open

Khi Admin mở drill-down của dòng "Chưa quy được phòng ban", nếu truy vấn Open WebUI để xác định ai đã có phòng ban bị lỗi, hệ thống SHALL báo lỗi cho người dùng. Hệ thống SHALL KHÔNG bỏ qua bước lọc rồi trả về danh sách người dùng chưa được lọc, vì kết quả đó trông như dữ liệu thật nhưng thực chất là toàn bộ người dùng của hệ thống bị dán nhãn sai.

Danh sách thành viên của dòng này SHALL được suy ra từ cùng một map Primary Group đã dùng cho bảng cha, không cần truy vấn Open WebUI lần thứ hai.

#### Scenario: Open WebUI query failure surfaces as an error

- **WHEN** Admin mở drill-down của dòng "Chưa quy được phòng ban" và truy vấn sang Open WebUI DB thất bại
- **THEN** bảng phụ hiển thị thông báo lỗi, KHÔNG hiển thị danh sách người dùng

#### Scenario: Users who do have a department are excluded

- **WHEN** Admin mở drill-down của dòng "Chưa quy được phòng ban"
- **THEN** danh sách chỉ gồm các định danh không phân giải được về một Primary Group nào, và không gồm bất kỳ user nào đang có Primary Group

### Requirement: Drill-down member spending reflects the shared aggregation source

Số liệu từng thành viên trong drill-down SHALL đến từ `compute_usage_summary` qua hàm thuần dùng chung, cùng đơn vị đếm (rid duy nhất) và cùng luật lọc trạng thái (`ok`/`reconciled` mới cộng tiền) như bảng cha và như tab Usage. Drill-down SHALL KHÔNG tự duyệt `mw_audit_log`.

#### Scenario: A member's request count matches the Usage tab

- **WHEN** so sánh số request của một user trong drill-down với số request của user đó trên bảng Top Users của tab Usage, cùng cửa sổ thời gian, **và user đó nằm trong 20 dòng mà endpoint Usage trả về**
- **THEN** hai giá trị bằng nhau

> Điều kiện 20 dòng là bắt buộc: `get_summary_v2` cắt `breakdown_by_user[:20]` trước khi trả về, nên user ngoài top 20 không có gì để đối chiếu trên UI. Muốn kiểm cho toàn bộ user thì so với payload đầy đủ của `compute_usage_summary`, không so với phản hồi của endpoint.

#### Scenario: Deleted users keep their drill-down history

- **WHEN** một user đã bị xóa khỏi Open WebUI nhưng còn lịch sử trong `mw_audit_log`
- **THEN** chi phí của user đó vẫn xuất hiện trong drill-down của dòng "Chưa quy được phòng ban", với tên hiển thị rơi về định danh gốc

### Requirement: Each member reports their share of the department's cost

Mỗi dòng trong drill-down SHALL mang `cost_share_of_group_percent` — tỷ lệ chi phí của thành viên đó trên **tổng chi phí của nhóm đang mở**, không phải trên tổng hệ thống. Tên field SHALL nói rõ mẫu số, không dùng lại tên của bảng nhóm (mẫu số ở đó là tổng hệ thống). Nhãn cột: **"Tỷ trọng trong phòng"**.

Vì tập thành viên của drill-down đã là phân hoạch theo nhóm chính — mỗi người thuộc đúng một nhóm — tổng các tỷ lệ SHALL bằng 100% và SHALL KHÔNG bao giờ vượt quá.

#### Scenario: Member shares add up to the department

- **WHEN** Admin mở drill-down của một nhóm có chi phí lớn hơn 0
- **THEN** tổng tỷ lệ của các thành viên bằng 100%, sai lệch không quá sai số hiển thị của một chữ số thập phân

#### Scenario: A department with no cost guards the division

- **WHEN** Admin mở drill-down của một nhóm có tổng chi phí bằng 0
- **THEN** tỷ lệ của mọi thành viên là 0, không phát sinh lỗi chia cho 0

### Requirement: Quota utilisation is read in bulk and never mutates state

Drill-down SHALL hiển thị phần trăm hạn mức đã dùng của **kỳ quota hiện tại** cho từng thành viên, đọc từ `mw_users` bằng **một truy vấn theo lô** cho toàn bộ danh sách.

Hệ thống SHALL KHÔNG gọi hàm lấy quota theo từng người để dựng bảng này. Hàm đó thực hiện reset kỳ quota như tác dụng phụ, nên gọi nó một lần cho mỗi dòng nghĩa là **một lần render trang có thể sửa dữ liệu quota** của toàn bộ người dùng trong nhóm.

Phần trăm SHALL dùng đúng công thức mà cơ chế cảnh báo quota đang dùng, để một người sắp bị cảnh báo và một người hiển thị gần 100% ở đây là cùng một người.

#### Scenario: Rendering the drill-down does not change quota state

- **WHEN** Admin mở drill-down của một nhóm nhiều lần liên tiếp
- **THEN** không bản ghi quota nào trong `mw_users` bị thay đổi, và số kỳ quota không bị reset

#### Scenario: Quota is read once for the whole list

- **WHEN** drill-down hiển thị N thành viên
- **THEN** hệ thống thực hiện một truy vấn quota cho cả danh sách, không phải N truy vấn

### Requirement: Unavailable quota is distinguished from unlimited quota

Ô phần trăm hạn mức SHALL phân biệt ba trạng thái, vì "không biết" và "vô hạn" là hai nghĩa ngược nhau và gộp lại là dán nhãn sai:

- Định danh **không có** bản ghi trong `mw_users` — tài khoản hệ thống, hoặc tài khoản đã bị xoá khỏi Open WebUI — SHALL hiển thị `—` kèm chú giải nêu lý do.
- Tài khoản **đã xoá mềm** SHALL hiển thị `—` kèm chú giải "tài khoản đã xoá". Hạn mức chỉ có nghĩa khi còn hiệu lực; điều này khác với chi phí, vốn đã phát sinh nên vĩnh viễn có nghĩa và SHALL vẫn hiển thị.
- Hạn mức **bằng hoặc nhỏ hơn 0** SHALL hiển thị **"Không giới hạn"**, KHÔNG hiển thị `—`: giá trị này tra được và câu trả lời là vô hạn.

#### Scenario: A system identity shows no quota with a reason

- **WHEN** drill-down chứa một định danh không phải người dùng và không có bản ghi trong `mw_users`
- **THEN** ô hạn mức hiển thị `—` kèm chú giải cho biết đây không phải tài khoản người dùng, và chi phí của định danh đó vẫn hiển thị bình thường

#### Scenario: Unlimited quota is not shown as unknown

- **WHEN** một thành viên có hạn mức bằng 0 hoặc nhỏ hơn
- **THEN** ô hạn mức hiển thị "Không giới hạn", không hiển thị `—` và không hiển thị `0%`

#### Scenario: A soft-deleted account keeps its spending but not its quota

- **WHEN** một thành viên đã bị xoá mềm nhưng còn lịch sử chi phí trong cửa sổ
- **THEN** cột chi tiêu hiển thị chi phí thật của họ, còn ô hạn mức hiển thị `—` kèm chú giải "tài khoản đã xoá"

### Requirement: Columns on different time axes are labelled with their period

Drill-down đặt cột **chi tiêu theo cửa sổ đang xem** ngay cạnh cột **hạn mức theo kỳ quota hiện tại**. Hai cột này SHALL mang nhãn nêu rõ mốc thời gian của từng cột — nhãn chốt: **"Chi tiêu (khoảng đang xem)"** và **"Đã dùng hạn mức (kỳ này)"**.

Nhãn trống như "Chi tiêu" và "Quota" SHALL KHÔNG được dùng: khi hai cột cạnh nhau mà không nói trục thời gian, người đọc mặc định chúng cùng kỳ và sẽ suy ra sai.

#### Scenario: The two periods are stated on the headers

- **WHEN** Admin mở drill-down
- **THEN** tiêu đề cột chi tiêu nêu rõ nó theo khoảng thời gian đang chọn, và tiêu đề cột hạn mức nêu rõ nó theo kỳ quota hiện tại

#### Scenario: Changing the window moves only one of the two columns

- **WHEN** Admin đổi cửa sổ thời gian của dashboard
- **THEN** cột chi tiêu đổi theo, còn cột phần trăm hạn mức giữ nguyên vì nó thuộc kỳ quota chứ không thuộc cửa sổ

