# RAG (Retrieval-Augmented Generation) - Kiến trúc chi tiết

> **Hệ thống**: Open WebUI + PostgreSQL + PGVector + LLM Middleware  
> **Cập nhật**: 2026-04-06

---

## 1. Tổng quan

RAG (Retrieval-Augmented Generation) là kỹ thuật cho phép LLM trả lời dựa trên dữ liệu ngoài (documents, files) thay vì chỉ dựa vào training data. Hệ thống của chúng ta triển khai RAG thông qua Open WebUI tích hợp PGVector.

### 1.1. Luồng hoạt động tổng quát

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INDEXING PHASE                               │
│                                                                     │
│  User Upload File → Extract Text → Split Chunks → Embedding →       │
│  Store in PGVector (document_chunk table)                           │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        RETRIEVAL PHASE                              │
│                                                                     │
│  User Query → Embedding Query → Vector Search (cosine similarity)   │
│  → Top-K Chunks → Inject vào Prompt → LLM Generate Response         │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2. Các thành phần chính

| STT | Thành phần      | Technology                                                       | Vai trò                                                         |
| --- | --------------- | ---------------------------------------------------------------- | --------------------------------------------------------------- |
| 01  | Vector DB       | PostgreSQL + PGVector 0.8.0                                      | Lưu trữ và tìm kiếm vector embeddings                           |
| 02  | Embedding Model | `gemini-embedding-001` (qua Middleware)                          | Chuyển text thành vector 1536 chiều (giảm từ 3072)              |
| 03  | Text Splitter   | Character-based splitter                                         | Chia document thành chunks                                      |
| 04  | OCR Engine      | Docling (`quay.io/docling-project/docling-serve-cpu`, port 5001) | Extract text từ PDF scan, Word, hình ảnh                        |
| 05  | Search          | Hybrid (BM25 + Vector)                                           | Kết hợp keyword search + semantic search                        |
| 06  | Index           | HNSW (Hierarchical Navigable Small World)                        | Tìm kiếm approximate nearest neighbors                          |

> [!IMPORTANT]
> **Cơ chế Embedding qua Cloud API**: Quá trình tạo vector embeddings cho tài liệu (RAG) **không thực hiện tại chỗ (local)**. Thay vào đó, văn bản trích xuất được gửi qua Middleware đến Gemini API (Cloud) dưới sự kiểm soát chặt chẽ của Middleware (giúp thực hiện giám sát hạn ngạch - quota control, ghi nhật ký kiểm toán - audit logs, và mã hóa dữ liệu truyền tải). Bản thân các vector embeddings kết quả được đưa trở lại lưu trữ hoàn toàn on-premise trong cơ sở dữ liệu PostgreSQL + PGVector cục bộ.

---

## 2. Chi tiết kỹ thuật

### 2.1. Cấu hình hiện tại (docker-compose.yml)

```yaml
# RAG Configuration
ENABLE_RAG: true
CHUNK_SIZE: 1500                    # Mỗi chunk tối đa 1500 ký tự
CHUNK_OVERLAP: 100                  # Overlap 100 ký tự giữa các chunks
RAG_TEXT_SPLITTER: character        # Chia theo ký tự (không theo token)
ENABLE_RAG_HYBRID_SEARCH: true      # BM25 + Vector search
RAG_FILE_MAX_SIZE: 2048             # Tối đa 2048 MB / file
RAG_FILE_MAX_COUNT: 20              # Tối đa 20 files / lần upload
RAG_EMBEDDING_BATCH_SIZE: 50        # Batch 50 chunks mỗi lần gọi API

# Embedding (qua Middleware → LiteLLM → Gemini API)
RAG_EMBEDDING_ENGINE: openai
RAG_EMBEDDING_MODEL: gemini-embedding-001
RAG_EMBEDDING_OPENAI_API_BASE_URL: http://middleware:5000/v1
RAG_EMBEDDING_OPENAI_API_KEY: ${SUBKEY_ADMIN}

# Vector Database
VECTOR_DB: pgvector
PGVECTOR_DB_URL: postgresql://openwebui_user:***@postgres:5432/openwebui
PGVECTOR_CREATE_EXTENSION: true
PGVECTOR_INDEX_METHOD: hnsw
```

### 2.2. Indexing Pipeline (Upload File → Lưu Vector)

#### Bước 1: Extract Text
Open WebUI hỗ trợ nhiều format:
- **PDF**: PyPDF2 / Docling (hiện tại) / Mistral OCR
- **Word** (.docx): python-docx
- **Excel** (.xlsx): openpyxl
- **Text** (.txt, .csv, .md): đọc trực tiếp
- **HTML**: BeautifulSoup

#### Bước 2: Text Splitting (Chunking)

