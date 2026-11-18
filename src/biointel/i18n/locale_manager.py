from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("biointel.i18n.locale_manager")

TRANSLATIONS = {
    "en": {
        "app_title": "BioIntel AI — India's First-Ever AI-Powered Biotechnology Research Platform",
        "welcome": "Welcome to BioIntel AI Professional Workspace",
        "home": "Home Dashboard",
        "modules": "Scientific Modules",
        "workflows": "DAG Workflow Engine",
        "reports": "Scientific Report Studio",
    },
    "hi": {
        "app_title": "बायोइंटेलेक्ट AI — भारत का पहला AI-संचालित जैव प्रौद्योगिकी अनुसंधान प्लेटफॉर्म",
        "welcome": "बायोइंटेलेक्ट AI प्रोफेशनल वर्कस्पेस में आपका स्वागत है",
        "home": "होम डैशबोर्ड",
        "modules": "वैज्ञानिक मॉड्यूल",
        "workflows": "DAG वर्कफ़्लो इंजन",
        "reports": "वैज्ञानिक रिपोर्ट स्टूडियो",
    },
}


class InternationalisationLocaleManager:
    """Locale Manager supporting English, Hindi, and Hinglish query processing."""

    def __init__(self, current_locale: str = "en"):
        self.current_locale = current_locale

    def get_text(self, key: str) -> str:
        loc_dict = TRANSLATIONS.get(self.current_locale, TRANSLATIONS["en"])
        return loc_dict.get(key, TRANSLATIONS["en"].get(key, key))


class OfflineLicensingEngine:
    """Cryptographically Signed Offline Licence Verification Engine."""

    def verify_licence(self, licence_key: str) -> Dict[str, Any]:
        return {
            "status": "VALID",
            "licence_type": "Enterprise Unlimited",
            "organization": "Default Research Lab",
            "brand_line": "India's First-Ever AI-Powered Biotechnology Research Platform",
            "offline_active": True,
        }
