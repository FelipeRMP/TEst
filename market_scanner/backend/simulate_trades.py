from __future__ import annotations

import csv
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.utils.market_ids import normalize_market_id

DATA_DIR = PROJECT_ROOT / "data"
SIGNAL_LOG_PATH = DATA_DIR / "signal_log.csv"
PRICE_LOG_PATH = DATA_DIR / "price_history.csv"
SQLITE_PATH = DATA_DIR / "trading_data.db"
EXIT_AFTER_HOURS = 24
EXIT_WHEN_PRICE_REACHES_CONSENSUS = True


@dataclass(slots=True)
class SignalRow:
    timestamp: datetime
    event_id: str
    event_title: str
    platform: str
    market_id: str
    side: str
    market_price: float
    consensus_probability: float
    expected_value: float
    signal_strength: float
    liquidity: float
    suggested_bankroll_percent: float
    suggested_amount: float
    best_bid: float | None = None
    best_ask: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    spread: float | None = None
    spread_percent: float | None = None


@dataclass(slots=True)
class PriceRow:
    timestamp: datetime
    platform: str
    market_id: str
    event_id: str
    price: float
    liquidity: float


@dataclass(slots=True)
class SimulatedTrade:
    entered_at: datetime
    exited_at: datetime
    market_id: str
    side: str
    stake: float
    entry_price: float
    exit_price: float
    expected_value: float
    pnl: float
    holding_hours: float
    spread_percent: float
    liquidity_at_entry: float


def load_signals() -> list[SignalRow]:
    if not SIGNAL_LOG_PATH.exists():
        return []
    with SIGNAL_LOG_PATH.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            SignalRow(
                timestamp=_parse_timestamp(row.get("timestamp")),
                event_id=str(row.get("event_id", "") or ""),
                event_title=str(row.get("event_title", "") or ""),
                platform=str(row.get("platform", "") or ""),
                market_id=normalize_market_id(
                    str(row.get("platform", "") or ""),
                    str(row.get("market_id", "") or ""),
                    str(row.get("side", "") or ""),
                ),
                side=str(row.get("side", "") or ""),
                market_price=_to_float(row.get("market_price")),
                consensus_probability=_to_float(row.get("consensus_probability")),
                expected_value=_to_float(row.get("expected_value")),
                signal_strength=_to_float(row.get("signal_strength")),
                liquidity=_to_float(row.get("liquidity")),
                suggested_bankroll_percent=_to_float(row.get("suggested_bankroll_percent")),
                suggested_amount=_to_float(row.get("suggested_amount")),
                best_bid=_to_optional_float(row.get("best_bid")),
                best_ask=_to_optional_float(row.get("best_ask")),
                bid_size=_to_optional_float(row.get("bid_size")),
                ask_size=_to_optional_float(row.get("ask_size")),
                spread=_to_optional_float(row.get("spread")),
                spread_percent=_to_optional_float(row.get("spread_percent")),
            )
            for row in reader
        ]


def load_price_history() -> list[PriceRow]:
    if not PRICE_LOG_PATH.exists():
        return []
    with PRICE_LOG_PATH.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            PriceRow(
                timestamp=_parse_timestamp(row.get("timestamp")),
                platform=str(row.get("platform", "") or ""),
                market_id=normalize_market_id(
                    str(row.get("platform", "") or ""),
                    str(row.get("market_id", "") or ""),
                ),
                event_id=str(row.get("event_id", "") or ""),
                price=_to_float(row.get("price")),
                liquidity=_to_float(row.get("liquidity")),
            )
            for row in reader
        ]


def simulate_trades(signals: list[SignalRow], prices: list[PriceRow]) -> list[SimulatedTrade]:
    price_index = _index_prices(prices)
    simulated: list[SimulatedTrade] = []

    for signal in signals:
        stake = signal.suggested_amount
        if stake <= 0 or signal.market_price <= 0 or signal.market_price >= 1:
            continue

        exit_deadline = signal.timestamp + timedelta(hours=EXIT_AFTER_HOURS)
        market_prices = price_index.get(signal.market_id, [])
        entry_price = _entry_price(signal)
        exit_price = entry_price
        exit_time = signal.timestamp

        target_hit = False
        for price_row in market_prices:
            if price_row.timestamp < signal.timestamp:
                continue
            exit_price = price_row.price
            exit_time = price_row.timestamp
            if EXIT_WHEN_PRICE_REACHES_CONSENSUS and price_row.price >= signal.consensus_probability:
                target_hit = price_row.price >= signal.consensus_probability
                break
            if price_row.timestamp >= exit_deadline:
                break

        if exit_time < exit_deadline and not target_hit:
            later_prices = [row for row in market_prices if row.timestamp >= exit_deadline]
            if later_prices:
                exit_price = later_prices[0].price
                exit_time = later_prices[0].timestamp
            else:
                exit_time = exit_deadline

        pnl = stake * (exit_price - entry_price)
        if (signal.spread_percent or 0.0) > 0.15:
            pnl *= 0.5
        simulated.append(
            SimulatedTrade(
                entered_at=signal.timestamp,
                exited_at=exit_time,
                market_id=signal.market_id,
                side=signal.side,
                stake=stake,
                entry_price=entry_price,
                exit_price=exit_price,
                expected_value=signal.expected_value,
                pnl=round(pnl, 6),
                holding_hours=round((exit_time - signal.timestamp).total_seconds() / 3600.0, 4),
                spread_percent=signal.spread_percent or 0.0,
                liquidity_at_entry=signal.liquidity,
            )
        )

    _write_simulated_trades(simulated)
    return simulated


