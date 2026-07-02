## Context

He thong hien tai la mot deployment Docker Compose gom:

- `open-webui` build tu `Dockerfile.openwebui`
- PostgreSQL/PGVector cho `openwebui` va `middleware`
- Redis cho WebSocket manager va SearXNG
- middleware rieng de auth/quota/cost tracking
- LiteLLM rieng
- SearXNG cho web search
- Docling cho content extraction
- Nginx reverse proxy

Open WebUI dang chay:

- image base `ghcr.io/open-webui/open-webui:main`
- `UVICORN_WORKERS=6`
- `ENABLE_WEBSOCKET_SUPPORT=true`
- `WEBSOCKET_MANAGER=redis`

Release line `v0.9.0` -> `v0.9.5` khong chi them tinh nang. No gom ca:

- backend async migration
- database migrations
- Responses API improvements
- web search, file, STT, analytics, persisted chat fixes
- security hardening va permission tightening

Vi vay, change nay can duoc xu ly nhu mot platform upgrade co inventory + migration + verification, khong phai chi doi image tag.

## Goals / Non-Goals

**Goals:**
- Nang Open WebUI len mot target on dinh va cu the: `v0.9.5`
- Bao toan kha nang van hanh hien tai: chat, RAG, web search, tools, middleware integration, dashboard
- Xac dinh va xu ly cac runtime artifact co the bi anh huong boi async migration
- Xac thuc cac breaking changes tu `v0.9.0` -> `v0.9.5` tren deployment nay
- Tien hanh upgrade theo cach rollback duoc va co downtime co kiem soat

**Non-Goals:**
- Khong bat ngay toan bo tinh nang moi cua Open WebUI
- Khong thay doi kien truc searxng/middleware/litellm
- Khong gop chung provider-native web search vao change nay
- Khong refactor middleware tru khi upgrade lam lo blocker ro rang

## Decisions

### D1. Pin len `v0.9.5`, khong dung `main`, khong dung `v0.9.0`

**Decision:** target image se la `ghcr.io/open-webui/open-webui:v0.9.5`.

**Rationale:**
- `main` gay drift va khong reproducible
- `v0.9.5` gom cac sua loi/hardening cua `v0.9.1` -> `v0.9.5`
- tranh phai nang cap len `v0.9.0` roi lai tiep tuc patch gap len cac ban sau

**Alternatives considered:**
- Giu `main`: bi loai vi khong kiem soat duoc thay doi
- Dung `v0.9.0`: bi loai vi bo lo nhieu sua loi va security fixes

### D2. Tach "core upgrade" khoi "feature adoption"

**Decision:** change nay uu tien nang cap nen tang an toan. Tinh nang moi nhu Automations, Calendar, Desktop app, Channel tool streaming chi duoc danh gia sau khi core upgrade on dinh.

**Rationale:**
- Giam blast radius
- de phan biet loi do migration voi loi do feature adoption
- phu hop deployment hien tai dang co middleware, quota, searxng, docling rieng

**Alternatives considered:**
- Bat ngay tinh nang moi sau upgrade: tang rui ro, kho debug

### D3. Inventory runtime artifacts ngoai repo la bat buoc

**Decision:** truoc khi apply, phai inventory custom tools/functions/filters trong runtime Open WebUI (Admin DB / workspace config), khong chi xem code trong repo.

**Rationale:**
- repo hien chi cho thay mot phan (`tools/tool_export_all.py`, `quota_alert_filter.py`)
- Open WebUI cho phep luu runtime artifact trong DB/Admin Panel
- async migration se danh vao runtime behavior truoc tien

**Alternatives considered:**
- Chi audit repo: khong du tin cay

### D4. Xem deployment nay la "simultaneous service upgrade", khong rolling

**Decision:** production rollout phai theo mot dot maintenance co downtime co kiem soat.

**Rationale:**
- release notes neu ro DB migration khong ho tro rolling update
- service dang chay nhieu workers va co Redis/WebSocket coordination

**Alternatives considered:**
- rolling restart: bi loai vi conflict schema/runtime

### D5. Verification phai bao gom nhung diem moi cua `v0.9.2+`

**Decision:** smoke test se khong dung lai o chat co response, ma phai cover them:

- signout flow (`POST`)
- persisted chat settings/autosave
- streaming analytics / token accounting
- SearXNG behavior
- file preview/attachments
- multi-worker tool refresh va WebSocket stability

**Rationale:**
- day la cac diem da duoc sua trong `v0.9.2` -> `v0.9.5`
- deployment nay dang phu thuoc truc tiep vao search, RAG, streaming, custom tools

### D6. Hardening env vars duoc danh gia sau khi staging on dinh

**Decision:** cac env moi nhu `AIOHTTP_CLIENT_ALLOW_REDIRECTS`, `IFRAME_CSP`, `TERMINAL_PROXY_HEADERS`, `CUSTOM_API_KEY_HEADER` duoc danh gia ro rang tren staging thay vi bat vo dieu kien ngay trong cung thay doi image.

**Rationale:**
- mot so cai co the thay doi hanh vi preview/fetch/proxy
- can tach "phien ban moi chay on" khoi "chinh sach bao mat moi"

**Alternatives considered:**
- Bat tat ca hardening ngay: an toan hon tren ly thuyet, nhung kho xac dinh goc loi neu co regression

## Risks / Trade-offs

- [Runtime artifact nam ngoai repo] -> Export/inventory tu Admin Panel va database truoc khi deploy
- [DB migration loi] -> Backup `openwebui` DB, backup volume neu can, chot rollback plan truoc
- [Multi-worker incompatibility] -> Deploy dong thoi trong maintenance window, khong rolling
- [Behavior changes o auth/retrieval/sharing] -> Them checklist verify signout, sharing, file attachment, knowledge attachment
- [Security hardening lam lo workflow cu] -> Test cac luong fetch URL, image preview, HTML/file preview, terminal proxy tren staging
- [Tinh nang moi lam tang scope] -> Tinh nang moi chi ghi nhan va danh gia sau, khong auto-enable

## Migration Plan

1. Preflight
   - pin target version `v0.9.5`
   - inventory runtime artifacts
   - review release-impact areas: signout, retrieval, db driver, sharing, outbound fetch

2. Backup
   - backup `openwebui` DB
   - backup `middleware` DB
   - backup config/build files
   - backup `openwebui_data` neu can

3. Staging
   - doi image tag
   - build va bring up staging
   - chay migration
   - chay smoke test cho auth/chat/RAG/search/tools/streaming/dashboard

4. Production
   - maintenance window
   - deploy dong thoi service Open WebUI
   - xac nhan health, logs, migrations, worker behavior

5. Rollback
   - rollback image/build neu startup fail
   - rollback DB neu migration gay su co nghiem trong

## Open Questions

- Cac custom tools/functions/filters dang duoc luu trong Admin DB la gi, va cai nao chua async-safe?
- Co client/script/noi bo nao dang dua vao signout `GET` hay retrieval status endpoint cu khong?
- Sau khi nang cap on dinh, co muon bat Automations/Calendar cho nguoi dung hay de sau?
- Co can bat them hardening env vars ngay trong dot nang cap nay hay de mot change rieng?
