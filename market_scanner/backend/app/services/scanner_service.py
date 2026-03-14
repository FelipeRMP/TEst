from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from analysis.bankroll_allocator import BankrollAllocator  # noqa: E402
from models import Market, Opportunity  # noqa: E402
from scanner import ScanSnapshot, scan_markets  # noqa: E402

from ..schemas import OpportunityLegResponse, OpportunityResponse, ScanRequest


@dataclass(slots=True)
class CachedScan:
    params: ScanRequest
    scanned_at: datetime
    opportunities: list[OpportunityResponse]


class ScannerService:
    def __init__(self) -> None:
        self._cache: CachedScan | None = None
        self._bankroll_allocator = BankrollAllocator()

    async def run_scan(self, params: ScanRequest) -> CachedScan:
        snapshot = await scan_markets(
            limit=params.limit,
            min_liquidity=params.min_liquidity,
            min_ev=params.min_ev,
        )
        cached = CachedScan(
            params=params,
            scanned_at=datetime.now(timezone.utc),
            opportunities=self._build_responses(snapshot, params.bankroll_amount),
        )
        self._cache = cached
        return cached

    def get_cached(self) -> CachedScan | None:
        return self._cache

    def _build_responses(self, snapshot: ScanSnapshot, bankroll_amount: float) -> list[OpportunityResponse]:
        market_index: dict[tuple[str, str], Market] = {
            (market.platform, market.market_id): market for market in snapshot.markets
        }
        event_lookup = {event.event_id: event for event in snapshot.events}
        response_items: list[OpportunityResponse] = []

        for index, opportunity in enumerate(snapshot.opportunities, start=1):
            event = event_lookup.get(opportunity.event_id)
            consensus = snapshot.consensus_map.get(opportunity.event_id)
            legs: list[OpportunityLegResponse] = []

            for key, implied_probability in opportunity.implied_probabilities.items():
                platform, market_id, outcome_label = key.split(":", maxsplit=2)
                market = market_index.get((platform, market_id))
                if market is None:
                    continue

                consensus_probability = None
                if consensus is not None:
                    consensus_probability = consensus.probabilities.get(outcome_label.strip().upper())

                legs.append(
                    OpportunityLegResponse(
                        platform=platform,
                        market_id=market_id,
                        market_title=market.event_title,
                        outcome=outcome_label,
                        price=opportunity.prices.get(key, implied_probability),
                        implied_probability=implied_probability,
                        consensus_probability=consensus_probability,
                        liquidity=market.liquidity,
                        volume_24h=market.volume_24h,
                        spread_bps=market.spread_bps,
                        description=market.description,
                        resolution_criteria=market.resolution_criteria,
                    )
                )

            if not legs and event is not None:
                for market in event.markets:
                    for outcome in market.outcomes:
                        if outcome.implied_probability is None:
                            continue
                        legs.append(
                            OpportunityLegResponse(
                                platform=market.platform,
                                market_id=market.market_id,
                                market_title=market.event_title,
                                outcome=outcome.label,
                                price=outcome.price or outcome.implied_probability,
                                implied_probability=outcome.implied_probability,
                                consensus_probability=(
                                    snapshot.consensus_map.get(event.event_id).probabilities.get(
                                        outcome.label.strip().upper()
                                    )
                                    if snapshot.consensus_map.get(event.event_id)
                                    else None
                                ),
                                liquidity=market.liquidity,
                                volume_24h=market.volume_24h,
                                spread_bps=market.spread_bps,
                                description=market.description,
                                resolution_criteria=market.resolution_criteria,
                            )
                        )

            if not legs:
                continue

            primary_leg = max(legs, key=lambda leg: (leg.consensus_probability or 0, leg.liquidity))
            confidence = round(
                (
                    float(opportunity.risk.get("match_confidence", 0.0))
                    + float(opportunity.risk.get("model_confidence", 0.0))
                )
                / 2.0,
                4,
            )
            recommendation = self._bankroll_allocator.recommend(
                expected_value=opportunity.expected_value,
                confidence=confidence,
                liquidity=max(leg.liquidity for leg in legs),
                bankroll_amount=bankroll_amount,
                implied_probability=primary_leg.implied_probability,
            )

            response_items.append(
                OpportunityResponse(
                    opportunity_id=f"{opportunity.event_id}-{index}",
                    event_id=opportunity.event_id,
                    event=opportunity.event_title,
                    market=", ".join(
                        f"{leg.platform}:{leg.market_id}:{leg.outcome}" for leg in legs
                    ),
                    platform=primary_leg.platform,
                    platforms=sorted({leg.platform for leg in legs}),
                    implied_probability=primary_leg.implied_probability,
                    consensus_probability=primary_leg.consensus_probability,
                    expected_value=opportunity.expected_value,
                    liquidity=max(leg.liquidity for leg in legs),
                    arbitrage_flag=opportunity.opportunity_type == "cross_market_arbitrage",
                    confidence=confidence,
                    opportunity_type=opportunity.opportunity_type,
                    net_edge=opportunity.net_edge,
                    max_executable_size=opportunity.max_executable_size,
                    recommended_bankroll_fraction=recommendation.recommended_bankroll_fraction,
                    recommended_position_size=recommendation.recommended_position_size,
                    risk_level=recommendation.risk_level,
                    risk=opportunity.risk,
                    suggested_trade_strategy=opportunity.suggested_trade_strategy,
                    legs=legs,
                )
            )

        return response_items
