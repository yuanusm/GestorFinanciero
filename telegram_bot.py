"""Telegram entry point for the local-first financial assistant bot."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from audio_pipeline import AudioPipelineError, transcribe_voice_message
from settings import Settings, load_settings
from ambiguity_detector import detect_ambiguity
from database import Transaction, initialize_database, insert_transaction
from financial_prefilter import is_financially_relevant
from fusion import fuse_transactions
from intent_router import ReportPeriod, route_intent
from parser import parse_transactions
from qwen_analyzer import QwenAnalysisError, analyze_with_qwen
from reporting import export_report_charts, format_summary, generate_summary
from whisper_runner import WhisperError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger(__name__)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process authorized Telegram voice messages through the local pipeline."""
    settings: Settings = context.application.bot_data["settings"]
    if not _is_authorized(update, settings):
        LOGGER.info("Ignoring message from unauthorized user")
        return
    if update.message is None or update.message.voice is None:
        return

    voice = update.message.voice
    ogg_path = settings.voice_dir / f"{voice.file_unique_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.ogg"
    try:
        telegram_file = await context.bot.get_file(voice.file_id)
        await telegram_file.download_to_drive(custom_path=ogg_path)
        transcript = transcribe_voice_message(ogg_path, settings)
    except (AudioPipelineError, WhisperError, OSError) as exc:
        LOGGER.exception("Voice transcription failed")
        await update.message.reply_text("No pude procesar el audio de forma segura. Revisa los logs locales para más detalles.")
        return

    await update.message.reply_text(f"🎙️ Transcripción: {transcript}")
    await _handle_text_intent(update, context, transcript)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process authorized Spanish text messages without requiring voice input."""
    settings: Settings = context.application.bot_data["settings"]
    if not _is_authorized(update, settings):
        LOGGER.info("Ignoring message from unauthorized user")
        return
    if update.message is None or update.message.text is None:
        return
    await _handle_text_intent(update, context, update.message.text)


async def daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a daily text and PNG report to the authorized user."""
    await _send_report(update, context, period="daily")


async def weekly_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a weekly text and PNG report to the authorized user."""
    await _send_report(update, context, period="weekly")


async def monthly_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a monthly text and PNG report to the authorized user."""
    await _send_report(update, context, period="monthly")


async def historical_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a full historical text and PNG report to the authorized user."""
    await _send_report(update, context, period="historical")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send Spanish usage help."""
    settings: Settings = context.application.bot_data["settings"]
    if not _is_authorized(update, settings) or update.message is None:
        return
    await update.message.reply_text(
        "Puedo registrar gastos e ingresos desde audios o texto.\n"
        "Ejemplos:\n"
        "- gasté 12 lucas en sushi\n"
        "- me devolvieron 5 mil\n\n"
        "Reportes disponibles:\n"
        "/daily o /diario\n"
        "/weekly o /semanal\n"
        "/monthly o /mensual\n"
        "/history o /historico"
    )


