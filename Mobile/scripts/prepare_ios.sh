#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Add only the iOS platform; preserve the existing Android/Dart project.
flutter create --platforms=ios --org com.btsmanager .

python3 - <<'PY'
from pathlib import Path
p=Path('ios/Runner/Info.plist')
s=p.read_text()
needle='</dict>'
insert='''\n\t<key>CFBundleDisplayName</key>\n\t<string>BTS Manager Mobile</string>\n\t<key>NSLocationWhenInUseUsageDescription</key>\n\t<string>BTS Manager cần quyền vị trí để xác định vị trí hiện tại và tính khoảng cách đến các trạm BTS gần nhất.</string>\n'''
if 'NSLocationWhenInUseUsageDescription' not in s:
    s=s.replace(needle, insert+needle, 1)
p.write_text(s)

# Fixed bundle identifier for the iOS target.
for f in [Path('ios/Runner.xcodeproj/project.pbxproj')]:
    s=f.read_text()
    s=s.replace('PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.btsManagerMobile;', 'PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.mobile;')
    s=s.replace('PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.bts_manager_mobile;', 'PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.mobile;')
    f.write_text(s)

# Keep the existing BTS Manager icon. The source icon is already part of the final V85.60.50 source.
asset=Path('assets/bts_manager_icon_ios.png')
appicon=Path('ios/Runner/Assets.xcassets/AppIcon.appiconset')
appicon.mkdir(parents=True, exist_ok=True)
(appicon/'bts_manager_icon_ios.png').write_bytes(asset.read_bytes())
(appicon/'Contents.json').write_text('''{\n  "images" : [\n    {\n      "filename" : "bts_manager_icon_ios.png",\n      "idiom" : "ios-marketing",\n      "scale" : "1x",\n      "size" : "1024x1024"\n    }\n  ],\n  "info" : {\n    "author" : "xcode",\n    "version" : 1\n  }\n}\n''')
PY
