from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.models import Event
from src.storage.price_history_store import PriceHistoryPoint, price_history_store


@dataclass(slots=True)
class MovementMetrics:
    price_change_5m: float = 0.0
    price_change_30m: float = 0.0
    price_change_2h: float = 0.0
    price_change_24h: float = 0.0
    movement_signal: str = "stable"
    movement_confidence: float = 0.0
    volatility_5m: float = 0.0
    volatility_30m: float = 0.0
    volatility_2h: float = 0.0


class MovementDetector:
    async def analyze(self, events: list[Event]) -> dict[tuple[str, str, str], MovementMetrics]:
        market_keys = []
        event_outcome_map: dict[tuple[str, str], list[tuple[str, str, str]]] = {}

        for event in events:
            for market in event.markets:
                for outcome in market.outcomes:
                    if outcome.implied_probability is None:
                        continue
                    key = (market.platform, market.market_id, outcome.label.strip().upper())
                    market_keys.append(key)
                    event_outcome_map.setdefault((event.event_id, outcome.label.strip().upper()), []).append(key)

        history_map = await price_history_store.get_history(market_keys)
        metrics_map: dict[tuple[str, str, str], MovementMetrics] = {}

        for key, history in history_map.items():
            metrics = MovementMetrics(
                price_change_5m=self._price_change(history, timedelta(minutes=5)),
                price_change_30m=self._price_change(history, timedelta(minutes=30)),
                price_change_2h=self._price_change(history, timedelta(hours=2)),
                price_change_24h=self._price_change(history, timedelta(hours=24)),
                volatility_5m=self._volatility(history, timedelta(minutes=5)),
                volatility_30m=self._volatility(history, timedelta(minutes=30)),
                volatility_2h=self._volatility(history, timedelta(hours=2)),
            )
            metrics_map[key] = metrics

        for key, metrics in metrics_map.items():
            signal, confidence = self._movement_signal(metrics)
            metrics.movement_signal = signal
            metrics.movement_confidence = confidence

        for _, keys in event_outcome_map.items():
            if len(keys) < 2:
                continue

            strongest_change = max(
                (abs(metrics_map[key].price_change_30m) for key in keys if key in metrics_map),
                default=0.0,
            )

            for key in keys:
                metrics = metrics_map.get(key)
                if metrics is None:
                    continue
                if strongest_change > 0.08 and abs(metrics.price_change_30m) < 0.02:
                    metrics.movement_signal = "lagging_market"
                    metrics.movement_confidence = max(
                        metrics.movement_confidence,
                        min(1.0, strongest_change),
                    )

        return metrics_map

    @staticmethod
    def _price_change(history: list[PriceHistoryPoint], window: timedelta) -> float:
        if len(history) < 2:
            return 0.0
        latest = history[-1]
        target_time = latest.timestamp - window
        baseline = next((point for point in reversed(history[:-1]) if point.timestamp <= target_time), history[0])
        return round(latest.probability - baseline.probability, 4)

    @staticmethod
    def _volatility(history: list[PriceHistoryPoint], window: timedelta) -> float:
        if len(history) < 2:
            return 0.0
        latest = history[-1].timestamp
        window_points = [point.probability for point in history if point.timestamp >= latest - window]
        if len(window_points) < 2:
            return 0.0
        return round(float(statistics.pstdev(window_points)), 4)

    @staticmethod
    def _movement_signal(metrics: MovementMetrics) -> tuple[str, float]:
        max_move = max(abs(metrics.price_change_5m), abs(metrics.price_change_30m), abs(metrics.price_change_2h))
        if abs(metrics.price_change_5m) >= 0.08:
            signal = "rapid_up" if metrics.price_change_5m > 0 else "rapid_down"
            return signal, min(1.0, abs(metrics.price_change_5m) * 10.0)
        if abs(metrics.price_change_30m) <= 0.01 and abs(metrics.price_change_2h) <= 0.015:
            return "stale_market", 0.05
        return "stable", min(0.75, max_move * 6.0)
