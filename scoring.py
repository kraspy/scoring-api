import random
from typing import Protocol


class ClientInterestsReader(Protocol):
    """Хранилище интересов клиента для `get_interests` (структурная типизация)."""

    def get_interests(self, client_id: int) -> list[str] | None: ...


def get_score(
    phone,
    email,
    birthday=None,
    gender=None,
    first_name=None,
    last_name=None,
) -> float:
    score = 0

    if phone:
        score += 1.5

    if email:
        score += 1.5

    if birthday and gender:
        score += 1.5

    if first_name and last_name:
        score += 0.5

    return score


_INTERESTS_CATALOG = [
    "cars",
    "pets",
    "travel",
    "hi-tech",
    "sport",
    "music",
    "books",
    "tv",
    "cinema",
    "geek",
    "otus",
]


def get_interests(cid: str, store: ClientInterestsReader | None = None) -> list[str]:
    """
    Возвращает интересы клиента.
    Если передан store, данные читаются из хранилища; при отсутствии записи — [].
    Иначе — два случайных значения из каталога.
    """
    if store is not None:
        row = store.get_interests(int(cid))
        return list(row) if row is not None else []

    return random.sample(_INTERESTS_CATALOG, 2)
