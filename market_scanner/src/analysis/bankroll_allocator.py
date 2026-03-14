from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BankrollRecommendation:
    recommended_bankroll_fraction: float
    recommended_position_size: float
    risk_level: str


class BankrollAllocator:
    def __init__(self, min_safety_factor: float = 0.25, max_safety_factor: float = 0.5) -> None:
        self.min_safety_factor = min_safety_factor
        self.max_safety_factor = max_safety_factor

    def recommend(
        self,
        expected_value: float,
        confidence: float,
        liquidity: float,
        bankroll_amount: float,
        implied_probability: float,
    ) -> BankrollRecommendation:
        if bankroll_amount <= 0 or expected_value <= 0 or confidence <= 0 or implied_probability <= 0:
            return BankrollRecommendation(0.0, 0.0, "high")

        decimal_odds = 1.0 / max(implied_probability, 0.01)
        edge = expected_value
        payout_multiple = max(decimal_odds - 1.0, 0.01)
        kelly_fraction = max(0.0, edge / payout_multiple)

        safety_factor = self.min_safety_factor + (
            (self.max_safety_factor - self.min_safety_factor) * max(0.0, min(confidence, 1.0))
        )

        recommended_fraction = kelly_fraction * safety_factor

        # Avoid suggesting a position that is too large relative to displayed liquidity.
        liquidity_cap = min(0.1, max(0.0, liquidity / max(bankroll_amount * 20.0, 1.0)))
        recommended_fraction = min(recommended_fraction, liquidity_cap if liquidity_cap > 0 else recommended_fraction)
        recommended_fraction = min(max(recommended_fraction, 0.0), 0.1)

        position_size = bankroll_amount * recommended_fraction

        risk_score = (1.0 - confidence) + (0.04 if recommended_fraction > 0.05 else 0.0)
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
        )
