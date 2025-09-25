# app/llm.py
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

import litellm
from litellm import acompletion
from litellm.exceptions import UnsupportedParamsError

from .normalizer import enforce_xor_categories
from .settings import settings
from .taxonomy import taxonomy


def _build_schema() -> dict[str, Any]:
    """
    JSON Schema vincolato alla tassonomia runtime.
    Nota: outcome_categories permette 1–2 voci (es. ['Wants','Fun']).
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "transaction_schema",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "description": {"type": "string"},
                    "amount": {"type": "number"},
                    "currency": {"type": "string", "enum": ["EUR"]},
                    "account": {
                        "type": "string",
                        "enum": list(taxonomy.accounts),
                    },
                    "date": {"type": "string", "format": "date"},
                    "outcome_categories": {
                        "type": ["array", "null"],
                        "minItems": 1,
                        "maxItems": 2,
                        "items": {
                            "type": "string",
                            "enum": list(taxonomy.outcome_categories),
                        },
                    },
                    "income_categories": {
                        "type": ["array", "null"],
                        "minItems": 1,
                        "maxItems": 1,
                        "items": {
                            "type": "string",
                            "enum": list(taxonomy.income_categories),
                        },
                    },
                    "notes": {"type": ["string", "null"]},
                },
                "required": [
                    "description",
                    "amount",
                    "currency",
                    "account",
                    "date",
                ],
            },
        },
    }


def _build_system_prompt() -> str:
    """
    Outcome: preferisci DUE categorie -> [MACRO, SPECIFICA].
    MACRO ∈ {'Wants','Needs','Savings'}; SPECIFICA è una categoria Outcome.
    Se non esiste una SPECIFICA sensata (es. risparmio generico),
    puoi usare solo la MACRO.
    """
    accounts = list(taxonomy.accounts)
    outcome = list(taxonomy.outcome_categories)
    income = list(taxonomy.income_categories)

    lines = [
        (
            "Sei un estrattore di transazioni in italiano. "
            "Devi restituire SOLO JSON conforme allo schema fornito."
        ),
        "",
        "REGOLE:",
        "- 'amount' è un numero con punto decimale (es. 1.2).",
        (
            f"- 'date' in formato YYYY-MM-DD usando il fuso {settings.timezone} "
            "(interpreta 'oggi', 'ieri')."
        ),
        f"- 'account' deve essere uno fra: {accounts}.",
        "- Se è una SPESA: scegli SOLO tra queste categorie Outcome:",
        f"  {outcome}.",
        "- Se è un'ENTRATA: scegli SOLO tra queste categorie Income:",
        f"  {income}.",
        (
            "- NON impostare contemporaneamente outcome_categories e "
            "income_categories (regola XOR)."
        ),
        (
            "- Non usare sinonimi o valori non presenti nelle liste. "
            "Non scrivere testo extra fuori dal JSON."
        ),
        "- Quando un campo non si applica, usa null (non liste vuote).",
        "",
        "CONVENZIONE PER LE SPESE (Outcome):",
        "- Preferisci due categorie nell'ordine: [MACRO, SPECIFICA].",
        "- La MACRO è una di: 'Wants', 'Needs', 'Savings'.",
        (
            "- La SPECIFICA è una categoria dettagliata (es. 'Fun', 'Supermarket', "
            "'Bollette', 'Salute', 'Travel', 'Ballo', 'Palestra', "
            "'Gifts & Donations', ...)."
        ),
        (
            "- Se non c'è una SPECIFICA sensata (es. risparmio generico), "
            "puoi usare solo la MACRO (['Savings'])."
        ),
        "",
        "SCELTA DELLA MACRO (default, salvo contesto contrario):",
        (
            "- 'Eating Out and Takeway', 'Fun', 'Subscriptions', 'Travel', 'Ballo', "
            "'Palestra', 'Vestiario' → MACRO = 'Wants'"
        ),
        (
            "- 'Supermarket', 'Bollette', 'Casa', 'Salute', 'Integratori', "
            "'Benzina', 'Car' → MACRO = 'Needs'"
        ),
        (
            "- Casi di risparmio/spostamenti verso obiettivi: 'Savings', "
            "'Risparmio', 'Risparmio Car', 'Salvadanaio Winnies' → "
            "MACRO = 'Savings'"
        ),
        "",
        "ALCUNE MAPPATURE DI CONTENUTO (SPECIFICA):",
        (
            "- BAR/PASTI: 'caffè', 'cappuccino', 'bar', 'pranzo', 'cena', "
            "'pizzeria', 'ristorante', 'aperitivo' → 'Eating Out and Takeway'"
        ),
        "- SUPERMERCATO: 'supermercato', 'spesa' → 'Supermarket'",
        (
            "- GAMING: 'videogioco', 'videogame', 'gioco', 'gaming', 'steam', "
            "'epic games', 'gog', 'uplay', 'origin', 'playstation store', "
            "'ps store', 'nintendo eshop', 'xbox', 'game pass' → 'Fun'"
        ),
        (
            "- ABBONAMENTI DIGITALI: 'spotify', 'netflix', 'abbonamento' "
            "(servizi ricorrenti) → 'Subscriptions'"
        ),
        "- VIAGGI/TRASPORTO: 'taxi', 'treno', 'biglietto', 'aereo' → 'Travel'",
        ("- DONAZIONI (denaro dato/beneficenza): 'donazione', 'donare' → " "'Gifts & Donations'"),
        "",
        "ENTRATE (Income):",
        "- Non usare la convenzione macro+specifica. Metti solo una categoria.",
        "- 'regalo' come ENTRATA (denaro ricevuto) → 'Gifts' (Income).",
        "- 'stipendio' → 'Salary' (Income).",
        (
            "- Se non si adatta ad alcuna Income e 'Other Income' è disponibile, "
            "usa 'Other Income'."
        ),
        "",
        "ESEMPI (usa i nomi esatti delle liste):",
        "Input: 'ho comprato un videogioco su Steam con Hype 3,99€ ieri'",
        (
            "Output: {"
            '  "description": "ho comprato un videogioco su Steam con Hype 3,99€ ieri",'
            '  "amount": 3.99,'
            '  "currency": "EUR",'
            '  "account": "Hype",'
            f'  "date": "<ieri in {settings.timezone} in ISO>",'
            '  "outcome_categories": ["Wants", "Fun"],'
            '  "income_categories": null,'
            '  "notes": null'
            "}"
        ),
        "Input: 'spesa supermercato 27,90€ con Hype oggi'",
        (
            "Output: {"
            '  "description": "spesa supermercato 27,90€ con Hype oggi",'
            '  "amount": 27.90,'
            '  "currency": "EUR",'
            '  "account": "Hype",'
            '  "date": "<oggi in ISO>",'
            '  "outcome_categories": ["Needs", "Supermarket"],'
            '  "income_categories": null,'
            '  "notes": null'
            "}"
        ),
        "Input: 'bolletta luce 63,25€ poste italiane'",
        (
            "Output: {"
            '  "description": "bolletta luce 63,25€ poste italiane",'
            '  "amount": 63.25,'
            '  "currency": "EUR",'
            '  "account": "Poste Italiane",'
            '  "date": "<oggi in ISO>",'
            '  "outcome_categories": ["Needs", "Bollette"],'
            '  "income_categories": null,'
            '  "notes": null'
            "}"
        ),
        "Input: 'spostato 200€ su Risparmio Car'",
        (
            "Output: {"
            '  "description": "spostato 200€ su Risparmio Car",'
            '  "amount": 200.0,'
            '  "currency": "EUR",'
            '  "account": "<se indicato nel testo, altrimenti deducibile>",'
            '  "date": "<oggi in ISO>",'
            '  "outcome_categories": ["Savings", "Risparmio Car"],'
            '  "income_categories": null,'
            '  "notes": null'
            "}"
        ),
        "Input: 'ho fatto una donazione 15€ con Revolut'",
        (
            "Output: {"
            '  "description": "ho fatto una donazione 15€ con Revolut",'
            '  "amount": 15.0,'
            '  "currency": "EUR",'
            '  "account": "Revolut",'
            '  "date": "<oggi in ISO>",'
            '  "outcome_categories": ["Wants", "Gifts & Donations"],'
            '  "income_categories": null,'
            '  "notes": null'
            "}"
        ),
        "Input: 'ho ricevuto un regalo 50€ contanti'",
        (
            "Output: {"
            '  "description": "ho ricevuto un regalo 50€ contanti",'
            '  "amount": 50.0,'
            '  "currency": "EUR",'
            '  "account": "Contanti",'
            '  "date": "<oggi in ISO>",'
            '  "outcome_categories": null,'
            '  "income_categories": ["Gifts"],'
            '  "notes": null'
            "}"
        ),
        "",
        (
            "Se nessuna categoria SPECIFICA è adatta ma è chiaramente una SPESA, "
            "usa ['Wants'] o ['Needs'] o ['Savings'] da sola, secondo buon senso."
        ),
        "Rispondi SOLO con JSON valido.",
    ]
    return "\n".join(lines) + "\n"


def _is_gpt5() -> bool:
    return settings.llm_model.lower().startswith("gpt-5")


async def _call_llm(
    messages: list[dict[str, str]],
    response_format: dict[str, Any],
) -> Any:
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


async def extract_transaction(text: str) -> dict[str, Any]:
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz).strftime("%Y-%m-%d")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": f"Oggi è {now}. Testo: {text}"},
    ]

    response_format = _build_schema()

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

    # ---- Enforce XOR tra outcome/income (difesa centrale) ----
    out_fixed, inc_fixed = enforce_xor_categories(
        description=data.get("description", ""),
        outcome=data.get("outcome_categories"),
        income=data.get("income_categories"),
        allowed_outcome=set(taxonomy.outcome_categories),
        allowed_income=set(taxonomy.income_categories),
    )
    data["outcome_categories"] = out_fixed
    data["income_categories"] = inc_fixed

    return cast(dict[str, Any], data)
