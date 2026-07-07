## Why

Hiện tại, hệ thống LLM Middleware lưu trữ bảng giá các model trong database PostgreSQL (`mw_prices`) và dự phòng tại file `llm-mw/prices.json`. Tuy nhiên, quản trị viên (QTV) không có giao diện (UI) để cấu hình, chỉnh sửa đơn giá này mà phải thao tác thủ công, gây bất tiện và dễ xảy ra lỗi. Đồng thời, hệ thống cũng thiếu một trang so sánh trực quan chi phí giữa các model và nhà cung cấp để hỗ trợ QTV tối ưu hóa ngân sách và cấu hình quota cho người dùng.

## What Changes

- **Thêm Tab Bảng giá (Prices)**: Tích hợp tab quản lý giá mới trên Admin Dashboard.
- **Trình chỉnh sửa giá Model (Price Editor)**: Cho phép xem danh sách đơn giá, thêm mới, sửa đổi và xóa cấu hình giá của từng model (input, output, image cost, ghi chú).
- **Bộ mô phỏng truy vấn (Query Simulator)**: Cung cấp ô nhập số lượng Token Input/Output dự kiến để tính toán trực tiếp chi phí một phiên chat.
- **Biểu đồ So sánh Chi phí (Cost Comparison)**: Sử dụng các thanh biểu đồ CSS trực quan để xếp hạng chi phí của các model từ rẻ nhất đến đắt nhất dựa trên số lượng token được nhập từ bộ mô phỏng.
- **Tự động sao lưu**: Mọi thao tác chỉnh sửa bảng giá trên giao diện sẽ cập nhật trực tiếp vào cơ sở dữ liệu `mw_prices` và đồng bộ sao lưu tự động ra file cấu hình `llm-mw/prices.json`.

## Capabilities

### New Capabilities

- `model-price-management`: Cung cấp giao diện quản lý CRUD bảng giá model trong Middleware và đồng bộ tự động ra file JSON dự phòng.
- `model-cost-comparison`: Cung cấp giao diện mô phỏng và xếp hạng trực quan chi phí sử dụng giữa các model và nhà cung cấp.

### Modified Capabilities

<!-- Không có thay đổi yêu cầu đối với các đặc tả hiện có -->

## Impact

- **Backend**:
  - Tạo mới file `llm-mw/api/price_admin.py` chứa các endpoints `GET`, `POST` và `DELETE` cho bảng giá.
  - Cập nhật file `llm-mw/main.py` để đăng ký các endpoints mới này.
- **Frontend**:
  - Cập nhật `llm-mw/dashboard/index.html` để thêm giao diện tab Bảng giá, bộ mô phỏng, biểu đồ so sánh chi phí và modal Thêm/Sửa giá.
  - Tạo mới file `llm-mw/dashboard/js/prices.js` chứa logic điều khiển giao diện so sánh và CRUD.
  - Cập nhật `llm-mw/dashboard/js/tabs.js` để tích hợp sự kiện chuyển tab.
