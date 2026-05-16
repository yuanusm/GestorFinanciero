# Local-first Telegram Financial Assistant

A CPU-only Python 3.11 Telegram bot that receives voice notes from one authorized user, transcribes them with local `whisper.cpp`, parses deterministic Spanish financial phrases, and stores transactions in SQLite.

## What runs locally

- Telegram integration uses `python-telegram-bot`; Telegram itself is the only network dependency needed to receive bot messages.
- Speech-to-text runs with `whisper.cpp` through `subprocess.run()`.
- Storage is local SQLite.
- Parsing is regex-based and deterministic; no LLMs, cloud APIs, OpenAI APIs, web frameworks, Docker, n8n, PostgreSQL, or CUDA are used.

## Hardware target

Designed for CPU-only use on an Intel i7-7700 with 16 GB RAM. The default whisper.cpp thread count is `4` to keep RAM and CPU use predictable with the medium model.

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

## Initialize SQLite

The application initializes SQLite automatically on startup. To initialize manually:

```bash
sqlite3 data/finance.sqlite3 < schema.sql
```

## Run

```bash
python telegram_bot.py
```

## Telegram commands

- Send a voice note like `gasté 12 lucas en sushi` to save an expense of `12000` CLP in the `food` category.
- Send a voice note like `me devolvieron 5 mil` to save income of `5000` CLP in the `transfer` category.
- `/daily` sends a daily text summary and PNG chart.
- `/weekly` sends a weekly text summary and PNG chart.

## Project structure

- `telegram_bot.py` handles Telegram authorization, voice downloads, replies, and report sending.
- `audio_pipeline.py` converts OGG/Opus to WAV with ffmpeg.
- `whisper_runner.py` executes whisper.cpp with JSON output.
- `parser.py` extracts amount, transaction type, category, and description with regex/rules.
- `database.py` initializes and writes SQLite transactions.
- `reporting.py` creates daily/weekly summaries and PNG charts.
- `config.py` centralizes local paths and environment variables.
- `schema.sql` contains the SQLite initialization SQL.
