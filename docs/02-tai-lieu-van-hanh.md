# TÀI LIỆU VẬN HÀNH HỆ THỐNG AI NỘI BỘ (OPEN WEBUI STACK)

**Mã tài liệu:** DOC-02  
**Phiên bản:** 2.0  
**Ngày lập:** 06/03/2026 | **Cập nhật:** 27/03/2026  
**Đối tượng:** Quản trị viên hệ thống, Đội kỹ thuật  
**Phân loại:** NỘI BỘ - KỸ THUẬT

---

## MỤC LỤC

0. Thông tin tài liệu
1. Kiến trúc và sơ đồ thực tế
2. Cài đặt và triển khai
3. Quản lý Scheduled Tasks
4. Quản lý Database
5. Quản lý Logs
6. Quản lý người dùng
7. Monitoring và Health Check
8. Bảo mật
9. Troubleshooting
10. Maintenance
11. Scaling
12. Disaster Recovery
13. Source Code và Repository
14. Infrastructure / DevOps

---

## 0. THÔNG TIN TÀI LIỆU

### 0.1. Tổng quan hệ thống (System Overview)

Hệ thống AI nội bộ gồm **9 services** chạy trên Docker, quản lý bởi Nginx reverse proxy:

| STT | Service    | Container            | Port (nội bộ)  | Vai trò                                              |
| --- | ---------- | -------------------- | -------------- | ---------------------------------------------------- |
| 01  | **Nginx**  | openwebui-nginx      | **3000 HTTPS** | Reverse proxy, SSL, rate limiting (ĐẦU VÀO DUY NHẤT) |
| 02  | Open WebUI | openwebui-app        | 8080           | Giao diện chat, RAG, knowledge                       |
| 03  | Middleware | openwebui-middleware | 5000           | Auth, quota, cost, dashboard                         |
| 04  | LiteLLM    | openwebui-litellm    | 4000           | LLM proxy (OpenAI + Gemini + xAI + Anthropic)        |
| 05  | PostgreSQL | openwebui-postgres   | 5432           | Database + PGVector                                  |
| 06  | Docling    | openwebui-docling    | 5001           | OCR / Document extraction                            |
| 07  | SearXNG    | openwebui-searxng    | 8080           | Web search (internal only)                           |
| 08  | Redis      | openwebui-redis      | 6379           | Cache search + rate limiter                          |

### 0.2. Phạm vi và Deliverables

| STT | Phạm vi             | Chi tiết                                          |
| --- | ------------------- | ------------------------------------------------- |
| 01  | Hệ điều hành server | Windows Server 2019+ / Ubuntu 20.04+              |
| 02  | Docker              | Docker Engine 24.0+, Compose v2.20+               |
| 03  | Databases           | PostgreSQL 16 + PGVector 0.8.0 (2 databases)      |
| 04  | API Providers       | OpenAI, Google Gemini, xAI Grok, Anthropic Claude |
| 05  | Models              | 19 models (12 chat + 6 image + 1 embedding)       |
| 06  | Users               | 200+ concurrent                                   |

### 0.3. Danh mục tài sản (Asset List)

| STT | Tài sản        | Đường dẫn                   | Mô tả                       |
| --- | -------------- | --------------------------- | --------------------------- |
| 01  | Source code    | Oppen_Web_UI/               | Root project                |
| 02  | Middleware     | llm-mw/                     | Python FastAPI middleware   |
| 03  | Dashboard      | llm-mw/dashboard/           | HTML/CSS/JS SPA             |
| 04  | LiteLLM config | litellm/litellm_config.yaml | Model definitions           |
| 05  | Docker config  | docker-compose.yml          | Stack orchestration         |
| 06  | Environment    | .env                        | API keys, secrets           |
| 07  | Scripts        | scripts/                    | Management scripts          |
| 08  | Nginx config   | nginx/nginx.conf            | Reverse proxy routing, SSL  |
| 09  | SSL cert       | nginx/ssl/                  | fullchain.pem + privkey.pem |
| 10  | Documentation  | docs/                       | 17 tài liệu (01-17)         |

---

## 1. KIẾN TRÚC VÀ SƠ ĐỒ THỰC TẾ

### 1.1. Kiến trúc hệ thống

