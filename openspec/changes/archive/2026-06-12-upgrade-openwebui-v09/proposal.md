# Upgrade Open WebUI -> v0.9.5

## Ly do

Hien tai he thong dang build tu `ghcr.io/open-webui/open-webui:main`, trong khi muc tieu cu trong change la `v0.9.0`. Dieu nay khong con phu hop:

- `main` khong on dinh cho production va co the thay doi ngoai y muon
- `v0.9.0` da cu so voi chuoi release `v0.9.1` -> `v0.9.5`
- cac ban `v0.9.2+` bo sung nhieu sua loi, hardening va thay doi van hanh quan trong cho deployment nay

Tu `v0.9.0` den `v0.9.5`, Open WebUI bo sung:

- backend async va cac toi uu hieu nang lon
- Automations, Calendar workspace, task management
- ho tro Responses API tot hon (Azure, Ollama, tool output, citations)
- cai tien file handling, terminal, chat persistence, analytics
- sua loi lien quan web search, streaming, tools, chat settings, STT
- hardening bao mat: SSRF guard, iframe CSP, stricter permissions, file ownership checks

Deployment nay dac biet nhay cam vi dang co:

- PostgreSQL + PGVector
- Redis + WebSocket manager
- 6 `UVICORN_WORKERS`
- middleware rieng, LiteLLM rieng, Nginx rieng
- SearXNG, Docling, custom tools/functions/filters

## Breaking Changes / Behavioral Changes

### 1. Database migrations va deploy mode

`v0.9.0` va `v0.9.3` deu nhan manh:

- co database schema migrations
- multi-worker / multi-instance phai update dong thoi
- rolling update khong duoc ho tro

Deployment hien tai dang chay nhieu workers trong cung mot service, nen can xem day la mot lan nang cap co downtime co kiem soat, khong phai hot-swap.

### 2. Async migration cho custom Functions / Tools / Filters

Open WebUI `v0.9.x` chuyen nhieu path backend sang async. Moi custom runtime artifact can duoc inventory lai:

- tools/functions luu trong Admin Panel / database
- filters dang gan vao model / workspace
- code custom nam ngoai repo nay

Phan trong repo cho thay `tools/tool_export_all.py` da la `async def action(...)`, nhung chang the ket luan toan bo artifact runtime deu da san sang.

### 3. Signout endpoint thay doi

Tu `v0.9.3`, signout dung `POST` thay vi `GET`. Neu co custom client, reverse proxy flow, script test, hoac tai lieu noi bo dang goi logout theo `GET`, can cap nhat.

### 4. Async database driver thay doi

`v0.9.2` doi async PostgreSQL driver tu `asyncpg` sang `psycopg` v3. Ve mat chuc nang thong thuong day la thay doi trong suot, nhung moi custom connection string hoac patch dua tren `asyncpg` semantics can duoc ra soat.

### 5. Security defaults va permission tightening

`v0.9.3` va `v0.9.5` them nhieu hardening:

- chong redirect-based SSRF
- iframe CSP control
- stricter file / folder / knowledge attachment ownership
- stricter tool source code update permissions
- stricter public sharing permissions cho skill/calendar/chat
- bo endpoint retrieval status khong xac thuc

Can xem co workflow nao hien tai dang vo tinh dua vao hanh vi cu hay khong.

## Scope

### [MODIFY] Docker/Open WebUI target version

- doi `Dockerfile.openwebui` tu `open-webui:main` sang `open-webui:v0.9.5`
- xac nhan custom pip dependencies van compatible

### [MODIFY] Upgrade plan va runtime artifact inventory

- inventory toan bo custom tools/functions/filters dang ton tai trong Open WebUI runtime
- xac dinh artifact nao can sua de tuong thich voi backend async
- xac dinh tich hop nao co the bi anh huong boi signout POST, driver change, permissions hardening

### [MODIFY] Deployment va verification flow

- cap nhat quy trinh backup/deploy/rollback theo yeu cau migration cua `v0.9.x`
- them verification cho WebSocket multi-worker, SearXNG, Docling, upload/query RAG, custom tools, analytics, signout

### [MODIFY] Docs

- cap nhat version target thanh `v0.9.5`
- document tinh nang moi dang quan tam, nhung tach ro:
  - tinh nang duoc huong loi ngay sau upgrade
  - tinh nang se danh gia/bat sau

## Khong nam trong scope

- Khong auto-bat toan bo tinh nang moi (Automations, Calendar, Channel tools, Desktop app)
- Khong doi kien truc middleware/LiteLLM/Nginx
- Khong thay SearXNG bang provider-native web search trong change nay
- Khong refactor ung dung middleware neu khong co blocker thuc su do upgrade gay ra

## Thanh phan bi anh huong

Nhung thanh phan duoi day khong nhat thiet bi "xoa" sau upgrade, nhung co kha nang bi anh huong boi migration, async runtime, permission hardening, hoac behavioral changes:

### 1. Open WebUI database va runtime config

- bang `config`
- bang `model`
- bang `function`
- bang `tool`
- chat/message metadata va persisted chat settings
- sharing/access control metadata

**Rui ro:** du lieu van con nhung API/UI/runtime behavior thay doi, dan den "co ma nhu mat".

### 2. Custom runtime artifacts

