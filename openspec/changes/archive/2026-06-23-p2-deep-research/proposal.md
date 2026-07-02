## Why

Trợ lý AI mặc định chỉ tìm kiếm web một bước đơn giản (single-hop search), dễ bỏ sót thông tin chuyên sâu hoặc không tổng hợp được báo cáo phân tích đa chiều. Việc xây dựng Deep Research Agent dạng Stateful Pipeline giúp tự động hóa tìm kiếm đa bước (multi-hop search), cào đọc sâu nội dung trang web, tự động đánh giá lỗ hổng thông tin để truy vấn bổ sung và tổng hợp thành báo cáo hoàn chỉnh kèm trích dẫn nguồn trực quan cho doanh nghiệp.

## What Changes

- **Deep Research Pipeline (Stateful Pipe):** Xây dựng Custom Pipe Function [deep_research_pipe.py](file:///d:/Works/openwebui_clone/tools/deep_research_pipe.py) để quản lý chu kỳ nghiên cứu đa bước: lập kế hoạch tìm kiếm, chạy tìm kiếm SearXNG song song, cào nội dung trang web, đánh giá lỗ hổng và tổng hợp báo cáo.
- **Hiển thị tiến trình (Stream Thinking):** Hiển thị trực quan quá trình lập kế hoạch, truy vấn và đọc nguồn của Agent cho người dùng trong thời gian thực dưới dạng khối suy nghĩ hoặc các dòng bullet point tiến độ.
- **Trích dẫn nguồn trực quan (Citations):** Tự động liên kết các khẳng định trong báo cáo với nguồn gốc bằng các thẻ trích dẫn `[1]`, `[2]` trỏ đến danh mục tài liệu tham khảo kèm liên kết trực tiếp ở cuối báo cáo.

## Capabilities

### New Capabilities
- `deep-research`: Hỗ trợ tác vụ Deep Research tự động thông qua Custom Pipe, thực hiện truy vấn SearXNG đa bước, cào/đọc nội dung, đánh giá thông tin và viết báo cáo chuyên sâu kèm trích dẫn.

### Modified Capabilities
<!-- No modified capabilities -->

## Impact

- **OpenWebUI Functions:** Tạo Custom Pipe mới tại `tools/deep_research_pipe.py`.
- **SearXNG Service:** Gọi API SearXNG nội bộ thông qua docker network.
