## 0. Điều tra trước khi code

- [x] 0.1 Đọc log giải thích **1.981 lượt `/health` trả 503** — toàn bộ 503 của hệ thống. Phân biệt "LiteLLM chết thật" với "healthcheck chạy lúc container đang khởi động". Kết quả quyết định mục **9**: nếu LiteLLM thật sự chập chờn thì thẻ Sức khỏe sẽ đỏ thường xuyên và cần một cách hiển thị chịu được điều đó, không phải một đèn nhị phân
- [x] 0.2 Ghi lại số 503 theo ngày để có mốc so sánh sau khi deploy
  > **Đo 02/08/2026.** Tổng 1.982 lượt 503, **100% từ `/health`**, `client = 127.0.0.1` (Docker `HEALTHCHECK`).
  > Phân bố: 01/07 = 909/1.000 (91%) · 02/07 = 773/967 (80%) — **1.682/1.982 = 85% dồn vào hai ngày sự cố thật**.
  > Ngày thường: 26/07 0,49% · 27/07 0,75% · 28/07 1,00% · 30/07 1,96% · 31/07 0,42% · 02/08 0,90%.
  > **Kết luận cho mục 9:** đèn nhị phân là đủ — nền dưới 2% là healthcheck lúc container khởi động, không phải LiteLLM chập chờn.

## 1. Mở đường cho thẻ Sức khỏe

- [x] 1.1 `main.py` — `app.add_api_route("/v1/_mw/health", health_report, methods=["GET"])`
  > ⚠️ **Lệch design, có chủ đích.** Design viết *"gọi lại chính `health_check`"*. Nhưng `health_check` trả **503 khi degraded**, mà `mwFetch` coi `res.ok=false` là hỏng → nhánh `catch` của mục 9.6 sẽ **xoá sạch thẻ đúng lúc LiteLLM chết**. Tách `_collect_health()` dùng chung; `/health` giữ nguyên 200/503 cho Docker, `/v1/_mw/health` **luôn 200** + guard, người đọc xem trường `ok` trong body. Hai hợp đồng khác nhau, một nguồn dữ liệu.
- [x] 1.2 Giữ nguyên route `/health` cũ (Docker `HEALTHCHECK` gọi qua `localhost` trong container, không qua nginx)
- [x] 1.3 ✅ Đo 02/08: `:3000/health` → `{"status":true}` (Open WebUI, không đổi) · `:5000/health` → `{"ok":true,"uptime_seconds":22,"litellm":"ok","disk_free_gb":282.45,…}` · `:3000/v1/_mw/health` → tồn tại (403 khi chưa auth, không phải 404). Kiểm **qua `:3000`**: `/v1/_mw/health` trả JSON có `uptime_seconds`, còn `/health` vẫn trả `{"status":true}` của Open WebUI — hai đường, hai kết quả, đúng như thiết kế
- [x] 1.4 ✅ `403` khi chưa đăng nhập (route bịa trả `404`, nên `403` chứng minh route có thật và guard chạy)

## 2. Access summary — hết nuốt lỗi

- [x] 2.1 Bỏ `try/except: pass` ở `access_logs.py:62`; DB hỏng thì raise, không lặng lẽ rơi sang file
- [x] 2.2 Giữ nhánh đọc file làm fallback **có chủ đích** — thêm tham số `source` (`db` | `file`). `source=file` là chọn tường minh; DB không cấu hình thì đọc file (sự thật triển khai); DB có mà đọc hỏng thì **raise**
- [x] 2.3 `access.js` — banner đỏ theo khuôn `ragStorError` sẵn có, **và xoá luôn số cũ về `—`**: banner đặt trên dãy số của khoảng thời gian trước vẫn đọc như thể dãy số đó thuộc khoảng đang chọn
- [x] 2.4 Nghiệm thu **một phần** — đo được vế hiển thị, chưa đo được vế DB thật.
  > ✅ **Vế UI ĐẠT.** Nạp số thật (`513` request · `2.5%` bị từ chối · `30ms` P95 · bảng 16 dòng, không banner) → ép `/v1/_mw/access_summary` trả `500` → **mọi thẻ về `—`, bảng về `—`, banner đỏ hiện** → gọi lại bình thường → số quay lại đúng, banner tắt. Đúng yêu cầu spec *"số của khoảng trước không được sống sót qua một lần lỗi"*.
  > ❌ **Vế DB thật chưa chạy:** dừng Postgres bị hệ thống quyền chặn, và tôi không lách. Vế này mới chứng minh được *"DB hỏng thì raise chứ không lặng lẽ đọc file"* — hiện chỉ xác nhận bằng đọc code (`try/except: pass` đã gỡ, nhánh file chỉ vào được khi `source=file` hoặc DB không cấu hình).
  > Muốn đóng nốt: cấp quyền `docker compose stop postgres` rồi chạy lại, kiểm `data.source` **không** bằng `"file"`.

