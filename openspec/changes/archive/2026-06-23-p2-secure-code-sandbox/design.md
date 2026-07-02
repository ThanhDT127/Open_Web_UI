## Context

OpenWebUI cần khả năng thực thi code Python do mô hình tạo ra để hỗ trợ các tác vụ phân tích và vẽ đồ thị. Hiện tại chưa có môi trường sandbox cô lập an toàn, dẫn đến nguy cơ bảo mật hệ thống nếu chạy trực tiếp.

## Goals / Non-Goals

**Goals:**
- Thiết lập container `code-sandbox` chạy `jupyter/kernel-gateway` trong [docker-compose.yml](file:///d:/Works/openwebui_clone/docker-compose.yml).
- Đặt giới hạn tài nguyên nghiêm ngặt cho Sandbox: CPU `1.0`, RAM `512M`, root filesystem read-only, thư mục tạm `/tmp` dùng 64MB `tmpfs`.
- Cô lập mạng: Sandbox chỉ kết nối được với OpenWebUI (để gọi thực thi) và `pypi.org` (để cài thư viện), không thể truy cập các service nội bộ khác như `postgres`, `redis`, `litellm`.
- Thiết lập Custom Tool [code_interpreter.py](file:///d:/Works/openwebui_clone/tools/code_interpreter.py) thực hiện giao tiếp REST API với Jupyter Gateway.
- Đồng bộ thư mục output đồ thị/biểu đồ thông qua Docker shared volume (`sandbox_outputs`) để OpenWebUI có thể phục vụ tĩnh (static serving) file ảnh trực tiếp tại đường dẫn `/static/outputs/`.

**Non-Goals:**
- Không thay đổi mã nguồn gốc (Svelte/TypeScript) của OpenWebUI.
- Không cấu hình sandbox cho phép ghi đè lên mã nguồn hoặc dữ liệu nhạy cảm của hệ thống.

## Decisions

### 1. Sử dụng Jupyter Kernel Gateway làm Sandbox Engine
- **Lý do:** Khác với việc cài đặt đầy đủ Jupyter Notebook, Kernel Gateway cung cấp một giao diện REST API tối giản, hiệu quả và dễ dàng kiểm soát luồng thực thi các kernel Python từ xa mà không cần chạy giao diện UI của Jupyter.

### 2. Cô lập mạng bằng thiết kế Multi-Network
- **Lý do:** Sandbox chỉ cần liên lạc với OpenWebUI. Chúng ta tạo mạng `sandbox-network` nối giữa `open-webui` và `code-sandbox`. 
- **Cách hoạt động:** Các container nhạy cảm như `postgres`, `redis`, `litellm` và `middleware` chỉ nằm trong mạng `openwebui-network`. Vì `code-sandbox` không tham gia vào mạng này, nó hoàn toàn không có cách nào phân giải DNS hay kết nối vật lý tới các cơ sở dữ liệu và API nội bộ.

### 3. Chia sẻ thư mục Output qua Docker Volumes
- **Lý do:** Thay vì Custom Tool phải tải file ảnh kết quả từ Sandbox về thông qua API HTTP (tốn băng thông và phức tạp), chúng ta gắn một volume dùng chung `sandbox_outputs` được mount vào `/tmp/outputs` ở Sandbox và `/app/backend/data/static/outputs` ở OpenWebUI. 
- **Cách hoạt động:** Khi mã Python lưu biểu đồ matplotlib vào `/tmp/outputs/my_plot.png`, file ảnh này xuất hiện ngay lập tức trong thư mục tĩnh của OpenWebUI và có thể truy cập qua URL `/static/outputs/my_plot.png`.

## Risks / Trade-offs

- **[Risk] Vòng lặp vô hạn hoặc quá tải RAM:** Đoạn mã nguy hiểm có thể cố gắng tiêu thụ tài nguyên của host.
  - *Mitigation:* Giới hạn tài nguyên ở mức Docker `cpus: '1.0'` và `memory: 512M` đảm bảo Sandbox bị giới hạn cứng và tự động bị Docker OOM-kill nếu vượt quá RAM, đồng thời Custom Tool thiết lập HTTP client timeout tối đa 30 giây cho mỗi lượt gọi thực thi.
