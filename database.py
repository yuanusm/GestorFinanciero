"""SQLite persistence layer for financial transactions.

All SQL in this module is fixed and parameterized. The Telegram layer never receives
or executes arbitrary SQL text.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    amount_clp INTEGER NOT NULL CHECK (amount_clp >= 0),
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('expense', 'income')),
    category TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(transaction_type);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
"""


@dataclass(frozen=True)
class Transaction:
    """A normalized transaction ready for storage or reporting."""

    raw_text: str
    amount_clp: int
    transaction_type: str
    category: str
    description: str
    timestamp: datetime | None = None


@dataclass(frozen=True)
class StoredTransaction(Transaction):
    """A transaction read back from SQLite."""

    id: int = 0


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database(database_path: Path) -> None:
    """Create the SQLite database and transaction table if needed."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(database_path) as connection:
        connection.executescript(SCHEMA_SQL)


def insert_transaction(database_path: Path, transaction: Transaction) -> int:
    """Persist a transaction and return its SQLite row id."""
    _validate_transaction(transaction)
    timestamp = transaction.timestamp or datetime.now(timezone.utc)
    with _connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO transactions (
                timestamp, raw_text, amount_clp, transaction_type, category, description
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp.isoformat(),
                transaction.raw_text,
                transaction.amount_clp,
                transaction.transaction_type,
                transaction.category,
                transaction.description,
            ),
        )
        return int(cursor.lastrowid)


def fetch_transactions_between(
    database_path: Path,
    start: datetime,
    end: datetime,
) -> list[StoredTransaction]:
    """Fetch transactions whose timestamps are within [start, end)."""
    with _connect(database_path) as connection:
        rows: Iterable[sqlite3.Row] = connection.execute(
            """
            SELECT id, timestamp, raw_text, amount_clp, transaction_type, category, description
            FROM transactions
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    return [_row_to_transaction(row) for row in rows]


def fetch_all_transactions(database_path: Path) -> list[StoredTransaction]:
    """Fetch all transactions for full historical reporting."""
    with _connect(database_path) as connection:
        rows: Iterable[sqlite3.Row] = connection.execute(
            """
            SELECT id, timestamp, raw_text, amount_clp, transaction_type, category, description
            FROM transactions
            ORDER BY timestamp ASC
            """
        ).fetchall()
    return [_row_to_transaction(row) for row in rows]


def _row_to_transaction(row: sqlite3.Row) -> StoredTransaction:
    return StoredTransaction(
        id=int(row["id"]),
        timestamp=datetime.fromisoformat(row["timestamp"]),
        raw_text=str(row["raw_text"]),
        amount_clp=int(row["amount_clp"]),
        transaction_type=str(row["transaction_type"]),
        category=str(row["category"]),
        description=str(row["description"]),
    )


def _validate_transaction(transaction: Transaction) -> None:
    if transaction.amount_clp < 0:
        raise ValueError("amount_clp must be non-negative")
    if transaction.transaction_type not in {"expense", "income"}:
        raise ValueError("transaction_type must be 'expense' or 'income'")
    if not transaction.category.strip():
        raise ValueError("category must not be empty")
    if not transaction.description.strip():
        raise ValueError("description must not be empty")
