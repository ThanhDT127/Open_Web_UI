## MODIFIED Requirements

### Requirement: API Endpoint Phân tích hợp nhất
Hệ thống SHALL cung cấp một API endpoint (`GET /v1/_mw/admin/analytics/chat`) trả về số liệu thống kê gộp từ cả Database của Open WebUI và Database của Middleware.

Mọi chỉ tiêu liên quan tới request (tổng số request, chuỗi thời gian, phân bổ theo model, phân bổ theo giờ, số request của từng user) SHALL lấy từ hiện thực gom dùng chung của middleware, KHÔNG được tự gom lại `mw_audit_log`. Endpoint SHALL KHÔNG suy ra số request từ bảng `message` của Open WebUI.

#### Scenario: Yêu cầu lấy phân tích trong 24 giờ
- **WHEN** Admin gửi request yêu cầu lấy analytics với tham số `time_range=24h`
- **THEN** Hệ thống trả về tổng số lượng chat, số lượng request, số lượng token, và tổng chi phí USD trong 24 giờ qua, được gom nhóm theo từng giờ.

#### Scenario: Tổng số request khớp với tab Usage
- **WHEN** Admin xem tab Chat Analytics và tab Usage với cùng một khoảng thời gian
- **THEN** `totals.requests` của `/v1/_mw/admin/analytics/chat` bằng đúng `totals.requests_total` của `/v1/_mw/summary`
- **AND** tổng số request trong bảng xếp hạng người dùng và phân bổ theo model của hai tab cũng bằng nhau — kể cả khi con số đó nhỏ hơn tổng chung do có request chưa đạt trạng thái cuối cùng

#### Scenario: Request được ghi log nhiều lần chỉ tính một lần
- **WHEN** một request được ghi vào `mw_audit_log` hai lần (một dòng `pending`, một dòng `reconciled` cùng `rid`)
- **THEN** mọi chỉ tiêu request của endpoint tính request đó **đúng một lần**

#### Scenario: Bảng message của Open WebUI rỗng
- **WHEN** bảng `message` của Open WebUI không có dòng nào (phiên bản Open WebUI lưu tin nhắn trong JSON `chat.chat`)
- **THEN** `totals.requests` vẫn trả về số request thật đọc từ `mw_audit_log`, không trả về `0`

### Requirement: Các biểu đồ chi tiết (Detailed Charts)
Hệ thống SHALL cung cấp đa dạng các biểu đồ để phân tích sâu hơn về hành vi người dùng và chi phí mô hình. Tab Chat Analytics SHALL tự đủ thông tin — người dùng KHÔNG phải chuyển sang tab khác để xem số liệu lưu lượng hay chi phí.

#### Scenario: Phân tích theo giờ và theo mô hình
- **WHEN** Admin xem tab Analytics
- **THEN** Hệ thống hiển thị:
  1. Biểu đồ **Hourly Activity (0h-23h)** cho biết **tổng** số request phân bố theo các giờ trong ngày, cộng dồn toàn bộ khoảng thời gian đang xem.
  2. Biểu đồ **Model Breakdown** (Doughnut chart) và bảng **Top Models** cho biết tỷ trọng chi phí và số lượng request của từng loại AI model.
  3. Biểu đồ **Daily Trend** (Dual-axis line chart) so sánh số lượng request và chi phí USD theo từng ngày.
  4. Metric **Người tạo phiên chat** — số người dùng duy nhất đã tạo phiên chat mới trong Open WebUI trong khoảng đang xem.
  5. Bảng **Top Users Leaderboard** hiển thị Email, **tên thật** của người dùng, **số phiên chat** của người đó, số request, tokens, chi phí, tỷ lệ phần trăm chi phí (Cost Share) và model dùng nhiều nhất.

#### Scenario: Thẻ Người tạo phiên chat phản ánh đúng phép tính
- **WHEN** trong khoảng đang xem có 9 người dùng tạo phiên chat mới trong Open WebUI, trong khi 13 người có gọi LLM qua middleware
- **THEN** thẻ hiển thị `9` với nhãn nêu rõ đây là số người **tạo phiên chat mới trong Open WebUI**, không phải số người dùng hệ thống

#### Scenario: Leaderboard hiển thị tên thật thay vì lặp lại email
- **WHEN** một user có bản ghi trong bảng `user` của Open WebUI với `email = "tranxuantuan1522005@gmail.com"` và `name = "Trần Xuân Tuấn"`
- **THEN** cột Display Name hiển thị `Trần Xuân Tuấn`, không lặp lại địa chỉ email

#### Scenario: Leaderboard hiển thị số phiên chat thật
- **WHEN** trong khoảng đang xem có các phiên chat thuộc những người dùng có định danh phía middleware
- **THEN** cột số phiên chat của họ hiển thị số thật, không phải toàn số `0`

#### Scenario: Phiên chat của người dùng không có định danh middleware
- **WHEN** một phiên chat thuộc user đã bị xoá khỏi Open WebUI và user đó không có bản ghi nào trong `mw_users` lẫn `mw_audit_log`
- **THEN** phiên đó KHÔNG được quy vào dòng nào của leaderboard, vì leaderboard chỉ gồm những người dùng có hoạt động phía middleware
- **AND** tổng cột số phiên chat SẼ nhỏ hơn `totals.chats` — đây là hành vi đúng, không phải lỗi

#### Scenario: Người dùng đã xoá khỏi Open WebUI vẫn giữ số phiên chat lịch sử
- **WHEN** một user đã bị xoá khỏi Open WebUI nhưng vẫn còn phiên chat trong khoảng đang xem
- **THEN** số phiên chat của người đó vẫn được tính, nhờ giải định danh qua `mw_users` rồi tới `mw_audit_log` thay vì join trực tiếp bảng `user`

#### Scenario: Leaderboard không bị cắt dòng khi vượt 20 người dùng
- **WHEN** trong khoảng đang xem có hơn 20 người dùng có hoạt động
- **THEN** leaderboard của tab Chat Analytics vẫn liệt kê đầy đủ, không bị giới hạn 20 dòng của endpoint summary

## REMOVED Requirements

### Requirement: Bộ lọc thời gian riêng biệt cho tab Analytics

**Reason:** Yêu cầu này chưa từng được cài đặt và đã lỗi thời. Tab Chat Analytics dùng bộ lọc thời gian toàn cục của dashboard (`currentTimeRange`), thống nhất với hướng đã chốt ở năng lực `analytics-date-filtering` — mọi API analytics nhận tham số `minutes`/`start`/`end` từ bộ lọc chung thay vì tự quản lý khoảng thời gian riêng.

**Migration:** Không cần di trú. Người dùng đã và đang dùng bộ lọc toàn cục ở đầu dashboard; bộ lọc đó áp cho tab Chat Analytics như mọi tab khác. Không có API hay giao diện nào bị gỡ bỏ.
