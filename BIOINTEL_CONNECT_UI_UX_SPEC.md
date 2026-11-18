# BioIntel Connect UI/UX specification

The navigation catalogue contains 15 Connect pages and is healthy with no missing or duplicate paths. New pages are Messages, Scientific communities, Discover and collaborate, Stories and short videos, Live and calls, Onboarding and verification, Connect administration, and Accessibility and notifications.

UI rules:

- Streamlit 1.58 native widgets, `st.navigation` catalogue integration, Material Symbols and sentence-case labels.
- Main content stays in the workspace; horizontal containers are used for action/KPI groups and layouts use at most four columns.
- No deprecated `use_container_width` was added.
- Native bordered containers, tabs, forms, chat elements, metrics and dataframes keep pages responsive.
- Backend authorization remains authoritative; the UI reports permission failures rather than leaking hidden objects.
- English, Hindi and Hinglish are persisted user preferences. Media requires alt text/transcripts where applicable, captions default on, data-saving/reduced-motion controls persist, and audio autoplay is always off.

All 15 Connect pages passed Streamlit AppTest. Browser QA verified the new route surfaces without Streamlit exceptions or console errors; the Admin page correctly denied an unprivileged browser identity.
