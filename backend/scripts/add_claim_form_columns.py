"""Add claimant-form columns to an existing claim table."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.claim_service import ensure_claim_form_columns

ensure_claim_form_columns()
print("Migration complete: claim form columns are live.")
