## Context

Dashboard hiện **không có bất kỳ logic so sánh kỳ nào** — grep toàn repo cho `compare` / `previous` / `delta` / `.delta-badge` chỉ trả về `hmac.compare_digest` và vài comment không liên quan. Mọi luật CK/KT trong `docs/dashboard_prototype_prompt_addendum_v2.md` mới là đề xuất trên prototype, chưa chạm code.

Ba dữ kiện khảo sát định hình toàn bộ thiết kế này:

1. **Mọi endpoint dashboard đã nhận `start`/`end` tuyệt đối.** 6 module, 12 endpoint (`summary_v2`, `analytics` ×2, `group_analytics` ×2, `access_logs`, `rag_health` ×3, `knowledge_analytics` ×3). Hỏi backend về một kỳ quá khứ hôm nay đã làm được, không cần thêm gì.
2. **Backend có 5 hàm resolve khoảng thời gian phân kỳ nhau**, trong đó `analytics._time_boundaries` nuốt lặng lỗi parse rồi rơi về mặc định 30 ngày, còn `summary_v2._resolve_range` thì `raise 400`. `access_logs` chứa một bản copy-paste của `_resolve_range`. Đây là nợ có sẵn.
3. **Frontend có 11 chỗ tự dựng `URLSearchParams`** từ `currentTimeRange`, mỗi chỗ tự lấy `Date.now()` riêng. Ba trong số đó (`raghealth.js`, `knowledge.js`, `export.js`) đã tự quy đổi preset sang `start`/`end` tuyệt đối bằng 8 dòng giống hệt nhau — tiền lệ có sẵn, chỉ chưa gom.

Ràng buộc: `api/export_report.py:58` gọi `get_summary_v2()` và đọc shape cũ, nên mọi thay đổi response backend đều có consumer thứ ba cần cân nhắc.

## Goals / Non-Goals

**Goals:**

- Một luật kỳ duy nhất, phủ 5 nút preset lẫn khoảng tuỳ ý, không bảng tra, không ngưỡng phát minh.
- Không thay đổi hợp đồng API nào đang chạy.
- Một nguồn chân lý cho "khoảng thời gian đang xem", để các tab không thể lệch số nhau.
- Đặt nền cho Phase 11 (Việt hoá nhãn) rẻ đi: đổi nhãn = sửa một file.

**Non-Goals:**

- Không thêm CK/KT vào file export (`export_report.py`) trong change này.
- Không hợp nhất 5 resolver backend — thiết kế này khiến chúng không còn chạy, nhưng dọn nợ là việc riêng.
- Không wiring các tab phụ thuộc phase chưa làm (Providers, Groups, Satisfaction, RAG Health, Access, Logs).
- Không sửa mốc tháng của thẻ Cost MTD (xem Risks).

## Decisions

### D1 — Phép tính cửa sổ nằm ở frontend; backend không đổi 1 dòng

Frontend tự tính 3 cửa sổ rồi gọi song song 3 lần lên chính endpoint hiện có, tính delta ở client.

*Đã cân nhắc:* thêm param `compare=1`, để mỗi endpoint gọi hàm gom của nó 3 lần rồi trả `{current, kt, ck}` (đúng như plan mô tả).

*Vì sao chọn frontend:* phương án backend đòi sửa 6 module, trong đó `analytics.py` và `group_analytics.py` phải **tách hàm gom ra khỏi endpoint** trước khi gọi lại được (query đang inline trong hàm route), đồng thời buộc phải xử lý backward-compat cho `export_report`, và buộc phải hợp nhất 5 resolver trước — nếu không CK/KT của tab Chat Analytics sẽ tính trên nền lệch so với tab Usage. Phương án frontend làm **toàn bộ khối việc đó biến mất**, đổi lấy 2 request song song và một ít payload thừa. Với `mw_audit_log` ~4,2k dòng, cái giá đó không đáng kể.

*Không khoá đường về:* cùng ~20 dòng số học ấy port sang Python bất cứ lúc nào, khi export cần CK/KT.

### D2 — CK neo theo ngày lịch, lùi đúng 1 năm, kẹp 29/02 → 28/02

*Đã cân nhắc:*

| Phương án | Bỏ vì |
| :--- | :--- |
| Lùi 24h / 7d / 28d theo độ dài range (plan cũ) | không phủ nút `6h`/`30d`; không có câu trả lời cho khoảng tuỳ ý; và **dùng sai thuật ngữ** — "cùng kỳ" trong nghiệp vụ Việt Nam mặc định là cùng kỳ *năm trước* |
| Giữ nguyên độ dài (`[start−1y, start−1y+Δ]`) | ngày kết thúc không còn là "cùng ngày", lệch với mọi công cụ BI |
| Neo theo day-of-year | nguồn khuyến nghị cách này (OneNumber/Tableau) chỉ nói cho **YTD**, không phải khoảng tuỳ ý |
| Căn theo thứ trong tuần (−364 ngày) | giải bài toán mùa vụ tuần, mà quyết định của dự án là không khử nhịp |

