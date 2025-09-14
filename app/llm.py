# app/llm.py
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

import litellm
from litellm import acompletion
from litellm.exceptions import UnsupportedParamsError

from .settings import settings
from .taxonomy import taxonomy


def _build_schema() -> dict[str, Any]:
    # JSON Schema vincolato alla tassonomia runtime
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
                    "items": {
                        "type": "string",
                        "enum": list(taxonomy.outcome_categories),
                    },
                },
                "income_categories": {
                    "type": ["array", "null"],
                    "items": {
                        "type": "string",
                        "enum": list(taxonomy.income_categories),
                    },
                },
                "notes": {"type": ["string", "null"]},
            },
            "required": ["description", "amount", "currency", "account", "date"],
        },
    }


def _pick_example_outcome() -> str:
    # Preferenze solo tra categorie che realmente esistono
    prefs = [
        "Eating Out and Takeway",
        "Supermarket",
        "Needs",
        "Fun",
        "Other Outcome",
    ]
    for p in prefs:
        if p in taxonomy.outcome_categories:
            return p
    return taxonomy.outcome_categories[0] if taxonomy.outcome_categories else "Other Outcome"


def _pick_example_income() -> str:
    prefs = ["Salary", "Gifts", "Other Income", "Prelievo", "Risparmio", "Risparmio Car"]
    for p in prefs:
        if p in taxonomy.income_categories:
            return p
    return taxonomy.income_categories[0] if taxonomy.income_categories else "Salary"


def _build_system_prompt() -> str:
    """
    Prompt forte: regole, liste vincolate e few-shot mirati per bar vs supermercato.
    Nota: manteniamo i nomi esatti presenti in tassonomia (es. 'Eating Out and Takeway').
    """
    lines = [
        "Sei un estrattore di transazioni. L'utente scrive frasi in italiano "
        "come 'ho comprato un caffè 1,20€ con Hype ieri'.",
        "Devi restituire SOLO JSON conforme allo schema fornito (nessun testo extra).",
        "Regole:",
        "- 'amount' è un numero con punto decimale (es. 1.2).",
        f"- 'date' in formato YYYY-MM-DD usando il fuso {settings.timezone} (interpreta 'oggi', 'ieri').",
        f"- 'account' deve essere uno di: {list(taxonomy.accounts)}.",
        "- Se è una spesa: scegli SOLO tra queste categorie Outcome:",
        f"  {list(taxonomy.outcome_categories)}.",
        "- Se è un'entrata: scegli SOLO tra queste categorie Income:",
        f"  {list(taxonomy.income_categories)}.",
        "- Se nessuna categoria è adatta, usa 'Other Outcome'.",
        "- Non lasciare campi vuoti se ricavabili dal testo. Se il testo menziona un account, usalo.",
        "",
        "Suggerimenti di mappatura (se il contesto non dice il contrario):",
        "- 'caffè', 'caffe', 'cappuccino', 'espresso', 'cornetto', 'brioche', 'bar', 'colazione' → 'Eating Out and Takeway'",
        "- 'ristorante', 'trattoria', 'pizzeria', 'aperitivo' → 'Eating Out and Takeway'",
        "- 'supermercato', 'spesa' → 'Supermarket'",
        "- 'stipendio' → 'Salary' (se presente nelle categorie Income)",
        "- 'regalo', 'donazione' → 'Gifts' (se presente nelle categorie Income)",
        "",
        "Esempi:",
        f"Input: 'ho preso un caffè al bar 1,20€ con Hype ieri'\n"
        f"Output: {{\n"
        f'  "description": "ho preso un caffè al bar 1,20€ con Hype ieri",\n'
        f'  "amount": 1.2,\n'
        f'  "currency": "EUR",\n'
        f'  "account": "Hype",\n'
        f'  "date": "<ieri in {settings.timezone} in ISO>",\n'
        f'  "outcome_categories": ["Eating Out and Takeway"],\n'
        f'  "income_categories": null,\n'
        f'  "notes": null\n'
        f"}}",
        f"Input: 'comprato caffè in grani al supermercato 12€ con Contanti oggi'\n"
        f"Output: {{\n"
        f'  "description": "comprato caffè in grani al supermercato 12€ con Contanti oggi",\n'
        f'  "amount": 12.0,\n'
        f'  "currency": "EUR",\n'
        f'  "account": "Contanti",\n'
        f'  "date": "<oggi in {settings.timezone} in ISO>",\n'
        f'  "outcome_categories": ["Supermarket"],\n'
        f'  "income_categories": null,\n'
        f'  "notes": null\n'
        f"}}",
        "",
        "Rispondi SOLO con JSON valido.",
    ]
    return "\n".join(lines) + "\n"


