"""
Юнит-тесты: валидация полей, правила запросов, scoring без БД, auth.
"""

from __future__ import annotations

import datetime
import hashlib
from unittest.mock import patch

import pytest

import api
from scoring import ClientInterestsReader, get_score, get_interests

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "value,ok",
    [
        ("abc", True),
        (123, False),
        (None, False),
    ],
)
def test_char_field(value: object, ok: bool) -> None:
    field = api.CharField(required=False)
    field.field_name = "x"
    valid, err = field.validate(value)
    assert valid is ok
    if not ok:
        assert err is not None


def test_char_field_nullable_accepts_none() -> None:
    field = api.CharField(required=False, nullable=True)
    field.field_name = "note"
    assert field.validate(None) == (True, None)


@pytest.mark.parametrize(
    "value,ok",
    [
        ("a@b", True),
        ("no-at", False),
    ],
)
def test_email_field(value: str, ok: bool) -> None:
    field = api.EmailField(required=False)
    field.field_name = "email"
    valid, _ = field.validate(value)
    assert valid is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("79175002040", True),
        (79175002040, True),
        ("89175002040", False),
        ("7917500204", False),
    ],
)
def test_phone_field(value: object, ok: bool) -> None:
    field = api.PhoneField(required=False)
    field.field_name = "phone"
    valid, _ = field.validate(value)
    assert valid is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("20.07.2017", True),
        ("1.07.2017", False),
        ("32.01.2017", False),
        ("not-a-date", False),
        (None, True),
    ],
)
def test_date_field(value: object, ok: bool) -> None:
    field = api.DateField(required=False, nullable=True)
    field.field_name = "date"
    valid, _ = field.validate(value)
    assert valid is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        (0, True),
        (1, True),
        (2, True),
        (-1, False),
        (3, False),
        pytest.param(True, False, id="bool_true_rejected"),
        ("1", False),
    ],
)
def test_gender_field(value: object, ok: bool) -> None:
    field = api.GenderField(required=False)
    field.field_name = "gender"
    valid, _ = field.validate(value)
    assert valid is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ([1, 2], True),
        ([], False),
        ("1,2", False),
        ([1, "2"], False),
        ([1, True], False),
    ],
)
def test_client_ids_field(value: object, ok: bool) -> None:
    field = api.ClientIDsField(required=True)
    field.field_name = "client_ids"
    valid, _ = field.validate(value)
    assert valid is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ({}, True),
        ([], False),
        (None, False),
    ],
)
def test_arguments_field(value: object, ok: bool) -> None:
    field = api.ArgumentsField(required=True, nullable=True)
    field.field_name = "arguments"
    valid, _ = field.validate(value)
    assert valid is ok


@pytest.mark.parametrize(
    "data,ok",
    [
        ({"client_ids": [1]}, True),
        ({"client_ids": [1], "date": None}, True),
        ({"client_ids": [1], "date": "bad"}, False),
        ({}, False),
    ],
)
def test_clients_interests_request(data: dict, ok: bool) -> None:
    req = api.ClientsInterestsRequest(data)
    valid, errs = req.validate()
    assert valid is ok
    if not ok:
        assert errs


def test_method_request_requires_method_and_arguments_key() -> None:
    base = {
        "account": "a",
        "login": "u",
        "token": "t",
        "arguments": {},
    }
    missing_method = {k: v for k, v in base.items() if k != "method"}
    assert api.MethodRequest(missing_method).validate()[0] is False

    assert api.MethodRequest({**base, "method": "online_score"}).validate()[0] is True

    missing_arguments = {k: v for k, v in base.items() if k != "arguments"}
    missing_arguments["method"] = "online_score"
    assert api.MethodRequest(missing_arguments).validate()[0] is False


def test_birthday_rejects_too_old() -> None:
    field = api.BirthDayField(required=False)
    field.field_name = "birthday"
    old = (datetime.datetime.now() - datetime.timedelta(days=71 * 365)).strftime(
        "%d.%m.%Y"
    )
    valid, err = field.validate(old)
    assert valid is False
    assert err is not None and "70" in err


@pytest.mark.parametrize(
    "arguments,expect_ok",
    [
        ({}, False),
        ({"phone": "79175002040"}, False),
        (
            {"phone": "79175002040", "email": "x@y.ru"},
            True,
        ),
        ({"first_name": "a", "last_name": "b"}, True),
        ({"gender": 1, "birthday": "01.01.2000"}, True),
    ],
)
def test_online_score_request_pair_rule(
    arguments: dict, expect_ok: bool
) -> None:
    req = api.OnlineScoreRequest(arguments)
    ok, errs = req.validate()
    assert ok is expect_ok
    if not expect_ok:
        assert errs


def test_get_score_components() -> None:
    assert get_score("7", "a@b") == 3.0
    assert get_score(None, None, birthday="01.01.2000", gender=1) == 1.5
    assert get_score(None, None, first_name="A", last_name="B") == 0.5


def test_check_auth_admin_ok() -> None:
    token = hashlib.sha512(
        (datetime.datetime.now().strftime("%Y%m%d%H") + api.ADMIN_SALT).encode()
    ).hexdigest()
    assert api.check_auth({"login": api.ADMIN_LOGIN, "token": token}) is True


def test_check_auth_user_ok() -> None:
    body = {"account": "acc", "login": "user", "token": ""}
    msg = (body["account"] + body["login"] + api.SALT).encode()
    body["token"] = hashlib.sha512(msg).hexdigest()
    assert api.check_auth(body) is True


@patch("scoring.random.sample", return_value=["music", "books"])
def test_get_interests_without_store(mock_sample) -> None:
    out = get_interests("1")
    assert out == ["music", "books"]
    mock_sample.assert_called_once()


def test_get_interests_with_fake_store() -> None:
    class Fake:
        def get_interests(self, client_id: int) -> list[str] | None:
            if client_id == 5:
                return ["cars", "sport"]
            return None

    store: ClientInterestsReader = Fake()
    assert get_interests("5", store=store) == ["cars", "sport"]
    assert get_interests("99", store=store) == []
