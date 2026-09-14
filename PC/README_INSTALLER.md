# BTS Manager V9.6.4 - Windows Bootstrap Installer v26

## Mục tiêu
Bản v26 sửa lỗi cài trên máy khác khi Windows chưa có Python hoặc `python.exe` chỉ trỏ tới Microsoft Store App Execution Alias.

## Cách cài đặt khuyến nghị
1. Giải nén **toàn bộ ZIP** vào một thư mục local, ví dụ Desktop hoặc Downloads.
2. Chuột phải `INSTALL_BTS_MANAGER.bat` → **Run as administrator**.
3. Không chạy `python`, không cần cài Python thủ công trước.
4. Installer tự xử lý theo thứ tự:
   - kiểm tra Windows 10/11 64-bit;
   - kiểm tra/cài Microsoft Visual C++ Runtime;
   - tìm Python thật, bỏ qua Windows Store alias;
   - thử `winget` trước;
   - nếu `winget` không có hoặc cài thất bại, tự tải Python 3.13.15 chính thức từ python.org và cài silent;
   - tạo `.venv-installer` riêng;
   - cài PySide6, openpyxl, PyInstaller;
   - build `BTS_Manager.exe`;
   - cài vào `%LOCALAPPDATA%\BTS Manager`;
   - tạo shortcut Desktop + Start Menu;
   - tự khởi động BTS Manager.

## Dữ liệu người dùng
Database được lưu cố định tại:

`%LOCALAPPDATA%\BTS Manager\bts_manager.db`

Điều này đã được sửa để tránh lỗi mất dữ liệu khi chạy PyInstaller `--onefile`: thư mục `_MEIPASS` của EXE là thư mục tạm và không được dùng để lưu database.

## Internet
Máy đích cần Internet trong lần cài đầu nếu thiếu Python/VC++ hoặc các package Python. Nếu máy dùng proxy/firewall doanh nghiệp, xem `install.log` để biết URL hoặc package nào bị chặn.

## Nếu cài lỗi
Mở:

`install.log`

trong cùng thư mục với `INSTALL_BTS_MANAGER.bat` và gửi toàn bộ log nếu cần xử lý tiếp.

## Lưu ý
- Đây là **bootstrap installer**: máy đích tự dựng EXE, vì vậy không yêu cầu Python có sẵn trước.
- `BUILD_INSTALLER_WINDOWS.bat` chỉ dành cho máy phát triển đã có Python.
- `INSTALL_BTS_MANAGER.bat` mới là file dành cho máy người dùng cuối.


## v38 installer fix
- If BTS Manager is already running, the installer closes it before replacing BTS_Manager.exe.
- Includes a retry loop for short Windows/antivirus file locks.
- This prevents the installation failure caused by `BTS_Manager.exe` being used by another process.

## Tối ưu V64
- Installer giữ lại cache Python/PyInstaller tại `%ProgramData%\BTS Manager\InstallerCache` để các lần cài/update sau nhanh hơn.
- Chỉ build lại EXE khi `main.py`, template Excel hoặc icon thay đổi.
- ZIP end-user không chứa `__pycache__`, các README lịch sử và các file build/deploy không cần thiết.
