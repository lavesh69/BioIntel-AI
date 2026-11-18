# BioIntel AI 6.0 — Store Publishing Guide

This repository is a store-publish **source candidate** for Google Play, Apple App Store and Microsoft Store. It contains production application code, native projects, store metadata, listing assets, privacy/data-safety templates, signing-aware build scripts and CI workflows.

## What is already complete

- Android Capacitor project targeting API 36 and producing a signed Android App Bundle when upload-key secrets are supplied.
- iOS Capacitor/Xcode project with iOS 15 minimum, privacy manifest, App Store archive/export script and signing workflow.
- Windows Electron desktop project that packages the complete local BioIntel workspace into APPX and NSIS formats.
- Hosted HTTPS backend deployment using Docker Compose and Caddy.
- Production UI authentication, API-key protection, privacy export/clear controls and legal/support pages.
- Listing text, icons, screenshots, Google Play feature graphic and privacy/data-safety declarations.
- Model checksum manifest, database integrity verification and one-command store release audit.

## Google Play

1. Create/reserve application ID `com.biointel.workspace` in Play Console.
2. Enrol the app in Play App Signing and create an upload keystore.
3. Add these repository secrets:
   - `BIOINTEL_ANDROID_KEYSTORE_BASE64`
   - `BIOINTEL_ANDROID_KEYSTORE_PASSWORD`
   - `BIOINTEL_ANDROID_KEY_ALIAS`
   - `BIOINTEL_ANDROID_KEY_PASSWORD`
4. Run `.github/workflows/store-mobile.yml` or tag `v6.2.0`.
5. Upload the generated `.aab`, listing metadata, screenshots and `store/data-safety/google-play-data-safety.json` answers.
6. Complete internal-track physical-device testing before production rollout.

## Apple App Store

1. Register bundle ID `com.biointel.workspace` in Apple Developer and App Store Connect.
2. Create an Apple Distribution certificate and App Store provisioning profile.
3. Add these repository secrets:
   - `BIOINTEL_IOS_CERTIFICATE_BASE64`
   - `BIOINTEL_IOS_CERTIFICATE_PASSWORD`
   - `BIOINTEL_IOS_PROFILE_BASE64`
   - `BIOINTEL_IOS_PROFILE_NAME`
   - `BIOINTEL_IOS_TEAM_ID`
4. Run `.github/workflows/store-mobile.yml` on a macOS runner.
5. Upload the generated IPA, listing metadata, screenshots and confirm the App Privacy answers against the deployed server.
6. Complete TestFlight device testing and App Review submission.

## Microsoft Store

1. Reserve the product in Partner Center and copy its identity/publisher values.
2. Provide a Windows code-signing certificate and these repository secrets:
   - `BIOINTEL_WINDOWS_PUBLISHER`
   - `BIOINTEL_WINDOWS_PUBLISHER_NAME`
   - `BIOINTEL_WINDOWS_PUBLISHER_DISPLAY_NAME`
   - `BIOINTEL_WINDOWS_IDENTITY_NAME`
   - `BIOINTEL_WINDOWS_CERTIFICATE_BASE64`
   - `BIOINTEL_WINDOWS_CERTIFICATE_PASSWORD`
3. Run `.github/workflows/store-windows.yml` or `BUILD_STORE_RELEASE_WINDOWS.bat` on Windows.
4. Upload the generated APPX package and listing assets to Partner Center; retain the NSIS installer for direct distribution.

## Hosted mobile backend

Mobile editions are secure companion clients and require an HTTPS BioIntel server. Copy `config/store-production.example.env` to `config/store-production.env`, replace every placeholder, configure DNS, and run:

```bash
docker compose --env-file config/store-production.env -f deploy/store/docker-compose.yml up -d --build
```

The Windows desktop edition launches its own local packaged backend and does not require the hosted server for local workflows.

## Final local verification

```bash
python scripts/verify_store_release.py --strict
```

On Windows, run `VERIFY_STORE_RELEASE_WINDOWS.bat`.

## Scientific and regulatory boundary

BioIntel AI is packaged for research and education. Store packaging does not convert it into a clinically validated medical device. Regulatory clearance, laboratory validation, journal acceptance, customer acceptance and store approval are external outcomes and are not represented as completed unless genuine evidence is supplied.
