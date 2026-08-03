## Why

Phase 4 của `docs/dashboard_metrics_implementation_plan.md` — **User/Account: mức độ áp dụng**. Đây là câu hỏi cốt lõi của một hệ nội bộ, không phải SaaS ([[internal-rag-chatbot-adoption-not-growth]]): *đã cấp bao nhiêu tài khoản, thực sự có bao nhiêu người dùng, ai được cấp rồi bỏ đó, xu hướng người dùng đang lan ra hay co lại?* Phase 1 đã cố tình để **2 thẻ Overview ở dạng placeholder** (`Tỷ lệ sử dụng`, `Chi phí / người dùng thật`) chờ đúng phase này vì chúng cần khái niệm "active users theo range", khác hẳn "Active Users (realtime)" của SSE.

Điểm mấu chốt: Phase 4 chạm **hai miền dữ liệu khác bản chất** — *hoạt động* (`mw_audit_log`, theo cửa sổ) và *danh sách* (`mw_users`, snapshot roster). Phần quét audit đắt tiền **đã có `compute_usage_summary` gom sẵn**; `mw_users` là bảng nhỏ (~186 dòng). Nên mỗi chỉ tiêu Phase 4 chủ yếu là **phép giao/hiệu/chia giữa hai tập đã có**, cộng vài query nhẹ — không bảng mới, không migration.

An toàn định danh (khác chỗ Chat Analytics gãy — [[chat-analytics-id-mismatch]]): `mw_users.user_id` là **email** (PRIMARY KEY), `mw_audit_log.user_id` cũng là **email** → cùng namespace, phép hiệu/chia tập chạy trực tiếp. Không đụng bảng `chat`/UUID của Open WebUI.

## What Changes

- **Endpoint mới `GET /v1/_mw/adoption`** (module `api/adoption.py`, đăng ký ở `main.py` theo khuôn các endpoint dashboard khác) — nhận `start`/`end` tuyệt đối như mọi endpoint dashboard, trả về:
  - **Adoption rate** — tử số = số user active trong kỳ **và đang còn trong roster** (giao `breakdown_by_user` ∩ `mw_users` chưa xóa — cùng định nghĩa mà leaderboard tab Users rút ra, tính trên toàn population); mẫu số = `COUNT(*) FROM mw_users WHERE deleted_at IS NULL` (snapshot "tính đến hiện tại" — quyết định Q1a). Lấy **giao** để tỷ lệ luôn ≤ 100% (user đã xóa còn hoạt động lịch sử không nằm ở mẫu số nên cũng phải loại khỏi tử số).
  - **Tài khoản cấp mới trong kỳ** — `COUNT(*) FROM mw_users WHERE created_at ∈ [start,end]`, **không** lọc `deleted_at`: một sự kiện cấp tài khoản đã xảy ra trong kỳ thì không nên bị xóa về sau làm co lại kỳ quá khứ (bẫy xói mòn Phase 2 đã cảnh báo). Windowed → badge so kỳ tự chạy. Middleware vận hành **chỉ xóa mềm** (`soft_delete_user` giữ dòng, `deleted_at` set) nên bỏ filter là đếm đủ ở **mọi kỳ**, con số quá khứ không co lại. Xóa cứng (`?purge`) không phải luồng vận hành — xem context ở design.
  - **Chuỗi DAU/WAU** — một query gom `(ngày, user)` duy nhất → DAU (đếm theo ngày) + WAU (hợp 7 ngày trượt). Đường tham chiếu ngang = tổng tài khoản đã cấp (reuse mẫu số adoption).
  - **Danh sách tài khoản "ngủ"** — `SELECT user_id, max(ts) FROM mw_audit_log GROUP BY user_id` đối chiếu roster → *chưa bao giờ dùng* (`max(ts)=NULL`) + *ngừng dùng > 30 ngày* (ngưỡng cấu hình được). Snapshot roster → **chặn so kỳ**.
  - **Histogram mức dùng quota** — `SELECT user_id, quota FROM mw_users WHERE deleted_at IS NULL`, bucket `used/limit%` bằng đúng công thức của `get_user_quota_status` (`alerting.py`): 0–25 / 25–50 / 50–75 / 75–90 / >90 / *không giới hạn*. Snapshot → chặn so kỳ.
  - **Pareto top 10% chi phí** — ✅ **ĐÃ CÓ SẴN**: `top10_pct_cost_share` + `breakdown_by_user` (full) từ `compute_usage_summary`. **0 backend**, chỉ vẽ đường Pareto ở frontend.
