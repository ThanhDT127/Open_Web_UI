## 1. Cấu hình Database & Kết nối

- [ ] 1.1 Khởi tạo kết nối phụ chỉ đọc (Read-only Pool) tới DB `openwebui` trong `llm-mw/core/db.py`
- [ ] 1.2 Bổ sung hàm kiểm tra cấu trúc bảng `"user"` bên DB `openwebui` khi khởi động Middleware

## 2. Phát triển Core Lazy Provisioning

- [ ] 2.1 Cập nhật hàm `find_user` trong `llm-mw/core/auth.py` để tự động kích hoạt tìm kiếm chéo sang DB `openwebui` khi không tìm thấy key cục bộ
- [ ] 2.2 Viết hàm khởi tạo lười (Lazy Provision) tạo dòng mới trong `mw_users` kèm theo quota mặc định và sinh subkey mới
- [ ] 2.3 Tích hợp Thread Lock và database transaction để đảm bảo an toàn luồng ghi ghi trùng lặp (Race condition)

## 3. Cải tiến API & Đồng bộ tự động

- [ ] 3.1 Cập nhật API `/v1/_mw/quota-status` để trả về plaintext subkey cho người dùng khi gọi lần đầu (hoặc từ IP an toàn nội bộ)
- [ ] 3.2 Viết API đối chiếu tài khoản `/v1/_mw/admin/users/sync-status` trả về danh sách các user bị lệch đồng bộ
- [ ] 3.3 Tích hợp logic kiểm tra trạng thái khóa tài khoản (`active = false` bên Open WebUI) trong luồng xác thực tin nhắn

## 4. Thiết kế & Xây dựng Dashboard Quản trị Thông minh

- [ ] 4.1 Thêm giao diện tab/view "Sync Status" bên trong trang quản lý Users của Admin Dashboard
- [ ] 4.2 Triển khai tính năng "Proactive Sync" (Nút Sync Now) cho phép Admin chủ động đồng bộ trước người dùng
- [ ] 4.3 Triển khai kiến trúc hiển thị mở rộng: Bọc các bảng dữ liệu bằng CSS Scrollable Container và Sticky Header
- [ ] 4.4 Cài đặt thuật toán điều hướng sự chú ý (Smart Sorting): Sắp xếp bảng Quota theo % sử dụng, bảng Sync theo trọng số lỗi hệ thống

## 5. Viết Test & Xác minh

- [ ] 5.1 Viết unit test giả lập người dùng mới đăng nhập lần đầu và kiểm tra xem Middleware có tự tạo subkey/quota không
- [ ] 5.2 Thử nghiệm kịch bản khóa người dùng trên Open WebUI và xác nhận subkey bên Middleware bị vô hiệu hóa lập tức
