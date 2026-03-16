from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from backend.utils.price_logger import log_market_price
from src.analysis.arbitrage_detector import OpportunityDetector
from src.analysis.consensus_model import ConsensusModel, ConsensusResult
from src.analysis.movement_detector import MovementDetector, MovementMetrics
from src.config import settings
from src.ingestion.kalshi_client import KalshiClient
from src.ingestion.polymarket_client import PolymarketClient
from src.matching.event_matcher import EventMatcher
from src.models import Event, Market, Opportunity
from src.storage.price_history_store import price_history_store


@dataclass(slots=True)
class ScanSnapshot:
    scan_id: str
    scan_started_at: datetime
    scan_finished_at: datetime
    scan_duration_seconds: float
    markets: list[Market]
    events: list[Event]
    consensus_map: dict[str, ConsensusResult]
    opportunities: list[Opportunity]
    movement_map: dict[tuple[str, str, str], MovementMetrics]
    price_snapshot_count: int


async def scan_markets(
    limit: int = settings.default_market_limit,
    min_liquidity: float = settings.min_liquidity,
    min_ev: float = settings.min_expected_value,
    scan_id: str | None = None,
    scan_started_at: datetime | None = None,
) -> ScanSnapshot:
    started_at = scan_started_at or datetime.now(timezone.utc)
    active_scan_id = scan_id or f"scan-{uuid4().hex}"
    async with PolymarketClient() as polymarket_client, KalshiClient() as kalshi_client:
        results = await asyncio.gather(
            polymarket_client.fetch_active_markets(limit=limit),
            kalshi_client.fetch_active_markets(limit=limit),
            return_exceptions=True,
        )

    markets: list[Market] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        markets.extend(result)

    filtered_markets = [
        market
        for market in (_sanitize_market(market) for market in markets)
        if market is not None and market.status == "open" and market.liquidity >= min_liquidity and market.outcomes
    ]
    await asyncio.gather(
        *(
            log_market_price(market, scan_id=active_scan_id, scan_timestamp=started_at)
            for market in filtered_markets
        ),
        return_exceptions=True,
    )
    price_snapshot_count = sum(len(market.outcomes) for market in filtered_markets)

    matcher = EventMatcher()
    events = matcher.group_markets(filtered_markets)
    consensus_model = ConsensusModel()
    consensus_map = consensus_model.compute(events)
    await price_history_store.record_event_prices(events, timestamp=started_at, scan_id=active_scan_id)
    movement_detector = MovementDetector()
    movement_map = await movement_detector.analyze(events)

    detector = OpportunityDetector(min_ev=min_ev)
    opportunities = detector.find(events, consensus_map)
    finished_at = datetime.now(timezone.utc)

    return ScanSnapshot(
        scan_id=active_scan_id,
        scan_started_at=started_at,
        scan_finished_at=finished_at,
        scan_duration_seconds=round((finished_at - started_at).total_seconds(), 4),
        markets=filtered_markets,
        events=events,
        consensus_map=consensus_map,
        opportunities=opportunities,
        movement_map=movement_map,
        price_snapshot_count=price_snapshot_count,
    )


def _sanitize_market(market: Market) -> Market | None:
    sanitized_outcomes = []
    for outcome in market.outcomes:
        probability = outcome.implied_probability
        if probability is None and outcome.price is not None and 0.0 <= outcome.price <= 1.0:
            probability = outcome.price
        if probability is None:
            continue
        if not 0.0 <= probability <= 1.0:
            continue

        price = outcome.price
        if price is None or not 0.0 <= price <= 1.0:
            price = probability
        best_bid = outcome.best_bid if outcome.best_bid is not None and 0.0 <= outcome.best_bid <= 1.0 else None
        best_ask = outcome.best_ask if outcome.best_ask is not None and 0.0 <= outcome.best_ask <= 1.0 else None
        if best_bid is None and outcome.bid is not None and 0.0 <= outcome.bid <= 1.0:
            best_bid = outcome.bid
        if best_ask is None and outcome.ask is not None and 0.0 <= outcome.ask <= 1.0:
            best_ask = outcome.ask
        if best_bid is None:
            best_bid = probability
        if best_ask is None:
            best_ask = probability

        sanitized_outcomes.append(
            outcome.model_copy(
                update={
                    "price": round(price, 6),
                    "implied_probability": round(probability, 6),
                    "best_bid": round(best_bid, 6),
                    "best_ask": round(best_ask, 6),
                    "bid": round(best_bid, 6),
                    "ask": round(best_ask, 6),
                }
            )
        )

    if not sanitized_outcomes:
        return None

    return market.model_copy(update={"outcomes": sanitized_outcomes})
