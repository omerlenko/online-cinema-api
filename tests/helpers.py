import re
from dataclasses import dataclass
from typing import Any

from src.accounts.models import User
from src.core.security import create_access_token


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@dataclass
class SentEmail:
    to: str
    subject: str
    body: str


class FakeEmailSender:

    def __init__(self) -> None:
        self.sent_emails: list[SentEmail] = []

    def send_email(self, to: str, subject: str, body: str) -> None:
        email = SentEmail(to, subject, body)
        self.sent_emails.append(email)


def extract_reset_token_from_email(email_body: str) -> str:
    match = re.search(r"Password reset token: (\S+)", email_body)
    assert match is not None, "No password reset token found in the email body"
    return match.group(1)


class FakeTaskSession:
    def __init__(self) -> None:
        self.committed: bool = False

    async def __aenter__(self) -> "FakeTaskSession":
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


def create_movie_payload(
    certification_id: int,
    genre_ids: list[int] | None = None,
    star_ids: list[int] | None = None,
    director_ids: list[int] | None = None,
    **kwargs,
) -> dict[str, Any]:
    movie_payload = {
        "name": "Test Movie",
        "year": 2026,
        "time": 120,
        "imdb": 8.5,
        "votes": 100000,
        "meta_score": 81,
        "gross": 210000000,
        "description": "Test Movie description",
        "price": 9.99,
        "certification_id": certification_id,
        "genre_ids": genre_ids or [],
        "star_ids": star_ids or [],
        "director_ids": director_ids or [],
    }
    if kwargs:
        movie_payload.update(**kwargs)
    return movie_payload
