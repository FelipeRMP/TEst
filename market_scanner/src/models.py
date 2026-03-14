from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Outcome(BaseModel):
    label: str = Field(min_length=1)
    price: float | None = Field(default=None, ge=0)
    implied_probability: float | None = Field(default=None, ge=0, le=1)
    best_bid: float | None = Field(default=None, ge=0, le=1)
    best_ask: float | None = Field(default=None, ge=0, le=1)
    bid_size: float | None = Field(default=None, ge=0)
    ask_size: float | None = Field(default=None, ge=0)
    bid: float | None = Field(default=None, ge=0)
    ask: float | None = Field(default=None, ge=0)
    spread_bps: float | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Market(BaseModel):
    platform: str = Field(min_length=1)
    market_id: str = Field(min_length=1)
    event_key: str | None = None
    event_title: str = Field(min_length=1)
    description: str | None = None
    category: str | None = None
    resolution_criteria: str | None = None
    status: str = Field(default="open")
    liquidity: float = Field(default=0.0, ge=0)
    volume_24h: float = Field(default=0.0, ge=0)
    spread_bps: float | None = Field(default=None, ge=0)
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)
    end_date: datetime | None = None
    outcomes: list[Outcome] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    event_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: str | None = None
    end_date: datetime | None = None
    match_confidence: float = Field(default=1.0, ge=0, le=1)
    markets: list[Market] = Field(default_factory=list)


class Opportunity(BaseModel):
    event_id: str = Field(min_length=1)
    event_title: str = Field(min_length=1)
    opportunity_type: str = Field(min_length=1)
    platforms: list[str] = Field(default_factory=list)
    prices: dict[str, float] = Field(default_factory=dict)
    implied_probabilities: dict[str, float] = Field(default_factory=dict)
    expected_value: float = 0.0
    net_edge: float = 0.0
    max_executable_size: float | None = Field(default=None, ge=0)
    risk: dict[str, Any] = Field(default_factory=dict)
    suggested_trade_strategy: str = Field(min_length=1)