```
    ┌────────────────────────────────────────────────────────────────┐
    │                     NGƯỜI DÙNG (Browser)                       │
    │   https://openwebui.example.com:51122/                     │
    │   https://openwebui.example.com:51122/dashboard            │
    └───────────────────────────┬────────────────────────────────────┘
                                │
                    Firewall NAT: 51122 → 3000
                                │
    ╔═══════════════════════════╪════════════════════════════════════╗
    ║  Windows Server (20 CPU / 32GB RAM)                            ║
    ║  Docker Compose · 9 containers · openwebui-network             ║
    ║                               │                                ║
    ║  ┌────────────────────────────▼────────────────────────────┐   ║
    ║  │          NGINX (openwebui-nginx) :3000 HTTPS            │   ║
    ║  │          ← DUY NHẤT PORT MỞ RA NGOÀI →                  │   ║
    ║  │  SSL: wildcard *.example.com (TLS 1.2/1.3)          │   ║
    ║  │  Rate limit: 10 req/s (chat), 5 req/phút (login)        │   ║
    ║  │  Gzip: CSS, JS, JSON, SVG | Upload: max 100MB           │   ║
    ║  │                                                         │   ║
    ║  │  Routing (nginx.conf):                                  │   ║
    ║  │  /                → open-webui:8080  (chat UI)          │   ║
    ║  │  /_app/, /static/ → open-webui:8080  (JS/CSS assets)    │   ║
    ║  │  /ws/             → open-webui:8080  (WebSocket)        │   ║
    ║  │  /api/v1/auths/   → open-webui:8080  (login, 5req/m)    │   ║
    ║  │  /v1/             → middleware:5000  (LLM API proxy)    │   ║
    ║  │  /v1/_mw/         → middleware:5000  (admin API + SSE)  │   ║
    ║  │  /dashboard       → middleware:5000  (admin SPA)        │   ║
    ║  └──────┬─────────────────────────────────────┬────────────┘   ║
    ║         │                                     │                ║
    ║         ▼                                     ▼                ║
    ║  ┌──────────────────┐              ┌───────────────────────┐   ║
    ║  │  OPEN WEBUI      │              │  MIDDLEWARE           │   ║
    ║  │  :8080 (6 wrk)   │              │  :5000 (4 workers)    │   ║
    ║  │  CPU: 6 | 10GB   │              │  CPU: 4 | 2GB         │   ║
    ║  │                  │────────────▶│                       │   ║
    ║  │  Chat, RAG, KBs  │ LLM requests │  Auth (subkey HMAC)   │   ║
    ║  │  File upload     │ qua MW proxy │  Quota enforcement    │   ║
    ║  │  Admin Panel     │              │  Cost tracking        │   ║
    ║  │  User Auth (JWT) │              │  Dashboard SPA        │   ║
    ║  │                  │              │  Audit trail (SSE)    │   ║
    ║  └──┬─────────┬─────┘              └──────┬────────────────┘   ║
    ║     │         │                           │                    ║
    ║     │ DB      │ Web Search                │ Forward LLM        ║
    ║     │         │                           │                    ║
    ║     │         ▼                           ▼                    ║
    ║     │  ┌──────────────┐          ┌─────────────────────┐       ║
    ║     │  │  SEARXNG     │          │  LITELLM            │       ║
    ║     │  │  :8080       │          │  :4000 (4 workers)  │       ║
    ║     │  │  CPU: 1 | 1GB│          │  CPU: 4 | 4GB       ║       ║
    ║     │  │              │          │                     │       ║
    ║     │  │  DuckDuckGo  │          │  Model routing      │       ║
    ║     │  │  Brave       │          │  Retry  Fallback    │       ║
    ║     │  │  Bing        │          │  SSE streaming      │       ║
    ║     │  │  Google      │          │  19 models config   │       ║
    ║     │  └───────┬──────┘          └──────────┬──────────┘       ║
    ║     │          │ cache                      │                  ║
    ║     │          ▼                            │                  ║
    ║     │  ┌──────────────┐                     │                  ║
    ║     │  │  REDIS       │                     │                  ║
    ║     │  │  :6379       │                     │                  ║
    ║     │  │ CPU:0.5 256M │                     │                  ║
    ║     │  │  Search cache│                     │                  ║
    ║     │  └──────────────┘                     │                  ║
    ║     │                                       │                  ║
    ║     ▼                                       │                  ║
    ║  ┌──────────────────────┐                   │                  ║
    ║  │  POSTGRESQL          │                   │                  ║
    ║  │  :5432               │                   │                  ║
    ║  │  CPU: 2 | 8GB        │                   │                  ║
    ║  │  + PGVector 0.8.0    │                   │                  ║
    ║  │                      │                   │                  ║
    ║  │  DB: openwebui (26T) │                   │                  ║
    ║  │  DB: middleware (6T) │◄── MW ghi audit───┘                  ║
    ║  │                      │                                      ║
    ║  │  Tuning: shared=4GB  │                                      ║
    ║  │  max_conn=300        │                                      ║
    ║  └──────────────────────┘                                      ║
    ║                                                                ║
    ║  DOCLING (:5001) — OCR/Document extraction (PDF, DOCX, scan)   ║
    ║                                                                ║
    ║  Port mở: CHỈ Nginx :3000/tcp                                  ║
    ║  Port ĐÓNG: 8080, 5000, 5001, 4000, 5432, 6379                 ║
    ╚══════════════════════════════════════════════╪═════════════════╝
                                                   │
                                    LiteLLM gọi API ra ngoài
                                                   │
                           ┌───────────────┬───────────────┤──────────┐
                           │               │               │          │
                           ▼               ▼               ▼          ▼
                    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
                    │ OpenAI   │    │ Google   │    │ xAI      │    │ Anthropic│
                    │ GPT-5    │    │ Gemini   │    │ Grok-4   │    │ Claude4.6│
                    │ image    │    │ 2.5/3    │    │          │    │          │
                    │          │    │ Image    │    │          │    │          │
                    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### 1.1b. Luồng request chính

```
  Chat request:
  Browser ──HTTPS──▶ Nginx :3000 ──/v1/──▶ MW :5000 ──▶ LiteLLM :4000 ──▶ OpenAI/Gemini
                                   (auth+quota)          (route model)       (LLM API)

  Dashboard:
  Browser ──HTTPS──▶ Nginx :3000 ──/dashboard──▶ MW :5000 ──▶ index.html + SSE stream

  Web Search:
  Open WebUI ──▶ SearXNG :8080 ──▶ DuckDuckGo/Brave/Bing
                                        │
                                        ▼
                                   Redis :6379 (cache kết quả)

  Chat UI:
  Browser ──HTTPS──▶ Nginx :3000 ──/──▶ Open WebUI :8080

  Login:
  Browser ──HTTPS──▶ Nginx :3000 ──/api/v1/auths/──▶ Open WebUI :8080 (rate: 5req/phút)
