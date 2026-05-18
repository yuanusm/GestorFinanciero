"""Audio conversion and transcription pipeline."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from config import Settings
from whisper_runner import transcribe_audio

LOGGER = logging.getLogger(__name__)


class AudioPipelineError(RuntimeError):
    """Raised when audio conversion or transcription fails."""


def convert_ogg_to_wav(ogg_path: Path, wav_path: Path, ffmpeg_binary: Path) -> Path:
    """Convert Telegram OGG/Opus voice audio to mono 16 kHz WAV for whisper.cpp."""
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg_binary),
        "-y",
        "-i",
        str(ogg_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        str(wav_path),
    ]
    LOGGER.info("Converting audio with ffmpeg: %s", " ".join(command))
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise AudioPipelineError(f"Failed to execute ffmpeg: {exc}") from exc

    if completed.returncode != 0:
        raise AudioPipelineError(f"ffmpeg failed: {completed.stderr.strip()}")
    return wav_path


def transcribe_voice_message(ogg_path: Path, settings: Settings) -> str:
    """Convert a saved Telegram voice message and transcribe it locally."""
    wav_path = settings.wav_dir / f"{ogg_path.stem}.wav"
    convert_ogg_to_wav(ogg_path, wav_path, settings.ffmpeg_binary)
    transcript = transcribe_audio(
        wav_path=wav_path,
        whisper_binary=settings.whisper_cpp_binary,
        model_path=settings.whisper_model_path,
        threads=settings.whisper_threads,
        language=settings.whisper_language,
    )
    if not transcript:
        raise AudioPipelineError("whisper.cpp returned an empty transcription")
    return transcript
