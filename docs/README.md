# Open WebUI Stack

Nền tảng chat AI đầy đủ tính năng với middleware xác thực, quản lý quota, và hỗ trợ đa nhà cung cấp LLM.

## Khởi động Nhanh

```bash
# Clone & thiết lập
git clone https://github.com/your-org/oppen-web-ui.git
cd oppen-web-ui

# Cấu hình
cp .env.example .env
# Sửa .env với API keys của bạn

# Chạy
docker compose up -d

# Truy cập
open http://localhost:3000
```

## Kiến trúc

```
User ──HTTPS──▶ Nginx (:3000) ─▶ Open WebUI (:8080) ─▶ Middleware (:5000) ─▶ LiteLLM (:4000) ─▶ OpenAI/Gemini/xAI/Anthropic
                                                             ↓
                                                      PostgreSQL (:5432)
```

## Mô hình Hỗ trợ

| Tiền tố | Loại                          | Ví dụ                                     |
| ------- | ----------------------------- | ----------------------------------------- |
| `chat-` | Chat đa phương thức (text+vision) | `chat-gpt-5.4`, `chat-gemini-2.5-flash` |
| `img-`  | Tạo ảnh                       | `img-gpt-1.5`, `img-gemini-3.1-flash`    |
| `tts-`  | Text-to-Speech                | `tts-gpt-4o-mini`                         |
| `stt-`  | Speech-to-Text                | `stt-gpt-4o`, `stt-gpt-4o-mini`           |

## Tài liệu

| Tài liệu                                                       | Mô tả                            |
| -------------------------------------------------------------- | -------------------------------- |
| [01-tong-quan-he-thong.md](docs/01-tong-quan-he-thong.md)      | Tổng quan hệ thống               |
| [02-tai-lieu-van-hanh.md](docs/02-tai-lieu-van-hanh.md)        | Tài liệu vận hành                |
| [03-architecture.md](docs/03-architecture.md)                  | Kiến trúc Middleware             |
| [04-architecture-diagrams.md](docs/04-architecture-diagrams.md)| Sơ đồ kiến trúc                  |
| [05-database-architecture.md](docs/05-database-architecture.md)| Kiến trúc Database (32 bảng)     |
| [06-rag-architecture.md](docs/06-rag-architecture.md)          | Kiến trúc RAG chi tiết           |
| [07-api-reference.md](docs/07-api-reference.md)                | Tài liệu API endpoints           |
| [08-dashboard.md](docs/08-dashboard.md)                        | Dashboard Admin                  |
| [09-user-management.md](docs/09-user-management.md)            | Quản lý người dùng               |
| [10-user-guide-vi.md](docs/10-user-guide-vi.md)                | Hướng dẫn sử dụng                |
| [11-system-overview-report.md](docs/11-system-overview-report.md)| Báo cáo tổng quan hệ thống     |
| [12-checklist-tinh-nang.md](docs/12-checklist-tinh-nang.md)    | Checklist tính năng              |

## Lệnh Thường dùng

```bash
# Khởi động tất cả services
docker compose up -d

# Dừng tất cả services
docker compose down

# Rebuild sau khi thay đổi cấu hình
docker compose up -d --build

# Xem logs
docker compose logs -f middleware

# Kiểm tra sức khỏe
curl http://localhost:5000/health
```

## API Keys Cần thiết

- **OpenAI**: [platform.openai.com](https://platform.openai.com)
- **Gemini**: [aistudio.google.com](https://aistudio.google.com)
- **xAI (Grok)**: [console.x.ai](https://console.x.ai)
- **Anthropic**: [console.anthropic.com](https://console.anthropic.com)

## Cấu trúc Dự án

```
├── docker-compose.yml      # Điều phối chính
├── .env.example            # Template môi trường
├── litellm/
│   └── litellm_config.yaml # Định nghĩa models
├── llm-mw/                 # Mã nguồn Middleware
│   ├── api/                # API endpoints
│   ├── core/               # Auth, quota, cost
│   ├── data/               # users.json, prices.json
│   └── Dockerfile
├── docs/                   # Tài liệu
└── tests/                  # Playwright tests
```

## Kiểm thử

```bash
cd tests
npm install
npx playwright test
```

## Giấy phép

MIT