- **Frontend (đúng convention hiện có):** namespace `window.adoptionAPI` (theo mẫu `overviewAPI`/`ragHealthAPI`), thêm khối chỉ tiêu + 2 chart (DAU/WAU line, Pareto) + bảng tài khoản ngủ vào **tab Users**; khai báo chỉ tiêu windowed trong `metrics_registry.js` để badge so kỳ tự chạy; chỉ tiêu snapshot khai `compare: false`.
- **Gỡ placeholder 2 thẻ Overview** (`ovCardAdoption`, `ovCardCpu`) — đổ số thật: adoption rate (reuse) và `Chi phí / người dùng thật` = `total_cost / active_users` (reuse cả hai vế).

## Capabilities

### New Capabilities

- `dashboard-adoption-metrics`: Tập chỉ tiêu mức độ áp dụng cho hệ nội bộ — tỷ lệ áp dụng (active-trong-kỳ / đã-cấp), tài khoản cấp mới trong kỳ, chuỗi người dùng hoạt động theo ngày/tuần (DAU/WAU) kèm đường tham chiếu tổng đã cấp, danh sách tài khoản ngủ (chưa từng dùng / ngừng lâu), và histogram mức dùng quota. Quy tắc: chỉ tiêu theo cửa sổ thời gian đủ điều kiện so kỳ (adoption rate — tử số windowed, cấp mới trong kỳ); chỉ tiêu snapshot roster (danh sách ngủ, histogram quota, số đếm tổng tài khoản đã cấp) bị chặn so kỳ. Miền hoạt động REUSE `compute_usage_summary`; miền roster query thẳng `mw_users`.

### Modified Capabilities

<!-- Không có. `dashboard-metric-registry` và `dashboard-period-compare` được TÁI DÙNG nguyên vẹn (thêm khai báo chỉ tiêu, badge chạy qua cơ chế sẵn có). `dashboard-request-metrics` không đổi — Phase 4 chỉ ĐỌC `top10_pct_cost_share`/`breakdown_by_user` mà `compute_usage_summary` đã trả, không sửa hàm. -->

## Impact

- **Backend** — thêm module `api/adoption.py` (mới) + đăng ký route ở `main.py`. **`compute_usage_summary` KHÔNG đổi một dòng** (xem design D2 — vì sao lệch giả định của plan gốc): DAU/WAU lấy từ query gom `(ngày,user)` riêng thay vì nhồi set user/bucket vào hàm dùng chung, giữ hot path Usage/Chat nguyên vẹn. Các query mới đều nhẹ: 1 gom `(ngày,user)`, 1 gom `max(ts)/user`, 2–3 query trên `mw_users` (bảng nhỏ). **0 bảng mới, 0 migration.**
- **Frontend** — `metrics_registry.js` (khai báo chỉ tiêu mới), tab Users trong `index.html` + `dashboard/js/adoption.js` (mới, namespace `adoptionAPI`), `overview.js` (gỡ 2 placeholder), `charts.js`/`dashboard.css` nếu cần cho line chart + Pareto + annotation đường tham chiếu (snippet `afterDatasetsDraw` đã để sẵn ở `docs/dashboard_frontend_harvest.md` §3b).
- **Tải hệ thống** — thêm một endpoint `/adoption` gọi khi mở tab Users (cặp KT/CK do Phase 2 lo cho chỉ tiêu windowed). Query nặng nhất là gom `(ngày,user)` trên `mw_audit_log`, dedupe sẵn ở SQL nên payload nhỏ; quy mô nội bộ (~186 user) không đáng ngại.
- **Non-goal — Nút "nhắc đào tạo" ở danh sách ngủ:** cố ý để lại (quyết định của anh Tuấn). Bảng ngủ giai đoạn này **read-only**; lớp gửi thông báo/nhắc làm sau.
- **Non-goal — WAU trên range ngắn / bucket phút:** chuỗi DAU/WAU chỉ có nghĩa ở độ phân giải ngày; endpoint luôn dựng chuỗi theo **ngày** bất kể bucket auto của tab Usage. Range < 1 ngày trả chuỗi rỗng/ẩn chart thay vì vẽ nhiễu.
- **Nợ kỹ thuật liên quan (không sửa ở đây):** thẻ Cost MTD lệch 7 tiếng timezone (mục #2 phần "Nợ kỹ thuật" của plan) — Phase 4 không đặt hai số đó cạnh nhau nên chưa chạm; để Phase 6 xử như đã ghi.