- Functions upload qua Admin Panel
- Tools paste vao editor cua Open WebUI
- Filters dang gan global hoac gan theo model
- Model-level params/system prompts/feature toggles

**Rui ro:** artifact van ton tai trong DB nhung khong con async-safe, khong duoc expose day du qua list API, hoac bi chuyen hanh vi boi permission changes.

### 3. Auth va session flow

- login/logout qua `/api/v1/auths/`
- session persistence
- reverse proxy / browser flow dang dua vao signout behavior cu

**Rui ro:** `signout` chuyen sang `POST`, mot so flow cu co the hong neu dang goi `GET`.

### 4. Chat runtime va streaming

- chat completions qua middleware + LiteLLM
- streaming responses
- token usage / analytics / dashboard
- task prompts (title/tags/follow-up/query)

**Rui ro:** async backend va streaming accounting thay doi; can xac nhan khong co regression trong usage tracking va chat tasks.

### 5. RAG va file workflows

- upload file
- Docling extraction
- PGVector indexing
- attach lai file cu
- persisted chat attachments
- file previews

**Rui ro:** `v0.9.x` co nhieu sua doi quanh file handling, preview, STT, ownership checks va persisted chat behavior.

### 6. Web search

- SearXNG integration
- multi-language search params
- function calling / native tool behavior trong WebUI

**Rui ro:** release notes co fix lien quan web search va search provider handling; can xac nhan luong SearXNG hien tai van chay nhu cu.

### 7. Multi-worker behavior

- `UVICORN_WORKERS=6`
- Redis-backed WebSocket manager
- tool/function refresh behavior

**Rui ro:** release notes canh bao schema incompatibility trong rollout, va `v0.9.3+` co fix lien quan worker/tool consistency. Can test lai tren deployment thuc te.

## Can test lai sau khi cap nhat

### Bat buoc test lai

1. **Auth**
   - login
   - logout
   - refresh page sau login
   - session/cookie con hop le

2. **Chat**
   - chat thuong
   - streaming
   - title/tags/follow-up generation
   - model params/system prompt van duoc ap dung

3. **Providers**
   - OpenAI
   - Gemini
   - Claude
   - xAI
   - OpenRouter/DeepSeek (neu dang dung)

4. **RAG**
   - upload file moi
   - parse bang Docling
   - index vao PGVector
   - hoi dap tren knowledge da upload
   - attach lai file da co san

5. **Web search**
   - SearXNG search flow
   - query co dau / nhieu ngon ngu neu dang dung
   - khong co double-search ngoai y muon

6. **Custom tools/functions/filters**
   - export tool
   - quota alert filter
   - moi function/filter/tool dang co trong runtime production

7. **Admin / settings**
   - Models page
   - Functions page
   - Tools page
   - Settings page
   - sharing / permissions / access grants

8. **Dashboard / analytics**
   - middleware dashboard
   - token/cost accounting
   - logs / audit query

### Nen test lai

- file preview
- image generation
- STT/TTS neu dang dung
- chat persistence sau reload
- shared chats
- model visibility voi user non-admin

## Tieu chi "an toan de apply"

Co the vao apply phase khi:

- da inventory duoc custom runtime artifacts trong production
- da backup DB `openwebui` va `middleware`
- da xac dinh ro cac luong bat buoc phai regression test
- da chap nhan rang rollout can la mot dot downtime co kiem soat, khong rolling update

## Quy trinh deploy muc tieu

```text
1. Backup PostgreSQL (ca openwebui va middleware)
2. Backup openwebui_data volume neu can
3. Export settings / tools / functions / models config tu Admin Panel neu co
4. Inventory custom runtime artifacts can sua cho async compatibility
5. Pin image sang v0.9.5 va build tren staging
6. Chay migration va smoke test day du tren staging
7. Deploy production trong mot dot dong thoi, co downtime co kiem soat
8. Verify chat, auth, RAG, web search, tools, streaming, analytics
9. Danh gia tinh nang moi nao nen bat sau upgrade
```

## Rui ro

> [!CAUTION]
> - DB migration fail co the anh huong du lieu neu khong backup day du
> - custom runtime tools/filters trong Admin DB co the break du repo da on
> - signout / retrieval / permission changes co the lam vo mot so flow cu
> - multi-worker deployment khong ho tro rolling update
> - hardening moi co the lam lo ra nhung workflow truoc day dang dua vao hanh vi khong an toan

## Prerequisites

- Hoan thanh inventory custom runtime artifacts truoc khi apply
- Backup bat buoc cho database va config quan trong
- Co staging hoac it nhat mot cua so maintenance de test migration
- Ra quyet dinh ro: upgrade chi de on dinh nen tang, hay dong thoi bat them mot so tinh nang moi

## Verification

- [ ] Login / logout hoat dong dung sau thay doi signout method
- [ ] Chat completion qua tat ca providers
- [ ] Streaming response, usage tracking, analytics khong loi
- [ ] RAG upload/query voi Docling + PGVector
- [ ] Web search qua SearXNG van hoat dong
- [ ] Custom tools/functions/filters van chay
- [ ] Admin Panel, model settings, permissions, sharing controls hoat dong
- [ ] Multi-worker WebSocket behavior on dinh
- [ ] MW Dashboard van hoat dong
- [ ] Khong co regressions ro rang o file preview, attachments, va persisted chats
