from app.normalizer import enforce_xor_categories, normalize_account, normalize_outcome


def test_normalize_account_matches_allowed_case_insensitive() -> None:
    allowed = {"Hype", "Poste Italiane", "Trade Republic"}

    assert normalize_account("hype", allowed) == "Hype"
    assert normalize_account("poste italiane", allowed) == "Poste Italiane"
    assert normalize_account("trade republic", allowed) == "Trade Republic"


def test_normalize_account_keeps_supported_aliases() -> None:
    assert normalize_account("cash", {"Contanti"}) == "Contanti"
    assert normalize_account("poste", {"Poste Italiane"}) == "Poste Italiane"


def test_enforce_xor_infers_risparmio_income_without_nonexistent_category() -> None:
    outcome, income = enforce_xor_categories(
        description="spostato 200 euro su Risparmio",
        outcome=None,
        income=None,
        allowed_outcome={"Savings", "Risparmio"},
        allowed_income={"Risparmio"},
    )

    assert outcome is None
    assert income == ["Risparmio"]


def test_enforce_xor_prefers_text_income_when_both_sides_are_present() -> None:
    outcome, income = enforce_xor_categories(
        description="prelievo risparmi 250 euro",
        outcome=["Prelievo"],
        income=["Prelievo"],
        allowed_outcome={"Prelievo"},
        allowed_income={"Prelievo"},
    )

    assert outcome is None
    assert income == ["Prelievo"]


def test_normalize_outcome_does_not_match_bar_inside_barbiere() -> None:
    outcome = normalize_outcome(
        outcome_list=None,
        description="barbiere 18 euro contanti",
        allowed={"Eating Out and Takeway", "Barbiere", "Other Outcome"},
    )

    assert outcome == ["Barbiere"]


def test_normalize_outcome_canonicalizes_existing_categories_case_insensitive() -> None:
    outcome = normalize_outcome(
        outcome_list=["wants", "fun"],
        description="comprato videogioco",
        allowed={"Wants", "Fun", "Other Outcome"},
    )

    assert outcome == ["Wants", "Fun"]
