"""
Seeds repair_cost_reference with starting AUD cost ranges, sourced from
public Australian repair/restoration cost guides 

Run from backend/:
    python scripts/seed_repair_cost_reference.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import get_sync_connection

TODAY = date.today().isoformat()

# (product, damage_type, severity, cost_low, cost_high, unit, source)
ROWS = [
    # --- Motor ---
    ("motor", None, "minor", 100, 700, "per claim",
     "Bumper scuff/scratch, single-panel touch-up (K&W Panel Beating; MrP Automotive Refinishing)"),
    ("motor", None, "moderate", 1200, 3500, "per claim",
     "Multi-panel smash repair, national average (Alpha Smash Repair; Autobody Prestige Melbourne)"),
    ("motor", None, "severe", 5000, 20000, "per claim",
     "Rough estimate only - public guides don't cover severe/write-off tier well. "
     "Past ~60-70% of vehicle value, insurers typically total the vehicle instead "
     "of repairing (valuation-based, not repair-cost-based). Needs review."),
    ("motor", "storm", "minor", 60, 100, "per claim",
     "Windscreen chip repair (Airtasker; Yellow Pages windscreen guide)"),
    ("motor", "storm", "moderate", 300, 1200, "per claim",
     "Windscreen replacement, common vehicles (GoingRate windscreen calculator)"),

    # --- Property ---
    ("property", "storm", "minor", 150, 3000, "per claim",
     "General roof repair (Home Improvement Australia roof repair guide)"),
    ("property", "storm", "moderate", 800, 4500, "per claim",
     "Storm damage repair, Sydney-based guide (whatsthedamage.com.au)"),
    ("property", "storm", "severe", 4000, 28000, "per claim",
     "Hail/major roof damage up to full replacement ($22k-$65k at the top end) "
     "(whatsthedamage.com.au Sydney storm damage guide)"),
    ("property", "fire", "minor", 1500, 5000, "per claim",
     "Single room smoke/soot cleaning (disasterrecovery.com.au fire damage guide)"),
    ("property", "fire", "moderate", 8000, 30000, "per claim",
     "Whole-house smoke damage (disasterrecovery.com.au fire damage guide)"),
    ("property", "fire", "severe", 20000, 80000, "per claim",
     "Partial structural fire damage (disasterrecovery.com.au fire damage guide)"),
    ("property", "flood", "minor", 400, 1200, "per claim",
     "Single room carpet extraction/drying (servicetasker.com.au water damage guide)"),
    ("property", "flood", "moderate", 2500, 8000, "per claim",
     "Kitchen/bathroom water damage, whole-house restoration "
     "(floodservicesnewcastle.com.au; average payout ~$11,605 per stormlawpartners.com)"),
    ("property", "flood", "severe", 5000, 20000, "per claim",
     "Large-property full restoration incl. structural drying + mould remediation "
     "(floodservicesnewcastle.com.au water damage guide)"),
    ("property", "cyclone", "moderate", 10000, 40000, "per claim",
     "Typical mid-range residential cyclone event (disasterrecovery.com.au storm damage guide)"),
    ("property", "cyclone", "severe", 40000, 150000, "per claim",
     "Cyclone-specific structural restoration (disasterrecovery.com.au storm damage guide)"),
]

conn = get_sync_connection()
conn.autocommit = False
cur = conn.cursor()

cur.execute("DELETE FROM repair_cost_reference")
cur.executemany(
    """
    INSERT INTO repair_cost_reference
        (product, damage_type, severity, cost_low, cost_high, unit, region, source, effective_date)
    VALUES (%s, %s, %s, %s, %s, %s, 'AU', %s, %s)
    """,
    [(p, dt, sev, lo, hi, unit, src, TODAY) for p, dt, sev, lo, hi, unit, src in ROWS],
)

conn.commit()
print(f"Seeded {len(ROWS)} repair_cost_reference rows.")
conn.close()
