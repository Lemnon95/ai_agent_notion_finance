#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from app.finance_service import FinanceService, notion_tx_from_llm
from app.llm import extract_transaction
from app.taxonomy import taxonomy


async def main(text: str) -> int:
    # 1) Stesso bootstrap del bot: schema, tassonomia, DEFAULT_ACCOUNT (non scrive su Notion)
    FinanceService().bootstrap()

    # Guard di sicurezza
    if not (taxonomy.accounts and taxonomy.outcome_categories and taxonomy.income_categories):
        print("ERRORE: tassonomia vuota dopo il bootstrap.")
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

    # 4) Normalizzazione + validazione come nel bot; anteprima payload Notion (non scrive)
    ntx = notion_tx_from_llm(data)
    print("NOTION READY:", ntx.model_dump())
    return 0


if __name__ == "__main__":
    sample = " ".join(sys.argv[1:]) or "ho comprato un caffè 1,20€ con Hype ieri"
    raise SystemExit(asyncio.run(main(sample)))
