# CHECK LIST TÍNH NĂNG OPEN WEBUI

> **Ngày cập nhật**: 2026-03-03  
> **Phiên bản hệ thống**: Open WebUI + LiteLLM + Middleware + PostgreSQL/PGVector

---

## Cấu trúc bảng

| STT | Cột                       | Mô tả                             |
| --- | ------------------------- | --------------------------------- |
| 01  | STT                       | Số thứ tự                         |
| 02  | Module                    | Nhóm chức năng lớn                |
| 03  | Nhóm tính năng            | Phân nhóm con                     |
| 04  | Tính năng cụ thể          | Mô tả tính năng                   |
| 05  | Hướng dẫn sử dụng / Mô tả | Cách sử dụng hoặc đầu vào/đầu ra  |
| 06  | Câu lệnh ví dụ            | Ví dụ thực tế                     |
| 07  | Trạng thái                | Đã có / Chưa có / Đang phát triển |
| 08  | Kết quả test              | OK / Đang lỗi / Chưa test         |
| 09  | Ghi chú                   | Thông tin bổ sung                 |

---

## I. PHÂN QUYỀN & QUẢN LÝ NGƯỜI DÙNG

| STT | Nhóm                | Tính năng                     | Mô tả                                             | Kết quả   | Ghi chú                          |
| --- | ------------------- | ----------------------------- | ------------------------------------------------- | --------- | -------------------------------- |
| 1   | Đăng ký & Đăng nhập | Đăng ký bằng email/password   | Truy cập `:3000` → Sign Up → điền thông tin       | OK        | `ENABLE_SIGNUP=true`             |
| 2   |                     | Đăng nhập bằng email/password | Email + password → nhận JWT token                 | OK        |                                  |
| 3   |                     | Hỗ trợ OAuth/SSO              | Đăng nhập qua AD/LDAP/Google/Microsoft            | Chưa test | Cần cấu hình `OAUTH_*` env       |
| 4   | Phân quyền          | 3 cấp: Admin, User, Pending   | Admin: toàn quyền. User: chat. Pending: chờ duyệt | OK        |                                  |
| 5   |                     | Quản lý user (Admin)          | Thêm/xoá user, đổi role, reset password           | OK        | Admin → Settings → Users         |
| 6   |                     | Access Control trên Knowledge | Giới hạn quyền truy cập Knowledge theo user/group | OK        | Hỗ trợ JSON access_control       |
| 7   |                     | Access Control trên Model     | Giới hạn model nào user nào được dùng             | OK        | Admin → Settings → Models        |
| 10  | Nhóm phòng ban      | 8 group phòng ban mẫu         | Seed bằng `scripts/seed_department_access.py`     | OK        | Gán thành viên tay qua Admin UI  |
| 11  |                     | Phân quyền tool theo group    | `access_grant` cho workspace tool + mcpo server    | OK        | Mặc định private, xem doc 09     |
| 12  |                     | Phân quyền tool theo user     | Override cá nhân ngoài chính sách group            | OK        | Workspace → Tools → Access Control |
| 8   | Quản lý log (Admin) | Log hoạt động API requests    | Ghi log: user, model, tokens, cost, timestamp     | OK        | PostgreSQL (mw_audit_log) + file |
| 9   |                     | Dashboard quản trị            | Tổng quan chi phí, request, top users/models      | OK        | `http://<server>:5000/dashboard` |

---

## II. CHAT AI ĐA MÔ HÌNH

