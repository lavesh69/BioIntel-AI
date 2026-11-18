#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/platform/mobile"
npm ci
npm run build
npx cap sync android
if [[ -z "${BIOINTEL_ANDROID_KEYSTORE_BASE64:-}" ]]; then
  echo "BIOINTEL_ANDROID_KEYSTORE_BASE64 is required for a signed Play Store bundle." >&2
  exit 2
fi
printf '%s' "$BIOINTEL_ANDROID_KEYSTORE_BASE64" | base64 --decode > android/upload-keystore.jks
export BIOINTEL_ANDROID_KEYSTORE_PATH="$PWD/android/upload-keystore.jks"
cd android
./gradlew clean bundleRelease
