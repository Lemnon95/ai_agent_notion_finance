# app/models.py
from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, field_validator, model_validator

from .taxonomy import taxonomy  # runtime, settato al bootstrap

ALLOWED_CURRENCIES = {"EUR"}


def _canon_list(v: object, allowed: list[str]) -> list[str] | None:
    """
    Accetta list[str] o stringa CSV e:
    - fa strip per elemento
    - canonicalizza in base a allowed (case-insensitive) preservando la grafia ufficiale
    - deduplica preservando l'ordine
    - ritorna None se vuoto
    - solleva ValueError se trova elementi sconosciuti
    """
    if v is None or v == [] or v == "":
        return None

    if isinstance(v, str):
        items = [s.strip() for s in v.split(",") if s.strip()]
    elif isinstance(v, list):
        items = [str(s).strip() for s in v if str(s).strip()]
    else:
        raise ValueError("categories must be list[str] or a comma-separated string")

    canon_map = {c.lower(): c for c in allowed}
    out: list[str] = []
    seen: set[str] = set()

    unknown: list[str] = []
    for it in items:
        key = it.lower()
        if key not in canon_map:
            unknown.append(it)
            continue
        val = canon_map[key]
        if val not in seen:
            seen.add(val)
            out.append(val)

    if unknown:
        # Messaggio chiaro con allowed disponibili
        raise ValueError(f"unknown category: {', '.join(unknown)}")

    return out or None


class ExtractedTx(BaseModel):
    """
    Modello validato dell'estrazione LLM (dopo normalizer).
    - Usa tassonomia dinamica (taxonomy.*) per account/categorie.
    - Arrotonda amount a 2 decimali (ROUND_HALF_UP).
    - Valida currency contro ALLOWED_CURRENCIES.
    - Impone un range ragionevole per la data.
    - Impone XOR tra outcome e income.
    """

    description: str
    amount: Decimal
    currency: str = "EUR"
    account: str
    date: dt.date

    outcome_categories: list[str] | None = None
    income_categories: list[str] | None = None

    notes: str | None = None

    model_config = {
        "extra": "forbid",  # niente campi inattesi dall'LLM
        "str_strip_whitespace": True,  # trim automatico per i campi stringa
    }

    # ---------- Scalar validators ----------

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("description must not be empty")
        return v.strip()

    @field_validator("notes")
    @classmethod
    def notes_trim(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount must be > 0")
        # forza 2 decimali con ROUND_HALF_UP
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @field_validator("currency")
    @classmethod
    def currency_ok(cls, v: str) -> str:
        vv = v.strip().upper()
        if vv not in ALLOWED_CURRENCIES:
            raise ValueError(f"unsupported currency: {v}")
        return vv

    @field_validator("account")
    @classmethod
    def account_ok(cls, v: str) -> str:
        acc = v.strip()
        allowed_accounts = set(taxonomy.accounts)
        if acc not in allowed_accounts:
            raise ValueError(f"unsupported account: {acc}")
        return acc

    @field_validator("date")
    @classmethod
    def date_in_reasonable_range(cls, d: dt.date) -> dt.date:
        today = dt.date.today()
        # tolleranza +3 giorni (timezone/casi limite) e -366 giorni (ultimo anno)
        if d > today.fromordinal(today.toordinal() + 3):
            raise ValueError("date too far in the future")
        if d < today.fromordinal(today.toordinal() - 366):
            raise ValueError("date too far in the past")
        return d

    # ---------- Categories (canonicalization BEFORE) ----------

    @field_validator("outcome_categories", mode="before")
    @classmethod
    def canon_outcome(cls, v: object) -> list[str] | None:
        return _canon_list(v, taxonomy.outcome_categories)

    @field_validator("income_categories", mode="before")
    @classmethod
    def canon_income(cls, v: object) -> list[str] | None:
        return _canon_list(v, taxonomy.income_categories)

    # ---------- Cross-field validation ----------

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
    """
    Payload pronto per l'inserimento su Notion.
    """

    description: str
    amount: Decimal
    date: dt.date
    account: str
    outcome_categories: list[str] | None = None
    income_categories: list[str] | None = None
    notes: str | None = None

    model_config = {
        "extra": "forbid",
        "str_strip_whitespace": True,
    }

    @classmethod
    def from_extracted(cls, e: ExtractedTx) -> NotionTx:
        return cls(
            description=e.description.strip(),
            amount=e.amount,
            date=e.date,
            account=e.account,
            outcome_categories=e.outcome_categories,
            income_categories=e.income_categories,
            notes=(e.notes.strip() if isinstance(e.notes, str) else e.notes),
        )