| STT | Model / Tính năng          | Mô tả                                  | Kết quả | Ghi chú                              |
| --- | -------------------------- | -------------------------------------- | ------- | ------------------------------------ |
| 1   | Chat GPT-5.4 (Flagship)    | Model mạnh nhất OpenAI, reasoning      | OK      | `chat-gpt-5.4`                       |
| 2   | Chat GPT-5.2               | Cân bằng chất lượng và tốc độ          | OK      | `chat-gpt-5.2`                       |
| 3   | Chat GPT-5                 | Tiêu chuẩn, chi phí hợp lý             | OK      | `chat-gpt-5`                         |
| 4   | Chat Gemini 3.1 Pro        | Flagship Google, reasoning mạnh        | OK      | `chat-gemini-3.1-pro-preview`        |
| 5   | Chat Gemini 3.1 Flash-Lite | Nhanh, chi phí thấp                    | OK      | `chat-gemini-3.1-flash-lite-preview` |
| 6   | Chat Gemini 2.5 Flash      | Cân bằng, tiếng Việt tốt               | OK      | `chat-gemini-2.5-flash`              |
| 7   | Chat Grok 4.20 Reasoning   | Reasoning mạnh, real-time data         | OK      | `chat-grok-4.20-reasoning`           |
| 8   | Chat Grok 4.1 Fast         | Nhanh, reasoning                       | OK      | `chat-grok-4-1-fast-reasoning`       |
| 9   | Chat Grok 4.1 Fast Lite    | Nhanh nhất xAI, chi phí thấp           | OK      | `chat-grok-4-1-fast-non-reasoning`   |
| 10  | Chat Claude Opus 4.6       | Flagship Anthropic, phân tích phức tạp | OK      | `chat-claude-opus-4.6`               |
| 11  | Chat Claude Sonnet 4.6     | Cân bằng chất lượng và tốc độ          | OK      | `chat-claude-sonnet-4.6`             |
| 12  | Chat Claude Haiku 4.5      | Nhanh, chi phí thấp                    | OK      | `chat-claude-haiku-4.5`              |
| 13  | Streaming response         | Response hiển thị từng token realtime  | OK      |                                      |
| 14  | Chat history               | Lưu toàn bộ lịch sử hội thoại          | OK      | Lưu trong PostgreSQL                 |
| 15  | Pin / Archive chat         | Ghim hoặc lưu trữ hội thoại            | OK      |                                      |
| 16  | Share chat                 | Chia sẻ hội thoại qua link công khai   | OK      |                                      |
| 17  | Folder tổ chức chat        | Sắp xếp hội thoại vào folder           | OK      |                                      |
| 18  | Tags                       | Gắn tag cho hội thoại để phân loại     | OK      |                                      |
| 19  | Chuyển model giữa chừng    | Đổi model trong cùng 1 hội thoại       | OK      |                                      |
| 20  | Multimodal input           | Gửi hình ảnh kèm text trong chat       | OK      | Với GPT-5, Gemini, Claude            |

---

## III. TẠO ẢNH AI (IMAGE GENERATION)

| STT | Nhóm   | Tính năng              | Mô tả                                    | Kết quả | Ghi chú                |
| --- | ------ | ---------------------- | ---------------------------------------- | ------- | ---------------------- |
| 1   | OpenAI | GPT-Image-1.5          | Mới nhất, 4x nhanh hơn, 3 cấp chất lượng | OK      | `img-gpt-image-1.5`    |
| 2   |        | GPT-Image-1            | Chất lượng cao, 3 cấp độ                 | OK      | `img-gpt-image-1`      |
| 3   | Google | Gemini 3.1 Flash Image | Tạo ảnh nhanh, chi phí thấp              | OK      | `img-gemini-3.1-flash` |
| 4   |        | Gemini 3 Pro Image     | Chất lượng cao                           | OK      | `img-gemini-3-pro`     |
| 5   | xAI    | Grok Imagine           | Tiêu chuẩn, $0.05/ảnh                    | OK      | `img-grok-imagine`     |
| 6   |        | Grok Imagine Pro       | Chất lượng cao, $0.10/ảnh                | OK      | `img-grok-imagine-pro` |

---

## IV. GIỌNG NÓI (VOICE)

