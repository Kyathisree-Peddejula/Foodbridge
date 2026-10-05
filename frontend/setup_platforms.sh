#!/usr/bin/env bash
# Generates the android/ ios/ web platform folders (existing lib/, web/index.html, test/ are kept)
# and applies camera + local-HTTP settings needed by the barcode scanner and dev backend.
set -euo pipefail
cd "$(dirname "$0")"
flutter create . --project-name foodbridge --org dev.foodbridge --platforms=web,android,ios
flutter pub get

# Android: allow http:// to the dev backend (10.0.2.2) and declare camera use.
MANIFEST=android/app/src/main/AndroidManifest.xml
if ! grep -q 'android.permission.CAMERA' "$MANIFEST"; then
  perl -0pi -e 's#<application#<uses-permission android:name="android.permission.INTERNET"/>\n    <uses-permission android:name="android.permission.CAMERA"/>\n    <application android:usesCleartextTraffic="true"#' "$MANIFEST"
fi
# mobile_scanner needs minSdk 21+
GRADLE=$(ls android/app/build.gradle* | head -1)
perl -pi -e 's/minSdk = flutter.minSdkVersion/minSdk = 21/; s/minSdkVersion flutter.minSdkVersion/minSdkVersion 21/' "$GRADLE"

# iOS: camera usage string + allow local HTTP during development.
PLIST=ios/Runner/Info.plist
if ! grep -q NSCameraUsageDescription "$PLIST"; then
  # first <dict> only (the root dictionary)
  perl -0pi -e 's#<dict>#<dict>\n\t<key>NSCameraUsageDescription</key>\n\t<string>FoodBridge scans product barcodes and QR codes to update inventory.</string>\n\t<key>NSAppTransportSecurity</key>\n\t<dict><key>NSAllowsArbitraryLoads</key><true/></dict>#' "$PLIST"
fi
echo "Platforms ready. Run: flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000/api"