```python
# Character-based splitting (cấu hình hiện tại)
chunk_size = 1500       # Mỗi chunk ≤ 1500 ký tự
chunk_overlap = 100     # Overlap 100 ký tự để giữ context

# Ví dụ: document 4000 ký tự → 3 chunks
# Chunk 1: char 0-1499
# Chunk 2: char 1400-2899   (overlap 100 từ chunk 1)
# Chunk 3: char 2800-3999   (overlap 100 từ chunk 2)
```

**Tại sao overlap?** Để tránh mất context tại ranh giới chunk. Một câu bị cắt giữa chừng sẽ xuất hiện đầy đủ trong chunk kế tiếp.

#### Bước 3: Embedding (Text → Vector)

```
Model: gemini-embedding-001 (qua Middleware → LiteLLM → Gemini API)
├── Native dimension: 3072 vectors
├── Middleware inject: dimensions=1536 (giảm để khớp PGVector HNSW max 2000)
├── Thực tế lưu: 1536-dim vectors trong DB
├── Chi phí: $0.15 / 1M tokens (Gemini API)
├── Tốc độ: phụ thuộc network + Gemini API latency
├── Hỗ trợ: 100+ ngôn ngữ, tiếng Việt tốt
└── Luồng: Open WebUI → Middleware (inject dims) → LiteLLM → Gemini API
```

> ⚠️ **Lưu ý quan trọng**: Middleware tự động inject `dimensions=1536` vào mọi embedding request. Gemini native output 3072-dim nhưng PGVector HNSW chỉ hỗ trợ tối đa 2000 dims. Dimension reduction qua API param đảm bảo tương thích với DB schema `vector(1536)`.

#### Bước 4: Lưu vào PGVector

Mỗi chunk được lưu vào table `document_chunk`:

```sql
Table "public.document_chunk"
     Column      |     Type     | Nullable
-----------------+--------------+----------
 id              | text         | NOT NULL   -- UUID unique
 vector          | vector(1536) |            -- Vector embedding
 collection_name | text         | NOT NULL   -- Thuộc collection nào
 text            | text         |            -- Nội dung text gốc
 vmetadata       | jsonb        |            -- Metadata (source, page, etc.)

Indexes:
  "document_chunk_pkey" PRIMARY KEY, btree (id)
  "idx_document_chunk_collection_name" btree (collection_name)
  "idx_document_chunk_vector" hnsw (vector vector_cosine_ops)
    WITH (m='16', ef_construction='64')
```

### 2.3. HNSW Index - Giải thích kỹ thuật

HNSW (Hierarchical Navigable Small World) là thuật toán ANN (Approximate Nearest Neighbor) cho phép tìm kiếm vector tương tự rất nhanh.

```
Cấu hình hiện tại:
├── Distance metric: cosine similarity (vector_cosine_ops)
├── m = 16         → Mỗi node kết nối tối đa 16 neighbors
├── ef_construction = 64  → Số candidates khi build index
│
├── Trade-offs:
│   ├── m cao hơn → recall tốt hơn, nhưng tốn RAM + build chậm hơn
│   └── ef_construction cao → build index chậm, nhưng tìm kiếm chính xác hơn
│
└── Hiệu năng:
    ├── Build time: O(N × log(N))
    ├── Search time: O(log(N))  ← RẤT NHANH, kể cả triệu vectors
    └── RAM: ~1.5x kích thước raw vectors
```

### 2.4. Retrieval Pipeline (Query → Relevant Chunks)

#### Hybrid Search (BM25 + Vector)

```
User Query: "Chính sách bảo mật dữ liệu khách hàng"
                │
    ┌───────────┴───────────┐
    │                       │
    ▼                       ▼
BM25 Search             Vector Search
(keyword matching)      (semantic similarity)
    │                       │
    │ Results ranked        │ Results ranked
    │ by term frequency     │ by cosine similarity
    │                       │
    └───────────┬───────────┘
                │
                ▼
        Reciprocal Rank Fusion (RRF)
        (kết hợp 2 ranked lists)
                │
                ▼
        Top-K chunks (mặc định K=4)
                │
                ▼
        Inject vào System Prompt
                │
                ▼
        LLM generates response
        (with citations)
```

**BM25**: Tìm chính xác theo keyword. Tốt cho tên riêng, mã số, thuật ngữ chuyên ngành.  
**Vector Search**: Tìm theo nghĩa (semantic). Tốt cho câu hỏi khái quát, paraphrase.  
**Hybrid**: Kết hợp cả hai → recall tốt nhất.

### 2.5. Prompt Injection

Khi tìm được relevant chunks, Open WebUI inject vào prompt dạng:

```
### Context from uploaded documents:

[Source: document_name.pdf, Page 5]
<nội dung chunk 1>

[Source: document_name.pdf, Page 12]
<nội dung chunk 2>

---
Based on the above context, answer the following question:
<user's question>
```

