# PROJECT.md — Nguồn sự thật cho AI

> File này là context cố định cho AI coding assistant (Antigravity, Claude Code, Copilot...).
> Đọc file này TRƯỚC khi làm bất kỳ thay đổi nào trong dự án.

---

## Dự án là gì?

**Open WebUI Stack** — Nền tảng AI nội bộ cho doanh nghiệp 200+ nhân viên.
Một "ChatGPT nội bộ" với kiểm soát chi phí, bảo mật dữ liệu, và quản trị tập trung.

**Owner**: Rạng Đông  
**Domain**: `https://openwebui.example.com:51122/`  
**Infra**: Windows Server (20 CPU / 32GB RAM), Docker Compose, 8 containers  

---

## Tech Stack

| Layer | Tech | Version |
|-------|------|---------|
| Reverse Proxy | Nginx (alpine) | latest, HTTPS TLS 1.2/1.3 |
| Frontend | Open WebUI | Custom build, SvelteKit |
| Middleware | FastAPI (Python) | Custom build, 4 Uvicorn workers |
| LLM Proxy | LiteLLM | `ghcr.io/berriai/litellm:main-latest`, 4 workers |
| Database | PostgreSQL 16 + PGVector 0.8.0 | 32 tables (26 openwebui + 6 middleware) |
| Search | SearXNG | Self-hosted, DuckDuckGo/Brave/Bing |
| Cache | Redis 7 | Search cache + WebSocket state |
| Embedding | sentence-transformers | `paraphrase-multilingual-MiniLM-L12-v2` (local) |

---

## Cấu trúc thư mục

```
Oppen_Web_UI/
├── docker-compose.yml       # 8 services định nghĩa
├── .env                     # API keys, secrets (KHÔNG commit)
├── Dockerfile.openwebui     # Open WebUI custom build
├── nginx/
│   ├── nginx.conf           # Routing, SSL, rate limiting
│   └── ssl/                 # Certificates (gitignored)
├── litellm/
│   └── litellm_config.yaml  # 20 models: 14 chat + 3 image + 1 TTS + 2 STT
├── llm-mw/                  # Middleware source code
│   ├── main.py              # FastAPI entry point
│   ├── api/                 # Endpoint handlers (chat, admin, images, audio, stream...)
│   ├── core/                # Business logic (auth, quota, cost, db, alerting)
│   ├── dashboard/           # Admin SPA (HTML/CSS/JS)
│   ├── data/                # Runtime data (alert_config, system_alerts)
│   ├── models/              # SQLAlchemy models
│   ├── services/            # External clients (litellm)
│   └── utils/               # Helpers (jwt, logging, auth_guard)
├── docs/                    # 17 tài liệu kỹ thuật (xem mục lục bên dưới)
├── scripts/                 # Migration scripts, SQL init
├── searxng/                 # SearXNG config
├── tests/                   # Playwright tests
├── tools/                   # Open WebUI custom tools (export Excel/PDF/Word)
├── openspec/                # OpenSpec specs & changes
│   ├── changes/             # Active feature specs
│   └── specs/               # Project-level specs
└── logs/                    # Runtime logs (gitignored)
```

---

## Services Architecture

```
NAT: 51122 → 3000
       │
  Nginx :3000 (HTTPS) ← CHỈ PORT NÀY MỞ
       │
  ┌────┴──────────────┐
  │                   │
  Open WebUI :8080    Middleware :5000
  (6 workers, 10GB)   (4 workers, 2GB)
  │                   │
  SearXNG :8080       LiteLLM :4000
  Redis :6379         (4 workers, 4GB)
  │                   │
  PostgreSQL :5432    → OpenAI / Gemini / xAI / Anthropic
  (8GB, PGVector)
```

### Nginx Routing Rules

| Path | Backend | Purpose |
|------|---------|---------|
| `/` | open-webui:8080 | Chat UI |
| `/_app/`, `/static/` | open-webui:8080 | JS/CSS assets |
| `/ws/` | open-webui:8080 | WebSocket |
| `/api/v1/auths/` | open-webui:8080 | Login (rate: 5req/min) |
| `/v1/` | middleware:5000 | LLM API proxy |
| `/v1/_mw/` | middleware:5000 | Admin API + SSE |
| `/dashboard` | middleware:5000 | Admin SPA |

---

## Databases

### openwebui (26 tables)
User, Auth, Chat, Channel, Message, Knowledge, File, Document, DocumentChunk (vector 384d HNSW), Config, Feedback, Group, Tag...

### middleware (6 tables)
- `mw_users` — user_id, subkey_hash (HMAC-SHA256), role, active, allowed_models, quota (JSONB)
- `mw_prices` — model pricing (input_per_1m, output_per_1m, image_cost)
- `mw_audit_log` — every request: user, model, tokens, cost, latency
- `mw_request_log` — HTTP access log
- `mw_pending` — streaming requests in progress
- `mw_config` — runtime config (key-value JSONB)

