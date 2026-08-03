## ADDED Requirements

### Requirement: Each department reports its share of total system cost

Mỗi dòng nhóm SHALL mang `cost_share_of_system_percent` — chi phí của nhóm trên **tổng chi phí toàn hệ thống** của cùng cửa sổ, tức `totals.cost_total_usd`. Mẫu số SHALL là tổng hệ thống, KHÔNG phải tổng các dòng đang hiển thị, để mỗi dòng báo đúng tỷ lệ thật của nó kể cả khi danh sách bị cắt.

Vì tử số và mẫu số đến từ cùng một lời gọi `compute_usage_summary`, tổng các tỷ lệ SHALL bằng 100% mà không cần hiệu chỉnh.

#### Scenario: Shares add up to the whole

- **WHEN** Admin xem tab Groups trên một cửa sổ có dữ liệu
- **THEN** tổng `cost_share_of_system_percent` của tất cả các dòng (kể cả dòng "Chưa quy được phòng ban") bằng 100%, sai lệch không quá sai số hiển thị của một chữ số thập phân

#### Scenario: Zero total cost is guarded

- **WHEN** cửa sổ đang xem không có chi phí nào
- **THEN** `cost_share_of_system_percent` của mọi nhóm là 0, không phát sinh lỗi chia cho 0

### Requirement: Department member count is labelled distinctly from tool-access membership

Bảng Groups SHALL hiển thị `primary_member_count` dưới nhãn **"Nhân sự phòng"**. Nhãn này SHALL KHÔNG dùng lại chữ **"Thành viên"**, vì section phân quyền tool nằm cùng tab và ngay bên dưới đã dùng chữ đó cho một phép đếm khác — **mọi** membership thay vì chỉ nhóm chính.

Cột "Thành viên" hiện có ở section phân quyền tool SHALL giữ nguyên: đếm mọi membership là đúng ở đó, vì nó trả lời "bật tool cho phòng này thì bao nhiêu người thấy".

#### Scenario: The two counts diverge when someone belongs to two groups

- **WHEN** một user thuộc nhóm A (gia nhập sớm hơn) và nhóm B
- **THEN** cột "Nhân sự phòng" của nhóm B KHÔNG đếm user đó, trong khi cột "Thành viên" ở section phân quyền tool CÓ đếm — và hai cột mang hai nhãn khác nhau nên không thể đọc nhầm là cùng một số

#### Scenario: The unresolved row has no member count

- **WHEN** bảng hiển thị dòng "Chưa quy được phòng ban"
- **THEN** ô "Nhân sự phòng" của dòng đó hiển thị `—`, vì dòng đó không phải một phòng ban và không có danh sách thành viên

### Requirement: Cost is normalised by department size

Mỗi dòng nhóm SHALL mang hai chỉ tiêu trên đầu người, giữ **cả hai** vì chúng trả lời hai câu hỏi khác nhau:

- `cost_per_member` = chi phí nhóm ÷ số người có nhóm này là nhóm chính — *"trung bình mỗi nhân sự phòng này tốn bao nhiêu"*.
- `cost_per_active_member` = chi phí nhóm ÷ số người **hoạt động** — *"người thực sự dùng thì tốn bao nhiêu"*.

Cả hai SHALL hiển thị `—` khi mẫu số bằng 0, KHÔNG hiển thị `0`.

#### Scenario: A department with no members reports no per-head cost

- **WHEN** một phòng ban có 0 thành viên
- **THEN** cả hai ô chi phí trên đầu người hiển thị `—` kèm chú giải, không hiển thị `0` và không phát sinh lỗi chia cho 0

#### Scenario: Per-head cost separates spend from headcount

- **WHEN** phòng A chi nhiều hơn phòng B về số tuyệt đối nhưng có nhiều thành viên hơn theo tỷ lệ lớn hơn
- **THEN** `cost_per_member` của phòng A nhỏ hơn phòng B, phản ánh đúng rằng phòng A tiêu ít hơn trên mỗi đầu người

### Requirement: Active members are the intersection of activity and membership

`active_member_count` của một nhóm SHALL là **giao** của hai tập: người có ít nhất một request trong cửa sổ đang xem, và người có nhóm này là nhóm chính. Hệ thống SHALL KHÔNG chỉ đếm người có hoạt động rồi gán theo nhóm.

Phép giao là bắt buộc vì `mw_audit_log` giữ lịch sử của cả người đã rời phòng ban: không giao thì một người đã bị xoá khỏi `group_member` vẫn được tính là đang hoạt động của nhóm, và số người hoạt động có thể **vượt** tổng số thành viên.

Hệ quả kiểm chứng được: `active_member_count <= primary_member_count` với **mọi** nhóm và **mọi** cửa sổ.

#### Scenario: Active never exceeds total

- **WHEN** tính chỉ tiêu cho bất kỳ nhóm nào trên bất kỳ cửa sổ nào
- **THEN** số thành viên hoạt động nhỏ hơn hoặc bằng số thành viên của nhóm đó

#### Scenario: Someone who left the department is not counted as active

- **WHEN** một user từng phát sinh request trong cửa sổ rồi bị xoá khỏi mọi nhóm bên Open WebUI
- **THEN** user đó không được tính vào `active_member_count` của bất kỳ phòng ban nào; chi phí của họ vẫn xuất hiện ở dòng "Chưa quy được phòng ban"

### Requirement: The department scorecard excludes unattributable spending from every denominator

Tab Groups SHALL hiển thị ba thẻ ở **đầu tab**: *Số phòng ban*, *Nhân sự đã có phòng ban*, *Chi phí bình quân mỗi phòng ban*. Dòng "Chưa quy được phòng ban" SHALL bị loại khỏi **mọi mẫu số** của ba thẻ này — nó không phải một phòng ban — nhưng SHALL vẫn hiển thị trong bảng bên dưới.