```

### 1.2. Các thành phần chính

| # | Thành phần | Công nghệ          | Workers | CPU | RAM   | Image                                     |
| - | ---------- | ------------------ | ------- | --- | ----- | ----------------------------------------- |
| 0 | **Nginx**  | Nginx alpine       | auto    | 1   | 512MB | nginx:alpine                              |
| 1 | Open WebUI | Python + SvelteKit | 6       | 6   | 10GB  | Custom (Dockerfile.openwebui)             |
| 2 | Middleware | Python + FastAPI   | 4       | 4   | 2GB   | Custom (./llm-mw/Dockerfile)              |
| 3 | LiteLLM    | Python             | 4       | 4   | 4GB   | ghcr.io/berriai/litellm:main-latest       |
| 4 | PostgreSQL | C                  | —       | 2   | 8GB   | pgvector/pgvector:0.8.0-pg16              |
| 5 | Docling    | Python             | 1       | 2   | 2GB   | quay.io/docling-project/docling-serve-cpu |
| 6 | SearXNG    | Python             | —       | 1   | 1GB   | searxng/searxng:latest                    |
| 7 | Redis      | C                  | —       | 0.5 | 256MB | redis:7-alpine                            |

### 1.3. Phân chia modules trong Middleware

```
llm-mw/
  main.py                  # FastAPI app, đăng ký routes
  config.py                # Biến môi trường, hằng số
  requirements.txt         # Thư viện Python
  Dockerfile               # Build container
  core/
    auth.py                # Xác thực subkey, tra cứu user, HMAC-SHA256
    cost.py                # Tra cứu giá, tính chi phí, kiểm tra quota
    db.py                  # PostgreSQL pool, schema, CRUD
    alerting.py            # Cảnh báo quota, thông báo
    notification.py        # Daily digest scheduler, notification logic
    audit_state.py         # Per-request audit state tracking
  api/
    user_admin.py          # CRUD user, xoay khóa, xóa
    summary.py             # Tổng hợp metrics (v1)
    summary_v2.py          # Tổng hợp metrics (v2, dựa trên DB)
    stream.py              # SSE sự kiện real-time
    access_logs.py         # Nhật ký truy cập phân trang
    audit_query.py         # Truy vấn audit trail admin
    models.py              # Danh sách models
    quota_status.py        # Trạng thái quota user real-time
    notifications.py       # Hệ thống thông báo nội bộ
    auth_check.py          # Kiểm tra xác thực session
    auth_test.py           # Endpoint test auth (diagnostic)
    dashboard_login.py     # Đăng nhập/đăng xuất dashboard
    images.py              # Sinh ảnh (image generation)
    embeddings.py          # Tạo vector embeddings
    audio.py               # Chuyển đổi giọng nói → văn bản (STT)
    media.py               # Phục vụ file media
  services/                # Background services & schedulers
  dashboard/
    index.html             # Điểm vào SPA
    css/dashboard.css      # Giao diện
    js/
      main.js              # Điều phối ứng dụng
      charts.js            # Biểu đồ Chart.js
      filters.js           # Bộ lọc ngày/user/model
      logs.js              # Bảng log và phân trang
      usage.js             # Metrics sử dụng
      users.js             # Giao diện CRUD user
  data/
    users.json             # Bản sao lưu user (nguồn: DB)
    prices.json            # Bản sao lưu giá (nguồn: DB)
    alert_config.json      # Cấu hình cảnh báo quota
    system_alerts.json     # Trạng thái cảnh báo hệ thống
```

---

## 2. CÀI ĐẶT VÀ TRIỂN KHAI

### 2.1. Yêu cầu hệ thống

| STT | Tài nguyên | Tối thiểu    | Hiện tại (Production)               |
| --- | ---------- | ------------ | ----------------------------------- |
| 01  | RAM        | 16 GB        | **32 GB** (25.8GB allocated)        |
| 02  | CPU        | 8 cores      | **20 cores** (18.5 allocated)       |
| 03  | Storage    | 50 GB free   | 100 GB+ (DB + uploads)              |
| 04  | Docker     | Engine 24.0+ | Latest                              |
| 05  | Compose    | v2.20+       | Latest                              |
| 06  | Network    | LAN access   | **Firewall + NAT + HTTPS**          |
| 07  | SSL        | —            | **Wildcard cert *.example.com** |

### 2.2. Cài đặt dependencies

```
# 1. Cài Docker Desktop (Windows)
# Tải từ https://docker.com/products/docker-desktop

# 2. Clone repository
git clone https://github.com/ThanhDT127/Oppen_Web_UI.git
cd Oppen_Web_UI
git checkout dashboard

# 3. Xác nhận Docker
docker --version        # >= 24.0
docker compose version  # >= 2.20
```

### 2.3. Cấu hình môi trường

Tạo file .env từ template:

```
cp .env.example .env
```

#### Biến môi trường bắt buộc

```
# API Keys (BẮT BUỘC)
OPENAI_API_KEY=sk-proj-...
GEMINI_API_KEY=AIzaSy...

# LiteLLM
LITELLM_KEY=sk-litellm-master-key-change-me

# Bảo mật Middleware
MW_SECRET=random_32_char_string_for_subkey_hashing
JWT_SECRET=another_random_string_for_jwt_signing
ADMIN_KEY=YOUR_ADMIN_KEY

# PostgreSQL
POSTGRES_USER=openwebui_user
POSTGRES_PASSWORD=your_secure_password_min_16_chars
POSTGRES_DB=openwebui

