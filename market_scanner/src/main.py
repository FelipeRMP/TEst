from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_DEPS = PROJECT_ROOT / ".deps"
if LOCAL_DEPS.exists():
    sys.path.insert(0, str(LOCAL_DEPS))
if __package__ in {None, ""}:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx

from src.config import settings
from src.models import Opportunity
from src.scanner import scan_markets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan Polymarket for MVP market opportunities.")
    parser.add_argument("--limit", type=int, default=settings.default_market_limit, help="Number of active markets to fetch.")
    parser.add_argument("--min-liquidity", type=float, default=settings.min_liquidity, help="Minimum market liquidity.")
    parser.add_argument("--min-ev", type=float, default=settings.min_expected_value, help="Minimum expected value threshold.")
    parser.add_argument("--json", action="store_true", help="Print opportunities as JSON.")
    return parser


async def run(limit: int, min_liquidity: float, min_ev: float) -> list[Opportunity]:
    snapshot = await scan_markets(limit=limit, min_liquidity=min_liquidity, min_ev=min_ev)
    return snapshot.opportunities


def render_human_readable(opportunities: Sequence[Opportunity]) -> None:
    if not opportunities:
        print("No opportunities found.")
        return

    for opportunity in opportunities:
        print("=" * 80)
        print(f"Event: {opportunity.event_title}")
        print(f"Type: {opportunity.opportunity_type}")
        print(f"Platforms: {', '.join(opportunity.platforms)}")
        print(f"Expected Value: {opportunity.expected_value:.4f}")
        print(f"Net Edge: {opportunity.net_edge:.4f}")
        if opportunity.max_executable_size is not None:
            print(f"Max Executable Size: {opportunity.max_executable_size:.2f}")
        print(f"Risk: {json.dumps(opportunity.risk)}")
        print("Prices:")
        for key, value in opportunity.prices.items():
            print(f"  {key}: {value:.4f}")
        print(f"Strategy: {opportunity.suggested_trade_strategy}")


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        opportunities = await run(args.limit, args.min_liquidity, args.min_ev)
    except httpx.HTTPError as exc:
        print(f"Failed to fetch market data: {exc}")
        return

    if args.json:
        print(json.dumps([opportunity.model_dump(mode="json") for opportunity in opportunities], indent=2))
        return

    render_human_readable(opportunities)


if __name__ == "__main__":
    asyncio.run(main())
