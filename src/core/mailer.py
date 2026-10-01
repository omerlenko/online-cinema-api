import smtplib
from email.message import EmailMessage
from typing import Annotated

from fastapi import Depends

from src.core.config import get_settings, Settings


class EmailSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send_email(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.settings.EMAIL_SENDER_ADDRESS
        msg["To"] = to

        msg.set_content(body)

        with smtplib.SMTP(self.settings.SMTP_HOST, self.settings.SMTP_PORT) as server:
            if self.settings.SMTP_USE_TLS:
                server.starttls()

            if self.settings.SMTP_USER and self.settings.SMTP_PASSWORD:
                server.login(self.settings.SMTP_USER, self.settings.SMTP_PASSWORD)
            server.send_message(msg)


def get_email_sender() -> EmailSender:
    return EmailSender(get_settings())


EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]
