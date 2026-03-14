from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
SIGNAL_LOG_PATH = DATA_DIR / "signal_log.csv"
PRICE_LOG_PATH = DATA_DIR / "price_history.csv"
SQLITE_PATH = DATA_DIR / "trading_data.db"


@dataclass(slots=True)
class ScanActivity:
    timestamp: datetime
    signal_count: int = 0
    price_snapshot_count: int = 0


def load_collection_stats() -> dict[str, object]:
    signal_rows = _read_csv_rows(SIGNAL_LOG_PATH)
    price_rows = _read_csv_rows(PRICE_LOG_PATH)
    activities = _build_recent_activity(signal_rows, price_rows)
    simulator_summary = _load_simulator_summary()

    latest_timestamps = [
        parsed
        for parsed in (
            _latest_timestamp(signal_rows),
            _latest_timestamp(price_rows),
        )
        if parsed is not None
    ]

    average_ev = 0.0
    if signal_rows:
        ev_values = [_to_float(row.get("expected_value")) for row in signal_rows]
        average_ev = sum(ev_values) / len(ev_values)

    return {
        "total_signals_logged": len(signal_rows),
        "total_price_snapshots_logged": len(price_rows),
        "latest_scan_timestamp": max(latest_timestamps) if latest_timestamps else None,
        "simulator_trade_count": simulator_summary["trade_count"],
        "simulated_realized_pnl": simulator_summary["realized_pnl"],
        "average_ev": average_ev,
        "win_rate": simulator_summary["win_rate"],
        "recent_scan_activity": activities,
    }


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []


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


def _minute_bucket(value: str | None) -> datetime | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    return parsed.replace(second=0, microsecond=0)


def _latest_timestamp(rows: list[dict[str, str]]) -> datetime | None:
    parsed = [_parse_timestamp(row.get("timestamp")) for row in rows]
    valid = [item for item in parsed if item is not None]
    return max(valid) if valid else None


def _load_simulator_summary() -> dict[str, float]:
    if not SQLITE_PATH.exists():
        return {"trade_count": 0.0, "realized_pnl": 0.0, "win_rate": None}

    try:
        with sqlite3.connect(SQLITE_PATH) as connection:
            rows = connection.execute(
                """
                SELECT pnl
                FROM simulated_trades
                """
            ).fetchall()
    except sqlite3.Error:
        return {"trade_count": 0.0, "realized_pnl": 0.0, "win_rate": None}

    if not rows:
        return {"trade_count": 0.0, "realized_pnl": 0.0, "win_rate": None}

    pnls = [float(row[0]) for row in rows]
    wins = sum(1 for pnl in pnls if pnl > 0)
    return {
        "trade_count": float(len(pnls)),
        "realized_pnl": sum(pnls),
        "win_rate": wins / len(pnls),
    }


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _to_float(value: str | float | int | None) -> float:
    try:
        if value in {None, ""}:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