| STT | Nhóm tính năng | Tính năng cụ thể            | Hướng dẫn sử dụng / Mô tả                        | Câu lệnh ví dụ            | Trạng thái | Kết quả | Ghi chú           |
| --- | -------------- | --------------------------- | ------------------------------------------------ | ------------------------- | ---------- | ------- | ----------------- |
| 1   | Text-to-Speech | Chuyển text thành giọng nói | AI đọc nội dung response bằng giọng nói tự nhiên | Nhấn icon 🔊 trên response | Đã có      | OK      | `tts-gpt-4o-mini` |
| 2   | Speech-to-Text | Nhập liệu bằng giọng nói    | Nói vào mic → AI chuyển thành text → gửi prompt  | Nhấn icon 🎤 trong chat    | Đã có      | OK      | `stt-gpt-4o`      |
| 3   |                | Phiên bản nhẹ STT           | Nhận dạng giọng nói nhanh hơn, chi phí thấp      | —                         | Đã có      | OK      | `stt-gpt-4o-mini` |

---

## V. RAG – KNOWLEDGE BASE (CƠ SỞ TRI THỨC)

| STT | Nhóm               | Tính năng                      | Mô tả                                             | Kết quả | Ghi chú                               |
| --- | ------------------ | ------------------------------ | ------------------------------------------------- | ------- | ------------------------------------- |
| 1   | Quản lý Knowledge  | Tạo Knowledge Collection       | Workspace → Knowledge → Create                    | OK      |                                       |
| 2   |                    | Upload file vào Knowledge      | PDF, DOCX, TXT, CSV, MD, HTML, Excel (max 2048MB) | OK      |                                       |
| 3   |                    | Xoá file khỏi Knowledge        | Xoá file → xoá luôn vector embeddings             | OK      | CASCADE delete                        |
| 4   |                    | Access control Knowledge       | Giới hạn quyền truy cập theo user/group           | OK      |                                       |
| 5   | Sử dụng trong chat | Gọi Knowledge bằng `#`         | Gõ `#tên-knowledge` trong chat để chọn            | OK      |                                       |
| 6   |                    | Attach file trực tiếp          | Kéo thả file vào chat, AI đọc và trả lời          | OK      | Xử lý tạm thời, không lưu lâu dài     |
| 7   |                    | Gán Knowledge vào Model        | Admin gán Knowledge mặc định cho model cụ thể     | OK      |                                       |
| 8   | Tìm kiếm           | Hybrid Search (BM25 + Vector)  | Kết hợp keyword + semantic search                 | OK      | `ENABLE_RAG_HYBRID_SEARCH=true`       |
| 9   |                    | HNSW Vector Index              | Approximate nearest neighbor nhanh                | OK      | m=16, ef_construction=64              |
| 10  |                    | Citation (trích dẫn nguồn)     | AI trích dẫn tên file và trang nguồn              | OK      |                                       |
| 11  | Embedding          | Gemini Embedding (API)         | `gemini-embedding-001`, 1536-dim qua Middleware   | OK      | Chi phí: $0.15/1M tokens              |
| 12  |                    | Text chunks gửi qua Gemini API | Chunks gửi tới Google để embedding,lưu on-premise | OK      | Cần lưu ý khi truyền dữ liệu nhạy cảm |
| 13  | Cấu hình           | Chunk size                     | 1500 ký tự / chunk                                | OK      | Có thể điều chỉnh                     |
| 14  |                    | Chunk overlap                  | 100 ký tự overlap giữa các chunks                 | OK      | Giữ context liên tục                  |
| 15  | Định dạng file     | PDF                            | Extract text từ PDF (có hỗ trợ OCR)               | OK      |                                       |
| 16  |                    | Word (.docx)                   | Extract text từ file Word                         | OK      |                                       |
| 17  |                    | Excel (.xlsx)                  | Extract text từ file Excel                        | OK      |                                       |
| 18  |                    | Text (.txt, .csv, .md)         | Đọc trực tiếp                                     | OK      |                                       |
| 19  |                    | HTML                           | Extract text từ trang web                         | OK      |                                       |

---

## VI. CÔNG CỤ MỞ RỘNG (CUSTOM TOOLS)

