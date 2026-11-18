# BioIntel AI Store Submission Checklist

## Repository-side checks

- Run `python scripts/verify_store_release.py`.
- Run the full Python regression suite and mobile TypeScript build.
- Confirm the release manifest, model checksums and database integrity.
- Confirm all store screenshots match the current build.
- Confirm Privacy Policy, Terms and Support pages are deployed at stable HTTPS URLs.

## Google Play

- Reserve the final package name in Play Console.
- Create an upload keystore and enrol in Play App Signing.
- Build a signed Android App Bundle (`.aab`).
- Complete Data safety, content rating, target audience and app access forms.
- Add a reviewer account/server when login is required.
- Upload first to internal testing and verify on physical arm64 devices.

## Apple App Store

- Reserve the bundle ID and app record in App Store Connect.
- Build on macOS with a supported Xcode/iOS SDK and valid team signing.
- Confirm `PrivacyInfo.xcprivacy` and third-party SDK privacy manifests in the archive.
- Complete App Privacy, updated age rating and accessibility information.
- Provide a stable review server and dedicated demo credentials.
- Validate with TestFlight on iPhone and iPad before review.

## Microsoft Store

- Reserve the product name in Partner Center.
- Copy exact Identity Name, Publisher and Publisher Display Name values into build secrets.
- Build and inspect the AppX/MSIX package on Windows.
- Run Windows App Certification Kit and test install/update/uninstall.
- Confirm the local workspace remains in the user profile after application updates.

## Mandatory external values

The repository cannot manufacture developer accounts, legal publisher identity, certificates, provisioning profiles, store-reserved IDs, public DNS/TLS or reviewer credentials. Submission is blocked until the publisher supplies them.
