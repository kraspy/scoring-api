"""Общие фикстуры и хелперы для pytest."""

from __future__ import annotations

import datetime
import hashlib
import threading
from collections.abc import Callable, Generator
from typing import Any

import pytest

import api


def set_valid_auth(request: dict[str, Any]) -> None:
    if request.get("login") == api.ADMIN_LOGIN:
        request["token"] = hashlib.sha512(
            (
                datetime.datetime.now().strftime("%Y%m%d%H") + api.ADMIN_SALT
            ).encode("utf-8")
        ).hexdigest()
    else:
        msg = (
            request.get("account", "") + request.get("login", "") + api.SALT
        ).encode("utf-8")
        request["token"] = hashlib.sha512(msg).hexdigest()


@pytest.fixture
def interests_request_factory() -> Callable[[dict[str, Any]], dict[str, Any]]:
    def _make(arguments: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "account": "horns&hoofs",
            "login": "h&f",
            "method": "clients_interests",
            "arguments": arguments,
        }
        set_valid_auth(body)
        return body

    return _make


@pytest.fixture
def online_score_request_factory() -> Callable[[dict[str, Any]], dict[str, Any]]:
    def _make(arguments: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "account": "horns&hoofs",
            "login": "h&f",
            "method": "online_score",
            "arguments": arguments,
        }
        set_valid_auth(body)
        return body

    return _make


@pytest.fixture
def scoring_server() -> Generator[api.ScoringHTTPServer, None, None]:
    """ScoringHTTPServer на случайном порту; останавливается после теста."""
    server = api.ScoringHTTPServer(("127.0.0.1", 0), api.MainHTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
