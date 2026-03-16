from __future__ import annotations

import asyncio
import csv
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from .market_ids import normalize_market_id

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
SIGNAL_LOG_PATH = DATA_DIR / "signal_log.csv"
SQLITE_PATH = DATA_DIR / "trading_data.db"
REEMIT_WINDOW = timedelta(hours=6)
MATERIAL_CHANGE_THRESHOLDS = {
    "market_price": 0.01,
    "consensus_probability": 0.01,
    "expected_value": 0.02,
    "signal_strength": 0.05,
}

SIGNAL_HEADERS = [
    "signal_id",
    "scan_id",
    "scan_timestamp",
    "timestamp",
    "signal_family",
    "opportunity_type",
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
    ("signal_id", "TEXT"),
    ("scan_id", "TEXT"),
    ("scan_timestamp", "TEXT"),
    ("timestamp", "TEXT NOT NULL"),
    ("signal_family", "TEXT"),
    ("opportunity_type", "TEXT"),
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


async def log_signal(
    opportunity: Any,
    *,
    scan_id: str = "",
    scan_timestamp: datetime | None = None,
) -> bool:
    try:
        row = _build_signal_row(opportunity, scan_id=scan_id, scan_timestamp=scan_timestamp)
        return await asyncio.to_thread(_write_signal_row, row)
    except Exception as exc:
        print(f"[signal_logger] failed to log signal: {exc}")
        return False


def _build_signal_row(
    opportunity: Any,
    *,
    scan_id: str = "",
    scan_timestamp: datetime | None = None,
) -> dict[str, Any]:
    legs = getattr(opportunity, "legs", None) or []
    primary_leg = legs[0] if legs else None
    platform = getattr(opportunity, "platform", None) or getattr(primary_leg, "platform", "") or ""
    raw_market_id = getattr(primary_leg, "market_id", "") if primary_leg is not None else ""
    side = getattr(primary_leg, "outcome", "") if primary_leg is not None else ""
    price = _to_optional_float(getattr(primary_leg, "price", None)) if primary_leg is not None else None
    consensus_probability = _to_optional_float(getattr(opportunity, "consensus_probability", None))
    if consensus_probability is None and primary_leg is not None:
        consensus_probability = _to_optional_float(getattr(primary_leg, "consensus_probability", None))

    market_identifier = normalize_market_id(
        platform,
        raw_market_id or str(getattr(opportunity, "market", "") or ""),
        side,
    )
    emitted_at = scan_timestamp or datetime.now(timezone.utc)
    opportunity_type = str(getattr(opportunity, "opportunity_type", "") or "")
    event_id = str(getattr(opportunity, "event_id", "") or "")
    signal_family = f"{event_id}|{market_identifier}|{opportunity_type or 'signal'}"

    return {
        "signal_id": f"sig-{uuid4().hex}",
        "scan_id": str(scan_id or ""),
        "scan_timestamp": _iso_timestamp(emitted_at),
        "timestamp": _utc_timestamp(),
        "signal_family": signal_family,
        "opportunity_type": opportunity_type,
        "event_id": event_id,
        "event_title": str(getattr(opportunity, "event", None) or getattr(opportunity, "event_title", "") or ""),
        "platform": str(platform),
        "market_id": market_identifier,
        "side": str(side),
        "market_price": _rounded_optional(price),
        "consensus_probability": _rounded_optional(consensus_probability),
        "expected_value": _rounded_optional(getattr(opportunity, "expected_value", None)),
        "signal_strength": _rounded_optional(getattr(opportunity, "confidence", None)),
        "liquidity": _rounded_optional(getattr(opportunity, "liquidity", None)),
        "suggested_bankroll_percent": _rounded_optional(getattr(opportunity, "recommended_bankroll_fraction", None)),
        "suggested_amount": _rounded_optional(getattr(opportunity, "recommended_position_size", None)),
        "best_bid": _rounded_optional(getattr(primary_leg, "best_bid", None)),
        "best_ask": _rounded_optional(getattr(primary_leg, "best_ask", None)),
        "bid_size": _rounded_optional(getattr(primary_leg, "bid_size", None)),
        "ask_size": _rounded_optional(getattr(primary_leg, "ask_size", None)),
        "spread": _rounded_optional(getattr(primary_leg, "spread", None)),
        "spread_percent": _rounded_optional(getattr(primary_leg, "spread_percent", None)),
    }


def _write_signal_row(row: dict[str, Any]) -> bool:
    with _write_lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        should_write = True
        try:
            with sqlite3.connect(SQLITE_PATH) as connection:
                _ensure_sqlite_schema(connection)
                should_write = _should_emit_signal(connection, row)
                if should_write:
                    _write_sqlite(connection, row)
        except Exception as exc:
            print(f"[signal_logger] sqlite write failed: {exc}")
        if not should_write:
            return False
        try:
            _ensure_signal_headers()
            with SIGNAL_LOG_PATH.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=SIGNAL_HEADERS)
                if SIGNAL_LOG_PATH.stat().st_size == 0:
                    writer.writeheader()
                writer.writerow(row)
        except Exception as exc:
            print(f"[signal_logger] csv write failed: {exc}")
        return True


