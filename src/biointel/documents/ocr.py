from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from biointel.documents.models import ExtractedRegion


@dataclass(frozen=True)
class OCRPageResult:
    page_number: int
    text: str
    mean_confidence: float
    regions: tuple[ExtractedRegion, ...]
    requires_review: bool
    warnings: tuple[str, ...]


def ocr_pdf_page(
    pdf_data: bytes,
    page_number: int,
    *,
    language: str = "eng",
    scale: float = 2.0,
    confidence_threshold: float = 70.0,
) -> OCRPageResult:
    try:
        import pypdfium2 as pdfium
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise RuntimeError(
            "OCR requires pypdfium2 and pytesseract. Install Step 27 requirements and the "
            "Tesseract OCR engine."
        ) from exc
    document = pdfium.PdfDocument(io.BytesIO(pdf_data))
    page = None
    bitmap = None
    try:
        if page_number < 1 or page_number > len(document):
            raise ValueError("OCR page number is outside the PDF page range.")
        page = document[page_number - 1]
        bitmap = page.render(scale=max(1.0, min(float(scale), 4.0)))
        image = bitmap.to_pil()
        payload: dict[str, list[Any]] = pytesseract.image_to_data(
            image,
            lang=language,
            output_type=Output.DICT,
        )
    finally:
        if bitmap is not None:
            bitmap.close()
        if page is not None:
            page.close()
        document.close()
    width, height = image.size
    regions: list[ExtractedRegion] = []
    tokens: list[str] = []
    confidences: list[float] = []
    for index, raw_text in enumerate(payload.get("text", [])):
        text = str(raw_text or "").strip()
        if not text:
            continue
        try:
            confidence = float(payload["conf"][index])
        except (KeyError, TypeError, ValueError):
            confidence = -1.0
        x = float(payload["left"][index])
        y = float(payload["top"][index])
        w = float(payload["width"][index])
        h = float(payload["height"][index])
        normalized_bbox = (x / width, y / height, (x + w) / width, (y + h) / height)
        regions.append(
            ExtractedRegion(
                region_id=uuid4().hex,
                source=f"page:{page_number}",
                kind="ocr_word",
                text=text,
                page_number=page_number,
                bbox=normalized_bbox,
                confidence=max(0.0, confidence) / 100.0 if confidence >= 0 else None,
                metadata={"coordinate_space": "normalized_page"},
            )
        )
        tokens.append(text)
        if confidence >= 0:
            confidences.append(confidence)
    mean = sum(confidences) / max(len(confidences), 1)
    text = " ".join(tokens)
    low_numeric = [
        region
        for region in regions
        if any(char.isdigit() for char in region.text)
        and region.confidence is not None
        and region.confidence * 100 < confidence_threshold
    ]
    warnings = []
    if mean < confidence_threshold:
        warnings.append(
            f"OCR page {page_number} mean confidence is {mean:.1f}%; human review is required."
        )
    if low_numeric:
        warnings.append(
            f"OCR page {page_number} contains {len(low_numeric)} low-confidence numeric token(s)."
        )
    return OCRPageResult(
        page_number=page_number,
        text=text,
        mean_confidence=round(mean / 100.0, 4),
        regions=tuple(regions),
        requires_review=bool(mean < confidence_threshold or low_numeric or not text),
        warnings=tuple(warnings),
    )


def ocr_pdf(
    pdf_data: bytes,
    page_numbers: list[int],
    *,
    language: str = "eng",
    scale: float = 2.0,
    confidence_threshold: float = 70.0,
) -> tuple[OCRPageResult, ...]:
    return tuple(
        ocr_pdf_page(
            pdf_data,
            page_number,
            language=language,
            scale=scale,
            confidence_threshold=confidence_threshold,
        )
        for page_number in page_numbers
    )
