from __future__ import annotations

from itertools import combinations

from analysis.consensus_model import ConsensusResult
from config import settings
from models import Event, Market, Opportunity, Outcome


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

        return sorted(opportunities, key=lambda item: (item.net_edge, item.expected_value), reverse=True)

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

            total_cost = yes_outcome.implied_probability + no_outcome.implied_probability + (2 * self.fee_rate)
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
                        f"{yes_market.platform}:{yes_market.market_id}:YES": yes_outcome.price or yes_outcome.implied_probability,
                        f"{no_market.platform}:{no_market.market_id}:NO": no_outcome.price or no_outcome.implied_probability,
                    },
                    implied_probabilities={
                        f"{yes_market.platform}:{yes_market.market_id}:YES": yes_outcome.implied_probability,
                        f"{no_market.platform}:{no_market.market_id}:NO": no_outcome.implied_probability,
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

                expected_value = consensus_probability - outcome.implied_probability - self.fee_rate
                if expected_value < self.min_ev:
                    continue

                opportunities.append(
                    Opportunity(
                        event_id=event.event_id,
                        event_title=event.title,
                        opportunity_type="positive_ev",
                        platforms=[market.platform],
                        prices={f"{market.platform}:{market.market_id}:{outcome_label}": outcome.price or outcome.implied_probability},
                        implied_probabilities={
                            f"{market.platform}:{market.market_id}:{outcome_label}": outcome.implied_probability
                        },
                        expected_value=expected_value,
                        net_edge=expected_value,
                        max_executable_size=market.liquidity,
                        risk=self._risk_payload(event, consensus, market.liquidity),
                        suggested_trade_strategy=(
                            f"Buy {outcome_label} on {market.platform} market {market.market_id}; "
                            f"consensus fair probability is {consensus_probability:.3f} versus market {outcome.implied_probability:.3f}."
                        ),
                    )
                )

        return opportunities

    @staticmethod
    def _risk_payload(
        event: Event,
        consensus: ConsensusResult | None,
        executable_size: float,
    ) -> dict[str, float | str]:
        model_confidence = consensus.model_confidence if consensus else 0.0
        liquidity_risk = 0.1 if executable_size >= 10_000 else 0.35 if executable_size >= 1_000 else 0.6
        resolution_risk = max(0.0, 1.0 - event.match_confidence)
        overall_score = (liquidity_risk + resolution_risk + (1.0 - model_confidence)) / 3.0

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
        }
