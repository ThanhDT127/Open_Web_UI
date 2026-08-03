## ADDED Requirements

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