| STT | Nhóm             | Tính năng                    | Mô tả                                             | Kết quả   | Ghi chú          |
| --- | ---------------- | ---------------------------- | ------------------------------------------------- | --------- | ---------------- |
| 1   | Xuất Excel       | Trích xuất hội thoại → Excel | Action → "Xuất Excel" → .xlsx có format, filter   | OK        | `tool excel.py`  |
| 2   |                  | Wizard UI khi xuất           | Modal progress: chuẩn hoá → tạo file → tải xuống  | OK        | UX thân thiện    |
| 3   |                  | Auto-detect số, ngày, %      | Nhận dạng: số, dấu phẩy, ngày tháng, phần trăm    | OK        |                  |
| 4   |                  | Hỗ trợ tiền tệ VNĐ, $, €     | Nhận dạng và format đúng tiền tệ                  | OK        |                  |
| 5   | Xuất PDF         | Xuất hội thoại → PDF         | Action → "Xuất PDF"                               | OK        | `tool pdf.py`    |
| 6   | Xuất DOCX        | Xuất hội thoại → Word        | Action → "Xuất DOCX"                              | OK        | `tool docx.py`   |
| 7   | Custom Functions | Framework function tuỳ chỉnh | Admin thêm Python functions chạy trong Open WebUI | Chưa test | Hạ tầng sẵn sàng |
| 8   | Custom Tools     | Framework tool tuỳ chỉnh     | Admin tạo tools cho AI gọi (function calling)     | Chưa test | Hạ tầng sẵn sàng |
| 9   | Tool cá nhân hóa | Gmail — gửi mail đứng tên user | Chat: "gửi mail cho anh B..." → duyệt → gửi     | OK        | `google_gmail_tool.py`, OAuth broker |
| 10  |                  | Office 365 — mail/lịch/Teams/SharePoint | Gửi/đọc mail, tạo/xem lịch, nhắn Teams, đọc file | ⚠️ Mô phỏng | MCP `office365` hiện là bản **giả lập** — `outlook_send_email` trả "Email sent (Simulated)" mà KHÔNG gửi mail. Chờ thay bản thật. Tool per-user `office365_tool.py` đã gỡ |
| 11  |                  | GitHub — repo/issue/PR/code  | Xem repo, đọc issue/PR, tìm code bằng token user  | Chưa test | `github_tool.py`; cần GITHUB_CLIENT_ID |
| 12  |                  | Google Drive — tìm/đọc file  | Tìm file, đọc nội dung (tự export Google Docs)     | Chưa test | `google_drive_tool.py`; cần GOOGLE_CLIENT_ID |
| 13  |                  | Kết nối tài khoản 1 chạm     | Tool trả link OAuth; user bấm 1 lần, tự gia hạn    | OK        | `state` ký HMAC, hạn 10 phút     |
| 14  |                  | Duyệt hành động nhạy cảm     | Gửi mail/lịch/Teams phải bấm Duyệt mới thực hiện   | OK        | `filter_approval_handler.py`     |

---

## VII. TÌM KIẾM WEB (WEB SEARCH - SearXNG)

| STT | Tính năng                | Mô tả                                              | Kết quả | Ghi chú                         |
| --- | ------------------------ | -------------------------------------------------- | ------- | ------------------------------- |
| 1   | SearXNG Engine ($0 cost) | Search engine tự host, tổng hợp Google/Brave/DDG   | OK      | Container `searxng`, port 8080  |
| 2   | Native Function Calling  | Model tự gọi tool search khi cần (FC = Gốc/Native) | OK      | GPT-5, 4o, 4.1, Gemini 2.5+/3   |
| 3   | Web Search mặc định      | Bật Default Features > Web Search cho user         | OK      | Mỗi model cấu hình riêng        |
| 4   | Cấu hình Result Count    | Số kết quả = 5, Concurrent Requests = 1            | OK      | Giảm noise, tiết kiệm tokens    |
| 5   | Trích dẫn nguồn          | Response kèm nguồn gốc (chip/tag: website + URL)   | OK      | "Retrieved X sources" indicator |
| 6   | Multi-engine search      | Google + Brave + DuckDuckGo song song              | OK      | Cấu hình `searxng/settings.yml` |