Vì tổng chi phí trong bảng do đó **lớn hơn** phần được chia trong thẻ *Chi phí bình quân mỗi phòng ban*, hệ thống SHALL hiển thị chú thích ngay dưới cụm thẻ, nêu số phòng ban và chỉ ra phần chi phí nằm ngoài. Chú thích này là **bắt buộc**, không phải trang trí: thiếu nó thì người đọc cộng cột chi phí rồi chia cho số phòng ban sẽ ra một con số khác hẳn mà không ai giải thích được.

Chú thích SHALL kèm giải thích ba loại định danh nằm trong dòng đó: nhân viên chưa được gán phòng ban, tài khoản đã bị xoá khỏi Open WebUI, và định danh hệ thống không phải người dùng.

Section "🔧 Phân quyền Tool theo phòng ban" SHALL giữ nguyên vị trí và nội dung; scorecard chỉ được chèn thêm lên đầu tab.

#### Scenario: Scorecard denominators ignore the unresolved row

- **WHEN** dòng "Chưa quy được phòng ban" có chi phí lớn hơn 0
- **THEN** thẻ *Số phòng ban* không đếm nó, và thẻ *Chi phí bình quân mỗi phòng ban* không cộng chi phí của nó vào tử số

#### Scenario: The gap between table and scorecard is explained on screen

- **WHEN** Admin xem cụm scorecard
- **THEN** ngay dưới cụm thẻ có chú thích nêu số phòng ban và cho biết phần chi phí còn lại nằm ở dòng "Chưa quy được phòng ban" trong bảng, kèm giải thích ba loại định danh của dòng đó

#### Scenario: Department count does not follow the time window

- **WHEN** Admin đổi cửa sổ thời gian
- **THEN** thẻ *Số phòng ban* không đổi giá trị, vì nó mô tả cơ cấu tổ chức chứ không mô tả cửa sổ

### Requirement: Only scorecards carry period comparison

Badge so kỳ KT/CK SHALL chỉ gắn cho thẻ *Chi phí bình quân mỗi phòng ban*. Hai thẻ còn lại (*Số phòng ban*, *Nhân sự đã có phòng ban*) là snapshot cơ cấu tổ chức, không có trục thời gian, nên SHALL KHÔNG có badge so kỳ.

Các cột trong bảng breakdown SHALL KHÔNG được khai báo trong `metrics_registry.js` và SHALL KHÔNG mang badge so kỳ, nhất quán với luật đã có: chỉ scorecard mới vào registry.

Để badge hoạt động, tab Groups SHALL có cơ chế lấy dữ liệu của ba cửa sổ (hiện tại, kỳ trước, cùng kỳ năm trước). Cơ chế này chưa tồn tại ở tab Groups và phải được dựng; khai báo trong registry là điều kiện cần nhưng không đủ.

#### Scenario: Structure cards have no comparison badge

- **WHEN** cụm scorecard hiển thị
- **THEN** chỉ thẻ *Chi phí bình quân mỗi phòng ban* có badge KT/CK; *Số phòng ban* và *Nhân sự đã có phòng ban* không có

#### Scenario: Table columns are not registry metrics

- **WHEN** bảng Groups render các cột mới
- **THEN** không cột nào được tra trong `metrics_registry.js`, và không cột nào mang badge so kỳ

### Requirement: The headcount card shows how many staff still have no department

Thẻ nhân sự SHALL hiển thị **cả tử số và mẫu số**: số người đã được gán phòng ban trên tổng số tài khoản đang hoạt động, dưới nhãn **"Nhân sự đã có phòng ban"**.

Nhãn SHALL KHÔNG là "Tổng thành viên" hay bất kỳ chữ nào đọc ra thành *tổng nhân sự của tổ chức* — con số này chỉ đếm người **đã có phòng ban**. Trên dev có 12 tài khoản đang hoạt động nhưng chỉ 5 người có phòng ban; hiện `5` trơ dưới nhãn "Tổng thành viên" sẽ khiến người đọc tin tổ chức có 5 người.

Hiện cả mẫu số là bắt buộc vì phần chênh chính là **nguyên nhân** của chi phí không quy được: người chưa có phòng ban thì chi phí của họ không thể quy về đâu. Khác với chi phí chưa quy được — vốn là hệ quả — số người chưa gán là việc xử lý được ngay.

#### Scenario: The card exposes the unassigned gap

- **WHEN** hệ thống có nhiều tài khoản đang hoạt động hơn số người đã được gán phòng ban
- **THEN** thẻ hiển thị dạng `N / M` với `N` là số người đã có phòng ban và `M` là tổng tài khoản đang hoạt động, dưới nhãn không hàm ý `N` là toàn bộ nhân sự

### Requirement: The unresolved row carries no per-head metrics

Dòng "Chưa quy được phòng ban" SHALL trả `None` cho `primary_member_count`, `active_member_count`, `cost_per_member` và `cost_per_active_member`. Dòng này không phải một đơn vị nên mọi chỉ tiêu "trên đầu người của đơn vị" đều không áp dụng, dù nó **có** người phát sinh chi phí.

Bất biến `active_member_count <= primary_member_count` SHALL chỉ được kiểm trên các nhóm có `group_id`.

#### Scenario: Active count is absent, not zero, for the unresolved row

- **WHEN** dòng "Chưa quy được phòng ban" có nhiều người phát sinh request trong cửa sổ
- **THEN** các ô chỉ tiêu trên đầu người của dòng đó hiển thị `—`, không hiển thị số người hoạt động và không hiển thị `0`
