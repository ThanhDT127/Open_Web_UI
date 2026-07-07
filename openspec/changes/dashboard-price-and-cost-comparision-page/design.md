## Context

Bảng giá model LLM hiện tại được lưu trữ trong bảng `mw_prices` của database PostgreSQL và file sao lưu dự phòng tại `llm-mw/prices.json`. Middleware sử dụng dữ liệu này để tính toán chi phí sử dụng của user (`cost_usd`) phục vụ việc quản lý quota và hiển thị thống kê. 

Thiết kế này sẽ cung cấp một phân hệ giao diện hoàn chỉnh trên Admin Dashboard để QTV thao tác chỉnh sửa đơn giá (CRUD) và mô phỏng so sánh chi phí một cách trực quan, giải quyết việc cấu hình giá thủ công phức tạp như hiện nay.

## Goals / Non-Goals

**Goals:**
- Triển khai các API endpoints mới `/v1/_mw/admin/prices` để đọc, ghi và xóa thông tin giá model trong database PostgreSQL.
- Đảm bảo tính nhất quán dữ liệu: Sau khi ghi vào database, hệ thống sẽ tự động đồng bộ hóa nội dung mới nhất ghi đè vào file sao lưu `prices.json`.
- Thiết kế giao diện tab **Prices** mới tích hợp:
  - Bộ mô phỏng số lượng token truy vấn (Query Simulator).
  - Biểu đồ thanh so sánh trực quan (Cost Comparison chart) sử dụng CSS thuần.
  - Bảng CRUD hiển thị thông tin chi tiết và hỗ trợ sửa đổi giá.
- Ràng buộc dữ liệu đầu vào: Chỉ chấp nhận các số thực không âm đối với đơn giá.

**Non-Goals:**
- Không thay đổi cấu trúc schema của bảng `mw_prices` (dữ liệu dạng JSONB vẫn đáp ứng tốt yêu cầu lưu trữ động).
- Không tự động phân tích hoặc hiển thị nhận xét bằng chữ (Quick Insights) để tránh gò bó giao diện và logic phức tạp không cần thiết.
- Không chỉnh sửa trực tiếp file `prices.json` từ phía frontend (mọi thay đổi phải đi qua backend API).

## Decisions

### 1. Kiến trúc Module hóa API ở Backend
- **Lựa chọn:** Tạo mới file `llm-mw/api/price_admin.py` thay vì gộp chung vào `admin.py` hay `user_admin.py`.
- **Lý do:** Giúp mã nguồn tách biệt, dễ bảo trì và dễ dàng import/register router trong `main.py`.

### 2. Thiết kế Giao diện Biểu đồ So sánh
- **Lựa chọn:** Sử dụng thanh đo bằng CSS thuần (HTML `div` kết hợp thuộc tính `style="width: x%"` và CSS flexbox) thay vì tích hợp thêm thư viện vẽ biểu đồ nặng như Chart.js cho phần so sánh này.
- **Lý do:** Giúp Dashboard tải nhanh hơn, đồng bộ màu sắc dark/light mode dễ dàng với giao diện hiện tại của dự án, và dễ định dạng hiển thị text đơn giá bên cạnh mỗi thanh.

### 3. Đồng bộ hóa File Backup `prices.json`
- **Lựa chọn:** Mỗi khi có request cập nhật hoặc xóa giá thành công trong database, backend sẽ tự động gọi hàm đọc toàn bộ dữ liệu mới nhất từ DB và ghi đè vào `prices.json`.
- **Lý do:** Đảm bảo file backup `prices.json` luôn phản ánh chính xác trạng thái mới nhất của database, giữ nguyên tính năng fallback khi database gặp sự cố.

### 4. Vô hiệu hóa chỉnh sửa Tên Model trong chế độ Edit
- **Lựa chọn:** Khi sửa đổi giá, trường tên model (`model_name`) sẽ bị khóa (read-only). QTV muốn đổi tên model phải thực hiện Thêm mới và Xóa model cũ.
- **Lý do:** Tránh việc vô tình làm thay đổi tên model chính yếu, làm đứt gãy việc liên kết tính toán chi phí với các bản ghi log audit cũ.

## Risks / Trade-offs

- **[Risk]** Nhập giá trị giá âm hoặc giá trị chuỗi không hợp lệ gây lỗi tính toán hoặc lỗi chuyển đổi kiểu dữ liệu.
  - **Mitigation:** Áp dụng Pydantic validation ở backend và ép kiểu `parseFloat` kèm min value là `0` ở frontend trước khi gửi dữ liệu.
- **[Risk]** Ghi đồng thời dữ liệu giá từ nhiều phiên đăng nhập admin khác nhau gây mất dữ liệu.
  - **Mitigation:** Thao tác CRUD bảng giá có tần suất rất thấp (chỉ khi cập nhật bảng giá hãng). PostgreSQL và cơ chế ghi đè của file JSON đảm bảo tính nhất quán dữ liệu tại thời điểm commit.
