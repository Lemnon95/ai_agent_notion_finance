# app/models.py
from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, field_validator, model_validator

from .taxonomy import taxonomy  # runtime, settato al bootstrap

ALLOWED_CURRENCIES = {"EUR"}


def _canon_list(v: object, allowed: list[str]) -> list[str] | None:
    if v is None or v == [] or v == "":
        return None
    if isinstance(v, str):
        items = [s.strip() for s in v.split(",") if s.strip()]
    elif isinstance(v, list):
        items = [str(s).strip() for s in v if str(s).strip()]
    else:
        raise ValueError("categories must be list[str] or comma-separated string")

    canon_map = {c.lower(): c for c in allowed}
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        key = it.lower()
        if key not in canon_map:
            raise ValueError(f"unknown category: {it}")
        val = canon_map[key]
        if val not in seen:
            seen.add(val)
            out.append(val)
    return out or None


class ExtractedTx(BaseModel):
    description: str
    amount: Decimal
    currency: str = "EUR"
    account: str
    date: dt.date

    outcome_categories: list[str] | None = None
    income_categories: list[str] | None = None

    notes: str | None = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount must be > 0")
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @field_validator("currency")
    @classmethod
    def currency_ok(cls, v: str) -> str:
        if v not in ALLOWED_CURRENCIES:
            raise ValueError(f"unsupported currency: {v}")
        return v

    @field_validator("account")
    @classmethod
    def account_ok(cls, v: str) -> str:
        if v not in set(taxonomy.accounts):
            raise ValueError(f"unsupported account: {v}")
        return v

    @field_validator("outcome_categories", mode="before")
    @classmethod
    def canon_outcome(cls, v: object) -> list[str] | None:
        return _canon_list(v, taxonomy.outcome_categories)

    @field_validator("income_categories", mode="before")
    @classmethod
    def canon_income(cls, v: object) -> list[str] | None:
        return _canon_list(v, taxonomy.income_categories)

    @field_validator("date")
    @classmethod
    def date_in_reasonable_range(cls, d: dt.date) -> dt.date:
        today = dt.date.today()
        if d > today.fromordinal(today.toordinal() + 3):
            raise ValueError("date too far in the future")
        if d < today.fromordinal(today.toordinal() - 366):
            raise ValueError("date too far in the past")
        return d

    @model_validator(mode="after")
    def xor_income_outcome(self) -> ExtractedTx:
        has_out = bool(self.outcome_categories)
        has_inc = bool(self.income_categories)
        if has_out and has_inc:
            raise ValueError("a transaction cannot be both income and outcome")
        if not (has_out or has_inc):
            raise ValueError("provide at least one of outcome_categories or income_categories")
        return self


class NotionTx(BaseModel):
    description: str
    amount: Decimal
    date: dt.date
    account: str
    outcome_categories: list[str] | None = None
    income_categories: list[str] | None = None
    notes: str | None = None

    @classmethod
    def from_extracted(cls, e: ExtractedTx) -> NotionTx:
        return cls(
            description=e.description.strip(),
            amount=e.amount,
            date=e.date,
            account=e.account,
            outcome_categories=e.outcome_categories,
            income_categories=e.income_categories,
            notes=e.notes,
        )
