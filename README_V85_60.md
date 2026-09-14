BTS Manager V85.60.13 - MLL sync compatibility fix

# BTS Manager V85.60.24 — FULL CLEAN

## Baseline / chức năng giữ nguyên
- PC + Mobile dùng chung Supabase.
- Đồng bộ Thông báo hai chiều PC ↔ Cloud ↔ Mobile.
- Phân quyền Thông báo theo Email trong sheet TRẠM BTS.
- Admin `tntsang@gmail.com` xem toàn bộ.
- User chỉ xem thông báo của chính mình; cảnh báo tự động theo Email của trạm.
- User được tạo thông báo cá nhân; thông báo thủ công chỉ người tạo và Admin thấy.
- Admin có thể tạo user, đổi mật khẩu, đổi quyền và xóa user trong cột Thao tác.
- Dashboard MLL giữ nguyên logic PC-authoritative/KPI đã chốt.
- Dashboard PC giữ nhãn **Mất LL (TB MLL)** và hiển thị dạng **0.48 / 0.5 phút**.
- Combobox mẫu Import dùng tên **Mẫu KPI**.

## Thành phần runtime / build
- `PC/main.py`, `PC/cloud_client.py`
- `PC/BTS_Manager_Import_Template_V85_60_5_EMAIL.xlsx`
- `PC/BTS_Manager_MLL_Template.xlsx`
- `PC/BTS_Manager_KPI_Import_Template.xlsx`
- `PC/SUPABASE_SCHEMA.sql` — schema nền.
- `Supabase/SUPABASE_SCHEMA_PC_BASE.sql` — schema nền bản đồng bộ.
- `Supabase/SUPABASE_NOTIFICATION_PERMISSION_V85_60.sql` — migration phân quyền + xóa user.
- `Mobile/lib/**`, `Mobile/android/**`, `Mobile/pubspec.yaml`, `Mobile/build_apk.bat`
- `BUILD_V85_60_ALL.bat`, `INSTALL_PC_V85_60.bat`

## Đã tinh gọn
- Xóa README lịch sử V83/V84/V85 cũ.
- Xóa source backup `main.py.bak_*`.
- Xóa `__pycache__`.
- Xóa build/test script cũ không dùng cho release.
- Xóa thư mục patch PC_MLL_CLOUD_SYNC cũ đã tích hợp vào source hiện tại.
- Xóa template Mobile trùng/không được source sử dụng.
- Xóa template PC trùng; giữ một template Email-enabled làm nguồn chuẩn.
- Xóa các SQL migration sửa lỗi cũ đã được tích hợp/không cần chạy lại trong bản full.

## Build
Chạy `BUILD_V85_60_ALL.bat` một lần trên Windows development PC. Script build cả PC EXE và Mobile APK, sau đó kiểm tra output.

Trước khi test phân quyền Thông báo trên project Supabase hiện tại, chạy một lần:
`Supabase/SUPABASE_NOTIFICATION_PERMISSION_V85_60.sql`
