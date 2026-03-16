from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

from src.analysis.bankroll_allocator import BankrollAllocator
from src.models import Market, Opportunity
from src.scanner import ScanSnapshot, scan_markets

from ..schemas import OpportunityLegResponse, OpportunityResponse, ScanRequest
from ...utils.signal_logger import log_signal
from ...utils.scan_batches import record_scan_batch_finished, record_scan_batch_started


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
        started_at = datetime.now(timezone.utc)
        scan_id = started_at.strftime("scan-%Y%m%dT%H%M%S-%f")
        await record_scan_batch_started(
            scan_id=scan_id,
            started_at=started_at,
            limit=params.limit,
            min_liquidity=params.min_liquidity,
            min_ev=params.min_ev,
            bankroll_amount=params.bankroll_amount,
        )
        try:
            snapshot = await scan_markets(
                limit=params.limit,
                min_liquidity=params.min_liquidity,
                min_ev=params.min_ev,
                scan_id=scan_id,
                scan_started_at=started_at,
            )
            cached = CachedScan(
                params=params,
                scanned_at=snapshot.scan_finished_at,
                opportunities=self._build_responses(snapshot, params.bankroll_amount),
            )
            emitted_signal_count = await self._log_signals(
                cached.opportunities,
                scan_id=scan_id,
                scan_timestamp=snapshot.scan_started_at,
            )
            await record_scan_batch_finished(
                scan_id=scan_id,
                finished_at=snapshot.scan_finished_at,
                status="completed",
                market_count=len(snapshot.markets),
                price_snapshot_count=snapshot.price_snapshot_count,
                detected_opportunity_count=len(cached.opportunities),
                emitted_signal_count=emitted_signal_count,
            )
            self._cache = cached
            return cached
        except Exception as exc:
            await record_scan_batch_finished(
                scan_id=scan_id,
                finished_at=datetime.now(timezone.utc),
                status="failed",
                error_message=str(exc),
            )
            raise

    def get_cached(self) -> CachedScan | None:
        return self._cache

    async def _log_signals(
        self,
        opportunities: list[OpportunityResponse],
        *,
        scan_id: str,
        scan_timestamp: datetime,
    ) -> int:
        if not opportunities:
            return 0
        results = await asyncio.gather(
            *(log_signal(opportunity, scan_id=scan_id, scan_timestamp=scan_timestamp) for opportunity in opportunities),
            return_exceptions=True,
        )
        return sum(1 for result in results if result is True)

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
                    self._leg_response(
                        platform=platform,
                        market=market,
                        market_id=market_id,
                        outcome_label=outcome_label,
                        price=opportunity.prices.get(key, implied_probability),
                        implied_probability=implied_probability,
                        consensus_probability=consensus_probability,
                    )
                )

            if not legs and event is not None:
                for market in event.markets:
                    for outcome in market.outcomes:
                        if outcome.implied_probability is None:
                            continue
                        legs.append(
                            self._leg_response(
                                platform=market.platform,
                                market=market,
                                market_id=market.market_id,
                                outcome_label=outcome.label,
                                price=outcome.price or outcome.implied_probability,
                                implied_probability=outcome.implied_probability,
                                consensus_probability=(
                                    snapshot.consensus_map.get(event.event_id).probabilities.get(
                                        outcome.label.strip().upper()
                                    )
                                    if snapshot.consensus_map.get(event.event_id)
                                    else None
                                ),
                            )
                        )

            if not legs:
                continue

            primary_leg = max(legs, key=lambda leg: (leg.consensus_probability or 0, leg.liquidity))
            event_label = self._display_event_title(opportunity.event_title, primary_leg.market_title)
            movement_metrics = snapshot.movement_map.get(
                (primary_leg.platform, primary_leg.market_id, primary_leg.outcome.strip().upper())
            )
            event_consistent = self._event_consistency(event_label, legs)
            base_confidence = (
                (
                    float(opportunity.risk.get("match_confidence", 0.0))
                    + float(opportunity.risk.get("model_confidence", 0.0))
                )
                / 2.0
            )
            if not event_consistent:
                base_confidence *= 0.35
            spread_penalty = self._spread_penalty(primary_leg.spread_percent)
            if spread_penalty > 0:
                base_confidence *= (1.0 - spread_penalty)
            stale_penalty = 0.35 if movement_metrics and movement_metrics.movement_signal == "stale_market" else 0.0
            volatility_penalty = min(
                0.8,
                ((movement_metrics.volatility_5m if movement_metrics else 0.0) * 6.0)
                + ((movement_metrics.volatility_30m if movement_metrics else 0.0) * 4.0)
                + stale_penalty,
            )
            confidence = round(max(0.0, min(1.0, base_confidence * (1.0 - volatility_penalty))), 4)
            recommendation = self._bankroll_allocator.recommend(
                expected_value=opportunity.expected_value,
                consensus_probability=primary_leg.consensus_probability or 0.0,
                confidence=confidence,
                liquidity=max(leg.liquidity for leg in legs),
                bankroll_amount=bankroll_amount,
                implied_probability=primary_leg.best_ask or primary_leg.implied_probability,
                volatility_30m=movement_metrics.volatility_30m if movement_metrics else 0.0,
                movement_confidence=movement_metrics.movement_confidence if movement_metrics else 0.0,
                movement_signal=movement_metrics.movement_signal if movement_metrics else "stable",
            )
            adjusted_fraction = recommendation.recommended_bankroll_fraction
            adjusted_position_size = recommendation.recommended_position_size
            if (primary_leg.spread_percent or 0.0) > 0.25:
                adjusted_fraction = round(adjusted_fraction * 0.7, 4)
                adjusted_position_size = round(adjusted_position_size * 0.7, 2)
            available_size = self._available_orderbook_size(legs)
            thin_orderbook = available_size is not None and available_size < adjusted_position_size
            if thin_orderbook:
                adjusted_position_size = round(max(available_size, 0.0), 2)
                if bankroll_amount > 0:
                    adjusted_fraction = round(min(adjusted_fraction, adjusted_position_size / bankroll_amount), 4)
            risk_payload = {
                **opportunity.risk,
                "volatility_penalty": recommendation.volatility_penalty,
                "movement_confidence_weight": recommendation.movement_confidence_weight,
                "grouped_event_consistent": "true" if event_consistent else "false",
                "suspicious_price": "true"
                if not (0.0 <= primary_leg.implied_probability <= 1.0 and 0.0 <= primary_leg.price <= 1.0)
                else "false",
                "wide_spread": "true" if (primary_leg.spread_percent or 0.0) > 0.25 else "false",
                "thin_orderbook": "true" if thin_orderbook else "false",
            }

            response_items.append(
                OpportunityResponse(
                    opportunity_id=f"{opportunity.event_id}-{index}",
                    event_id=opportunity.event_id,
                    event=event_label,
                    market=", ".join(
                        f"{leg.platform}:{leg.market_id}:{leg.outcome}" for leg in legs
                    ),
                    platform=primary_leg.platform,
                    platforms=sorted({leg.platform for leg in legs}),
                    implied_probability=primary_leg.implied_probability,
                    best_bid=primary_leg.best_bid,
                    best_ask=primary_leg.best_ask,
                    spread=primary_leg.spread,
                    spread_percent=primary_leg.spread_percent,
                    consensus_probability=primary_leg.consensus_probability,
                    expected_value=opportunity.expected_value,
                    liquidity=max(leg.liquidity for leg in legs),
                    arbitrage_flag=opportunity.opportunity_type == "cross_market_arbitrage",
                    confidence=confidence,
                    related_signal_count=1,
                    opportunity_type=opportunity.opportunity_type,
                    net_edge=opportunity.net_edge,
                    max_executable_size=opportunity.max_executable_size,
                    recommended_bankroll_fraction=adjusted_fraction,
                    recommended_position_size=adjusted_position_size,
                    risk_level=recommendation.risk_level,
                    price_change_5m=movement_metrics.price_change_5m if movement_metrics else 0.0,
                    price_change_30m=movement_metrics.price_change_30m if movement_metrics else 0.0,
                    price_change_2h=movement_metrics.price_change_2h if movement_metrics else 0.0,
                    price_change_24h=movement_metrics.price_change_24h if movement_metrics else 0.0,
                    movement_signal=movement_metrics.movement_signal if movement_metrics else "stable",
                    movement_confidence=movement_metrics.movement_confidence if movement_metrics else 0.0,
                    volatility_5m=movement_metrics.volatility_5m if movement_metrics else 0.0,
                    volatility_30m=movement_metrics.volatility_30m if movement_metrics else 0.0,
                    volatility_2h=movement_metrics.volatility_2h if movement_metrics else 0.0,
                    consensus_variance=consensus.consensus_variance if consensus else 0.0,
                    risk=risk_payload,
                    suggested_trade_strategy=opportunity.suggested_trade_strategy,
                    legs=legs,
                )
            )

        clustered = self._cluster_opportunity_families(response_items)
        return sorted(clustered, key=self._ranking_score, reverse=True)

    @staticmethod
    def _ranking_score(opportunity: OpportunityResponse) -> float:
        movement_bonus = 0.0
        if opportunity.movement_signal == "lagging_market":
            movement_bonus = 0.1
        elif opportunity.movement_signal == "stale_market":
            movement_bonus = -0.25
        effective_ev = min(opportunity.expected_value, 3.0)

        return (
            (1.3 * effective_ev)
            + (0.05 * math.log1p(max(opportunity.liquidity, 0.0)))
            + (0.25 * opportunity.confidence)
            + (0.2 * opportunity.movement_confidence)
            + movement_bonus
            - (2.2 * opportunity.volatility_30m)
            - (0.35 if opportunity.risk.get("grouped_event_consistent") == "false" else 0.0)
            - (0.25 if opportunity.risk.get("suspicious_ev") == "true" else 0.0)
        )

    @staticmethod
    def _display_event_title(event_title: str, leg_title: str) -> str:
        similarity = SequenceMatcher(None, event_title.lower(), leg_title.lower()).ratio()
        return leg_title if similarity < 0.6 else event_title

    @staticmethod
    def _event_consistency(event_title: str, legs: list[OpportunityLegResponse]) -> bool:
        if not legs:
            return False
        return all(
            SequenceMatcher(None, event_title.lower(), leg.market_title.lower()).ratio() >= 0.55 for leg in legs
        )

    @staticmethod
    def _spread_metrics(best_bid: float | None, best_ask: float | None) -> tuple[float | None, float | None]:
        if best_bid is None or best_ask is None:
            return None, None
        spread = max(0.0, best_ask - best_bid)
        mid_price = (best_bid + best_ask) / 2.0
        if mid_price <= 0:
            return round(spread, 6), None
        return round(spread, 6), round(spread / mid_price, 6)

    @classmethod
    def _leg_response(
        cls,
        *,
        platform: str,
        market: Market,
        market_id: str,
        outcome_label: str,
        price: float,
        implied_probability: float,
        consensus_probability: float | None,
    ) -> OpportunityLegResponse:
        outcome = next(
            (
                item
                for item in market.outcomes
                if item.label.strip().upper() == outcome_label.strip().upper()
            ),
            None,
        )
        best_bid = outcome.best_bid if outcome is not None else None
        best_ask = outcome.best_ask if outcome is not None else None
        spread, spread_percent = cls._spread_metrics(best_bid, best_ask)
        return OpportunityLegResponse(
            platform=platform,
            market_id=market_id,
            market_title=market.event_title,
            outcome=outcome_label,
            price=price,
            implied_probability=implied_probability,
            best_bid=best_bid,
            best_ask=best_ask,
            bid_size=outcome.bid_size if outcome is not None else None,
            ask_size=outcome.ask_size if outcome is not None else None,
            spread=spread,
            spread_percent=spread_percent,
            consensus_probability=consensus_probability,
            liquidity=market.liquidity,
            volume_24h=market.volume_24h,
            spread_bps=market.spread_bps,
            description=market.description,
            resolution_criteria=market.resolution_criteria,
        )

    @staticmethod
    def _spread_penalty(spread_percent: float | None) -> float:
        if spread_percent is None:
            return 0.0
        if spread_percent > 0.10:
            return 0.3
        return 0.0

    @staticmethod
    def _available_orderbook_size(legs: list[OpportunityLegResponse]) -> float | None:
        sizes = [leg.ask_size for leg in legs if leg.ask_size is not None]
        if not sizes:
            return None
        return min(sizes)

    @classmethod
    def _cluster_opportunity_families(
        cls,
        opportunities: list[OpportunityResponse],
    ) -> list[OpportunityResponse]:
        grouped: dict[tuple[str, str], list[OpportunityResponse]] = defaultdict(list)
        for opportunity in opportunities:
            grouped[(opportunity.event_id, opportunity.platform)].append(opportunity)

        clustered: list[OpportunityResponse] = []
        for items in grouped.values():
            best = max(items, key=cls._ranking_score)
            clustered.append(best.model_copy(update={"related_signal_count": len(items)}))

        return clustered
