import unicodedata
from collections.abc import Iterable

ACCOUNT_SYNONYMS = {
    "hype next": "Hype",
    "hype card": "Hype",
    "contante": "Contanti",
    "cash": "Contanti",
}

OUTCOME_SYNONYMS = {
    "other": "Other Outcome",
    "altro": "Other Outcome",
}

EATING_OUT_HINTS = {
    "caffe",
    "caffè",
    "espresso",
    "cappuccino",
    "cornetto",
    "brioche",
    "bar",
    "colazione",
}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalize_account(acc: str, allowed: set[str]) -> str:
    key = acc.strip().lower()
    acc2 = ACCOUNT_SYNONYMS.get(key, acc.strip())
    return acc2 if acc2 in allowed else acc.strip()


def _infer_outcome_from_desc(description: str) -> str | None:
    text = _strip_accents(description.lower())
    if any(tok in text for tok in EATING_OUT_HINTS):
        return "Eating Out and Takeway"
    return None


def normalize_outcome(
    outcome_list: Iterable[str] | None, description: str, allowed: set[str]
) -> list[str]:
    fixed: list[str] = []
    # 1) Mappa sinonimi e tieni solo consentiti
    for c in outcome_list or []:
        key = c.strip().lower()
        c2 = OUTCOME_SYNONYMS.get(key, c.strip())
        if c2 in allowed:
            fixed.append(c2)

    # 2) Se vuoto, prova inferenza dalla descrizione
    if not fixed:
        inferred = _infer_outcome_from_desc(description)
        if inferred and inferred in allowed:
            fixed.append(inferred)

    # 3) Ultima spiaggia
    if not fixed and "Other Outcome" in allowed:
        fixed.append("Other Outcome")

    # dedup preservando l’ordine
    seen = set()
    deduped = []
    for x in fixed:
        if x not in seen:
            seen.add(x)
            deduped.append(x)
    return deduped
