"""Reporting utilities with summaries and PNG chart export."""

from __future__ import annotations

from collections import defaultdict
import logging
import struct
import zlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Literal

from database import StoredTransaction, fetch_all_transactions, fetch_transactions_between

ReportPeriod = Literal["daily", "weekly", "monthly", "historical"]
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Summary:
    """A summarized view of transactions in a period."""

    period: ReportPeriod
    start: datetime | None
    end: datetime | None
    income_clp: int
    expense_clp: int
    net_clp: int
    by_category: dict[str, int]
    trend_by_day: dict[date, int]
    transaction_count: int


def generate_daily_summary(database_path: Path, day: date | None = None) -> Summary:
    """Generate a transaction summary for one UTC day."""
    selected_day = day or datetime.now(timezone.utc).date()
    start = datetime.combine(selected_day, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return _summarize("daily", fetch_transactions_between(database_path, start, end), start, end)


def generate_weekly_summary(database_path: Path, week_start: date | None = None) -> Summary:
    """Generate a transaction summary for a Monday-starting UTC week."""
    today = datetime.now(timezone.utc).date()
    selected_start = week_start or (today - timedelta(days=today.weekday()))
    start = datetime.combine(selected_start, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    return _summarize("weekly", fetch_transactions_between(database_path, start, end), start, end)


def generate_monthly_summary(database_path: Path, month_start: date | None = None) -> Summary:
    """Generate a transaction summary for one UTC calendar month."""
    today = datetime.now(timezone.utc).date()
    selected = month_start or today.replace(day=1)
    start_date = selected.replace(day=1)
    if start_date.month == 12:
        next_month = start_date.replace(year=start_date.year + 1, month=1)
    else:
        next_month = start_date.replace(month=start_date.month + 1)
    start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(next_month, time.min, tzinfo=timezone.utc)
    return _summarize("monthly", fetch_transactions_between(database_path, start, end), start, end)


def generate_historical_summary(database_path: Path) -> Summary:
    """Generate a summary across the full local SQLite history."""
    transactions = fetch_all_transactions(database_path)
    start = transactions[0].timestamp if transactions else None
    end = transactions[-1].timestamp + timedelta(microseconds=1) if transactions and transactions[-1].timestamp else None
    return _summarize("historical", transactions, start, end)


def generate_summary(database_path: Path, period: ReportPeriod) -> Summary:
    """Generate a report summary by period without dynamic SQL."""
    if period == "daily":
        return generate_daily_summary(database_path)
    if period == "weekly":
        return generate_weekly_summary(database_path)
    if period == "monthly":
        return generate_monthly_summary(database_path)
    return generate_historical_summary(database_path)


def export_category_distribution_chart(summary: Summary, output_path: Path) -> Path:
    """Export a category distribution chart to PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    categories = list(summary.by_category.keys()) or ["sin gastos"]
    values = list(summary.by_category.values()) or [0]

    plt, _ = _load_matplotlib()
    fig, ax = plt.subplots(figsize=(8, 6))
    if sum(values) > 0:
        ax.pie(values, labels=categories, autopct="%1.1f%%", startangle=90)
        ax.set_title("Distribución de gastos por categoría")
    else:
        ax.bar(categories, values, color="#e76f51")
        ax.set_title("Sin gastos registrados")
        ax.set_ylabel("CLP")
    _save_figure(fig, output_path)
    plt.close(fig)
    return output_path


def export_trend_chart(summary: Summary, output_path: Path) -> Path:
    """Export a daily net cash-flow trend chart to PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    days = list(summary.trend_by_day.keys())
    values = list(summary.trend_by_day.values())

    plt, mdates = _load_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 4))
    if days:
        ax.plot(days, values, marker="o", color="#264653")
        ax.axhline(0, color="#999999", linewidth=1)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        try:
            fig.autofmt_xdate()
        except Exception:
            LOGGER.warning("matplotlib autofmt_xdate failed; continuing without date auto-format")
    else:
        ax.plot([], [])
        ax.text(0.5, 0.5, "Sin transacciones", ha="center", va="center", transform=ax.transAxes)
    ax.set_title("Tendencia diaria neta")
    ax.set_ylabel("CLP")
    _save_figure(fig, output_path)
    plt.close(fig)
    return output_path


