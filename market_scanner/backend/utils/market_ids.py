from __future__ import annotations


def normalize_market_id(platform: str, market_id: str, side: str | None = None) -> str:
    known_platforms = {"polymarket", "kalshi"}
    known_sides = {"YES", "NO", "BUY", "SELL"}
    normalized_platform = (platform or "").strip().lower()
    normalized_market_id = (market_id or "").strip()
    normalized_side = (side or "").strip().upper()

    if not normalized_market_id:
        return f"{normalized_platform}:{normalized_side}" if normalized_side else normalized_platform

    parts = [part.strip() for part in normalized_market_id.split(":") if part.strip()]
    if parts and parts[0].lower() in known_platforms:
        normalized_platform = parts.pop(0).lower()

    extracted_side = ""
    while parts and parts[-1].upper() in known_sides:
        extracted_side = parts.pop().upper()
    if extracted_side and not normalized_side:
        normalized_side = extracted_side

    core_market_id = ":".join(parts)
    if normalized_side:
        return f"{normalized_platform}:{core_market_id}:{normalized_side}"
    return f"{normalized_platform}:{core_market_id}"
