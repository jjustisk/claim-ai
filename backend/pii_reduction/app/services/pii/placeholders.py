"""Semantic, session-scoped placeholder management."""

from __future__ import annotations

import re
from typing import Any


# Map Presidio / custom entity types → semantic placeholder prefixes
ENTITY_PREFIX: dict[str, str] = {
    "PERSON": "CUSTOMER",
    "LOCATION": "ADDRESS",
    "AU_ADDRESS": "ADDRESS",
    "PHONE_NUMBER": "PHONE",
    "AU_PHONE": "PHONE",
    "EMAIL_ADDRESS": "EMAIL",
    # Presidio tags *all* dates as DATE_TIME — keep DOB only for real birth dates
    "DATE_TIME": "DATE",
    "DOB": "DOB",
    "CREDIT_CARD": "CARD",
    "IBAN_CODE": "IBAN",
    "IP_ADDRESS": "IP",
    "AU_POSTCODE": "POSTCODE",
    "DRIVER_LICENSE": "LICENSE",
    "MEDICARE": "MEDICARE",
    "ABN": "ABN",
    "ACN": "ACN",
    "BSB": "BSB",
    "ACCOUNT_NUMBER": "ACCOUNT",
    "POLICY_NUMBER": "POLICY",
    "CLAIM_NUMBER": "CLAIM",
    "CLAIM_AMOUNT": "AMOUNT",
    "NRP": "CUSTOMER",
    "URL": "URL",
}


PLACEHOLDER_RE = re.compile(r"\b([A-Z][A-Z0-9]*_\d+)\b")


class PlaceholderRegistry:
    """Session-scoped semantic placeholders with reversible mapping."""

    def __init__(self, existing: dict[str, str] | None = None) -> None:
        self.mapping: dict[str, str] = dict(existing or {})
        self._value_to_placeholder: dict[tuple[str, str], str] = {}
        self._counters: dict[str, int] = {}
        for placeholder, value in self.mapping.items():
            prefix = placeholder.rsplit("_", 1)[0]
            try:
                num = int(placeholder.rsplit("_", 1)[1])
            except (IndexError, ValueError):
                continue
            self._counters[prefix] = max(self._counters.get(prefix, 0), num)
            # Prefer PERSON-like prefix lookup by normalised value
            self._value_to_placeholder[(prefix, value.strip().lower())] = placeholder

    def _next(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}_{self._counters[prefix]}"

    def placeholder_for(self, entity_type: str, value: str) -> str:
        prefix = ENTITY_PREFIX.get(entity_type, entity_type.upper().replace(" ", "_"))
        key = (prefix, value.strip().lower())
        if key in self._value_to_placeholder:
            return self._value_to_placeholder[key]
        # Also reuse if same raw value already mapped under this prefix
        for ph, mapped in self.mapping.items():
            if ph.startswith(prefix + "_") and mapped.strip().lower() == value.strip().lower():
                self._value_to_placeholder[key] = ph
                return ph
        placeholder = self._next(prefix)
        self.mapping[placeholder] = value
        self._value_to_placeholder[key] = placeholder
        return placeholder

    def replace_span(self, text: str, start: int, end: int, entity_type: str) -> tuple[str, str]:
        original = text[start:end]
        placeholder = self.placeholder_for(entity_type, original)
        return text[:start] + placeholder + text[end:], placeholder


def extract_placeholders(text: str) -> list[str]:
    return PLACEHOLDER_RE.findall(text)


def rehydrate_text(
    text: str,
    mapping: dict[str, str],
    allowed_prefixes: set[str] | None = None,
) -> tuple[str, list[str]]:
    """Replace placeholders using session mapping. Returns (text, unknown)."""
    unknown: list[str] = []

    def repl(match: re.Match[str]) -> str:
        token = match.group(1)
        prefix = token.rsplit("_", 1)[0]
        if allowed_prefixes is not None and prefix not in allowed_prefixes:
            return token
        if token not in mapping:
            unknown.append(token)
            return token
        return mapping[token]

    return PLACEHOLDER_RE.sub(repl, text), unknown


def rehydrate_structure(
    data: Any,
    mapping: dict[str, str],
    allowed_prefixes: set[str] | None = None,
) -> tuple[Any, list[str]]:
    unknown: list[str] = []

    if isinstance(data, str):
        return rehydrate_text(data, mapping, allowed_prefixes)

    if isinstance(data, list):
        out = []
        for item in data:
            value, unk = rehydrate_structure(item, mapping, allowed_prefixes)
            out.append(value)
            unknown.extend(unk)
        return out, unknown

    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            new_val, unk = rehydrate_structure(value, mapping, allowed_prefixes)
            out[key] = new_val
            unknown.extend(unk)
        return out, unknown

    return data, unknown
