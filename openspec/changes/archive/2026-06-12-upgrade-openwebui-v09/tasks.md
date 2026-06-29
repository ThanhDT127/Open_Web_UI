## 1. Preflight va inventory

- [x] 1.1 Xac nhan target upgrade chinh thuc la `ghcr.io/open-webui/open-webui:v0.9.5`
- [x] 1.2 Inventory toan bo custom tools/functions/filters dang ton tai trong Open WebUI runtime, khong chi trong repo
- [x] 1.3 Xac dinh co hay khong custom client/script dang goi logout bang `GET`
- [x] 1.4 Xac dinh co hay khong workflow dang dua vao unauthenticated retrieval status endpoint
- [x] 1.5 Ra soat connection/config nao co the bi anh huong boi driver change `asyncpg -> psycopg`

## 2. Backup va staging readiness

- [x] 2.1 Backup database `openwebui`
- [x] 2.2 Backup database `middleware`
- [x] 2.3 Backup `Dockerfile.openwebui` va `docker-compose.yml`
- [x] 2.4 Backup `openwebui_data` volume neu can phuc hoi nhanh
- [x] 2.5 Export settings, models, tools, functions tu Admin Panel neu deployment dang dung nhieu runtime config

## 3. Runtime compatibility fixes

- [x] 3.1 Sua cac custom runtime tools/functions/filters chua tuong thich async
- [x] 3.2 Xac nhan `tools/tool_export_all.py` va cac artifact trong repo van tuong thich voi `v0.9.5`
- [x] 3.3 Ra soat anh huong cua permission hardening doi voi sharing, tool updates, file attachments, knowledge attachments
- [x] 3.4 Ra soat anh huong cua security hardening doi voi external image URLs, HTML/file previews, va outbound fetch behavior

## 4. Image pin va deployment changes

- [x] 4.1 Cap nhat `Dockerfile.openwebui` sang `open-webui:v0.9.5`
- [x] 4.2 Danh gia co can them env vars moi cho hardening nhu `AIOHTTP_CLIENT_ALLOW_REDIRECTS`, `IFRAME_CSP`, `TERMINAL_PROXY_HEADERS`, `CUSTOM_API_KEY_HEADER` hay khong
- [x] 4.3 Build Open WebUI image tren staging
- [x] 4.4 Khoi dong staging va theo doi migration/log startup

## 5. Staging verification

- [x] 5.1 Test login/logout va session flow
- [x] 5.2 Test chat completion cho tat ca providers
- [x] 5.3 Test streaming, usage tracking, va dashboard analytics
- [x] 5.4 Test RAG upload/query voi Docling + PGVector
- [x] 5.5 Test web search qua SearXNG, bao gom search co nhieu ngon ngu neu can
- [x] 5.6 Test custom tools/functions/filters, bao gom export flow
- [x] 5.7 Test persisted chats, attachments, file preview, va Admin Panel
- [x] 5.8 Test multi-worker WebSocket behavior voi Redis manager

## 6. Production rollout

- [x] 6.1 Chot cua so maintenance, tranh rolling update
- [x] 6.2 Build va deploy Open WebUI production trong mot dot dong thoi
- [x] 6.3 Theo doi logs de xac nhan migration thanh cong va khong co crash async/runtime
- [x] 6.4 Chay smoke test production ngay sau deploy

## 7. Rollback va hau kiem

- [x] 7.1 Chuan bi rollback image/build neu startup hoac smoke test that bai
- [x] 7.2 Chuan bi rollback database tu backup neu migration gay loi nghiem trong
- [x] 7.3 Cap nhat docs van hanh theo version moi va thay doi behavior
- [x] 7.4 Danh gia tinh nang moi nao nen bat sau upgrade: Automations, Calendar, task management, hardening env vars, Channel tool support
