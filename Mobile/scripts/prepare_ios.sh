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

# Configure geolocator_apple for foreground-only location permission.
# Keep Flutter's generated Podfile dependency/target structure unchanged.
podfile=Path('ios/Podfile')
pod=podfile.read_text() if podfile.exists() else ''
marker='# BTS Manager: geolocator iOS foreground-only location permission'
if marker not in pod:
    lines=pod.splitlines()
    hook_start=None
    for i,line in enumerate(lines):
        if line.strip().startswith('post_install do |installer|'):
            hook_start=i
            break
    block=[
        '  # BTS Manager: geolocator iOS foreground-only location permission',
        '  installer.pods_project.targets.each do |target|',
        '    if target.name == "geolocator_apple"',
        '      target.build_configurations.each do |config|',
        "        defs = config.build_settings['GCC_PREPROCESSOR_DEFINITIONS']",
        "        defs = ['$(inherited)'] if defs.nil?",
        '        defs = [defs] unless defs.is_a?(Array)',
        "        defs << 'BYPASS_PERMISSION_LOCATION_ALWAYS=1' unless defs.include?('BYPASS_PERMISSION_LOCATION_ALWAYS=1')",
        "        config.build_settings['GCC_PREPROCESSOR_DEFINITIONS'] = defs",
        '      end',
        '    end',
        '  end',
    ]
    if hook_start is not None:
        depth=0
        insert_at=None
        for i in range(hook_start, len(lines)):
            st=lines[i].strip()
            if st.startswith('post_install do'):
                depth += 1
            elif ' do |' in st:
                depth += st.count(' do |')
            elif st.startswith(('if ', 'unless ', 'case ')):
                depth += 1
            if st == 'end':
                depth -= 1
                if depth == 0:
                    insert_at=i
                    break
        if insert_at is None:
            raise SystemExit('Could not locate existing post_install end')
        lines[insert_at:insert_at]=block
        pod='\n'.join(lines)+'\n'
    else:
        fallback=[
            '',
            '',
            'post_install do |installer|',
            '  installer.pods_project.targets.each do |target|',
            '    # BTS Manager: geolocator iOS foreground-only location permission',
            '    if target.name == "geolocator_apple"',
            '      target.build_configurations.each do |config|',
            "        defs = config.build_settings['GCC_PREPROCESSOR_DEFINITIONS']",
            "        defs = ['$(inherited)'] if defs.nil?",
            '        defs = [defs] unless defs.is_a?(Array)',
            "        defs << 'BYPASS_PERMISSION_LOCATION_ALWAYS=1' unless defs.include?('BYPASS_PERMISSION_LOCATION_ALWAYS=1')",
            "        config.build_settings['GCC_PREPROCESSOR_DEFINITIONS'] = defs",
            '      end',
            '    end',
            '  end',
            'end',
        ]
        pod += '\n'.join(fallback)+'\n'
    podfile.write_text(pod)

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
