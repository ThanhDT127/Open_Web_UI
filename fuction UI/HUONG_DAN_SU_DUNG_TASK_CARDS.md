# Hướng Dẫn Tích Hợp Task Cards và Custom Suggestions Vào OpenWebUI

Tài liệu này hướng dẫn quản trị viên (Admin) cách kích hoạt giao diện Task Cards (thẻ tác vụ) dạng Grid 2x2 cho trang chủ OpenWebUI.

---

## Bước 1: Tiêm Mã Custom CSS
1. Đăng nhập vào tài khoản Admin của OpenWebUI.
2. Truy cập **Admin Panel** -> **Settings** -> **Interface** (Giao diện).
3. Cuộn xuống phần **Custom CSS** (CSS Tùy biến).
4. Sao chép toàn bộ nội dung trong tệp [task_cards_styling.css](file:///d:/Works/openwebui_clone/fuction%20UI/task_cards_styling.css) và dán vào ô nhập liệu Custom CSS.
5. Bấm **Save** (Lưu) để áp dụng.

---

## Bước 2: Cấu Hình Chat Suggestions (Gợi Ý Trò Chuyện)
1. Vẫn trong mục **Interface** của Settings.
2. Tìm phần **Chat Suggestions** (Gợi ý trò chuyện).
3. Xóa các gợi ý mặc định cũ (nếu có).
4. Thêm 4 gợi ý trò chuyện mới tương ứng với cấu hình trong tệp [task_suggestions_config.json](file:///d:/Works/openwebui_clone/fuction%20UI/task_suggestions_config.json):
   
   *   **Gợi ý 1 (Hỏi tài liệu):**
       *   *Nội dung hiển thị (Title & Description):* 
           `📂 Hỏi tài liệu (RAG Local): Tra cứu, tổng hợp và phân tích thông tin chính xác từ các tài liệu nội bộ (PDF, DOCX, Excel) đã đăng tải.`
       *   *Prompt kích hoạt:* 
           `[Tác vụ: Hỏi tài liệu] Tôi muốn tra cứu thông tin trong tài liệu đã tải lên. Hãy phân tích nguồn và trả lời câu hỏi sau:`
   *   **Gợi ý 2 (Nghiên cứu Web):**
       *   *Nội dung hiển thị (Title & Description):* 
           `🌐 Nghiên cứu Web (Deep Research): Tìm kiếm chuyên sâu đa bước (multi-hop) trên Internet, cào dữ liệu nguồn và tổng hợp báo cáo chi tiết kèm trích dẫn.`
       *   *Prompt kích hoạt:* 
           `[Tác vụ: Nghiên cứu web] Tôi cần thực hiện một nghiên cứu chi tiết về chủ đề sau. Hãy chạy tìm kiếm đa bước và lập báo cáo:`
   *   **Gợi ý 3 (Phân tích File):**
       *   *Nội dung hiển thị (Title & Description):* 
           `📊 Phân tích File (Code Sandbox): Tải lên tệp Excel, CSV để thực hiện tính toán, vẽ biểu đồ trực quan và phân tích dữ liệu trong môi trường sandbox an toàn.`
       *   *Prompt kích hoạt:* 
           `[Tác vụ: Phân tích file] Tôi đã tải lên tệp dữ liệu. Hãy viết và chạy mã Python để phân tích các chỉ số sau và vẽ biểu đồ:`
   *   **Gợi ý 4 (Tạo biểu mẫu):**
       *   *Nội dung hiển thị (Title & Description):* 
           `📝 Tạo biểu mẫu (Form Generator): Soạn thảo văn bản, hợp đồng, biểu mẫu hành chính hoặc báo cáo chuyên nghiệp theo form chuẩn doanh nghiệp.`
       *   *Prompt kích hoạt:* 
           `[Tác vụ: Tạo biểu mẫu] Hãy giúp tôi soạn thảo một biểu mẫu chuẩn cho nội dung sau:`

6. Bấm **Save** (Lưu) ở phía dưới cùng trang để kích hoạt Suggestions mới.

---

## Bước 3: Xác Minh Kết Quả
1. Tạo một hội thoại chat mới hoặc quay trở lại trang chủ OpenWebUI.
2. Kiểm tra xem 4 gợi ý trò chuyện đã hiển thị dạng grid 2x2 đẹp mắt với hiệu ứng hover gradient hay chưa.
3. Click thử vào một thẻ tác vụ để xác nhận prompt được điền tự động vào khung chat và kích hoạt đúng tác vụ.
