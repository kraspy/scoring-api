"""
Функциональные тесты: реальный HTTP POST к ScoringHTTPServer.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

import api
from conftest import set_valid_auth
from db_wrapper import SQLiteClientInterestsStore

pytestmark = pytest.mark.functional


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode("utf-8"))
        return e.code, body


def _method_url(server: api.ScoringHTTPServer) -> str:
    host, port = server.server_address
    return f"http://{host}:{port}/method"


def assert_ok_envelope(outer: dict) -> None:
    assert outer["code"] == api.OK
    assert "response" in outer


def assert_error_envelope(outer: dict, expected_api_code: int) -> None:
    assert outer["code"] == expected_api_code
    assert "error" in outer and outer["error"] is not None


def test_http_bad_json_returns_400(scoring_server) -> None:
    host, port = scoring_server.server_address
    url = f"http://{host}:{port}/method"
    req = urllib.request.Request(
        url,
        data=b"not-json",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=5)
    assert exc_info.value.code == 400


def test_http_unknown_path_404(scoring_server) -> None:
    host, port = scoring_server.server_address
    url = f"http://{host}:{port}/nope"
    code, body = _post_json(url, {"any": 1})
    assert code == 404
    assert "code" in body


def test_http_forbidden_wrong_token(scoring_server) -> None:
    url = _method_url(scoring_server)
    body_req = {
        "account": "horns&hoofs",
        "login": "h&f",
        "method": "online_score",
        "arguments": {"phone": "79175002040", "email": "u@example.com"},
        "token": "invalid",
    }
    code, outer = _post_json(url, body_req)
    assert code == api.FORBIDDEN
    assert_error_envelope(outer, api.FORBIDDEN)


def test_http_invalid_online_score_returns_422(scoring_server) -> None:
    url = _method_url(scoring_server)
    body_req = {
        "account": "horns&hoofs",
        "login": "h&f",
        "method": "online_score",
        "arguments": {"phone": "79175002040"},
    }
    set_valid_auth(body_req)
    code, outer = _post_json(url, body_req)
    assert code == api.INVALID_REQUEST
    assert_error_envelope(outer, api.INVALID_REQUEST)


def test_http_unknown_method_returns_422(scoring_server) -> None:
    url = _method_url(scoring_server)
    body_req = {
        "account": "horns&hoofs",
        "login": "h&f",
        "method": "not_a_real_method",
        "arguments": {},
    }
    set_valid_auth(body_req)
    code, outer = _post_json(url, body_req)
    assert code == api.INVALID_REQUEST
    assert_error_envelope(outer, api.INVALID_REQUEST)


def test_http_online_score_ok(scoring_server) -> None:
    url = _method_url(scoring_server)
    body_req = {
        "account": "horns&hoofs",
        "login": "h&f",
        "method": "online_score",
        "arguments": {"phone": "79175002040", "email": "u@example.com"},
    }
    set_valid_auth(body_req)
    code, outer = _post_json(url, body_req)
    assert code == api.OK
    assert_ok_envelope(outer)
    assert "score" in outer["response"]
    assert outer["response"]["score"] >= 0


def test_http_clients_interests_with_db(tmp_path, scoring_server) -> None:
    path = tmp_path / "http.db"
    store = SQLiteClientInterestsStore(path, check_same_thread=False)
    store.init_schema()
    store.set_interests(3, ["sport", "music"])
    scoring_server.settings = {"interests_store": store}

    url = _method_url(scoring_server)
    body_req = {
        "account": "horns&hoofs",
        "login": "h&f",
        "method": "clients_interests",
        "arguments": {"client_ids": [3]},
    }
    set_valid_auth(body_req)
    code, outer = _post_json(url, body_req)
    assert code == api.OK
    assert_ok_envelope(outer)
    inner = outer["response"]
    assert inner["3"] == ["sport", "music"]
