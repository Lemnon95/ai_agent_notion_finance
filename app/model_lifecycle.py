# app/model_lifecycle.py
"""Avviso anticipato quando OpenAI annuncia lo spegnimento del modello LLM configurato."""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx

OPENAI_MODELS_URL = "https://api.openai.com/v1/models/{model}"
WARNING_DAYS = 60


def openai_model_name(model: str) -> str | None:
    """Nome del modello per l'API OpenAI, o None se il modello e di un altro provider."""
    provider, sep, name = model.partition("/")
    if not sep:
        return model
    return name if provider.lower() == "openai" else None


def fetch_shutdown_date(model: str, api_key: str, client: httpx.Client) -> dt.date | None:
    """Legge `shutdown_date` (YYYY-MM-DD, null o assente se non annunciato) da GET /v1/models."""
    resp = client.get(
        OPENAI_MODELS_URL.format(model=model),
        headers={"Authorization": f"Bearer {api_key}"},
    )
    resp.raise_for_status()
    data: Any = resp.json()
    raw = data.get("shutdown_date") if isinstance(data, dict) else None
    return dt.date.fromisoformat(raw) if isinstance(raw, str) and raw else None


def shutdown_warning(
    model: str, shutdown: dt.date | None, today: dt.date, warning_days: int = WARNING_DAYS
) -> str | None:
    """Messaggio per l'utente se lo spegnimento e entro `warning_days` giorni (o gia passato)."""
    if shutdown is None:
        return None
    days = (shutdown - today).days
    if days > warning_days:
        return None
    when = shutdown.strftime("%d/%m/%Y")
    if days < 0:
        return f"⚠️ OpenAI ha spento il modello {model} in data {when}: cambia LLM_MODEL."
    return (
        f"⚠️ OpenAI spegnerà il modello {model} in data {when} (tra {days} giorni): "
        "cambia LLM_MODEL prima di quella data."
    )
