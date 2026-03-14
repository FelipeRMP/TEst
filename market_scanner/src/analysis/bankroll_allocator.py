from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BankrollRecommendation:
    recommended_bankroll_fraction: float
    recommended_position_size: float
    risk_level: str
    volatility_penalty: float = 0.0
    movement_confidence_weight: float = 1.0


class BankrollAllocator:
    def __init__(self, safety_factor: float = 0.25) -> None:
        self.safety_factor = safety_factor

    def recommend(
        self,
        expected_value: float,
        consensus_probability: float,
        confidence: float,
        liquidity: float,
        bankroll_amount: float,
        implied_probability: float,
        volatility_30m: float = 0.0,
        movement_confidence: float = 0.0,
        movement_signal: str = "stable",
    ) -> BankrollRecommendation:
        if (
            bankroll_amount <= 0
            or expected_value <= 0
            or confidence <= 0
            or implied_probability <= 0
            or consensus_probability <= 0
            or consensus_probability >= 1
        ):
            return BankrollRecommendation(0.0, 0.0, "high")

        p = consensus_probability
        q = 1.0 - p
        payout_multiple = max((1.0 / max(implied_probability, 0.01)) - 1.0, 0.01)
        kelly_fraction = max(((payout_multiple * p) - q) / payout_multiple, 0.0)

        recommended_fraction = kelly_fraction * self.safety_factor

        volatility_penalty = min(0.75, max(0.0, volatility_30m * 6.0))
        liquidity_penalty = 0.75 if liquidity < 500 else 0.5 if liquidity < 2_500 else 0.2
        movement_confidence_weight = 1.0
        if movement_signal in {"stale_market", "conflicting_signal"}:
            movement_confidence_weight = 0.45
        elif movement_signal == "lagging_market":
            movement_confidence_weight = 0.9 + min(0.1, movement_confidence * 0.2)
        else:
            movement_confidence_weight = 0.8 + min(0.2, movement_confidence * 0.2)

        confidence_adjustment = max(
            0.05,
            confidence * (1.0 - volatility_penalty) * movement_confidence_weight * (1.0 - liquidity_penalty * 0.5),
        )
        recommended_fraction *= confidence_adjustment

        liquidity_cap = min(0.1, max(0.0, liquidity / max(bankroll_amount * 20.0, 1.0)))
        recommended_fraction = min(recommended_fraction, liquidity_cap if liquidity_cap > 0 else recommended_fraction)
        recommended_fraction = min(max(recommended_fraction, 0.0), 0.1)

        position_size = bankroll_amount * recommended_fraction

        risk_score = (
            (1.0 - confidence)
            + volatility_penalty
            + (0.35 if movement_signal in {"stale_market", "conflicting_signal"} else 0.0)
            + (0.04 if recommended_fraction > 0.05 else 0.0)
        )
        if risk_score < 0.35:
            risk_level = "low"
        elif risk_score < 0.7:
            risk_level = "medium"
        else:
            risk_level = "high"

        return BankrollRecommendation(
            recommended_bankroll_fraction=round(recommended_fraction, 4),
            recommended_position_size=round(position_size, 2),
            risk_level=risk_level,
            volatility_penalty=round(volatility_penalty, 4),
            movement_confidence_weight=round(movement_confidence_weight, 4),
        )
