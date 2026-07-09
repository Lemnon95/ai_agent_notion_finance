# app/normalizer.py
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

# --- Sinonimi/alias ---

ACCOUNT_SYNONYMS = {
    "hype next": "Hype",
    "hype card": "Hype",
    "contante": "Contanti",
    "cash": "Contanti",
    "poste": "Poste Italiane",
}

OUTCOME_SYNONYMS = {
    "other": "Other Outcome",
    "altro": "Other Outcome",
    "donation": "Gifts & Donations",
    "donazione": "Gifts & Donations",
}

# --- Utilità ---


def _strip_accents_lower(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).lower()


def _contains_keyword(text: str, keyword: str) -> bool:
    normalized_keyword = _strip_accents_lower(keyword.strip())
    if not normalized_keyword:
        return False
    pattern = rf"(?<!\w){re.escape(normalized_keyword)}(?!\w)"
    return re.search(pattern, text) is not None


def _contains_any_keyword(text: str, keywords: Iterable[str]) -> bool:
    return any(_contains_keyword(text, keyword) for keyword in keywords)


def _canon_allowed(value: str, allowed: set[str]) -> str | None:
    canon = {item.casefold(): item for item in allowed}
    return canon.get(value.strip().casefold())


def _iter_values(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values]
    return [str(value) for value in values]


def _canon_many(values: Iterable[str] | None, allowed: set[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in _iter_values(values):
        canon = _canon_allowed(value, allowed)
        if canon and canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out


# Eating out (aggiunti pranzo/cena)
EATING_OUT_HINTS = {
    "caffe",
    "caffè",
    "espresso",
    "cappuccino",
    "cornetto",
    "brioche",
    "bar",
    "colazione",
    "pranzo",
    "cena",
    "pizzeria",
    "ristorante",
    "aperitivo",
}

# Mapping keyword -> categoria outcome
KEYWORD_TO_OUTCOME = [
    (
        {
            "videogioco",
            "videogame",
            "gioco",
            "gaming",
            "steam",
            "epic",
            "epic games",
            "gog",
            "uplay",
            "origin",
            "playstation store",
            "ps store",
            "nintendo eshop",
            "xbox",
            "game pass",
        },
        "Fun",
    ),
    ({"supermercato", "spesa", "esselunga"}, "Supermarket"),
    ({"benzina", "carburante", "gas"}, "Benzina"),
    ({"parrucchiere", "barbiere", "taglio", "barber"}, "Barbiere"),
    ({"palestra", "abbonamento palestra"}, "Palestra"),
    ({"farmacia", "medicina", "medicinale"}, "Salute"),
    ({"spotify", "netflix", "abbonamento", "subscription"}, "Subscriptions"),
    ({"taxi", "treno", "bus", "aereo"}, "Travel"),
    ({"olio motore", "cambio olio", "carrozzeria", "assicurazione auto"}, "Car"),
    ({"regalo", "donazione", "donation"}, "Gifts & Donations"),
    ({"salvadanaio", "winnies"}, "Salvadanaio Winnies"),
]

# Hint per Income
KEYWORD_TO_INCOME = [
    ({"stipendio", "salary"}, "Salary"),
    ({"regalo", "gift"}, "Gifts"),
    ({"prelievo"}, "Prelievo"),
    ({"risparmio"}, "Risparmio"),
    ({"other income"}, "Other Income"),
]


def normalize_account(acc: str | None, allowed: set[str]) -> str | None:
    """
    Tollerante a None. Applica sinonimi e ritorna:
    - l'alias normalizzato se è consentito
    - la stringa ufficiale se coincide case-insensitive con un account consentito
    - None se non deducibile/consentito
    """
    if not acc:
        return None
    key = acc.strip().lower()
    alias = ACCOUNT_SYNONYMS.get(key)
    if alias and alias in allowed:
        return alias
    canon = {a.lower(): a for a in allowed}
    return canon.get(key)


def _infer_outcome_from_desc(description: str, allowed: set[str]) -> str | None:
    text = _strip_accents_lower(description)
    # Eating out
    if _contains_any_keyword(text, EATING_OUT_HINTS):
        if "Eating Out and Takeway" in allowed:
            return "Eating Out and Takeway"
    # Altri mapping keyword -> categoria
    for keywords, cat in KEYWORD_TO_OUTCOME:
        if _contains_any_keyword(text, keywords) and cat in allowed:
            return cat
    return None


def _infer_income_from_desc(description: str, allowed: set[str]) -> str | None:
    text = _strip_accents_lower(description)
    for keywords, cat in KEYWORD_TO_INCOME:
        if _contains_any_keyword(text, keywords) and (not allowed or cat in allowed):
            return cat
    return None


def normalize_outcome(
    outcome_list: Iterable[str] | None,
    description: str,
    allowed: set[str],
) -> list[str] | None:
    """
    Normalizza outcome:
    - mappa sinonimi
    - inferisce da descrizione se vuoto
    - aggiunge 'Other Outcome' SOLO se la frase non sembra 'income'
    """
    fixed: list[str] = []

    # 1) Mappa sinonimi e tieni solo consentiti
    for c in _iter_values(outcome_list):
        key = c.strip().lower()
        c2 = OUTCOME_SYNONYMS.get(key, c.strip())
        canon = _canon_allowed(c2, allowed)
        if canon:
            fixed.append(canon)

    # 2) Se vuoto, prova inferenza dalla descrizione (solo outcome hints)
    if not fixed:
        inferred = _infer_outcome_from_desc(description, allowed)
        if inferred and inferred in allowed:
            fixed.append(inferred)

    # 3) Ultima spiaggia: 'Other Outcome' SOLO se il testo NON sembra income
    looks_income = _infer_income_from_desc(description, set()) is not None
    if not fixed and not looks_income and "Other Outcome" in allowed:
        fixed.append("Other Outcome")

    # Dedup preservando ordine
    seen = set()
    deduped = []
    for x in fixed:
        if x not in seen:
            seen.add(x)
            deduped.append(x)
    return deduped or None


def enforce_xor_categories(
    description: str,
    outcome: Iterable[str] | None,
    income: Iterable[str] | None,
    allowed_outcome: set[str],
    allowed_income: set[str],
) -> tuple[list[str] | None, list[str] | None]:
    """
    Impone XOR tra outcome e income PRIMA del Pydantic.
    Regole:
      - Se solo uno è valorizzato -> ok.
      - Se entrambi -> decide usando gli hint del testo (income batte outcome; se testo è ambiguo:
        preferisci income).
      - Se nessuno -> tenta inferenze (prima outcome; poi income).
    """
    out = _canon_many(outcome, allowed_outcome)
    inc = _canon_many(income, allowed_income)

    text_income = _infer_income_from_desc(description, allowed_income)
    text_outcome = _infer_outcome_from_desc(description, allowed_outcome)

    if out and not inc:
        return out, None
    if inc and not out:
        return None, inc

    if out and inc:
        if text_income:
            return None, inc or [text_income]
        if text_outcome:
            return out or [text_outcome], None
        # Ambiguo: preferisci Income (più esplicito/ raro)
        return None, inc

    # Nessuno presente: prova inferenze
    if text_outcome:
        return [text_outcome], None
    if text_income:
        return None, [text_income]
    return None, None
