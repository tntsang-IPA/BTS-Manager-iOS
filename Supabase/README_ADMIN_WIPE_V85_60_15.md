# Admin Xóa sạch dữ liệu – V85.60.15

Bản này giữ nguyên nền `V85_60_12` và chỉ bổ sung chức năng **Xóa sạch dữ liệu**.

## Kích hoạt Cloud

1. Mở Supabase SQL Editor.
2. Chạy file `SUPABASE_ADMIN_WIPE_V85_60_15.sql` một lần.
3. Đăng nhập BTS Manager bằng tài khoản Admin.
4. Nút **🗑️ Xóa sạch dữ liệu** sẽ xuất hiện ở thanh bên.
5. Chọn xác nhận và nhập chính xác `XOA TOAN BO`.

Chức năng xóa Cloud chạy bằng RPC có kiểm tra Admin ở phía server; tài khoản Supabase Auth được giữ nguyên.

## Phạm vi xóa

- Cloud: Stations, Contracts, Equipment, Transmission, Power, Batteries, Auxiliary, Maintenance, MLL events, MLL summaries/analysis, KPI, Notifications và Audit log.
- PC: các bảng dữ liệu nghiệp vụ tương ứng, gồm cả Notifications và Auto Alerts.
- Giữ nguyên: cấu trúc ứng dụng, schema SQLite, tài khoản đăng nhập và cấu hình ứng dụng.
- Sau khi xóa, trạng thái bootstrap đồng bộ Cloud trên PC được reset để tránh dữ liệu cache cũ quay lại.

> Bản này **không lấy các thay đổi biểu đồ/MLL sync của V85_60_23**. Nền giao diện và logic MLL của V85_60_12 được giữ nguyên.