*Vì sao chọn:* Power BI `SAMEPERIODLASTYEAR` (và `DATEADD −1 YEAR`, cùng execution plan), GA4 "Same period last year", Adobe Analytics đều neo ngày lịch; DAX kẹp 29/02 về 28/02. Cơ quan Thống kê Anh (ONS) khuyến nghị **chỉ hiệu chỉnh năm nhuận khi độ lệch có ý nghĩa thống kê** — ở đây range đè lên 29/02 chỉ xảy ra vài ngày mỗi 4 năm, mức lệch tệ nhất ~3,6%.

*Múi giờ ảnh hưởng đúng một chỗ — xem D9.* Với phép trừ thông thường thì không: Việt Nam không có DST nên offset cố định `+07:00`, trừ 1 năm giữ nguyên trường lịch cho cùng kết quả dù tính ở giờ Việt Nam hay UTC. Nhưng **luật kẹp 29/02 thì có**, vì nó phải hỏi "ngày lịch của mốc này là ngày nào" — câu hỏi phụ thuộc múi giờ.

### D3 — KT là số học thuần trên Δ, không neo lịch

Không có nhánh riêng cho thẻ neo lịch. Thẻ Cost MTD dùng chung luật: KT = khoảng liền trước **dài đúng bằng phần đã trôi qua của tháng**.

*Đã cân nhắc:* nhánh riêng cho "họ chỉ tiêu neo lịch", KT = cùng khoảng ngày của tháng trước.

*Vì sao bỏ:* date picker sẵn có đã giải quyết việc đó — ai cần so tháng 7 với tháng 6 thì chọn thẳng `01/06 → 30/06`. Thêm nhánh riêng là dựng luật để làm thay việc mà UI đã làm được. Ngoài ra luật Δ tự né được cái bẫy được ghi nhận nhiều nhất trong thực tế: **so kỳ chưa đóng với kỳ đã đóng** (20 ngày đầu tháng vs trọn 31 ngày tháng trước) — vì cả ba cửa sổ luôn dài đúng Δ.

### D4 — Registry khai báo thay cho code rải rác

Một bảng khai báo cho toàn bộ chỉ tiêu scorecard: nhãn, formatter, kiểu delta, cực tính, cờ chặn so sánh.

*Đã cân nhắc:* viết tay từng thẻ như code hiện tại đang làm.

*Vì sao chọn:* Phase 2 gắn ~30 badge trên nhiều tab với **3 kiểu delta khác nhau** (tương đối / điểm % / tuyệt đối) và 3 cực tính. Viết tay là 30 cơ hội lệch nhau, và Phase 11 sau đó phải sờ lại đúng 30 chỗ ấy. Registry biến Phase 11 thành sửa một cột.

Cờ chặn so sánh là **bắt buộc về mặt kỹ thuật**, không phải thẩm mỹ: `pending_open_count` lấy từ `_get_global_pending_count()` (`SELECT count(*) FROM mw_pending`, không nhận tham số thời gian) nên trả **cùng một giá trị ở cả ba cửa sổ**. Không chặn thì badge hiện `0%` vĩnh viễn.

### D5 — Minh bạch thay vì ẩn ngầm

Badge luôn in mốc thật của cửa sổ đang so. Bỏ luật *"chồng lấn KT > 80% → ẩn CK"*.

*Vì sao:* luật đó suy ra từ mô hình shift cũ (D2) đã bị thay, nên không còn nền. Và khảo sát GA4 lẫn Adobe cho thấy **không công cụ nào chặn cửa sổ chồng lấn** — cả hai chỉ đưa 3 lựa chọn (kỳ trước / năm trước / tuỳ chọn) rồi để người dùng tự chịu. In mốc ra rẻ hơn (không có luật ẩn nào để test) và tránh kiểu lỗi tệ nhất: badge tự biến mất theo luật ngầm không ai biết.

### D6 — Nhịp tải compare tách khỏi poll 15s

`main.js:139` reload summary mỗi 15 giây. Compare chỉ gọi khi đổi range hoặc mở tab, cache theo `(module, start, end)`.

*Vì sao:* CK/KT là số của **kỳ đã đóng** — gom lại mỗi 15 giây là tính lại một hằng số. (Lưu ý: lý do **không phải** hiệu năng; ở 4,2k dòng thì 3 lần quét vẫn rẻ.)

### D7 — Ghim `now` một lần cho mỗi chu kỳ refresh

`buildRangeParams()` quy đổi preset sang `start`/`end` tuyệt đối tại thời điểm resolve, dùng chung cho mọi tab trong chu kỳ đó.

