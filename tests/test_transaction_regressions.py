import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from pytest import MonkeyPatch

import app.rule_parser as rule_parser
from app.rule_parser import parse_with_rules
from app.taxonomy import Taxonomy

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "transaction_regressions.json"


def _load_fixture() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def _str_list(value: object) -> list[str]:
    assert isinstance(value, list)
    return [str(item) for item in value]


def _taxonomy(raw: object) -> Taxonomy:
    assert isinstance(raw, dict)
    return Taxonomy(
        accounts=_str_list(raw["accounts"]),
        outcome_categories=_str_list(raw["outcome_categories"]),
        income_categories=_str_list(raw["income_categories"]),
    )


FIXTURE = _load_fixture()
CASES = cast(list[dict[str, object]], FIXTURE["cases"])
CASE_IDS = [str(case["id"]) for case in CASES]


def test_regression_fixture_has_unique_ids() -> None:
    assert len(CASE_IDS) == len(set(CASE_IDS))


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_real_style_transaction_regressions(
    case: dict[str, object],
    monkeypatch: MonkeyPatch,
) -> None:
    today = dt.date.fromisoformat(str(FIXTURE["today"]))
    monkeypatch.setattr(rule_parser, "_today", lambda: today)

    result = parse_with_rules(str(case["text"]), _taxonomy(FIXTURE["taxonomy"]))
    expected = case["expected"]

    if expected is None:
        assert result is None
        return

    assert result is not None
    assert isinstance(expected, dict)
    assert result.kind == expected["kind"]

    expected_transactions = cast(list[dict[str, object]], expected["transactions"])
    assert len(result.transactions) == len(expected_transactions)

    for tx, expected_tx in zip(result.transactions, expected_transactions, strict=True):
        assert tx.amount == Decimal(str(expected_tx["amount"]))
        assert tx.date == dt.date.fromisoformat(str(expected_tx["date"]))
        assert tx.account == expected_tx["account"]
        assert tx.outcome_categories == cast(list[str] | None, expected_tx["outcome_categories"])
        assert tx.income_categories == cast(list[str] | None, expected_tx["income_categories"])
