from typing import Annotated

from pydantic import (
    BaseModel,
    AfterValidator,
    ConfigDict,
    EmailStr,
    BeforeValidator,
    Field,
)

from src.accounts.validators import validate_password_complexity

Password = Annotated[str, AfterValidator(validate_password_complexity)]
Email = Annotated[
    EmailStr, BeforeValidator(lambda v: v.strip().lower() if isinstance(v, str) else v)
]


class BaseEmailPasswordSchema(BaseModel):
    email: Email
    password: Password = Field(
        description="8-32 characters with upper and lower case letters, "
        "a digit and a special character (@$!%*?#&).",
        examples=["Password123!"],
    )


class UserRegistrationRequestSchema(BaseEmailPasswordSchema):
    pass


class UserRegistrationResponseSchema(BaseModel):
    id: int
    email: Email

    model_config = ConfigDict(from_attributes=True)


class ResendActivationTokenRequestSchema(BaseModel):
    email: Email


class MessageResponseSchema(BaseModel):
    message: str


class UserLoginRequestSchema(BaseEmailPasswordSchema):
    password: str


class UserLoginResponseSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
