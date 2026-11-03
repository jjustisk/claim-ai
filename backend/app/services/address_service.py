"""Australian address search via the public Photon (OpenStreetMap) geocoder.

Demo-grade: queries leave Australia, so swap the provider before production.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.policy_prefill_service import state_code

logger = logging.getLogger(__name__)

PHOTON_URL = "https://photon.komoot.io/api/"
# Mainland Australia + Tasmania bounding box (min lon, min lat, max lon, max lat).
AU_BBOX = "112.9,-43.7,153.7,-10.6"
# Ranks nearby results first; Perth, where the demo policies are.
BIAS_LAT, BIAS_LON = -31.95, 115.86
_TIMEOUT = httpx.Timeout(5.0)
_HEADERS = {"User-Agent": "Claim-AI/1.0 (university capstone demo)"}


def _to_address(props: dict[str, Any]) -> dict[str, str] | None:
    street = props.get("street") or (props.get("name") if props.get("osm_key") == "highway" else None)
    if props.get("countrycode") != "AU" or not street:
        return None
    suburb = props.get("district") or props.get("locality") or props.get("city") or ""
    address = {
        "street_number": str(props.get("housenumber") or ""),
        "street_name": str(street),
        "suburb": str(suburb),
        "state": state_code(props.get("state")),
        "postcode": str(props.get("postcode") or ""),
    }
    head = " ".join(filter(None, [address["street_number"], address["street_name"]]))
    tail = " ".join(filter(None, [address["suburb"], address["state"], address["postcode"]]))
    address["label"] = ", ".join(filter(None, [head, tail]))
    return address


async def search_addresses(query: str, limit: int = 6) -> list[dict[str, str]]:
    """Return up to `limit` Australian address suggestions for free text; [] on any failure."""
    params = {"q": query, "limit": limit * 2, "lang": "en", "bbox": AU_BBOX, "lat": BIAS_LAT, "lon": BIAS_LON}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            response = await client.get(PHOTON_URL, params=params)
            response.raise_for_status()
            features = response.json().get("features") or []
    except (httpx.HTTPError, ValueError):
        logger.warning("Address search failed", exc_info=True)
        return []

    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for feature in features:
        address = _to_address(feature.get("properties") or {})
        if address and address["label"] not in seen:
            seen.add(address["label"])
            results.append(address)
        if len(results) >= limit:
            break
    return results
