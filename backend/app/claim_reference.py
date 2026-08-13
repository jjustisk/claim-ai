""" Generates short, unique claim reference codes for claims. """

import secrets
import string 
from datetime import datetime, timezone

# Uppercase letters and digits for the claim reference code
_REFERENCE_ALPHABET = string.ascii_uppercase + string.digits
_SUFFIX_LENGTH = 6


def generate_claim_reference() -> str:
    """ 
    Build a reference like "CLM-20260813-K7QX2M"
    
    The date segment makes references sortable.
    Secrets are used to generate the random suffix to ensure uniqueness and unpredictability.

    """

    date_segment = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(_SUFFIX_LENGTH))
    return f"CLM-{date_segment}-{suffix}"