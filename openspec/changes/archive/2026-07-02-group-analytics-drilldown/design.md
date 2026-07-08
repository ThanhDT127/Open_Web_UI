## Context

Dashboard hiện tại có tab Group Analytics dùng để tổng hợp lượng quota tiêu thụ của các phòng ban. Tuy nhiên, logic lọc thời gian của tab này đang hoàn toàn bị tách rời khỏi các phần khác của hệ thống phân tích (bị hardcode lùi lại 30 ngày ở phía backend). Hơn nữa, các quản trị viên (admin) thường xuyên cần xem chi tiết (drill-down) lượng quota tiêu thụ của từng người dùng cụ thể trong một nhóm để phân bổ chi phí chính xác, nhưng tính năng này hiện chưa tồn tại.

## Goals / Non-Goals

**Goals:**
- Áp dụng bộ lọc thời gian/ngày toàn cục (`minutes`, `start`, `end`) cho API Group Analytics (`/v1/_mw/admin/analytics/groups`).
- Mở thêm một API endpoint mới để lấy dữ liệu phân tích sử dụng của các users nằm trong một nhóm cụ thể, sử dụng chung cơ chế lọc thời gian.
- Triển khai giao diện drill-down dạng accordion trong bảng Group Analytics, giúp tải (lazy load) và hiển thị dữ liệu user khi click vào một dòng.

**Non-Goals:**
- Không thay đổi hoặc chỉnh sửa cấu trúc (schema) cơ sở dữ liệu hiện tại.
- Không triển khai real-time websocket stream cho group analytics; chỉ dùng REST endpoints là đủ.
- Không xây dựng bảng trượt (slide-over panel) cho tính năng drill-down để tránh che khuất bảng dữ liệu chính.

## Decisions

- **Tái sử dụng hàm `_time_boundaries`:** Thay vì viết lại logic xử lý ngày giờ cho các API nhóm, chúng ta sẽ import và sử dụng hàm hỗ trợ `_time_boundaries` từ module `api.analytics` vào bên trong `api/group_analytics.py`. Việc này đảm bảo tính nhất quán tuyệt đối với API chat analytics.
- **Tải lười (Lazy loading) dữ liệu drill-down:** Dữ liệu phân tích cấp độ user sẽ không được trả về trong payload gốc của API `/groups`. Thay vào đó, thao tác click vào một dòng nhóm sẽ kích hoạt một lệnh gọi (fetch) đến `/groups/{group_id}/users`. Cách tiếp cận này giúp tránh việc phải tải một lượng lớn dữ liệu không cần thiết đối với những nhóm có quy mô lớn.
- **Giao diện Accordion kết hợp Scroll (Cuộn chuột):** Giao diện accordion (mở rộng dòng ngay bên dưới dòng được click) được chọn thay vì dùng modal, bởi vì nó giữ nguyên ngữ cảnh. Để tránh việc mở một nhóm có quá nhiều user làm đẩy giao diện chính đi quá xa, bảng phụ bên trong accordion sẽ được giới hạn chiều cao (`max-height`) và có thanh cuộn chuột dọc, kế thừa toàn bộ cơ chế và CSS từ bảng User Quota Management hiện có.

## Risks / Trade-offs

- **Rủi ro**: Các dòng accordion có thể làm phá vỡ luồng hiển thị trực quan của bảng nếu có quá nhiều dòng được mở rộng cùng lúc.
  - *Giải pháp (Mitigation)*: Chúng ta sẽ thêm style màu xen kẽ cho các dòng của bảng phụ để phân biệt rõ ràng với bảng chính, đồng thời cho phép click lại để thu gọn dòng.
- **Rủi ro**: Hiệu suất của API có thể bị suy giảm nếu một nhóm có hàng ngàn user.
  - *Giải pháp (Mitigation)*: Vì dữ liệu được tải lười (lazy-loaded) cho từng nhóm, nên thời gian tải bảng chính ban đầu không bị ảnh hưởng. Nếu việc truy vấn một nhóm cụ thể bị chậm, nó chỉ ảnh hưởng cục bộ đến thao tác drill-down đó. Chúng ta có thể thêm tính năng phân trang (pagination) sau này nếu thực sự cần thiết.
