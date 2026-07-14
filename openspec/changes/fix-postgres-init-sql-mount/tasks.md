## 1. Dọn dẹp môi trường và Sửa cấu hình

- [x] 1.1 Dừng các container Docker hiện tại bằng cách chạy lệnh `docker compose down`
- [x] 1.2 Xóa thư mục lỗi `./scripts/init_pgvector.sql` tự động tạo bởi Docker trên máy host
- [x] 1.3 Cập nhật đường dẫn mount volume cho Postgres trong file [docker-compose.yml](file:///d:/Works/openwebui_clone/docker-compose.yml) từ `./scripts/init_pgvector.sql` thành `./scripts/sql/init_pgvector.sql`

## 2. Khởi động và Xác minh hoạt động

- [x] 2.1 Khởi chạy container `postgres` bằng lệnh `docker compose up -d postgres`
- [x] 2.2 Xác minh container `postgres` khởi động thành công và ở trạng thái healthy bằng cách chạy `docker ps`
- [x] 2.3 Thực thi bộ test tích hợp cục bộ [test_unified_identity.py](file:///d:/Works/openwebui_clone/llm-mw/test_unified_identity.py) để kiểm tra kết nối database hoạt động bình thường