## 3. Access summary — bỏ resolver thứ năm

- [x] 3.1 Gỡ khối giải mã thời gian nội bộ `access_logs.py:41-59` → gọi `summary_v2._resolve_range`
- [x] 3.2 Truyền `minutes=60` tường minh để giữ nguyên mặc định cũ
- [x] 3.3 Nghiệm thu: `start=2026-13-45` trả `400` cùng thông điệp với 5 endpoint Phase 9a đã đo. Bỏ trống `start`/`end` vẫn về 60 phút
- [x] 3.4 Cập nhật ghi chú **nợ kỹ thuật #1** trong `docs/dashboard_metrics_implementation_plan.md`: Phase 9a tuyên bố đã đóng nhưng `access_logs.py` còn một bản; nay mới thật sự chỉ còn `summary_v2._resolve_range`

## 4. Ba nhóm lỗi thay cho một thẻ gộp

- [x] 4.1 `_format_access_result` trả `failures` (5xx **trừ** `/health`) · `denied` (401/403) · `throttled` (429), mỗi nhóm kèm tỷ lệ. Luật phân loại nằm **một chỗ** (`_add_record`), dùng chung cho nhánh DB và nhánh file
- [x] 4.2 Trả riêng dưới khoá `health_probe_failures` (mọi 5xx trên `/health`, không chỉ 503 — giữ bốn nhóm rời nhau tuyệt đối)
- [x] 4.3 **Bất biến ĐẠT trên 5 cửa sổ** (1h · 24h · 7d · 30d · 90d): `5 nhóm == error_count` khớp tuyệt đối mọi cửa sổ.
  > Tách trên toàn bộ dữ liệu: `health_probe 1.982` · `throttled 1.375` · `other 4xx 377` · `denied 305` · `failures 265` = **4.304**. Xác nhận lý do trừ `/health`: nếu gộp, `failures` thật bị át **7,5:1**.
- [x] 4.4 Thẻ "Error Rate" cũ tách làm ba trên UI; không giữ lại con số gộp ở bất kỳ đâu

## 5. Bảng Top Paths — bỏ hai cột hằng số

- [x] 5.1 Backend trả `errors` và `error_rate_percent` thật cho **từng đường dẫn**
- [x] 5.2 `access.js:31-34` — bỏ nhánh `p.error_rate_percent !== undefined ? … : (p.errors || 0)`; đọc thẳng field thật
- [x] 5.3 **Bất biến ĐẠT trên 5 cửa sổ.** ⚠️ Bảng bị cắt `[:20]` nên tổng 20 dòng hiển thị **không** tự đóng được — đúng bẫy `[:20]` của Phase 1/Phase 4. Trả thêm `totals.errors_outside_top_paths`; bất biến phát biểu lại là `Σ errors(top20) + errors_outside_top_paths == error_count`
- [x] 5.4 Nghiệm thu: bảng phải có ít nhất một dòng khác `0` (cùng cửa sổ hiện có 4.296 request ≥ 400)

## 6. P95 và số mẫu