---

## 3. Cách sử dụng RAG

### 3.1. Tạo Knowledge Collection

1. Vào **Workspace** → **Knowledge** → **Create Knowledge**
2. Đặt tên collection (VD: "Tài liệu nội bộ")
3. Upload files (PDF, DOCX, TXT, CSV, MD, HTML)
4. Chờ hệ thống xử lý (extract → chunk → embed → store)

### 3.2. Sử dụng trong Chat

- **Cách 1**: Attach file trực tiếp trong chat (icon 📎)
- **Cách 2**: Gõ `#` trong chat để chọn Knowledge Collection
- **Cách 3**: Gán Knowledge Collection vào model cụ thể (Admin Settings)

### 3.3. Ví dụ thực tế

```
User: #tài-liệu-nội-bộ Chính sách nghỉ phép của công ty là gì?

System: [Tìm kiếm trong knowledge "tài-liệu-nội-bộ"]
         → Tìm thấy 3 chunks relevant
         → Inject vào prompt

LLM: Theo tài liệu nội bộ (nguồn: HR_Policy.pdf, trang 15),
     chính sách nghỉ phép của công ty bao gồm:
     - Phép năm: 12 ngày/năm
     - Phép ốm: 30 ngày/năm
     [Citation: HR_Policy.pdf]
```

---

## 4. Giới hạn và Khả năng

### 4.1. Giới hạn cấu hình hiện tại

| STT | Thông số                     | Giá trị                              | Ghi chú                                  |
| --- | ---------------------------- | ------------------------------------ | ---------------------------------------- |
| 01  | File size tối đa             | **2048 MB**                          | `RAG_FILE_MAX_SIZE=2048`                 |
| 02  | Số files / lần upload        | **20 files**                         | `RAG_FILE_MAX_COUNT=20`                  |
| 03  | Chunk size                   | 1500 ký tự                           | ~225-300 từ tiếng Việt                   |
| 04  | Chunk overlap                | 100 ký tự                            | ~15-20 từ overlap                        |
| 05  | Embedding dimension          | 1536 (Gemini, giảm từ native 3072)   | `dimensions: 1536` inject bởi middleware |
| 06  | Max input tokens (embedding) | 2048 tokens                          | Gemini embedding-001 hỗ trợ 2048 tokens  |

### 4.2. Ví dụ: Upload văn bản 100 trang

```
Tình huống: File PDF 100 trang, ~50,000 từ (~250,000 ký tự)

Bước 1. Extract text:
   - 250,000 ký tự extracted
   - Thời gian: 5-30 giây (tùy PDF format, có hình/bảng không)

Bước 2. Chunking:
   - chunk_size = 1500, overlap = 100
   - Số chunks ≈ 250,000 / (1500 - 100) = ~179 chunks

Bước 3. Embedding:
   - 179 chunks × 1536 dimensions × 4 bytes = ~1.1 MB vectors
   - Thời gian: 5-15 giây (Gemini API, batch_size=50)

Bước 4. Lưu DB:
   - 313 rows trong document_chunk
   - Storage: ~2-5 MB (text + vectors + metadata + indexes)

Kết luận: ✅ HOÀN TOÀN KHẢ THI
Thời gian xử lý: ~30-60 giây tổng cộng
```

### 4.3. Ví dụ: Upload file 100 MB

```
Tình huống: File PDF 100 MB

✅ CÓ THỂ LOAD với cấu hình hiện tại
   - RAG_FILE_MAX_SIZE = 2048 MB → đủ

Lưu ý khi xử lý file lớn:
1. Docling có thể mất 2-5 phút extract text
2. Embedding qua Gemini API batch_size=50, có thể mất 1-2 phút
3. Nginx proxy_read_timeout cần đủ lớn (đã cấu hình 300s)

Ước tính nếu được phép upload:
   - File PDF 100 MB có thể chứa ~500,000-2,000,000 ký tự
   - Số chunks: 2,000,000 / 800 = ~2,500 chunks
   - Embedding time: ~3-10 giây
   - Storage: ~15-30 MB trong DB
   - ✅ Về kỹ thuật khả thi nhưng cần tăng config
```

### 4.4. Giới hạn thực tế và khuyến nghị

| STT | Tình huống      | Khả thi?       | Ghi chú                                   |
| --- | --------------- | -------------- | ----------------------------------------- |
| 01  | PDF 10 trang    | ✅ Tốt         | Xử lý < 10 giây                           |
| 02  | PDF 100 trang   | ✅ Tốt         | Xử lý < 1 phút                            |
| 03  | PDF 500 trang   | ✅ Khả thi     | Xử lý 2-5 phút                            |
| 04  | PDF 1000+ trang | ⚠️ Cần monitor | Có thể timeout, cần tăng config           |
| 05  | File > 100 MB   | ✅ Khả thi     | RAG_FILE_MAX_SIZE=2048, Docling xử lý OK  |
| 06  | File > 1 GB     | ⚠️ Cần tuning  | Tăng timeout, monitor Docling RAM         |
| 07  | 100 files nhỏ   | ✅ Khả thi     | Upload theo batch 20 files                |
| 08  | Tiếng Việt      | ✅ Tốt         | `gemini-embedding-001` hỗ trợ đa ngôn ngữ |

