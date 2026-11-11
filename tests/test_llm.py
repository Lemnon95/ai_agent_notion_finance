import pytest

from app.llm import _model_specific_kwargs


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
