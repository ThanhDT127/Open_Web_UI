# 🎯 Open WebUI Stack — Nền tảng AI Nội bộ

> **"ChatGPT nội bộ"** cho doanh nghiệp — kiểm soát chi phí, bảo mật dữ liệu, quản trị tập trung.

[![Stack](https://img.shields.io/badge/Stack-Docker_Compose-blue)](docs/03-architecture.md)
[![Services](https://img.shields.io/badge/Services-8_containers-green)](docker-compose.yml)
[![Models](https://img.shields.io/badge/AI_Models-20-purple)](litellm/litellm_config.yaml)
[![Docs](https://img.shields.io/badge/Docs-17_tài_liệu-orange)](docs/)

---

## 📋 Mục lục

- [Tổng quan](#-tổng-quan)
- [Truy cập hệ thống](#-truy-cập-hệ-thống)
- [Kiến trúc](#-kiến-trúc)
- [Tài liệu](#-tài-liệu)
- [Vận hành](#-vận-hành)
- [Phát triển](#-phát-triển)

---

## 🎯 Tổng quan

| Tiêu chí | Chi tiết |
|----------|----------|
| **Mục đích** | Nền tảng AI tập trung: chat, tạo ảnh, RAG, web search |
| **Quy mô** | 200+ nhân viên, đa phòng ban |
| **Hạ tầng** | Windows Server, 20 CPU / 32GB RAM |
| **Triển khai** | Docker Compose, 8 containers |
| **Providers** | OpenAI, Google Gemini, xAI, Anthropic (20 models) |
| **Bảo mật** | HTTPS, HMAC-SHA256 subkey, JWT, rate limiting |

### Tính năng chính

| Module | Số tính năng | Mô tả |
|--------|:---:|--------|
| Chat AI | 18 | 14 models, streaming, markdown, code highlight |
| Knowledge / RAG | 15 | Upload PDF/Word/Excel, hybrid search, citations |
| Web Search | 6 | SearXNG tự host, Native Function Calling |
| Image Generation | 6 | DALL-E 3, Gemini Image, cost tracking |
| Middleware Proxy | 20 | Auth, quota, cost, routing, audit |
| Dashboard Admin | 15 | 7 KPIs, charts, user CRUD, SSE real-time |
| **Tổng cộng** | **109** | |

---

## 🔗 Truy cập hệ thống

| Dịch vụ | URL | Đối tượng |
|---------|-----|-----------|
| Chat AI | `https://openwebui.example.com:51122/` | Tất cả users |
| Dashboard Admin | `https://openwebui.example.com:51122/dashboard` | Admin |
| API Endpoint | `https://openwebui.example.com:51122/v1/` | Tích hợp |
| Nội bộ (LAN) | `https://10.0.0.1:3000/` | Truy cập trực tiếp |

---

## 🏗️ Kiến trúc

```
Internet → Firewall NAT: 51122 → 3000
                    │
             Nginx :3000 (HTTPS) ← DUY NHẤT PORT MỞ
                    │
        ┌───────────┴───────────┐
        │                       │
  Open WebUI :8080        Middleware :5000
  (Chat, RAG, KB)         (Auth, Quota, Dashboard)
        │                       │
  SearXNG + Redis          LiteLLM :4000
        │                       │
  PostgreSQL :5432          → OpenAI / Gemini / xAI / Anthropic
  (PGVector)
```

| Service | Port | CPU | RAM | Mục đích |
|---------|:----:|:---:|:---:|----------|
| Nginx | **3000** | 1 | 512MB | Reverse proxy, SSL, rate limit |
| Open WebUI | 8080 | 6 | 10GB | Chat UI, RAG, knowledge |
| Middleware | 5000 | 4 | 2GB | Auth, quota, cost, dashboard |
| LiteLLM | 4000 | 4 | 4GB | LLM routing, retry, fallback |
| PostgreSQL | 5432 | 2 | 8GB | Database + vector search |
| SearXNG | 8080 | 1 | 1GB | Web search engine |
| Redis | 6379 | 0.5 | 256MB | Search cache + WebSocket |

> Chi tiết kiến trúc: [docs/03-architecture.md](docs/03-architecture.md)

---

## 📚 Tài liệu

### Cho tất cả
| # | Tài liệu | Nội dung |
|---|----------|----------|
| 01 | [Tổng quan hệ thống](docs/01-tong-quan-he-thong.md) | **📌 Nguồn sự thật chính** — toàn bộ hệ thống |
| 11 | [Báo cáo tổng quan](docs/11-system-overview-report.md) | Báo cáo trình bày cho lãnh đạo |
| 10 | [Hướng dẫn sử dụng](docs/10-user-guide-vi.md) | Hướng dẫn end-user (tiếng Việt) |

### Cho quản trị viên
| # | Tài liệu | Nội dung |
|---|----------|----------|
| 02 | [Vận hành](docs/02-tai-lieu-van-hanh.md) | Troubleshooting, commands, monitoring |
| 08 | [Dashboard](docs/08-dashboard.md) | Dashboard UI, metrics, charts |
| 09 | [Quản lý Users](docs/09-user-management.md) | User CRUD, RBAC, subkey |
| 13 | [Cảnh báo Quota](docs/13-canh-bao-quota.md) | Hệ thống cảnh báo quota |
| 15 | [Nginx HTTPS](docs/15-nginx-https.md) | SSL, routing, rate limiting |

### Cho đội kỹ thuật
| # | Tài liệu | Nội dung |
|---|----------|----------|
| 03 | [Kiến trúc](docs/03-architecture.md) | System, component, data flow diagrams |
| 04 | [Sơ đồ](docs/04-architecture-diagrams.md) | Diagrams bổ sung |
| 05 | [Database](docs/05-database-architecture.md) | Schema 32 tables, ERD |
| 06 | [RAG](docs/06-rag-architecture.md) | Embedding, chunking, vector search |
| 07 | [API Reference](docs/07-api-reference.md) | REST endpoints, request/response |
| 12 | [Checklist](docs/12-checklist-tinh-nang.md) | 109 tính năng, trạng thái test |
| 14 | [Kế hoạch mở rộng](docs/14-ke-hoach-mo-rong.md) | Scale plan Phase 1-3 |
| 16 | [Web Search](docs/16-web-search.md) | SearXNG, Redis cache |
| 17 | [Cân bằng tải](docs/17-can-bang-tai.md) | Load balancing, RPM |

**Thứ tự đọc khuyến nghị**: 01 → 11 → 10 → 02 → 08 → 03 → 05

> Cho AI assistant: Đọc [PROJECT.md](PROJECT.md) để có context nhanh nhất.

---

## 🛠️ Vận hành

### Lệnh thường dùng

```bash
# Khởi động / Dừng
docker compose up -d                              # Start 8 services
docker compose down                               # Stop, giữ data
docker compose restart middleware                  # Restart 1 service

# Xem logs
docker compose logs -f middleware --tail=50        # Follow middleware logs
docker compose ps                                 # Trạng thái containers

# Nginx (zero-downtime)
docker exec openwebui-nginx nginx -t              # Test config
docker exec openwebui-nginx nginx -s reload        # Reload

# Backup database
docker exec openwebui-postgres pg_dump -U openwebui_user -d openwebui > backup_openwebui.sql
docker exec openwebui-postgres pg_dump -U openwebui_user -d middleware > backup_middleware.sql
```

### Thao tác định kỳ

| Chu kỳ | Thao tác |
|--------|----------|
| Hàng ngày | Duyệt user pending, kiểm tra chi phí |
| Hàng tuần | Review chi phí per user, health check, backup DB |
| Hàng tháng | Điều chỉnh quota, update hệ thống |
| Hàng năm | Gia hạn SSL certificate |

> Chi tiết: [docs/02-tai-lieu-van-hanh.md](docs/02-tai-lieu-van-hanh.md)

---

## 💻 Phát triển

### Quy trình (OpenSpec + Superpower)

| Độ phức tạp | Quy trình |
|-------------|-----------|
| **Nhỏ** (fix bug, config) | Implement thẳng |
| **Vừa** (1-3 files) | `/opsx:propose` → `/opsx:apply` → `/opsx:archive` |
| **Lớn** (5+ files) | `/superpower` — 7 bước: brainstorm → plan → branch → TDD → review → verify → merge |

### File cấu hình quan trọng

| File | Khi nào sửa |
|------|-------------|
| `docker-compose.yml` | Đổi port, tăng resource, thêm service |
| `.env` | Đổi API key, mật khẩu DB |
| `nginx/nginx.conf` | Thêm route, đổi rate limit |
| `litellm/litellm_config.yaml` | Thêm/bớt model AI |
| `searxng/settings.yml` | Thêm/bớt search engine |

### Cấu trúc Middleware

```
llm-mw/
├── main.py              # FastAPI entry point
├── api/                 # Endpoint handlers
│   ├── chat.py          # /v1/chat/completions (main proxy)
│   ├── images.py        # /v1/images/generations
│   ├── audio.py         # /v1/audio/transcriptions
│   ├── summary.py       # /v1/_mw/summary (dashboard metrics)
│   ├── stream.py        # /v1/_mw/stream (SSE audit)
│   ├── user_admin.py    # User CRUD API
│   └── ...
├── core/                # Business logic
│   ├── auth.py          # HMAC-SHA256 subkey validation
│   ├── quota.py         # Quota enforcement
│   ├── cost.py          # Cost calculation
│   ├── db.py            # PostgreSQL connection
│   └── alerting.py      # Quota alerts
├── dashboard/           # Admin SPA (HTML/CSS/JS)
└── data/                # Runtime configs
```

### Kiểm thử (Testing)

Dự án sử dụng **Playwright** cho kiểm thử tự động E2E:

```bash
cd tests
npx playwright test rag.spec.ts    # Chạy test RAG functional
npx playwright test auth.spec.ts   # Chạy test Authentication
npx playwright show-report         # Xem báo cáo chi tiết
```

---

## 🔒 Bảo mật

- ✅ **HTTPS** TLS 1.2/1.3 qua Nginx
- ✅ **Subkey** HMAC-SHA256 (one-way hash)
- ✅ **JWT** HttpOnly cookie (4h expiry)
- ✅ **Rate limiting** 10 req/s chat, 5 req/min login
- ✅ **Docker network** — tất cả port internal ĐÓNG
- ✅ **Embedding local** — tài liệu RAG không gửi ra ngoài
- ⚠️ Chat content được gửi tới LLM providers (bản chất cloud LLM)

---

**Version**: 4.0 (Docker + Nginx HTTPS + 4 Providers)  
**Cập nhật**: 28/03/2026  
**Liên hệ**: Đội kỹ thuật AI — Rạng Đông
