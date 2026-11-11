import asyncio
import datetime as dt
import os
from decimal import Decimal
from typing import Any, cast

import pytest
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
        self.archived: list[str] = []
        self.fail_archive = False

    def verify_schema(self) -> None:
        pass

    def read_taxonomy(self) -> Taxonomy:
        return _taxonomy()

    def save_transaction(self, tx: NotionTx) -> str:
        self.saved.append(tx)
        return f"https://notion.test/{len(self.saved)}"

    def archive_page(self, url: str) -> None:
        if self.fail_archive:
            raise RuntimeError("notion down")
        self.archived.append(url)


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


def _llm_payload(account: str | None) -> dict[str, Any]:
    return {
        "description": "cena 18€",
        "amount": 18,
        "currency": "EUR",
        "account": account,
        "date": dt.date.today().isoformat(),
        "outcome_categories": ["Needs"],
        "income_categories": None,
        "notes": None,
    }


def test_llm_without_account_uses_default_account(monkeypatch: MonkeyPatch) -> None:
    set_taxonomy(_taxonomy())
    monkeypatch.setattr(settings, "rule_parser_mode", "conservative")
    monkeypatch.setattr(settings, "default_account", "Hype")

    async def fake_extract(text: str) -> dict[str, Any]:
        return _llm_payload(None)

    monkeypatch.setattr("app.finance_service.extract_transaction", fake_extract)
    gateway = FakeGateway()
    service = FinanceService(gateway=cast(Any, gateway))

    result = asyncio.run(service.process_text("cena 18€", chat_id=1))

    assert result.parser == "llm"
    assert gateway.saved[0].account == "Hype"


def test_llm_account_wins_over_default_account(monkeypatch: MonkeyPatch) -> None:
    set_taxonomy(_taxonomy())
    monkeypatch.setattr(settings, "default_account", "Hype")

    async def fake_extract(text: str) -> dict[str, Any]:
        return _llm_payload("Contanti")

    monkeypatch.setattr("app.finance_service.extract_transaction", fake_extract)
    gateway = FakeGateway()
    service = FinanceService(gateway=cast(Any, gateway))

    asyncio.run(service.process_text("cena 18€ contanti", chat_id=2))

    assert gateway.saved[0].account == "Contanti"


def test_llm_without_account_and_no_default_asks_for_account(monkeypatch: MonkeyPatch) -> None:
    set_taxonomy(_taxonomy())
    monkeypatch.setattr(settings, "default_account", None)

    async def fake_extract(text: str) -> dict[str, Any]:
        return _llm_payload(None)

    monkeypatch.setattr("app.finance_service.extract_transaction", fake_extract)
    service = FinanceService(gateway=cast(Any, FakeGateway()))

    with pytest.raises(ValueError, match="unsupported account"):
        asyncio.run(service.process_text("cena 18€", chat_id=3))


def test_bootstrap_rejects_default_account_missing_from_notion(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "default_account", "Revolut")
    service = FinanceService(gateway=cast(Any, FakeGateway()))

    with pytest.raises(ValueError, match="DEFAULT_ACCOUNT 'Revolut'"):
        service.bootstrap()


def test_default_account_is_flagged_only_when_used(monkeypatch: MonkeyPatch) -> None:
    set_taxonomy(_taxonomy())
    monkeypatch.setattr(settings, "default_account", "Hype")
    payloads = [_llm_payload(None), _llm_payload("Contanti")]

    async def fake_extract(text: str) -> dict[str, Any]:
        return payloads.pop(0)

    monkeypatch.setattr("app.finance_service.extract_transaction", fake_extract)
    gateway = FakeGateway()
    service = FinanceService(gateway=cast(Any, gateway))

    asyncio.run(service.process_text("cena 18€", chat_id=10))
    asyncio.run(service.process_text("cena 18€ contanti", chat_id=10))

    assert [tx.account_is_default for tx in gateway.saved] == [True, False]


def test_undo_last_archives_transfer_and_allows_resending(monkeypatch: MonkeyPatch) -> None:
    set_taxonomy(_taxonomy())
    gateway = FakeGateway()
    service = FinanceService(gateway=cast(Any, gateway))

    asyncio.run(service.process_text("prelievo 100€ da Hype", chat_id=20))
    undone = asyncio.run(service.undo_last(20))

    assert [s.tx.account for s in undone] == ["Hype", "Contanti"]
    assert gateway.archived == ["https://notion.test/1", "https://notion.test/2"]
    # Una sola volta: niente da annullare la seconda volta.
    assert asyncio.run(service.undo_last(20)) == []
    # Dopo l'annullamento lo stesso messaggio non e piu considerato un duplicato.
    again = asyncio.run(service.process_text("prelievo 100€ da Hype", chat_id=20))
    assert not again.duplicate
    assert len(gateway.saved) == 4


def test_undo_last_is_per_chat_and_ignores_duplicates(monkeypatch: MonkeyPatch) -> None:
    set_taxonomy(_taxonomy())
    gateway = FakeGateway()
    service = FinanceService(gateway=cast(Any, gateway))

    asyncio.run(service.process_text("prelievo 100€ da Hype", chat_id=30))
    asyncio.run(service.process_text("prelievo 50€ da Hype", chat_id=31))
    asyncio.run(service.process_text("prelievo 100€ da Hype", chat_id=30))  # duplicato

    assert asyncio.run(service.undo_last(99)) == []
    undone = asyncio.run(service.undo_last(30))
    assert [s.tx.amount for s in undone] == [Decimal("100"), Decimal("100")]
    assert gateway.archived == ["https://notion.test/1", "https://notion.test/2"]


def test_undo_last_failure_can_be_retried(monkeypatch: MonkeyPatch) -> None:
    set_taxonomy(_taxonomy())
    gateway = FakeGateway()
    service = FinanceService(gateway=cast(Any, gateway))
    asyncio.run(service.process_text("prelievo 100€ da Hype", chat_id=40))

    gateway.fail_archive = True
    with pytest.raises(RuntimeError):
        asyncio.run(service.undo_last(40))

    gateway.fail_archive = False
    assert len(asyncio.run(service.undo_last(40))) == 2


def test_check_model_shutdown_sets_warning(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_model", "gpt-5-mini")
    monkeypatch.setattr(
        "app.finance_service.fetch_shutdown_date",
        lambda model, api_key, client: dt.date(2026, 12, 11),
    )
    service = FinanceService(gateway=cast(Any, FakeGateway()))

    service.check_model_shutdown(today=dt.date(2026, 11, 11))

    assert service.model_warning is not None
    assert "gpt-5-mini" in service.model_warning
    assert "11/12/2026" in service.model_warning


def test_check_model_shutdown_never_blocks_startup(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_model", "gpt-6-luna")

    def boom(model: str, api_key: str, client: Any) -> dt.date:
        raise RuntimeError("rete giu")

    monkeypatch.setattr("app.finance_service.fetch_shutdown_date", boom)
    service = FinanceService(gateway=cast(Any, FakeGateway()))

    service.check_model_shutdown()

    assert service.model_warning is None


def test_check_model_shutdown_skips_non_openai_models(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_model", "groq/llama-3.1-8b-instant")
    called: list[str] = []
    monkeypatch.setattr(
        "app.finance_service.fetch_shutdown_date",
        lambda model, api_key, client: called.append(model),
    )
    service = FinanceService(gateway=cast(Any, FakeGateway()))

    service.check_model_shutdown()

    assert called == []
    assert service.model_warning is None
