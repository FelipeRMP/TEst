from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from backend.utils.market_ids import normalize_market_id

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
SQLITE_PATH = DATA_DIR / "trading_data.db"
CSV_PATHS = {
    "signal_log.csv": ("platform", "market_id", "side"),
    "price_history.csv": ("platform", "market_id", None),
}


def repair_storage() -> dict[str, int]:
    repaired = {"sqlite_rows": 0, "csv_rows": 0}
    if SQLITE_PATH.exists():
        repaired["sqlite_rows"] = _repair_sqlite()
    repaired["csv_rows"] = _repair_csvs()
    return repaired


def _repair_sqlite() -> int:
    updated_rows = 0
    with sqlite3.connect(SQLITE_PATH) as connection:
        updated_rows += _repair_table(connection, "signals", side_column="side")
        updated_rows += _repair_table(connection, "price_history", side_column=None)
        updated_rows += _repair_table(connection, "simulated_trades", side_column="side")
        connection.commit()
    return updated_rows


def _repair_table(connection: sqlite3.Connection, table_name: str, side_column: str | None) -> int:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    if row is None:
        return 0

    columns = {item[1] for item in connection.execute(f"PRAGMA table_info({table_name})")}
    if "market_id" not in columns or ("platform" not in columns and table_name != "simulated_trades"):
        return 0

    selected_columns = ["rowid", "market_id"]
    if "platform" in columns:
        selected_columns.append("platform")
    if side_column and side_column in columns:
        selected_columns.append(side_column)
    rows = connection.execute(f"SELECT {', '.join(selected_columns)} FROM {table_name}").fetchall()
    updated = 0
    for row_values in rows:
        rowid = row_values[0]
        market_id = row_values[1]
        platform = row_values[2] if len(row_values) >= 3 else ""
        side = row_values[3] if len(row_values) >= 4 else ""
        if not platform and isinstance(market_id, str) and ":" in market_id:
            candidate = market_id.split(":", maxsplit=1)[0].lower()
            if candidate in {"polymarket", "kalshi"}:
                platform = candidate
        normalized = normalize_market_id(str(platform or ""), str(market_id or ""), str(side or ""))
        if normalized == market_id:
            continue
        connection.execute(
            f"UPDATE {table_name} SET market_id = ? WHERE rowid = ?",
            (normalized, rowid),
        )
        updated += 1
    return updated


def _repair_csvs() -> int:
    updated_rows = 0
    for file_name, (platform_key, market_id_key, side_key) in CSV_PATHS.items():
        path = DATA_DIR / file_name
        if not path.exists():
            continue
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            rows = list(reader)
        changed = False
        for row in rows:
            normalized = normalize_market_id(
                row.get(platform_key, "") or "",
                row.get(market_id_key, "") or "",
                row.get(side_key, "") if side_key else "",
            )
            if row.get(market_id_key, "") == normalized:
                continue
            row[market_id_key] = normalized
            updated_rows += 1
            changed = True
        if not changed:
            continue
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    return updated_rows


if __name__ == "__main__":
    repaired = repair_storage()
    print(f"Repaired {repaired['sqlite_rows']} SQLite rows and {repaired['csv_rows']} CSV rows.")
