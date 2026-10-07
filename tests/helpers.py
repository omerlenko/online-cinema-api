from dataclasses import dataclass

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
