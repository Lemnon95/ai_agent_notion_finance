import asyncio
import datetime as dt
import os
from decimal import Decimal
from typing import Any, cast

from pytest import MonkeyPatch

from app.idempotency import IdempotencyStore
from app.models import NotionTx
from app.taxonomy import Taxonomy, set_taxonomy

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("NOTION_TOKEN", "test")
os.environ.setdefault("NOTION_DB_ID", "test")
os.environ.setdefault("OPENAI_API_KEY", "test")

from app.finance_service import FinanceService  # noqa: E402
from app.settings import settings  # noqa: E402


def _taxonomy() -> Taxonomy:
    return Taxonomy(
        accounts=["Hype", "Contanti", "Risparmio"],
        outcome_categories=["Needs", "Supermarket", "Prelievo", "Risparmio", "Barbiere"],
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


def test_finance_service_conservative_mode_sends_non_whitelisted_rules_to_llm(
    monkeypatch: MonkeyPatch,
) -> None:
    set_taxonomy(_taxonomy())
    monkeypatch.setattr(settings, "rule_parser_mode", "conservative")

    async def fake_extract(self: FinanceService, text: str) -> NotionTx:
        return NotionTx(
            description=text,
            amount=Decimal("18"),
            date=dt.date(2026, 7, 9),
            account="Contanti",
            outcome_categories=["Barbiere"],
        )

    monkeypatch.setattr(FinanceService, "_extract_with_llm", fake_extract)
    gateway = FakeGateway()
    service = FinanceService(gateway=cast(Any, gateway))

    result = asyncio.run(service.process_text("barbiere 18 euro contanti", chat_id=123))

    assert result.parser == "llm"
    assert result.saved[0].tx.outcome_categories == ["Barbiere"]
    assert len(gateway.saved) == 1


def test_finance_service_balanced_mode_accepts_non_whitelisted_rule_categories(
    monkeypatch: MonkeyPatch,
) -> None:
    set_taxonomy(_taxonomy())
    monkeypatch.setattr(settings, "rule_parser_mode", "balanced")
    gateway = FakeGateway()
    service = FinanceService(gateway=cast(Any, gateway))

    result = asyncio.run(service.process_text("barbiere 18 euro contanti", chat_id=123))

    assert result.parser == "rules"
    assert result.saved[0].tx.outcome_categories == ["Barbiere"]
    assert len(gateway.saved) == 1