async def _handle_text_intent(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if update.message is None:
        return
    if not is_financially_relevant(text):
        LOGGER.info("Ignoring non-financial message before Qwen fallback")
        return

    intent = route_intent(text)
    if intent.intent_type == "report" and intent.report_period is not None:
        await _send_report(update, context, period=intent.report_period)
        return

    settings: Settings = context.application.bot_data["settings"]
    parsed = parse_transactions(text)
    ambiguity = detect_ambiguity(parsed)
    semantic = None
    if ambiguity.needs_qwen:
        LOGGER.info("Using Qwen fallback: %s", ambiguity.reason)
        try:
            semantic = analyze_with_qwen(text, settings)
            if semantic is not None and semantic.raw_output:
                await update.message.reply_text(f"🤖 Raw LLM: {semantic.raw_output}")
        except QwenAnalysisError:
            LOGGER.exception("Local Qwen fallback failed; continuing with deterministic parser")

    if semantic is not None and semantic.intent == "dashboard":
        await _send_report(update, context, period=semantic.report_period or "weekly")
        return

    transactions = fuse_transactions(text, parsed, semantic)
    if not transactions:
        await update.message.reply_text(
            "Entendí que el mensaje era financiero, pero no pude detectar una transacción clara. "
            "Puedes decir, por ejemplo: 'gasté 12 lucas en sushi'."
        )
        return

    saved_ids: list[int] = []
    try:
        for transaction in transactions:
            saved_ids.append(insert_transaction(settings.database_path, transaction))
    except ValueError:
        LOGGER.exception("Rejected invalid transaction")
        await update.message.reply_text("No pude guardar la transacción porque los datos no son válidos.")
        return

    await update.message.reply_text(_format_saved_transactions(saved_ids, transactions, text))


def _analyze_transaction(text: str, settings: Settings) -> Transaction | None:
    """Backward-compatible single transaction analyzer used by older callers/tests."""
    if not is_financially_relevant(text):
        return None
    parsed = parse_transactions(text)
    ambiguity = detect_ambiguity(parsed)
    semantic = None
    if ambiguity.needs_qwen:
        try:
            semantic = analyze_with_qwen(text, settings)
        except QwenAnalysisError:
            LOGGER.exception("Local Qwen fallback failed; continuing with deterministic parser")
    transactions = fuse_transactions(text, parsed, semantic)
    return transactions[0] if transactions else None


async def _send_report(update: Update, context: ContextTypes.DEFAULT_TYPE, period: ReportPeriod) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not _is_authorized(update, settings):
        return
    if update.message is None:
        return

    summary = generate_summary(settings.database_path, period)
    await update.message.reply_text(format_summary(summary))
    try:
        chart_paths = export_report_charts(summary, settings.report_dir)
        for chart_path in chart_paths:
            with chart_path.open("rb") as chart_file:
                await update.message.reply_photo(photo=chart_file)
    except (RuntimeError, OSError) as exc:
        LOGGER.exception("Report chart export failed")
        await update.message.reply_text("No pude generar los PNG del reporte. Revisa que matplotlib esté instalado localmente.")


def _format_saved_transactions(saved_ids: list[int], transactions: list[Transaction], raw_text: str) -> str:
    header = "✅ Transacción guardada" if len(transactions) == 1 else f"✅ {len(transactions)} transacciones guardadas"
    lines = [header, f"Texto: {raw_text}"]
    for row_id, transaction in zip(saved_ids, transactions, strict=True):
        lines.extend(
            [
                "",
                f"ID: {row_id}",
                f"Tipo: {_type_label(transaction.transaction_type)}",
                f"Categoría: {transaction.category}",
                f"Descripción: {transaction.description}",
                f"Monto: ${transaction.amount_clp:,} CLP",
            ]
        )
    return "\n".join(lines)


def _is_authorized(update: Update, settings: Settings) -> bool:
    user = update.effective_user
    return user is not None and str(user.id) == settings.authorized_telegram_user_id


def _type_label(transaction_type: str) -> str:
    return "ingreso" if transaction_type == "income" else "gasto"


def build_application(settings: Settings) -> Application:
    """Build the python-telegram-bot application."""
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN must be set")

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["settings"] = settings
    application.add_handler(CommandHandler(["daily", "diario"], daily_report))
    application.add_handler(CommandHandler(["weekly", "semanal"], weekly_report))
    application.add_handler(CommandHandler(["monthly", "mensual"], monthly_report))
    application.add_handler(CommandHandler(["history", "historico", "histórico"], historical_report))
    application.add_handler(CommandHandler(["start", "help", "ayuda"], help_command))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return application


def main() -> None:
    """Initialize local storage and start Telegram polling."""
    settings = load_settings()
    initialize_database(settings.database_path)
    application = build_application(settings)
    LOGGER.info("Starting local-first Telegram finance bot")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