- [x] 6.1 Sửa `round(p95_latency, 2) if p95_latency else None` → `if p95_latency is not None` — P95 bằng `0` thật đang bị biến thành `None`
- [x] 6.2 Trả `latency_sample_count`
- [x] 6.3 Hiện số mẫu lên UI khi độ phủ dưới 100% (đúng cách Phase 7a xử lý `latency_sum_ms` / `latency_sample_count`)
- [x] 6.4 Sửa nốt `if ms:` → `if ms is not None:` để không âm thầm bỏ các request nhanh nhất
  > **Đo trên dữ liệu thật: `ms` thiếu = 0 dòng, `ms == 0` = 0 dòng / 52.110.** Nên đây là **phòng ngừa, không phải chữa lỗi đang xảy ra** — `latency_sample_count == requests_total` ở cả 5 cửa sổ. Ghi đúng để sau này không ai tưởng nó đã sửa được một sai lệch thật.

## 7. Nợ kỹ thuật #4 — cookie không khôi phục

- [x] 7.1 `auth.js:145` — bỏ hẳn `document.addEventListener('DOMContentLoaded', …)` trong `initAuth()`, gọi thẳng `checkAuthStatus()`. Lúc `initAuth()` chạy thì DOM chắc chắn đã sẵn sàng (nó nằm sau 4 lần `await`)
- [x] 7.2 Nghiệm thu **cả ba đường**: cookie còn hạn → vào thẳng · cookie hết hạn → màn hình đăng nhập · chưa từng đăng nhập → màn hình đăng nhập
  > ⚠️ **Chỉ đo được 2/3 đường sau khi sửa.** ✅ *cookie còn hạn* → hard-refresh vào thẳng dashboard, `auth_check` `200 cookie_present:true`. ✅ *chưa đăng nhập* → `403`, hiện màn hình đăng nhập. ❌ *cookie hết hạn* — **chưa kiểm sau khi sửa**; muốn kiểm phải chờ cookie 4 giờ tự hết hoặc xoá tay. Ghi thẳng ra chứ không đánh đồng với hai đường kia.
- [x] 7.3 Đo lại: 403 vào `/v1/_mw/*` (trừ `dashboard/login`) trong một phiên mới phải về ~0. Mốc trước khi sửa: **89 lượt tích luỹ**
- [x] 7.4 Cập nhật ghi chú nợ #4 trong plan là đã đóng

## 8. Ghi đúng địa chỉ người gọi

