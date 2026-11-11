import datetime as dt
from decimal import Decimal
from typing import Any

import pytest
from pytest import MonkeyPatch

from app import notion_gateway
from app.models import NotionTx
from app.notion_gateway import NotionGateway

DB_IDS = {"Account": "db-acc", "Outcome": "db-out", "Income": "db-inc"}


def _schema() -> dict[str, Any]:
    props: dict[str, Any] = {
        "Name": {"type": "title"},
        "Amount": {"type": "number"},
        "Date": {"type": "date"},
    }
    for name, db_id in DB_IDS.items():
        props[name] = {"type": "relation", "relation": {"database_id": db_id}}
    return props


def _page(page_id: str, title: str) -> dict[str, Any]:
    return {
        "id": page_id,
        "properties": {"Name": {"type": "title", "title": [{"plain_text": title}]}},
    }


class FakeDatabases:
    def __init__(self, props: dict[str, Any], pages: dict[str, list[dict[str, Any]]]) -> None:
        self.props = props
        self.pages = pages
        self.queries: list[dict[str, Any]] = []

    def retrieve(self, db_id: str) -> dict[str, Any]:
        return {"properties": self.props}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.queries.append(kwargs)
        pages = self.pages[kwargs["database_id"]]
        flt = kwargs.get("filter")
        if flt:
            name = flt["title"]["equals"]
            hits = [p for p in pages if NotionGateway._extract_title(p) == name]
            return {"results": hits[:1], "has_more": False}
        # Paginazione a blocchi di 2 per esercitare il cursore.
        start = int(kwargs.get("start_cursor") or 0)
        more = start + 2 < len(pages)
        return {
            "results": pages[start : start + 2],
            "has_more": more,
            "next_cursor": str(start + 2) if more else None,
        }


class FakePages:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> dict[str, Any]:
        self.created.append(kwargs)
        return {"id": "new-page", "url": "https://notion.test/new-page"}


class FakeClient:
    def __init__(self, props: dict[str, Any], pages: dict[str, list[dict[str, Any]]]) -> None:
        self.databases = FakeDatabases(props, pages)
        self.pages = FakePages()


def _gateway(
    monkeypatch: MonkeyPatch,
    props: dict[str, Any] | None = None,
    pages: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[NotionGateway, FakeClient]:
    client = FakeClient(
        _schema() if props is None else props,
        pages
        or {
            "db-acc": [
                _page("acc-hype", "Hype"),
                _page("acc-rev", "Revolut"),
                _page("acc-blank", "  "),
                _page("acc-hype-dup", "Hype"),
                _page("acc-cash", "Contanti"),
            ],
            "db-out": [_page("out-needs", "Needs"), _page("out-super", "Supermarket")],
            "db-inc": [_page("inc-salary", "Salary")],
        },
    )
    monkeypatch.setattr(notion_gateway, "Client", lambda auth: client)
    return NotionGateway(), client


def test_read_taxonomy_paginates_dedups_and_skips_blank_titles(monkeypatch: MonkeyPatch) -> None:
    gateway, _ = _gateway(monkeypatch)

    tax = gateway.read_taxonomy()

    assert tax.accounts == ["Hype", "Revolut", "Contanti"]
    assert tax.outcome_categories == ["Needs", "Supermarket"]
    assert tax.income_categories == ["Salary"]


def test_verify_schema_accepts_minimal_schema(monkeypatch: MonkeyPatch) -> None:
    gateway, _ = _gateway(monkeypatch)
    gateway.verify_schema()


def test_verify_schema_reports_missing_and_wrong_types(monkeypatch: MonkeyPatch) -> None:
    props = _schema()
    del props["Date"]
    props["Amount"] = {"type": "rich_text"}
    props["Income"] = {"type": "select"}
    gateway, _ = _gateway(monkeypatch, props=props)

    with pytest.raises(ValueError) as exc:
        gateway.verify_schema()

    msg = str(exc.value)
    assert "Missing property: 'Date'" in msg
    assert "'Amount' has type 'rich_text', expected 'number'" in msg
    assert "'Income' must be relation" in msg


def _tx(**overrides: Any) -> NotionTx:
    data: dict[str, Any] = {
        "description": "spesa supermercato",
        "amount": Decimal("27.90"),
        "date": dt.date(2026, 11, 11),
        "account": "Hype",
        "outcome_categories": ["Needs", "Supermarket"],
    }
    data.update(overrides)
    return NotionTx(**data)


def test_save_transaction_builds_payload_with_cached_relation_ids(monkeypatch: MonkeyPatch) -> None:
    gateway, client = _gateway(monkeypatch)
    gateway.read_taxonomy()  # popola la cache titolo -> id, come al bootstrap
    queries_before = len(client.databases.queries)

    url = gateway.save_transaction(_tx())

    assert url == "https://notion.test/new-page"
    assert len(client.databases.queries) == queries_before  # nessuna query: id dalla cache
    created = client.pages.created[0]
    assert created["parent"] == {"database_id": "test"}
    props = created["properties"]
    assert props["Name"]["title"][0]["text"]["content"] == "spesa supermercato"
    assert props["Amount"] == {"number": 27.9}
    assert props["Date"] == {"date": {"start": "2026-11-11"}}
    assert props["Account"] == {"relation": [{"id": "acc-hype"}]}
    assert props["Outcome"] == {"relation": [{"id": "out-needs"}, {"id": "out-super"}]}
    assert "Income" not in props
    assert "Notes" not in props


def test_save_transaction_income_with_notes_looks_up_uncached_titles(
    monkeypatch: MonkeyPatch,
) -> None:
    gateway, client = _gateway(monkeypatch)  # senza read_taxonomy: cache vuota

    gateway.save_transaction(
        _tx(
            description="stipendio",
            account="Revolut",
            outcome_categories=None,
            income_categories=["Salary"],
            notes="novembre",
        )
    )

    props = client.pages.created[0]["properties"]
    assert props["Account"] == {"relation": [{"id": "acc-rev"}]}
    assert props["Income"] == {"relation": [{"id": "inc-salary"}]}
    assert "Outcome" not in props
    assert props["Notes"]["rich_text"][0]["text"]["content"] == "novembre"
    assert any("filter" in q for q in client.databases.queries)


def test_save_transaction_fails_when_related_page_is_missing(monkeypatch: MonkeyPatch) -> None:
    gateway, client = _gateway(monkeypatch)

    with pytest.raises(ValueError, match="Missing related pages in 'Account'"):
        gateway.save_transaction(_tx(account="Satispay"))

    assert client.pages.created == []
