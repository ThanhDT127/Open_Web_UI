# 📘 HƯỚNG DẪN SỬ DỤNG - OPEN WEBUI STACK

> **Phiên bản:** 4.0 | **Cập nhật:** 11/05/2026

Tài liệu hướng dẫn sử dụng hệ thống Open WebUI với Middleware, bao gồm kiến trúc, RAG, tạo ảnh, quản lý user, và troubleshooting.

---

## 📋 Mục Lục

1. [Tổng Quan Hệ Thống](#1-tổng-quan-hệ-thống)
2. [Các Model Hỗ Trợ](#2-các-model-hỗ-trợ)
3. [Sử Dụng RAG](#3-sử-dụng-rag)
4. [Tạo Ảnh (Image Generation)](#4-tạo-ảnh-image-generation)
5. [Quản Lý Quota & Chi Phí](#5-quản-lý-quota--chi-phí)
6. [Quản Lý User & Subkey](#6-quản-lý-user--subkey)
7. [Xuất File (Export Tool)](#7-xuất-file-export-tool)
8. [Kết Nối Tài Khoản Cá Nhân](#8-kết-nối-tài-khoản-cá-nhân)
9. [Trợ Lý Phòng Ban](#9-trợ-lý-phòng-ban)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Tổng Quan Hệ Thống

### 1.1 Kiến Trúc 3-Tier

```
┌─────────────────────────────────────────────────────────────────┐
│                         NGƯỜI DÙNG                              │
└─────────────────────────┬───────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 0: Nginx (:3000 HTTPS) — Entry point duy nhất             │
│  TLS 1.2/1.3 | Rate limit | Gzip                                │
└─────────────────────────┬───────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 1: Open WebUI (:8080, qua Nginx)                          │
│  - Giao diện chat đa phương thức                                │
│  - Quản lý Knowledge Base & RAG                                 │
└─────────────────────────┬───────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 2: Middleware (Port 5000)                                 │
│  - Xác thực subkey                                              │
│  - Quản lý quota & cost                                         │
│  - Audit logging                                                │
└─────────────────────────┬───────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 3: LiteLLM (Port 4000) + PostgreSQL (Port 5432)           │
│  - Model routing (OpenAI, Gemini, xAI, Anthropic)               │
│  - Vector embeddings (PGVector)                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Docker Services

| STT | Service        | Port | Chức Năng                          |
| --- | -------------- | ---- | ---------------------------------- |
| 01  | **Nginx**      | 3000 | Reverse proxy, HTTPS, load balance |
| 02  | **Open WebUI** | 8080 | Giao diện người dùng (internal)    |
| 03  | **Middleware** | 5000 | Xác thực + Quota (internal)        |
| 04  | **LiteLLM**    | 4000 | LLM Proxy (internal)               |
| 05  | **PostgreSQL** | 5432 | Database + Vector DB (internal)    |
| 06  | **Docling**    | 5001 | OCR / Document extraction          |
| 07  | **SearXNG**    | 8080 | Web search engine (internal)       |
| 08  | **Redis**      | 6379 | Cache + SearXNG limiter            |

---

## 2. Các Model Hỗ Trợ

### Quy Ước Đặt Tên

| STT | Prefix  | Chức Năng                              |
| --- | ------- | -------------------------------------- |
| 01  | `chat-` | **Chat AI** - Hỏi đáp text + vision    |
| 02  | `img-`  | **Image Generation** - Tạo ảnh từ text |

### Danh Sách Model

#### Chat AI (14 models – 5 providers)
| STT | Model                                | Provider  | Ghi Chú                       |
| --- | ------------------------------------ | --------- | ----------------------------- |
| 01  | `chat-gpt-5.4`                       | OpenAI    | Flagship, reasoning mạnh nhất |
| 02  | `chat-gpt-5.2`                       | OpenAI    | Cân bằng                      |
| 03  | `chat-gpt-5`                         | OpenAI    | Tiêu chuẩn                    |
| 04  | `chat-gemini-3.1-pro-preview`        | Google    | Flagship Google, reasoning    |
| 05  | `chat-gemini-3.1-flash-lite-preview` | Google    | Nhanh, chi phí thấp           |
| 06  | `chat-gemini-2.5-flash`              | Google    | Cân bằng, tiếng Việt tốt      |
| 07  | `chat-grok-4.20`                     | xAI       | Reasoning mạnh                |
| 08  | `chat-grok-4.1-fast`                 | xAI       | Nhanh, reasoning              |
| 09  | `chat-grok-4.1-fast-lite`            | xAI       | Nhanh nhất, rẻ                |
| 10  | `chat-claude-opus-4.6`               | Anthropic | Flagship, phân tích sâu       |
| 11  | `chat-claude-sonnet-4.6`             | Anthropic | Cân bằng                      |
| 12  | `chat-claude-haiku-4.5`              | Anthropic | Nhanh, tiết kiệm              |
| 13  | `chat-deepseek-v4-pro`               | DeepSeek  | Reasoning mạnh, 1M context    |
| 14  | `chat-deepseek-v4-flash`             | DeepSeek  | Nhanh nhất, rẻ nhất fleet     |

#### Image Generation (6 models)
| STT | Model                  | Provider | Ghi Chú                       |
| --- | ---------------------- | -------- | ----------------------------- |
| 01  | `img-gpt-1.5`          | OpenAI   | Mới nhất, 4x nhanh hơn        |
| 02  | `img-gpt-1`            | OpenAI   | Chất lượng cao                |
| 03  | `img-gemini-3.1-flash` | Google   | Nhanh, chi phí thấp           |
| 04  | `img-gemini-3-pro`     | Google   | Chất lượng cao                |
| 05  | `img-grok-imagine`     | xAI      | Tiêu chuẩn                    |
| 06  | `img-grok-imagine-pro` | xAI      | ✅ Khuyến nghị, chất lượng cao |

#### Smart Routing — Auto Models (5 models)

| STT | Model ID        | Tên Hiển Thị     | Mô Tả                                            |
| --- | --------------- | ---------------- | ------------------------------------------------- |
| 01  | `openai-auto`   | ChatGPT (Auto)   | Tự chọn GPT-5 / 5.2 / 5.4 theo độ phức tạp       |
| 02  | `gemini-auto`   | Gemini (Auto)    | Tự chọn 2.5-flash / 3.1-flash-lite / 3.1-pro      |
| 03  | `grok-auto`     | Grok (Auto)      | Tự chọn 4.1-fast-lite / 4.1-fast / 4.20           |
| 04  | `claude-auto`   | Claude (Auto)    | Tự chọn haiku / sonnet / opus                      |
| 05  | `deepseek-auto` | DeepSeek (Auto)  | Tự chọn v4-flash / v4-pro                          |

> 💡 **Cách hoạt động:** Smart Routing phân tích độ phức tạp câu hỏi (độ dài, từ khóa, số lượt chat, file đính kèm) để chọn model phù hợp nhất. Khi quota đạt ≥60%, hệ thống tự động chuyển sang model tiết kiệm nhất.

---

## 3. Sử Dụng RAG

### 3.1 RAG Là Gì?

**RAG = Retrieval-Augmented Generation**

Cho phép AI truy xuất thông tin từ tài liệu của bạn để trả lời câu hỏi.

```
Câu hỏi → Tìm chunks liên quan → Ghép vào context → LLM trả lời
```

### 3.2 Cách Sử Dụng

#### Cách 1: Gắn Knowledge Base vào Model (Khuyến nghị)

1. **Workspace** → **Models** → Click **[+]**
2. Điền:
   - **Name**: Tên model (vd: "Tài Liệu Dự Án")
   - **Base Model**: `chat-gemini-2.5-flash`
   - **Knowledge**: Chọn KB của bạn
3. **Save**
4. Chat với model này → AI tự động tìm trong KB

#### Cách 2: Dùng # trong Chat

```
# Truy vấn file cụ thể
#my_document.pdf Tóm tắt nội dung chính

# Truy vấn Knowledge Base
#TenKnowledgeBase Giải thích về kiến trúc

# Truy vấn URL (real-time)
#https://example.com Tóm tắt trang này
```

### 3.3 Cấu Hình RAG

**Admin Panel → Settings → Documents**

| STT | Tham Số       | Mặc Định | Mô Tả                   |
| --- | ------------- | -------- | ----------------------- |
| 01  | Top K         | 5        | Số chunks retrieve      |
| 02  | Chunk Size    | 1500     | Kích thước mỗi chunk    |
| 03  | Chunk Overlap | 100      | Độ chồng lấp            |
| 04  | Hybrid Search | On       | Vector + Keyword search |

---

## 4. Tạo Ảnh (Image Generation)

### 4.1 Cấu Hình

**Admin Settings → Images:**
- **Engine**: OpenAI
- **API Base URL**: `http://middleware:5000/v1`
- **API Key**: Subkey của bạn
- **Model**: `img-grok-imagine-pro` (khuyến nghị)

### 4.2 Test Tạo Ảnh

```bash
curl -X POST http://localhost:5000/v1/images/generations \
  -H "Authorization: Bearer YOUR_SUBKEY_ADMIN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "img-gemini-3.1-flash",
    "prompt": "A futuristic city at sunset",
    "size": "1024x1024"
  }'
```

### 4.3 Response

```json
{
  "data": [{"url": "http://localhost:5000/v1/_mw/media/abc123.png"}],
  "_mw_user": "admin",
  "_mw_added_cost_usd": 0.002
}
```

---

## 5. Quản Lý Quota & Chi Phí

### 5.1 Schema Quota

```json
{
  "user_id": "admin",
  "subkey": "YOUR_SUBKEY_ADMIN",
  "allowed_models": ["*"],
  "quota": {
    "period": "monthly",
    "limit_cost_usd": 50.0,
    "limit_image_requests": 100,
    "used_cost_usd": 5.25,
    "used_image_requests": 25
  }
}
```

### 5.2 Kiểm Tra Quota

```bash
curl -H "X-Admin-Key: admin_key" \
  http://localhost:5000/admin/usage | jq '.[] | select(.user_id=="admin")'
```

### 5.3 Reset Quota

```bash
curl -X POST -H "X-Admin-Key: admin_key" \
  http://localhost:5000/admin/reset \
  -d '{"user_id":"admin"}'
```

---

## 6. Quản Lý User & Subkey

### 6.1 Kiến Trúc — 2 Hệ Thống User

| STT | Hệ thống       | Database                       | Vai trò                              |
| --- | -------------- | ------------------------------ | ------------------------------------ |
| 01  | **Open WebUI** | `openwebui` → bảng `user`      | Đăng nhập web, phân quyền Admin/User |
| 02  | **Middleware** | `middleware` → bảng `mw_users` | Xác thực API, quản lý quota, subkey  |

> ⚠️ Hai hệ thống **độc lập** — user_id trong middleware không liên kết với user_id trong Open WebUI.

### 6.2 Quản Lý qua Dashboard (Giao Diện)

Truy cập: `https://openwebui.example.com:51122/dashboard` → Tab **Users**

| STT | Thao tác           | Cách làm                                           |
| --- | ------------------ | -------------------------------------------------- |
| 01  | **Tạo user**       | Nhấn ➕ Add User → Điền form → Create → Copy subkey |
| 02  | **Sửa user**       | Nhấn ✏️ → Sửa quota/model/role → Save              |
| 03  | **Xóa user**       | Nhấn 🗑️ → Confirm 2 lần                            |
| 04  | **Rotate key**     | Nhấn 🔑 → Confirm → Copy subkey mới                 |
| 05  | **Enable/Disable** | Nhấn 🔴/🟢 toggle                                    |

### 6.3 Subkey — Bảo Mật

- Subkey là **mã xác thực API** (dạng `sk_abc123...`)
- Mã hóa **HMAC-SHA256** — không thể dịch ngược
- Plaintext chỉ hiện **1 lần** khi tạo/rotate → phải copy ngay
- Dashboard chỉ hiện hash rút gọn (`abc...xyz`)

### 6.4 Quản Lý qua API

```bash
# Tạo user
curl -X POST http://localhost:5000/v1/_mw/admin/users \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "role": "user", "limit_cost_usd": 5.0}'

# Sửa user
curl -X PATCH http://localhost:5000/v1/_mw/admin/users/alice \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"limit_cost_usd": 10.0}'

# Xóa user
curl -X DELETE http://localhost:5000/v1/_mw/admin/users/alice \
  -H "X-Admin-Key: $ADMIN_KEY"

# Rotate key
curl -X POST http://localhost:5000/v1/_mw/admin/users/alice/rotate_key \
  -H "X-Admin-Key: $ADMIN_KEY"
```

---

## 7. Xuất File (Export Tool)

### 7.1 Các Định Dạng

| STT | Công cụ                | Mô Tả                                           |
| --- | ---------------------- | ----------------------------------------------- |
| 01  | **Xuất Excel** (.xlsx) | Trích xuất bảng biểu, auto-format số/ngày/tiền  |
| 02  | **Xuất PDF**           | Xuất hội thoại, hỗ trợ tiếng Việt (font DejaVu) |
| 03  | **Xuất Word** (.docx)  | Xuất hội thoại dạng Word                        |

### 7.2 Cách Sử Dụng

1. Mở chat → gõ gì đó để bot trả lời
2. Nhấn icon ⚡ (Action) bên dưới tin nhắn bot
3. Chọn **Xuất File**
4. Chọn format: 1=Excel, 2=PDF, 3=Word
5. File tự tải xuống

> 💡 Tool Excel tự nhận dạng: số, ngày tháng, %, tiền VNĐ/$/€ và format đúng.

---

## 8. Kết Nối Tài Khoản Cá Nhân

Các công cụ gửi mail Gmail, tra GitHub, đọc Google Drive đều chạy **dưới danh tính thật của bạn** — email bạn gửi đi hiện tên bạn và nằm trong hộp Sent của bạn, không phải một tài khoản dùng chung.

> Office 365 **không** nằm trong nhóm này: nó đang là bản chạy thử, không kết nối tài khoản Microsoft của bạn. Xem cảnh báo ở mục 9.

### 8.1 Cách kết nối

Bạn không cần vào trang cài đặt nào. Cứ yêu cầu trợ lý làm việc đó:

```
Gửi mail Gmail cho anh Nam về lịch họp sáng mai
```

Nếu bạn **chưa liên kết** tài khoản, trợ lý trả về một link kết nối:

> ⚠️ Tài khoản Google (Gmail) của bạn chưa được liên kết.
> 👉 **Kết nối tài khoản Google của bạn**

1. Bấm vào link → cửa sổ đăng nhập của Google/GitHub hiện ra
2. Đăng nhập và bấm **Đồng ý** (Allow) với các quyền được xin
3. Thấy màn hình "✓ Kết Nối Thành Công" → đóng cửa sổ, quay lại khung chat
4. Yêu cầu lại việc lúc nãy — lần này trợ lý làm được

Chỉ cần kết nối **một lần**; hệ thống tự gia hạn phiên. Link kết nối có hạn 10 phút và chỉ dùng được cho chính bạn.

### 8.2 Dịch vụ kết nối được

| Dịch vụ            | Trợ lý làm được gì                                             |
| ------------------ | -------------------------------------------------------------- |
| Microsoft 365      | Gửi/đọc mail Outlook, tạo/xem lịch, gửi tin Teams, đọc SharePoint |
| Gmail              | Gửi email                                                      |
| Google Drive       | Tìm và đọc nội dung file                                       |
| GitHub             | Xem repo, đọc issue/PR, tìm code                               |

### 8.3 Duyệt trước khi gửi

Với các hành động **gửi ra ngoài** (gửi mail, tạo lịch mời người khác, nhắn Teams), trợ lý **không tự làm ngay**. Một hộp thoại hiện ra cho bạn xem trước nội dung:

- Bấm **Duyệt** → hành động được thực hiện bằng tài khoản của bạn
- Bấm **Từ chối** → hủy bỏ, không có gì được gửi đi

Các hành động chỉ đọc (đọc mail, xem lịch, tìm file) chạy thẳng, không cần duyệt.

---

## 9. Công Cụ Theo Phòng Ban

Bạn chọn **model AI bất kỳ** (ChatGPT, Gemini, Claude…) rồi **tự bật công cụ** cần dùng trong khung chat. Danh sách công cụ hiện ra đã được lọc sẵn theo phòng ban của bạn — bạn chỉ thấy những công cụ mình được phép dùng.

**Dùng thế nào**: trong khung chat, mở menu công cụ (biểu tượng ➕ / Tools) → bật công cụ cần dùng → chat bình thường.

Công cụ được cấp theo phòng ban:

| Công cụ                     | Phòng ban được dùng          | Làm được gì                                     |
| --------------------------- | ---------------------------- | ----------------------------------------------- |
| **Office 365** ⚠️           | Mọi phòng ban                | **Đang là bản chạy thử — xem cảnh báo bên dưới** |
| **Gmail**                   | Mọi phòng ban                | Soạn/gửi mail Gmail                             |
| **Google Drive**            | Mọi phòng ban                | Tìm và đọc tài liệu trên Drive                  |
| **GitHub**                  | IT, Kỹ thuật/R&D             | Tra repo, issue, code                           |
| **Code Interpreter**        | IT, Kỹ thuật/R&D             | Viết & chạy code Python trong sandbox           |
| **Postgres / Playwright**   | IT, Kỹ thuật/R&D             | Truy vấn dữ liệu (chỉ đọc), tự động hóa trình duyệt |
| **Tìm kiếm web, Xuất file** | Mọi nhân viên                | Tìm thông tin, xuất PDF/Excel/Word              |

> ⚠️ **Office 365 đang là bản chạy thử — ĐỪNG tin kết quả của nó.** Nếu bạn nhờ trợ lý gửi mail Outlook, tạo lịch hay nhắn Teams, nó sẽ **báo là đã gửi thành công nhưng thực tế không gửi gì cả**. Đọc mail / tìm file SharePoint cũng chỉ trả về **dữ liệu mẫu bịa sẵn**, không phải hộp thư thật của bạn. Bản thật đang được xây, sẽ thông báo khi dùng được. Cần gửi mail thật thì dùng **Gmail**.

> 💡 Không thấy công cụ bạn cần? Liên hệ admin để được thêm vào group phòng ban tương ứng, hoặc xin cấp quyền riêng cho tài khoản của bạn.

---

## 10. Troubleshooting

### 10.1 Lỗi Thường Gặp

| STT | Lỗi                     | Nguyên Nhân                     | Giải Pháp                   |
| --- | ----------------------- | ------------------------------- | --------------------------- |
| 01  | 401 Missing sub-key     | Thiếu Authorization header      | Thêm `Bearer <subkey>`      |
| 02  | 403 Invalid sub-key     | Subkey sai hoặc user bị disable | Kiểm tra DB hoặc rotate key |
| 03  | 403 Model not allowed   | Model bị chặn                   | Thêm vào allowed_models     |
| 04  | 403 Quota exceeded      | Hết quota                       | Reset hoặc tăng limit       |
| 05  | 502 LiteLLM unavailable | LiteLLM chưa chạy               | Kiểm tra container          |

### 10.2 Kiểm Tra Service

```bash
# Health check
curl http://localhost:5000/health

# Kiểm tra logs
docker compose logs middleware --tail 50
docker compose logs litellm --tail 50

# Kiểm tra models
curl http://localhost:5000/v1/models \
  -H "Authorization: Bearer <subkey>"
```

### 10.3 RAG Không Hoạt Động

1. **Verify file đã index**: Workspace → Knowledge → Click KB
2. **Check embedding model**: `docker compose logs open-webui | grep embedding`
3. **Verify PGVector**: 
   ```bash
   docker exec openwebui-postgres psql -U openwebui_user -d openwebui \
     -c "SELECT COUNT(*) FROM document_chunk;"
   ```

---

## 📌 Quick Reference

### URLs

| STT | Service        | URL                                               |
| --- | -------------- | ------------------------------------------------- |
| 01  | Open WebUI     | https://openwebui.example.com:51122           |
| 02  | Dashboard      | https://openwebui.example.com:51122/dashboard |
| 03  | Middleware API | https://openwebui.example.com:51122/v1/_mw/   |
| 04  | LLM API        | https://openwebui.example.com:51122/v1/       |

### Commands

```bash
# Start stack
docker compose up -d

# Restart sau khi đổi config
docker compose down && docker compose up -d --build

# Xem logs
docker compose logs -f middleware
```

---

*Tài liệu gộp từ: TAI_LIEU_TONG_QUAN_DU_AN.md, HUONG_DAN_SU_DUNG_RAG.md, IMAGE_GENERATION.md, HUONG_DAN_IMAGE_GENERATION.md, HUONG_DAN_TRIEN_KHAI_EXPORT.md, huong-dan-thao-tac-he-thong.md*

