## Context

Hệ thống RAG hiện tại đang gặp nút thắt cổ chai về mặt hiệu năng tại hai điểm:
- **Ingestion Path:** Docling chuyển đổi PDF thành JSON chứa các chuỗi Base64 cực lớn, khiến Middleware tốn RAM/CPU để parse JSON và giải mã ngược lại thành tệp PNG ghi xuống đĩa cục bộ.
- **Query Path:** Middleware vẫn phải quét tìm và giải mã các chuỗi Base64 trong prompt một cách đồng bộ vì còn dữ liệu RAG cũ chưa được làm sạch trong DB.
- **Lưu trữ:** Lưu ảnh local làm cản trở việc chạy cụm Docker Swarm/Kubernetes (Multi-node) và làm nghẽn băng thông của Middleware Gateway.

## Goals / Non-Goals

**Goals:**
- Loại bỏ hoàn toàn Base64 khỏi luồng Ingestion bằng cách truyền file ZIP thô từ Docling.
- Giải nén ZIP trên bộ nhớ RAM (In-memory), convert ảnh sang WebP (nén quality=80) để tiết kiệm 30-50% dung lượng.
- Lưu trữ tập trung hình ảnh RAG trên MinIO/S3 để hỗ trợ mở rộng hệ thống đa máy chủ (Multi-node).
- Tách biệt luồng phục vụ file tĩnh: Client sẽ tải ảnh trực tiếp từ MinIO/S3 hoặc qua CDN, giải phóng băng thông cho Middleware Gateway.
- Viết script di trú dữ liệu một lần để dọn dẹp các Base64 cũ trong database, cho phép gỡ bỏ hoàn toàn logic quét Base64 ở Query Path (`chat.py`).

**Non-Goals:**
- Sửa đổi mã nguồn Frontend hoặc Backend của Open WebUI.
- Thiết lập cụm queue phức tạp (như Celery/RabbitMQ) cho Ingest Task trong phase này (sử dụng FastAPI BackgroundTasks đơn giản).

## Decisions

### Decision 1: Sử dụng tệp nén ZIP (Referenced Mode) thay vì JSON Base64
- **Chọn:** Đặt tham số `CONTENT_EXTRACTION_ENGINE=docling` với `DOCLING_PARAMS={"image_export_mode":"referenced"}`. Khi chuyển đổi, Docling-Serve trả về tệp nén ZIP nhị phân.
- **Tại sao:** ZIP nén nhị phân giúp giảm 33% kích thước dữ liệu truyền tải so với Base64, tránh việc Middleware bị tràn RAM khi parse các chuỗi văn bản Base64 khổng lồ trong JSON.
- **Lựa chọn thay thế:** Sử dụng chung thư mục ổ đĩa (Shared Volume) giữa Docling và Middleware. Bị từ chối vì việc mount ổ đĩa mạng chia sẻ (NFS) rất phức tạp khi hệ thống chạy trên nhiều máy chủ vật lý khác nhau.

### Decision 2: Chuyển đổi định dạng sang WebP (Quality=80)
- **Chọn:** Sử dụng thư viện `Pillow` trong Python để chuyển đổi các tệp PNG trích xuất được sang dạng WebP với mức chất lượng 80 trước khi upload.
- **Tại sao:** Định dạng WebP nén tối ưu hơn PNG từ 30-50% đối với ảnh biểu đồ tài liệu nhưng vẫn giữ nguyên độ sắc nét của văn bản bên trong ảnh, giúp tiết kiệm dung lượng đĩa và băng thông client.
- **Lựa chọn thay thế:** Giữ nguyên PNG. Bị từ chối do tốn dung lượng lưu trữ và làm chậm tốc độ load ảnh của client trên mạng yếu.

### Decision 3: Lưu trữ trên cụm MinIO/S3 thay vì đĩa cục bộ (Local Disk)
- **Chọn:** Tích hợp client S3 (`boto3` hoặc `miniopy`) vào Middleware, đẩy toàn bộ ảnh WebP lên bucket `rag-images/`.
- **Tại sao:** MinIO/S3 là hệ thống lưu trữ phân tán, có thể mở rộng vô hạn, hỗ trợ nhiều container Middleware cùng ghi/đọc đồng thời. Đồng thời cho phép trình duyệt tải ảnh trực tiếp thông qua URL tĩnh của S3/CDN mà không cần Middleware can thiệp.
- **Lựa chọn thay thế:** Lưu trên Local Disk Volume. Bị từ chối vì không thể chạy đa máy chủ (Multi-node) và gây nghẽn băng thông Middleware Gateway.

### Decision 4: Di trú database cũ và gỡ bỏ code quét Base64 ở Query Path
- **Chọn:** Viết script `scripts/migrate_rag_base64_to_minio.py` để quét bảng `document_chunk` của Open WebUI database, dọn sạch Base64 cũ. Sau đó xóa bỏ code quét Base64 ở `chat.py`.
- **Tại sao:** Giải phóng hoàn toàn luồng chat complettions khỏi logic quét chuỗi và ghi đĩa đồng bộ, tăng tốc độ sinh từ đầu tiên (TTFT) cho người dùng.
- **Lựa chọn thay thế:** Giữ nguyên code quét Base64 ở Query Path mãi mãi. Bị từ chối vì tốn tài nguyên hệ thống vô ích cho mọi request chat.

## Risks / Trade-offs

- **[Risk] Mất kết nối tới cụm MinIO/S3** ➔ **[Mitigation]** Middleware sẽ thiết lập cơ chế retry. Nếu thất bại sau 3 lần, fallback tạm thời ghi xuống đĩa local của Middleware, nâng cảnh báo hệ thống (System Alert) để quản trị viên kiểm tra, sau đó chạy job sync đồng bộ ngầm khi MinIO online trở lại.
- **[Risk] Docling-Serve lỗi không trả về file ZIP** ➔ **[Mitigation]** Middleware bắt lỗi ngoại lệ khi parse ZIP. Nếu file zip lỗi, fallback về chỉ lấy text Markdown thô không kèm ảnh để đảm bảo việc upload tài liệu của người dùng không bị gián đoạn.
- **[Risk] Quá trình migration DB làm gián đoạn hệ thống** ➔ **[Mitigation]** Script migration sẽ chạy offline ngoài giờ làm việc. Chạy backup database `openwebui` đầy đủ trước khi thực hiện migration.