- [x] 8.1 `Dockerfile` — **cố ý KHÔNG dùng `--proxy-headers`** (xem 8.4: nó đọc `X-Forwarded-For`, mà header đó bị nginx nối thêm nên phần tử đầu là lời tự khai). Địa chỉ đọc từ `X-Real-IP` qua `utils/client_ip.py`, dải tin cậy khai tường minh trong đó, **không** dùng `*`
- [x] 8.2 ✅ **Quyết định này vừa được thực tế xác nhận:** design đo `172.18`, hôm nay đo lại là **`172.19.0.9` (nginx) / `172.19.0.1` (host)** — subnet đã trôi lần nữa chỉ trong 2 ngày. Ghim `/16` thì nay đã hỏng im lặng. **Không ghim subnet cụ thể của compose.** Docker cấp động và dự án đã trôi thật (`172.19` → `172.18`); ghim rồi trôi thì nginx thôi được tin và hỏng **im lặng**. Hoặc dùng `172.16.0.0/12`, hoặc ghim subnet trong `docker-compose.yml` **rồi** mới ghim ở đây — không ghim một bên
- [x] 8.3 ✅ **ĐẠT.** Qua nginx, `payload.client = 172.19.0.1` (host thật) chứ không phải `172.19.0.9` (nginx). Đo trực tiếp trên `mw_request_log`
- [x] 8.4 ✅ **ĐẠT sau khi đổi cách làm.** Bốn phép thử qua nginx đều ghi `172.19.0.1`: bình thường · giả `X-Forwarded-For` · giả `X-Real-IP` · giả cả hai.
  > **Bản đầu TRƯỢT** và đã bị thay. `--proxy-headers` đọc `X-Forwarded-For`, mà nginx dựng header đó bằng `$proxy_add_x_forwarded_for` — **nối thêm** chứ không ghi đè, nên phần tử đầu là lời tự khai của người gọi, và uvicorn lấy đúng phần tử đầu. Đo được: `curl -H "X-Forwarded-For: 203.0.113.55"` → ghi nguyên `203.0.113.55`.
  > **Cách thay thế (anh Tuấn chốt: KHÔNG đụng `nginx.conf`):** bỏ `--proxy-headers`, đọc `X-Real-IP` — nginx đặt bằng `$remote_addr` (**ghi đè**) ở cả **12/12 khối proxy**, nên lời khai của người gọi bị xoá trước khi rời nginx. Hàm dùng chung `utils/client_ip.py`, chỉ tin header khi kết nối đến từ dải riêng.
  > **Ghi rõ mức ảnh hưởng của bản lỗi:** IP chỉ dùng để **ghi log**, không nơi nào dùng để ra quyết định — không mở được cửa nào, không né được `limit_req` (nginx đếm theo địa chỉ TCP thật), không giấu được dấu vết (access log của nginx ghi IP thật, không bịa được).
  > **Nguyên nhân:** `nginx.conf` dùng `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for` ở **11 khối `location`**. Biến đó **nối thêm** chứ không ghi đè: client gửi `203.0.113.55` thì nginx chuyển tiếp `203.0.113.55, 172.19.0.1`. `--proxy-headers` của uvicorn lấy **phần tử đầu** làm "client gốc" — tức đúng giá trị kẻ gọi tự khai. Vì kết nối tới từ nginx (nằm trong dải tin cậy) nên uvicorn tin.
  > **Đây là lỗ hổng thật, không phải lỗi test:** hệ thống phơi ra Internet (`nginx.conf:36`, NAT 51122 → 3000), nên bất kỳ ai cũng tự ghi IP tuỳ ý vào `mw_request_log`.
  > **Sửa:** `proxy_set_header X-Forwarded-For $remote_addr;` (ghi đè, vứt bỏ giá trị client khai). **Nhưng đụng `nginx.conf`, mà Decision 1 của design cố ý tránh** — cần anh Tuấn quyết.
- [x] 8.5 Cả 3 chỗ đã chuyển sang `client_address()` chung: `user_admin.py` (`ip` nhật ký admin) · `core/auth.py` (`auth_fail`) · `api/auth_test.py`. Ghi vào plan ở 13.6
- [x] 8.6 ✅ Không dựng thẻ đếm IP. Dữ liệu chỉ nằm trong `mw_request_log`, truy vấn được bất cứ lúc nào

## 9. Thẻ Sức khỏe hệ thống (Overview)

- [x] 9.1 `dashboard/js/overview.js` — gỡ placeholder ở thẻ `ovCardHealth` (thẻ thứ 3 của Overview), dòng uptime để trống từ Phase 1
- [x] 9.2 Hiện LiteLLM · dung lượng đĩa · thời gian chạy
- [x] 9.3 Nhãn **"Chạy liên tục từ lần khởi động gần nhất"**, không dùng chữ "Uptime" trống. Chú thích in kèm mốc khởi động thật
- [x] 9.4 **Không hiện `active_users`** — trùng cách gọi với badge tab Users và thẻ Tỷ lệ áp dụng, mà định nghĩa khác
- [x] 9.5 Chú thích cho chuyện `--workers 4`: mỗi worker giữ mốc khởi động riêng nên số có thể nhích giữa hai lần tải
- [x] 9.6 Nhánh `catch` phải xoá **cả số lẫn dòng chú thích** — bài học thẻ CSAT Phase 8

## 10. Chỉ tiêu mới trên tab Access

