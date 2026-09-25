"""Presidio-based PII detection and semantic placeholder replacement."""

from __future__ import annotations

import logging
import re
from typing import Any

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry

from app.config.settings import Settings, get_settings
from app.services.pii.placeholders import PlaceholderRegistry
from app.services.pii.recognizers import build_australian_recognizers, filter_enabled

logger = logging.getLogger(__name__)

# Claim schema field → preferred entity type for structured values
FIELD_ENTITY_HINTS: dict[str, str] = {
    "customer_name": "PERSON",
    "customer": "PERSON",
    "name": "PERSON",
    "address": "LOCATION",
    "date_of_birth": "DOB",
    "dob": "DOB",
    "birth_date": "DOB",
    "phone": "PHONE_NUMBER",
    "phone_number": "PHONE_NUMBER",
    "mobile": "PHONE_NUMBER",
    "email": "EMAIL_ADDRESS",
    "email_address": "EMAIL_ADDRESS",
    "policy_number": "POLICY_NUMBER",
    "claim_id": "CLAIM_NUMBER",
    "claim_number": "CLAIM_NUMBER",
    "claim_amount": "CLAIM_AMOUNT",
    "account_number": "ACCOUNT_NUMBER",
    "bsb": "BSB",
    "medicare": "MEDICARE",
    "abn": "ABN",
    "driver_license": "DRIVER_LICENSE",
}

_DOB_CONTEXT = re.compile(
    r"\b(date\s*of\s*birth|birth\s*date|birthday|\bdob\b|born\s+on|born\s*:)\b",
    re.IGNORECASE,
)
_HAS_DIGIT = re.compile(r"\d")
# SpaCy/Presidio often tags bare calendar words / doc nouns as DATE_TIME
_WEAK_DATE_TOKENS = frozenset(
    {
        "schedule",
        "scheduled",
        "monthly",
        "annually",
        "annual",
        "weekly",
        "daily",
        "quarterly",
        "today",
        "tomorrow",
        "yesterday",
        "now",
        "date",
        "time",
        "period",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }
)


class PIIDetector:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.enabled = self.settings.enabled_entities()
        self._analyzer: AnalyzerEngine | None = None

    @property
    def analyzer(self) -> AnalyzerEngine:
        if self._analyzer is None:
            registry = RecognizerRegistry()
            registry.load_predefined_recognizers()
            for recognizer in filter_enabled(build_australian_recognizers(), self.enabled):
                registry.add_recognizer(recognizer)
            self._analyzer = AnalyzerEngine(registry=registry)
        return self._analyzer

    def detect(self, text: str) -> list[dict[str, Any]]:
        if not text or not text.strip():
            return []
        # Only request entities Presidio can resolve (avoids unsupported-entity warnings)
        supported = {
            r.entity_type if hasattr(r, "entity_type") else None
            for r in self.analyzer.registry.recognizers
        }
        # PatternRecognizer uses supported_entities
        for r in self.analyzer.registry.recognizers:
            ents = getattr(r, "supported_entities", None) or []
            supported.update(ents)
        supported.discard(None)
        entities = sorted(self.enabled & supported) if self.enabled else None
        results = self.analyzer.analyze(text=text, language="en", entities=entities or None)
        # Sort descending by start so replacements from the end are safe
        results = sorted(results, key=lambda r: (r.start, -r.end), reverse=True)
        # Deduplicate overlapping spans — keep highest score
        kept: list[Any] = []
        occupied: list[tuple[int, int]] = []
        for r in sorted(results, key=lambda x: (-x.score, x.start, -(x.end - x.start))):
            if any(not (r.end <= s or r.start >= e) for s, e in occupied):
                continue
            occupied.append((r.start, r.end))
            kept.append(r)
        kept.sort(key=lambda r: r.start, reverse=True)
        out: list[dict[str, Any]] = []
        for r in kept:
            span = text[r.start : r.end]
            entity_type = r.entity_type
            if entity_type == "DATE_TIME":
                if not self._plausible_date_span(span):
                    continue
                entity_type = self._date_entity_type(text, r.start, r.end)
            out.append(
                {
                    "entity_type": entity_type,
                    "start": r.start,
                    "end": r.end,
                    "score": r.score,
                    "text": span,
                }
            )
        return out

    @staticmethod
    def _plausible_date_span(span: str) -> bool:
        """Drop weak DATE_TIME hits (e.g. bare 'Schedule' / 'September')."""
        cleaned = span.strip()
        if not cleaned:
            return False
        if _HAS_DIGIT.search(cleaned):
            return True
        tokens = re.findall(r"[A-Za-z]+", cleaned.lower())
        if not tokens:
            return False
        # Single weak token with no digits is almost always a false positive
        if len(tokens) == 1 and tokens[0] in _WEAK_DATE_TOKENS:
            return False
        if all(t in _WEAK_DATE_TOKENS for t in tokens):
            return False
        return True

    @staticmethod
    def _date_entity_type(text: str, start: int, end: int) -> str:
        """Use DOB only when the date is immediately tied to a birth-date label."""
        # Only look *before* the span so an earlier DOB line doesn't taint later dates
        prefix = text[max(0, start - 36) : start]
        if _DOB_CONTEXT.search(prefix):
            return "DOB"
        return "DATE_TIME"

    def sanitize_text(
        self,
        text: str,
        registry: PlaceholderRegistry,
    ) -> tuple[str, int]:
        detections = self.detect(text)
        sanitised = text
        count = 0
        for det in detections:
            sanitised, _ = registry.replace_span(
                sanitised,
                det["start"],
                det["end"],
                det["entity_type"],
            )
            count += 1
        return sanitised, count

    def sanitize_claim_record(
        self,
        claim: dict[str, Any],
        registry: PlaceholderRegistry,
        schema_pii_fields: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Sanitize structured claim. Prefer field hints; also run free-text detection."""
        hints = {**FIELD_ENTITY_HINTS, **(schema_pii_fields or {})}
        entities = 0
        out: dict[str, Any] = {}

        for key, value in claim.items():
            if isinstance(value, str):
                hint = hints.get(key.lower())
                entity_allowed = bool(hint) and (
                    not self.enabled
                    or hint in self.enabled
                    or (hint == "DOB" and "DATE_TIME" in self.enabled)
                )
                if entity_allowed and value.strip():
                    # Structured known-PII field: replace whole value
                    placeholder = registry.placeholder_for(hint, value)
                    out[key] = placeholder
                    entities += 1
                    continue
                sanitised, count = self.sanitize_text(value, registry)
                out[key] = sanitised
                entities += count
            elif isinstance(value, dict):
                nested, count = self.sanitize_claim_record(value, registry, schema_pii_fields)
                out[key] = nested
                entities += count
            elif isinstance(value, list):
                items = []
                for item in value:
                    if isinstance(item, str):
                        sanitised, count = self.sanitize_text(item, registry)
                        items.append(sanitised)
                        entities += count
                    elif isinstance(item, dict):
                        nested, count = self.sanitize_claim_record(item, registry, schema_pii_fields)
                        items.append(nested)
                        entities += count
                    else:
                        items.append(item)
                out[key] = items
            else:
                # Non-string scalars (amounts etc.) — leave unless field marked PII
                hint = hints.get(key.lower())
                entity_allowed = bool(hint) and (
                    not self.enabled
                    or hint in self.enabled
                    or (hint == "DOB" and "DATE_TIME" in self.enabled)
                )
                if entity_allowed and isinstance(value, (int, float)):
                    placeholder = registry.placeholder_for(hint, str(value))
                    out[key] = placeholder
                    entities += 1
                else:
                    out[key] = value
        return out, entities
