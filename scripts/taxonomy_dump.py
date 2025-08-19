#!/usr/bin/env python3
from __future__ import annotations

from app.notion_gateway import NotionGateway


def main() -> None:
    g = NotionGateway()
    t = g.read_taxonomy()
    print("Accounts:", t.accounts)
    print("Outcome:", t.outcome_categories)
    print("Income:", t.income_categories)


if __name__ == "__main__":
    main()
