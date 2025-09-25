# app/ux.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

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
    # Alcune categorie comuni (espandibili)
    "Supermarket": "🛒",
    "Eating Out and Takeway": "🍽️",
    "Benzina": "⛽",
    "Travel": "✈️",
    "Casa": "🏠",
    "Subscriptions": "🔁",
    "Savings": "🏦",
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


@dataclass
class TxnView:
    description: str
    amount: Decimal  # NotionTx.amount è Decimal
    account: str | None
    currency: str
    date: date
    notion_url: str | None = None
    category: str | None = None

    def confirmation_message(self) -> str:
        parts = [
            f"{EMOJI['ok']} *Spesa registrata*",
            f"{EMOJI['desc']} *{self.description}*",
            f"{emoji_for_account(self.account)} {self.account or '—'}",
            f"{EMOJI['amount']} {fmt_amount_eur(self.amount)}",
            f"{EMOJI['date']} {fmt_date(self.date)}",
        ]
        if self.category:
            parts.insert(2, f"{emoji_for_category(self.category)} {self.category}")

        if self.notion_url:
            parts.append(f"{EMOJI['link']} [Apri in Notion]({self.notion_url})")

        return "\n".join(parts)


def friendly_parse_error(example: str = "10€ benzina con Hype ieri") -> str:
    return (
        f"{EMOJI['err']} *Non ho capito bene.*\n"
        f"Puoi riscrivere includendo *importo* e *account*?\n\n"
        f"Esempio: _{example}_"
    )
