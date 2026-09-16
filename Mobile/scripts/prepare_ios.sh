#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Add only the iOS platform; preserve the existing Android/Dart project.
flutter create --platforms=ios --org com.btsmanager .

python3 - <<'PY'
from pathlib import Path
import re
import json

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

# Fixed bundle identifier and force the generated Xcode target to use the
# explicit Runner/Info.plist file. This avoids any generated-plist ambiguity.
f=Path('ios/Runner.xcodeproj/project.pbxproj')
s=f.read_text()
s=s.replace('PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.btsManagerMobile;', 'PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.mobile;')
s=s.replace('PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.bts_manager_mobile;', 'PRODUCT_BUNDLE_IDENTIFIER = com.btsmanager.mobile;')

privacy = {
    'NSLocationWhenInUseUsageDescription': 'BTS Manager cần quyền vị trí để xác định vị trí hiện tại và tính khoảng cách đến các trạm BTS gần nhất.',
    'NSLocationAlwaysAndWhenInUseUsageDescription': 'BTS Manager cần quyền vị trí để hỗ trợ chức năng xác định các trạm BTS gần nhất.',
    'NSLocationAlwaysUsageDescription': 'BTS Manager cần quyền vị trí để hỗ trợ chức năng xác định các trạm BTS gần nhất.',
}

# Make every Xcode build configuration explicitly consume Runner/Info.plist.
# This is deliberately limited to iOS project generation; no Dart/runtime code changes.
def patch_build_settings(m):
    block=m.group(0)
    block=re.sub(r'(?m)^\s*GENERATE_INFOPLIST_FILE = YES;\s*\n', '', block)
    if 'GENERATE_INFOPLIST_FILE = NO;' not in block:
        block=block.replace('buildSettings = {\n', 'buildSettings = {\n\t\t\tGENERATE_INFOPLIST_FILE = NO;\n', 1)
    if 'INFOPLIST_FILE = Runner/Info.plist;' not in block:
        block=block.replace('buildSettings = {\n', 'buildSettings = {\n\t\t\tINFOPLIST_FILE = Runner/Info.plist;\n', 1)
    if 'ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;' not in block:
        block=block.replace('buildSettings = {\n', 'buildSettings = {\n\t\t\tASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;\n', 1)
    return block
s= re.sub(r'(?ms)buildSettings = \{.*?\n\s*\};', patch_build_settings, s)
# Ensure privacy values are present in the actual plist as the authoritative source.
f.write_text(s)

# Ensure privacy values are present in the actual plist as the authoritative source.
f.write_text(s)

plist=Path('ios/Runner/Info.plist')
ps=plist.read_text()
needle='</dict>'
for key,val in privacy.items():
    if key not in ps:
        ps=ps.replace(needle, f'\n\t<key>{key}</key>\n\t<string>{val}</string>\n'+needle, 1)
plist.write_text(ps)
PY

# Keep the same BTS Manager icon as PC/APK. Build a complete iPhone/iPad
# AppIcon asset set so iOS cannot fall back to Flutter's default icon.
# Use macOS `sips` for resizing so the GitHub macOS runner needs no Pillow/PIL package.
# Add the required 1x iPad small icons using the same source image.
asset="assets/bts_manager_icon_ios.png"
appicon="ios/Runner/Assets.xcassets/AppIcon.appiconset"
mkdir -p "$appicon"
find "$appicon" -maxdepth 1 -name '*.png' -delete

gen_icon() {
  local name="$1"
  local size="$2"
  cp "$asset" "$appicon/$name"
  sips -z "$size" "$size" "$appicon/$name" >/dev/null
}

gen_icon 'Icon-App-20x20@1x.png' 20
gen_icon 'Icon-App-20x20@2x.png' 40
gen_icon 'Icon-App-20x20@3x.png' 60
gen_icon 'Icon-App-29x29@1x.png' 29
gen_icon 'Icon-App-29x29@2x.png' 58
gen_icon 'Icon-App-29x29@3x.png' 87
gen_icon 'Icon-App-40x40@1x.png' 40
gen_icon 'Icon-App-40x40@2x.png' 80
gen_icon 'Icon-App-40x40@3x.png' 120
gen_icon 'Icon-App-60x60@2x.png' 120
gen_icon 'Icon-App-60x60@3x.png' 180
gen_icon 'Icon-App-76x76@1x.png' 76
gen_icon 'Icon-App-76x76@2x.png' 152
gen_icon 'Icon-App-83.5x83.5@2x.png' 167
gen_icon 'Icon-App-1024x1024@1x.png' 1024

python3 - <<'PY'
from pathlib import Path
import json
appicon=Path('ios/Runner/Assets.xcassets/AppIcon.appiconset')
contents={
  'images':[
    {'filename':'Icon-App-20x20@2x.png','idiom':'iphone','scale':'2x','size':'20x20'},
    {'filename':'Icon-App-20x20@3x.png','idiom':'iphone','scale':'3x','size':'20x20'},
    {'filename':'Icon-App-29x29@2x.png','idiom':'iphone','scale':'2x','size':'29x29'},
    {'filename':'Icon-App-29x29@3x.png','idiom':'iphone','scale':'3x','size':'29x29'},
    {'filename':'Icon-App-40x40@2x.png','idiom':'iphone','scale':'2x','size':'40x40'},
    {'filename':'Icon-App-40x40@3x.png','idiom':'iphone','scale':'3x','size':'40x40'},
    {'filename':'Icon-App-60x60@2x.png','idiom':'iphone','scale':'2x','size':'60x60'},
    {'filename':'Icon-App-60x60@3x.png','idiom':'iphone','scale':'3x','size':'60x60'},
    {'filename':'Icon-App-20x20@1x.png','idiom':'ipad','scale':'1x','size':'20x20'},
    {'filename':'Icon-App-20x20@2x.png','idiom':'ipad','scale':'2x','size':'20x20'},
    {'filename':'Icon-App-29x29@1x.png','idiom':'ipad','scale':'1x','size':'29x29'},
    {'filename':'Icon-App-29x29@2x.png','idiom':'ipad','scale':'2x','size':'29x29'},
    {'filename':'Icon-App-40x40@1x.png','idiom':'ipad','scale':'1x','size':'40x40'},
    {'filename':'Icon-App-40x40@2x.png','idiom':'ipad','scale':'2x','size':'40x40'},
    {'filename':'Icon-App-76x76@1x.png','idiom':'ipad','scale':'1x','size':'76x76'},
    {'filename':'Icon-App-76x76@2x.png','idiom':'ipad','scale':'2x','size':'76x76'},
    {'filename':'Icon-App-83.5x83.5@2x.png','idiom':'ipad','scale':'2x','size':'83.5x83.5'},
    {'filename':'Icon-App-1024x1024@1x.png','idiom':'ios-marketing','scale':'1x','size':'1024x1024'},
  ],
  'info':{'author':'xcode','version':1}
}
(appicon/'Contents.json').write_text(json.dumps(contents,ensure_ascii=False,indent=2)+'\n')
PY
