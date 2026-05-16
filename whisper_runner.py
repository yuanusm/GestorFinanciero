"""Local whisper.cpp subprocess wrapper."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class WhisperError(RuntimeError):
    """Raised when whisper.cpp fails or produces unreadable output."""


def transcribe_audio(
    wav_path: Path,
    whisper_binary: Path,
    model_path: Path,
    threads: int = 4,
    language: str = "es",
) -> str:
    """Run whisper.cpp with JSON output and return the combined transcript text."""
    output_prefix = wav_path.with_suffix("")
    command = [
        str(whisper_binary),
        "-m",
        str(model_path),
        "-f",
        str(wav_path),
        "-l",
        language,
        "-t",
        str(threads),
        "-oj",
        "-of",
        str(output_prefix),
    ]
    LOGGER.info("Running whisper.cpp: %s", " ".join(command))
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise WhisperError(f"Failed to execute whisper.cpp: {exc}") from exc

    if completed.returncode != 0:
        raise WhisperError(f"whisper.cpp failed: {completed.stderr.strip()}")

    json_path = output_prefix.with_suffix(".json")
    if not json_path.exists():
        raise WhisperError(f"Expected whisper.cpp JSON output was not created: {json_path}")

    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WhisperError(f"Invalid whisper.cpp JSON output: {json_path}") from exc

    return _extract_text(payload).strip()


def _extract_text(payload: dict[str, object]) -> str:
    transcription = payload.get("transcription")
    if isinstance(transcription, list):
        parts = [str(item.get("text", "")) for item in transcription if isinstance(item, dict)]
        return " ".join(parts)

    # Some whisper.cpp builds emit a top-level result object with segments.
    result = payload.get("result")
    if isinstance(result, dict) and isinstance(result.get("transcription"), list):
        parts = [str(item.get("text", "")) for item in result["transcription"] if isinstance(item, dict)]
        return " ".join(parts)

    text = payload.get("text")
    return str(text) if text else ""
