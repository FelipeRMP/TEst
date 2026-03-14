from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx

from src.config import settings
from src.models import Market, Outcome


class KalshiClient:
    def __init__(
        self,
        base_url: str = settings.kalshi_base_url,
        timeout_seconds: float = settings.request_timeout_seconds,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_seconds,
            headers={"Accept": "application/json"},
        )

    async def __aenter__(self) -> "KalshiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_active_markets(self, limit: int = settings.default_market_limit) -> list[Market]:
        events_payload = await self._get_json(
            "/events",
            params={
                "status": "open",
                "limit": str(limit),
            },
        )
        event_items = events_payload.get("events", []) if isinstance(events_payload, dict) else []

        market_payloads = await asyncio.gather(
            *[
                self._get_json(
                    settings.kalshi_markets_path,
                    params={"event_ticker": str(event_item.get("event_ticker", ""))},
                )
                for event_item in event_items
                if isinstance(event_item, dict) and event_item.get("event_ticker")
            ],
            return_exceptions=True,
        )

        parsed_markets: list[Market] = []
        for payload in market_payloads:
            if isinstance(payload, Exception) or not isinstance(payload, dict):
                continue
            for item in payload.get("markets", []):
                if not isinstance(item, dict):
                    continue
                market = self._parse_market(item)
                if market is not None:
                    parsed_markets.append(market)
                if len(parsed_markets) >= limit:
                    return parsed_markets[:limit]

        return parsed_markets

    async def _get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def _parse_market(self, payload: dict[str, Any]) -> Market | None:
        market_type = str(payload.get("market_type", "")).lower()
        if market_type and market_type != "binary":
            return None
        if payload.get("mve_selected_legs") and len(payload.get("mve_selected_legs", [])) > 1:
            return None

        base_title = str(payload.get("title") or payload.get("subtitle") or payload.get("ticker") or "Kalshi Market")
        market_id = str(payload.get("ticker") or payload.get("id") or base_title)
        yes_sub_title = str(payload.get("yes_sub_title") or "").strip()
        no_sub_title = str(payload.get("no_sub_title") or "").strip()
        title = self._normalized_contract_title(base_title, yes_sub_title, no_sub_title)

        yes_bid = self._to_float_or_none(payload.get("yes_bid_dollars") or payload.get("yes_bid"))
        yes_ask = self._to_float_or_none(payload.get("yes_ask_dollars") or payload.get("yes_ask"))
        no_bid = self._to_float_or_none(payload.get("no_bid_dollars") or payload.get("no_bid"))
        no_ask = self._to_float_or_none(payload.get("no_ask_dollars") or payload.get("no_ask"))
        yes_bid_size = self._to_float_or_none(
            payload.get("yes_bid_quantity")
            or payload.get("yes_bid_size")
            or payload.get("yes_bid_shares")
        )
        yes_ask_size = self._to_float_or_none(
            payload.get("yes_ask_quantity")
            or payload.get("yes_ask_size")
            or payload.get("yes_ask_shares")
        )
        no_bid_size = self._to_float_or_none(
            payload.get("no_bid_quantity")
            or payload.get("no_bid_size")
            or payload.get("no_bid_shares")
        )
        no_ask_size = self._to_float_or_none(
            payload.get("no_ask_quantity")
            or payload.get("no_ask_size")
            or payload.get("no_ask_shares")
        )
        last_price = self._to_float_or_none(
            payload.get("last_price_dollars")
            or payload.get("last_price")
            or payload.get("yes_price_dollars")
        )

        yes_price = self._best_price(last_price, yes_bid, yes_ask)
        no_price = self._best_price(None, no_bid, no_ask)
        if no_price is None and yes_price is not None:
            no_price = max(0.0, min(1.0, 1.0 - yes_price))

        yes_spread = self._spread_bps(yes_bid, yes_ask)
        no_spread = self._spread_bps(no_bid, no_ask)
        market_spread = min(
            value for value in [yes_spread, no_spread] if value is not None
        ) if any(value is not None for value in [yes_spread, no_spread]) else None

        rules_parts = [str(payload.get("rules_primary") or "").strip(), str(payload.get("rules_secondary") or "").strip()]
        resolution_criteria = " ".join(part for part in rules_parts if part) or None

        return Market(
            platform="kalshi",
            market_id=market_id,
            event_key=str(payload.get("event_ticker") or payload.get("ticker") or market_id),
            event_title=title,
            description=str(payload.get("subtitle") or yes_sub_title or "") or None,
            category=self._category_from_ticker(str(payload.get("ticker") or "")),
            resolution_criteria=resolution_criteria,
            status="open" if str(payload.get("status", "")).lower() in {"active", "open"} else "inactive",
            liquidity=self._to_float(payload.get("liquidity_dollars") or payload.get("liquidity")),
            volume_24h=self._to_float(payload.get("volume_24h_fp") or payload.get("volume_24h") or payload.get("volume_fp")),
            spread_bps=market_spread,
            last_updated_at=self._parse_datetime(payload.get("updated_time") or payload.get("close_time")),
            end_date=self._parse_datetime_or_none(payload.get("expiration_time") or payload.get("close_time")),
            outcomes=[
                Outcome(
                    label="YES",
                    price=yes_price,
                    implied_probability=yes_price,
                    best_bid=yes_bid if yes_bid is not None else yes_price,
                    best_ask=yes_ask if yes_ask is not None else yes_price,
                    bid_size=yes_bid_size,
                    ask_size=yes_ask_size,
                    bid=yes_bid,
                    ask=yes_ask,
                    spread_bps=yes_spread,
                ),
                Outcome(
                    label="NO",
                    price=no_price,
                    implied_probability=no_price,
                    best_bid=no_bid if no_bid is not None else no_price,
                    best_ask=no_ask if no_ask is not None else no_price,
                    bid_size=no_bid_size,
                    ask_size=no_ask_size,
                    bid=no_bid,
                    ask=no_ask,
                    spread_bps=no_spread,
                ),
            ],
            metadata=payload,
        )

    @staticmethod
    def _normalized_contract_title(base_title: str, yes_sub_title: str, no_sub_title: str) -> str:
        if yes_sub_title and yes_sub_title.lower() not in base_title.lower():
            if base_title.lower().startswith("who will "):
                return f"{base_title} ({yes_sub_title})"
            return f"{base_title} - {yes_sub_title}"
        if no_sub_title and no_sub_title.lower() not in base_title.lower() and not yes_sub_title:
            return f"{base_title} - {no_sub_title}"
        return base_title

    @staticmethod
    def _best_price(last_price: float | None, bid: float | None, ask: float | None) -> float | None:
        if last_price is not None and 0 <= last_price <= 1:
            return last_price
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            return (bid + ask) / 2.0
        if ask is not None and 0 <= ask <= 1:
            return ask
        if bid is not None and 0 <= bid <= 1:
            return bid
        return None

    @staticmethod
    def _spread_bps(bid: float | None, ask: float | None) -> float | None:
        if bid is None or ask is None or bid < 0 or ask < 0:
            return None
        return round(abs(ask - bid) * 10_000, 2)

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            if value is None or value == "":
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _to_float_or_none(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            normalized = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(normalized)
            except ValueError:
                pass
        return datetime.utcnow()

    @staticmethod
    def _parse_datetime_or_none(value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(normalized)
            except ValueError:
                return None
        return None

    @staticmethod
    def _category_from_ticker(ticker: str) -> str | None:
        ticker_upper = ticker.upper()
        if ticker_upper.startswith("KX"):
            return "sports"
        if ticker_upper.startswith("KXBT") or "BTC" in ticker_upper:
            return "crypto"
        if ticker_upper.startswith("KXPOL") or "ELECT" in ticker_upper:
            return "politics"
        return None
