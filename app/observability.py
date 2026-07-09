from __future__ import annotations

import json
import logging
from typing import Any


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Log strutturato minimale, senza dipendere da librerie esterne."""
    payload = json.dumps(fields, ensure_ascii=False, sort_keys=True, default=str)
    logger.info("event=%s %s", event, payload)
