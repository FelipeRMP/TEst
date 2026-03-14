from __future__ import annotations

import csv
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
SIGNAL_LOG_PATH = DATA_DIR / "signal_log.csv"
PRICE_LOG_PATH = DATA_DIR / "price_history.csv"
SQLITE_PATH = DATA_DIR / "trading_data.db"
DEFAULT_SCAN_INTERVAL_SECONDS = 60


@dataclass(slots=True)
class ScanActivity:
    timestamp: datetime
    signal_count: int = 0
    price_snapshot_count: int = 0


def load_collection_stats() -> dict[str, object]:
    signal_rows = _read_csv_rows(SIGNAL_LOG_PATH)
    price_rows = _read_csv_rows(PRICE_LOG_PATH)
    signal_summary = _signal_summary(signal_rows)
    price_summary = _price_summary(price_rows)
    sqlite_summary = _sqlite_summary()

    total_signals_logged = sqlite_summary.get("total_signals_logged", signal_summary["count"])
    total_price_snapshots_logged = sqlite_summary.get("total_price_snapshots_logged", price_summary["count"])
    latest_signal_timestamp = sqlite_summary.get("latest_signal_timestamp", signal_summary["latest_timestamp"])
    latest_price_timestamp = sqlite_summary.get("latest_price_timestamp", price_summary["latest_timestamp"])
    average_expected_value = sqlite_summary.get("average_expected_value", signal_summary["average_expected_value"])
    recent_signal_count_24h = sqlite_summary.get("recent_signal_count_24h", signal_summary["count_24h"])
    recent_price_snapshot_count_24h = sqlite_summary.get(
        "recent_price_snapshot_count_24h",
        price_summary["count_24h"],
    )

    latest_candidates = [
        timestamp
        for timestamp in (latest_signal_timestamp, latest_price_timestamp)
        if timestamp is not None
    ]
    latest_scan_timestamp = max(latest_candidates) if latest_candidates else None
    expected_interval = _scan_interval_seconds()

    simulator_trade_count = sqlite_summary.get("simulator_trade_count", 0)
    simulator_total_pnl = sqlite_summary.get("simulator_total_pnl", 0.0)
    simulator_win_rate = sqlite_summary.get("simulator_win_rate")

    return {
        "total_signals_logged": total_signals_logged,
        "total_price_snapshots_logged": total_price_snapshots_logged,
        "latest_signal_timestamp": latest_signal_timestamp,
        "latest_price_timestamp": latest_price_timestamp,
        "latest_scan_timestamp": latest_scan_timestamp,
        "simulator_trade_count": simulator_trade_count,
        "simulator_total_pnl": simulator_total_pnl,
        "simulated_realized_pnl": simulator_total_pnl,
        "simulator_win_rate": simulator_win_rate,
        "win_rate": simulator_win_rate,
        "average_expected_value": average_expected_value,
        "average_ev": average_expected_value,
        "recent_signal_count_24h": recent_signal_count_24h,
        "recent_price_snapshot_count_24h": recent_price_snapshot_count_24h,
        "expected_scan_interval_seconds": expected_interval,
        "data_freshness_status": _freshness_status(latest_scan_timestamp, expected_interval),
        "recent_scan_activity": _build_recent_activity(signal_rows, price_rows),
    }


def _signal_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    values = [_to_float(row.get("expected_value")) for row in rows]
    return {
        "count": len(rows),
        "latest_timestamp": _latest_timestamp(rows),
        "average_expected_value": (sum(values) / len(values)) if values else 0.0,
        "count_24h": _count_since(rows, timedelta(hours=24)),
    }


def _price_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "count": len(rows),
        "latest_timestamp": _latest_timestamp(rows),
        "count_24h": _count_since(rows, timedelta(hours=24)),
    }


def _sqlite_summary() -> dict[str, Any]:
    if not SQLITE_PATH.exists():
        return {}

    try:
        with sqlite3.connect(SQLITE_PATH) as connection:
            signal_summary = _query_signal_table(connection)
            price_summary = _query_price_table(connection)
            simulator_summary = _query_simulated_trades(connection)
    except sqlite3.Error:
        return {}

    return {
        **signal_summary,
        **price_summary,
        **simulator_summary,
    }


