from __future__ import annotations

import re

from biointel.shiro.models import LanguageInfo

_DEVANAGARI = re.compile(r"[\u0900-\u097f]")
_TOKEN = re.compile(r"[^\W_]+(?:[-.:/][^\W_]+)*", re.UNICODE)
_SCIENTIFIC = re.compile(
    r"\b(?:[A-Z]{2,}[A-Z0-9-]*|rs\d+|[cgmnpr]\.[0-9_+*>A-Za-z-]+|\d+(?:\.\d+)?(?:mg|ng|µg|mM|µM|nM|bp|kb|Mb))\b"
)

_HINGLISH = {
    "kya": "what",
    "ka": "of",
    "ke": "of",
    "ki": "of",
    "hai": "is",
    "hain": "are",
    "ye": "this",
    "mere": "my",
    "mera": "my",
    "project": "project",
    "dikhao": "show",
    "batao": "explain",
    "samjhao": "explain",
    "karo": "do",
    "karna": "do",
    "result": "result",
    "results": "results",
    "report": "report",
    "evidence": "evidence",
    "function": "function",
    "gene": "gene",
    "variant": "variant",
    "pathway": "pathway",
    "cancer": "cancer",
    "mein": "in",
    "se": "from",
    "simple": "simple",
    "hindi": "hindi",
    "uploaded": "uploaded",
    "summary": "summary",
    "summarize": "summarize",
    "compare": "compare",
    "aur": "and",
    "lekin": "but",
    "nahi": "not",
    "mila": "found",
    "search": "search",
    "bahar": "external",
}


def _tokens(value: str) -> list[str]:
    return _TOKEN.findall(value)


def detect_language(query: str, preferred: str = "auto") -> LanguageInfo:
    clean = " ".join(query.strip().split())
    scientific = tuple(dict.fromkeys(_SCIENTIFIC.findall(clean)))
    words = [word.casefold() for word in _tokens(clean)]
    devanagari_count = len(_DEVANAGARI.findall(clean))
    hinglish_hits = sum(word in _HINGLISH for word in words)
    preference = preferred.strip().casefold()
    if preference in {"english", "en"}:
        code, label = "en", "English"
    elif preference in {"hindi", "hi"}:
        code, label = "hi", "Hindi"
    elif preference in {"hinglish", "hi-latn"}:
        code, label = "hi-Latn", "Hinglish"
    elif devanagari_count:
        code, label = "hi", "Hindi"
    elif hinglish_hits >= 2 or (hinglish_hits and any(word in {"kya", "batao", "dikhao", "karo"} for word in words)):
        code, label = "hi-Latn", "Hinglish"
    else:
        code, label = "en", "English"
    additions = [meaning for word in words if (meaning := _HINGLISH.get(word)) and meaning != word]
    normalized = clean
    if additions:
        normalized = clean + " " + " ".join(dict.fromkeys(additions))
    script = "Devanagari" if devanagari_count else "Latin"
    confidence = 0.98 if preference != "auto" else (0.92 if devanagari_count or hinglish_hits >= 2 else 0.8)
    return LanguageInfo(code, label, script, confidence, normalized, scientific)


def meaningful_terms(text: str) -> tuple[str, ...]:
    stop = {
        "the", "a", "an", "and", "or", "of", "in", "to", "for", "from", "is", "are",
        "this", "that", "my", "do", "what", "show", "please", "kya", "ka", "ke", "ki",
        "hai", "hain", "ye", "mere", "mera", "karo", "batao", "dikhao", "mein", "se",
    }
    return tuple(dict.fromkeys(word.casefold() for word in _tokens(text) if len(word) > 1 and word.casefold() not in stop))
