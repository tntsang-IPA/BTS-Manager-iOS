#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/prepare_ios.sh
flutter pub get
flutter build ios --release --no-codesign
rm -rf build/ios/unsigned_ipa/Payload
mkdir -p build/ios/unsigned_ipa/Payload
cp -R build/ios/iphoneos/Runner.app build/ios/unsigned_ipa/Payload/Runner.app
cd build/ios/unsigned_ipa
rm -f BTS_Manager_Mobile_V85_60_50_UNSIGNED.ipa
zip -qry BTS_Manager_Mobile_V85_60_50_UNSIGNED.ipa Payload
printf '%s\n' "IPA: $(pwd)/BTS_Manager_Mobile_V85_60_50_UNSIGNED.ipa"