def _is_gpt5() -> bool:
    return settings.llm_model.lower().startswith("gpt-5")


async def _call_llm(messages: list[dict[str, str]], response_format: dict[str, Any]) -> Any:
    """Chiama l'LLM gestendo differenze tra GPT-5 e altri modelli."""
    kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "response_format": response_format,
        "max_tokens": 300,
    }
    try:
        if _is_gpt5():
            # GPT-5: niente temperature/top_p; usa controlli nuovi
            return await acompletion(
                extra_body={"reasoning_effort": "minimal", "verbosity": "low"},
                **kwargs,
            )
        # Modelli non GPT-5: forza determinismo per l'estrazione
        return await acompletion(temperature=0.0, **kwargs)
    except UnsupportedParamsError:
        # Se qualche param non è supportato, lascia che litellm lo rimuova
        litellm.drop_params = True
        return await acompletion(**kwargs)


def _heuristic_fill_account(text: str, account: str | None) -> str | None:
    """Se l'LLM non ha messo l'account, prova a dedurlo dal testo (match case-insensitive)."""
    if account and account.strip():
        return account
    t = text.lower()
    for acc in taxonomy.accounts:
        if acc.lower() in t:
            return acc
    return account


def _infer_default_categories(
    text: str, outcome: list[str] | None, income: list[str] | None
) -> tuple[list[str] | None, list[str] | None]:
    """
    Se l'LLM non ha messo alcuna categoria, prova a dedurre una scelta ragionevole.
    - Preferisci mappature che esistono DAVVERO nella tassonomia.
    - Fallback a 'Other Outcome' se presente, altrimenti prima outcome disponibile.
    """
    if outcome or income:
        return outcome, income

    t = text.lower()

    # Heuristics per entrate (solo se la categoria esiste davvero)
    inc_prefs: list[tuple[str, str]] = [
        ("stipendio", "Salary"),
        ("salary", "Salary"),
        ("regalo", "Gifts"),
        ("donazione", "Gifts"),
        ("gift", "Gifts"),
        ("prelievo", "Prelievo"),
        ("risparmio car", "Risparmio Car"),
        ("risparmio", "Risparmio"),
        ("other income", "Other Income"),
    ]
    for kw, cat in inc_prefs:
        if kw in t and cat in taxonomy.income_categories:
            return outcome, [cat]

    # Default outcome ragionevole
    if "Other Outcome" in taxonomy.outcome_categories:
        return ["Other Outcome"], income
    if taxonomy.outcome_categories:
        return [taxonomy.outcome_categories[0]], income

    return outcome, income


async def extract_transaction(text: str) -> dict[str, Any]:
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz).strftime("%Y-%m-%d")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": f"Oggi è {now}. Testo: {text}"},
    ]

    response_format: dict[str, Any] = {
        "type": "json_schema",
        "json_schema": _build_schema(),
    }

    try:
        resp: Any = await _call_llm(messages, response_format)
        content: str = resp.choices[0].message.content
    except Exception:
        # Fallback: stesso prompt con reminder esplicito
        resp = await _call_llm(
            [
                messages[0],
                {
                    "role": "user",
                    "content": (messages[1]["content"] + "\nRispondi SOLO con JSON valido."),
                },
            ],
            response_format,
        )
        content = resp.choices[0].message.content

    content = content.strip()
    # Rimuovi eventuali fence ```json
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

    # ---- Post-processing robusto (rimane leggero: il grosso lo farà il normalizer + validator) ----
    # 1) Account vuoto → prova a dedurre dal testo
    acc = cast(str | None, data.get("account"))
    data["account"] = _heuristic_fill_account(text, acc) or acc

    # 2) Nessuna categoria → metti un default coerente
    out_raw = cast(list[str] | None, data.get("outcome_categories"))
    inc_raw = cast(list[str] | None, data.get("income_categories"))
    out_fixed, inc_fixed = _infer_default_categories(text, out_raw, inc_raw)
    data["outcome_categories"] = out_fixed
    data["income_categories"] = inc_fixed

    return cast(dict[str, Any], data)
