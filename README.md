# Local-first Telegram Financial Assistant

Bot offline-first en Python para Telegram que procesa audios/textos financieros en español chileno, extrae una o varias transacciones CLP, distingue ingresos vs gastos, guarda en SQLite y responde reportes en español con PNG.

## Arquitectura híbrida obligatoria

```text
audio / texto Telegram
↓
whisper.cpp (solo audio)
↓
normalizador de texto
↓
prefiltro financiero
↓
parser determinístico multi-transacción
↓
detector de ambigüedad
↓
Qwen2.5 vía llama.cpp SOLO si hay ambigüedad
↓
fusión final
↓
SQLite + respuesta Telegram / dashboard PNG
```

El parser determinístico es la fuente principal. Qwen **no** crea transacciones por defecto: solo se invoca como fallback cuando falta claridad semántica, hay baja confianza, no se puede decidir income/expense o el parser no pudo resolver una intención financiera.

## Qué soporta el parser determinístico

- Múltiples transacciones en una misma frase.
- Montos CLP numéricos y hablados: `12.500`, `2500`, `2k`, `cinco mil`, `21 mil 500`.
- Slang chileno: `luca`, `lucas`, `luka`, `lukas`, `gamba`, `gambas`, `palo`, `palos`.
- Frases como `3 lucas y media` → `3500` CLP.
- Ingresos por contexto: `me transfirió`, `me pagaron`, `recibí`, `me devolvieron`, `depositaron`, `me dieron`, `me ingresaron`, `sueldo`, `salario`.
- Gastos por contexto: `compré`, `gasté`, `pagué`, `salió`, `costó`, `pedí`, `consumí`.

Ejemplos esperados:

- `Mi mamá me transfirió cinco mil pesos` → ingreso `5000` CLP.
- `Anoche compré sushi por 12 lucas y después un café por 2500` → dos gastos: `12000` y `2500` CLP.
- `Me devolvieron 15 mil` → ingreso `15000` CLP.
- `Tuve un gasto de 2 mil` → gasto `2000` CLP.

## Qwen + llama.cpp

Qwen2.5 se ejecuta localmente con `llama-cli` y JSON Schema nativo para evitar generaciones infinitas. No se usa `--stop` porque algunas builds no lo soportan.

Parámetros CPU-only:

- Contexto chico (`-c 512`).
- Pocos tokens (`-n 32` por defecto, configurable).
- `--temp 0`, `--top-k 1`, `--top-p 0`.
- `--no-perf`.
- `--json-schema` con un objeto que obliga `intent`, `transactions` y `report_period`.
- Timeout corto: `QWEN_TIMEOUT_SECONDS=20`.

El prompt es breve y exige solo JSON válido, sin markdown ni explicaciones.

## Configuración Windows offline (.env)

Crea un archivo `.env` como este o usa el incluido con placeholders:

```env
TELEGRAM_BOT_TOKEN=###########
AUTHORIZED_TELEGRAM_USER_ID=###########

WHISPER_CPP_BINARY=../whisper.cpp/build/bin/whisper-cli.exe
WHISPER_MODEL_PATH=../whisper.cpp/models/ggml-medium.bin

DATABASE_PATH=./data/finance.sqlite3
DATA_DIR=./data

WHISPER_THREADS=6
WHISPER_LANGUAGE=es

FFMPEG_BINARY=ffmpeg

QWEN_ENABLED="1"
QWEN_RUNNER_BINARY="../llama-b9204-bin-win-cpu-x64/llama-cli.exe"
QWEN_MODEL_PATH="../qwen2.5-1.5b-instruct-q4_k_m.gguf"

QWEN_THREADS="10"
QWEN_MAX_TOKENS="48"
QWEN_TIMEOUT_SECONDS="20"
QWEN_CONTEXT_TOKENS="512"

LLAMA_ARG_THREADS=10
LLAMA_ARG_CTX_SIZE=512
LLAMA_ARG_N_PREDICT=48

REPORT_DIR=./data/reports
LOG_LEVEL=INFO
```

> Nota: la aplicación lee variables del entorno. En Windows puedes cargarlas con PowerShell, `setx`, o una herramienta como `python-dotenv` si decides integrarla.

## Instalación Python

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

En Linux/macOS:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Dependencias locales

### whisper.cpp

Compila o descarga `whisper-cli.exe` y un modelo GGML, por ejemplo `ggml-medium.bin`. Configura:

```env
WHISPER_CPP_BINARY=../whisper.cpp/build/bin/whisper-cli.exe
WHISPER_MODEL_PATH=../whisper.cpp/models/ggml-medium.bin
WHISPER_LANGUAGE=es
```

### llama.cpp + Qwen2.5

Usa una build CPU de `llama-cli.exe` y un GGUF pequeño/cuantizado de Qwen2.5, por ejemplo `qwen2.5-1.5b-instruct-q4_k_m.gguf`.

Si `QWEN_ENABLED=0`, o faltan binario/modelo, el bot sigue funcionando con el parser determinístico.

### ffmpeg

`ffmpeg` debe estar en `PATH` o configurado en `FFMPEG_BINARY` para convertir audios de Telegram antes de `whisper.cpp`.

## Uso en Telegram

- Texto/audio: `gasté 12 lucas en sushi` → guarda gasto.
- Texto/audio: `me devolvieron 5 mil` → guarda ingreso.
- Texto/audio: `compré sushi por 12 lucas y después un café por 2500` → guarda dos filas.
- Mensajes casuales o sin relevancia financiera se ignoran y no llaman a Qwen.
- `/daily` o `/diario` → reporte diario.
- `/weekly` o `/semanal` → reporte semanal.
- `/monthly` o `/mensual` → reporte mensual.
- `/history` o `/historico` → histórico completo.

Los reportes generan PNG. Si matplotlib no está disponible o falla al guardar, se escribe un PNG fallback válido para que Telegram no rompa el flujo.

## Estructura principal

- `telegram_bot.py`: pipeline Telegram, autorización, múltiples transacciones, respuestas en español y reportes.
- `text_normalizer.py`: lowercase, remoción de acentos, puntuación, espacios y slang chileno.
- `financial_prefilter.py`: descarta conversaciones casuales/no financieras antes del parser y Qwen.
- `money_parser.py`: extracción determinística de múltiples montos CLP.
- `parser.py`: transacciones determinísticas con confidence, fragmento local, categoría y tipo preliminar.
- `ambiguity_detector.py`: decide si Qwen es necesario.
- `qwen_analyzer.py`: fallback Qwen2.5 con llama.cpp y JSON Schema nativo.
- `fusion.py`: fusiona parser + Qwen sin reemplazar montos determinísticos claros.
- `database.py`: SQLite local con SQL fijo/parametrizado.
- `reporting.py`: summaries y PNG con fallback.
- `settings.py` / `config.py`: configuración por entorno.
