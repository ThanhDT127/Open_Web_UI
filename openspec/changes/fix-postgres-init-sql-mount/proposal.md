## Why

File `scripts/init_pgvector.sql` đã bị di chuyển sang `scripts/sql/init_pgvector.sql` trong các commit trước, nhưng cấu hình volume mount trong `docker-compose.yml` vẫn trỏ về đường dẫn cũ. Khi chạy `docker compose up`, Docker tự động tạo một thư mục trống tên `init_pgvector.sql` trên máy host tại đường dẫn cũ và thử mount nó đè lên file trong container, dẫn đến lỗi xung đột mount và làm sập Postgres database.

## What Changes

- Cập nhật đường dẫn mount volume cho Postgres trong [docker-compose.yml](file:///d:/Works/openwebui_clone/docker-compose.yml) để trỏ đến đúng vị trí mới: `./scripts/sql/init_pgvector.sql`.
- Khôi phục hoạt động của Postgres container và kết nối của Middleware cục bộ.
- Xóa thư mục rác `scripts/init_pgvector.sql` phát sinh do Docker tự tạo nhầm trên host.

## Capabilities

### New Capabilities

- `docker-postgres-config`: Cấu hình dịch vụ cơ sở dữ liệu Postgres trong docker-compose.yml để mount đúng file khởi tạo SQL.

### Modified Capabilities

*(None)*

## Impact

- **Hạ tầng / Môi trường chạy**: Sửa lỗi mount ổ đĩa trong file [docker-compose.yml](file:///d:/Works/openwebui_clone/docker-compose.yml), đảm bảo container `postgres` khởi động thành công.
- **Kiểm thử cục bộ**: Sửa lỗi kết nối database bị từ chối/không có mật khẩu khi chạy các bộ test cục bộ như [test_unified_identity.py](file:///d:/Works/openwebui_clone/llm-mw/test_unified_identity.py).
