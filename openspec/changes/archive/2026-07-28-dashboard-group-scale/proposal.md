# Dashboard group scale metrics (Phase 7b)

## Why

Tab Groups hiện trả lời được *"phòng ban nào tiêu bao nhiêu"* nhưng không trả lời được *"phòng ban nào tiêu **nhiều**"*. Hai câu đó khác nhau: Admin tiêu `$0.0241` với 1 người, R&D tiêu `$0.0084` với 2 người — con số tuyệt đối nói Admin đắt gấp 3, nhưng tính trên đầu người thì Admin đắt gấp **5,7 lần**. Không chuẩn hoá theo quy mô thì phòng đông người luôn đứng đầu bảng chi phí, và đó là thông tin gần như vô dụng để ra quyết định.

Đây là 6 gạch đầu dòng mà `docs/dashboard_metrics_implementation_plan.md` §Phase 7 liệt kê từ đầu. Chúng bị chặn suốt vì chỉ tiêu đầu bảng — `cost share %` — là một phân số bắc cầu giữa hai tab: tử số từ Groups, mẫu số từ Usage. Groups đếm **dòng** còn Usage đếm **request duy nhất**, nên phép chia đó vô nghĩa. Change `unify-group-aggregation` (7a, archive 2026-07-27) đã dọn: giờ `Σ nhóm == totals` trên **mọi** cửa sổ, kiểm chứng bằng 10 cửa sổ × 3 nguồn độc lập.

Nên change này chỉ **cộng thêm**, không sửa lại gì. Một nửa số chỉ tiêu là phép chia trên dữ liệu 7a đã đưa sẵn vào payload — không thêm một truy vấn nào.

## What Changes

**Chỉ tiêu mới — không cần truy vấn mới** (dùng `primary_member_count`, `department_count`, `total_cost` mà 7a đã đưa vào payload)

- **Tỷ trọng chi phí** của mỗi phòng trên tổng hệ thống. Trên dev: Chưa quy được `48.3%` · Admin `36.0%` · R&D `12.6%` · DataCenter `2.6%` · DevOps `0.4%` · Marketing `0.0%` — tổng đúng `100.0%`.
- **Tỷ trọng trong phòng** của mỗi thành viên, trong drill-down. 7a đã bảo đảm `Σ drill-down == dòng cha` nên tổng không thể vượt 100%.
- **Chi phí / thành viên** — cột mới **"Nhân sự phòng"** kèm cột **"Chi phí / nhân sự"**. Trên dev: Admin `0.024123` · R&D `0.004215` · DataCenter `0.001771` · DevOps `0.000281` · Marketing `—`.
- **Scorecard 3 thẻ** ở đầu tab: *Số phòng ban* · *Nhân sự đã có phòng ban* · *Chi phí bình quân mỗi phòng ban*. Trên dev: `5` · `5 / 12` · `$0.006921`.

**Chỉ tiêu mới — cần code mới**

- **Chi phí / thành viên hoạt động.** "Hoạt động" = *có ≥1 request trong khoảng đang xem* **∩** *thành viên theo nhóm chính*. Phép giao là bắt buộc, không phải tuỳ chọn: nó là thứ đã cứu Phase 4 khỏi tỷ lệ áp dụng 108%, và nó bảo đảm `active ≤ total`.
- **% hạn mức kỳ quota hiện tại** trong drill-down thành viên. Cần truy vấn mới sang `mw_users`.

**Hạ tầng**

- **Cơ chế fetch 3 cửa sổ song song** cho tab Groups, để thẻ *Chi phí bình quân mỗi phòng ban* có badge KT/CK. **BREAKING so với plan:** plan cũ ghi việc này là *"🟢 chỉ khai báo thêm một dòng registry"* — sai. Tab Usage/Overview có sẵn cơ chế đó, tab Groups **không có**; phải dựng.

**Nhãn và cách trình bày** (bảng nhãn đầy đủ ở `design.md` D12)

- Nhãn chọn theo ba tiêu chí: **danh từ**, **tự nói ra mẫu số**, và chỉ tiêu chia cho nhau thì **dùng chung một chữ**. Cột nhân sự tên **"Nhân sự phòng"** — không dùng lại chữ "Thành viên" (xem § Impact), và không dùng *"Thuộc phòng này"* như 7a đề xuất vì đó là cụm tính từ, khó đọc với người chưa theo dõi Phase 7.
- Dòng *"Chưa quy được phòng ban"* **giữ trong bảng** nhưng **loại khỏi mọi mẫu số** của scorecard, kèm chú thích + tooltip bắt buộc.
- Chỉ tiêu không tính được hiện `—` kèm tooltip lý do, **không** hiện `0`. Riêng quota `limit ≤ 0` hiện **"Không giới hạn"** — *"không biết"* và *"vô hạn"* là hai nghĩa ngược nhau.

## Capabilities

### New Capabilities

Không có. Change này bổ sung requirement cho hai capability đã tồn tại.

### Modified Capabilities

