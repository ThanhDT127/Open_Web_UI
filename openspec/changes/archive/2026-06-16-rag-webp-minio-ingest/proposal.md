## Why

Hiện tại, hệ thống RAG xử lý hình ảnh qua cơ chế Base64 trung gian phức tạp và kém hiệu quả (Base64 Ping-Pong). Điều này làm phình to payload truyền tải nội bộ, ngốn RAM/CPU của Middleware khi phải decode Base64 và ghi tệp PNG đồng bộ ngay trên luồng chat (Query Path), tăng thời gian phản hồi (TTFT) của người dùng. Đồng thời, việc lưu trữ ảnh cục bộ trên container Middleware không thể mở rộng (scale-out) khi chạy cụm đa node (multi-node) và làm nghẽn băng thông của gateway khi phải serve các tệp tĩnh này.

## What Changes

- **Thay đổi luồng Ingestion:** Docling-Serve sẽ xuất ảnh dạng tham chiếu (`image_export_mode=referenced`) và đóng gói thành tệp nén **ZIP** (chứa Markdown + ảnh PNG gốc) thay vì JSON Base64.
- **Xử lý hình ảnh tối ưu:** Middleware giải nén ZIP trực tiếp trên RAM (in-memory), convert ảnh PNG sang định dạng **WebP** với chất lượng `quality=80` (sử dụng Pillow) để giảm dung lượng lưu trữ từ 30-50%.
- **Tích hợp MinIO/S3 Storage:** Lưu trữ tập trung toàn bộ hình ảnh RAG trên MinIO/S3 thay vì đĩa cục bộ của container Middleware, trả về URL tĩnh của MinIO về cho Open WebUI lưu trữ trong DB.
- **Bypass Base64 trên Query Path:** Gỡ bỏ hoàn toàn logic quét và decode Base64 trong luồng chat completion (`chat.py`). Ảnh đính kèm trực tiếp (Chat Attachments) được truyền trực tiếp dưới dạng Multimodal native cho LLM API.
- **Database Migration:** Script di trú dữ liệu chạy một lần để làm sạch 100% Base64 còn sót trong các chunk tài liệu cũ của database, thay bằng URL tĩnh.

## Capabilities

### New Capabilities
- `rag-webp-minio-ingest`: Tích hợp xử lý trích xuất ảnh RAG bằng file ZIP, chuyển đổi sang WebP, lưu trữ tập trung trên MinIO/S3 và loại bỏ Base64 khỏi luồng chat request.

### Modified Capabilities
<!-- Không có capability hiện tại nào thay đổi yêu cầu cấp spec -->

## Impact

- **llm-mw/api/chat.py:** Loại bỏ logic Context Cleaning (Base64 extraction).
- **llm-mw/api/docling.py:** Sửa đổi proxy nhận phản hồi ZIP, giải nén RAM, chuyển WebP, upload S3 và cập nhật Markdown URL.
- **llm-mw/utils/media.py / config.py:** Thêm cấu hình kết nối S3/MinIO và logic convert WebP.
- **open-webui config:** Cập nhật biến môi trường `DOCLING_PARAMS` sang dạng `referenced`.
- **Database (openwebui):** Cần chạy migration script để làm sạch dữ liệu cũ.
