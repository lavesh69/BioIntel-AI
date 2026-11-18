"""
BioIntel AI 15.6.0 — Vendor RAW Mass-Spectrometry Compatibility Module
Provides vendor file format detection (Thermo RAW, Bruker, SCIEX, Waters, Agilent) and MSConvert conversion preview.
"""

import os
import shutil
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("biointel.proteomics.vendor_raw")


class VendorRAWProteomicsEngine:
    """Vendor mass spectrometry RAW format detector and MSConvert preview engine."""

    VENDOR_EXTENSIONS = {
        ".raw": "Thermo Fisher Scientific RAW",
        ".d": "Bruker / Agilent Data Folder",
        ".wiff": "SCIEX Mass Spectrometry Data",
        ".raw_waters": "Waters MassLynx Format",
        ".mzml": "Standard Open mzML Format",
        ".mzxml": "Standard Open mzXML Format",
    }

    def inspect_vendor_file(self, file_path: str) -> Dict[str, Any]:
        """Detect vendor raw format, check MSConvert availability, and generate conversion command preview."""
        ext = os.path.splitext(file_path)[1].lower() if file_path else ""
        vendor_name = self.VENDOR_EXTENSIONS.get(ext, "Unknown / Custom Mass Spectrometry Format")

        msconvert_path = shutil.which("msconvert") or shutil.which("msconvert.exe")
        msconvert_available = msconvert_path is not None

        cmd_preview = f'msconvert "{file_path}" --mzML --32 --zlib -o "./output"' if file_path else 'msconvert "input.raw" --mzML'

        return {
            "file_path": file_path or "sample_thermo.RAW",
            "detected_vendor": vendor_name,
            "requires_conversion": ext not in [".mzml", ".mzxml"],
            "msconvert_available": msconvert_available,
            "msconvert_path": msconvert_path or "Not Found on PATH",
            "conversion_command_preview": cmd_preview,
            "status_label": "Ready for Conversion" if msconvert_available else "Vendor Conversion Software Required (MSConvert)",
        }


if __name__ == "__main__":
    raw_eng = VendorRAWProteomicsEngine()
    print("Vendor RAW Probes:")
    print(raw_eng.inspect_vendor_file("sample_thermo.RAW"))
