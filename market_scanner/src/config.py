from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    polymarket_base_url: str = Field(
        default="https://gamma-api.polymarket.com",
        description="Base URL for the Polymarket Gamma API.",
    )
    polymarket_markets_path: str = Field(
        default="/markets",
        description="Path for the active markets endpoint.",
    )
    kalshi_base_url: str = Field(
        default="https://api.elections.kalshi.com/trade-api/v2",
        description="Base URL for the Kalshi Trade API.",
    )
    kalshi_markets_path: str = Field(
        default="/markets",
        description="Path for the active Kalshi markets endpoint.",
    )
    request_timeout_seconds: float = Field(default=20.0, gt=0)
    default_market_limit: int = Field(default=100, ge=1, le=500)
    min_liquidity: float = Field(default=100.0, ge=0)
    min_expected_value: float = Field(default=0.02, ge=0)
    fee_bps: int = Field(default=50, ge=0, le=10_000)
    match_threshold: float = Field(default=0.72, ge=0, le=1)
    embedding_similarity_enabled: bool = Field(default=False)
    price_history_db_path: str = Field(
        default=str(Path(__file__).resolve().parents[1] / "market_history.sqlite3")
    )
    price_history_cache_size: int = Field(default=1024, ge=128)
    platform_reliability: dict[str, float] = Field(
        default_factory=lambda: {"polymarket": 1.0, "kalshi": 1.1}
    )
    default_kelly_safety_factor: float = Field(default=0.25, ge=0, le=1)


settings = Settings()
