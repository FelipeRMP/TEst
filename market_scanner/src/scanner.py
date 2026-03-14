from __future__ import annotations

import asyncio
from dataclasses import dataclass

from analysis.arbitrage_detector import OpportunityDetector
from analysis.consensus_model import ConsensusModel, ConsensusResult
from config import settings
from ingestion.kalshi_client import KalshiClient
from ingestion.polymarket_client import PolymarketClient
from matching.event_matcher import EventMatcher
from models import Event, Market, Opportunity


@dataclass(slots=True)
class ScanSnapshot:
    markets: list[Market]
    events: list[Event]
    consensus_map: dict[str, ConsensusResult]
    opportunities: list[Opportunity]


async def scan_markets(
    limit: int = settings.default_market_limit,
    min_liquidity: float = settings.min_liquidity,
    min_ev: float = settings.min_expected_value,
) -> ScanSnapshot:
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
        for market in markets
        if market.status == "open" and market.liquidity >= min_liquidity and market.outcomes
    ]

    matcher = EventMatcher()
    events = matcher.group_markets(filtered_markets)
    consensus_model = ConsensusModel()
    consensus_map = consensus_model.compute(events)

    detector = OpportunityDetector(min_ev=min_ev)
    opportunities = detector.find(events, consensus_map)

    return ScanSnapshot(
        markets=filtered_markets,
        events=events,
        consensus_map=consensus_map,
        opportunities=opportunities,
    )
