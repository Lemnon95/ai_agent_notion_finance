from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from .models import NotionTx
from .normalizer import (
    ACCOUNT_SYNONYMS,
    enforce_xor_categories,
    normalize_account,
    normalize_outcome,
)
from .taxonomy import Taxonomy


@dataclass
class RuleParseResult:
    transactions: list[NotionTx]
    kind: Literal["single", "transfer"]


_AMOUNT_WITH_CURRENCY_RE = re.compile(r"(?<!\d)(\d+(?:[,.]\d{1,2})?)\s*(?:€|eur|euro)", re.I)
_CENTS_AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:centesimi|cent)", re.I)
_DECIMAL_AMOUNT_RE = re.compile(r"(?<!\d)(\d+[,.]\d{1,2})(?!\d)", re.I)
_AMOUNT_RE = re.compile(r"(?<!\d)(\d+(?:[,.]\d{1,2})?)(?!\d)", re.I)
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_IT_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_MONTHS_IT = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
}
_DAY_WORDS_IT = {"primo": 1}
_IT_MONTH_DATE_RE = re.compile(
    rf"\b(?:(?:il|l')\s*)?(\d{{1,2}}|{'|'.join(_DAY_WORDS_IT)})\s+"
    rf"({'|'.join(_MONTHS_IT)})(?:\s+(\d{{4}}))?\b",
    re.I,
)


def parse_with_rules(text: str, taxonomy: Taxonomy) -> RuleParseResult | None:
    amount = _extract_amount(text)
    if amount is None:
        return None

    date = _extract_date(text)
    accounts = _find_account_mentions(text, taxonomy.accounts)

    transfer = _parse_transfer(text, amount, date, accounts, taxonomy)
    if transfer:
        return transfer

    if len(accounts) != 1:
        return None

    account = normalize_account(accounts[0], set(taxonomy.accounts))
    if not account:
        return None

    income_categories = _income_categories_from_text(text, taxonomy)
    if income_categories:
        outcome_categories = None
    elif _is_ambiguous_gift(text):
        return None
    else:
        outcome_categories = normalize_outcome(
            None,
            text,
            set(taxonomy.outcome_categories),
        )
        outcome_categories, income_categories = enforce_xor_categories(
            description=text,
            outcome=outcome_categories,
            income=None,
            allowed_outcome=set(taxonomy.outcome_categories),
            allowed_income=set(taxonomy.income_categories),
        )
        if outcome_categories == ["Other Outcome"]:
            return None
    if not (outcome_categories or income_categories):
        return None

    tx = NotionTx(
        description=text,
        amount=amount,
        date=date,
        account=account,
        outcome_categories=_with_macro(outcome_categories, taxonomy.outcome_categories),
        income_categories=income_categories,
    )
    return RuleParseResult(transactions=[tx], kind="single")


def _extract_amount(text: str) -> Decimal | None:
    match = _AMOUNT_WITH_CURRENCY_RE.search(text)
    if match:
        return Decimal(match.group(1).replace(",", "."))

    text_without_dates = _strip_dates_from_amount_candidates(text)
    cents_match = _CENTS_AMOUNT_RE.search(text_without_dates)
    if cents_match:
        return Decimal(cents_match.group(1)) / Decimal("100")

    match = _DECIMAL_AMOUNT_RE.search(text_without_dates) or _AMOUNT_RE.search(text_without_dates)
    if not match:
        return None
    return Decimal(match.group(1).replace(",", "."))


def _today() -> dt.date:
    tz = ZoneInfo(os.getenv("TIMEZONE", "Europe/Rome"))
    return dt.datetime.now(tz).date()


def _strip_dates_from_amount_candidates(text: str) -> str:
    without_numeric_dates = _IT_DATE_RE.sub(" ", _ISO_DATE_RE.sub(" ", text))
    return _IT_MONTH_DATE_RE.sub(" ", without_numeric_dates)


def _extract_date(text: str) -> dt.date:
    today = _today()
    normalized = text.casefold()

    if "l'altro ieri" in normalized or "altro ieri" in normalized:
        return today - dt.timedelta(days=2)
    if "ieri" in normalized:
        return today - dt.timedelta(days=1)
    if "domani" in normalized:
        return today + dt.timedelta(days=1)

    iso = _ISO_DATE_RE.search(text)
    if iso:
        return dt.date.fromisoformat(iso.group(1))

    it_date = _IT_DATE_RE.search(text)
    if it_date:
        day, month, year = (int(part) for part in it_date.groups())
        return dt.date(year, month, day)

    it_month_date = _IT_MONTH_DATE_RE.search(normalized)
    if it_month_date:
        day_s, month_s, year_s = it_month_date.groups()
        year = int(year_s) if year_s else today.year
        try:
            return dt.date(year, _MONTHS_IT[month_s], _parse_italian_day(day_s))
        except ValueError:
            return today

    return today


def _find_account_mentions(text: str, accounts: list[str]) -> list[str]:
    found: list[tuple[int, str]] = []
    normalized = _normalize(text)
    for account in accounts:
        pattern = rf"(?<!\w){re.escape(_normalize(account))}(?!\w)"
        match = re.search(pattern, normalized)
        if match:
            found.append((match.start(), account))
    for alias, account in ACCOUNT_SYNONYMS.items():
        if account not in accounts:
            continue
        pattern = rf"(?<!\w){re.escape(_normalize(alias))}(?!\w)"
        match = re.search(pattern, normalized)
        if match:
            found.append((match.start(), account))
    ordered: list[str] = []
    seen: set[str] = set()
    for _, account in sorted(found):
        if account not in seen:
            seen.add(account)
            ordered.append(account)
    return ordered


