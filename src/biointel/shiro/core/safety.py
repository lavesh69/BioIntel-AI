from __future__ import annotations

import re

_CLINICAL = re.compile(
    r"\b(?:diagnose|diagnosis|prescribe|prescription|dose|dosage|should i take|treatment for me|"
    r"patient-specific|emergency symptom|इलाज|दवा|खुराक|निदान)\b",
    re.IGNORECASE,
)
_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"reveal\s+(?:the\s+)?(?:system prompt|secrets?|api keys?)", re.IGNORECASE),
    re.compile(r"send\s+(?:all\s+)?files?\s+(?:outside|externally|to)", re.IGNORECASE),
    re.compile(r"execute\s+(?:this\s+)?(?:command|code|script)", re.IGNORECASE),
    re.compile(r"change\s+(?:the\s+)?system settings?", re.IGNORECASE),
)
_SECRET = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{16,})\b")


def is_clinical_request(text: str) -> bool:
    return bool(_CLINICAL.search(text))


def neutralize_untrusted_text(text: str) -> tuple[str, tuple[str, ...]]:
    clean = text.replace("\x00", " ")
    detections: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(clean):
            detections.append(pattern.pattern)
            clean = pattern.sub("[UNTRUSTED INSTRUCTION REMOVED]", clean)
    return clean, tuple(detections)


def redact_secrets(text: str) -> str:
    return _SECRET.sub("[REDACTED SECRET]", text)


def clinical_safety_message(language_code: str) -> str:
    if language_code == "hi":
        return (
            "मैं शोध-साक्ष्य समझा सकता हूँ, लेकिन रोग-निदान, दवा, खुराक या व्यक्तिगत उपचार निर्णय नहीं दे सकता। "
            "कृपया योग्य चिकित्सक से सलाह लें; आप चाहें तो मैं उपलब्ध शोध-साक्ष्य और उसकी सीमाएँ संक्षेप में बता सकता हूँ।"
        )
    if language_code == "hi-Latn":
        return (
            "Main research evidence explain kar sakta hoon, lekin diagnosis, medicine, dose ya patient-specific "
            "treatment decision nahi de sakta. Qualified clinician se review karayein; main evidence aur limitations summarize kar sakta hoon."
        )
    return (
        "I can explain research evidence, but I cannot provide diagnosis, medication, dosage, or patient-specific treatment decisions. "
        "Please seek review from a qualified clinician; I can summarize the available evidence and its limitations."
    )
