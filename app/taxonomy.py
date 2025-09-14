# app/taxonomy.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Taxonomy:
    accounts: list[str] = field(default_factory=list)
    outcome_categories: list[str] = field(default_factory=list)
    income_categories: list[str] = field(default_factory=list)


# Singleton mutabile importato ovunque
taxonomy = Taxonomy()


def _coerce_iter(x: Any) -> list[str]:
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        return [str(i) for i in x]
    # supporta anche dict/Notion payload già normalizzati altrove
    return [str(x)]


def set_taxonomy(src: dict[str, Any] | Taxonomy) -> None:
    """
    Aggiorna *in place* il singleton `taxonomy` senza riassegnarlo,
    così tutti i moduli che l'hanno importato vedono i nuovi valori.
    Accetta sia un dict (chiavi flessibili) sia un Taxonomy.
    """
    if isinstance(src, Taxonomy):
        accounts = list(src.accounts)
        outcome = list(src.outcome_categories)
        income = list(src.income_categories)
    else:
        # accetta sia chiavi camel-case sia con iniziale maiuscola (dal dump Notion)
        accounts = _coerce_iter(
            src.get("accounts") or src.get("Accounts") or src.get("account") or []
        )
        outcome = _coerce_iter(
            src.get("outcome_categories") or src.get("Outcome") or src.get("outcome") or []
        )
        income = _coerce_iter(
            src.get("income_categories") or src.get("Income") or src.get("income") or []
        )

    # Normalizzazione minima: trim e rimozione vuoti
    accounts = [a.strip() for a in accounts if a and str(a).strip()]
    outcome = [o.strip() for o in outcome if o and str(o).strip()]
    income = [i.strip() for i in income if i and str(i).strip()]

    # MUTAZIONE IN PLACE (no rebind del singleton!)
    taxonomy.accounts[:] = accounts
    taxonomy.outcome_categories[:] = outcome
    taxonomy.income_categories[:] = income


def is_taxonomy_loaded() -> bool:
    return bool(taxonomy.accounts and taxonomy.outcome_categories and taxonomy.income_categories)
