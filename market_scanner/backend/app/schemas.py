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
    best_bid: float | None = None
    best_ask: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    spread: float | None = None
    spread_percent: float | None = None
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
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    spread_percent: float | None = None
    consensus_probability: float | None = None
    expected_value: float
    liquidity: float
    arbitrage_flag: bool
    confidence: float
    related_signal_count: int = 1
    opportunity_type: str
    net_edge: float
    max_executable_size: float | None = None
    recommended_bankroll_fraction: float = 0.0
    recommended_position_size: float = 0.0
    risk_level: str = "high"
    price_change_5m: float = 0.0
    price_change_30m: float = 0.0
    price_change_2h: float = 0.0
    price_change_24h: float = 0.0
    movement_signal: str = "stable"
    movement_confidence: float = 0.0
    volatility_5m: float = 0.0
    volatility_30m: float = 0.0
    volatility_2h: float = 0.0
    consensus_variance: float = 0.0
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


class RecentScanActivityResponse(BaseModel):
    timestamp: datetime
    signal_count: int
    price_snapshot_count: int


class CollectionStatsResponse(BaseModel):
    total_signals_logged: int
    total_price_snapshots_logged: int
    latest_signal_timestamp: datetime | None = None
    latest_price_timestamp: datetime | None = None
    latest_scan_timestamp: datetime | None = None
    simulator_trade_count: int
    simulator_total_pnl: float
    simulated_realized_pnl: float
    simulator_win_rate: float | None = None
    average_expected_value: float
    average_ev: float
    recent_signal_count_24h: int
    recent_price_snapshot_count_24h: int
    expected_scan_interval_seconds: int
    data_freshness_status: str
    win_rate: float | None = None
    recent_scan_activity: list[RecentScanActivityResponse]
