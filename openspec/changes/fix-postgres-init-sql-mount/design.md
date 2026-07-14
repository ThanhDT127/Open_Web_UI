## Context

Trong các commit trước, file khởi tạo database và extension pgvector `scripts/init_pgvector.sql` đã được chuyển vào thư mục con `scripts/sql/init_pgvector.sql`. Tuy nhiên, cấu hình volume mount cho container `postgres` trong file [docker-compose.yml](file:///d:/Works/openwebui_clone/docker-compose.yml) vẫn tham chiếu tới đường dẫn cũ `./scripts/init_pgvector.sql`.

Khi chạy lệnh khởi động `docker compose up`, Docker Daemon tìm kiếm file này trên host nhưng không thấy, nên tự động tạo một thư mục trống trùng tên `./scripts/init_pgvector.sql` trên máy host và mount vào đường dẫn file `/docker-entrypoint-initdb.d/init.sql:ro` trong container. Lỗi này làm container `postgres` sụp đổ khi khởi tạo (runc mount error), kéo theo sự ngừng hoạt động của toàn bộ stack dịch vụ và làm các bộ test tích hợp cục bộ thất bại do mất kết nối DB.

## Goals / Non-Goals

**Goals:**
- Khắc phục lỗi cấu hình đường dẫn volume mount trong file [docker-compose.yml](file:///d:/Works/openwebui_clone/docker-compose.yml) bằng cách trỏ đúng vào file `./scripts/sql/init_pgvector.sql`.
- Xóa bỏ thư mục trống lỗi `./scripts/init_pgvector.sql` tự phát sinh trên máy host để trả lại trạng thái sạch.
- Đảm bảo stack Docker Compose chạy kiểm thử Postgres và Middleware hoạt động ổn định và các unit test cục bộ vượt qua thành công.

**Non-Goals:**
- Không thay đổi mã nguồn logic nghiệp vụ của Middleware hoặc Open WebUI.
- Không thay đổi hay định nghĩa lại cấu trúc bảng dữ liệu của Postgres.

## Decisions

### Quyết định 1: Cập nhật trực tiếp đường dẫn mount trong docker-compose.yml
- **Giải pháp**: Thay đổi giá trị mount từ `./scripts/init_pgvector.sql` thành `./scripts/sql/init_pgvector.sql`.
- **Lý do**: Đây là đường dẫn thực tế của file khởi tạo SQL sau khi cấu trúc lại thư mục.

### Quyết định 2: Xóa thủ công thư mục lỗi trên host trước khi start lại container
- **Giải pháp**: Phải xóa thư mục trống `./scripts/init_pgvector.sql` trên máy host.
- **Lý do**: Nếu không xóa thư mục trống này, Docker vẫn sẽ tiếp tục cố gắng mount nó dưới dạng thư mục vào container và tiếp tục báo lỗi.

## Risks / Trade-offs

- **[Risk] Docker daemon lưu cache mount cũ hoặc lỗi không chịu nhả file** → *Mitigation*: Thực hiện dừng hẳn stack bằng `docker compose down`, xóa thư mục lỗi trên host, sau đó mới chạy `docker compose up -d postgres`.
