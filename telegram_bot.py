"""Telegram entry point for the local-first financial assistant bot."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from audio_pipeline import AudioPipelineError, transcribe_voice_message
from config import Settings, load_settings
from database import initialize_database, insert_transaction
from parser import parse_transaction
from reporting import export_summary_chart, format_summary, generate_daily_summary, generate_weekly_summary
from whisper_runner import WhisperError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger(__name__)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process authorized Telegram voice messages into stored transactions."""
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
        transaction = parse_transaction(transcript)
        if transaction is None:
            await update.message.reply_text(f"I transcribed this, but could not find an amount: {transcript}")
            return
        row_id = insert_transaction(settings.database_path, transaction)
    except (AudioPipelineError, WhisperError, OSError) as exc:
        LOGGER.exception("Voice processing failed")
        await update.message.reply_text(f"Could not process the voice message safely: {exc}")
        return

    await update.message.reply_text(
        "Transaction saved\n"
        f"ID: {row_id}\n"
        f"Text: {transcript}\n"
        f"Type: {transaction.transaction_type}\n"
        f"Category: {transaction.category}\n"
        f"Amount: ${transaction.amount_clp:,} CLP"
    )


async def daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a daily text and PNG report to the authorized user."""
    await _send_report(update, context, period="daily")


async def weekly_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a weekly text and PNG report to the authorized user."""
    await _send_report(update, context, period="weekly")


async def _send_report(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not _is_authorized(update, settings):
        return
    if update.message is None:
        return

    summary = (
        generate_daily_summary(settings.database_path)
        if period == "daily"
        else generate_weekly_summary(settings.database_path)
    )
    chart_path = export_summary_chart(summary, settings.report_dir / f"{period}_{summary.start.date()}.png")
    await update.message.reply_text(format_summary(summary))
    with chart_path.open("rb") as chart_file:
        await update.message.reply_photo(photo=chart_file)


def _is_authorized(update: Update, settings: Settings) -> bool:
    user = update.effective_user
    return user is not None and str(user.id) == settings.authorized_telegram_user_id


def build_application(settings: Settings) -> Application:
    """Build the python-telegram-bot application."""
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN must be set")

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["settings"] = settings
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(CommandHandler("daily", daily_report))
    application.add_handler(CommandHandler("weekly", weekly_report))
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