def _parse_transfer(
    text: str,
    amount: Decimal,
    date: dt.date,
    accounts: list[str],
    taxonomy: Taxonomy,
) -> RuleParseResult | None:
    if not _looks_like_transfer(text):
        return None

    source = _account_with_prefix(text, accounts, ("da", "dal", "dalla"))
    destination: str | None = _account_with_prefix(
        text,
        accounts,
        ("a", "ad", "su", "sul", "sulla", "in", "verso", "nel", "nella"),
    )

    if not source and len(accounts) == 1 and _looks_like_cash_withdrawal(text):
        source = accounts[0]

    if source and not destination and _looks_like_cash_withdrawal(text):
        destination = normalize_account("Contanti", set(taxonomy.accounts))

    if source and destination and source != destination:
        category = _transfer_category(text, source, destination, taxonomy)
        if not category:
            return None
        outcome_category, income_category = category
        return RuleParseResult(
            transactions=[
                NotionTx(
                    description=text,
                    amount=amount,
                    date=date,
                    account=source,
                    outcome_categories=[outcome_category],
                ),
                NotionTx(
                    description=text,
                    amount=amount,
                    date=date,
                    account=destination,
                    income_categories=[income_category],
                ),
            ],
            kind="transfer",
        )

    if destination:
        destination_income_category = _canon(destination, taxonomy.income_categories)
        if destination_income_category:
            return RuleParseResult(
                transactions=[
                    NotionTx(
                        description=text,
                        amount=amount,
                        date=date,
                        account=destination,
                        income_categories=[destination_income_category],
                    )
                ],
                kind="single",
            )

    return None


def _looks_like_transfer(text: str) -> bool:
    return any(
        _contains_word(text, keyword)
        for keyword in (
            "spostato",
            "spostare",
            "trasferito",
            "trasferire",
            "prelevato",
            "prelevare",
            "prelievo",
            "versato",
        )
    )


def _looks_like_cash_withdrawal(text: str) -> bool:
    return any(_contains_word(text, keyword) for keyword in ("prelevato", "prelevare", "prelievo"))


def _income_categories_from_text(text: str, taxonomy: Taxonomy) -> list[str] | None:
    if _contains_word(text, "stipendio"):
        salary = _canon("Salary", taxonomy.income_categories)
        return [salary] if salary else None

    if any(_contains_word(text, word) for word in ("interessi", "entrati", "entrato")):
        other = _canon("Other Income", taxonomy.income_categories)
        return [other] if other else None

    gift_words = ("ricevuto", "ricevuta", "ricevere", "entrata", "accredito", "incassato")
    if _contains_word(text, "regalo") and any(_contains_word(text, word) for word in gift_words):
        gifts = _canon("Gifts", taxonomy.income_categories)
        return [gifts] if gifts else None

    return None


def _is_ambiguous_gift(text: str) -> bool:
    return _contains_word(text, "regalo") and not any(
        _contains_word(text, word)
        for word in ("ricevuto", "ricevuta", "ricevere", "donazione", "donare")
    )


def _account_with_prefix(text: str, accounts: list[str], prefixes: tuple[str, ...]) -> str | None:
    normalized = _normalize(text)
    for account in accounts:
        account_pattern = re.escape(_normalize(account))
        prefix_pattern = "|".join(re.escape(prefix) for prefix in prefixes)
        pattern = rf"(?:^|\s)(?:{prefix_pattern})\s+{account_pattern}(?!\w)"
        if re.search(pattern, normalized):
            return account
    return None


def _transfer_category(
    text: str,
    source: str,
    destination: str,
    taxonomy: Taxonomy,
) -> tuple[str, str] | None:
    if _contains_word(text, "prelievo"):
        preferred = "Prelievo"
    elif _normalize(source) == "risparmio" or _normalize(destination) == "risparmio":
        preferred = "Risparmio"
    else:
        preferred = "Prelievo"

    outcome = _canon(preferred, taxonomy.outcome_categories)
    income = _canon(preferred, taxonomy.income_categories)
    if outcome and income:
        return outcome, income
    return None


def _with_macro(categories: list[str] | None, allowed: list[str]) -> list[str] | None:
    if not categories:
        return None
    first = categories[0]
    if first in {"Wants", "Needs", "Savings"}:
        return categories

    macro = {
        "Eating Out and Takeway": "Wants",
        "Fun": "Wants",
        "Subscriptions": "Wants",
        "Travel": "Wants",
        "Ballo": "Wants",
        "Palestra": "Wants",
        "Vestiario": "Wants",
        "Gifts & Donations": "Wants",
        "Supermarket": "Needs",
        "Bollette": "Needs",
        "Casa": "Needs",
        "Salute": "Needs",
        "Integratori": "Needs",
        "Benzina": "Needs",
        "Car": "Needs",
        "Risparmio": "Savings",
        "Salvadanaio Winnies": "Savings",
    }.get(first)

    if macro and macro in allowed:
        return [macro, *categories]
    return categories


def _contains_word(text: str, word: str) -> bool:
    normalized = _normalize(text)
    return re.search(rf"(?<!\w){re.escape(_normalize(word))}(?!\w)", normalized) is not None


def _canon(value: str, allowed: list[str]) -> str | None:
    canon = {item.casefold(): item for item in allowed}
    return canon.get(value.casefold())


def _parse_italian_day(value: str) -> int:
    word = _DAY_WORDS_IT.get(value.casefold())
    if word is not None:
        return word
    return int(value)


def _normalize(text: str) -> str:
    return " ".join(text.casefold().replace("€", " euro").split())
