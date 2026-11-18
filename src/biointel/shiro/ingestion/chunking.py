from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from biointel.shiro.ingestion.extractors import ExtractedSection

CHUNKING_VERSION = "document-aware-v1"


@dataclass(frozen=True)
class ChunkDraft:
    text: str
    location: str
    section: str
    ordinal: int


def _split_text(text: str, maximum: int, overlap: int) -> list[str]:
    clean = re.sub(r"[ \t]+", " ", text.replace("\x00", " "))
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    if len(clean) <= maximum:
        return [clean] if clean else []
    pieces: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + maximum)
        if end < len(clean):
            candidates = [clean.rfind("\n\n", start + maximum // 2, end), clean.rfind("\n", start + maximum // 2, end), clean.rfind(". ", start + maximum // 2, end), clean.rfind("; ", start + maximum // 2, end), clean.rfind(" ", start + maximum // 2, end)]
            boundary = max(candidates)
            if boundary > start:
                end = boundary + (2 if clean[boundary:boundary + 2] == ". " else 1)
        value = clean[start:end].strip()
        if value:
            pieces.append(value)
        if end >= len(clean):
            break
        start = max(start + 1, end - min(overlap, maximum // 4))
    return pieces


def chunk_sections(sections: Sequence[ExtractedSection], maximum: int = 1600, overlap: int = 160) -> tuple[ChunkDraft, ...]:
    drafts: list[ChunkDraft] = []
    for section in sections:
        for part_index, part in enumerate(_split_text(section.text, maximum, overlap), start=1):
            location = section.location if part_index == 1 else f"{section.location}, part {part_index}"
            drafts.append(ChunkDraft(part, location, section.section, len(drafts) + 1))
    return tuple(drafts)
