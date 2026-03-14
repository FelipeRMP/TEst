from __future__ import annotations

import re
from difflib import SequenceMatcher
from functools import lru_cache
from datetime import datetime, timezone

from config import settings
from models import Event, Market

STOPWORDS = {
    "a",
    "an",
    "and",
    "be",
    "by",
    "for",
    "if",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "will",
    "market",
    "resolve",
    "yes",
    "no",
}


class EventMatcher:
    def __init__(self, threshold: float = settings.match_threshold) -> None:
        self.threshold = threshold
        self.embedding_similarity_enabled = settings.embedding_similarity_enabled

    def group_markets(self, markets: list[Market]) -> list[Event]:
        events: list[Event] = []
        for market in markets:
            platform_independent_key = self.platform_independent_event_key(market)
            best_index = -1
            best_score = 0.0

            for index, event in enumerate(events):
                if event.event_id == platform_independent_key:
                    best_index = index
                    best_score = 1.0
                    break

                score = self.match_confidence(market, event)
                if score > best_score:
                    best_index = index
                    best_score = score

            if best_index >= 0 and best_score >= self.threshold:
                existing = events[best_index]
                existing.markets.append(market)
                existing.match_confidence = min(existing.match_confidence, best_score)
            else:
                events.append(
                    Event(
                        event_id=platform_independent_key,
                        title=market.event_title,
                        category=market.category,
                        end_date=market.end_date,
                        match_confidence=1.0,
                        markets=[market],
                    )
                )

        return events

    def match_confidence(self, market: Market, event: Event) -> float:
        reference_market = event.markets[0] if event.markets else None
        if reference_market is None:
            return 0.0

        text_left = self._combined_text(market)
        text_right = self._combined_text(reference_market)

        normalized_text_score = SequenceMatcher(
            None,
            self._normalize_text(text_left),
            self._normalize_text(text_right),
        ).ratio()

        token_score = self._token_similarity(text_left, text_right)
        threshold_score = self._threshold_score(text_left, text_right)
        date_score = self._date_score(market, reference_market)
        embedding_score = self._embedding_similarity(text_left, text_right)
        category_score = 1.0 if market.category and market.category == reference_market.category else 0.5

        weights = {
            "text": 0.32,
            "token": 0.24,
            "threshold": 0.16,
            "date": 0.14,
            "category": 0.08,
            "embedding": 0.06 if embedding_score is not None else 0.0,
        }

        total_weight = sum(weights.values())
        weighted_sum = (
            normalized_text_score * weights["text"]
            + token_score * weights["token"]
            + threshold_score * weights["threshold"]
            + date_score * weights["date"]
            + category_score * weights["category"]
            + ((embedding_score or 0.0) * weights["embedding"])
        )
        return round(weighted_sum / total_weight, 4) if total_weight else 0.0

    def platform_independent_event_key(self, market: Market) -> str:
        title_text = market.event_title
        text = self._combined_text(market)
        tokens = [token for token in self._normalize_text(title_text).split() if token not in STOPWORDS and len(token) > 2]
        token_segment = "-".join(tokens[:6]) if tokens else self._normalize_text(title_text).replace(" ", "-")
        threshold_segment = "-".join(self._extract_thresholds(title_text)[:2]) or "no-threshold"
        date_segment = market.end_date.date().isoformat() if market.end_date else "no-date"
        return f"{token_segment}-{threshold_segment}-{date_segment}".strip("-")

    def _combined_text(self, market: Market) -> str:
        parts = [market.event_title, market.description or "", market.resolution_criteria or ""]
        return " ".join(part for part in parts if part).strip()

    def _token_similarity(self, left_text: str, right_text: str) -> float:
        left_tokens = self._tokens(left_text)
        right_tokens = self._tokens(right_text)
        if not left_tokens and not right_tokens:
            return 1.0
        if not left_tokens or not right_tokens:
            return 0.0
        intersection = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        return intersection / union if union else 0.0

    def _threshold_score(self, left_text: str, right_text: str) -> float:
        left_thresholds = self._extract_thresholds(left_text)
        right_thresholds = self._extract_thresholds(right_text)
        if not left_thresholds and not right_thresholds:
            return 1.0
        if not left_thresholds or not right_thresholds:
            return 0.55

        if set(left_thresholds) & set(right_thresholds):
            return 1.0

        left_numbers = [self._threshold_number(value) for value in left_thresholds]
        right_numbers = [self._threshold_number(value) for value in right_thresholds]
        left_numbers = [value for value in left_numbers if value is not None]
        right_numbers = [value for value in right_numbers if value is not None]

        if not left_numbers or not right_numbers:
            return 0.3

        min_distance = min(abs(left - right) for left in left_numbers for right in right_numbers)
        scale = max(max(left_numbers), max(right_numbers), 1.0)
        relative_distance = min_distance / scale
        return max(0.0, 1.0 - min(relative_distance * 3.0, 1.0))

    def _date_score(self, left_market: Market, right_market: Market) -> float:
        if left_market.end_date is None and right_market.end_date is None:
            return 0.85
        if left_market.end_date is None or right_market.end_date is None:
            return 0.6

        delta_seconds = abs(self._to_timestamp(left_market.end_date) - self._to_timestamp(right_market.end_date))
        if delta_seconds <= 3600:
            return 1.0
        if delta_seconds <= 86400:
            return 0.9
        if delta_seconds <= 7 * 86400:
            return 0.7
        if delta_seconds <= 30 * 86400:
            return 0.35
        return 0.1

    def _embedding_similarity(self, left_text: str, right_text: str) -> float | None:
        if not self.embedding_similarity_enabled:
            return None
        model = self._embedding_model()
        if model is None:
            return None

        embeddings = model.encode([left_text, right_text], normalize_embeddings=True)
        if len(embeddings) != 2:
            return None

        left_vector, right_vector = embeddings
        score = float(sum(left * right for left, right in zip(left_vector, right_vector)))
        return max(0.0, min(score, 1.0))

    @staticmethod
    @lru_cache(maxsize=1)
    def _embedding_model():
        try:
            from sentence_transformers import SentenceTransformer

            return SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            return None

    @staticmethod
    def _tokens(text: str) -> set[str]:
        normalized = EventMatcher._normalize_text(text)
        tokens = {token for token in normalized.split() if token and token not in STOPWORDS and len(token) > 2}
        return tokens

    @staticmethod
    def _extract_thresholds(text: str) -> list[str]:
        matches = re.findall(r"\$?\d+(?:,\d{3})*(?:\.\d+)?%?", text.lower())
        return [match.replace(",", "") for match in matches]

    @staticmethod
    def _threshold_number(value: str) -> float | None:
        cleaned = value.replace("$", "").replace("%", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _normalize_text(value: str) -> str:
        lowered = value.lower().strip()
        collapsed = re.sub(r"[^a-z0-9\s$%.]", " ", lowered)
        return re.sub(r"\s+", " ", collapsed).strip()

    @staticmethod
    def _to_timestamp(value: datetime) -> float:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).timestamp()
        return value.timestamp()
