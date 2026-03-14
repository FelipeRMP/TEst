from __future__ import annotations


def normalize_market_id(platform: str, market_id: str, side: str | None = None) -> str:
    known_sides = {"YES", "NO", "BUY", "SELL"}
    normalized_platform = (platform or "").strip().lower()
    normalized_market_id = (market_id or "").strip()
    normalized_side = (side or "").strip().upper()

    if normalized_market_id.endswith(":YES") or normalized_market_id.endswith(":NO"):
        if normalized_market_id.count(":") == 2 and normalized_market_id.split(":", maxsplit=1)[0].lower() in {
            "polymarket",
            "kalshi",
        }:
            return normalized_market_id

    if ":" in normalized_market_id:
        prefix, separator, remainder = normalized_market_id.partition(":")
        if separator and prefix.lower() in {"polymarket", "kalshi"}:
            normalized_platform = prefix.lower()
            normalized_market_id = remainder

        parts = normalized_market_id.split(":")
        extracted_side = ""
        while parts and parts[-1].upper() in known_sides:
            extracted_side = parts.pop().upper()
        if extracted_side:
            normalized_market_id = ":".join(parts)
            if not normalized_side:
                normalized_side = extracted_side

    if normalized_side:
        return f"{normalized_platform}:{normalized_market_id}:{normalized_side}"
    return f"{normalized_platform}:{normalized_market_id}"
