from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from src.config import settings
from src.models import Event


@dataclass(slots=True)
class ConsensusResult:
    event_id: str
    probabilities: dict[str, float]
    model_confidence: float
    dispersion: float
    consensus_variance: float
    market_disagreement_score: float


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
                            "platform": market.platform,
                        }
                    )

        if not rows:
            return {}

        df = pd.DataFrame(rows)
        results: dict[str, ConsensusResult] = {}

        for event_id, event_frame in df.groupby("event_id"):
            probabilities: dict[str, float] = {}
            outcome_dispersion: list[float] = []
            outcome_variances: list[float] = []

            for outcome_label, outcome_frame in event_frame.groupby("outcome"):
                weights = outcome_frame.apply(
                    lambda row: math.log1p(max(float(row["liquidity"]), 1.0))
                    * settings.platform_reliability.get(str(row["platform"]), 1.0),
                    axis=1,
                )
                weighted_probability = (outcome_frame["probability"] * weights).sum() / weights.sum()
                probabilities[outcome_label] = float(weighted_probability)
                variance = float(outcome_frame["probability"].var(ddof=0) or 0.0)
                outcome_variances.append(variance)
                outcome_dispersion.append(float(math.sqrt(variance)))

            source_count = int(event_frame["market_id"].nunique())
            effective_liquidity = float(event_frame["liquidity"].sum())
            average_dispersion = sum(outcome_dispersion) / len(outcome_dispersion) if outcome_dispersion else 0.0
            consensus_variance = sum(outcome_variances) / len(outcome_variances) if outcome_variances else 0.0
            disagreement_score = min(1.0, average_dispersion * 4.0)
            confidence = self._confidence_score(
                source_count=source_count,
                effective_liquidity=effective_liquidity,
                average_dispersion=average_dispersion,
                consensus_variance=consensus_variance,
            )

            results[event_id] = ConsensusResult(
                event_id=event_id,
                probabilities=probabilities,
                model_confidence=confidence,
                dispersion=average_dispersion,
                consensus_variance=consensus_variance,
                market_disagreement_score=disagreement_score,
            )

        return results

    @staticmethod
    def _confidence_score(
        source_count: int,
        effective_liquidity: float,
        average_dispersion: float,
        consensus_variance: float,
    ) -> float:
        source_signal = min(0.28, math.log1p(max(source_count, 0)) * 0.14)
        liquidity_signal = min(0.36, math.log1p(max(effective_liquidity, 1.0)) / 24.0)
        dispersion_penalty = min(0.55, average_dispersion * 2.6)
        variance_penalty = min(0.3, consensus_variance * 8.0)
        base_confidence = 0.18 + source_signal + liquidity_signal - dispersion_penalty - variance_penalty
        # Keep confidence calibrated below certainty; exact 1.0 should be effectively unreachable.
        return round(max(0.02, min(0.98, base_confidence)), 4)
