"""Australian / insurance-specific Presidio recognisers."""

from __future__ import annotations

from typing import Optional

from presidio_analyzer import Pattern, PatternRecognizer


def build_australian_recognizers() -> list[PatternRecognizer]:
    """Custom recognisers for AU/insurance identifiers."""

    au_phone = PatternRecognizer(
        supported_entity="AU_PHONE",
        name="au_phone_recognizer",
        patterns=[
            Pattern(
                name="au_mobile",
                regex=r"\b(?:\+?61\s?4|04)\d{2}[\s-]?\d{3}[\s-]?\d{3}\b",
                score=0.7,
            ),
            Pattern(
                name="au_landline",
                regex=r"\b(?:\+?61\s?[2-8]|0[2-8])\d{1,4}[\s-]?\d{3,4}[\s-]?\d{3,4}\b",
                score=0.4,
            ),
        ],
        context=["phone", "mobile", "call", "contact"],
    )

    au_postcode = PatternRecognizer(
        supported_entity="AU_POSTCODE",
        name="au_postcode_recognizer",
        patterns=[
            Pattern(
                name="au_postcode",
                regex=r"\b(?:0[2-9]\d{2}|[1-9]\d{3})\b",
                score=0.3,
            )
        ],
        context=["postcode", "postal", "nsw", "vic", "qld", "wa", "sa", "tas", "act", "nt"],
    )

    driver_license = PatternRecognizer(
        supported_entity="DRIVER_LICENSE",
        name="au_driver_license_recognizer",
        patterns=[
            Pattern(
                name="au_dl_numeric",
                regex=r"\b[0-9]{6,10}\b",
                score=0.2,
            ),
            Pattern(
                name="au_dl_alnum",
                regex=r"\b[A-Z]{1,3}[0-9]{5,9}\b",
                score=0.3,
            ),
        ],
        context=["licence", "license", "driver", "driving"],
    )

    medicare = PatternRecognizer(
        supported_entity="MEDICARE",
        name="medicare_recognizer",
        patterns=[
            Pattern(
                name="medicare",
                regex=r"\b[2-6]\d{3}[\s-]?\d{5}[\s-]?\d\b",
                score=0.6,
            )
        ],
        context=["medicare", "health", "card"],
    )

    abn = PatternRecognizer(
        supported_entity="ABN",
        name="abn_recognizer",
        patterns=[
            Pattern(
                name="abn",
                regex=r"\b\d{2}[\s]?\d{3}[\s]?\d{3}[\s]?\d{3}\b",
                score=0.5,
            )
        ],
        context=["abn", "business", "gst"],
    )

    acn = PatternRecognizer(
        supported_entity="ACN",
        name="acn_recognizer",
        patterns=[
            Pattern(
                name="acn",
                regex=r"\b\d{3}[\s]?\d{3}[\s]?\d{3}\b",
                score=0.3,
            )
        ],
        context=["acn", "company", "asic"],
    )

    bsb = PatternRecognizer(
        supported_entity="BSB",
        name="bsb_recognizer",
        patterns=[
            Pattern(
                name="bsb",
                regex=r"\b\d{3}[-\s]?\d{3}\b",
                score=0.4,
            )
        ],
        context=["bsb", "bank", "account"],
    )

    account_number = PatternRecognizer(
        supported_entity="ACCOUNT_NUMBER",
        name="account_number_recognizer",
        patterns=[
            Pattern(
                name="account",
                regex=r"\b\d{6,10}\b",
                score=0.2,
            )
        ],
        context=["account", "bsb", "bank", "deposit"],
    )

    policy_number = PatternRecognizer(
        supported_entity="POLICY_NUMBER",
        name="policy_number_recognizer",
        patterns=[
            Pattern(
                name="policy",
                regex=r"\b(?:POL|POLICY)[-_]?\d{4,12}\b",
                score=0.7,
            )
        ],
        context=["policy", "insurance", "cover"],
    )

    claim_number = PatternRecognizer(
        supported_entity="CLAIM_NUMBER",
        name="claim_number_recognizer",
        patterns=[
            Pattern(
                name="claim",
                regex=r"\b(?:CLM|CLAIM)[-_]?\d{4,12}\b",
                score=0.7,
            )
        ],
        context=["claim", "reference", "lodgement"],
    )

    au_address = PatternRecognizer(
        supported_entity="AU_ADDRESS",
        name="au_address_recognizer",
        patterns=[
            Pattern(
                name="au_street_address",
                regex=(
                    r"\b\d{1,5}[A-Za-z]?\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+"
                    r"(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr|Court|Ct|"
                    r"Place|Pl|Parade|Pde|Crescent|Cres|Boulevard|Blvd|Highway|Hwy|"
                    r"Terrace|Tce|Way|Close|Cl)\b"
                    r"(?:,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"  # suburb after comma
                    r"?(?:,?\s+(?:NSW|VIC|QLD|WA|SA|TAS|ACT|NT))?"
                    r"(?:,?\s+\d{4})?"
                ),
                score=0.8,
            ),
            Pattern(
                name="au_unit_address",
                regex=(
                    r"\b(?:Unit|Apt|Apartment|Suite)\s+\d+[A-Za-z]?/?\d*[A-Za-z]?"
                    r",?\s+\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s+"
                    r"(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr)\b"
                ),
                score=0.75,
            ),
        ],
        context=["address", "reside", "street", "suburb", "postcode"],
    )

    claim_amount = PatternRecognizer(
        supported_entity="CLAIM_AMOUNT",
        name="claim_amount_recognizer",
        patterns=[
            Pattern(
                name="currency_aud",
                regex=r"\b(?:AUD\s?)?\$?\d{1,3}(?:,\d{3})+(?:\.\d{2})?\b|\b(?:AUD\s?)?\$\d+(?:\.\d{2})?\b",
                score=0.45,
            ),
        ],
        context=["amount", "claim", "payout", "excess", "cost", "quote"],
    )

    return [
        au_phone,
        au_postcode,
        driver_license,
        medicare,
        abn,
        acn,
        bsb,
        account_number,
        policy_number,
        claim_number,
        au_address,
        claim_amount,
    ]


def filter_enabled(
    recognizers: list[PatternRecognizer],
    enabled: Optional[set[str]] = None,
) -> list[PatternRecognizer]:
    if enabled is None:
        return recognizers
    return [r for r in recognizers if r.supported_entities[0] in enabled]
