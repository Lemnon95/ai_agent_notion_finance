# app/ux.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

EMOJI = {
    # Generici
    "ok": "✅",
    "err": "⚠️",
    "info": "ℹ️",
    "desc": "📝",
    "amount": "💶",
    "account": "💳",
    "date": "📅",
    "link": "🔗",
    # Macro
    "Wants": "✨",
    "Needs": "📌",
    "Savings": "🏦",
    # Alcune specifiche comuni (espandibili)
    "Supermarket": "🛒",
    "Eating Out and Takeway": "🍽️",
    "Benzina": "⛽",
    "Travel": "✈️",
    "Casa": "🏠",
    "Subscriptions": "🔁",
    "Learning": "📚",
    "Fun": "🎉",
    "Ballo": "🕺",
    "Gifts & Donations": "🎁",
    "Salute": "🩺",
    "Integratori": "💊",
    "Car": "🚗",
    "Barbiere": "💈",
    "Other Outcome": "📦",
    # Account frequenti
    "Hype": "💳",
    "Revolut": "💳",
    "Contanti": "💵",
    "Poste Italiane": "🏤",
}


def emoji_for_category(cat: str | None) -> str:
    if not cat:
        return "📦"
    return EMOJI.get(cat, "📦")


def emoji_for_account(acc: str | None) -> str:
    if not acc:
        return "💳"
    return EMOJI.get(acc, "💳")


def _to_decimal_2(amount: Decimal | float) -> Decimal:
    """Converte a Decimal e arrotonda a 2 decimali (HALF_UP)."""
    if isinstance(amount, Decimal):
        dec = amount
    else:
        dec = Decimal(str(amount))
    return dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt_amount_eur(amount: Decimal | float) -> str:
    """Formato italiano con due decimali (virgola decimale)."""
    dec = _to_decimal_2(amount)
    s = format(dec, ",.2f")  # es: '1,234.56'
    return f"{s}€".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_date(d: date) -> str:
    """Formato data DD/MM/YYYY."""
    return d.strftime("%d/%m/%Y")


_MD_ESCAPE = "\\`*_[]()~>#+-=|{}.!".replace(".", "")  # tieni il punto fuori


def _escape_md(text: str) -> str:
    """Escape minimale per Markdown (Telegram legacy)."""
    out = []
    for ch in text:
        if ch in _MD_ESCAPE:
            out.append(f"\\{ch}")
        else:
            out.append(ch)
    return "".join(out)


def escape_md(text: str) -> str:
    return _escape_md(text)


def _fmt_categories_line(categories: list[str] | None) -> str | None:
    if not categories:
        return None
    parts = [f"{emoji_for_category(c)} {_escape_md(c)}" for c in categories]
    return " • ".join(parts)


@dataclass
class TxnView:
    description: str
    amount: Decimal  # manteniamo precisione
    account: str | None
    currency: str
    date: date
    notion_url: str | None = None
    categories: list[str] | None = None  # <<— ora supporta 0..n categorie
    kind: Literal["outcome", "income"] = "outcome"
    account_is_default: bool = False

    def confirmation_message(self) -> str:
        title = "Entrata registrata" if self.kind == "income" else "Spesa registrata"
        parts = [
            f"{EMOJI['ok']} *{title}*",
            f"{EMOJI['desc']} *{_escape_md(self.description)}*",
        ]

        cats_line = _fmt_categories_line(self.categories)
        if cats_line:
            parts.append(cats_line)

        parts.extend(
            [
                f"{emoji_for_account(self.account)} "
                f"{_escape_md(self.account) if self.account else '—'}"
                f"{' _(predefinito)_' if self.account_is_default else ''}",
                f"{EMOJI['amount']} {fmt_amount_eur(self.amount)}",
                f"{EMOJI['date']} {fmt_date(self.date)}",
            ]
        )

        if self.notion_url:
            parts.append(f"{EMOJI['link']} [Apri in Notion]({self.notion_url})")

        return "\n".join(parts)


def friendly_parse_error(example: str = "10€ benzina con Hype ieri") -> str:
    return (
        f"{EMOJI['err']} *Non ho capito bene.*\n"
        f"Puoi riscrivere includendo *importo* e *account*?\n\n"
        f"Esempio: _{_escape_md(example)}_"
    )
