## 1. Backend API Implementation

- [x] 1.1 Tạo file `llm-mw/api/price_admin.py` với các endpoint CRUD bảng giá `/v1/_mw/admin/prices` bảo vệ bởi `require_admin_or_session`.
- [x] 1.2 Viết logic tự động đồng bộ hóa cơ sở dữ liệu `mw_prices` sang file backup `prices.json` sau mỗi thao tác cập nhật/xóa.
- [x] 1.3 Cập nhật file `llm-mw/main.py` để import và đăng ký các endpoint quản lý giá mới.

## 2. Giao diện Frontend & Bố cục (Layout & Tabs)

- [x] 2.1 Cập nhật `llm-mw/dashboard/index.html` để thêm tab điều hướng `💸 Prices`.
- [x] 2.2 Tạo vùng hiển thị tab `#pricesTab` trong `index.html` chứa bộ mô phỏng (Query Simulator) và bảng dữ liệu giá.
- [x] 2.3 Tạo Modal popup `#priceModal` trong `index.html` để phục vụ thêm mới/chỉnh sửa đơn giá.
- [x] 2.4 Cập nhật `llm-mw/dashboard/js/tabs.js` để gọi hàm load dữ liệu khi người dùng chuyển sang tab Prices.

## 3. Logic xử lý Frontend & So sánh giá (JS Logic)

- [x] 3.1 Tạo file `llm-mw/dashboard/js/prices.js` chứa các hàm fetch, render danh sách giá, và xử lý lưu/xóa giá model qua API.
- [x] 3.2 Viết logic tính toán chi phí mô phỏng dựa trên Input/Output token của bộ mô phỏng và render biểu đồ thanh CSS trong `js/prices.js`.
- [x] 3.3 Đăng ký các hàm điều khiển vào đối tượng toàn cục `window.dashboardAPI` để liên kết các nút bấm trong HTML.

## 4. Kiểm thử & Xác thực (Verification)

- [ ] 4.1 Test thủ công tạo model mới `test-model-1`, kiểm tra hiển thị trên UI và kiểm tra file backup `prices.json`.
- [ ] 4.2 Test thủ công sửa đổi đơn giá và xác nhận biểu đồ so sánh chi phí thay đổi trực quan theo thời gian thực khi chỉnh bộ mô phỏng.
- [ ] 4.3 Test thủ công xóa model và verify dữ liệu biến mất khỏi database cũng như file JSON.
