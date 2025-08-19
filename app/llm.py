# app/llm.py
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from litellm import acompletion

from .settings import settings
from .taxonomy import taxonomy


def _build_schema() -> dict[str, Any]:
    return {
        "name": "transaction_schema",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "description": {"type": "string"},
                "amount": {"type": "number"},
                "currency": {"type": "string", "enum": ["EUR"]},
                "account": {"type": "string", "enum": list(taxonomy.accounts)},
                "date": {"type": "string", "format": "date"},
                "outcome_categories": {
                    "type": ["array", "null"],
                    "items": {"type": "string", "enum": list(taxonomy.outcome_categories)},
                },
                "income_categories": {
                    "type": ["array", "null"],
                    "items": {"type": "string", "enum": list(taxonomy.income_categories)},
                },
                "notes": {"type": ["string", "null"]},
            },
            "required": ["description", "amount", "currency", "account", "date"],
        },
    }


def _build_system_prompt() -> str:
    lines = [
        "Sei un estrattore di transazioni. L'utente scrive frasi in italiano "
        "come 'ho comprato un caffè 1,20€ con Hype ieri'.",
        "Devi restituire SOLO JSON conforme allo schema fornito.",
        "Regole:",
        "- 'amount' in EUR come numero con punto decimale (1.20).",
        f"- 'date' normalizzata in formato YYYY-MM-DD usando il fuso {settings.timezone}.",
        f"- 'account' ∈ {list(taxonomy.accounts)}.",
        "- Se è una spesa: scegli SOLO tra queste categorie Outcome:",
        f"  {list(taxonomy.outcome_categories)}.",
        "- Se è un'entrata: scegli SOLO tra queste categorie Income:",
        f"  {list(taxonomy.income_categories)}.",
        "- Non inventare categorie nuove.",
    ]
    return "\n".join(lines) + "\n"


async def extract_transaction(text: str) -> dict[str, Any]:
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz).strftime("%Y-%m-%d")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": f"Oggi è {now}. Testo: {text}"},
    ]

    response_format: dict[str, Any] = {"type": "json_schema", "json_schema": _build_schema()}

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
