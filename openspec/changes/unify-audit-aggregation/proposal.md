## Why

Hai endpoint cùng gom bảng `mw_audit_log` bằng hai kỷ luật khác nhau, nên hai tab dashboard trả về hai con số cho cùng một câu hỏi. `summary_v2` (tab Usage) đếm theo `rid` duy nhất với trạng thái cuối cùng — đúng. `analytics.py` (tab Chat Analytics) đếm theo **dòng** — phồng 40% (264 thay vì 189), vì một request được ghi log hai lần khi chuyển `pending → reconciled`.

Nghiêm trọng hơn, thẻ **Total Requests** của tab Chat Analytics đọc `COUNT(id) FROM message` của Open WebUI — bảng đó **rỗng hoàn toàn**, nên thẻ luôn hiển thị `0` trong khi biểu đồ ngay bên dưới cộng lại ra 264. Cùng lúc, cột `CHATS` luôn bằng `0` và cột `DISPLAY NAME` luôn trùng hệt cột email, do lệch định danh giữa hai hệ thống (Open WebUI dùng UUID, middleware dùng email).

Sửa riêng lẻ từng chỗ sẽ chỉ vá triệu chứng — nguyên nhân gốc là **có hai nơi cùng biết cách gom một bảng**.

## What Changes

- Tách `compute_usage_summary()` — hàm thuần, không phụ thuộc `Request`/HTTP — ra khỏi `get_summary_v2`. Hai endpoint cùng gọi nó thay vì mỗi bên tự gom.
- `get_chat_analytics` bỏ vòng lặp gom `mw_audit_log` của riêng nó và bỏ truy vấn `COUNT(id) FROM message` (bảng rỗng, vô dụng).
- Bổ sung vào hàm dùng chung: `hourly_activity` (đếm theo `rid`) và số đếm model theo từng user (để dựng `top_model`).
- Chuyển việc cắt `breakdown_by_user[:20]` từ trong hàm gom ra ngoài endpoint, tránh làm leaderboard Chat Analytics âm thầm mất dòng khi vượt 20 user.
- Sửa `DISPLAY NAME`: join bảng `user` của Open WebUI theo `email` thay vì `id`, để hiện tên thật.
- Sửa `CHATS`: tái sử dụng chuỗi giải UUID→email đã có sẵn trong `get_satisfaction_analytics`.
- Đổi nhãn thẻ `Active Users` → `Người tạo phiên chat`, phản ánh đúng phép tính (`COUNT(DISTINCT user_id) FROM chat WHERE created_at BETWEEN …`).
- **KHÔNG xoá bất kỳ thẻ, bảng hay biểu đồ nào.** Tab Chat Analytics phải tiếp tục tự đủ thông tin, người dùng không phải nhảy qua lại giữa hai tab.

Không có breaking change: response chỉ thêm trường, `analytics.py` map lại tên trường nên frontend không đổi một dòng nào.

## Capabilities

### New Capabilities

Không có năng lực mới. Đây là thay đổi về tính đúng đắn và cấu trúc của năng lực sẵn có.

### Modified Capabilities

- `chat-analytics`: các chỉ tiêu request phải phản ánh số request thật (đếm `rid` duy nhất); leaderboard phải hiện tên thật và số phiên chat thật; thẻ `Active Users` đổi tên và nêu rõ nghĩa; bỏ yêu cầu "bộ lọc thời gian riêng biệt" đã lỗi thời (tab dùng bộ lọc toàn cục, thống nhất với `analytics-date-filtering`).
- `usage-audit-integrity`: bổ sung bất biến về **kỷ luật gom** — mọi chỉ tiêu request phải đếm theo `rid` duy nhất với trạng thái cuối cùng, và phải đến từ một hiện thực dùng chung duy nhất. Đây là điều kiện chống tái phát.

## Impact

**Backend**
- `llm-mw/api/summary_v2.py` — tách `_resolve_range()` và `compute_usage_summary()`; thêm `hourly_activity` + số đếm model theo user; chuyển `[:20]` ra ngoài. Không đổi phép tính nào, nhưng khối `:123-471` bị thụt lề lại nên diff rất lớn — xem `design.md` để biết cách soát.
- `llm-mw/api/analytics.py` — `get_chat_analytics` từ ~146 dòng còn ~70 dòng; thêm lớp map tên trường; sửa 2 truy vấn Open WebUI.

**Frontend**
- `llm-mw/dashboard/index.html` — chỉ đổi nhãn một thẻ.
- `llm-mw/dashboard/js/analytics.js` — **0 dòng**.

**API** (bổ sung, tương thích ngược)
- `GET /v1/_mw/summary` — thêm `hourly_activity`, thêm `top_model` trong `breakdown_by_user`.
- `GET /v1/_mw/admin/analytics/chat` — giữ nguyên hình dạng response; giá trị đổi từ sai sang đúng.

**Người dùng nhìn thấy**
- `Total Requests`: `0` → `189`; mọi biểu đồ/bảng request giảm ~40% về đúng số; cột `CHATS` và `DISPLAY NAME` bắt đầu có dữ liệu thật. Cần báo trước cho team để không ai tưởng hệ thống hỏng.

**Rủi ro chính**
- Refactor chạm vào lõi tính toán của tab Usage — tab được dùng nhiều nhất. Việc tách hàm khiến `git diff` hiển thị ~349 dòng xoá + ~349 dòng thêm dù không sửa phép tính nào, nên **không soát bằng mắt theo cách thường được**. Bắt buộc dùng quy trình soát ở `design.md` D9 và kiểm chứng output `/v1/_mw/summary` bất biến từng chữ số. Giao diện và JS của tab Usage không đổi một dòng.

**Ngoài phạm vi**
- Không sửa timezone (đang đúng ở VN nhờ timezone phiên DB); không sửa lỗi lệch 7 tiếng của đường dự phòng đọc file (lỗi có sẵn, đang ngủ); không đụng cột `purpose` (móc nối chết); không dọn phần dup còn lại của bad merge `2cb7510`.