# Open WebUI
WEBUI_SECRET_KEY=webui_secret_min_32_chars
```

#### Mô tả từng biến

| STT | Biến              | Vai trò                                | Sử dụng bởi |
| --- | ----------------- | -------------------------------------- | ----------- |
| 01  | OPENAI_API_KEY    | Xác thực OpenAI API (GPT, DALL-E, TTS) | LiteLLM     |
| 02  | GEMINI_API_KEY    | Xác thực Google Gemini API             | LiteLLM     |
| 03  | LITELLM_KEY       | Master key cho LiteLLM admin API       | LiteLLM     |
| 04  | MW_SECRET         | Salt cho HMAC-SHA256 hash subkey       | Middleware  |
| 05  | JWT_SECRET        | Secret cho JWT token signing           | Middleware  |
| 06  | ADMIN_KEY         | Key đăng nhập Dashboard admin          | Middleware  |
| 07  | POSTGRES_PASSWORD | Mật khẩu PostgreSQL                    | PostgreSQL  |
| 08  | WEBUI_SECRET_KEY  | Secret cho Open WebUI sessions         | Open WebUI  |

### 2.4. Khởi động hệ thống

```
# Khởi động toàn bộ
docker compose up -d

# Kiểm tra trạng thái
docker compose ps

# Xem logs (theo dõi)
docker compose logs -f

# Chỉ khởi động middleware
docker compose up -d middleware

# Restart hệ thống
docker compose restart

# Dừng hệ thống (giữ data)
docker compose down

# Dừng + xóa volumes (MẤT DỮ LIỆU)
docker compose down -v
```

### 2.5. Cập nhật code mới

```
# 1. Pull code mới
git pull origin dashboard

# 2. Rebuild containers (nếu có thay đổi Dockerfile)
docker compose build --no-cache middleware

# 3. Restart
docker compose up -d

# 4. Xác nhận
docker compose ps
curl -k https://localhost:3000/
```

---

## 3. QUẢN LÝ SCHEDULED TASKS

### 3.1. Reconcile Scheduler

Mục đích: Đồng bộ pending requests với LiteLLM logs (tính cost chính xác cho streaming).

- Tần suất: Tự động, triggered sau mỗi streaming response
- Endpoint: POST /admin/reconcile
- Phương thức: Đọc LiteLLM logs > match rid > cập nhật tokens/cost

### 3.2. Quota Reset

Mục đích: Reset used_tokens, used_cost_usd về 0 theo chu kỳ.

- Tần suất: Monthly (đầu mỗi tháng) hoặc Weekly
- Logic: Kiểm tra mw_users.quota.period > reset nếu đến kỳ
- Config: Từng user cấu hình period riêng (monthly/weekly)

### 3.3. Alert Scheduler

Mục đích: Gửi cảnh báo khi user gần hết quota.

- Tần suất: Mỗi 5 phút kiểm tra
- Ngưỡng: 80% quota > warning, 95% > critical
- Hành động: Log cảnh báo, có thể webhook notification

### 3.4. Quản lý Scheduler

```
# Xem logs scheduler
docker compose logs middleware | findstr "scheduler"

# Reconcile thủ công
curl -X POST http://localhost:5000/admin/reconcile -H "X-Admin-Key: YOUR_ADMIN_KEY"

# Reset quota thủ công cho 1 user
curl -X POST http://localhost:5000/admin/reset -H "X-Admin-Key: YOUR_ADMIN_KEY" -H "Content-Type: application/json" -d "{\"user_id\": \"user1\"}"
```

---

## 4. QUẢN LÝ DATABASE

### 4.1. PostgreSQL - 2 Databases

#### Database openwebui - 26 bảng

| STT | Nhóm      | Bảng chính                      | Mục đích               |
| --- | --------- | ------------------------------- | ---------------------- |
| 01  | User      | user, auth                      | Tài khoản, credentials |
| 02  | Chat      | chat, message, channel          | Hội thoại              |
| 03  | Knowledge | knowledge, file, knowledge_file | Tài liệu               |
| 04  | RAG       | document, document_chunk        | Vector embeddings      |
| 05  | Config    | config, feedback, tag           | Cấu hình               |

#### Database middleware - 6 bảng

| STT | Bảng           | Columns                                   | Mục đích         |
| --- | -------------- | ----------------------------------------- | ---------------- |
| 01  | mw_users       | user_id, subkey_hash, role, active, quota | Quản lý user API |
| 02  | mw_prices      | model, input_per_1m, output_per_1m        | Bảng giá         |
| 03  | mw_config      | key, value                                | Config runtime   |
| 04  | mw_pending     | rid, user_id, model                       | Pending requests |
| 05  | mw_audit_log   | ts, user_id, model, status, cost          | Audit log        |
| 06  | mw_request_log | ts, method, path, status_code, latency    | HTTP access log  |

### 4.2. Kết nối Database

```
# Kết nối trực tiếp
docker exec -it openwebui-postgres psql -U openwebui_user -d openwebui

# Kiểm tra database middleware
docker exec -it openwebui-postgres psql -U openwebui_user -d middleware

# Connection string (trong docker network)
# postgresql://openwebui_user:<password>@postgres:5432/openwebui
# postgresql://openwebui_user:<password>@postgres:5432/middleware
```

### 4.3. Monitoring Database

```sql
-- Xem kích thước database
SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname))
FROM pg_database ORDER BY pg_database_size(pg_database.datname) DESC;

-- Xem kích thước từng bảng
SELECT tablename, pg_size_pretty(pg_total_relation_size(tablename::regclass))
FROM pg_tables WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(tablename::regclass) DESC;

