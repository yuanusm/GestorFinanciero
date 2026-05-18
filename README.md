# Local-first Telegram Financial Assistant

A CPU-only Python 3.11 Telegram bot that receives voice notes or text from one authorized user, transcribes voice locally with `whisper.cpp`, parses Chilean Spanish financial phrases, uses a local Qwen2.5 fallback only for ambiguous financial messages, stores transactions in SQLite, and sends Spanish financial reports with PNG charts through Telegram.

## Local-only architecture

```text
Telegram audio/text
↓
ffmpeg (voice only)
↓
WAV
↓
whisper.cpp medium model
↓
transcribed text
↓
financial pre-filter
↓
deterministic multi-amount parser
↓
ambiguity detector
↓
optional local Qwen fallback
↓
intent router
↓
SQLite storage or dashboard PNG generation
↓
Spanish Telegram response
```

The application does not use cloud APIs, OpenAI APIs, web frameworks, Docker, n8n, PostgreSQL, or CUDA. Telegram network access is only used to receive and answer bot messages.

## Hardware target

Designed for CPU-only use on an Intel i7-7700 with 16 GB RAM. Defaults use four CPU threads for `whisper.cpp` and optional local Qwen execution to keep memory and CPU load predictable.

## Configuration

Set environment variables before starting the bot:

```bash
export TELEGRAM_BOT_TOKEN="your-telegram-bot-token"
export AUTHORIZED_TELEGRAM_USER_ID="$$$$"
export WHISPER_CPP_BINARY="/absolute/path/to/whisper.cpp/build/bin/whisper-cli"
export WHISPER_MODEL_PATH="/absolute/path/to/whisper.cpp/models/ggml-medium.bin"
export DATABASE_PATH="data/finance.sqlite3"
export DATA_DIR="data"
export WHISPER_THREADS="4"
```

The authorized Telegram user ID defaults to `$$$$` in `config.py`; messages from all other users are ignored.

### Optional local Qwen semantic analysis

The deterministic parser is always the primary parser. Qwen is a fallback only: it is skipped for non-financial text and skipped whenever deterministic parsing is clear enough. To add local semantic fallback for ambiguous cases, run a small Qwen2.5 GGUF model with a local CPU runner such as `llama.cpp`:

```bash
export QWEN_ENABLED="1"
export QWEN_RUNNER_BINARY="/absolute/path/to/llama.cpp/build/bin/llama-cli"
export QWEN_MODEL_PATH="/absolute/path/to/qwen-model.gguf"
export QWEN_THREADS="4"
export QWEN_MAX_TOKENS="32"
export QWEN_CONTEXT_TOKENS="2048"
export QWEN_TIMEOUT_SECONDS="20"
```

If the local Qwen binary or model is missing, the bot logs a warning and continues with deterministic parsing only. The Qwen prompt is intentionally short, requests only JSON, and uses low generation limits (`-n 32`, `-c 2048`, `--temp 0`) for CPU-only hardware. No external LLM service is contacted.

## Install Python dependencies

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Install ffmpeg on Linux

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install ffmpeg
```

Fedora:

```bash
sudo dnf install ffmpeg
```

Arch Linux:

```bash
sudo pacman -S ffmpeg
```

## Build whisper.cpp on Linux

```bash
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
cmake -B build -DWHISPER_CUBLAS=OFF
cmake --build build --config Release -j4
bash ./models/download-ggml-model.sh medium
```

Point `WHISPER_CPP_BINARY` to `whisper.cpp/build/bin/whisper-cli` and `WHISPER_MODEL_PATH` to `whisper.cpp/models/ggml-medium.bin`.

## Optional: build llama.cpp for local Qwen

```bash
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
cmake -B build -DGGML_CUDA=OFF
cmake --build build --config Release -j4
```

Download a Qwen GGUF model manually from a trusted source and store it outside the repository or under an ignored `models/` directory. Configure `QWEN_RUNNER_BINARY` and `QWEN_MODEL_PATH` as shown above.

## Initialize SQLite

The application initializes SQLite automatically on startup. To initialize manually:

```bash
sqlite3 data/finance.sqlite3 < schema.sql
```

All database access is implemented with fixed SQL statements and parameterized values. The bot never accepts arbitrary SQL from Telegram.

## Run

```bash
python telegram_bot.py
```

## Telegram usage

All Telegram responses are written in Spanish.

- Send a voice note or text like `gasté 12 lucas en sushi` to save an expense of `12000` CLP in the `food` category.
- Send a voice note or text like `me devolvieron 5 mil` to save income of `5000` CLP in the `transfer` category.
- Send multiple transactions in one message, such as `compré sushi por 12 mil y después pagué 5 mil en Uber`, to create two SQLite rows.
- Non-financial messages are ignored before any Qwen fallback can run.
- `/daily` or `/diario` sends a daily summary and PNG charts.
- `/weekly` or `/semanal` sends a weekly summary and PNG charts.
- `/monthly` or `/mensual` sends a monthly summary and PNG charts.
- `/history` or `/historico` sends a full historical summary and PNG charts.
- Text such as `reporte semanal`, `resumen mensual`, or `resumen histórico` also triggers reports.

Each report exports and sends:

- Combined totals chart.
- Category distribution chart.
- Net trend chart.

## Project structure

- `telegram_bot.py` handles authorization, Telegram audio/text, Spanish replies, and report PNG sending.
- `audio_pipeline.py` converts OGG/Opus to WAV with ffmpeg.
- `whisper_runner.py` executes whisper.cpp with JSON output.
- `text_normalizer.py` normalizes accents, whitespace, punctuation, and Chilean money slang before parsing.
- `financial_filter.py` rejects non-financial text before any Qwen fallback is considered.
- `money_parser.py` extracts multiple CLP amounts, including `21 mil 500`, `3 lucas y media`, and `12 mil 200 pesos`.
- `parser.py` creates one or more deterministic transactions with type/category/description confidence.
- `ambiguity_detector.py` decides whether deterministic parsing is sufficient; when it is, Qwen is never called.
- `qwen_analyzer.py` optionally executes a local Qwen2.5 GGUF model through llama.cpp with strict JSON and short generation settings.
- `fusion.py` combines deterministic and fallback outputs without letting Qwen override clear amounts or generate SQL.
- `intent_router.py` detects dashboard/report intents versus transaction intents.
- `database.py` initializes and safely queries SQLite.
- `reporting.py` creates daily, weekly, monthly, and historical summaries plus PNG charts.
- `config.py` centralizes local paths and environment variables.
- `schema.sql` contains the SQLite initialization SQL.
