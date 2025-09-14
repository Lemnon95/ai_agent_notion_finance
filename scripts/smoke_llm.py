#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from app.llm import extract_transaction
from app.models import ExtractedTx, NotionTx
from app.normalizer import enforce_xor_categories, normalize_account, normalize_outcome
from app.notion_gateway import NotionGateway
from app.taxonomy import set_taxonomy, taxonomy


async def main(text: str) -> int:
    # 1) Bootstrap taxonomy (da Notion) prima di tutto
    g = NotionGateway()
    g.verify_schema()
    set_taxonomy(g.read_taxonomy())

    # Guard di sicurezza
    if not (taxonomy.accounts and taxonomy.outcome_categories and taxonomy.income_categories):
        print("ERRORE: tassonomia vuota dopo set_taxonomy().")
        print("accounts:", taxonomy.accounts)
        print("outcome :", taxonomy.outcome_categories)
        print("income  :", taxonomy.income_categories)
        return 1

    print(f"RAW: {text}")

    # 2) LLM extraction
    data: dict[str, Any] = await extract_transaction(text)
    print("LLM JSON:", json.dumps(data, ensure_ascii=False, indent=2))

    # 3) Debug: liste consentite
    print("ALLOWED ACCOUNTS:", taxonomy.accounts)
    print("ALLOWED OUTCOME:", taxonomy.outcome_categories)
    print("ALLOWED INCOME:", taxonomy.income_categories)

    # 4) Normalizzazione PRIMA della validazione Pydantic
    data["account"] = normalize_account(
        (data.get("account") or ""), set(taxonomy.accounts)
    ) or data.get("account")

    data["outcome_categories"] = normalize_outcome(
        data.get("outcome_categories"),
        data.get("description", ""),
        set(taxonomy.outcome_categories),
    )

    # 5) Impone XOR tra outcome/income (risolve doppie classificazioni)
    out_fixed, inc_fixed = enforce_xor_categories(
        description=data.get("description", ""),
        outcome=data.get("outcome_categories"),
        income=data.get("income_categories"),
        allowed_outcome=set(taxonomy.outcome_categories),
        allowed_income=set(taxonomy.income_categories),
    )
    data["outcome_categories"] = out_fixed
    data["income_categories"] = inc_fixed

    # 6) Validazione stretta
    tx = ExtractedTx.model_validate(data)
    print("VALIDATED:", tx.model_dump())

    # 7) Anteprima payload Notion (non scrive)
    ntx = NotionTx.from_extracted(tx)
    print("NOTION READY:", ntx.model_dump())
    return 0


if __name__ == "__main__":
    sample = " ".join(sys.argv[1:]) or "ho comprato un caffè 1,20€ con Hype ieri"
    raise SystemExit(asyncio.run(main(sample)))
