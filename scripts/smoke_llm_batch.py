#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from typing import Any

from app.llm import extract_transaction
from app.models import ExtractedTx
from app.normalizer import (
    enforce_xor_categories,
    normalize_account,
    normalize_outcome,
)
from app.notion_gateway import NotionGateway
from app.taxonomy import set_taxonomy, taxonomy

SAMPLES: list[str] = [
    # Outcome
    "cappuccino e cornetto 3,40€ contanti oggi",
    "pranzo pizzeria 14,50€ con Revolut",
    "spesa supermercato 27,90€ con Hype",
    "benzina 45€ hype",
    "parrucchiere 18€ contanti",
    "abbonamento spotify 9,99€ su revolut",
    "bolletta luce 63,25€ poste italiane",
    "palestra 39,90€ con hype",
    "integratori omega3 12,50€ contanti",
    "scarpe 79,99€ con Hype",
    "farmacia 8,70€ contanti",
    "lezione salsa 10€ contanti",
    "taxi 17€ hype",
    "scarico 30€ versati nel salvadanaio winnies",
    "regalo compleanno 25€ con revolut",
    # Income
    "stipendio 1820€ su Revolut oggi",
    "regalo 50€ contanti",
    "prelievo 100€ da Hype",
    "spostato 200€ su Risparmio Car",
    # Edge
    "ho preso un caffe 1.20 euro hype ieri",
    "cena 18€",
    "biglietto treno 24,90€",
    "olio motore 19€",
    "donazione 15€ con Revolut",
]


async def prep_taxonomy() -> None:
    g = NotionGateway()
    g.verify_schema()
    set_taxonomy(g.read_taxonomy())


def pretty_tx(tx: ExtractedTx) -> str:
    cats = tx.outcome_categories or tx.income_categories or []
    cats_s = ", ".join(cats) if cats else "—"
    return (
        f"  - desc: {tx.description}\n"
        f"  - date: {tx.date}\n"
        f"  - amt : €{tx.amount}\n"
        f"  - acc : {tx.account}\n"
        f"  - cat : {cats_s}\n"
    )


async def run_one(sample: str) -> None:
    try:
        data: dict[str, Any] = await extract_transaction(sample)

        # --- Normalizzazione PRIMA della validazione ---
        # account tollerante a None
        data["account"] = normalize_account(
            (data.get("account") or ""), set(taxonomy.accounts)
        ) or data.get("account")

        # categorie outcome preliminari (keyword -> categoria)
        data["outcome_categories"] = normalize_outcome(
            data.get("outcome_categories"),
            data.get("description", ""),
            set(taxonomy.outcome_categories),
        )

        # Impone XOR tra outcome/income (evita doppie classificazioni)
        out_fixed, inc_fixed = enforce_xor_categories(
            description=data.get("description", ""),
            outcome=data.get("outcome_categories"),
            income=data.get("income_categories"),
            allowed_outcome=set(taxonomy.outcome_categories),
            allowed_income=set(taxonomy.income_categories),
        )
        data["outcome_categories"] = out_fixed
        data["income_categories"] = inc_fixed

        # --- Validazione ---
        tx = ExtractedTx.model_validate(data)
        print(f"OK: {sample}")
        print(pretty_tx(tx))
    except Exception as e:
        print(f"FAIL: {sample}")
        print(f"  > {e}\n")


async def main() -> int:
    await prep_taxonomy()
    print("ACCOUNTS:", taxonomy.accounts)
    print("OUTCOME :", taxonomy.outcome_categories)
    print("INCOME  :", taxonomy.income_categories)
    print("=" * 60)

    for s in SAMPLES:
        await run_one(s)
        print("-" * 60)
    return 0


if __name__ == "__main__":
    asyncio.run(main())