> **Lưu ý**: Không có FK giữa 2 databases (by design).

---

## Authentication

| Component | Method | Detail |
|-----------|--------|--------|
| Open WebUI | Email + Password | Bcrypt, JWT |
| Middleware API | Subkey (Bearer) | HMAC-SHA256 with MW_SECRET |
| Dashboard | Admin key | JWT cookie, HttpOnly, 4h |
| LiteLLM | Master key | LITELLM_MASTER_KEY env |

---

## AI Providers (via LiteLLM)

4 providers: **OpenAI**, **Google Gemini**, **xAI**, **Anthropic**
- 14 chat models (e.g., GPT-5, Gemini 2.5 Flash/Pro, Grok-4, Claude 4.6)
- 3 image models (DALL-E, Gemini Image)
- 1 TTS + 2 STT models

---

## Coding Conventions

### Python (Middleware)
- **Framework**: FastAPI + Uvicorn
- **Style**: Type hints required, async preferred
- **DB**: SQLAlchemy + psycopg / psycopg2-based PostgreSQL integrations
- **Auth**: HMAC-SHA256 subkey hashing, JWT for dashboard
- **Logging**: Structured logging to `logs/`
- **Tests**: Playwright (E2E), pytest (unit)

### Quy tắc chung
- `.env` KHÔNG BAO GIỜ commit (secrets)
- Tất cả port internal ĐÓNG, chỉ Nginx :3000 mở
- Embedding chạy 100% local — tài liệu nội bộ KHÔNG gửi ra ngoài
- Chat content GỬI tới LLM providers (đây là bản chất cloud LLM)

---

## Tài liệu (docs/)

| # | File | Nội dung | Đối tượng |
|---|------|----------|-----------|
| 01 | tong-quan-he-thong | **Nguồn sự thật chính** — toàn bộ hệ thống | Tất cả |
| 02 | tai-lieu-van-hanh | Vận hành, troubleshooting, commands | QTV |
| 03 | architecture | Diagrams: system, component, data flow | Kỹ thuật |
| 04 | architecture-diagrams | Sơ đồ bổ sung | Kỹ thuật |
| 05 | database-architecture | Schema 32 tables, ERD | Kỹ thuật |
| 06 | rag-architecture | RAG pipeline, embedding, vector search | Kỹ thuật |
| 07 | api-reference | REST endpoints, request/response | Dev |
| 08 | dashboard | Dashboard UI, metrics, charts | QTV |
| 09 | user-management | User CRUD, RBAC, subkey | QTV |
| 10 | user-guide-vi | Hướng dẫn end-user (tiếng Việt) | Users |
| 11 | system-overview-report | Báo cáo cho lãnh đạo | Ban LĐ |
| 12 | checklist-tinh-nang | 109 tính năng, trạng thái test | QTV+KT |
| 13 | canh-bao-quota | Hệ thống cảnh báo quota | QTV |
| 14 | ke-hoach-mo-rong | Scale plan: Phase 1-3 | Kỹ thuật |
| 15 | nginx-https | Nginx config, SSL, routing | QTV |
| 16 | web-search | SearXNG, Redis cache, filter | Kỹ thuật |
| 17 | can-bang-tai | Load balancing, rate limit | Kỹ thuật |

**Thứ tự đọc**: 01 → 11 → 10 → 02 → 08 → 03 → 05

---

## Common Commands

```bash
# Start/Stop
docker compose up -d
docker compose down
docker compose restart middleware

# Logs
docker compose logs -f middleware --tail=50
docker compose logs -f litellm --tail=50

# Health check
docker compose ps
curl -k https://localhost:3000/health

# Database backup
docker exec openwebui-postgres pg_dump -U openwebui_user -d openwebui > backup_openwebui.sql
docker exec openwebui-postgres pg_dump -U openwebui_user -d middleware > backup_middleware.sql

# Nginx reload (zero-downtime)
docker exec openwebui-nginx nginx -t
docker exec openwebui-nginx nginx -s reload
```

---

## Development Workflow

Dự án sử dụng **OpenSpec** + **Superpower workflow**:

| Task size | Process |
|-----------|---------|
| Nhỏ (< 5 min) | Implement thẳng |
| Vừa (1-3 files) | `/opsx:propose` → `/opsx:apply` → `/opsx:archive` |
| Lớn (5+ files) | `/superpower` (7 bước: brainstorm → plan → branch → TDD → review → verify → merge) |

Specs lưu tại: `openspec/changes/<feature>/`

---

*Cập nhật: 28/03/2026 — Phiên bản 1.0*
