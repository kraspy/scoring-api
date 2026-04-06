"""Юнит-тесты маршрутизации и `method_handler` без HTTP и БД."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import api
from conftest import set_valid_auth

pytestmark = pytest.mark.unit


def test_method_handler_empty_body_invalid() -> None:
    response, code = api.method_handler({"body": {}, "headers": {}}, {})
    assert code == api.INVALID_REQUEST
    assert "error" in response


def test_method_handler_forbidden_bad_token() -> None:
    body: dict = {
        "account": "horns&hoofs",
        "login": "h&f",
        "method": "online_score",
        "arguments": {"phone": "79175002040", "email": "x@y.ru"},
        "token": "wrong",
    }
    response, code = api.method_handler({"body": body, "headers": {}}, {})
    assert code == api.FORBIDDEN
    assert response.get("error") == "Forbidden"


def test_method_handler_unknown_method() -> None:
    body: dict = {
        "account": "horns&hoofs",
        "login": "h&f",
        "method": "unknown_method_xyz",
        "arguments": {},
    }
    set_valid_auth(body)
    response, code = api.method_handler({"body": body, "headers": {}}, {})
    assert code == api.INVALID_REQUEST
    assert "не найден" in response.get("error", "")


def test_method_handler_online_score_ok_sets_ctx() -> None:
    body: dict = {
        "account": "horns&hoofs",
        "login": "h&f",
        "method": "online_score",
        "arguments": {"phone": "79175002040", "email": "x@y.ru"},
    }
    set_valid_auth(body)
    ctx: dict = {}
    response, code = api.method_handler({"body": body, "headers": {}}, ctx)
    assert code == api.OK
    assert response.get("score") == 3.0
    assert sorted(ctx.get("has", [])) == ["email", "phone"]


def test_method_handler_online_score_admin_always_42() -> None:
    body: dict = {
        "account": "horns&hoofs",
        "login": api.ADMIN_LOGIN,
        "method": "online_score",
        "arguments": {"phone": "79175002040", "email": "x@y.ru"},
    }
    set_valid_auth(body)
    response, code = api.method_handler({"body": body, "headers": {}}, {})
    assert code == api.OK
    assert response.get("score") == 42


@patch("scoring.random.sample", return_value=["books", "music"])
def test_method_handler_clients_interests_without_store(_mock_sample) -> None:
    body: dict = {
        "account": "horns&hoofs",
        "login": "h&f",
        "method": "clients_interests",
        "arguments": {"client_ids": [7, 8]},
    }
    set_valid_auth(body)
    ctx: dict = {}
    response, code = api.method_handler({"body": body, "headers": {}}, ctx)
    assert code == api.OK
    assert response["7"] == ["books", "music"]
    assert response["8"] == ["books", "music"]
    assert ctx.get("nclients") == 2


def test_method_handler_online_score_invalid_arguments() -> None:
    body: dict = {
        "account": "horns&hoofs",
        "login": "h&f",
        "method": "online_score",
        "arguments": {"phone": "79175002040"},
    }
    set_valid_auth(body)
    response, code = api.method_handler({"body": body, "headers": {}}, {})
    assert code == api.INVALID_REQUEST
    assert "error" in response
