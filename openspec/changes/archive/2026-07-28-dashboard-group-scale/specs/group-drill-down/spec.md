## ADDED Requirements

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
