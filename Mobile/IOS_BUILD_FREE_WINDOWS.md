# BTS Manager V85.60.50 – iOS miễn phí từ Windows

## Mục tiêu
- Không mua Apple Developer.
- Không cần máy Mac riêng.
- Windows là máy thao tác chính.
- CI dùng GitHub Actions macOS để tạo **unsigned IPA**.
- IPA unsigned sau đó đưa vào SideStore để SideStore ký bằng Apple Account miễn phí.

## Build
1. Đưa source này lên một GitHub repository **public** (GitHub-hosted standard macOS runners are free for public repositories).
2. Vào `Actions` → workflow `BTS Manager iOS unsigned IPA` → `Run workflow`.
3. Chờ workflow hoàn tất.
4. Tải artifact `BTS_Manager_Mobile_V85_60_50_UNSIGNED_IPA` về Windows.
5. Import IPA vào SideStore và ký/cài trên iPhone.

## iOS changes
- Chỉ thêm `ios/` target trong CI bằng `flutter create --platforms=ios`.
- Thêm `NSLocationWhenInUseUsageDescription` cho GPS.
- Đặt tên app `BTS Manager Mobile`.
- Bundle ID: `com.btsmanager.mobile`.
- Giữ asset `phat_trien_moi.png` và icon BTS Manager hiện tại.
- Không thay đổi Dart logic, Supabase, MLL/KPI/BTBD, vận hành, thông báo hoặc Android.

## Quan trọng
IPA tạo bởi workflow này là **unsigned**. Không đưa Apple ID/password vào GitHub Actions.
SideStore thực hiện bước ký bằng Apple Account miễn phí trên thiết bị/SideStore.

## Lưu ý GitHub
Workflow dùng `macos-latest`. Standard GitHub-hosted runners là miễn phí cho public repositories theo chính sách hiện hành của GitHub. Nếu repository private, GitHub Free có quota phút miễn phí và sau đó có thể phát sinh phí.
