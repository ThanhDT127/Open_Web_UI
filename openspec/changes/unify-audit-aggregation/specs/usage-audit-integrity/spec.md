## ADDED Requirements

### Requirement: Single aggregation implementation for audit metrics

Mọi endpoint dashboard tổng hợp số liệu từ `mw_audit_log` SHALL dùng chung **một** hiện thực gom duy nhất. Endpoint SHALL KHÔNG tự viết vòng lặp gom riêng cho bảng này.

Hiện thực dùng chung SHALL là một hàm thuần — không phụ thuộc đối tượng `Request`, không thực hiện xác thực, không ném lỗi tầng HTTP — để mọi endpoint gọi trực tiếp mà không phải đi qua endpoint khác.

Hiện thực dùng chung SHALL cho phép bên gọi quyết định có giới hạn số dòng của các bảng xếp hạng hay không, để endpoint hiển thị đầy đủ danh sách không bị cắt bởi giới hạn mặc định của endpoint khác.

#### Scenario: Hai tab dashboard trả về cùng một con số
- **WHEN** tab Usage và tab Chat Analytics cùng hỏi số liệu cho một khoảng thời gian giống nhau
- **THEN** tổng số request, tổng tokens và tổng chi phí của hai tab bằng nhau

#### Scenario: Endpoint mới không được tự gom lại
- **WHEN** một endpoint dashboard mới cần số liệu tổng hợp từ `mw_audit_log`
- **THEN** endpoint đó gọi hàm gom dùng chung, không viết truy vấn và vòng lặp gom của riêng nó

### Requirement: Request metrics counted by distinct request ID

Mọi chỉ tiêu đếm request SHALL đếm theo `rid` **duy nhất**, KHÔNG đếm theo số dòng của `mw_audit_log`. Khi một `rid` có nhiều dòng, trạng thái dùng để phân loại request đó SHALL là trạng thái của dòng có `ts` mới nhất.

Yêu cầu này áp cho tất cả chỉ tiêu request: tổng số, chuỗi thời gian, phân bổ theo model, phân bổ theo giờ trong ngày, và số request của từng người dùng.

#### Scenario: Cặp pending và reconciled của cùng một request
- **WHEN** một request sinh ra hai dòng audit cùng `rid` — một dòng `status='pending'` và một dòng `status='reconciled'`
- **THEN** mọi chỉ tiêu request đếm nó **một** lần, và phân loại nó theo trạng thái `reconciled`

#### Scenario: Số dòng nhiều hơn số request
- **WHEN** `mw_audit_log` có 264 dòng trong khoảng đang xem, tương ứng 189 `rid` duy nhất
- **THEN** tổng số request báo cáo là `189`, không phải `264`

#### Scenario: Request bắc cầu qua ranh giới giờ không bị đếm đôi
- **WHEN** một request có dòng `pending` lúc 14:59 và dòng `reconciled` lúc 15:01
- **THEN** biểu đồ phân bổ theo giờ tính request đó vào đúng **một** khung giờ, không cộng vào cả hai