**Cấu hình:** Admin > Settings > Web Search > Engine = `searxng` | Admin > Models > Advanced > Gọi Function = `Gốc`

---

## VIII. KIỂM SOÁT CHI PHÍ & QUOTA (MIDDLEWARE)

| STT | Nhóm          | Tính năng                       | Mô tả                                                 | Kết quả | Ghi chú                                  |
| --- | ------------- | ------------------------------- | ----------------------------------------------------- | ------- | ---------------------------------------- |
| 1   | Quota         | Giới hạn chi phí / user / tháng | Cấu hình qua Dashboard: `limit_cost_usd`              | OK      | Lưu trong PostgreSQL (mw_users)          |
| 2   |               | Cảnh báo khi gần hết quota      | User nhận thông báo khi sử dụng gần hết               | OK      |                                          |
| 3   |               | Chặn khi hết quota              | Từ chối request khi vượt quota                        | OK      | HTTP 429                                 |
| 4   | Sub-keys      | Cấp API key riêng               | Mỗi user có sub-key riêng biệt                        | OK      | Trong DB (mw_users), backup `users.json` |
| 5   | Cost tracking | Ghi log chi phí từng request    | Log: model, tokens, cost_usd, user, timestamp         | OK      | DB (mw_audit_log) + file backup          |
| 6   |               | Tính chi phí theo bảng giá      | Bảng giá riêng cho từng model (backup: `prices.json`) | OK      |                                          |
| 7   | Dashboard     | Xem báo cáo chi phí             | Tổng chi phí, theo user, model, ngày                  | OK      | `http://<server>:5000/dashboard`         |

---

## IX. DATABASE & HẠ TẦNG

| STT | Nhóm       | Tính năng               | Mô tả                                                                 | Kết quả   | Ghi chú                   |
| --- | ---------- | ----------------------- | --------------------------------------------------------------------- | --------- | ------------------------- |
| 1   | PostgreSQL | Database chính          | PostgreSQL 16, lưu toàn bộ data hệ thống                              | OK        | 32 tables (OW) + 6 (MW)   |
| 2   |            | PGVector extension      | Vector similarity search cho RAG, HNSW index                          | OK        | v0.8.0                    |
| 3   |            | Persistent storage      | Docker volume `postgres_data` giữ data                                | OK        |                           |
| 4   | Docker     | 9 containers orchestra  | PostgreSQL + LiteLLM + MW + WebUI + SearXNG + Redis + Nginx + Docling | OK        | `docker compose up -d`    |
| 5   |            | Health checks           | Tự kiểm tra sức khoẻ, restart nếu lỗi                                 | OK        | `restart: unless-stopped` |
| 6   |            | Auto-restart            | Container tự restart khi server reboot                                | OK        |                           |
| 7   | Backup     | Manual backup           | `pg_dump` full database                                               | Chưa test | Cần chạy thủ công         |
| 8   | Network    | Internal Docker network | Giao tiếp qua mạng Docker riêng, nội bộ                               | OK        | `openwebui-network`       |
| 9   | Firewall   | Port 3000 (Nginx HTTPS) | Đã mở firewall, truy cập qua Nginx                                    | OK        |                           |
| 10  |            | Port 5000 (ĐÓNG)        | Không expose ra ngoài, chỉ truy cập nội bộ                            | OK        | Truy cập qua Nginx :3000  |

---

## X. TÍNH NĂNG DÀNH CHO NGƯỜI DÙNG (END-USER)

