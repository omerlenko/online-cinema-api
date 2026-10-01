from typing import Annotated

from pydantic import (
    BaseModel,
    AfterValidator,
    ConfigDict,
    EmailStr,
    BeforeValidator,
)

from src.accounts.validators import validate_password_complexity

Password = Annotated[str, AfterValidator(validate_password_complexity)]
Email = Annotated[
    EmailStr, BeforeValidator(lambda v: v.strip().lower() if isinstance(v, str) else v)
]


class UserRegistrationRequestSchema(BaseModel):
    email: Email
    password: Password


class UserRegistrationResponseSchema(BaseModel):
    id: int
    email: Email

    model_config = ConfigDict(from_attributes=True)


class ResendActivationTokenRequestSchema(BaseModel):
    email: Email


class MessageResponseSchema(BaseModel):
    message: str
