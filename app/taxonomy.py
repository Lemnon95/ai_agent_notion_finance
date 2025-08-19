# app/taxonomy.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Taxonomy:
    accounts: list[str]
    outcome_categories: list[str]
    income_categories: list[str]


# stato globale semplice (caricato al bootstrap)
taxonomy = Taxonomy(accounts=[], outcome_categories=[], income_categories=[])


def set_taxonomy(new: Taxonomy) -> None:
    global taxonomy
    taxonomy = new
