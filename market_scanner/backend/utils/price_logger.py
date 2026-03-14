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
    "timestamp",
    "platform",
    "market_id",
    "event_id",
    "price",
    "liquidity",
]

_write_lock = Lock()


async def log_market_price(market: Any) -> None:
    try:
        rows = _build_price_rows(market)
        if not rows:
            return
        await asyncio.to_thread(_write_price_rows, rows)
    except Exception as exc:
        print(f"[price_logger] failed to log price history: {exc}")
        return


def _build_price_rows(market: Any) -> list[dict[str, Any]]:
    timestamp = _utc_timestamp()
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
            _write_sqlite(rows)
        except Exception as exc:
            print(f"[price_logger] sqlite write failed: {exc}")


def _write_sqlite(rows: list[dict[str, Any]]) -> None:
    with sqlite3.connect(SQLITE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS price_history(
                timestamp TEXT NOT NULL,
                platform TEXT,
                market_id TEXT,
                event_id TEXT,
                price REAL,
                liquidity REAL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO price_history(timestamp, platform, market_id, event_id, price, liquidity)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [[row[header] for header in PRICE_HEADERS] for row in rows],
        )
        connection.commit()


def _ensure_price_headers() -> None:
    if not PRICE_LOG_PATH.exists() or PRICE_LOG_PATH.stat().st_size == 0:
        return

    with PRICE_LOG_PATH.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        existing_headers = reader.fieldnames or []
        existing_rows = list(reader)

    if existing_headers != PRICE_HEADERS:
        rewritten_rows = [{header: row.get(header, "") for header in PRICE_HEADERS} for row in existing_rows]
    else:
        rewritten_rows = existing_rows

    normalized_rows = []
    for row in rewritten_rows:
        normalized_rows.append(
            {
                **row,
                "market_id": normalize_market_id(
                    row.get("platform", "") or "",
                    row.get("market_id", "") or "",
                ),
            }
        )

    with PRICE_LOG_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRICE_HEADERS)
        writer.writeheader()
        writer.writerows(normalized_rows)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
