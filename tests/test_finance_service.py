import asyncio
import os
from typing import Any, cast

from app.idempotency import IdempotencyStore
from app.models import NotionTx
from app.taxonomy import Taxonomy, set_taxonomy

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("NOTION_TOKEN", "test")
os.environ.setdefault("NOTION_DB_ID", "test")
os.environ.setdefault("OPENAI_API_KEY", "test")

from app.finance_service import FinanceService  # noqa: E402


def _taxonomy() -> Taxonomy:
    return Taxonomy(
        accounts=["Hype", "Contanti", "Risparmio"],
        outcome_categories=["Needs", "Supermarket", "Prelievo", "Risparmio"],
        income_categories=["Salary", "Gifts", "Prelievo", "Risparmio"],
    )


class FakeGateway:
    def __init__(self) -> None:
        self.saved: list[NotionTx] = []

    def verify_schema(self) -> None:
        pass

    def read_taxonomy(self) -> Taxonomy:
        return _taxonomy()

    def save_transaction(self, tx: NotionTx) -> str:
        self.saved.append(tx)
        return f"https://notion.test/{len(self.saved)}"


def test_finance_service_saves_transfer_and_deduplicates_recent_retry() -> None:
    set_taxonomy(_taxonomy())
    gateway = FakeGateway()
    service = FinanceService(
        gateway=cast(Any, gateway),
        idempotency=IdempotencyStore(ttl_seconds=60),
    )

    result = asyncio.run(service.process_text("prelievo 100€ da Hype", chat_id=123))
    retry = asyncio.run(service.process_text("prelievo 100€ da Hype", chat_id=123))

    assert result.parser == "rules"
    assert result.plan_kind == "transfer"
    assert not result.duplicate
    assert [(saved.tx.account, saved.kind) for saved in result.saved] == [
        ("Hype", "outcome"),
        ("Contanti", "income"),
    ]
    assert retry.duplicate
    assert len(gateway.saved) == 2
