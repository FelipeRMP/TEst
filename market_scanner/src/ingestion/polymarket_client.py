from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx

from config import settings
from models import Market, Outcome


class PolymarketClient:
    def __init__(
        self,
        base_url: str = settings.polymarket_base_url,
        timeout_seconds: float = settings.request_timeout_seconds,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_seconds,
            headers={"Accept": "application/json"},
        )

    async def __aenter__(self) -> "PolymarketClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_active_markets(self, limit: int = settings.default_market_limit) -> list[Market]:
        params = {
            "active": "true",
            "closed": "false",
            "limit": str(limit),
        }
        payload = await self._get_json(settings.polymarket_markets_path, params=params)
        market_items = self._extract_items(payload)
        return [self._parse_market(item) for item in market_items]

    async def fetch_prices(self, market_id: str) -> dict[str, float]:
        payload = await self._get_json(f"{settings.polymarket_markets_path}/{market_id}")
        market = self._parse_market(payload)
        return {
            outcome.label: outcome.price
            for outcome in market.outcomes
            if outcome.price is not None
        }

    async def fetch_liquidity(self, market_id: str) -> float:
        payload = await self._get_json(f"{settings.polymarket_markets_path}/{market_id}")
        market = self._parse_market(payload)
        return market.liquidity

    async def _get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            data = payload.get("data") or payload.get("markets") or payload.get("items")
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        return []

    def _parse_market(self, payload: dict[str, Any]) -> Market:
        title = (
            payload.get("question")
            or payload.get("title")
            or payload.get("eventTitle")
            or f"market-{payload.get('id', 'unknown')}"
        )
        market_id = str(payload.get("id") or payload.get("conditionId") or title)
        outcomes = self._parse_outcomes(payload)

        return Market(
            platform="polymarket",
            market_id=market_id,
            event_key=payload.get("slug") or payload.get("eventSlug") or self._slugify(title),
            event_title=title,
            description=payload.get("description"),
            category=payload.get("category"),
            resolution_criteria=payload.get("rules") or payload.get("resolutionSource"),
            status=self._status_from_payload(payload),
            liquidity=self._to_float(payload.get("liquidityNum") or payload.get("liquidity")),
            volume_24h=self._to_float(
                payload.get("volume24hr")
                or payload.get("volume24Hr")
                or payload.get("volumeNum")
                or payload.get("volume")
            ),
            spread_bps=self._to_float_or_none(payload.get("spreadBps")),
            last_updated_at=self._parse_datetime(
                payload.get("updatedAt")
                or payload.get("lastUpdated")
                or payload.get("lastTradeTime")
            ),
            end_date=self._parse_datetime_or_none(payload.get("endDateIso") or payload.get("endDate")),
            outcomes=outcomes,
            metadata=payload,
        )

    def _parse_outcomes(self, payload: dict[str, Any]) -> list[Outcome]:
        labels = self._coerce_list(payload.get("outcomes"))
        prices = self._coerce_list(payload.get("outcomePrices"))

        parsed_outcomes: list[Outcome] = []
        for index, label in enumerate(labels):
            price = self._to_float_or_none(prices[index]) if index < len(prices) else None
            implied_probability = None
            if price is not None and 0 <= price <= 1:
                implied_probability = price

            parsed_outcomes.append(
                Outcome(
                    label=str(label),
                    price=price,
                    implied_probability=implied_probability,
                )
            )

        return parsed_outcomes

    @staticmethod
    def _coerce_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            return [part.strip() for part in stripped.split(",")]
        return [value]

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
    def _status_from_payload(payload: dict[str, Any]) -> str:
        if payload.get("closed") or payload.get("archived"):
            return "closed"
        if payload.get("active", True):
            return "open"
        return "inactive"

    @staticmethod
    def _slugify(value: str) -> str:
        return "-".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())
