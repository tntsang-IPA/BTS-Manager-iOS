# BTS Manager Mobile – Final

## Phạm vi chốt
1. Đăng nhập app, đăng xuất và đổi mật khẩu.
2. Dashboard theo các nhóm chính của Dashboard PC, bố cục tối ưu cho màn hình điện thoại.
3. Vận hành hiện trường:
   - Cập nhật thông tin trạm bằng 2 combobox: Mã trạm + Sheet dữ liệu.
   - Nút Tìm mở popup hiển thị toàn bộ trường của sheet để chỉnh sửa.
   - Chọn vị trí hiện tại để tính khoảng cách đến đúng 4 trạm gần nhất.
   - Tọa độ trạm lấy từ Vĩ độ/Kinh độ của sheet TRẠM BTS, đã được đồng bộ vào stations.latitude/longitude.
4. Thông báo với các thao tác tương tự PC: xem, tạo, đặt lịch, đánh dấu hoàn thành/chưa hoàn thành và xóa theo quyền.

## Không nằm trong bản Final
- Camera/Push nâng cao của V82.
- Ghi BTBD hoặc ghi nhận MLL trực tiếp từ Mobile.

## Build
Ứng dụng cần Flutter SDK. Cấu hình bằng:
`--dart-define=SUPABASE_URL=... --dart-define=SUPABASE_PUBLISHABLE_KEY=...`

Không nhúng service-role key vào Mobile.


## Release signing

The FINAL release build is configured to sign the APK automatically. On the first build, `build_apk.bat` creates a local release keystore at `%USERPROFILE%\.bts_manager_v83\release-key.jks` and stores its password locally in the same folder. The keystore is intentionally kept outside the project ZIP. Subsequent builds on the same Windows user reuse the same signing key, allowing future APK updates to be signed consistently. After Gradle builds the APK, the script verifies the APK with Android SDK `apksigner`; an unsigned or invalidly signed APK is treated as a build failure.


V83.8: PC launcher icon + MLL analytics synchronized with PC/Supabase, month range, monthly TB BSC chart and details.
V84.2: Restored all PC MLL KPI aliases and made the selected end-month analysis point use the same authoritative PC KPI value.


## RELEASE SIGNER LOCK
- Release updates MUST use the existing `%USERPROFILE%\.bts_manager_v83\release-key.jks`.
- The locked alias is `btsmanager`; the build validates the existing keystore/password before Gradle.
- NEVER generate, replace, or auto-discover a different release alias for an update build.
- If validation fails, stop before Gradle and report the signer error.