| STT | Nhóm         | Tính năng                | Mô tả                                         | Kết quả   | Ghi chú                   |
| --- | ------------ | ------------------------ | --------------------------------------------- | --------- | ------------------------- |
| 1   | Giao diện    | Giao diện web responsive | Hỗ trợ desktop và mobile qua trình duyệt      | OK        |                           |
| 2   |              | Dark mode / Light mode   | Chuyển đổi giao diện sáng/tối                 | OK        | Settings → Theme          |
| 3   |              | Đa ngôn ngữ              | Tiếng Việt, tiếng Anh, và nhiều ngôn ngữ khác | OK        | Settings → Language       |
| 4   | Cá nhân hoá  | Chọn model mặc định      | User chọn model ưa thích làm mặc định         | OK        | Settings → Default Model  |
| 5   |              | System prompt cá nhân    | User tự đặt system prompt riêng               | OK        | Settings → System Prompt  |
| 6   |              | Memory (AI nhớ user)     | AI lưu thông tin user để cá nhân hoá trả lời  | OK        | Lưu trong table `memory`  |
| 7   | Tìm kiếm     | Tìm trong lịch sử chat   | Tìm keyword trong tiêu đề hoặc nội dung       | OK        | Thanh search trên sidebar |
| 8   | Chia sẻ      | Chia sẻ hội thoại        | Tạo link chia sẻ cho người khác xem           | OK        | Share icon → Copy link    |
| 9   | Xuất dữ liệu | Export chat history      | Xuất lịch sử chat thành file                  | OK        |                           |
| 10  |              | Xuất Excel/PDF/DOCX      | Dùng custom tools để xuất có format           | OK        | Action → Xuất Excel/PDF   |
| 11  | Prompt       | Saved Prompts            | Lưu prompt hay dùng để tái sử dụng            | Chưa test | Hạ tầng sẵn               |
| 12  |              | Prompt suggestions       | Gợi ý câu hỏi khi mở chat mới                 | OK        | Cấu hình qua Admin        |

---

## XI. TÍNH NĂNG DÀNH CHO ADMIN

| STT | Nhóm tính năng    | Tính năng cụ thể           | Hướng dẫn sử dụng / Mô tả                     | Câu lệnh ví dụ                          | Trạng thái | Kết quả | Ghi chú        |
| --- | ----------------- | -------------------------- | --------------------------------------------- | --------------------------------------- | ---------- | ------- | -------------- |
| 1   | Quản lý User      | Danh sách user             | Xem tất cả users, role, trạng thái            | Admin Panel → Users                     | Đã có      | OK      |                |
| 2   |                   | Duyệt user mới             | Approve/Reject user pending                   | —                                       | Đã có      | OK      |                |
| 3   |                   | Đổi role user              | Thăng/hạ quyền (Admin ↔ User)                 | —                                       | Đã có      | OK      |                |
| 4   |                   | Xoá user                   | Xoá tài khoản user                            | —                                       | Đã có      | OK      |                |
| 5   | Quản lý Model     | Bật/tắt model              | Enable/disable model cho users                | Admin → Models                          | Đã có      | OK      |                |
| 6   |                   | Cấu hình model params      | Set temperature, top_p, max_tokens mặc định   | —                                       | Đã có      | OK      |                |
| 7   |                   | Gán Knowledge vào model    | Model tự động dùng Knowledge cụ thể           | —                                       | Đã có      | OK      |                |
| 8   | Quản lý Knowledge | Xem tất cả Knowledge       | Liệt kê toàn bộ Knowledge Collections         | Admin → Knowledge                       | Đã có      | OK      |                |
| 9   |                   | Xoá Knowledge              | Xoá collection + toàn bộ embeddings           | —                                       | Đã có      | OK      | CASCADE delete |
| 10  | Cấu hình RAG      | Điều chỉnh chunk size      | Thay đổi kích thước chunk khi embed           | ENV: `CHUNK_SIZE=1000`                  | Đã có      | OK      |                |
| 11  |                   | Điều chỉnh file size limit | Giới hạn dung lượng file upload               | ENV: `RAG_FILE_MAX_SIZE=50`             | Đã có      | OK      | Hiện 50 MB     |
| 12  |                   | Đổi embedding model        | Chuyển đổi giữa local / OpenAI embeddings     | ENV: `RAG_EMBEDDING_MODEL=...`          | Đã có      | OK      |                |
| 13  | Cấu hình hệ thống | WebUI settings             | Cấu hình: signup, default model, banner, v.v. | Admin → Settings → General              | Đã có      | OK      |                |
| 14  |                   | Connections                | Cấu hình kết nối đến LLM providers            | Admin → Settings → Connections          | Đã có      | OK      |                |
| 15  | Giám sát          | Request logs               | Xem log chi tiết từng API request             | Dashboard → Logs tab (DB: mw_audit_log) | Đã có      | OK      |                |
| 16  |                   | Application logs           | Xem lỗi, warning, events                      | `logs/middleware.log`                   | Đã có      | OK      |                |
| 17  |                   | Cost dashboard             | Báo cáo chi phí theo user/model/thời gian     | `http://<server>:5000/dashboard`        | Đã có      | OK      |                |

