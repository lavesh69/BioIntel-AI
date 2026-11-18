from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from biointel.shiro.models import Citation, LanguageInfo, RetrievalResult, SourceRecord


class GenerationProvider(Protocol):
    name: str
    model: str
    external: bool

    def generate(self, question: str, evidence: Sequence[RetrievalResult], citations: Sequence[Citation], language: LanguageInfo, *, history: Sequence[dict[str, Any]] = (), attachments: Sequence[SourceRecord] = (), cancelled: Callable[[], bool] | None = None) -> str:
        ...


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    model: str
    available: bool
    external: bool
    active: bool
    detail: str
    public_name: str = ""
    healthy: bool | None = None


class GroundedLocalProvider:
    name = "local"
    model = "grounded-extractive-v2"
    external = False

    @staticmethod
    def _excerpt(text: str, maximum: int = 420) -> str:
        clean = " ".join(text.split())
        if len(clean) <= maximum:
            return clean
        boundary = clean.rfind(". ", 0, maximum)
        return clean[: boundary + 1 if boundary > maximum // 2 else maximum].rstrip() + "…"

    def generate(self, question: str, evidence: Sequence[RetrievalResult], citations: Sequence[Citation], language: LanguageInfo, *, history: Sequence[dict[str, Any]] = (), attachments: Sequence[SourceRecord] = (), cancelled: Callable[[], bool] | None = None) -> str:
        if not evidence:
            if language.code == "hi-Latn":
                return "Insufficient evidence. Main offline evidence mode mein hoon. General generative model configured nahi hai, isliye main bina project evidence ke unsupported scientific answer fabricate nahi karunga. Shiro Local Intelligence setup karein ya evidence attach karein."
            if language.code == "hi":
                return "अपर्याप्त साक्ष्य। मैं ऑफ़लाइन साक्ष्य मोड में हूँ। कोई सामान्य जनरेटिव मॉडल कॉन्फ़िगर नहीं है, इसलिए मैं बिना प्रोजेक्ट साक्ष्य के वैज्ञानिक उत्तर नहीं गढ़ूँगा। Shiro Local Intelligence सेटअप करें या साक्ष्य संलग्न करें।"
            return "Insufficient evidence. Shiro is in offline evidence mode. No general generative model is configured, so it will not fabricate an unsupported scientific answer. Configure Shiro Local Intelligence or attach project evidence."
        items = []
        max_items = min(8, len(evidence))
        for result, citation in zip(evidence[:max_items], citations[:max_items]):
            items.append(f"- {self._excerpt(result.chunk.text)} [{citation.citation_id}]")
        evidence_text = "\n".join(items)
        if language.code == "hi":
            return "उपलब्ध आंतरिक प्रोजेक्ट साक्ष्य में निम्न संबंधित जानकारी मिली:\n\n" + evidence_text + "\n\n**व्याख्या:** यह उत्तर केवल ऊपर दिए गए अंशों पर आधारित है। वैज्ञानिक पहचानकर्ता मूल रूप में रखे गए हैं।\n\n**सीमाएँ:** ये अंश पूर्ण दस्तावेज़ या स्वतंत्र जैव-चिकित्सीय सत्यापन का विकल्प नहीं हैं।"
        if language.code == "hi-Latn":
            return "Active project ke internal evidence mein ye relevant information mili:\n\n" + evidence_text + "\n\n**Interpretation:** Yeh answer sirf retrieved excerpts par based hai; scientific identifiers unchanged rakhe gaye hain.\n\n**Limitations:** In excerpts ko complete document review ya independent biomedical validation ka replacement na samjhein."
        return "The active project's internal evidence contains the following relevant information:\n\n" + evidence_text + "\n\n**Interpretation:** This answer is limited to the retrieved excerpts, with scientific identifiers preserved.\n\n**Limitations:** These excerpts do not replace review of the full source or independent biomedical validation."