def export_summary_chart(summary: Summary, output_path: Path) -> Path:
    """Export a combined category and total chart to PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    categories = list(summary.by_category.keys()) or ["sin gastos"]
    values = list(summary.by_category.values()) or [0]

    plt, _ = _load_matplotlib()
    fig, (ax_categories, ax_totals) = plt.subplots(1, 2, figsize=(10, 4))
    ax_categories.bar(categories, values, color="#e76f51")
    ax_categories.set_title("Gastos por categoría")
    ax_categories.set_ylabel("CLP")
    ax_categories.tick_params(axis="x", rotation=35)

    ax_totals.bar(
        ["ingresos", "gastos", "neto"],
        [summary.income_clp, summary.expense_clp, summary.net_clp],
        color=["#2a9d8f", "#e76f51", "#264653"],
    )
    ax_totals.set_title("Totales del período")
    ax_totals.set_ylabel("CLP")

    fig.suptitle(_summary_title(summary))
    _save_figure(fig, output_path)
    plt.close(fig)
    return output_path


def export_report_charts(summary: Summary, output_dir: Path) -> list[Path]:
    """Export all PNG report charts and return their paths.

    If matplotlib is unavailable or fails during chart creation, write valid PNG
    placeholders so Telegram report delivery keeps working offline.
    """
    safe_start = summary.start.date().isoformat() if summary.start else "historico"
    prefix = f"{summary.period}_{safe_start}"
    paths = [
        output_dir / f"{prefix}_resumen.png",
        output_dir / f"{prefix}_categorias.png",
        output_dir / f"{prefix}_tendencia.png",
    ]
    try:
        return [
            export_summary_chart(summary, paths[0]),
            export_category_distribution_chart(summary, paths[1]),
            export_trend_chart(summary, paths[2]),
        ]
    except RuntimeError:
        LOGGER.exception("matplotlib unavailable; writing fallback PNG report placeholders")
        for path in paths:
            _write_fallback_png(path)
        return paths


def format_summary(summary: Summary) -> str:
    """Create a compact Spanish summary for Telegram messages."""
    categories = "\n".join(f"- {category}: ${amount:,} CLP" for category, amount in summary.by_category.items())
    if not categories:
        categories = "- Sin gastos registrados"
    return (
        f"📊 {_summary_title(summary)}\n"
        f"Ingresos: ${summary.income_clp:,} CLP\n"
        f"Gastos: ${summary.expense_clp:,} CLP\n"
        f"Neto: ${summary.net_clp:,} CLP\n"
        f"Transacciones: {summary.transaction_count}\n"
        f"Por categoría:\n{categories}"
    )


def _summarize(
    period: ReportPeriod,
    transactions: list[StoredTransaction],
    start: datetime | None,
    end: datetime | None,
) -> Summary:
    income = sum(tx.amount_clp for tx in transactions if tx.transaction_type == "income")
    expense = sum(tx.amount_clp for tx in transactions if tx.transaction_type == "expense")
    by_category: dict[str, int] = defaultdict(int)
    trend_by_day: dict[date, int] = defaultdict(int)
    for transaction in transactions:
        if transaction.transaction_type == "expense":
            by_category[transaction.category] += transaction.amount_clp
            trend_by_day[transaction.timestamp.date()] -= transaction.amount_clp
        else:
            trend_by_day[transaction.timestamp.date()] += transaction.amount_clp
    return Summary(
        period=period,
        start=start,
        end=end,
        income_clp=income,
        expense_clp=expense,
        net_clp=income - expense,
        by_category=dict(sorted(by_category.items())),
        trend_by_day=dict(sorted(trend_by_day.items())),
        transaction_count=len(transactions),
    )


def _summary_title(summary: Summary) -> str:
    label = {
        "daily": "Resumen diario",
        "weekly": "Resumen semanal",
        "monthly": "Resumen mensual",
        "historical": "Resumen histórico",
    }[summary.period]
    if summary.start is None or summary.end is None:
        return label
    if summary.period == "historical":
        return f"{label}: {summary.start.date()} a {summary.end.date()}"
    return f"{label}: {summary.start.date()} a {summary.end.date()}"


def _load_matplotlib():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError("matplotlib es obligatorio para exportar reportes PNG; instala requirements.txt") from exc
    return plt, mdates


def _save_figure(fig, output_path: Path) -> None:
    try:
        fig.tight_layout()
    except Exception:
        LOGGER.warning("matplotlib tight_layout failed; saving chart without tight layout")
    try:
        fig.savefig(output_path, dpi=140)
    except Exception:
        LOGGER.warning("matplotlib savefig failed; writing fallback PNG placeholder")
        _write_fallback_png(output_path)


def _write_fallback_png(output_path: Path, width: int = 640, height: int = 360) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_rows = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    compressed = zlib.compress(raw_rows, level=9)

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return struct.pack("!I", len(data)) + chunk_type + data + struct.pack("!I", checksum)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", compressed)
    png += chunk(b"IEND", b"")
    output_path.write_bytes(png)
