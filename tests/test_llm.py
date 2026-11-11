import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from pytest import MonkeyPatch

from app import llm
from app.llm import _model_specific_kwargs
from app.settings import settings
from app.taxonomy import Taxonomy, set_taxonomy


@pytest.mark.parametrize("model", ["gpt-6-luna", "openai/gpt-6-luna", "GPT-6-LUNA"])
def test_gpt6_uses_no_reasoning_and_no_temperature(model: str) -> None:
    kwargs = _model_specific_kwargs(model)
    assert kwargs == {"extra_body": {"reasoning_effort": "none"}}


@pytest.mark.parametrize("model", ["gpt-5-mini", "openai/gpt-5-mini"])
def test_gpt5_keeps_minimal_reasoning(model: str) -> None:
    kwargs = _model_specific_kwargs(model)
    assert kwargs == {"extra_body": {"reasoning_effort": "minimal", "verbosity": "low"}}


@pytest.mark.parametrize("model", ["gpt-4o-mini-2024-07-18", "groq/llama-3.1-8b-instant"])
def test_other_models_use_zero_temperature(model: str) -> None:
    assert _model_specific_kwargs(model) == {"temperature": 0.0}


# --- Schema, prompt ed estrazione (nessuna chiamata di rete) ---


def _set_test_taxonomy() -> None:
    set_taxonomy(
        Taxonomy(
            accounts=["Hype", "Revolut"],
            outcome_categories=["Needs", "Supermarket"],
            income_categories=["Salary"],
        )
    )


def test_schema_is_strict_and_requires_every_property() -> None:
    _set_test_taxonomy()
    js = llm._build_schema()["json_schema"]
    schema = js["schema"]

    assert js["strict"] is True
    assert schema["additionalProperties"] is False
    # OpenAI rifiuta uno schema strict se una proprieta non e in required.
    assert set(schema["required"]) == set(schema["properties"])


def test_schema_enums_come_from_taxonomy_and_account_is_nullable() -> None:
    _set_test_taxonomy()
    props = llm._build_schema()["json_schema"]["schema"]["properties"]

    assert props["account"]["enum"] == ["Hype", "Revolut", None]
    assert "null" in props["account"]["type"]
    assert props["outcome_categories"]["items"]["enum"] == ["Needs", "Supermarket"]
    assert props["income_categories"]["items"]["enum"] == ["Salary"]


def test_system_prompt_lists_accounts_and_asks_null_for_missing_account() -> None:
    _set_test_taxonomy()
    prompt = llm._build_system_prompt()

    assert "['Hype', 'Revolut']" in prompt
    assert "NON indica un account, usa null" in prompt


def _fake_response(content: str) -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_extract_transaction_parses_fenced_json_and_sends_model_kwargs(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_test_taxonomy()
    monkeypatch.setattr(settings, "llm_model", "gpt-6-luna")
    calls: list[dict[str, Any]] = []
    payload = {
        "description": "stipendio",
        "amount": 1820,
        "currency": "EUR",
        "account": "Revolut",
        "date": "2026-11-11",
        "outcome_categories": ["Needs"],  # sbagliato: lo stipendio e un'entrata
        "income_categories": ["Salary"],
        "notes": None,
    }

    async def fake_acompletion(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return _fake_response("```json\n" + json.dumps(payload) + "\n```")

    monkeypatch.setattr(llm, "acompletion", fake_acompletion)

    data = asyncio.run(llm.extract_transaction("stipendio 1820€ su Revolut"))

    assert data["account"] == "Revolut"
    # XOR applicato: resta solo una delle due liste.
    assert not (data["outcome_categories"] and data["income_categories"])
    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-6-luna"
    assert calls[0]["extra_body"] == {"reasoning_effort": "none"}
    assert "temperature" not in calls[0]
    assert calls[0]["response_format"]["json_schema"]["strict"] is True


def test_extract_transaction_retries_once_on_invalid_json(monkeypatch: MonkeyPatch) -> None:
    _set_test_taxonomy()
    responses = [
        "non e json",
        json.dumps(
            {
                "description": "cena",
                "amount": 18,
                "currency": "EUR",
                "account": None,
                "date": "2026-11-11",
                "outcome_categories": ["Needs"],
                "income_categories": None,
                "notes": None,
            }
        ),
    ]
    seen: list[list[dict[str, str]]] = []

    async def fake_acompletion(**kwargs: Any) -> Any:
        seen.append(kwargs["messages"])
        return _fake_response(responses[len(seen) - 1])

    monkeypatch.setattr(llm, "acompletion", fake_acompletion)

    data = asyncio.run(llm.extract_transaction("cena 18€"))

    assert data["account"] is None
    assert len(seen) == 2
    assert seen[1][1]["content"].endswith("Rispondi SOLO con JSON valido.")
