from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    min_liquidity: float = Field(default=100.0, ge=0)
    min_ev: float = Field(default=0.02, ge=0)
    bankroll_amount: float = Field(default=0.0, ge=0)


class OpportunityLegResponse(BaseModel):
    platform: str
    market_id: str
    market_title: str
    outcome: str
    price: float
    implied_probability: float
    consensus_probability: float | None = None
    liquidity: float
    volume_24h: float
    spread_bps: float | None = None
    description: str | None = None
    resolution_criteria: str | None = None


class OpportunityResponse(BaseModel):
    opportunity_id: str
    event_id: str
    event: str
    market: str
    platform: str
    platforms: list[str]
    implied_probability: float
    consensus_probability: float | None = None
    expected_value: float
    liquidity: float
    arbitrage_flag: bool
    confidence: float
    opportunity_type: str
    net_edge: float
    max_executable_size: float | None = None
    recommended_bankroll_fraction: float = 0.0
    recommended_position_size: float = 0.0
    risk_level: str = "high"
    risk: dict[str, float | str]
    suggested_trade_strategy: str
    legs: list[OpportunityLegResponse]


class ScanResponse(BaseModel):
    opportunities: list[OpportunityResponse]
    count: int
    scanned_at: datetime
    params: ScanRequest


class OpportunitiesResponse(BaseModel):
    opportunities: list[OpportunityResponse]
    count: int
    last_scan_at: datetime | None = None
