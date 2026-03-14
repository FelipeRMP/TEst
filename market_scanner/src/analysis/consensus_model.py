from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from models import Event


@dataclass(slots=True)
class ConsensusResult:
    event_id: str
    probabilities: dict[str, float]
    model_confidence: float
    dispersion: float


class ConsensusModel:
    def compute(self, events: list[Event]) -> dict[str, ConsensusResult]:
        rows: list[dict[str, object]] = []
        for event in events:
            for market in event.markets:
                for outcome in market.outcomes:
                    if outcome.implied_probability is None:
                        continue
                    rows.append(
                        {
                            "event_id": event.event_id,
                            "outcome": outcome.label.strip().upper(),
                            "probability": outcome.implied_probability,
                            "liquidity": market.liquidity,
                            "market_id": market.market_id,
                        }
                    )

        if not rows:
            return {}

        df = pd.DataFrame(rows)
        results: dict[str, ConsensusResult] = {}

        for event_id, event_frame in df.groupby("event_id"):
            probabilities: dict[str, float] = {}
            outcome_dispersion: list[float] = []

            for outcome_label, outcome_frame in event_frame.groupby("outcome"):
                weights = outcome_frame["liquidity"].fillna(0).map(lambda value: math.log1p(max(float(value), 1.0)))
                weighted_probability = (outcome_frame["probability"] * weights).sum() / weights.sum()
                probabilities[outcome_label] = float(weighted_probability)
                outcome_dispersion.append(float(outcome_frame["probability"].std(ddof=0) or 0.0))

            source_count = int(event_frame["market_id"].nunique())
            effective_liquidity = float(event_frame["liquidity"].sum())
            average_dispersion = sum(outcome_dispersion) / len(outcome_dispersion) if outcome_dispersion else 0.0
            confidence = min(
                1.0,
                0.15 * source_count + (math.log1p(max(effective_liquidity, 1.0)) / 10.0) - average_dispersion,
            )
            confidence = max(0.0, confidence)

            results[event_id] = ConsensusResult(
                event_id=event_id,
                probabilities=probabilities,
                model_confidence=confidence,
                dispersion=average_dispersion,
            )

        return results