### 4.5. Cấu hình embedding hiện tại (đã tối ưu cho tiếng Việt)

```yaml
# Đang sử dụng Gemini Embedding qua Middleware → LiteLLM → Google API
RAG_EMBEDDING_ENGINE: openai
RAG_EMBEDDING_MODEL: gemini-embedding-001
RAG_EMBEDDING_OPENAI_API_BASE_URL: http://middleware:5000/v1
# → Native 3072 dimensions, giảm xuống 1536 qua middleware inject `dimensions: 1536`
# → Hỗ trợ đa ngôn ngữ tốt (bao gồm tiếng Việt)
# → Chi phí: $0.15 / 1M input tokens
```

> ⚠️ **Lưu ý bảo mật**: Text chunks được gửi tới Google Gemini API để chuyển thành vectors.
> Vectors được lưu on-premise trong PGVector. Nội dung text gốc KHÔNG lưu trên Google.

---

## 5. Luồng dữ liệu (Data Flow)

```
┌──────────────────────────────────────────────────────────────┐
│                    USER UPLOADS FILE                         │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────┐     ┌──────────────────────┐
│   file table         │     │   document table     │
│   (metadata, path)   │────▶│   (collection_name,  │
│   id, filename,      │     │    title, content)   │
│   meta (JSON)        │     └──────────────────────┘
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐     ┌──────────────────────────────┐
│  knowledge_file      │     │   document_chunk             │
│  (links file to      │     │   id, vector(1536),          │
│   knowledge)         │     │   collection_name,           │
│  knowledge_id,       │     │   text, vmetadata (JSONB)    │
│  file_id             │     │                              │
└──────────────────────┘     │   HNSW Index on vector       │
                             └──────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    USER ASKS QUESTION                        │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│  1. Embed query → vector(1536)                               │
│  2. SELECT * FROM document_chunk                             │
│     WHERE collection_name = ?                                │
│     ORDER BY vector <=> query_vector                         │
│     LIMIT 4;                                                 │
│  3. BM25 search trên text column (nếu hybrid search ON)      │
│  4. Merge results (RRF)                                      │
│  5. Inject top-K chunks vào prompt                           │
│  6. LLM generates answer                                     │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. Đầu vào / Đầu ra

### Đầu vào (Input)
- **Files**: PDF, DOCX, TXT, CSV, MD, HTML, Excel
- **Web URLs**: Copy-paste URL, hệ thống fetch + extract
- **YouTube**: Paste URL, extract transcript
- **Raw text**: Paste trực tiếp vào chat

### Đầu ra (Output)
- **Chat response**: LLM trả lời dựa trên context từ documents
- **Citations**: Trích dẫn nguồn (tên file, trang, đoạn text)
- **Relevance scores**: Confidence score cho mỗi retrieved chunk

---

## 7. Security & Access Control

- Mỗi Knowledge Collection có `access_control` (JSON)
- Chỉ owner hoặc user được grant mới truy cập được
- Files được lưu trong Docker volume `openwebui_data`
- Vector data trong PostgreSQL volume `postgres_data`
- Middleware kiểm soát API access qua `SUBKEY_ADMIN`

---

## 8. Tóm tắt kiến trúc

```
             Browser (localhost:3000)
                 │
                 ▼
          ┌──────────────┐
          │  Open WebUI  │────── openwebui_data volume
          │  (port 8080) │       (files, uploads)
          └──────┬───────┘
                 │
        ┌────────┼────────┬─────────┐
        │        │        │         │
        ▼        ▼        ▼         ▼
  ┌──────────┐ ┌────────┐ ┌────────┐ ┌───────────┐
  │PostgreSQL│ │Docling │ │ Embed  │ │Middleware │
  │+ PGVector│ │ (OCR)  │ │Request │ │(port 5000)│
  │(port 5432│ │(p.5001)│ │  ──────┼─┤inject dims│
  └──────────┘ └────────┘ └────────┘ └─────┬─────┘
                                           │
                                     ┌──────────┐
                                     │ LiteLLM  │
                                     │(port 4000)│
                                     └──────────┘
                                           │
                               ┌───────────┼───────────┐
                               ▼           ▼           ▼
                         OpenAI API   Gemini API   Other APIs
                                    (embedding +
                                     chat models)
```
