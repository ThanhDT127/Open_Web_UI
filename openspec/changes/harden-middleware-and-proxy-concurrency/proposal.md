## Why

Trên cụm Production 16 GB RAM chạy đa worker (`open-webui: 2`, `middleware: 2`, `litellm: 2`) sau một IP WAN NAT văn phòng, còn 2 nhóm điểm nghẽn làm giảm độ ổn định khi nhiều nhân viên dùng đồng thời:

1. **Middleware (`llm-mw/`)**:
   - `config.py` mở cứng `maxconn=30` cho mỗi pool (`2 workers × 2 pools = 120` kết nối), chiếm 80% trần `max_connections=150` của PostgreSQL.
   - `api/docling.py` giải nén ZIP + nén ảnh WebP đồng bộ và `utils/logging.py` ghi file + `psycopg2` đồng bộ ngay trên `asyncio` event loop, gây khựng các luồng SSE chat đang chạy cùng worker.
   - `AsyncIOScheduler` trong `main.py` khởi chạy trên cả 2 worker khiến `send_daily_digest()` gửi trùng 2 email báo cáo lúc 8:00 sáng.
   - `RotatingFileHandler` dùng chung file log giữa 2 tiến trình không có khóa liên tiến trình, dễ lỗi khi xoay file hoặc ghi nhầm vào inode cũ sau khi xoay.
2. **Nginx & LiteLLM (`nginx/nginx.conf`, `litellm/litellm_config.yaml`)**:
   - `nginx.conf` giới hạn `/api/v1/auths/` ở mức `10r/m` (`burst=5`) cho cả `GET` kiểm tra phiên lẫn `POST` đăng nhập theo IP, dễ chặn nhầm văn phòng dùng chung 1 IP NAT, đồng thời thiếu `keepalive` cho `upstream`.
   - `litellm_config.yaml` khai báo lặp 2 lần khối `general_settings` và `logging`.

## What Changes

- **Co gọn DB Connection Pool (`llm-mw/config.py`, `llm-mw/core/db.py`)**: Đọc `DB_POOL_MIN` (mặc định `2`) và `DB_POOL_MAX` (mặc định `10`) từ biến môi trường, giảm tổng kết nối tối đa của 2 worker xuống `40/150`.
- **Tách tác vụ chặn khỏi Event Loop (`llm-mw/api/docling.py`, `llm-mw/utils/logging.py`)**: Đẩy giải nén ZIP + nén WebP + lưu ảnh sang `asyncio.to_thread` và đẩy ghi log file/DB sang `ThreadPoolExecutor` giới hạn luồng khi gọi từ ngữ cảnh bất đồng bộ.
- **Khóa Leader & Chống gửi trùng Cron 8h sáng (`llm-mw/core/notification.py`)**: Kết hợp `pg_try_advisory_lock` và trạng thái ngày gửi trong `mw_config` (`daily_digest_state`), đồng thời chạy phần tổng hợp/gửi SMTP trên threadpool.
- **Xoay Log Đa Tiến Trình An Toàn (`llm-mw/utils/file_lock_handler.py`, `llm-mw/config.py`, `llm-mw/api/user_admin.py`)**: Bổ sung `MultiProcessRotatingFileHandler` khóa file liên tiến trình và tự mở lại stream nếu tiến trình anh em vừa xoay file.
- **Cấu hình Nginx NAT Văn Phòng & Keepalive (`nginx/nginx.conf`)**: Chỉ áp rate-limit đăng nhập cho `POST` (`60r/m`, `burst=30`), trả mã `429`, nới ngưỡng `api`/`chat` cho IP NAT tập trung và bật `keepalive 32` cho `webui` cùng `mw_api`.
- **Khử trùng lặp khóa YAML (`litellm/litellm_config.yaml`)**: Gộp duy nhất một khối `general_settings` (`max_parallel_requests: 100`) và một khối `logging`.

## Capabilities

### New Capabilities
- `middleware-proxy-hardening`: Đảm bảo an toàn đa worker cho `llm-mw`, không chặn event loop khi xử lý tài liệu/ghi log, chống gửi trùng báo cáo ngày và tối ưu Nginx/LiteLLM cho môi trường IP NAT văn phòng.

## Impact

- `llm-mw/config.py`, `llm-mw/core/db.py`, `llm-mw/api/docling.py`, `llm-mw/utils/logging.py`, `llm-mw/core/notification.py`, `llm-mw/api/user_admin.py`, `llm-mw/utils/file_lock_handler.py`
- `nginx/nginx.conf`, `litellm/litellm_config.yaml`
- `tests/test_middleware_proxy_hardening.py`
