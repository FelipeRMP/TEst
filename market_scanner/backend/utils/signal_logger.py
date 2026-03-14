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
SIGNAL_LOG_PATH = DATA_DIR / "signal_log.csv"
SQLITE_PATH = DATA_DIR / "trading_data.db"

SIGNAL_HEADERS = [
    "timestamp",
    "event_id",
    "event_title",
    "platform",
    "market_id",
    "side",
    "market_price",
    "consensus_probability",
    "expected_value",
    "signal_strength",
    "liquidity",
    "suggested_bankroll_percent",
    "suggested_amount",
    "best_bid",
    "best_ask",
    "bid_size",
    "ask_size",
    "spread",
    "spread_percent",
]

SQLITE_SIGNAL_COLUMNS = [
    ("timestamp", "TEXT NOT NULL"),
    ("event_id", "TEXT"),
    ("event_title", "TEXT"),
    ("platform", "TEXT"),
    ("market_id", "TEXT"),
    ("side", "TEXT"),
    ("market_price", "REAL"),
    ("consensus_probability", "REAL"),
    ("expected_value", "REAL"),
    ("signal_strength", "REAL"),
    ("liquidity", "REAL"),
    ("suggested_bankroll_percent", "REAL"),
    ("suggested_amount", "REAL"),
    ("best_bid", "REAL"),
    ("best_ask", "REAL"),
    ("bid_size", "REAL"),
    ("ask_size", "REAL"),
    ("spread", "REAL"),
    ("spread_percent", "REAL"),
]

_write_lock = Lock()


async def log_signal(opportunity: Any) -> None:
    try:
        row = _build_signal_row(opportunity)
        await asyncio.to_thread(_write_signal_row, row)
    except Exception as exc:
        # Logging must never interrupt scanning.
        print(f"[signal_logger] failed to log signal: {exc}")
        return


def _build_signal_row(opportunity: Any) -> dict[str, Any]:
    legs = getattr(opportunity, "legs", None) or []
    primary_leg = legs[0] if legs else None
    platform = getattr(opportunity, "platform", None) or getattr(primary_leg, "platform", "") or ""
    raw_market_id = getattr(primary_leg, "market_id", "") if primary_leg is not None else ""
    side = getattr(primary_leg, "outcome", "") if primary_leg is not None else ""
    price = _to_float(getattr(primary_leg, "price", None)) if primary_leg is not None else 0.0
    consensus_probability = _to_float(getattr(opportunity, "consensus_probability", None))
    if consensus_probability == 0.0 and primary_leg is not None:
        consensus_probability = _to_float(getattr(primary_leg, "consensus_probability", None))

    market_identifier = normalize_market_id(platform, raw_market_id, side) if raw_market_id else normalize_market_id(
        platform,
        str(getattr(opportunity, "market", "") or ""),
        side,
    )

    return {
        "timestamp": _utc_timestamp(),
        "event_id": str(getattr(opportunity, "event_id", "") or ""),
        "event_title": str(getattr(opportunity, "event", None) or getattr(opportunity, "event_title", "") or ""),
        "platform": str(platform),
        "market_id": market_identifier,
        "side": str(side),
        "market_price": round(price, 6),
        "consensus_probability": round(consensus_probability, 6),
        "expected_value": round(_to_float(getattr(opportunity, "expected_value", None)), 6),
        "signal_strength": round(_to_float(getattr(opportunity, "confidence", None)), 6),
        "liquidity": round(_to_float(getattr(opportunity, "liquidity", None)), 6),
        "suggested_bankroll_percent": round(
            _to_float(getattr(opportunity, "recommended_bankroll_fraction", None)),
            6,
        ),
        "suggested_amount": round(_to_float(getattr(opportunity, "recommended_position_size", None)), 6),
        "best_bid": _rounded_optional(getattr(primary_leg, "best_bid", None)),
        "best_ask": _rounded_optional(getattr(primary_leg, "best_ask", None)),
        "bid_size": _rounded_optional(getattr(primary_leg, "bid_size", None)),
        "ask_size": _rounded_optional(getattr(primary_leg, "ask_size", None)),
        "spread": _rounded_optional(getattr(primary_leg, "spread", None)),
        "spread_percent": _rounded_optional(getattr(primary_leg, "spread_percent", None)),
    }


def _write_signal_row(row: dict[str, Any]) -> None:
    with _write_lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            _ensure_signal_headers()
            with SIGNAL_LOG_PATH.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=SIGNAL_HEADERS)
                if SIGNAL_LOG_PATH.stat().st_size == 0:
                    writer.writeheader()
                writer.writerow(row)
        except Exception as exc:
            print(f"[signal_logger] csv write failed: {exc}")
        try:
            _write_sqlite(row)
        except Exception as exc:
            print(f"[signal_logger] sqlite write failed: {exc}")


def _ensure_signal_headers() -> None:
    if not SIGNAL_LOG_PATH.exists() or SIGNAL_LOG_PATH.stat().st_size == 0:
        return

    with SIGNAL_LOG_PATH.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        existing_headers = reader.fieldnames or []
        existing_rows = list(reader)

    rewritten_rows = []
    needs_rewrite = existing_headers != SIGNAL_HEADERS
    for row in existing_rows:
        rewritten = {header: row.get(header, "") for header in SIGNAL_HEADERS}
        normalized_market_id = normalize_market_id(
            row.get("platform", "") or "",
            row.get("market_id", "") or "",
            row.get("side", "") or "",
        )
        if rewritten.get("market_id", "") != normalized_market_id:
            needs_rewrite = True
        rewritten["market_id"] = normalized_market_id
        rewritten_rows.append(rewritten)

    if not needs_rewrite:
        return

    with SIGNAL_LOG_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SIGNAL_HEADERS)
        writer.writeheader()
        writer.writerows(rewritten_rows)


def _write_sqlite(row: dict[str, Any]) -> None:
    with sqlite3.connect(SQLITE_PATH) as connection:
        column_definitions = ",\n                ".join(f"{name} {definition}" for name, definition in SQLITE_SIGNAL_COLUMNS)
        connection.execute(f"CREATE TABLE IF NOT EXISTS signals({column_definitions})")
        _ensure_sqlite_columns(connection)
        connection.execute(
            f"""
            INSERT INTO signals({", ".join(SIGNAL_HEADERS)})
            VALUES ({", ".join("?" for _ in SIGNAL_HEADERS)})
            """,
            [row[header] for header in SIGNAL_HEADERS],
        )
        connection.commit()


def _ensure_sqlite_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(signals)").fetchall()
    }
    for name, definition in SQLITE_SIGNAL_COLUMNS:
        if name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE signals ADD COLUMN {name} {definition}")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _rounded_optional(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None