---

## XII. TÍNH NĂNG CHƯA TRIỂN KHAI (KẾ HOẠCH)

| STT | Nhóm tính năng    | Tính năng cụ thể               | Hướng dẫn sử dụng / Mô tả             | Trạng thái | Ghi chú                          |
| --- | ----------------- | ------------------------------ | ------------------------------------- | ---------- | -------------------------------- |
| 1   | Nhóm người dùng   | Đồng bộ thành viên group từ HR | Tự lấy danh sách nhân sự → gán group  | Chưa có    | Group đã có (mục I); còn gán tay  |
| 11  | Tool thiết kế     | Tích hợp Canva / Figma         | Trợ lý tạo/sửa thiết kế cho Marketing | Chưa có    | Chờ công ty mua license           |
| 2   | Backup tự động    | Scheduled backup database      | Cron job chạy pg_dump hàng ngày       | Chưa có    | Cần cài đặt                      |
| 3   | Monitoring        | Uptime monitoring + alerting   | Prometheus + Grafana hoặc tương đương | Chưa có    |                                  |
| 4   | SSO/LDAP          | Đăng nhập bằng AD nội bộ       | Tích hợp Active Directory             | Chưa có    | Open WebUI hỗ trợ sẵn            |
| 5   | Mobile app        | Ứng dụng mobile native         | iOS/Android app                       | Chưa có    | Web responsive đã hỗ trợ         |
| 6   | API integration   | Tích hợp DMS, ERP              | Kết nối với hệ thống nội bộ khác      | Chưa có    | Middleware API sẵn sàng          |
| 7   | Scheduled reports | Báo cáo chi phí tự động        | Email/Zalo báo cáo chi phí hàng tuần  | Chưa có    |                                  |
| 8   | Fine-tuning       | Huấn luyện model riêng         | Train model trên dữ liệu nội bộ       | Chưa có    | Cần GPU                          |
| 9   | On-premise LLM    | Chạy AI local (Llama, Mistral) | Không phụ thuộc API bên ngoài         | Chưa có    | Cần GPU mạnh                     |
| 10  | Web crawling      | Crawl dữ liệu từ web           | Tự động fetch và index dữ liệu web    | Chưa có    | Open WebUI hỗ trợ sẵn URL import |

---

## Tổng kết

| STT | Nhóm                    | Số tính năng đã có | Chưa có / Kế hoạch |
| --- | ----------------------- | ------------------ | ------------------ |
| 01  | I. Phân quyền & Quản lý | 9                  | 1 (Groups)         |
| 02  | II. Chat AI             | 22                 | —                  |
| 03  | III. Tạo ảnh AI         | 3                  | —                  |
| 04  | IV. Giọng nói           | 3                  | —                  |
| 05  | V. RAG / Knowledge      | 19                 | —                  |
| 06  | VI. Custom Tools        | 8                  | —                  |
| 07  | **VII. Web Search**     | **6**              | —                  |
| 08  | VIII. Chi phí & Quota   | 7                  | —                  |
| 09  | IX. Database & Hạ tầng  | 10                 | 1 (Auto backup)    |
| 10  | X. Tính năng End-user   | 12                 | —                  |
| 11  | XI. Tính năng Admin     | 17                 | —                  |
| 12  | XII. Kế hoạch tương lai | —                  | 10                 |
| 13  | **Tổng**                | **116**            | **12**             |

> **116 tính năng đã hoạt động** / 12 tính năng trong kế hoạch phát triển.
