from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from functools import lru_cache

from src.config import settings
from src.models import Event, Market

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


@dataclass(slots=True)
class ParsedStructure:
    subject_phrase: str
    entity_tokens: set[str]
    entity_head: str | None
    thresholds: list[str]
    comparison_operator: str | None
    resolution_date: date | None
    category: str | None
    outcome_structure: str
    predicate_signature: str


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

        left_text = self._combined_text(market)
        right_text = self._combined_text(reference_market)
        left_structure = self._parse_structure(market)
        right_structure = self._parse_structure(reference_market)

        if left_structure.outcome_structure != right_structure.outcome_structure:
            return 0.05
        if (
            left_structure.subject_phrase
            and right_structure.subject_phrase
            and SequenceMatcher(None, left_structure.subject_phrase, right_structure.subject_phrase).ratio() < 0.55
        ):
            return 0.05

        normalized_text_score = SequenceMatcher(
            None,
            self._normalize_text(left_text),
            self._normalize_text(right_text),
        ).ratio()
        token_score = self._token_similarity(left_text, right_text)
        entity_score = self._set_similarity(left_structure.entity_tokens, right_structure.entity_tokens)
        predicate_score = SequenceMatcher(
            None,
            left_structure.predicate_signature,
            right_structure.predicate_signature,
        ).ratio()
        threshold_score = self._threshold_score(left_structure, right_structure)
        date_score = self._date_score(market, reference_market)
        category_score = self._category_score(left_structure.category, right_structure.category)
        comparison_score = self._comparison_score(
            left_structure.comparison_operator,
            right_structure.comparison_operator,
        )
        embedding_score = self._embedding_similarity(left_text, right_text)

        if threshold_score < 0.2 or date_score < 0.2:
            return 0.05
        if (
            left_structure.entity_head
            and right_structure.entity_head
            and left_structure.entity_head != right_structure.entity_head
        ):
            return 0.05
        if left_structure.entity_tokens and right_structure.entity_tokens and entity_score < 0.34:
            return 0.05
        if predicate_score < 0.78:
            return 0.05

        weights = {
            "text": 0.24,
            "token": 0.16,
            "entity": 0.2,
            "predicate": 0.12,
            "threshold": 0.14,
            "date": 0.12,
            "category": 0.08,
            "comparison": 0.04,
            "embedding": 0.04 if embedding_score is not None else 0.0,
        }
        total_weight = sum(weights.values())
        weighted_sum = (
            normalized_text_score * weights["text"]
            + token_score * weights["token"]
            + entity_score * weights["entity"]
            + predicate_score * weights["predicate"]
            + threshold_score * weights["threshold"]
            + date_score * weights["date"]
            + category_score * weights["category"]
            + comparison_score * weights["comparison"]
            + ((embedding_score or 0.0) * weights["embedding"])
        )
        return round(weighted_sum / total_weight, 4) if total_weight else 0.0

    def platform_independent_event_key(self, market: Market) -> str:
        parsed = self._parse_structure(market)
        title_tokens = [
            token
            for token in self._normalize_text(market.event_title).split()
            if token not in STOPWORDS and len(token) > 2
        ]
        token_segment = "-".join(title_tokens[:6]) if title_tokens else "event"
        threshold_segment = "-".join(parsed.thresholds[:2]) or "no-threshold"
        date_segment = parsed.resolution_date.isoformat() if parsed.resolution_date else "no-date"
        category_segment = (parsed.category or "uncategorized").lower()
        return f"{category_segment}-{token_segment}-{threshold_segment}-{date_segment}".strip("-")

    def _combined_text(self, market: Market) -> str:
        parts = [market.event_title, market.description or "", market.resolution_criteria or ""]
        return " ".join(part for part in parts if part).strip()

    def _parse_structure(self, market: Market) -> ParsedStructure:
        combined_text = self._combined_text(market)
        title_tokens = [
            token
            for token in self._normalize_text(market.event_title).split()
            if token not in STOPWORDS and len(token) > 2
        ]
        description_tokens = [
            token
            for token in self._normalize_text(market.description or "").split()
            if token not in STOPWORDS and len(token) > 2
        ]
        subject_phrase = self._extract_subject_phrase(market.event_title)
        subject_tokens = {
            token
            for token in self._normalize_text(subject_phrase).split()
            if token not in STOPWORDS and len(token) > 2
        }
        subject_token_list = [
            token
            for token in self._normalize_text(subject_phrase).split()
            if token not in STOPWORDS and len(token) > 2
        ]
        predicate_signature = self._predicate_signature(market.event_title, subject_phrase)
        outcome_labels = sorted({outcome.label.strip().upper() for outcome in market.outcomes})

        entity_tokens = set(subject_token_list)
        entity_tokens.update(description_tokens[:3])
        if not entity_tokens:
            entity_tokens = set(title_tokens[:4])

        return ParsedStructure(
            subject_phrase=subject_phrase,
            entity_tokens=entity_tokens,
            entity_head=subject_token_list[-1] if subject_token_list else (description_tokens[-1] if description_tokens else None),
            thresholds=self._extract_thresholds(combined_text),
            comparison_operator=self._extract_comparison_operator(combined_text),
            resolution_date=market.end_date.date() if market.end_date else None,
            category=market.category,
            outcome_structure="-".join(outcome_labels) if outcome_labels else "unknown",
            predicate_signature=predicate_signature,
        )

    def _token_similarity(self, left_text: str, right_text: str) -> float:
        return self._set_similarity(self._tokens(left_text), self._tokens(right_text))

    @staticmethod
    def _set_similarity(left_tokens: set[str], right_tokens: set[str]) -> float:
        if not left_tokens and not right_tokens:
            return 1.0
        if not left_tokens or not right_tokens:
            return 0.0
        intersection = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        return intersection / union if union else 0.0

    def _threshold_score(self, left: ParsedStructure, right: ParsedStructure) -> float:
        if not left.thresholds and not right.thresholds:
            return 1.0
        if not left.thresholds or not right.thresholds:
            return 0.05
        if left.comparison_operator == "between" and right.comparison_operator == "between":
            return 1.0 if left.thresholds == right.thresholds else 0.05
        if (
            left.comparison_operator
            and right.comparison_operator
            and left.comparison_operator != right.comparison_operator
        ):
            return 0.05

        if set(left.thresholds) & set(right.thresholds):
            return 1.0

        left_numbers = [self._threshold_number(value) for value in left.thresholds]
        right_numbers = [self._threshold_number(value) for value in right.thresholds]
        left_numbers = [value for value in left_numbers if value is not None]
        right_numbers = [value for value in right_numbers if value is not None]

        if not left_numbers or not right_numbers:
            return 0.15

        min_distance = min(abs(left_value - right_value) for left_value in left_numbers for right_value in right_numbers)
        scale = max(max(left_numbers), max(right_numbers), 1.0)
        relative_distance = min_distance / scale
        return max(0.0, 1.0 - min(relative_distance * 4.0, 1.0))

    @staticmethod
    def _comparison_score(left_operator: str | None, right_operator: str | None) -> float:
        if left_operator is None and right_operator is None:
            return 1.0
        if left_operator == right_operator:
            return 1.0
        if left_operator is None or right_operator is None:
            return 0.5
        return 0.1

    @staticmethod
    def _category_score(left_category: str | None, right_category: str | None) -> float:
        if not left_category and not right_category:
            return 0.75
        if left_category and right_category and left_category == right_category:
            return 1.0
        if not left_category or not right_category:
            return 0.6
        return 0.1

    def _date_score(self, left_market: Market, right_market: Market) -> float:
        if left_market.end_date is None and right_market.end_date is None:
            return 0.85
        if left_market.end_date is None or right_market.end_date is None:
            return 0.5

        delta_seconds = abs(self._to_timestamp(left_market.end_date) - self._to_timestamp(right_market.end_date))
        if delta_seconds <= 3600:
            return 1.0
        if delta_seconds <= 86400:
            return 0.9
        if delta_seconds <= 3 * 86400:
            return 0.65
        if delta_seconds <= 7 * 86400:
            return 0.35
        return 0.05

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
        return {
            token
            for token in normalized.split()
            if token and token not in STOPWORDS and len(token) > 2
        }

    @staticmethod
    def _extract_thresholds(text: str) -> list[str]:
        matches = re.findall(r"\$?\d+(?:,\d{3})*(?:\.\d+)?%?", text.lower())
        return [match.replace(",", "") for match in matches]

    @staticmethod
    def _extract_comparison_operator(text: str) -> str | None:
        lowered = text.lower()
        if "between" in lowered:
            return "between"
        if any(token in lowered for token in [">=", "at least", "minimum", "above or equal"]):
            return ">="
        if any(token in lowered for token in ["<=", "at most", "maximum", "below or equal"]):
            return "<="
        if any(token in lowered for token in [">", "above", "over", "exceed", "more than", "greater than"]):
            return ">"
        if any(token in lowered for token in ["<", "below", "under", "less than"]):
            return "<"
        return None

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
    def _extract_subject_phrase(title: str) -> str:
        normalized = EventMatcher._normalize_text(title)
        match = re.match(
            r"will\s+(?P<subject>.+?)\s+(win|be|have|visit|qualify|reach|exceed|close|sentenced|score|finish)\b",
            normalized,
        )
        if match:
            return match.group("subject").strip()
        return " ".join(normalized.split()[:4])

    @staticmethod
    def _predicate_signature(title: str, subject_phrase: str) -> str:
        normalized = EventMatcher._normalize_text(title)
        if subject_phrase:
            normalized = normalized.replace(subject_phrase, "<subject>", 1)
        normalized = re.sub(r"\$?\d+(?:\.\d+)?%?", "<num>", normalized)
        return normalized

    @staticmethod
    def _to_timestamp(value: datetime) -> float:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).timestamp()
        return value.timestamp()