*Vì sao:* hiện mỗi fetch tự lấy `Date.now()` riêng, nên hai tab load cách nhau vài giây đang dùng hai cửa sổ lệch nhau. Hôm nay chênh lệch đó không nhìn thấy; có compare thì mỗi tab suy ra biên CK/KT riêng và badge cùng một chỉ tiêu sẽ lệch vài phần trăm — người xem đọc ra là "dashboard sai". Đây cũng chính là điều kiện để giữ checklist v2 *"thẻ trùng chỉ tiêu giữa 2 tab phải trùng số"*.

Ghim theo **chu kỳ**, không ghim vĩnh viễn — range vẫn cuộn theo thời gian thật.

### D8 — Truyền số thô, tính delta ở tầng trình bày

Không tính sẵn `%` ở tầng dữ liệu.

*Vì sao:* định dạng delta phụ thuộc khai báo trong registry (D4) mà chỉ tầng trình bày biết; số thô còn dùng lại được cho tooltip và cho export sau này.

### D9 — Mọi diễn giải lịch dùng **giờ Việt Nam (UTC+7)**

Áp cho cả hai chỗ, và bắt buộc phải cùng một giá trị:

1. **Chuỗi mốc in trong badge** — hiển thị theo giờ Việt Nam.
2. **Lịch dùng để đánh giá luật kẹp 29/02** (D2) — "ngày lịch của mốc này" đọc theo giờ Việt Nam.

*Vì sao phải cùng giá trị:* nếu hiển thị theo giờ Việt Nam mà kẹp theo UTC, badge sẽ ghi `29/02` trong khi hệ thống xử lý mốc đó như `28/02` — không thể giải thích cho người đọc.

*Vì sao chọn giờ Việt Nam:* người dùng nhập khoảng bằng 2 ô `datetime-local`, tức giờ local trên máy họ — in lại bằng cùng múi giờ thì cái họ gõ vào bằng đúng cái họ đọc ra, không phải nhẩm lệch 7 tiếng. Postgres cũng đã chạy `TZ: Asia/Ho_Chi_Minh`, nên luật kỳ cùng lịch với nơi dữ liệu sống. Và "mùng 1" trong đầu người đọc báo cáo là mùng 1 giờ Việt Nam.

*Đã cân nhắc:* UTC, theo tiền lệ `Date.UTC` ở `overview.js:72`. Bỏ vì chính dòng đó là khoản nợ đã ghi trong Risks (lệch 7 tiếng so với cảnh báo ngân sách), không phải tiền lệ đáng theo.

*Ca biên khiến quyết định này là chuyện đúng/sai chứ không phải thẩm mỹ:* mốc `29/02/2028 05:00` giờ Việt Nam bằng `28/02/2028 22:00` UTC — ngày lịch khác nhau giữa hai múi giờ. Đọc theo giờ Việt Nam thì luật kẹp kích hoạt (`29/02` → `28/02/2027`); đọc theo UTC thì không (`28/02` tồn tại ở 2027). Hai cách cho ra cửa sổ so sánh **lệch nhau đúng 24 giờ**. Cửa sổ kích hoạt hẹp — chỉ các mốc rơi vào `00:00–07:00` giờ Việt Nam ngày `29/02` của năm nhuận — nhưng để mơ hồ thì hai người cài ra hai kết quả và không test nào bắt được.

*Thuật ngữ:* artifact dùng chữ **"giờ Việt Nam (UTC+7)"**, không dùng viết tắt `ICT`, để tránh hiểu nhầm là một múi giờ khác giờ Việt Nam.

## Risks / Trade-offs

