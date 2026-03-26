import datetime
import hashlib
import json
import logging
import re
import uuid
from argparse import ArgumentParser
from email.message import Message
from enum import Enum
from http.server import (
    BaseHTTPRequestHandler,
    HTTPServer,
)
from typing import Any, Callable


class Gender(Enum):
    UNKNOWN = 0
    MALE = 1
    FEMALE = 2


class ErrorMessage(Enum):
    BAD_REQUEST = "Bad Request"
    FORBIDDEN = "Forbidden"
    NOT_FOUND = "Not Found"
    INVALID_REQUEST = "Invalid Request"
    INTERNAL_ERROR = "Internal Server Error"


SALT = "Otus"
ADMIN_LOGIN = "admin"
ADMIN_SALT = "42"

OK = 200
BAD_REQUEST = 400
FORBIDDEN = 403
NOT_FOUND = 404
INVALID_REQUEST = 422
INTERNAL_ERROR = 500

ERRORS: dict[int, str] = {
    BAD_REQUEST: "Bad Request",
    FORBIDDEN: "Forbidden",
    NOT_FOUND: "Not Found",
    INVALID_REQUEST: "Invalid Request",
    INTERNAL_ERROR: "Internal Server Error",
}

MAX_YEARS_DIFF = 70


class Field:
    """Базовый дескриптор для полей запроса."""

    def __init__(
        self,
        required: bool = False,
        nullable: bool = False,
    ) -> None:
        self.required = required
        self.nullable = nullable
        self.field_name: str | None = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.field_name = name

    def __get__(self, obj: object | None, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        assert self.field_name is not None
        return obj.__dict__.get(self.field_name)

    def __set__(self, obj: object, value: Any) -> None:
        assert self.field_name is not None
        obj.__dict__[self.field_name] = value

    def validate(self, value: Any) -> tuple[bool, str | None]:
        if self.field_name is None:
            return True, None
        if value is None:
            if self.required:
                return False, f"Поле '{self.field_name}' обязательно"
            if not self.nullable:
                return False, f"Поле '{self.field_name}' не может быть null"
            return True, None
        return self._validate_value(value)

    def _validate_value(self, value: Any) -> tuple[bool, str | None]:
        return True, None


class CharField(Field):
    """Поле строкового типа."""

    def _validate_value(self, value: Any) -> tuple[bool, str | None]:
        if not isinstance(value, str):
            return False, f"Поле '{self.field_name}' должно быть строкой"
        return True, None


class EmailField(CharField):
    """Поле email с проверкой наличия @."""

    def _validate_value(self, value: Any) -> tuple[bool, str | None]:
        is_valid, error = super()._validate_value(value)
        if not is_valid:
            return is_valid, error
        if "@" not in value:
            return False, f"Поле '{self.field_name}' должно содержать символ '@'"
        return True, None


class PhoneField(Field):
    """Поле телефона: строка или число, длиной 11, начинается с 7."""

    def _validate_value(self, value: Any) -> tuple[bool, str | None]:
        if isinstance(value, int):
            value = str(value)
        elif not isinstance(value, str):
            return False, f"Поле '{self.field_name}' должно быть строкой или числом"

        value = str(value)
        if len(value) != 11:
            return False, f"Поле '{self.field_name}' должно содержать 11 символов"
        if not value.startswith("7"):
            return False, f"Поле '{self.field_name}' должно начинаться с 7"
        return True, None


class DateField(Field):
    """Поле даты в формате DD.MM.YYYY."""

    def _validate_value(self, value: Any) -> tuple[bool, str | None]:
        if not isinstance(value, str):
            return False, f"Поле '{self.field_name}' должно быть строкой"

        date_pattern = r"^\d{2}\.\d{2}\.\d{4}$"
        if not re.match(date_pattern, value):
            return False, f"Поле '{self.field_name}' должно быть в формате DD.MM.YYYY"

        try:
            day, month, year = map(int, value.split("."))
            datetime.datetime(year, month, day)
        except ValueError:
            return False, f"Поле '{self.field_name}' содержит некорректную дату"

        return True, None


class BirthDayField(DateField):
    """Поле даты рождения: дата в формате DD.MM.YYYY, не старше 70 лет."""

    def _validate_value(self, value: Any) -> tuple[bool, str | None]:
        is_valid, error = super()._validate_value(value)
        if not is_valid:
            return is_valid, error

        day, month, year = map(int, value.split("."))
        birth_date = datetime.datetime(year, month, day)
        today = datetime.datetime.now()
        years_diff = (today - birth_date).days / 365.25

        if years_diff > MAX_YEARS_DIFF:
            return (
                False,
                f"Поле '{self.field_name}' указывает на возраст более {MAX_YEARS_DIFF} лет",
            )
        return True, None


class GenderField(Field):
    """Поле пола: число 0, 1 или 2."""

    def _validate_value(self, value: Any) -> tuple[bool, str | None]:
        if not isinstance(value, int) or isinstance(value, bool):
            return False, f"Поле '{self.field_name}' должно быть целым числом"
        if value not in (0, 1, 2):
            return False, f"Поле '{self.field_name}' должно быть 0, 1 или 2"
        return True, None


class ClientIDsField(Field):
    """Поле списка идентификаторов клиентов: массив чисел."""

    def _validate_value(self, value: Any) -> tuple[bool, str | None]:
        if not isinstance(value, list):
            return False, f"Поле '{self.field_name}' должно быть массивом"
        if len(value) == 0:
            return False, f"Поле '{self.field_name}' не может быть пустым"
        for item in value:
            if not isinstance(item, int) or isinstance(item, bool):
                return False, f"Поле '{self.field_name}' должно содержать только числа"
        return True, None


class ArgumentsField(Field):
    """Поле аргументов: словарь."""

    def _validate_value(self, value: Any) -> tuple[bool, str | None]:
        if not isinstance(value, dict):
            return False, f"Поле '{self.field_name}' должно быть объектом (словарём)"
        return True, None


class RequestMeta(type):
    """
    Метакласс для классов запросов.
    Собирает все поля типа Field в список fields.
    """

    fields: list[Field]

    def __new__(mcs, name: str, bases: tuple, attrs: dict) -> type:
        fields: list[Field] = []
        for base in bases:
            if hasattr(base, "fields"):
                fields.extend(base.fields)
        for attr_name, attr_value in attrs.items():
            if isinstance(attr_value, Field):
                fields.append(attr_value)

        new_class = super().__new__(mcs, name, bases, attrs)
        new_class.fields = fields
        return new_class


class BaseRequest(metaclass=RequestMeta):
    """Базовый класс для всех запросов."""

    fields: list[Field]

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self._validated_fields: dict[str, Any] = {}
        self._errors: list[str] = []

    def validate(self) -> tuple[bool, list[str]]:
        self._errors = []
        self._validated_fields = {}

        for field in self.fields:
            field_name = field.field_name
            if field_name is None:
                continue
            value = self.data.get(field_name)
            is_valid, error = field.validate(value)

            if not is_valid and error:
                self._errors.append(error)
            else:
                self._validated_fields[field_name] = value

        return len(self._errors) == 0, self._errors

    @property
    def errors(self) -> list[str]:
        return self._errors

    @property
    def validated_data(self) -> dict[str, Any]:
        return self._validated_fields


class ClientsInterestsRequest(BaseRequest):
    client_ids = ClientIDsField(required=True)
    date = DateField(required=False, nullable=True)


class OnlineScoreRequest(BaseRequest):
    first_name = CharField(required=False, nullable=True)
    last_name = CharField(required=False, nullable=True)
    email = EmailField(required=False, nullable=True)
    phone = PhoneField(required=False, nullable=True)
    birthday = BirthDayField(required=False, nullable=True)
    gender = GenderField(required=False, nullable=True)

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(data)
        self.has_fields: list[str] = []

    def validate(self) -> tuple[bool, list[str]]:
        is_valid, errors = super().validate()
        if not is_valid:
            return False, errors

        phone = self.data.get("phone")
        email = self.data.get("email")
        first_name = self.data.get("first_name")
        last_name = self.data.get("last_name")
        gender = self.data.get("gender")
        birthday = self.data.get("birthday")

        has_phone_email = phone is not None and email is not None
        has_name_pair = first_name is not None and last_name is not None
        has_gender_birthday = gender is not None and birthday is not None

        if not (has_phone_email or has_name_pair or has_gender_birthday):
            return False, [
                "Должна быть хотя бы одна пара: (phone, email), "
                "(first_name, last_name) или (gender, birthday)"
            ]

        self.has_fields = [
            field
            for field in [
                "phone",
                "email",
                "first_name",
                "last_name",
                "gender",
                "birthday",
            ]
            if self.data.get(field) is not None
        ]
        return True, errors


class MethodRequest(BaseRequest):
    account = CharField(required=False, nullable=True)
    login = CharField(required=True, nullable=True)
    token = CharField(required=True, nullable=True)
    arguments = ArgumentsField(required=True, nullable=True)
    method = CharField(required=True, nullable=False)

    @property
    def is_admin(self) -> bool:
        return self.data.get("login") == ADMIN_LOGIN


def check_auth(request_data: dict[str, Any]) -> bool:
    login = request_data.get("login", "")
    if login == ADMIN_LOGIN:
        digest = hashlib.sha512(
            (datetime.datetime.now().strftime("%Y%m%d%H") + ADMIN_SALT).encode("utf-8")
        ).hexdigest()
    else:
        account = request_data.get("account", "")
        digest = hashlib.sha512((account + login + SALT).encode("utf-8")).hexdigest()
    return digest == request_data.get("token", "")


def online_score_handler(
    request_data: dict[str, Any],
    ctx: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    from scoring import get_score

    arguments = request_data.get("arguments", {})
    score_request = OnlineScoreRequest(arguments)
    is_valid, errors = score_request.validate()

    if not is_valid:
        return {"error": "; ".join(errors)}, INVALID_REQUEST

    ctx["has"] = score_request.has_fields
    validated = score_request.validated_data

    score = get_score(
        phone=validated.get("phone"),
        email=validated.get("email"),
        birthday=validated.get("birthday"),
        gender=validated.get("gender"),
        first_name=validated.get("first_name"),
        last_name=validated.get("last_name"),
    )

    if request_data.get("login") == ADMIN_LOGIN:
        score = 42

    return {"score": score}, OK


def clients_interests_handler(
    request_data: dict[str, Any],
    ctx: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    from scoring import get_interests

    arguments = request_data.get("arguments", {})
    interests_request = ClientsInterestsRequest(arguments)
    is_valid, errors = interests_request.validate()

    if not is_valid:
        return {"error": "; ".join(errors)}, INVALID_REQUEST

    validated = interests_request.validated_data
    client_ids = validated.get("client_ids", [])
    ctx["nclients"] = len(client_ids)

    response: dict[str, list[str]] = {}
    for cid in client_ids:
        response[str(cid)] = get_interests(str(cid))

    return response, OK


def method_handler(
    request: dict[str, Any],
    ctx: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    body = request.get("body", {})

    method_request = MethodRequest(body)
    is_valid, errors = method_request.validate()

    if not is_valid:
        return {"error": "; ".join(errors)}, INVALID_REQUEST

    if not check_auth(body):
        return {"error": "Forbidden"}, FORBIDDEN

    method_name = body.get("method", "")
    handlers: dict[str, Callable] = {
        "online_score": online_score_handler,
        "clients_interests": clients_interests_handler,
    }

    if method_name not in handlers:
        return {"error": f"Метод '{method_name}' не найден"}, INVALID_REQUEST

    return handlers[method_name](body, ctx)


class MainHTTPHandler(BaseHTTPRequestHandler):
    router: dict[str, Callable] = {"method": method_handler}

    def get_request_id(self, headers: Message) -> str:
        return headers.get("HTTP_X_REQUEST_ID", uuid.uuid4().hex)

    def do_POST(self) -> None:
        response: dict[str, Any] = {}
        code = OK
        context: dict[str, Any] = {"request_id": self.get_request_id(self.headers)}
        request: dict[str, Any] | None = None

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            data_string = self.rfile.read(content_length)
            request = json.loads(data_string)
        except (ValueError, json.JSONDecodeError):
            code = BAD_REQUEST
            data_string = b""

        if request:
            path = self.path.strip("/")
            logging.info("%s: %s %s", self.path, data_string, context["request_id"])

            if path in self.router:
                try:
                    response, code = self.router[path](
                        {"body": request, "headers": self.headers},
                        context,
                    )
                except Exception as e:
                    logging.exception("Unexpected error: %s", e)
                    code = INTERNAL_ERROR
            else:
                code = NOT_FOUND

        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        if code not in ERRORS:
            r = {"response": response, "code": code}
        else:
            error_msg = (
                response.get("error") if isinstance(response, dict) else response
            )
            r = {"error": error_msg, "code": code}

        context.update(r)
        logging.info("Response: %s", context)
        self.wfile.write(json.dumps(r).encode("utf-8"))


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("-p", "--port", action="store", type=int, default=8080)
    parser.add_argument("-l", "--log", action="store", default=None)
    args = parser.parse_args()

    logging.basicConfig(
        filename=args.log,
        level=logging.INFO,
        format="[%(asctime)s] %(levelname).1s %(message)s",
        datefmt="%Y.%m.%d %H:%M:%S",
        encoding="utf-8",
    )

    server = HTTPServer(("localhost", args.port), MainHTTPHandler)
    logging.info("Starting server at %s" % args.port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
