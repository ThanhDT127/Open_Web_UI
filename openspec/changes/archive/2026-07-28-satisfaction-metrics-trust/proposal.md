## Why

Tab Satisfaction hiện hiển thị những con số **không đứng vững**: một model bị đúng một người bấm chê được tô đỏ và xếp bét bảng; CSAT bị `int()` cắt cụt nên `66,7%` hiện thành `66%`; lý do đánh giá mà Open WebUI mới thêm thì đổ nguyên chuỗi `snake_case` ra màn hình; sheet Satisfaction trong Excel nuốt lỗi rồi tải về toàn số 0 như thể "chưa ai đánh giá".

Đồng thời chỉ tiêu quan trọng nhất của tab này vẫn chưa có: **bao nhiêu phần trăm câu trả lời được đánh giá**. Đo trên dev là **2,8%** — tức 97 trên 100 câu trả lời không ai bấm gì. Không con số nào khác trong dashboard nói được điều đó, và nó là căn cứ để quyết có cần nhắc nhân viên dùng nút đánh giá hay không.

## What Changes

**Nhóm 1 — sửa cái đang sai (số ĐỔI trên màn hình)**

- Thống nhất bộ giải mã khoảng thời gian: `analytics._time_boundaries` → `summary_v2._resolve_range`. **BREAKING** với tham số hỏng: trước đây im lặng rơi về 30 ngày, nay trả `400`. Chạm **cả** `get_chat_analytics` vì hai endpoint dùng chung hàm này.
- Ngưỡng mẫu tối thiểu **20 lượt** cho mọi xếp hạng và tô màu theo CSAT — áp cho **cả** bảng model lẫn thẻ "Mức hài lòng" ở tab Overview. Dưới ngưỡng: vẫn hiện số, nhưng không số hạng, không màu, xếp xuống tầng riêng.
- Bảng dịch lý do đánh giá thành danh sách **ưu tiên** + hàm dự phòng làm chuỗi lạ đọc được, thay vì đổ `snake_case`.
- Bỏ `int()` ở hai chỗ tính CSAT; payload trả số thô, làm tròn **một lần** ở tầng hiển thị bằng formatter `pct1` đã có sẵn trong registry.
- Sửa nhãn sai: Excel `"Tổng feedback"` và Overview `"N lượt đánh giá"` → `"lượt khen/chê"`. Payload thêm `feedback_rows` làm chốt an toàn khi xuất hiện rating khác `±1`. **Không** đụng 4 nhãn tiếng Anh của thẻ tab — đó là phạm vi Phase 11.
- Gom ngưỡng màu `80/50` (đang chép ở `overview.js` và `satisfaction.js`) cùng ngưỡng mẫu mới về **một chỗ duy nhất** trong `metrics_registry.js`.
- Tách hàm thuần `compute_satisfaction(cutoff, end_time)`; Excel gọi hàm thuần và **bỏ `except: pass`** — đúng cách `_collect_groups` đã được sửa ở Phase 7a.
- Sửa một **cảnh spec đã lỗi thời** mà Phase 7a để lại: `report-export` vẫn ghi *"OW DB group query fails → Sheet 4 chứa một dòng 'Dữ liệu nhóm không khả dụng'"*, trong khi `_collect_groups` từ Phase 7a **đã để lỗi lan ra**. Đây là sửa tài liệu cho khớp code đang chạy, không đổi hành vi.

**Nhóm 2 — thêm chỉ tiêu (số chỉ THÊM)**

- Chỉ tiêu **"% câu trả lời được đánh giá"**: tử số là lượt khen/chê, mẫu số là số `rid` duy nhất của **riêng** request `chat/completions`.
- Hàm `count_chat_completions(cutoff, end_time)` đặt trong `summary_v2.py` cạnh `compute_usage_summary`, dùng chung `_resolve_range`.

**Cố ý KHÔNG làm** (ghi kèm điều kiện mở khoá, xem `design.md`): xu hướng CSAT theo thời gian · thống kê lý do bị chê · CSAT ghép chi phí theo model · CSAT theo phòng ban. Cả bốn đều bị chặn bởi **cùng một lý do**: dữ liệu đánh giá quá ít, không phải vì khó.

## Capabilities

### New Capabilities

- `satisfaction-analytics`: chỉ tiêu tab Satisfaction phải đáng tin — ngưỡng mẫu tối thiểu trước khi xếp hạng/tô màu, nhãn khớp giá trị, làm tròn một lần ở tầng hiển thị, mọi lý do đánh giá đều đọc được, và tỷ lệ câu trả lời được đánh giá tính trên đúng loại request.

### Modified Capabilities

- `chat-analytics`: endpoint phân tích trả `400` khi khoảng thời gian không hợp lệ, thay vì im lặng rơi về mặc định 30 ngày.
- `report-export`: sheet Satisfaction phải hỏng lớn tiếng thay vì xuất file toàn số 0; nhãn ô khớp với giá trị nó chứa.
- `dashboard-metric-registry`: ngưỡng phân loại của một chỉ tiêu được khai báo tại registry, không chép ở từng module hiển thị.

## Impact

| Vùng | File | Ghi chú |
|-------------------|--------------------------------------|--------------------------------------------------------------|
| Backend           | `api/analytics.py`                   | Đổi resolver (chạm **cả** Chat Analytics), tách hàm thuần, bỏ `int()` |
| Backend           | `api/summary_v2.py`                  | Thêm `count_chat_completions()`                              |
| Backend           | `api/export_report.py`               | Gọi hàm thuần, bỏ `except: pass`, sửa nhãn ô                 |
| Frontend          | `dashboard/js/satisfaction.js`       | Ngưỡng mẫu, hàm dự phòng nhãn lý do, dùng `pct1`             |
| Frontend          | `dashboard/js/overview.js`           | Ngưỡng mẫu cho thẻ CSAT, dùng `pct1`, sửa nhãn               |
| Frontend          | `dashboard/js/metrics_registry.js`   | Nơi khai báo ngưỡng duy nhất                                 |
| Frontend          | `dashboard/index.html`               | Thêm chỗ hiển thị tỷ lệ được đánh giá                        |
| Tab bị ảnh hưởng  | Satisfaction · Overview · **Chat Analytics** · Excel export | Chat Analytics nằm ngoài tên gọi của change nhưng dùng chung resolver |

Không thêm bảng, không thêm cột database, không thêm index. Không ghi vào cơ sở dữ liệu của Open WebUI.
