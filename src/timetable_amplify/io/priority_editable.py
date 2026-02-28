"""Read/write editable priority JSON."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PRIORITY_TO_WEIGHT = {
    1: 0.6,
    2: 0.8,
    3: 1.0,
    4: 1.2,
    5: 1.5,
}


def write_priority_json(path: Path, band_names: list[str]) -> None:
    """Write priority JSON with deduplicated band names and default priority=3."""
    unique_names = sorted({name.strip() for name in band_names if name.strip()})
    payload = {
        "version": 1,
        "bands": [{"band": name, "priority": 3} for name in unique_names],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _priority_to_weight(priority_raw: object, band_name: str) -> float:
    try:
        priority = int(priority_raw)
    except (TypeError, ValueError):
        logger.warning("priority.json: band '%s' has invalid priority '%s', fallback weight=1.0", band_name, priority_raw)
        return 1.0
    weight = _PRIORITY_TO_WEIGHT.get(priority)
    if weight is None:
        logger.warning("priority.json: band '%s' priority out of range (%s), fallback weight=1.0", band_name, priority)
        return 1.0
    return weight


def read_priority_json(path: Path) -> dict[str, float]:
    """Read priority JSON and convert values into `band_name -> weight` map.

    Missing/unreadable/invalid files return an empty mapping.
    """
    if not path.exists():
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("priority.json: failed to read '%s' (%s), fallback to default weights", path, exc)
        return {}

    if not isinstance(raw, dict):
        logger.warning("priority.json: root object must be a JSON object, fallback to default weights")
        return {}

    bands = raw.get("bands")
    if not isinstance(bands, list):
        logger.warning("priority.json: 'bands' must be an array, fallback to default weights")
        return {}

    out: dict[str, float] = {}
    for idx, entry in enumerate(bands, start=1):
        if not isinstance(entry, dict):
            logger.warning("priority.json: bands[%d] is not an object, skipped", idx)
            continue
        band_name = str(entry.get("band", "")).strip()
        if not band_name:
            logger.warning("priority.json: bands[%d].band is empty, skipped", idx)
            continue

        if "weight" in entry:
            try:
                out[band_name] = float(entry["weight"])
                continue
            except (TypeError, ValueError):
                logger.warning("priority.json: band '%s' has invalid weight '%s', fallback via priority", band_name, entry["weight"])

        out[band_name] = _priority_to_weight(entry.get("priority", 3), band_name)

    return out
