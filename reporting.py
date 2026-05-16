"""Daily and weekly reporting utilities with PNG chart export."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from database import StoredTransaction, fetch_transactions_between


@dataclass(frozen=True)
class Summary:
    """A summarized view of transactions in a period."""

    start: datetime
    end: datetime
    income_clp: int
    expense_clp: int
    net_clp: int
    by_category: dict[str, int]
    transaction_count: int


def generate_daily_summary(database_path: Path, day: date | None = None) -> Summary:
    """Generate a transaction summary for one UTC day."""
    selected_day = day or datetime.now(timezone.utc).date()
    start = datetime.combine(selected_day, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return _summarize(fetch_transactions_between(database_path, start, end), start, end)


def generate_weekly_summary(database_path: Path, week_start: date | None = None) -> Summary:
    """Generate a transaction summary for a Monday-starting UTC week."""
    today = datetime.now(timezone.utc).date()
    selected_start = week_start or (today - timedelta(days=today.weekday()))
    start = datetime.combine(selected_start, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    return _summarize(fetch_transactions_between(database_path, start, end), start, end)


def export_summary_chart(summary: Summary, output_path: Path) -> Path:
    """Export a category expense chart and income/expense totals to PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    categories = list(summary.by_category.keys()) or ["no data"]
    values = list(summary.by_category.values()) or [0]

    fig, (ax_categories, ax_totals) = plt.subplots(1, 2, figsize=(10, 4))
    ax_categories.bar(categories, values, color="#e76f51")
    ax_categories.set_title("Expenses by category")
    ax_categories.set_ylabel("CLP")
    ax_categories.tick_params(axis="x", rotation=35)

    ax_totals.bar(["income", "expense", "net"], [summary.income_clp, summary.expense_clp, summary.net_clp], color=["#2a9d8f", "#e76f51", "#264653"])
    ax_totals.set_title("Period totals")
    ax_totals.set_ylabel("CLP")

    fig.suptitle(f"Financial summary: {summary.start.date()} to {summary.end.date()}")
    fig.tight_layout()
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path


def format_summary(summary: Summary) -> str:
    """Create a compact human-readable summary for Telegram messages."""
    categories = "\n".join(f"- {category}: ${amount:,} CLP" for category, amount in summary.by_category.items())
    if not categories:
        categories = "- No expenses recorded"
    return (
        f"Summary {summary.start.date()} to {summary.end.date()}\n"
        f"Income: ${summary.income_clp:,} CLP\n"
        f"Expenses: ${summary.expense_clp:,} CLP\n"
        f"Net: ${summary.net_clp:,} CLP\n"
        f"Transactions: {summary.transaction_count}\n"
        f"By category:\n{categories}"
    )


def _summarize(transactions: list[StoredTransaction], start: datetime, end: datetime) -> Summary:
    income = sum(tx.amount_clp for tx in transactions if tx.transaction_type == "income")
    expense = sum(tx.amount_clp for tx in transactions if tx.transaction_type == "expense")
    by_category: dict[str, int] = defaultdict(int)
    for transaction in transactions:
        if transaction.transaction_type == "expense":
            by_category[transaction.category] += transaction.amount_clp
    return Summary(
        start=start,
        end=end,
        income_clp=income,
        expense_clp=expense,
        net_clp=income - expense,
        by_category=dict(sorted(by_category.items())),
        transaction_count=len(transactions),
    )
