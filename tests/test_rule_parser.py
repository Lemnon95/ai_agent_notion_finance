import datetime as dt
from decimal import Decimal

from pytest import MonkeyPatch

import app.rule_parser as rule_parser
from app.rule_parser import parse_with_rules
from app.taxonomy import Taxonomy


def _taxonomy() -> Taxonomy:
    return Taxonomy(
        accounts=["Hype", "Contanti", "Risparmio"],
        outcome_categories=[
            "Needs",
            "Savings",
            "Supermarket",
            "Eating Out and Takeway",
            "Barbiere",
            "Prelievo",
            "Risparmio",
            "Integratori",
            "Salute",
            "Other Outcome",
        ],
        income_categories=["Salary", "Gifts", "Prelievo", "Risparmio", "Other Income"],
    )


def test_rules_parse_clear_cash_withdrawal_as_two_transactions() -> None:
    result = parse_with_rules("prelievo 100€ da Hype", _taxonomy())

    assert result is not None
    assert result.kind == "transfer"
    assert len(result.transactions) == 2
    assert result.transactions[0].account == "Hype"
    assert result.transactions[0].outcome_categories == ["Prelievo"]
    assert result.transactions[1].account == "Contanti"
    assert result.transactions[1].income_categories == ["Prelievo"]


def test_rules_parse_simple_expense_with_macro_category() -> None:
    result = parse_with_rules("spesa supermercato 27,90€ con hype oggi", _taxonomy())

    assert result is not None
    assert result.kind == "single"
    tx = result.transactions[0]
    assert tx.account == "Hype"
    assert tx.amount == Decimal("27.90")
    assert tx.outcome_categories == ["Needs", "Supermarket"]


def test_rules_leave_ambiguous_gift_to_llm() -> None:
    assert parse_with_rules("regalo compleanno 25€ contanti", _taxonomy()) is None


def test_rules_parse_explicit_received_gift_as_income() -> None:
    result = parse_with_rules("ho ricevuto un regalo 50€ contanti", _taxonomy())

    assert result is not None
    tx = result.transactions[0]
    assert tx.account == "Contanti"
    assert tx.income_categories == ["Gifts"]


def test_rules_do_not_read_dates_as_amounts() -> None:
    result = parse_with_rules("2026-07-09 spesa supermercato 10 con hype", _taxonomy())

    assert result is not None
    tx = result.transactions[0]
    assert tx.amount == Decimal("10")
    assert tx.date == dt.date(2026, 7, 9)


def test_rules_parse_italian_month_date_without_using_day_as_amount(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(rule_parser, "_today", lambda: dt.date(2026, 7, 9))

    result = parse_with_rules(
        "il 6 luglio ho speso 17.99 con hype per integratore magnesio",
        _taxonomy(),
    )

    assert result is not None
    tx = result.transactions[0]
    assert tx.amount == Decimal("17.99")
    assert tx.date == dt.date(2026, 7, 6)
    assert tx.outcome_categories == ["Needs", "Integratori"]


def test_rules_parse_health_keywords_from_italian_month_date(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(rule_parser, "_today", lambda: dt.date(2026, 7, 9))

    result = parse_with_rules("il 6 luglio ho speso 9.71 per gocce occhi con hype", _taxonomy())

    assert result is not None
    tx = result.transactions[0]
    assert tx.amount == Decimal("9.71")
    assert tx.date == dt.date(2026, 7, 6)
    assert tx.outcome_categories == ["Needs", "Salute"]


def test_rules_leave_other_outcome_fallback_to_llm() -> None:
    assert parse_with_rules("ho speso 12 con hype per una cosa strana", _taxonomy()) is None
