from __future__ import annotations

import asyncio
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from .market_ids import normalize_market_id

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
PRICE_LOG_PATH = DATA_DIR / "price_history.csv"
SQLITE_PATH = DATA_DIR / "trading_data.db"

PRICE_HEADERS = [
    "scan_id",
    "scan_timestamp",
    "timestamp",
    "platform",
    "market_id",
    "event_id",
    "price",
    "liquidity",
]

_write_lock = Lock()


async def log_market_price(
    market: Any,
    *,
    scan_id: str = "",
    scan_timestamp: datetime | None = None,
) -> None:
    try:
        rows = _build_price_rows(market, scan_id=scan_id, scan_timestamp=scan_timestamp)
        if not rows:
            return
        await asyncio.to_thread(_write_price_rows, rows)
    except Exception as exc:
        print(f"[price_logger] failed to log price history: {exc}")


def _build_price_rows(
    market: Any,
    *,
    scan_id: str = "",
    scan_timestamp: datetime | None = None,
) -> list[dict[str, Any]]:
    timestamp = _utc_timestamp()
    scan_time = scan_timestamp or datetime.now(timezone.utc)
    platform = str(getattr(market, "platform", "") or "")
    market_id = str(getattr(market, "market_id", "") or "")
    event_id = str(getattr(market, "event_key", None) or getattr(market, "market_id", "") or "")
    liquidity = round(_to_float(getattr(market, "liquidity", None)), 6)
    rows: list[dict[str, Any]] = []

    for outcome in getattr(market, "outcomes", []) or []:
        price = getattr(outcome, "implied_probability", None)
        if price is None:
            price = getattr(outcome, "price", None)
        price_value = _to_float(price)
        if not 0.0 <= price_value <= 1.0:
            continue
        rows.append(
            {
                "scan_id": str(scan_id or ""),
                "scan_timestamp": _iso_timestamp(scan_time),
                "timestamp": timestamp,
                "platform": platform,
                "market_id": normalize_market_id(
                    platform,
                    market_id,
                    str(getattr(outcome, "label", "") or "").strip().upper(),
                ),
                "event_id": event_id,
                "price": round(price_value, 6),
                "liquidity": liquidity,
            }
        )

    return rows


def _write_price_rows(rows: list[dict[str, Any]]) -> None:
    with _write_lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            _ensure_price_headers()
            with PRICE_LOG_PATH.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=PRICE_HEADERS)
                if PRICE_LOG_PATH.stat().st_size == 0:
                    writer.writeheader()
                writer.writerows(rows)
        except Exception as exc:
            print(f"[price_logger] csv write failed: {exc}")
        try:
            with sqlite3.connect(SQLITE_PATH) as connection:
                _ensure_sqlite_schema(connection)
                connection.executemany(
                    """
                    INSERT INTO price_history(scan_id, scan_timestamp, timestamp, platform, market_id, event_id, price, liquidity)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [[row[header] for header in PRICE_HEADERS] for row in rows],
                )
                connection.commit()
        except Exception as exc:
            print(f"[price_logger] sqlite write failed: {exc}")


def _ensure_sqlite_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history(
            scan_id TEXT,
            scan_timestamp TEXT,
            timestamp TEXT NOT NULL,
            platform TEXT,
            market_id TEXT,
            event_id TEXT,
            price REAL,
            liquidity REAL
        )
        """
    )
    existing_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(price_history)").fetchall()
    }
    for column, definition in [
        ("scan_id", "TEXT"),
        ("scan_timestamp", "TEXT"),
        ("timestamp", "TEXT NOT NULL"),
        ("platform", "TEXT"),
        ("market_id", "TEXT"),
        ("event_id", "TEXT"),
        ("price", "REAL"),
        ("liquidity", "REAL"),
    ]:
        if column in existing_columns:
            continue
        connection.execute(f"ALTER TABLE price_history ADD COLUMN {column} {definition}")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_price_history_scan_id
        ON price_history(scan_id, timestamp DESC)
        """
    )
    connection.execute(
        """
        UPDATE price_history
        SET market_id = REPLACE(REPLACE(market_id, ':YES:YES', ':YES'), ':NO:NO', ':NO')
        WHERE market_id LIKE '%:YES:YES' OR market_id LIKE '%:NO:NO'
        """
    )
    connection.commit()


def _ensure_price_headers() -> None:
    if not PRICE_LOG_PATH.exists() or PRICE_LOG_PATH.stat().st_size == 0:
        return

    with PRICE_LOG_PATH.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        existing_headers = reader.fieldnames or []
        existing_rows = list(reader)

    needs_rewrite = existing_headers != PRICE_HEADERS
    normalized_rows = []
    for row in existing_rows:
        rewritten = {header: row.get(header, "") for header in PRICE_HEADERS}
        rewritten["market_id"] = normalize_market_id(
            row.get("platform", "") or "",
            row.get("market_id", "") or "",
        )
        rewritten["scan_timestamp"] = row.get("scan_timestamp") or row.get("timestamp", "")
        if rewritten["market_id"] != row.get("market_id", ""):
            needs_rewrite = True
        normalized_rows.append(rewritten)

    if not needs_rewrite:
        return

    with PRICE_LOG_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRICE_HEADERS)
        writer.writeheader()
        writer.writerows(normalized_rows)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