-- Đếm records trong middleware tables
SELECT 'mw_users' as tbl, COUNT(*) FROM mw_users
UNION ALL SELECT 'mw_audit_log', COUNT(*) FROM mw_audit_log
UNION ALL SELECT 'mw_pending', COUNT(*) FROM mw_pending
UNION ALL SELECT 'mw_request_log', COUNT(*) FROM mw_request_log;

-- Xem index usage
SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes ORDER BY idx_scan DESC;
```

### 4.4. Bảo trì Database

```sql
-- VACUUM (dọn dẹp dead tuples)
VACUUM ANALYZE mw_audit_log;
VACUUM ANALYZE mw_request_log;

-- REINDEX (rebuild index)
REINDEX TABLE mw_audit_log;

-- Giữ lại dữ liệu: xóa log cũ hơn 90 ngày
DELETE FROM mw_audit_log WHERE ts < NOW() - INTERVAL '90 days';
DELETE FROM mw_request_log WHERE ts < NOW() - INTERVAL '90 days';
```

---

## 5. QUẢN LÝ LOGS

### 5.1. Cấu trúc log

| STT | File log       | Vị trí                 | Định dạng     | Rotation            |
| --- | -------------- | ---------------------- | ------------- | ------------------- |
| 01  | Audit log      | DB mw_audit_log        | JSONB payload | 90 ngày retention   |
| 02  | Request log    | DB mw_request_log      | JSONB         | 90 ngày retention   |
| 03  | Admin audit    | logs/admin_audit.jsonl | JSONL         | 20MB max, 5 bản sao |
| 04  | Container logs | Docker stdout          | Text          | Docker log driver   |

### 5.2. API quản lý logs

```
# Xem audit trail (24h gần nhất)
curl "http://localhost:5000/v1/_mw/admin/audit?minutes=1440" -H "X-Admin-Key: YOUR_ADMIN_KEY"

# Xem access logs (phân trang)
curl "http://localhost:5000/v1/_mw/access_summary?minutes=1440" -H "X-Admin-Key: YOUR_ADMIN_KEY"

# Xem summary metrics
curl "http://localhost:5000/v1/_mw/summary?minutes=60" -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

### 5.3. Giám sát logs

```
# Xem logs container real-time
docker compose logs -f middleware --tail 100
docker compose logs -f litellm --tail 100

# Tìm lỗi trong logs
docker compose logs middleware 2>&1 | findstr "ERROR"
docker compose logs middleware 2>&1 | findstr "500"

# Xuất logs
docker compose logs middleware > middleware_logs.txt 2>&1
```

### 5.4. Tìm kiếm trong DB logs

```sql
-- Tìm requests lỗi
SELECT ts, user_id, model, status, payload->>'error' as error
FROM mw_audit_log WHERE status = 'error'
ORDER BY ts DESC LIMIT 20;

-- Tìm requests của 1 user
SELECT ts, model, status, tokens_total, cost_usd
FROM mw_audit_log WHERE user_id = 'admin'
ORDER BY ts DESC LIMIT 50;

-- Thống kê request theo model (24h)
SELECT model, COUNT(*) as calls, SUM(cost_usd) as total_cost
FROM mw_audit_log
WHERE ts > NOW() - INTERVAL '24 hours' AND status IN ('ok','reconciled')
GROUP BY model ORDER BY total_cost DESC;
```

---

## 6. QUẢN LÝ NGƯỜI DÙNG

### 6.1. Hai hệ thống user

