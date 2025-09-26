# app/normalizer.py
from __future__ import annotations

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
    ({"risparmio car"}, "Risparmio Car"),
    ({"risparmio"}, "Risparmio"),
    ({"other income"}, "Other Income"),
]


def normalize_account(acc: str | None, allowed: set[str]) -> str | None:
    """
    Tollerante a None. Applica sinonimi e ritorna:
    - l'alias normalizzato se è consentito
    - la stringa originale se è consentita
    - None se non deducibile/consentito
    """
    if not acc:
        return None
    key = acc.strip().lower()
    alias = ACCOUNT_SYNONYMS.get(key)
    if alias and alias in allowed:
        return alias
    if acc.strip() in allowed:
        return acc.strip()
    return None


def _infer_outcome_from_desc(description: str, allowed: set[str]) -> str | None:
    text = _strip_accents_lower(description)
    # Eating out
    if any(tok in text for tok in EATING_OUT_HINTS):
        if "Eating Out and Takeway" in allowed:
            return "Eating Out and Takeway"
    # Altri mapping keyword -> categoria
    for keywords, cat in KEYWORD_TO_OUTCOME:
        if any(k in text for k in keywords) and cat in allowed:
            return cat
    return None


def _infer_income_from_desc(description: str, allowed: set[str]) -> str | None:
    text = _strip_accents_lower(description)
    for keywords, cat in KEYWORD_TO_INCOME:
        if any(k in text for k in keywords) and (not allowed or cat in allowed):
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
    for c in outcome_list or []:
        key = c.strip().lower()
        c2 = OUTCOME_SYNONYMS.get(key, c.strip())
        if c2 in allowed:
            fixed.append(c2)

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
    out = [c for c in (outcome or []) if c in allowed_outcome]
    inc = [c for c in (income or []) if c in allowed_income]

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
