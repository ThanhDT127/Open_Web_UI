## Context

Người dùng thường yêu cầu các nghiên cứu chuyên sâu về một chủ đề (như báo cáo thị trường, xu hướng công nghệ, phân tích đối thủ cạnh tranh). Khi dùng tìm kiếm web thông thường, LLM chỉ thực hiện tìm kiếm một bước đơn giản (single-hop) và dễ bỏ sót các nguồn tài liệu sâu hoặc không tổng hợp được báo cáo đa chiều. 

Thiết kế này đề xuất triển khai một Deep Research Agent dưới dạng Custom Pipe Function trong OpenWebUI. Agent sẽ tự chạy vòng lặp tìm kiếm đa bước (multi-hop), cào đọc nội dung trang web bằng BeautifulSoup, phát hiện khoảng trống thông tin để tìm kiếm bổ sung, và viết báo cáo hoàn chỉnh kèm trích dẫn nguồn.

## Goals / Non-Goals

**Goals:**
- Tạo Custom Pipe Function `deep_research_pipe.py` để quản lý luồng nghiên cứu đa bước.
- Tích hợp trực tiếp với API SearXNG hiện có tại `http://searxng:8080/search`.
- Thực hiện cào nội dung trang web (HTML scraping) và chuyển đổi thành văn bản sạch bằng BeautifulSoup.
- Sử dụng LLM nội bộ qua Middleware để lên kế hoạch tìm kiếm, đánh giá khoảng trống thông tin (gap analysis), và tổng hợp báo cáo.
- Hiển thị tiến trình suy nghĩ trực quan cho người dùng theo thời gian thực (stream thinking) trong khi chạy ngầm vòng lặp tìm kiếm.
- Tạo báo cáo Markdown chất lượng chuyên nghiệp có gắn chỉ số trích dẫn nguồn (`[1]`, `[2]`) liên kết đến danh mục tài liệu tham khảo ở cuối bài.

**Non-Goals:**
- Sửa đổi Svelte frontend của OpenWebUI.
- Triển khai cào các trang web yêu cầu đăng nhập hoặc bypass Cloudflare/CAPTCHA phức tạp.

## Decisions

### 1. Triển khai dạng Custom Pipe Function trong OpenWebUI
Chúng ta sẽ viết file `tools/deep_research_pipe.py` kế thừa từ lớp `Pipeline` hoặc cấu trúc Pipe của OpenWebUI.
*Alternative Considered:* Triển khai một service Python riêng chạy LangGraph.
*Rationale:* Custom Pipe chạy trực tiếp trong OpenWebUI container, không cần thêm container/service mới, dễ bảo trì, cấu hình Valves trực tiếp từ Admin Panel và có thể stream kết quả trực quan dễ dàng.

### 2. Luồng thực thi Stateful Multi-hop Search
Vòng lặp thực thi của Agent sẽ được tổ chức như sau:
1. **Lập kế hoạch (Hop 1):** LLM sinh ra 3 query tìm kiếm khác nhau từ prompt ban đầu của user.
2. **Tìm kiếm & Cào web:** Chạy SearXNG cho 3 query, lấy tối đa 4-5 URLs độc nhất, thực hiện HTTP request lấy HTML và dùng BeautifulSoup trích xuất text.
3. **Phân tích khoảng trống (Gap Analysis):** Gửi bản tóm tắt nội dung cào được cho LLM để phân tích xem có thiếu thông tin gì không. Nếu thiếu, LLM sinh thêm 2 query nâng cao để chạy Hop 2.
4. **Tìm kiếm bổ sung (Hop 2):** Chạy SearXNG cho các query bổ sung, cào thêm nội dung.
5. **Tổng hợp báo cáo:** LLM đọc toàn bộ văn bản tích lũy được và viết báo cáo chi tiết kèm trích dẫn nguồn.

### 3. Giao diện hiển thị suy nghĩ (Thinking UX)
Trong suốt quá trình chạy (có thể mất 20–40 giây), Pipe sẽ liên tục `yield` tiến trình của mình trong thẻ `<thinking>...</thinking>` (hoặc định dạng hiển thị log tương đương) để người dùng không cảm thấy ứng dụng bị treo.

## Risks / Trade-offs

- **[Risk]** Thời gian phản hồi lâu (High Latency).
  - *Mitigation:* Stream thinking log liên tục để người dùng theo dõi từng bước cào và đọc nguồn của trợ lý. Giới hạn số lượng liên kết cào và số hop (tối đa 2 hops) để đảm bảo thời gian chạy dưới 60 giây.
- **[Risk]** Gặp lỗi khi cào web (HTTP 403, Timeout).
  - *Mitigation:* Bỏ qua các trang lỗi hoặc timeout, chỉ xử lý các trang phản hồi thành công để đảm bảo tiến trình không bị gián đoạn.
