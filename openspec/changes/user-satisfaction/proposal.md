## Why (Tại sao)

Admins cần khả năng theo dõi cách người dùng đánh giá các câu trả lời được sinh ra bởi các mô hình AI khác nhau trong hệ thống. Hiện tại, phản hồi của người dùng (thumbs up/down và các bình luận) được thu thập trong bảng `feedback` của Open WebUI nhưng lại chưa được hiển thị trên bảng điều khiển dành cho admin (admin dashboard). Việc hiển thị dữ liệu này cho phép admins tính toán điểm số Hài lòng của Khách hàng (Customer Satisfaction - CSAT), so sánh hiệu suất giữa các mô hình và xem xét các phản hồi chi tiết để tối ưu hóa cấu hình hệ thống cũng như cách định tuyến mô hình.

## What Changes (Những thay đổi)

- Thêm một API endpoint mới trong Middleware (`/v1/_mw/admin/analytics/satisfaction`) để truy vấn và tổng hợp dữ liệu đánh giá từ cơ sở dữ liệu của Open WebUI.
- Thêm một tab hoặc phân vùng "User Satisfaction" (Mức độ hài lòng của người dùng) mới trong Admin Dashboard.
- Hiển thị điểm số CSAT tổng quan (tỷ lệ phần trăm phản hồi tích cực so với tổng số phản hồi) cho khoảng thời gian được chọn.
- Hiển thị bảng xếp hạng (leaderboard) các mô hình dựa trên mức độ hài lòng của người dùng.
- Hiển thị một luồng (live stream) các phản hồi chi tiết gần đây (gồm bình luận và lý do) cùng với thông tin người dùng và liên kết tới đoạn chat tương ứng.

## Capabilities (Các chức năng)

### New Capabilities (Chức năng mới)
- `user-satisfaction-analytics`: Tổng hợp và hiển thị phản hồi của người dùng, điểm số CSAT và hiệu suất của các mô hình dựa trên các lượt đánh giá từ người dùng.

### Modified Capabilities (Chức năng bị thay đổi)
- (Không có)

## Impact (Tác động)

- **API/Backend**: API endpoint mới trong `analytics.py` (hoặc một file chuyên biệt). Có quyền đọc (read access) vào bảng `feedback` trong cơ sở dữ liệu của Open WebUI.
- **Dashboard UI**: Các component mới để render điểm CSAT, bảng xếp hạng và luồng phản hồi gần đây.
- **Dependencies**: Tái sử dụng cơ chế lọc khoảng thời gian (time range filtering) hiện có trong dashboard để duy trì sự nhất quán với các tính năng phân tích khác.
