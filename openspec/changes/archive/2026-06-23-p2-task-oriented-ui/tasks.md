## 1. Setup and Preparation

- [x] 1.1 Tạo thư mục `fuction UI` nếu chưa tồn tại.
- [x] 1.2 Tạo tệp [task_cards_styling.css](file:///d:/Works/openwebui_clone/fuction%20UI/task_cards_styling.css) trống.
- [x] 1.3 Tạo tệp [task_suggestions_config.json](file:///d:/Works/openwebui_clone/fuction%20UI/task_suggestions_config.json) trống.

## 2. CSS Styling and Suggestions Configuration

- [x] 2.1 Viết mã CSS tiêm vào `task_cards_styling.css` để định hình grid layout 2x2, gradient card background và hiệu ứng hover.
- [x] 2.2 Viết cấu hình Suggestions JSON trong `task_suggestions_config.json` định nghĩa 4 thẻ công việc: Hỏi tài liệu, Nghiên cứu web, Phân tích file, Tạo biểu mẫu.

## 3. UI Verification and Automated Testing

- [x] 3.1 Soạn thảo tài liệu hướng dẫn Admin cách import CSS và Suggestions thủ công qua Admin Panel.
- [x] 3.2 Viết tệp kiểm thử Playwright mới [ui-task-cards.spec.ts](file:///d:/Works/openwebui_clone/tests/ui-task-cards.spec.ts) để tự động hóa việc đăng nhập, kiểm tra sự tồn tại của 4 thẻ tác vụ và xác minh các class CSS tùy biến được tiêm vào trang chủ.
- [x] 3.3 Chạy kiểm thử tự động Playwright bằng lệnh `npx playwright test tests/ui-task-cards.spec.ts` và xác nhận kết quả thành công 100%.
