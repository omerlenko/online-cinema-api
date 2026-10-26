from enum import Enum
from typing import Annotated

from pydantic import (
    BaseModel,
    AfterValidator,
    ConfigDict,
    EmailStr,
    BeforeValidator,
    Field,
    AliasPath,
    StringConstraints,
)

from src.accounts.models import UserGroupEnum
from src.accounts.validators import validate_password_complexity
from src.core.schemas import SortOrderEnum

Password = Annotated[str, AfterValidator(validate_password_complexity)]
Email = Annotated[
    EmailStr, BeforeValidator(lambda v: v.strip().lower() if isinstance(v, str) else v)
]


class BaseEmailPasswordSchema(BaseModel):
    email: Email
    password: Password = Field(
        description="8-32 characters with upper and lower case letters, "
        "a digit and a special character (@$!%*?#&).",
        examples=["Password12345!"],
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
    password: str = Field(examples=["Password12345!"])


class UserLoginResponseSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserDetailResponseSchema(BaseModel):
    id: int
    email: str
    group_name: str = Field(validation_alias=AliasPath("group", "name"))
    is_active: bool

    model_config = ConfigDict(from_attributes=True, validate_by_name=True)


class UserSortField(str, Enum):
    ID = "id"
    EMAIL = "email"


class UserQueryParameters(BaseModel):
    is_active: bool | None = None
    group: UserGroupEnum | None = None

    search: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None
    ) = None

    sort_by: UserSortField = UserSortField.ID
    order: SortOrderEnum = SortOrderEnum.ASC


class RefreshTokenRequestSchema(BaseModel):
    refresh_token: str


class RefreshTokenResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePasswordRequestSchema(BaseModel):
    old_password: str
    new_password: Password
    refresh_token: str | None = None


class ForgotPasswordRequestSchema(BaseModel):
    email: Email


class ResetPasswordRequestSchema(BaseModel):
    new_password: Password
    password_reset_token: str


class ChangeGroupRequestSchema(BaseModel):
    group_name: UserGroupEnum
