# V85.60.50 – SQLite Update Lock Fix

Phạm vi duy nhất: xử lý lỗi `OperationalError: database is locked` khi cập nhật dữ liệu vận hành trên PC.

- Tạm dừng timer Auto Sync trước khi ghi local.
- Nếu CloudSyncWorker đang chạy, chờ worker kết thúc tối đa 30 giây; nếu chưa xong thì không ghi.
- Rollback transaction cũ trên UI connection trước khi ghi.
- Dùng `BEGIN IMMEDIATE` để lấy write lock rõ ràng.
- Giữ `busy_timeout=30000` + WAL.
- Rollback khi lỗi và khôi phục Auto Sync sau thao tác.
- Áp dụng cho cập nhật bản ghi module vận hành và cập nhật thông tin trạm.
- Không thay đổi logic MLL/KPI/BTBD/Thông báo/Supabase/Mobile.
