from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def transcribe_voice(content: bytes, root: str | Path, data_dir: str | Path, language: str = "auto") -> dict[str, object]:
    from biointel.education.local_transcription import transcribe_local

    voice_dir = Path(data_dir) / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".wav", dir=voice_dir, delete=False) as handle:
        handle.write(content)
        path = Path(handle.name)
    try:
        return transcribe_local(path, root=root, language=language)
    finally:
        path.unlink(missing_ok=True)


def synthesize_windows_wav(text: str, data_dir: str | Path) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Local text-to-speech is available on Windows.")
    clean = text.strip()[:12000]
    if not clean:
        raise ValueError("Text is required for speech output.")
    target_dir = Path(data_dir) / "voice"
    target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target_dir) as temp:
        temp_path = Path(temp)
        text_path = temp_path / "speech.txt"
        wav_path = temp_path / "speech.wav"
        script_path = temp_path / "speak.ps1"
        text_path.write_text(clean, encoding="utf-8")
        script_path.write_text(
            "Add-Type -AssemblyName System.Speech\n"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
            f"$s.SetOutputToWaveFile('{str(wav_path).replace("'", "''")}')\n"
            f"$s.Speak([IO.File]::ReadAllText('{str(text_path).replace("'", "''")}', [Text.Encoding]::UTF8))\n"
            "$s.Dispose()\n",
            encoding="utf-8",
        )
        completed = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)], capture_output=True, text=True, timeout=90, check=False)
        if completed.returncode != 0 or not wav_path.is_file():
            raise RuntimeError("Windows speech synthesis failed: " + completed.stderr[-500:])
        return wav_path.read_bytes()
