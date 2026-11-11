import datetime as dt
from typing import Any

import httpx
import pytest

from app.model_lifecycle import fetch_shutdown_date, openai_model_name, shutdown_warning

TODAY = dt.date(2026, 11, 11)


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-6-luna", "gpt-6-luna"),
        ("openai/gpt-6-luna", "gpt-6-luna"),
        ("OpenAI/gpt-5-mini", "gpt-5-mini"),
        ("groq/llama-3.1-8b-instant", None),
    ],
)
def test_openai_model_name(model: str, expected: str | None) -> None:
    assert openai_model_name(model) == expected


def _client(body: Any, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models/gpt-5-mini"
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"id": "gpt-5-mini", "shutdown_date": "2026-12-11"}, dt.date(2026, 12, 11)),
        ({"id": "gpt-5-mini", "shutdown_date": None}, None),
        ({"id": "gpt-5-mini"}, None),
    ],
)
def test_fetch_shutdown_date(body: dict[str, Any], expected: dt.date | None) -> None:
    assert fetch_shutdown_date("gpt-5-mini", "sk-test", _client(body)) == expected


def test_fetch_shutdown_date_raises_on_http_error() -> None:
    with pytest.raises(httpx.HTTPStatusError):
        fetch_shutdown_date("gpt-5-mini", "sk-test", _client({"error": "x"}, status=401))


def test_no_warning_without_date_or_when_far_away() -> None:
    assert shutdown_warning("gpt-6-luna", None, TODAY) is None
    assert shutdown_warning("gpt-6-luna", dt.date(2027, 1, 11), TODAY) is None  # 61 giorni


def test_warning_within_sixty_days() -> None:
    msg = shutdown_warning("gpt-5-mini", dt.date(2027, 1, 10), TODAY)  # 60 giorni
    assert msg is not None
    assert "10/01/2027" in msg
    assert "tra 60 giorni" in msg


def test_warning_after_shutdown() -> None:
    msg = shutdown_warning("gpt-5-mini", dt.date(2026, 11, 1), TODAY)
    assert msg is not None
    assert "ha spento" in msg