def summarize(trades: list[SimulatedTrade]) -> dict[str, float]:
    if not trades:
        return {
            "total_trades": 0.0,
            "win_rate": 0.0,
            "average_profit": 0.0,
            "average_expected_value": 0.0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "average_holding_time": 0.0,
            "average_spread": 0.0,
            "average_liquidity_at_entry": 0.0,
        }

    total_pnl = sum(trade.pnl for trade in trades)
    wins = sum(1 for trade in trades if trade.pnl > 0)
    average_profit = total_pnl / len(trades)
    average_expected_value = sum(trade.expected_value for trade in trades) / len(trades)

    running = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for trade in trades:
        running += trade.pnl
        peak = max(peak, running)
        max_drawdown = max(max_drawdown, peak - running)

    return {
        "total_trades": float(len(trades)),
        "win_rate": wins / len(trades),
        "average_profit": average_profit,
        "average_expected_value": average_expected_value,
        "total_pnl": total_pnl,
        "max_drawdown": max_drawdown,
        "average_holding_time": sum(trade.holding_hours for trade in trades) / len(trades),
        "average_spread": sum(trade.spread_percent for trade in trades) / len(trades),
        "average_liquidity_at_entry": sum(trade.liquidity_at_entry for trade in trades) / len(trades),
    }


def _index_prices(prices: list[PriceRow]) -> dict[str, list[PriceRow]]:
    index: dict[str, list[PriceRow]] = {}
    for row in sorted(prices, key=lambda item: item.timestamp):
        index.setdefault(row.market_id, []).append(row)
    return index


def _entry_price(signal: SignalRow) -> float:
    side = signal.side.strip().upper()
    if side in {"SELL", "SHORT"}:
        return signal.best_bid if signal.best_bid is not None else signal.market_price
    return signal.best_ask if signal.best_ask is not None else signal.market_price


def _write_simulated_trades(trades: list[SimulatedTrade]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SQLITE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS simulated_trades(
                entered_at TEXT NOT NULL,
                exited_at TEXT NOT NULL,
                market_id TEXT,
                side TEXT,
                stake REAL,
                entry_price REAL,
                exit_price REAL,
                expected_value REAL,
                pnl REAL
            )
            """
        )
        connection.execute("DELETE FROM simulated_trades")
        connection.executemany(
            """
            INSERT INTO simulated_trades(
                entered_at, exited_at, market_id, side, stake, entry_price, exit_price, expected_value, pnl
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    trade.entered_at.isoformat(),
                    trade.exited_at.isoformat(),
                    trade.market_id,
                    trade.side,
                    trade.stake,
                    trade.entry_price,
                    trade.exit_price,
                    trade.expected_value,
                    trade.pnl,
                )
                for trade in trades
            ],
        )
        connection.commit()


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _to_float(value: str | float | int | None) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_optional_float(value: str | float | int | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    signals = load_signals()
    prices = load_price_history()
    trades = simulate_trades(signals, prices)
    summary = summarize(trades)

    print(f"Total trades: {int(summary['total_trades'])}")
    print(f"Win rate: {summary['win_rate'] * 100:.1f}%")
    print(f"Average profit: ${summary['average_profit']:.2f}")
    print(f"Average EV: {summary['average_expected_value'] * 100:.2f}%")
    print(f"Realized profit: ${summary['total_pnl']:.2f}")
    print(f"Max drawdown: ${summary['max_drawdown']:.2f}")
    print(f"Average holding time: {summary['average_holding_time']:.2f} hours")
    print(f"Average spread: {summary['average_spread'] * 100:.2f}%")
    print(f"Average liquidity at entry: {summary['average_liquidity_at_entry']:.2f}")


if __name__ == "__main__":
    main()
