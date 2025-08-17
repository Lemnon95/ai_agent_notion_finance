from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from litellm import acompletion

from .settings import settings

# enum dinamici dalle impostazioni
OUTCOME_ENUM = settings.outcome_categories
INCOME_ENUM = settings.income_categories

JSON_SCHEMA: dict[str, Any] = {
    "name": "transaction_schema",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "description": {"type": "string"},
            "amount": {"type": "number"},
            "currency": {"type": "string", "enum": ["EUR"]},
            "account": {"type": "string", "enum": ["Hype", "Revolut", "Contanti"]},
            "date": {"type": "string", "format": "date"},
            "outcome_categories": {
                "type": ["array", "null"],
                "items": {"type": "string", "enum": OUTCOME_ENUM},
            },
            "income_categories": {
                "type": ["array", "null"],
                "items": {"type": "string", "enum": INCOME_ENUM},
            },
            "notes": {"type": ["string", "null"]},
        },
        "required": ["description", "amount", "currency", "account", "date"],
    },
}

SYSTEM_PROMPT = (
    "Sei un estrattore di transazioni. L'utente scrive frasi in italiano "
    "come 'ho comprato un caffè 1,20€ con Hype ieri'.\n"
    "Devi restituire SOLO JSON conforme allo schema fornito.\n"
    "Regole:\n"
    "- 'amount' in EUR come numero con punto decimale (1.20).\n"
    "- 'date' normalizzata in formato YYYY-MM-DD usando il fuso {tz}.\n"
    "- 'account' ∈ ['Hype','Revolut','Contanti'].\n"
    f"- Se è una spesa: scegli SOLO tra queste categorie Outcome: {OUTCOME_ENUM}.\n"
    f"- Se è un'entrata: scegli SOLO tra queste categorie Income: {INCOME_ENUM}.\n"
    "- Non inventare categorie nuove.\n"
)


async def extract_transaction(text: str) -> dict[str, Any]:
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz).strftime("%Y-%m-%d")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT.format(tz=settings.timezone)},
        {"role": "user", "content": f"Oggi è {now}. Testo: {text}"},
    ]

    response_format: dict[str, Any] = {
        "type": "json_schema",
        "json_schema": JSON_SCHEMA,
    }

    try:
        resp: Any = await acompletion(
            model=settings.llm_model,
            messages=messages,
            response_format=response_format,
            max_tokens=300,
            temperature=0.0,
        )
        content: str = resp.choices[0].message.content
    except Exception:
        resp = await acompletion(
            model=settings.llm_model,
            messages=[
                messages[0],
                {
                    "role": "user",
                    "content": (messages[1]["content"] + "\nRispondi SOLO con JSON valido."),
                },
            ],
            max_tokens=300,
            temperature=0.0,
        )
        content = resp.choices[0].message.content

    content = content.strip()
    if content.startswith("```"):
        parts = content.split("```")
        if len(parts) >= 3:
            candidate = parts[1]
            if candidate.lower().startswith("json"):
                candidate = candidate[4:]
            content = candidate

    data: Any = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("LLM returned non-object JSON")
    return cast(dict[str, Any], data)
