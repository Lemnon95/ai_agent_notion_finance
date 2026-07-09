from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import ExtractedTx
from app.taxonomy import set_taxonomy


@pytest.fixture(autouse=True)
def taxonomy_fixture() -> None:
    set_taxonomy(
        {
            "accounts": ["Hype", "Risparmio"],
            "outcome_categories": ["Wants", "Fun", "Savings", "Risparmio"],
            "income_categories": ["Salary", "Risparmio"],
        }
    )


def test_extracted_tx_accepts_income_transaction() -> None:
    tx = ExtractedTx.model_validate(
        {
            "description": "stipendio",
            "amount": "1820",
            "currency": "eur",
            "account": "Hype",
            "date": date.today().isoformat(),
            "outcome_categories": None,
            "income_categories": ["salary"],
            "notes": None,
        }
    )

    assert tx.amount == Decimal("1820.00")
    assert tx.currency == "EUR"
    assert tx.income_categories == ["Salary"]


def test_extracted_tx_rejects_income_and_outcome_together() -> None:
    with pytest.raises(ValidationError, match="cannot be both income and outcome"):
        ExtractedTx.model_validate(
            {
                "description": "movimento ambiguo",
                "amount": "10",
                "currency": "EUR",
                "account": "Hype",
                "date": date.today().isoformat(),
                "outcome_categories": ["Fun"],
                "income_categories": ["Salary"],
            }
        )
