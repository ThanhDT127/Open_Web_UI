## 1. Cấu hình & Hạ tầng S3/MinIO

- [x] 1.1 Thêm các biến môi trường cho cấu hình S3/MinIO vào `llm-mw/config.py` (`S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_SECURE`)
- [x] 1.2 Kiểm tra sự tồn tại và cài đặt thư viện cần thiết (`boto3` hoặc `miniopy` và `Pillow`) trong virtual environment
- [x] 1.3 Cập nhật biến môi trường `DOCLING_PARAMS` của `open-webui` trong `docker-compose.yml` thành `{"image_export_mode":"referenced"}`

## 2. Thư viện Utility (WebP & S3)

- [x] 2.1 Tạo module `llm-mw/utils/s3.py` để triển khai S3 client helper (chức năng `upload_bytes`, `delete_object`)
- [x] 2.2 Tạo hàm `convert_bytes_to_webp(image_bytes, quality)` trong `llm-mw/utils/media.py` sử dụng `Pillow` để nén ảnh thành định dạng WebP
- [x] 2.3 Viết unit test cho s3 client helper và hàm chuyển đổi WebP để xác minh tính đúng đắn độc lập

## 3. Luồng Ingestion (Docling ZIP Proxy)

- [x] 3.1 Refactor hàm `docling_proxy` trong `llm-mw/api/docling.py` để tiếp nhận phản hồi ZIP khi Open WebUI gọi convert tài liệu
- [x] 3.2 Viết logic in-memory unzip sử dụng `zipfile` và `io.BytesIO` để đọc file `.md` và các ảnh `.png` trực tiếp trên RAM
- [x] 3.3 Tích hợp logic convert WebP và upload lên MinIO/S3 cho mỗi file ảnh trích xuất được
- [x] 3.4 Thay thế đường dẫn cục bộ của ảnh trong Markdown bằng URL tĩnh chính thức của MinIO trước khi trả về JSON cho Open WebUI
- [x] 3.5 Viết unit test giả lập (mocking) API của Docling-Serve trả về tệp ZIP để verify logic proxy hoạt động 100%

## 4. Script Di trú Dữ liệu cũ (Database Migration)

- [x] 4.1 Tạo script `scripts/migrate_rag_base64_to_minio.py` kết nối database `openwebui`
- [x] 4.2 Viết logic quét bảng `document_chunk` để tìm các chunk chứa `data:image/`
- [x] 4.3 Giải mã Base64 sang ảnh WebP, upload lên MinIO/S3, thay đổi chuỗi Base64 bằng URL tĩnh của MinIO, và cập nhật lại bản ghi trong database
- [x] 4.4 Chạy thử nghiệm script di trú trên môi trường test và xác thực dữ liệu sau khi di trú

## 5. Dọn dẹp Query Path (Chat completions)

- [x] 5.1 Xóa bỏ hoặc comment logic quét chuỗi Base64 `data:image/` tại dòng 912-983 của file `llm-mw/api/chat.py`
- [x] 5.2 Kiểm tra logic xử lý ảnh đính kèm trực tiếp của người dùng trong chat: Đảm bảo ảnh Base64 được giữ nguyên cấu trúc JSON chuẩn của OpenAI/LiteLLM để gửi trực tiếp cho Vision Model mà không ghi đĩa
- [x] 5.3 Chạy lại bộ test cũ `test_rag_image_injection.py` và `test_e2e_rag_image.py` để xác định không bị hồi quy lỗi (regression)

## 6. Kiểm thử E2E & Xác thực hiệu năng

- [x] 6.1 Thực hiện upload PDF có biểu đồ thực tế ➔ Verify ảnh WebP được tạo trên MinIO và Markdown lưu trong DB chứa URL tĩnh của MinIO
- [x] 6.2 Thực hiện chat với tài liệu vừa upload ➔ Verify Middleware inject ảnh RAG qua link tĩnh thành công
- [x] 6.3 Đo đạc hiệu năng: So sánh thời gian phản hồi (TTFT) luồng cũ và luồng mới để xác thực mức độ giảm tải latency
