# BioIntel Connect browser matrix

## Executed

| Surface | Browser/runtime | Result |
|---|---|---|
| Streamlit page execution | Streamlit 1.58 AppTest | 15/15 Connect pages passed |
| Local interactive render | Codex in-app Chromium browser | New Connect routes rendered without page exceptions or console errors |
| Authorization | Local browser viewer on Admin page | Correctly denied with administrative-role message |
| Navigation | BioIntel page catalogue | Healthy; no missing or duplicate Connect paths |

Validated headings/routes: Messages, Scientific communities, Discover and collaborate, Stories and short videos, Live and calls, Onboarding and verification, Connect administration, Accessibility and notifications.

## Compatibility target

The application uses standard Streamlit 1.58 widgets and supports current Chromium, Edge, Firefox and Safari engines at normal desktop/mobile breakpoints. Native controls preserve keyboard and screen-reader semantics. Audio autoplay is disabled. Transcripts/alt text are required for short video; captions and data-saving preferences are persistent.

Cross-engine cloud-device execution was not available in this local run, so it is a documented target rather than an executed claim.
