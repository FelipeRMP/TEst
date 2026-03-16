from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
SQLITE_PATH = DATA_DIR / "trading_data.db"


async def record_scan_batch_started(
    *,
    scan_id: str,
    started_at: datetime,
    limit: int,
    min_liquidity: float,
    min_ev: float,
    bankroll_amount: float,
) -> None:
    await asyncio.to_thread(
        _upsert_scan_batch,
        {
            "scan_id": scan_id,
            "started_at": _iso_timestamp(started_at),
            "scan_timestamp": _iso_timestamp(started_at),
            "status": "running",
            "limit_value": int(limit),
            "min_liquidity": float(min_liquidity),
            "min_ev": float(min_ev),
            "bankroll_amount": float(bankroll_amount),
        },
    )


async def record_scan_batch_finished(
    *,
    scan_id: str,
    finished_at: datetime,
    status: str,
    market_count: int = 0,
    price_snapshot_count: int = 0,
    detected_opportunity_count: int = 0,
    emitted_signal_count: int = 0,
    error_message: str | None = None,
) -> None:
    await asyncio.to_thread(
        _upsert_scan_batch,
        {
            "scan_id": scan_id,
            "finished_at": _iso_timestamp(finished_at),
            "status": status,
            "market_count": int(market_count),
            "price_snapshot_count": int(price_snapshot_count),
            "detected_opportunity_count": int(detected_opportunity_count),
            "emitted_signal_count": int(emitted_signal_count),
            "duration_seconds": round(
                max(
                    0.0,
                    (
                        finished_at
                        - _load_started_at(scan_id)
                    ).total_seconds(),
                ),
                4,
            ),
            "error_message": error_message or "",
        },
    )


def _load_started_at(scan_id: str) -> datetime:
    if not SQLITE_PATH.exists():
        return datetime.now(timezone.utc)
    try:
        with sqlite3.connect(SQLITE_PATH) as connection:
            _ensure_scan_batches_schema(connection)
            row = connection.execute(
                "SELECT started_at FROM scan_batches WHERE scan_id = ?",
                (scan_id,),
            ).fetchone()
    except sqlite3.Error:
        return datetime.now(timezone.utc)

    if not row or not row[0]:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(str(row[0]).replace("Z", "+00:00")).astimezone(timezone.utc)


def _upsert_scan_batch(values: dict[str, object]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SQLITE_PATH) as connection:
        _ensure_scan_batches_schema(connection)
        existing_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(scan_batches)").fetchall()
        }
        payload = {key: value for key, value in values.items() if key in existing_columns}
        scan_id = str(payload.pop("scan_id"))
        assignments = ", ".join(f"{column} = ?" for column in payload)
        params = list(payload.values()) + [scan_id]
        updated = 0
        if assignments:
            cursor = connection.execute(
                f"UPDATE scan_batches SET {assignments} WHERE scan_id = ?",
                params,
            )
            updated = cursor.rowcount
        if updated == 0:
            insert_payload = {"scan_id": scan_id, **payload}
            columns = ", ".join(insert_payload.keys())
            placeholders = ", ".join("?" for _ in insert_payload)
            connection.execute(
                f"INSERT INTO scan_batches({columns}) VALUES ({placeholders})",
                list(insert_payload.values()),
            )
        connection.commit()


def _ensure_scan_batches_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_batches(
            scan_id TEXT PRIMARY KEY,
            scan_timestamp TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            limit_value INTEGER,
            min_liquidity REAL,
            min_ev REAL,
            bankroll_amount REAL,
            market_count INTEGER DEFAULT 0,
            price_snapshot_count INTEGER DEFAULT 0,
            detected_opportunity_count INTEGER DEFAULT 0,
            emitted_signal_count INTEGER DEFAULT 0,
            duration_seconds REAL DEFAULT 0,
            error_message TEXT DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_scan_batches_started_at
        ON scan_batches(started_at DESC)
        """
    )


def _iso_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
