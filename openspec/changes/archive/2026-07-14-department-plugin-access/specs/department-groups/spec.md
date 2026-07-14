# department-groups Delta Specification

## ADDED Requirements

### Requirement: Seed bộ group phòng ban mẫu
Hệ thống SHALL cung cấp script seed idempotent tạo 8 group phòng ban mẫu trong Open WebUI (`ban-lanh-dao`, `kinh-doanh`, `marketing`, `ke-toan-tai-chinh`, `hcns`, `ky-thuat-rd`, `san-xuat`, `it`), mỗi group có description tiếng Việt và metadata `seeded-by: department-plugin-access` để nhận diện khi rollback.

#### Scenario: Chạy seed lần đầu
- **WHEN** admin chạy `scripts/seed_department_access.py` trên hệ thống chưa có group nào
- **THEN** 8 group phòng ban được tạo trong bảng `group` và script báo cáo danh sách group đã tạo

#### Scenario: Chạy seed lặp lại (idempotent)
- **WHEN** admin chạy lại script khi 8 group đã tồn tại
- **THEN** script bỏ qua group đã có, không tạo trùng, không sửa membership hiện hữu

#### Scenario: Dry-run
- **WHEN** admin chạy script với flag `--dry-run`
- **THEN** script chỉ in ra các thao tác dự kiến, không ghi bất kỳ thay đổi nào vào database

### Requirement: Rollback group đã seed
Script SHALL hỗ trợ flag `--rollback` xóa các group mang metadata `seeded-by: department-plugin-access`, và MUST từ chối xóa group đã có thành viên trừ khi kèm flag `--force`.

#### Scenario: Rollback an toàn
- **WHEN** admin chạy `--rollback` và một group đã được gán thành viên
- **THEN** script giữ nguyên group đó, cảnh báo rõ tên group bị bỏ qua, và chỉ xóa các group rỗng
