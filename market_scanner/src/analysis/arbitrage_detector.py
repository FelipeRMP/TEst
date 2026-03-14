from __future__ import annotations

import math
from itertools import combinations

from src.analysis.consensus_model import ConsensusResult
from src.config import settings
from src.models import Event, Market, Opportunity, Outcome


class OpportunityDetector:
    def __init__(self, fee_bps: int = settings.fee_bps, min_ev: float = settings.min_expected_value) -> None:
        self.fee_rate = fee_bps / 10_000.0
        self.min_ev = min_ev

    def find(self, events: list[Event], consensus_map: dict[str, ConsensusResult]) -> list[Opportunity]:
        opportunities: list[Opportunity] = []
        for event in events:
            consensus = consensus_map.get(event.event_id)
            opportunities.extend(self._find_arbitrage(event, consensus))
            opportunities.extend(self._find_positive_ev(event, consensus))

        return sorted(
            opportunities,
            key=lambda item: self._base_score(item, consensus_map.get(item.event_id)),
            reverse=True,
        )

    def _find_arbitrage(
        self,
        event: Event,
        consensus: ConsensusResult | None,
    ) -> list[Opportunity]:
        if len(event.markets) < 2:
            return []

        binary_quotes: list[tuple[Market, Outcome, str]] = []
        for market in event.markets:
            for outcome in market.outcomes:
                label = outcome.label.strip().upper()
                if label in {"YES", "NO"} and outcome.implied_probability is not None:
                    binary_quotes.append((market, outcome, label))

        opportunities: list[Opportunity] = []
        yes_quotes = [(market, outcome) for market, outcome, label in binary_quotes if label == "YES"]
        no_quotes = [(market, outcome) for market, outcome, label in binary_quotes if label == "NO"]

        for (yes_market, yes_outcome), (no_market, no_outcome) in combinations(yes_quotes + no_quotes, 2):
            if yes_outcome.label.strip().upper() == no_outcome.label.strip().upper():
                continue
            if yes_outcome.implied_probability is None or no_outcome.implied_probability is None:
                continue

            if yes_outcome.label.strip().upper() != "YES":
                yes_market, no_market = no_market, yes_market
                yes_outcome, no_outcome = no_outcome, yes_outcome

            yes_entry_price = self._entry_price(yes_outcome, "BUY")
            no_entry_price = self._entry_price(no_outcome, "BUY")
            if yes_entry_price is None or no_entry_price is None:
                continue

            total_cost = yes_entry_price + no_entry_price + (2 * self.fee_rate)
            if total_cost >= 1:
                continue

            net_edge = 1 - total_cost
            executable_size = min(yes_market.liquidity, no_market.liquidity)
            opportunities.append(
                Opportunity(
                    event_id=event.event_id,
                    event_title=event.title,
                    opportunity_type="cross_market_arbitrage",
                    platforms=[yes_market.platform, no_market.platform],
                    prices={
                        f"{yes_market.platform}:{yes_market.market_id}:YES": yes_entry_price,
                        f"{no_market.platform}:{no_market.market_id}:NO": no_entry_price,
                    },
                    implied_probabilities={
                        f"{yes_market.platform}:{yes_market.market_id}:YES": yes_entry_price,
                        f"{no_market.platform}:{no_market.market_id}:NO": no_entry_price,
                    },
                    expected_value=net_edge,
                    net_edge=net_edge,
                    max_executable_size=executable_size,
                    risk=self._risk_payload(event, consensus, executable_size),
                    suggested_trade_strategy=(
                        f"Buy YES in {yes_market.platform} market {yes_market.market_id} and "
                        f"buy NO in {no_market.platform} market {no_market.market_id} up to available depth."
                    ),
                )
            )

        return opportunities

    def _find_positive_ev(
        self,
        event: Event,
        consensus: ConsensusResult | None,
    ) -> list[Opportunity]:
        if consensus is None:
            return []

        opportunities: list[Opportunity] = []
        for market in event.markets:
            for outcome in market.outcomes:
                if outcome.implied_probability is None:
                    continue

                outcome_label = outcome.label.strip().upper()
                consensus_probability = consensus.probabilities.get(outcome_label)
                if consensus_probability is None:
                    continue

                entry_price = self._entry_price(outcome, "BUY")
                if entry_price is None:
                    continue

                true_expected_value = self._true_expected_value(consensus_probability, entry_price)
                expected_value = true_expected_value - self.fee_rate
                if expected_value < self.min_ev:
                    continue

                simple_edge = consensus_probability - entry_price
                suspicious_ev = expected_value > 3.0

                opportunities.append(
                    Opportunity(
                        event_id=event.event_id,
                        event_title=event.title,
                        opportunity_type="positive_ev",
                        platforms=[market.platform],
                        prices={f"{market.platform}:{market.market_id}:{outcome_label}": entry_price},
                        implied_probabilities={
                            f"{market.platform}:{market.market_id}:{outcome_label}": entry_price
                        },
                        expected_value=expected_value,
                        net_edge=simple_edge,
                        max_executable_size=market.liquidity,
                        risk=self._risk_payload(
                            event,
                            consensus,
                            market.liquidity,
                            suspicious_ev=suspicious_ev,
                        ),
                        suggested_trade_strategy=(
                            f"Buy {outcome_label} on {market.platform} market {market.market_id}; "
                            f"consensus fair probability is {consensus_probability:.3f} versus executable ask {entry_price:.3f}."
                        ),
                    )
                )

        return opportunities

    @staticmethod
    def _risk_payload(
        event: Event,
        consensus: ConsensusResult | None,
        executable_size: float,
        suspicious_ev: bool = False,
    ) -> dict[str, float | str]:
        model_confidence = consensus.model_confidence if consensus else 0.0
        consensus_variance = consensus.consensus_variance if consensus else 0.0
        liquidity_risk = 0.1 if executable_size >= 10_000 else 0.35 if executable_size >= 1_000 else 0.6
        resolution_risk = max(0.0, 1.0 - event.match_confidence)
        overall_score = (liquidity_risk + resolution_risk + (1.0 - model_confidence) + consensus_variance) / 4.0

        if overall_score < 0.25:
            overall = "low"
        elif overall_score < 0.5:
            overall = "medium"
        else:
            overall = "high"

        return {
            "overall": overall,
            "overall_score": round(overall_score, 4),
            "match_confidence": round(event.match_confidence, 4),
            "model_confidence": round(model_confidence, 4),
            "liquidity_risk": round(liquidity_risk, 4),
            "resolution_risk": round(resolution_risk, 4),
            "consensus_variance": round(consensus_variance, 4),
            "suspicious_ev": "true" if suspicious_ev else "false",
        }

    @staticmethod
    def _true_expected_value(consensus_probability: float, market_probability: float) -> float:
        if market_probability <= 0:
            return 0.0
        p = consensus_probability
        q = 1.0 - p
        profit_if_win = 1.0 - market_probability
        loss_if_lose = market_probability
        return (p * profit_if_win) - (q * loss_if_lose)

    @staticmethod
    def _entry_price(outcome: Outcome, trade_side: str) -> float | None:
        normalized_side = trade_side.strip().upper()
        if normalized_side == "SELL":
            candidate = outcome.best_bid if outcome.best_bid is not None else outcome.bid
        else:
            candidate = outcome.best_ask if outcome.best_ask is not None else outcome.ask

        if candidate is not None and 0 < candidate < 1:
            return candidate
        if outcome.implied_probability is not None and 0 < outcome.implied_probability < 1:
            return outcome.implied_probability
        if outcome.price is not None and 0 < outcome.price < 1:
            return outcome.price
        return None

    @staticmethod
    def _base_score(opportunity: Opportunity, consensus: ConsensusResult | None) -> float:
        liquidity = opportunity.max_executable_size or 0.0
        confidence = consensus.model_confidence if consensus else 0.0
        disagreement = consensus.market_disagreement_score if consensus else 0.0
        effective_ev = min(opportunity.expected_value, 3.0)
        return (
            (effective_ev * 1.5)
            + (math.log1p(max(liquidity, 0.0)) * 0.08)
            + (confidence * 0.3)
            - (disagreement * 0.2)
        )
