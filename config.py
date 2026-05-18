"""Application configuration for the local-first Telegram finance bot."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    telegram_bot_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    authorized_telegram_user_id: str = field(
        default_factory=lambda: os.environ.get("AUTHORIZED_TELEGRAM_USER_ID", "$$$$")
    )
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("DATA_DIR", "data")))
    database_path: Path = field(
        default_factory=lambda: Path(os.environ.get("DATABASE_PATH", "data/finance.sqlite3"))
    )
    whisper_cpp_binary: Path = field(
        default_factory=lambda: Path(os.environ.get("WHISPER_CPP_BINARY", "whisper.cpp/build/bin/whisper-cli"))
    )
    whisper_model_path: Path = field(
        default_factory=lambda: Path(os.environ.get("WHISPER_MODEL_PATH", "whisper.cpp/models/ggml-medium.bin"))
    )
    ffmpeg_binary: Path = field(default_factory=lambda: Path(os.environ.get("FFMPEG_BINARY", "ffmpeg")))
    whisper_threads: int = field(default_factory=lambda: int(os.environ.get("WHISPER_THREADS", "4")))
    whisper_language: str = field(default_factory=lambda: os.environ.get("WHISPER_LANGUAGE", "es"))
    qwen_enabled: bool = field(default_factory=lambda: os.environ.get("QWEN_ENABLED", "0") == "1")
    qwen_runner_binary: Path = field(
        default_factory=lambda: Path(os.environ.get("QWEN_RUNNER_BINARY", "llama.cpp/build/bin/llama-cli"))
    )
    qwen_model_path: Path = field(default_factory=lambda: Path(os.environ.get("QWEN_MODEL_PATH", "models/qwen.gguf")))
    qwen_threads: int = field(default_factory=lambda: int(os.environ.get("QWEN_THREADS", "4")))
    qwen_max_tokens: int = field(default_factory=lambda: int(os.environ.get("QWEN_MAX_TOKENS", "160")))
    qwen_timeout_seconds: int = field(default_factory=lambda: int(os.environ.get("QWEN_TIMEOUT_SECONDS", "45")))

    @property
    def voice_dir(self) -> Path:
        return self.data_dir / "voice"

    @property
    def wav_dir(self) -> Path:
        return self.data_dir / "wav"

    @property
    def report_dir(self) -> Path:
        return self.data_dir / "reports"

    def ensure_directories(self) -> None:
        """Create local storage directories needed by the bot."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.voice_dir.mkdir(parents=True, exist_ok=True)
        self.wav_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    """Load settings and ensure local directories exist."""
    settings = Settings()
    settings.ensure_directories()
    return settings