| STT | Hệ thống   | Database            | Mục đích                | Quản lý qua                              |
| --- | ---------- | ------------------- | ----------------------- | ---------------------------------------- |
| 01  | Open WebUI | openwebui.user      | Đăng nhập web, chat     | Admin Panel (https://....:51122/)        |
| 02  | Middleware | middleware.mw_users | Auth API, quota, subkey | Dashboard (https://....:51122/dashboard) |

Lưu ý: Hai hệ thống độc lập - cần tạo user ở CẢ HAI nơi.

### 6.2. CRUD qua Dashboard

Truy cập: `https://openwebui.example.com:51122/dashboard` > Tab Users

| STT | Thao tác  | Hướng dẫn                                                           |
| --- | --------- | ------------------------------------------------------------------- |
| 01  | Tạo user  | Add User > Điền user_id, role, quota, models > Create > Copy subkey |
| 02  | Sửa user  | Edit > Sửa trường cần > Save                                        |
| 03  | Xóa user  | Delete > Xác nhận 2 lần (vĩnh viễn)                                 |
| 04  | Xoay khóa | Rotate > Xác nhận > Copy subkey mới                                 |
| 05  | Bật/Tắt   | Toggle > disabled user bị 403                                       |

### 6.3. CRUD qua API

```
# Tạo user
curl -X POST http://localhost:5000/v1/_mw/admin/users \
  -H "X-Admin-Key: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"alice\",\"role\":\"user\",\"limit_cost_usd\":5.0,\"allowed_models\":[\"*\"]}"

# Sửa user
curl -X PATCH http://localhost:5000/v1/_mw/admin/users/alice \
  -H "X-Admin-Key: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"limit_cost_usd\":10.0,\"active\":true}"

# Xóa user
curl -X DELETE http://localhost:5000/v1/_mw/admin/users/alice \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"

# Xoay khóa
curl -X POST http://localhost:5000/v1/_mw/admin/users/alice/rotate_key \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"

# Tắt user
curl -X POST http://localhost:5000/v1/_mw/admin/users/alice/disable \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"

# Bật user
curl -X POST http://localhost:5000/v1/_mw/admin/users/alice/enable \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"

# Danh sách tất cả users
curl http://localhost:5000/v1/_mw/admin/users \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"

# Đăng nhập Dashboard (lấy JWT cookie)
curl -X POST http://localhost:5000/v1/_mw/dashboard/login \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d "{\"username\":\"admin\",\"password\":\"YOUR_ADMIN_KEY\"}"

# Đăng xuất Dashboard
curl -X POST http://localhost:5000/v1/_mw/dashboard/logout \
  -b cookies.txt
```

### 6.4. Phân quyền (RBAC)

| STT | Role    | Middleware API | Dashboard   | Admin Panel (WebUI) |
| --- | ------- | -------------- | ----------- | ------------------- |
| 01  | admin   | Full CRUD      | Full access | Full admin          |
| 02  | manager | API access     | Read-only   | -                   |
| 03  | user    | API (giới hạn) | Không có    | Standard user       |
| 04  | pending | Không có       | Không có    | Chờ duyệt           |

---

## 7. MONITORING VÀ HEALTH CHECK

### 7.1. Health Check API

```
# Nginx health (đầu vào chính)
curl -k https://localhost:3000/
# Kỳ vọng: HTML page Open WebUI

# Nginx config test
docker exec openwebui-nginx nginx -t
# Kỳ vọng: syntax is ok, test is successful

# Middleware health (qua Nginx)
curl -k https://localhost:3000/v1/_mw/health
# Hoặc nội bộ: docker exec openwebui-middleware curl http://localhost:5000/health
# Kỳ vọng: {"ok":true, "litellm":"ok", "database":"ok", ...}

# SearXNG health
docker inspect --format='{{.State.Health.Status}}' openwebui-searxng
# Kỳ vọng: healthy

# PostgreSQL
docker exec openwebui-postgres pg_isready -U openwebui_user -d openwebui
# Kỳ vọng: accepting connections
```

### 7.2. Dashboard Metrics (7 Cards)

| STT | Card         | Mô tả                            | Cảnh báo          |
| --- | ------------ | -------------------------------- | ----------------- |
| 01  | LLM Calls    | Tổng requests (chat+image+audio) | -                 |
| 02  | Admin Ops    | Thao tác admin                   | -                 |
| 03  | Pending      | Requests chưa hoàn thành         | >10: kiểm tra     |
| 04  | Error Rate   | % lỗi                            | >5%: điều tra     |
| 05  | P95 Latency  | 95th percentile ms               | >5000ms: kiểm tra |
| 06  | Total Tokens | Tokens đã xử lý                  | -                 |
| 07  | Total Cost   | Chi phí USD                      | Theo budget       |

### 7.3. SSE Real-time Stream

Dashboard tự động kết nối SSE endpoint /v1/_mw/stream.
Events: audit (mỗi request mới). Auto-reconnect: 5 giây.

### 7.4. Cảnh báo

| STT | Ngưỡng       | Mức      | Hành động                    |
| --- | ------------ | -------- | ---------------------------- |
| 01  | Quota 80%    | WARNING  | Log cảnh báo                 |
| 02  | Quota 95%    | CRITICAL | Log cảnh báo                 |
| 03  | Quota 100%   | BLOCKED  | 403 Forbidden (tự động chặn) |
| 04  | Error > 5%   | WARNING  | Cần điều tra                 |
| 05  | Pending > 10 | WARNING  | Cần kiểm tra LiteLLM         |

---

## 8. BẢO MẬT

### 8.1. Xác thực và Phân quyền

| STT | Thành phần     | Phương thức            | Secret                 |
| --- | -------------- | ---------------------- | ---------------------- |
| 01  | Open WebUI     | Email/Password + JWT   | WEBUI_SECRET_KEY       |
| 02  | Middleware API | Subkey HMAC-SHA256     | MW_SECRET              |
| 03  | Dashboard      | Admin key + JWT cookie | ADMIN_KEY + JWT_SECRET |
| 04  | LiteLLM        | Master key             | LITELLM_KEY            |

### 8.2. Bảo mật Mạng (Docker)

Docker Compose sử dụng bridge network nội bộ. Các services gọi nhau bằng container name.
LiteLLM (4000) và PostgreSQL (5432) KHÔNG bắt buộc expose ra ngoài.

Firewall rules cần thiết: Chỉ mở 1 port ra ngoài:
- Port 3000: Nginx HTTPS (reverse proxy đến Open WebUI + Middleware)
- Port 5000: **ĐÓNG** — truy cập qua Nginx tại /v1/_mw/ và /dashboard

### 8.3. Bảo mật Dữ liệu

| STT | Dữ liệu          | Bảo vệ                      | Chi tiết                                                                   |
| --- | ---------------- | --------------------------- | -------------------------------------------------------------------------- |
| 01  | Subkey           | HMAC-SHA256 (one-way hash)  | Plaintext chỉ hiện 1 lần                                                   |
| 02  | JWT token        | HMAC-SHA256 signature       | 4h expiry, HttpOnly cookie                                                 |
| 03  | Password (WebUI) | Bcrypt hash                 | Salt + rounds                                                              |
| 04  | Database         | Docker volume               | Không cloud, on-premise                                                    |
| 05  | RAG embedding    | Gemini API (qua Middleware) | Text chunks gửi tới Google Gemini API để embedding. Vectors lưu on-premise |
| 06  | Nội dung chat    | Gửi qua API                 | Gửi tới OpenAI/Google/xAI/Anthropic để xử lý                               |

### 8.4. Thực hành Bảo mật Tốt nhất

1. Xoay subkey mỗi 90 ngày hoặc khi nghi ngờ lộ
2. Đổi ADMIN_KEY sau khi deploy lần đầu
3. Không chia sẻ file .env - thêm vào .gitignore
4. Backup database định kỳ (ít nhất hàng tuần)
5. Giám sát audit logs cho hoạt động bất thường
6. Tắt đăng ký tự do khi không cần: ENABLE_SIGNUP=false

---

## 9. TROUBLESHOOTING

### 9.1. Các Vấn đề Thường gặp

| #  | Lỗi                        | Nguyên nhân                    | Giải pháp                                    |
| -- | -------------------------- | ------------------------------ | -------------------------------------------- |
| 1  | Container không start      | Port đã bị chiếm               | Kiểm tra port, kill process                  |
| 2  | 401 Missing sub-key        | Thiếu Authorization header     | Thêm Bearer <subkey>                         |
| 3  | 403 Invalid sub-key        | Subkey sai hoặc user disabled  | Xoay khóa hoặc bật user                      |
| 4  | 403 Quota exceeded         | Hết quota                      | Reset quota hoặc tăng limit                  |
| 5  | 502 LiteLLM unavailable    | LiteLLM container down         | docker compose restart litellm               |
| 6  | Dashboard trắng            | Session hết hạn                | Reload, nhập lại admin key                   |
| 7  | RAG không tìm thấy         | File chưa index xong           | Chờ indexing, kiểm tra document_chunk        |
| 8  | Image gen lỗi              | API key sai hoặc model sai     | Kiểm tra .env và litellm_config.yaml         |
| 9  | Web search không hoạt động | SearXNG unhealthy / config sai | Kiểm tra docker logs openwebui-searxng       |
| 10 | Model không tự search      | FC không set Native            | Model > Advanced > Function Calling = Native |

### 9.2. Lệnh Debug

```
# Kiểm tra containers
docker compose ps

# Kiểm tra ports
netstat -ano | findstr ":3000 :4000 :5000 :5432"

# Kiểm tra logs (chỉ lỗi)
docker compose logs middleware 2>&1 | findstr "ERROR CRITICAL"

# Kiểm tra kết nối database
docker exec openwebui-postgres pg_isready -U openwebui_user

# Kiểm tra dung lượng ổ đĩa
docker system df

# Kiểm tra sử dụng tài nguyên
docker stats --no-stream

# Test middleware health
curl http://localhost:5000/health

# Test LiteLLM
curl http://localhost:4000/health
```

---

## 10. BẢO TRÌ

### 10.1. Thao tác Hàng ngày

| STT | Thao tác            | Lệnh / Hành động                 |
| --- | ------------------- | -------------------------------- |
| 01  | Duyệt user pending  | Admin Panel > Users > Approve    |
| 02  | Kiểm tra chi phí    | Dashboard > Overview tab         |
| 03  | Kiểm tra error rate | Dashboard > Error Rate card < 5% |

### 10.2. Thao tác Hàng tuần

| STT | Thao tác                | Lệnh / Hành động              |
| --- | ----------------------- | ----------------------------- |
| 01  | Review chi phí per user | Dashboard > Filter by user    |
| 02  | Backup database         | pg_dump command (xem phần 12) |
| 03  | Kiểm tra dung lượng     | docker system df              |
| 04  | Kiểm tra container      | docker compose ps - tất cả Up |
| 05  | Review audit logs       | Dashboard > Logs tab          |

### 10.3. Thao tác Hàng tháng

| STT | Thao tác               | Lệnh / Hành động                     |
| --- | ---------------------- | ------------------------------------ |
| 01  | Cập nhật Docker images | docker compose pull && up -d         |
| 02  | Vacuum database        | VACUUM ANALYZE (xem phần 4.4)        |
| 03  | Review quotas          | Điều chỉnh theo mức sử dụng thực tế  |
| 04  | Xoay admin key         | Đổi ADMIN_KEY trong .env > restart   |
| 05  | Dọn log cũ             | Xóa mw_audit_log > 90 ngày           |
| 06  | Review bảo mật         | Kiểm tra .env, firewall, user access |

---

## 11. MỞ RỘNG (SCALING)

### 11.1. Mở rộng Ngang (Horizontal)

```
# Scale middleware replicas
docker compose up -d --scale middleware=3

# Cần load balancer (nginx/traefik) phía trước
```

Lưu ý: Middleware stateless (DB-backed) - mở rộng ngang dễ dàng.

### 11.2. Mở rộng Dọc (Vertical)

Tăng tài nguyên trong docker-compose.yml:

| STT | Service    | Tham số        | Giá trị khuyến nghị |
| --- | ---------- | -------------- | ------------------- |
| 01  | middleware | memory limit   | 2G                  |
| 02  | middleware | cpus limit     | 2.0                 |
| 03  | postgres   | memory limit   | 4G                  |
| 04  | postgres   | cpus limit     | 4.0                 |
| 05  | postgres   | shared_buffers | 1GB                 |
| 06  | postgres   | work_mem       | 16MB                |

---

## 12. KHÔI PHỤC SAU SỰ CỐ (DISASTER RECOVERY)

### 12.1. RTO / RPO

| STT | Metric | Mục tiêu  | Giải pháp                |
| --- | ------ | --------- | ------------------------ |
| 01  | RTO    | < 30 phút | Docker rebuild từ backup |
| 02  | RPO    | < 24 giờ  | Daily database backup    |

### 12.2. Chiến lược Backup

```
# === SCRIPT BACKUP HÀNG NGÀY ===

# 1. Backup databases
docker exec openwebui-postgres pg_dump -U openwebui_user -d openwebui > backup\openwebui_%date%.sql
docker exec openwebui-postgres pg_dump -U openwebui_user -d middleware > backup\middleware_%date%.sql

# 2. Backup .env và config
copy .env backup\.env_backup
copy litellm\litellm_config.yaml backup\litellm_config_backup.yaml

# 3. Dọn backup cũ (> 30 ngày)
forfiles /P backup /D -30 /C "cmd /c del @file"
```

### 12.3. Các bước Khôi phục

```
# === QUY TRÌNH KHÔI PHỤC SAU SỰ CỐ ===

# Bước 1: Đảm bảo Docker đang chạy
docker --version

# Bước 2: Clone repository (nếu mất code)
git clone https://github.com/ThanhDT127/Oppen_Web_UI.git
cd Oppen_Web_UI
git checkout dashboard

# Bước 3: Khôi phục .env
copy backup\.env_backup .env

# Bước 4: Khởi động stack
docker compose up -d

# Bước 5: Chờ PostgreSQL sẵn sàng (30 giây)
timeout /t 30
docker exec openwebui-postgres pg_isready -U openwebui_user

# Bước 6: Khôi phục databases
type backup\openwebui_latest.sql | docker exec -i openwebui-postgres psql -U openwebui_user -d openwebui
type backup\middleware_latest.sql | docker exec -i openwebui-postgres psql -U openwebui_user -d middleware

# Bước 7: Xác nhận
curl http://localhost:5000/health
curl http://localhost:3000/api/health
```

---

## 13. SOURCE CODE VÀ REPOSITORY

### 13.1. Cấu trúc thư mục

```
Oppen_Web_UI/
  docker-compose.yml          # Stack orchestration
  .env                        # Environment secrets (KHÔNG trong git)
  .env.example                # Template
  .gitignore                  # Git ignore rules
  llm-mw/                     # Middleware source
    Dockerfile                # Build container
    main.py                   # Ứng dụng FastAPI
    config.py                 # Cấu hình môi trường
    requirements.txt          # Thư viện Python
    core/                     # Modules lõi
    api/                      # API endpoints
    dashboard/                # Frontend SPA
    data/                     # Bản sao lưu JSON
  litellm/                    # Cấu hình LiteLLM
    litellm_config.yaml       # 20 định nghĩa model
  scripts/                    # Scripts quản lý
    init_pgvector.sql         # Khởi tạo DB
  docs/                       # Tài liệu (12 files)
    01-tong-quan-he-thong.md
    02-tai-lieu-van-hanh.md
    ...
  function tool/              # Custom tools (export)
    tool_export_all.py        # Export Excel/PDF/Word
```

### 13.2. Git Workflow

```
Branches:
  main                        # Production-ready
  dashboard                   # Phát triển mới nhất (User CRUD, docs)
  image                       # Tính năng tạo ảnh
  docker-deployment-with-tests # Triển khai Docker
```

```
# Checkout nhánh phát triển
git checkout dashboard

# Tạo feature branch
git checkout -b feature/my-feature

# Commit thay đổi
git add .
git commit -m "feat: mô tả thay đổi"

# Push
git push -u origin feature/my-feature
```

---

## 14. INFRASTRUCTURE / DEVOPS

### 14.1. Cấu hình Docker

| STT | Service    | Image                               | Healthcheck        | Restart        |
| --- | ---------- | ----------------------------------- | ------------------ | -------------- |
| 01  | postgres   | pgvector/pgvector:0.8.0-pg16        | pg_isready mỗi 10s | unless-stopped |
| 02  | litellm    | ghcr.io/berriai/litellm:main-latest | -                  | unless-stopped |
| 03  | middleware | ./llm-mw (custom build)             | -                  | unless-stopped |
| 04  | open-webui | ghcr.io/open-webui/open-webui:v0.9.5 | -                  | unless-stopped |

### 14.4. Upgrade Notes for Open WebUI v0.9.5

- Open WebUI `v0.9.x` co database migrations. Backup DB truoc khi nang cap.
- Khong thuc hien rolling update cho Open WebUI khi nang cap `v0.9.x`.
- Sau nang cap, can test lai:
  - login/logout
  - chat streaming
  - RAG upload/query
  - SearXNG web search
  - custom tools/functions/filters
  - persisted chats, attachments, file preview
  - dashboard analytics / token accounting

### 14.2. Volumes và Persistence

| STT | Volume         | Mounted to               | Dữ liệu                         |
| --- | -------------- | ------------------------ | ------------------------------- |
| 01  | postgres_data  | /var/lib/postgresql/data | Tất cả databases, tables, index |
| 02  | litellm_logs   | /app/logs                | LiteLLM request logs            |
| 03  | openwebui_data | /app/backend/data        | Files upload, user avatars      |

```
# Liệt kê volumes
docker volume ls | findstr "oppen"

# Xem chi tiết volume
docker volume inspect oppen_web_ui_postgres_data

# Backup volume
docker run --rm -v oppen_web_ui_postgres_data:/data -v %cd%:/backup alpine tar czf /backup/postgres_data.tar.gz /data
```

### 14.3. Monitoring và Logging Stack

Hiện tại:
- Docker logs (stdout/stderr)
- Middleware audit log (DB mw_audit_log)
- Admin audit file (logs/admin_audit.jsonl)
- Dashboard UI (metrics real-time)
- SSE stream (sự kiện real-time)

Khuyến nghị bổ sung:
- Prometheus + Grafana (trực quan hóa metrics)
- Loki (tập trung log)
- Alertmanager (cảnh báo email/Slack)
- cAdvisor (giám sát tài nguyên container)

---