- [x] 10.0 `dashboard/index.html` — thêm markup `.metric-card` cho các thẻ mới ở `accessTab`, theo đúng khuôn 3 thẻ sẵn có (`accessTotal` · `accessErrorRate` · `accessLatency`). Đặt id theo convention `access*`
- [x] 10.1 Thẻ **P95 tầng HTTP** kèm số mẫu
- [x] 10.2 Thẻ **Tỷ lệ bị từ chối** (401/403) — chỉ làm sau khi mục 7 xong, nếu không nó đo chính dashboard
- [x] 10.3 Thẻ **Số lần đăng nhập dashboard thất bại**. Nhãn **bắt buộc có chữ "dashboard"**: đăng nhập của nhân viên đi `nginx location /api/v1/auths/` → Open WebUI, **không** qua middleware, nên con số này không bao giờ phản ánh họ
- [x] 10.4 ⚠️ P95 của Access phải có **khoá riêng** `http_p95_latency_ms`, **không** dùng lại `p95_latency_ms`. Entry sẵn có nhãn `P95 Latency` đang phục vụ tab Usage và đo thời gian **model trả lời**; Access đo **mọi request HTTP** kể cả tải file tĩnh. Dùng chung là tái tạo đúng con "Total Requests" của Phase 0
- [x] 10.5 Nhãn của nó phải nói rõ tầng HTTP, để hai thẻ P95 trên hai tab không đọc như nhau
- [x] 10.6 Đăng ký 7 entry trong `metrics_registry.js`: `http_p95_latency_ms` · `failure_rate_percent` · `denied_rate_percent` · `throttled_rate_percent` · `failed_dashboard_logins` · `uptime_seconds` (`compare: false`) · `disk_free_gb` (`compare: false`)
- [x] 10.7 Không khai `bands` cho ba tỷ lệ lỗi cho tới khi có mốc thật — màu là một phán quyết (cùng lý do `top10_pct_cost_share` và `kb_coverage_percent` để trung tính)

## 11. Cảnh báo chi phí bất thường

- [x] 11.1 Tính thuần frontend từ `timeseries_data` — không endpoint mới, không query lại
- [x] 11.2 Ngưỡng `> 2×` trung bình chuỗi
- [x] 11.3 **Ngưỡng mẫu tối thiểu** khai ở `metrics_registry.js`: chuỗi quá ngắn thì không kết luận. Cùng cơ chế `minSample` của `csat_percent` và `citation_hit_rate`, không dựng cái mới
- [x] 11.4 **Không tô màu khi bucket cuối chưa đóng** — ngày mới chạy 3 tiếng thì chi phí thấp là đương nhiên, so với trung bình cả ngày là so hai thứ khác đơn vị
- [x] 11.5 Chú thích in cả giá trị bucket lẫn trung bình chuỗi, để người đọc tự kiểm

## 12. Badge so kỳ tab Access (Phase 2 wiring)

- [x] 12.1 Gọi `compare_data.loadCompare()` sẵn có — không dựng cơ chế mới, nó đang phục vụ 5 tab
- [x] 12.2 `pick()` phải trả **`null`** cho cửa sổ rỗng, **không** trả `0` — trả `0` thì badge chia cho 0 và hiện một mức tăng bịa ra (bài học Phase 7b)
- [x] 12.3 Badge cho: tổng request · ba nhóm lỗi · P95
- [x] 12.4 Chặn badge khi cửa sổ đem ra so dưới ngưỡng mẫu — một kỳ quá mỏng để tô màu thì cũng quá mỏng để làm mốc (bài học Phase 9c)

## 13. Nghiệm thu

- [x] 13.1 **Mọi kiểm tra định tuyến phải qua `https://localhost:3000/dashboard`**, không phải `:5000`. Phase 7 và Phase 9 nghiệm thu ở `:5000` là lý do bug `/health` sống sót qua ba phase
- [x] 13.2 `docker compose build middleware && up -d` — đụng `Dockerfile` nên `docker cp` không có tác dụng (`uvicorn --workers 4` không `--reload`)
- [x] 13.3 **Ctrl+Shift+R** bắt buộc: nợ kỹ thuật #5 khiến chỉ 3 module JS được cache-bust. Lần này `auth.js` nằm trong diff — không hard-refresh thì tưởng mục 7 không ăn
- [x] 13.4 Chạy bộ bất biến trên ≥ 4 cửa sổ: mục 4.3 · 5.3 · 8.3 · 8.4
- [x] 13.5 Console trình duyệt sạch
- [x] 13.6 Ghi kết quả vào `docs/dashboard_metrics_implementation_plan.md` §Phase 10, kèm hai non-goal và bằng chứng đo được của chúng
