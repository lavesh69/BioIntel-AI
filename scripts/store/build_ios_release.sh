#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MOBILE="$ROOT/platform/mobile"
cd "$MOBILE"
npm ci
npm run build
npx cap sync ios
: "${BIOINTEL_IOS_TEAM_ID:?BIOINTEL_IOS_TEAM_ID is required}"
: "${BIOINTEL_IOS_PROFILE_NAME:?BIOINTEL_IOS_PROFILE_NAME is required}"
mkdir -p build/export
cat > build/ExportOptions.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>method</key><string>app-store-connect</string>
<key>teamID</key><string>${BIOINTEL_IOS_TEAM_ID}</string>
<key>signingStyle</key><string>manual</string>
<key>stripSwiftSymbols</key><true/>
<key>uploadBitcode</key><false/>
</dict></plist>
EOF
xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Release \
  -archivePath "$MOBILE/build/BioIntelAI.xcarchive" \
  DEVELOPMENT_TEAM="$BIOINTEL_IOS_TEAM_ID" \
  CODE_SIGN_STYLE=Manual \
  CODE_SIGN_IDENTITY="Apple Distribution" \
  PROVISIONING_PROFILE_SPECIFIER="$BIOINTEL_IOS_PROFILE_NAME" \
  clean archive
xcodebuild -exportArchive \
  -archivePath "$MOBILE/build/BioIntelAI.xcarchive" \
  -exportPath "$MOBILE/build/export" \
  -exportOptionsPlist "$MOBILE/build/ExportOptions.plist"
