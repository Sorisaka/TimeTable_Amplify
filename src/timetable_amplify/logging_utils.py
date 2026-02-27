"""Centralized logger setup."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from .models import LoggingConfig


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(config: LoggingConfig, debug: bool = False) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    level = logging.DEBUG if debug else getattr(logging, config.level.upper(), logging.INFO)
    root.setLevel(level)

    handler = logging.StreamHandler()
    if config.json:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
