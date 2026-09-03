"""Diagnosability of Copilot provider failures.

GUA-20260903-2: a tool continuation failed with a bare status code, so the audit
could establish where the exchange died but not why. These cover the fields that
separate a malformed replayed item from a model or account problem.
"""

from __future__ import annotations

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError

from src.models.copilot import CopilotToolTrace
from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider


def _status_error(*, status: int, message: str, code: str | None, param: str | None) -> APIStatusError:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(
        status,
        request=request,
        json={"error": {"message": message, "code": code, "param": param, "type": "invalid_request_error"}},
    )
    return APIStatusError(message, response=response, body={"code": code, "param": param})


def test_status_error_surfaces_code_and_param_so_the_rejected_item_is_identifiable():
    exc = _status_error(status=400, message="Invalid value", code="invalid_value", param="input[3]")

    rendered = OpenAIResponsesCopilotProvider._sdk_error_message(exc)

    assert "OpenAI request failed (400)" in rendered
    assert "Invalid value" in rendered
    assert "code=invalid_value" in rendered
    assert "param=input[3]" in rendered


def test_status_error_without_structured_fields_stays_readable():
    exc = _status_error(status=500, message="Server error", code=None, param=None)

    rendered = OpenAIResponsesCopilotProvider._sdk_error_message(exc)

    assert "OpenAI request failed (500)" in rendered
    assert "Server error" in rendered
    assert "[" not in rendered.split("Server error")[-1]


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses")), "timed out"),
        (
            APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/responses")),
            "unreachable",
        ),
    ],
)
def test_transport_failures_keep_their_plain_messages(exc, expected):
    assert expected in OpenAIResponsesCopilotProvider._sdk_error_message(exc)


def test_first_turn_failure_adds_no_continuation_warning():
    warnings = OpenAIResponsesCopilotProvider._turn_failure_warnings(0, [{"type": "message"}], [])

    assert warnings == []


def test_continuation_failure_names_the_turn_and_replayed_state():
    input_items = [
        {"type": "message"},
        {"type": "reasoning"},
        {"type": "function_call"},
        {"type": "function_call_output", "call_id": "call_1"},
    ]
    traces = [
        CopilotToolTrace(
            tool_name="run_options_realized_implied_comparison",
            summary="ran",
            arguments={},
            source_ids=[],
        )
    ]

    warnings = OpenAIResponsesCopilotProvider._turn_failure_warnings(1, input_items, traces)

    assert len(warnings) == 1
    assert "turn 2" in warnings[0]
    assert "4 replayed input items" in warnings[0]
    assert "1 tool results" in warnings[0]
    assert "run_options_realized_implied_comparison" in warnings[0]
    assert "not the prompt" in warnings[0]
