from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
SQLITE_PATH = DATA_DIR / "trading_data.db"


def generate_labels() -> int:
    if not SQLITE_PATH.exists():
        return 0

    with sqlite3.connect(SQLITE_PATH) as connection:
        if not _table_exists(connection, "signals") or not _table_exists(connection, "price_history"):
            return 0
        _ensure_label_table(connection)
        signals = connection.execute(
            """
            SELECT
                COALESCE(signal_id, ''),
                COALESCE(scan_timestamp, timestamp),
                COALESCE(market_id, ''),
                COALESCE(market_price, 0),
                COALESCE(consensus_probability, 0)
            FROM signals
            WHERE COALESCE(signal_id, '') <> ''
            """
        ).fetchall()
        upserts = []
        for signal_id, timestamp, market_id, market_price, consensus_probability in signals:
            signal_time = _parse_timestamp(timestamp)
            labels = _compute_labels(
                connection,
                market_id=str(market_id),
                signal_time=signal_time,
                entry_price=float(market_price or 0.0),
                consensus_probability=float(consensus_probability or 0.0),
            )
            upserts.append((signal_id, datetime.now(timezone.utc).isoformat(), *labels))

        connection.executemany(
            """
            INSERT OR REPLACE INTO signal_labels(
                signal_id,
                generated_at,
                future_return_5m,
                future_return_1h,
                future_return_24h,
                hit_consensus_within_24h
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            upserts,
        )
        connection.commit()
        return len(upserts)


def _compute_labels(
    connection: sqlite3.Connection,
    *,
    market_id: str,
    signal_time: datetime,
    entry_price: float,
    consensus_probability: float,
) -> tuple[float | None, float | None, float | None, int]:
    future_prices = connection.execute(
        """
        SELECT COALESCE(scan_timestamp, timestamp), price
        FROM price_history
        WHERE market_id = ?
          AND COALESCE(scan_timestamp, timestamp) >= ?
          AND COALESCE(scan_timestamp, timestamp) <= ?
        ORDER BY COALESCE(scan_timestamp, timestamp) ASC
        """,
        (
            market_id,
            signal_time.isoformat(),
            (signal_time + timedelta(hours=24)).isoformat(),
        ),
    ).fetchall()
    if entry_price <= 0:
        return None, None, None, 0

    points = [(_parse_timestamp(timestamp), float(price or 0.0)) for timestamp, price in future_prices]
    return (
        _future_return(points, signal_time + timedelta(minutes=5), entry_price),
        _future_return(points, signal_time + timedelta(hours=1), entry_price),
        _future_return(points, signal_time + timedelta(hours=24), entry_price),
        1 if any(price >= consensus_probability > 0 for _, price in points) else 0,
    )


def _future_return(
    points: list[tuple[datetime, float]],
    horizon: datetime,
    entry_price: float,
) -> float | None:
    for timestamp, price in points:
        if timestamp >= horizon:
            return round(price - entry_price, 6)
    return None


def _ensure_label_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS signal_labels(
            signal_id TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            future_return_5m REAL,
            future_return_1h REAL,
            future_return_24h REAL,
            hit_consensus_within_24h INTEGER
        )
        """
    )


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


if __name__ == "__main__":
    count = generate_labels()
    print(f"Generated labels for {count} signals.")
