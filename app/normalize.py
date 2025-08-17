from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .settings import settings

# ✔️ Nomi ASCII per le variabili
EURO_SIGN_RE = re.compile(r"\s*€")  # oppure: re.compile(r"\s*" + "\u20AC")
COMMA_AMOUNT_RE = re.compile(r"(\d+),(\d{1,2})(?!\d)")
MULTI_SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    t = text.strip()
    # "1,20€" -> "1.20 EUR"
    t = EURO_SIGN_RE.sub(" EUR", t)
    t = COMMA_AMOUNT_RE.sub(lambda m: f"{m.group(1)}.{m.group(2)}", t)
    t = MULTI_SPACE_RE.sub(" ", t)
    return t


def resolve_relative_dates(text: str) -> str:
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()
    mapping = {
        "oggi": today,
        "ieri": today - timedelta(days=1),
        "l'altro ieri": today - timedelta(days=2),
    }
    out = text
    for k, d in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True):
        out = re.sub(rf"\b{k}\b", d.isoformat(), out, flags=re.IGNORECASE)
    return out


def preprocess(text: str) -> str:
    return resolve_relative_dates(normalize_text(text))
