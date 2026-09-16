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

# Fixed bundle identifier for the iOS target and force the privacy keys into
# the final generated app Info.plist as Xcode build settings. This is in
# addition to Runner/Info.plist so the compiled .app cannot lose the keys.
f=Path('ios/Runner.xcodeproj/project.pbxproj')
s=f.read_text()
s=s.replace('PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.btsManagerMobile;', 'PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.mobile;')
s=s.replace('PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.bts_manager_mobile;', 'PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.mobile;')
privacy = {
    'INFOPLIST_KEY_NSLocationWhenInUseUsageDescription': 'BTS Manager cần quyền vị trí để xác định vị trí hiện tại và tính khoảng cách đến các trạm BTS gần nhất.',
    'INFOPLIST_KEY_NSLocationAlwaysAndWhenInUseUsageDescription': 'BTS Manager cần quyền vị trí để hỗ trợ chức năng xác định các trạm BTS gần nhất.',
    'INFOPLIST_KEY_NSLocationAlwaysUsageDescription': 'BTS Manager cần quyền vị trí để hỗ trợ chức năng xác định các trạm BTS gần nhất.',
}
# Add each privacy key to every Xcode build configuration.
# Xcode then writes the keys into the final Runner.app/Info.plist even when
# the generated project uses INFOPLIST_KEY_* build settings.
import re
for key,val in privacy.items():
    if key in s:
        pass

# Patch the generated project file itself, not the shell environment.
# Each `buildSettings = {` belongs to an XCBuildConfiguration section.
def patch_build_settings(text):
    def repl(m):
        indent=m.group(1)
        following=m.group(2)
        additions=[]
        for key,val in privacy.items():
            if re.search(rf'(?m)^\s*{re.escape(key)}\s*=', following):
                continue
            additions.append(f'{indent}\t{key} = "{val}";')
        if not additions:
            return m.group(0)
        return m.group(0) + ''.join(additions)
    # Capture only the opening line plus the next small window for duplicate detection.
    return re.sub(r'(?m)^(\s*)buildSettings = \{\n((?:[ \t]+.*\n){0,80})', repl, text)

s=patch_build_settings(s)
f.write_text(s)

# Keep the same BTS Manager icon used by PC/APK.

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
