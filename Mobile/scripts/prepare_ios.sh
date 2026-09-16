#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Add only the iOS platform; preserve the existing Android/Dart project.
flutter create --platforms=ios --org com.btsmanager .

python3 - <<'PY'
from pathlib import Path

# iOS foreground/background location permission declarations.
p=Path('ios/Runner/Info.plist')
s=p.read_text()
needle='</dict>'
insert='''\n\t<key>CFBundleDisplayName</key>\n\t<string>BTS Manager Mobile</string>\n\t<key>NSLocationWhenInUseUsageDescription</key>\n\t<string>BTS Manager cần quyền vị trí để xác định vị trí hiện tại và tính khoảng cách đến các trạm BTS gần nhất.</string>\n\t<key>NSLocationAlwaysAndWhenInUseUsageDescription</key>\n\t<string>BTS Manager cần quyền vị trí để hỗ trợ chức năng xác định các trạm BTS gần nhất.</string>\n'''
if 'NSLocationWhenInUseUsageDescription' not in s:
    s=s.replace(needle, insert+needle, 1)
elif 'NSLocationAlwaysAndWhenInUseUsageDescription' not in s:
    extra='''\n\t<key>NSLocationAlwaysAndWhenInUseUsageDescription</key>\n\t<string>BTS Manager cần quyền vị trí để hỗ trợ chức năng xác định các trạm BTS gần nhất.</string>\n'''
    s=s.replace(needle, extra+needle, 1)
p.write_text(s)

# Flutter 3.44+ uses Swift Package Manager by default. All current iOS
# plugins in this app support SPM, so remove the legacy CocoaPods integration
# instead of maintaining a custom Podfile. This avoids pod install/workspace
# selection failures and does not change Dart/runtime logic.
for name in ('Podfile', 'Podfile.lock'):
    f=Path('ios')/name
    if f.exists():
        f.unlink()
for name in ('Pods', '.symlinks'):
    d=Path('ios')/name
    if d.exists() and d.is_dir():
        import shutil
        shutil.rmtree(d)

# Remove stale CocoaPods xcconfig includes if Flutter generated any.
for f in (Path('ios/Flutter/Debug.xcconfig'), Path('ios/Flutter/Release.xcconfig')):
    if f.exists():
        lines=f.read_text().splitlines()
        lines=[line for line in lines if 'Pods/Target Support Files' not in line]
        f.write_text('\n'.join(lines)+'\n')

# Fixed bundle identifier for the iOS target.
for f in [Path('ios/Runner.xcodeproj/project.pbxproj')]:
    s=f.read_text()
    s=s.replace('PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.btsManagerMobile;', 'PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.mobile;')
    s=s.replace('PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.bts_manager_mobile;', 'PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.mobile;')
    f.write_text(s)

# Keep the same BTS Manager icon used by PC/APK.
asset=Path('assets/bts_manager_icon_ios.png')
appicon=Path('ios/Runner/Assets.xcassets/AppIcon.appiconset')
appicon.mkdir(parents=True, exist_ok=True)
(appicon/'bts_manager_icon_ios.png').write_bytes(asset.read_bytes())
(appicon/'Contents.json').write_text('''{
  "images" : [
    {
      "filename" : "bts_manager_icon_ios.png",
      "idiom" : "ios-marketing",
      "scale" : "1x",
      "size" : "1024x1024"
    }
  ],
  "info" : {
    "author" : "xcode",
    "version" : 1
  }
}
''')
PY