- **Nguồn chân lý "kỳ là gì" nằm ở trình duyệt** → ai gọi API trực tiếp, hoặc `export_report`, không có so sánh kỳ. *Mitigation:* chấp nhận trong phạm vi dashboard; khi export cần, port ~20 dòng sang Python — lúc đó luật đã được nghiệm thu bằng mắt nên port là việc cơ học.
- **Payload thừa** — cửa sổ quá khứ trả về cả `breakdown_by_*`, `timeseries`, `hourly_activity` rồi bị vứt. *Mitigation:* đo trước; nếu đáng kể thì thêm `totals_only=1` — vẫn là thay đổi backend nhỏ hơn nhiều so với D1 phương án bị loại.
- **Sửa 11 chỗ dựng param là bán kính ảnh hưởng rộng trên các tab đang chạy tốt.** *Mitigation:* migrate `buildRangeParams()` như một refactor **giữ nguyên hành vi**, làm trước và tách khỏi phần compare; xác nhận từng tab còn load đúng rồi mới gắn badge. Bắt đầu từ `raghealth.js` / `knowledge.js` / `export.js` vì chúng vốn đã phát `start`/`end` tuyệt đối nên rủi ro thấp nhất.
- **CK sẽ là `—` cho tới ~05/2027** (`mw_audit_log` có dòng đầu tiên **04/05/2026**, đã đo trên DB 2026-07-20). Leader có thể hiểu là tính năng chưa làm xong. *Mitigation:* chuẩn bị fixture mock để demo hình dạng; và trình bày rõ mốc dữ liệu khi báo cáo.
- **Rủi ro thuật ngữ:** leader nói "cùng kỳ" nhiều khả năng hiểu theo nghĩa chuẩn (năm trước). Thiết kế này dùng đúng nghĩa đó — nhưng nó **khác** với luật đã demo trên prototype. *Mitigation:* nêu thẳng khi trình lại; badge in mốc tường minh nên không thể hiểu nhầm khi nhìn.
- **5 resolver backend phân kỳ vẫn còn đó.** Thiết kế này khiến chúng không chạy (frontend luôn gửi tuyệt đối), nhưng nếu về sau có caller bỏ `start`/`end` thì sự phân kỳ quay lại. *Mitigation:* ghi nợ; `buildRangeParams()` luôn phát tuyệt đối là hàng rào chính.
- **Thẻ Cost MTD đang neo mùng 1 theo `Date.UTC`** (`overview.js:72`) trong khi cảnh báo ngân sách neo theo `date_trunc('month', now())` ở Postgres chạy `TZ: Asia/Ho_Chi_Minh` — hai định nghĩa "tháng này" lệch nhau 7 tiếng. Lỗi có sẵn, nằm ngoài phạm vi, nhưng Phase 6 sẽ đặt hai con số cạnh nhau. *Mitigation:* ghi nhận ở đây để Phase 6 không phải điều tra lại.

## Migration Plan

Thuần frontend cộng thêm; không có bước migrate dữ liệu, không có thay đổi schema.

1. **Refactor giữ nguyên hành vi** — `buildRangeParams()` + ghim `now` theo chu kỳ; chuyển 11 call site. Nghiệm thu: mọi tab load ra đúng số như trước.
2. **Hạ tầng** — module luật kỳ + registry + `renderDelta()` + CSS `.delta-badge`. Chưa gắn vào thẻ nào.
3. **6 thẻ tab Usage** — chốt hình dạng với leader tại đây.
4. **Overview + Chat Analytics** — kiểm chéo: thẻ trùng chỉ tiêu phải trùng cả số lẫn badge.

*Rollback:* bước 2–4 gỡ bằng cách bỏ lời gọi `renderDelta()`, không để lại dấu vết. Bước 1 là điểm rủi ro duy nhất — nếu phải lùi thì revert riêng nó, vì nó độc lập với phần compare.

## Open Questions

- ~~**Fixture mock cho CK** đặt ở đâu và bật bằng cách nào (cờ dev-only? file seed?)~~ — **đã chốt 2026-07-20: không mock.** Không seed DB, không cờ frontend. CK để `—` cho tới khi có dữ liệu thật (~05/2027).
  - *Vì sao câu hỏi này tự tan:* nó được đặt ra khi còn tưởng **cả hai** cửa sổ so sánh đều rỗng. Đo lại thì KT có dữ liệu thật hẳn hoi (3.907 request ở 05–06/2026), nên badge đã trình được **toàn bộ** hình dạng cần duyệt — mũi tên, màu theo cực tính, mốc cửa sổ in tường minh, giá trị tuyệt đối, và cả ba kiểu delta (`rel` ở Requests, `pp` ở Error Rate). Mock chỉ thêm được một dòng thứ hai trông giống dòng đã có.
  - *Đã dựng rồi mới gỡ.* Bản mock đầu nhân tỉ lệ cả hai bên, nên bật cờ là ghi đè mất KT thật — giấu một cú sụt `−95%` sau con số demo. Sửa thành chỉ đắp CK khi rỗng, gắn nhãn `[MOCK]`, rồi bỏ hẳn: một con số bịa nằm trong dashboard thật chỉ cách "được đọc thành sự thật" đúng một ảnh chụp màn hình, và cái giá đó không mua lại được gì.
  - `CK: —` mờ là **hành vi đúng theo spec** (yêu cầu 3.7), không phải dấu hiệu tính năng còn dở. Khi báo cáo thì nói thẳng mốc dữ liệu.
- ~~**Ngưỡng payload** — có cần `totals_only=1` ngay không?~~ — **đã chốt 2026-07-20: KHÔNG cần.** Đo thực tế trên `?minutes=43200`: `/v1/_mw/summary` trung bình **4.2 KB/request**, nên hai cửa sổ so sánh cộng lại **~6.1 KB**, và chỉ phát **một lần mỗi khi đổi range** (poll 15s không phát thêm — đã kiểm). Thêm param backend để tiết kiệm 6 KB là không đáng. Ghi lại số đo ở đây để khỏi bàn lại.
