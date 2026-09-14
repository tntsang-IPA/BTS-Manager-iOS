# BTS Manager Mobile V83.4 - Build APK Release

## Mục tiêu
Build APK release từ đúng source V83.4. Không thêm chức năng Ghi BTBD hoặc Ghi MLL.

## NDK / Android SDK
- NDK ưu tiên: `28.2.13676358`.
- Script kiểm tra NDK có `source.properties` để tránh trường hợp thư mục NDK tồn tại nhưng Gradle vẫn báo `NDK ... not found`.
- Nếu NDK 28.2 chưa hợp lệ, script tự tìm `sdkmanager.bat` và thử cài `ndk;28.2.13676358`.
- Nếu 28.2 không thể cài nhưng NDK `30.0.15729638` hợp lệ đã có sẵn, script dùng 30.0 làm fallback để không chặn build.
- `android/app/build.gradle` nhận NDK qua biến môi trường `BTS_NDK_VERSION`; mặc định là `28.2.13676358`.

## Build
1. Mở CMD/PowerShell tại thư mục project.
2. Đảm bảo `flutter` có trong PATH.
3. Chạy `build_apk.bat`.
4. Nhập `SUPABASE_URL` và `SUPABASE_PUBLISHABLE_KEY` nếu biến môi trường chưa có.
5. Script chạy `flutter clean`, `flutter pub get`, `flutter analyze` và `flutter build apk --release`.
6. APK thành công: `build\app\outputs\flutter-apk\app-release.apk`.
7. Log: `build_apk_log.txt`.

## Bảo mật
Không nhúng Supabase service-role/secret key vào APK; chỉ dùng URL + Publishable Key qua `--dart-define`.