def _should_emit_signal(connection: sqlite3.Connection, row: dict[str, Any]) -> bool:
    existing = connection.execute(
        """
        SELECT
            COALESCE(scan_timestamp, timestamp),
            COALESCE(market_price, 0),
            COALESCE(consensus_probability, 0),
            COALESCE(expected_value, 0),
            COALESCE(signal_strength, 0)
        FROM signals
        WHERE signal_family = ?
        ORDER BY COALESCE(scan_timestamp, timestamp) DESC
        LIMIT 1
        """,
        (row["signal_family"],),
    ).fetchone()
    if existing is None:
        return True

    previous_timestamp = _parse_timestamp(existing[0])
    if previous_timestamp is None:
        return True

    current_scan_time = _parse_timestamp(str(row["scan_timestamp"]))
    if current_scan_time is None:
        current_scan_time = datetime.now(timezone.utc)
    if current_scan_time - previous_timestamp >= REEMIT_WINDOW:
        return True

    previous_values = {
        "market_price": float(existing[1] or 0.0),
        "consensus_probability": float(existing[2] or 0.0),
        "expected_value": float(existing[3] or 0.0),
        "signal_strength": float(existing[4] or 0.0),
    }
    current_values = {
        "market_price": _to_float(row.get("market_price")),
        "consensus_probability": _to_float(row.get("consensus_probability")),
        "expected_value": _to_float(row.get("expected_value")),
        "signal_strength": _to_float(row.get("signal_strength")),
    }
    return any(
        abs(current_values[key] - previous_values[key]) >= threshold
        for key, threshold in MATERIAL_CHANGE_THRESHOLDS.items()
    )


def _ensure_signal_headers() -> None:
    if not SIGNAL_LOG_PATH.exists() or SIGNAL_LOG_PATH.stat().st_size == 0:
        return

    with SIGNAL_LOG_PATH.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        existing_headers = reader.fieldnames or []
        existing_rows = list(reader)

    needs_rewrite = existing_headers != SIGNAL_HEADERS
    rewritten_rows = []
    for row in existing_rows:
        normalized_market_id = normalize_market_id(
            row.get("platform", "") or "",
            row.get("market_id", "") or "",
            row.get("side", "") or "",
        )
        rewritten = {header: row.get(header, "") for header in SIGNAL_HEADERS}
        rewritten["market_id"] = normalized_market_id
        rewritten["signal_family"] = (
            row.get("signal_family")
            or f"{row.get('event_id', '')}|{normalized_market_id}|{row.get('opportunity_type', '') or 'signal'}"
        )
        rewritten["signal_id"] = row.get("signal_id") or f"legacy-{uuid4().hex}"
        rewritten["scan_id"] = row.get("scan_id", "")
        rewritten["scan_timestamp"] = row.get("scan_timestamp") or row.get("timestamp", "")
        if rewritten["market_id"] != row.get("market_id", ""):
            needs_rewrite = True
        rewritten_rows.append(rewritten)

    if not needs_rewrite:
        return

    with SIGNAL_LOG_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SIGNAL_HEADERS)
        writer.writeheader()
        writer.writerows(rewritten_rows)


def _ensure_sqlite_schema(connection: sqlite3.Connection) -> None:
    column_definitions = ",\n                ".join(f"{name} {definition}" for name, definition in SQLITE_SIGNAL_COLUMNS)
    connection.execute(f"CREATE TABLE IF NOT EXISTS signals({column_definitions})")
    existing_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(signals)").fetchall()
    }
    for name, definition in SQLITE_SIGNAL_COLUMNS:
        if name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE signals ADD COLUMN {name} {definition}")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_signals_signal_family_timestamp
        ON signals(signal_family, timestamp DESC)
        """
    )
    connection.execute(
        """
        UPDATE signals
        SET market_id = REPLACE(REPLACE(market_id, ':YES:YES', ':YES'), ':NO:NO', ':NO')
        WHERE market_id LIKE '%:YES:YES' OR market_id LIKE '%:NO:NO'
        """
    )
    connection.commit()


def _write_sqlite(connection: sqlite3.Connection, row: dict[str, Any]) -> None:
    connection.execute(
        f"""
        INSERT INTO signals({", ".join(SIGNAL_HEADERS)})
        VALUES ({", ".join("?" for _ in SIGNAL_HEADERS)})
        """,
        [row.get(header) for header in SIGNAL_HEADERS],
    )
    connection.commit()


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _rounded_optional(value: Any) -> float | None:
    optional = _to_optional_float(value)
    if optional is None:
        return None
    return round(optional, 6)
