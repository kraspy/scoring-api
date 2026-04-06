"""
Интеграционные тесты: method_handler + SQLite через SQLiteClientInterestsStore.
"""

from __future__ import annotations

import pytest

import api
from conftest import set_valid_auth
from db_wrapper import SQLiteClientInterestsStore

pytestmark = pytest.mark.integration


@pytest.fixture
def db_store(tmp_path) -> SQLiteClientInterestsStore:
    path = tmp_path / "test.db"
    store = SQLiteClientInterestsStore(path)
    store.init_schema()
    return store


def test_clients_interests_reads_from_sqlite(db_store: SQLiteClientInterestsStore) -> None:
    db_store.set_interests(10, ["otus", "geek"])
    db_store.set_interests(11, ["books", "cinema"])

    body: dict = {
        "account": "horns&hoofs",
        "login": "h&f",
        "method": "clients_interests",
        "arguments": {"client_ids": [10, 11]},
    }
    set_valid_auth(body)

    ctx: dict = {}
    settings = {"interests_store": db_store}
    response, code = api.method_handler(
        {"body": body, "headers": {}},
        ctx,
        settings,
    )

    assert code == api.OK
    assert response["10"] == ["otus", "geek"]
    assert response["11"] == ["books", "cinema"]
    assert ctx.get("nclients") == 2


def test_clients_interests_unknown_client_empty_list(db_store: SQLiteClientInterestsStore) -> None:
    body: dict = {
        "account": "horns&hoofs",
        "login": "h&f",
        "method": "clients_interests",
        "arguments": {"client_ids": [404]},
    }
    set_valid_auth(body)
    response, code = api.method_handler(
        {"body": body, "headers": {}},
        {},
        {"interests_store": db_store},
    )
    assert code == api.OK
    assert response["404"] == []


def test_store_roundtrip(db_store: SQLiteClientInterestsStore) -> None:
    db_store.set_interests(1, ["a", "b"])
    assert db_store.get_interests(1) == ["a", "b"]
    assert db_store.get_interests(2) is None
