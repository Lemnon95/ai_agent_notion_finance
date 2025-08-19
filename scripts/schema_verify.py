#!/usr/bin/env python3
from __future__ import annotations

import sys

from app.notion_gateway import NotionGateway


def main() -> int:
    g = NotionGateway()
    # 1) Verifica tipi base del DB (title/number/date + relation)
    try:
        g.verify_schema()
    except Exception as e:
        print(f"❌ Schema check failed:\n{e}")
        return 1

    # 2) Leggi le tassonomie dalle relation e verifica che non siano vuote
    try:
        t = g.read_taxonomy()
    except Exception as e:
        print(f"❌ Unable to read taxonomy from Notion:\n{e}")
        return 2

    if not t.accounts:
        print("❌ Empty taxonomy: no Accounts")
        return 3
    if not t.outcome_categories:
        print("❌ Empty taxonomy: no Outcome categories")
        return 4
    if not t.income_categories:
        print("❌ Empty taxonomy: no Income categories")
        return 5

    # 3) Report compatto
    print("Notion DB schema OK ✅")
    print(f"- Accounts: {len(t.accounts)}")
    print(f"- Outcome categories: {len(t.outcome_categories)}")
    print(f"- Income categories: {len(t.income_categories)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
