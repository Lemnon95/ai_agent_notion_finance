from datetime import date
from decimal import Decimal

from app.ux import TxnView


def test_income_confirmation_uses_income_title() -> None:
    message = TxnView(
        description="stipendio",
        amount=Decimal("1820"),
        account="Hype",
        currency="EUR",
        date=date(2026, 7, 9),
        categories=["Salary"],
        kind="income",
    ).confirmation_message()

    assert "Entrata registrata" in message
    assert "Spesa registrata" not in message


def test_confirmation_escapes_dynamic_markdown_fields() -> None:
    message = TxnView(
        description="test _speciale_",
        amount=Decimal("10"),
        account="Account_Test",
        currency="EUR",
        date=date(2026, 7, 9),
        categories=["Fun_Test"],
    ).confirmation_message()

    assert "test \\_speciale\\_" in message
    assert "Account\\_Test" in message
    assert "Fun\\_Test" in message


def test_confirmation_marks_default_account() -> None:
    from datetime import date
    from decimal import Decimal

    from app.ux import TxnView

    def view(account_is_default: bool) -> TxnView:
        return TxnView(
            description="cena",
            amount=Decimal("18"),
            account="Revolut",
            currency="EUR",
            date=date(2026, 11, 11),
            account_is_default=account_is_default,
        )

    assert "_(predefinito)_" in view(True).confirmation_message()
    assert "predefinito" not in view(False).confirmation_message()
