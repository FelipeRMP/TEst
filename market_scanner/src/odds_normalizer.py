from __future__ import annotations

from typing import Sequence


def decimal_to_probability(decimal_odds: float) -> float:
    if decimal_odds <= 1:
        raise ValueError("Decimal odds must be greater than 1.")
    return 1.0 / decimal_odds


def fractional_to_probability(fractional_odds: str | tuple[int, int]) -> float:
    if isinstance(fractional_odds, tuple):
        numerator, denominator = fractional_odds
    else:
        parts = fractional_odds.split("/", maxsplit=1)
        if len(parts) != 2:
            raise ValueError("Fractional odds must be in 'a/b' format.")
        numerator, denominator = (int(part.strip()) for part in parts)

    if numerator < 0 or denominator <= 0:
        raise ValueError("Fractional odds must be non-negative with a positive denominator.")

    return denominator / (numerator + denominator)


def american_to_probability(american_odds: int) -> float:
    if american_odds == 0:
        raise ValueError("American odds cannot be zero.")
    if american_odds > 0:
        return 100.0 / (american_odds + 100.0)

    absolute = abs(american_odds)
    return absolute / (absolute + 100.0)


def remove_vig(probabilities: Sequence[float]) -> list[float]:
    total = sum(probabilities)
    if total <= 0:
        raise ValueError("Probabilities must sum to a positive number.")
    return [probability / total for probability in probabilities]


def normalize_odds(value: str | int | float | tuple[int, int], odds_type: str) -> float:
    odds_type_normalized = odds_type.strip().lower()
    if odds_type_normalized == "decimal":
        return decimal_to_probability(float(value))
    if odds_type_normalized == "fractional":
        return fractional_to_probability(value)  # type: ignore[arg-type]
    if odds_type_normalized == "american":
        return american_to_probability(int(value))
    raise ValueError(f"Unsupported odds type: {odds_type}")