def _query_signal_table(connection: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(connection, "signals"):
        return {}

    since = _iso_timestamp(datetime.now(timezone.utc) - timedelta(hours=24))
    row = connection.execute(
        """
        SELECT
            COUNT(*),
            MAX(timestamp),
            AVG(COALESCE(expected_value, 0)),
            SUM(CASE WHEN timestamp >= ? THEN 1 ELSE 0 END)
        FROM signals
        """
        ,
        (since,),
    ).fetchone()
    if row is None:
        return {}

    return {
        "total_signals_logged": int(row[0] or 0),
        "latest_signal_timestamp": _parse_timestamp(row[1]),
        "average_expected_value": float(row[2] or 0.0),
        "recent_signal_count_24h": int(row[3] or 0),
    }


def _query_price_table(connection: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(connection, "price_history"):
        return {}

    since = _iso_timestamp(datetime.now(timezone.utc) - timedelta(hours=24))
    row = connection.execute(
        """
        SELECT
            COUNT(*),
            MAX(timestamp),
            SUM(CASE WHEN timestamp >= ? THEN 1 ELSE 0 END)
        FROM price_history
        """
        ,
        (since,),
    ).fetchone()
    if row is None:
        return {}

    return {
        "total_price_snapshots_logged": int(row[0] or 0),
        "latest_price_timestamp": _parse_timestamp(row[1]),
        "recent_price_snapshot_count_24h": int(row[2] or 0),
    }


def _query_simulated_trades(connection: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(connection, "simulated_trades"):
        return {}

    row = connection.execute(
        """
        SELECT
            COUNT(*),
            SUM(COALESCE(pnl, 0)),
            AVG(CASE WHEN pnl > 0 THEN 1.0 ELSE 0.0 END)
        FROM simulated_trades
        """
    ).fetchone()
    if row is None:
        return {}

    trade_count = int(row[0] or 0)
    win_rate = float(row[2]) if row[2] is not None else None
    return {
        "simulator_trade_count": trade_count,
        "simulator_total_pnl": float(row[1] or 0.0),
        "simulator_win_rate": win_rate,
    }


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []


def _count_since(rows: list[dict[str, str]], window: timedelta) -> int:
    cutoff = datetime.now(timezone.utc) - window
    total = 0
    for row in rows:
        parsed = _parse_timestamp(row.get("timestamp"))
        if parsed is not None and parsed >= cutoff:
            total += 1
    return total


def _build_recent_activity(
    signal_rows: list[dict[str, str]],
    price_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    grouped: dict[str, ScanActivity] = {}

    for row in signal_rows:
        bucket = _minute_bucket(row.get("timestamp"))
        if bucket is None:
            continue
        activity = grouped.setdefault(bucket.isoformat(), ScanActivity(timestamp=bucket))
        activity.signal_count += 1

    for row in price_rows:
        bucket = _minute_bucket(row.get("timestamp"))
        if bucket is None:
            continue
        activity = grouped.setdefault(bucket.isoformat(), ScanActivity(timestamp=bucket))
        activity.price_snapshot_count += 1

    ordered = sorted(grouped.values(), key=lambda item: item.timestamp, reverse=True)
    return [
        {
            "timestamp": activity.timestamp,
            "signal_count": activity.signal_count,
            "price_snapshot_count": activity.price_snapshot_count,
        }
        for activity in ordered[:10]
    ]


def _scan_interval_seconds() -> int:
    try:
        return max(1, int(os.getenv("SCAN_INTERVAL_SECONDS", DEFAULT_SCAN_INTERVAL_SECONDS)))
    except (TypeError, ValueError):
        return DEFAULT_SCAN_INTERVAL_SECONDS


def _freshness_status(latest_timestamp: datetime | None, interval_seconds: int) -> str:
    if latest_timestamp is None:
        return "stale"

    age_seconds = max(0.0, (datetime.now(timezone.utc) - latest_timestamp).total_seconds())
    if age_seconds <= (interval_seconds * 2):
        return "healthy"
    if age_seconds <= 600:
        return "delayed"
    return "stale"


def _minute_bucket(value: str | None) -> datetime | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    return parsed.replace(second=0, microsecond=0)


def _latest_timestamp(rows: list[dict[str, str]]) -> datetime | None:
    parsed = [_parse_timestamp(row.get("timestamp")) for row in rows]
    valid = [item for item in parsed if item is not None]
    return max(valid) if valid else None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _iso_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_float(value: str | float | int | None) -> float:
    try:
        if value in {None, ""}:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
