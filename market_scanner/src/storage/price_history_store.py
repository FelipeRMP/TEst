from __future__ import annotations

import asyncio
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.config import settings
from src.models import Event


@dataclass(slots=True)
class PriceHistoryPoint:
    timestamp: datetime
    platform: str
    event_id: str
    market_id: str
    outcome: str
    probability: float
    liquidity: float


class PriceHistoryStore:
    def __init__(self, db_path: str = settings.price_history_db_path) -> None:
        self.db_path = Path(db_path)
        self._initialized = False
        self._recent_cache: dict[tuple[str, str, str], deque[PriceHistoryPoint]] = defaultdict(
            lambda: deque(maxlen=settings.price_history_cache_size)
        )

    async def ensure_initialized(self) -> None:
        if self._initialized:
            return
        await asyncio.to_thread(self._initialize_db)
        self._initialized = True

    async def record_event_prices(self, events: list[Event], timestamp: datetime | None = None) -> None:
        await self.ensure_initialized()
        captured_at = timestamp or datetime.now(timezone.utc)
        rows: list[tuple[str, str, str, str, str, float, float]] = []

        for event in events:
            for market in event.markets:
                for outcome in market.outcomes:
                    if outcome.implied_probability is None:
                        continue
                    point = PriceHistoryPoint(
                        timestamp=captured_at,
                        platform=market.platform,
                        event_id=event.event_id,
                        market_id=market.market_id,
                        outcome=outcome.label.strip().upper(),
                        probability=outcome.implied_probability,
                        liquidity=market.liquidity,
                    )
                    self._recent_cache[(point.platform, point.market_id, point.outcome)].append(point)
                    rows.append(
                        (
                            point.timestamp.isoformat(),
                            point.platform,
                            point.event_id,
                            point.market_id,
                            point.outcome,
                            point.probability,
                            point.liquidity,
                        )
                    )

        if rows:
            await asyncio.to_thread(self._insert_rows, rows)

    async def get_history(
        self,
        market_keys: list[tuple[str, str, str]],
        lookback: timedelta = timedelta(hours=24),
    ) -> dict[tuple[str, str, str], list[PriceHistoryPoint]]:
        await self.ensure_initialized()
        since = datetime.now(timezone.utc) - lookback
        db_rows = await asyncio.to_thread(self._fetch_rows, market_keys, since.isoformat())

        history_map: dict[tuple[str, str, str], list[PriceHistoryPoint]] = defaultdict(list)
        for row in db_rows:
            point = PriceHistoryPoint(
                timestamp=datetime.fromisoformat(row[0]),
                platform=row[1],
                event_id=row[2],
                market_id=row[3],
                outcome=row[4],
                probability=float(row[5]),
                liquidity=float(row[6]),
            )
            history_map[(point.platform, point.market_id, point.outcome)].append(point)

        for key in market_keys:
            for point in self._recent_cache.get(key, []):
                if point.timestamp >= since:
                    history_map[key].append(point)

        deduped: dict[tuple[str, str, str], list[PriceHistoryPoint]] = {}
        for key, points in history_map.items():
            unique = {
                (
                    point.timestamp.isoformat(),
                    point.platform,
                    point.market_id,
                    point.outcome,
                ): point
                for point in points
            }
            deduped[key] = sorted(unique.values(), key=lambda point: point.timestamp)

        return deduped

    def _initialize_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("PRAGMA journal_mode=WAL;")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS price_history(
                    timestamp TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    probability REAL NOT NULL,
                    liquidity REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_price_history_lookup
                ON price_history(platform, market_id, outcome, timestamp)
                """
            )
            connection.commit()

    def _insert_rows(self, rows: list[tuple[str, str, str, str, str, float, float]]) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.executemany(
                """
                INSERT INTO price_history(timestamp, platform, event_id, market_id, outcome, probability, liquidity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            connection.commit()

    def _fetch_rows(
        self,
        market_keys: list[tuple[str, str, str]],
        since_iso: str,
    ) -> list[tuple[str, str, str, str, str, float, float]]:
        if not market_keys:
            return []

        clauses = " OR ".join("(platform = ? AND market_id = ? AND outcome = ?)" for _ in market_keys)
        params: list[str] = [since_iso]
        for platform, market_id, outcome in market_keys:
            params.extend([platform, market_id, outcome])

        query = f"""
            SELECT timestamp, platform, event_id, market_id, outcome, probability, liquidity
            FROM price_history
            WHERE timestamp >= ?
              AND ({clauses})
            ORDER BY timestamp ASC
        """

        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(query, params)
            return list(cursor.fetchall())


price_history_store = PriceHistoryStore()
