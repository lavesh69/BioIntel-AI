"""Qualify the bundled Education speech-to-text runtime without network access."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.local_transcription import (  # noqa: E402
    local_transcription_readiness,
    transcribe_local,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Qualify BioIntel local lecture transcription")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--audio", default="")
    parser.add_argument("--language", default="auto", choices=("auto", "english", "hindi", "hinglish"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    readiness = local_transcription_readiness(root)
    payload: dict[str, object] = {
        "schema": "biointel.education.transcription-qualification.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "readiness": readiness,
        "functional_test": {"executed": False, "passed": False},
    }
    exit_code = 0 if readiness["ready"] else 1
    if args.audio and readiness["ready"]:
        try:
            result = transcribe_local(args.audio, root=root, language=args.language)
            payload["functional_test"] = {
                "executed": True,
                "passed": bool(result["text"] and result["segment_count"]),
                "source_path": result["source_path"],
                "source_size_bytes": result["source_size_bytes"],
                "source_sha256": result["source_sha256"],
                "detected_language": result["detected_language"],
                "language_probability": result["language_probability"],
                "duration_seconds": result["duration_seconds"],
                "segment_count": result["segment_count"],
                "transcript_excerpt": result["text"][:500],
                "model_manifest_sha256": result["model_manifest_sha256"],
                "network_used": result["network_used"],
            }
            exit_code = 0 if payload["functional_test"]["passed"] else 1
        except Exception as exc:
            payload["functional_test"] = {
                "executed": True,
                "passed": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
            exit_code = 1
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())