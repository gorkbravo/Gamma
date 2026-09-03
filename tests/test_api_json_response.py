from __future__ import annotations

import json
import logging
import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from src.api.json_response import GammaJSONResponse


def _app() -> FastAPI:
    app = FastAPI(default_response_class=GammaJSONResponse)

    # No return annotation: an annotated route is serialized by Pydantic first,
    # which nulls non-finite floats on its own and would never reach the encoder
    # this class exists to protect.
    @app.get("/finite")
    def finite():
        return {"value": 1.5, "nested": {"items": [1.0, 2.0]}}

    @app.get("/non-finite")
    def non_finite():
        return {
            "sections": ["equities", "macro"],
            "equities": {"nodes": [{"symbol": "AAA", "annual_volatility": float("nan")}]},
            "macro": {"latest": 4.39},
        }

    return app


def test_a_well_formed_payload_is_unchanged():
    with TestClient(_app()) as client:
        response = client.get("/finite")

    assert response.status_code == 200
    assert response.json() == {"value": 1.5, "nested": {"items": [1.0, 2.0]}}


def test_a_non_finite_value_degrades_to_null_instead_of_failing_the_response(caplog):
    """One uncomputable number must not take a whole workspace down.

    Starlette encodes with allow_nan=False, so a single NaN anywhere in a
    payload answered 500 and the client lost every healthy section with it.
    """

    with caplog.at_level(logging.WARNING):
        with TestClient(_app()) as client:
            response = client.get("/non-finite")

    assert response.status_code == 200
    payload = response.json()
    assert payload["equities"]["nodes"][0]["annual_volatility"] is None
    assert payload["equities"]["nodes"][0]["symbol"] == "AAA"
    assert payload["macro"] == {"latest": 4.39}
    assert payload["sections"] == ["equities", "macro"]


def test_the_replacement_is_logged_with_the_path_that_produced_it(caplog):
    """Nulling silently would hide the analytics bug behind it."""

    with caplog.at_level(logging.WARNING):
        with TestClient(_app()) as client:
            client.get("/non-finite")

    messages = [record.getMessage() for record in caplog.records if record.name == "src.api.json_response"]
    assert any("$.equities.nodes[0].annual_volatility" in message for message in messages)


def test_the_default_response_class_would_fail_the_whole_reply():
    """The behaviour this class replaces, pinned so the guard is not mistaken
    for something Starlette already does."""

    app = FastAPI()

    @app.get("/non-finite")
    def non_finite():
        return {"v": float("nan")}

    assert JSONResponse is not GammaJSONResponse
    with pytest.raises(ValueError, match="not JSON compliant"):
        with TestClient(app) as client:
            client.get("/non-finite")


def test_infinity_is_replaced_as_well_as_nan():
    rendered = GammaJSONResponse(content={"a": math.inf, "b": -math.inf, "c": 2.0}).body

    assert json.loads(rendered) == {"a": None, "b": None, "c": 2.0}
