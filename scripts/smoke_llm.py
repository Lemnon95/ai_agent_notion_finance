#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from app.llm import extract_transaction
from app.models import ExtractedTx, NotionTx
from app.normalizer import normalize_account, normalize_outcome
from app.notion_gateway import NotionGateway
from app.taxonomy import is_taxonomy_loaded, set_taxonomy, taxonomy


async def main(text: str) -> int:
    # 1) Bootstrap taxonomy da Notion (prima di tutto)
    g = NotionGateway()
    g.verify_schema()
    set_taxonomy(g.read_taxonomy())
    if not is_taxonomy_loaded():
        print("ERRORE: tassonomia vuota dopo set_taxonomy(). Dump:")
        print("accounts:", taxonomy.accounts)
        print("outcome:", taxonomy.outcome_categories)
        print("income:", taxonomy.income_categories)
        return 1

    print(f"RAW: {text}")

    # 2) Estrazione LLM (vincolata da JSON Schema)
    data: dict[str, Any] = await extract_transaction(text)
    print("LLM JSON:", json.dumps(data, ensure_ascii=False, indent=2))

    # (Opzionale) Debug: stampa cosa vede il validator
    print("ALLOWED ACCOUNTS:", taxonomy.accounts)
    print("ALLOWED OUTCOME:", taxonomy.outcome_categories)
    print("ALLOWED INCOME:", taxonomy.income_categories)

    # 3) Normalizzazione PRIMA della validazione Pydantic
    data["account"] = normalize_account(data.get("account", ""), set(taxonomy.accounts))
    data["outcome_categories"] = normalize_outcome(
        data.get("outcome_categories"),
        data.get("description", ""),
        set(taxonomy.outcome_categories),
    )

    # 4) Validazione stretta (raise se qualcosa non va)
    tx = ExtractedTx.model_validate(data)
    print("VALIDATED:", tx.model_dump())

    # 5) Anteprima payload Notion (non scrive)
    ntx = NotionTx.from_extracted(tx)
    print("NOTION READY:", ntx.model_dump())

    return 0


if __name__ == "__main__":
    sample = " ".join(sys.argv[1:]) or "ho comprato un caffè 1,20€ con Hype ieri"
    raise SystemExit(asyncio.run(main(sample)))
