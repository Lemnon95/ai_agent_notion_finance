from datetime import date
from decimal import Decimal

from app.idempotency import IdempotencyStore, make_plan_key
from app.models import NotionTx


def _tx(description: str = "caffe") -> NotionTx:
    return NotionTx(
        description=description,
        amount=Decimal("1.20"),
        date=date.today(),
        account="Hype",
        outcome_categories=["Eating Out and Takeway"],
    )


def test_idempotency_store_returns_recent_record() -> None:
    store = IdempotencyStore[str](ttl_seconds=60)
    store.set("key", "value")

    assert store.get("key") == "value"


def test_plan_key_changes_by_chat_and_payload() -> None:
    first = make_plan_key(1, [_tx()])
    same = make_plan_key(1, [_tx()])
    different_chat = make_plan_key(2, [_tx()])
    different_payload = make_plan_key(1, [_tx("cappuccino")])

    assert first == same
    assert first != different_chat
    assert first != different_payload
