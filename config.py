"""Application configuration for the local-first Telegram finance bot."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip().strip('"').strip("'")


def _env_int(name: str, default: str) -> int:
    return int(_env(name, default))


def _env_bool(name: str, default: str = "0") -> bool:
    return _env(name, default).lower() in {"1", "true", "yes", "on"}


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load a tiny Windows-compatible .env file without adding dependencies."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    telegram_bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN", ""))
    authorized_telegram_user_id: str = field(default_factory=lambda: _env("AUTHORIZED_TELEGRAM_USER_ID", "$$$$"))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", "data")))
    database_path: Path = field(default_factory=lambda: Path(_env("DATABASE_PATH", "data/finance.sqlite3")))
    whisper_cpp_binary: Path = field(
        default_factory=lambda: Path(_env("WHISPER_CPP_BINARY", "whisper.cpp/build/bin/whisper-cli"))
    )
    whisper_model_path: Path = field(
        default_factory=lambda: Path(_env("WHISPER_MODEL_PATH", "whisper.cpp/models/ggml-medium.bin"))
    )
    ffmpeg_binary: Path = field(default_factory=lambda: Path(_env("FFMPEG_BINARY", "ffmpeg")))
    whisper_threads: int = field(default_factory=lambda: _env_int("WHISPER_THREADS", "4"))
    whisper_language: str = field(default_factory=lambda: _env("WHISPER_LANGUAGE", "es"))
    qwen_enabled: bool = field(default_factory=lambda: _env_bool("QWEN_ENABLED", "0"))
    qwen_runner_binary: Path = field(
        default_factory=lambda: Path(_env("QWEN_RUNNER_BINARY", "llama.cpp/build/bin/llama-cli"))
    )
    qwen_model_path: Path = field(default_factory=lambda: Path(_env("QWEN_MODEL_PATH", "models/qwen.gguf")))
    qwen_threads: int = field(default_factory=lambda: _env_int("QWEN_THREADS", _env("LLAMA_ARG_THREADS", "4")))
    qwen_max_tokens: int = field(
        default_factory=lambda: _env_int("QWEN_MAX_TOKENS", _env("LLAMA_ARG_N_PREDICT", "32"))
    )
    qwen_context_tokens: int = field(
        default_factory=lambda: _env_int("QWEN_CONTEXT_TOKENS", _env("LLAMA_ARG_CTX_SIZE", "512"))
    )
    qwen_timeout_seconds: int = field(default_factory=lambda: _env_int("QWEN_TIMEOUT_SECONDS", "20"))
    report_dir_override: Path | None = field(
        default_factory=lambda: Path(_env("REPORT_DIR")) if _env("REPORT_DIR") else None
    )

    @property
    def voice_dir(self) -> Path:
        return self.data_dir / "voice"

    @property
    def wav_dir(self) -> Path:
        return self.data_dir / "wav"

    @property
    def report_dir(self) -> Path:
        return self.report_dir_override or self.data_dir / "reports"

    def ensure_directories(self) -> None:
        """Create local storage directories needed by the bot."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.voice_dir.mkdir(parents=True, exist_ok=True)
        self.wav_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    """Load settings from the environment/.env and ensure local directories exist."""
    _load_dotenv()
    settings = Settings()
    settings.ensure_directories()
    return settings