- `group-analytics`: thêm yêu cầu về `cost_share_of_system_percent` mỗi nhóm (mẫu số là tổng hệ thống, không phải tổng các dòng hiển thị) · `primary_member_count` được hiển thị dưới nhãn "Thuộc phòng này" · chi phí trên đầu thành viên và trên đầu thành viên hoạt động · định nghĩa "thành viên hoạt động" là phép giao hai tập · scorecard 3 thẻ loại dòng chưa quy được khỏi mẫu số kèm chú thích bắt buộc · badge KT/CK cho thẻ chi phí bình quân mỗi phòng ban.
- `group-drill-down`: thêm yêu cầu về tỷ lệ chi phí của thành viên trên tổng phòng · cột % hạn mức quota với ba luật hiển thị cho trường hợp không tra được / xoá mềm / không giới hạn · yêu cầu dán nhãn rõ hai cột có **hai trục thời gian khác nhau** (chi tiêu theo khoảng đang xem vs hạn mức theo kỳ quota hiện tại).

## Impact

**Backend**

| File | Thay đổi |
|-------------------------------|--------------------------------------------------------------|
| `llm-mw/api/group_analytics.py` | `compute_group_analytics`: thêm `cost_share_of_system_percent`, `active_member_count`, `cost_per_member`, `cost_per_active_member`. `compute_group_users`: thêm `cost_share_of_group_percent` và trường quota. **Tên field nói rõ mẫu số** — dùng cùng một chữ cho hai mẫu số khác nhau là đúng cái bẫy trùng chữ change này đi tránh |
| — (đọc thêm) | `mw_users` bulk-read theo mẫu Phase 4 (`adoption.py:_quota_histogram`). ⚠️ **KHÔNG** gọi `get_current_quota_user` từng người — hàm đó **reset kỳ quota** như side-effect; gọi 200 lần vừa chậm vừa sửa dữ liệu |

**Frontend**

| File | Thay đổi |
|--------------------------------------------|-------------------------------------------------------|
| `llm-mw/dashboard/index.html` | Scorecard 3 thẻ chèn **lên đầu** tab; cột mới trong bảng; **1 chỗ** `colspan` (dòng 570) |
| `llm-mw/dashboard/js/group_analytics.js` | Render cột mới, share %, quota; **7 chỗ `colspan`** |
| `llm-mw/dashboard/js/metrics_registry.js` | Khai báo **3 thẻ scorecard**. Cột bảng **KHÔNG** khai báo — spec `dashboard-model-metrics` đã chốt chỉ scorecard mới vào registry; cột dùng formatter `usd4` đã export |
| (mới) cơ chế 3 cửa sổ cho tab Groups | Cho badge KT/CK, theo khuôn tab Usage/Overview |

**Bẫy đã biết**

- Thêm cột vào bảng Groups phải sửa **8 chỗ** `colspan`: 7 trong `group_analytics.js` + **1** trong `index.html`. ⚠️ Con số "10 chỗ" ghi ở 7a và trong plan là **sai** — nó đếm cả `colspan="7"` của `syncTable` và `logsResults`, hai bảng thuộc tab khác. Sót một chỗ thì bảng lệch, mà sửa nhầm hai chỗ kia thì hỏng tab khác.
- Tiền hiển thị **luôn** qua `usd4()`, không viết `toFixed(4)` thẳng.
- Payload giữ số **chưa làm tròn**, làm tròn đúng một lần ở tầng hiển thị. Sai số làm tròn **tăng theo số phần tử được cộng**: 6 chữ số × 200 user (quy mô hệ thống này) dồn tới chữ số thập phân thứ 4 — đúng chữ số cuối `usd4()` hiển thị.

**Xung đột nhãn phải tránh**

Section *"🔧 Phân quyền Tool theo phòng ban"* nằm **cùng tab, ngay dưới** bảng chi phí, và đã có cột **"Thành viên"** đếm `count(*) FROM group_member` — tức **mọi** membership (`core/tool_access.py:85`). Cột mới đếm **nhóm chính**. Cả hai đúng trong ngữ cảnh của nó — cấp quyền tool thì phải đếm mọi membership, chia chi phí thì phải đếm nhóm chính — nhưng nếu trùng chữ thì người đọc lấy số ở bảng dưới chia chi phí ở bảng trên và ra sai: DevOps `$0.000281` với 1 người thật nhưng 2 membership sẽ đọc thành `$0.00014/người`, rẻ đi một nửa. Hôm nay dev chưa ai kiêm nhóm nên hai con số bằng nhau; chúng chỉ tách khi có người kiêm — mà group của Open WebUI kiêm luôn việc cấp quyền tool, nên chuyện đó sẽ xảy ra.

**Không đụng tới**

- `core/tool_access.py` và cột "Thành viên" hiện có — giữ nguyên.
- Cách gom của 7a, quy tắc nhóm chính (`created_at` cũ nhất), CHECK 1 (quota alert per-user).
- Section Tool Access giữ nguyên vị trí; scorecard chèn lên đầu tab (Phase 0).

**Nợ kỹ thuật kế thừa từ 7a** — cột latency của tab Groups dùng **trung bình**, trong khi chuẩn cho latency là percentile và tab Usage của chính dashboard này dùng p95. Giữ trung bình vì p95 **không cộng lại được** từ p95 của từng người (7a design D5). Không nằm trong phạm vi change này; ghi lại để quyết riêng.
