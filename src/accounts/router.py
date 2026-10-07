from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from sqlalchemy.exc import IntegrityError

from src.accounts.dependencies import CurrentUserDep
from src.core.schemas import ErrorResponseSchema
from src.core.config import get_settings
from src.core.mailer import EmailSenderDep
from src.accounts.crud import (
    get_user_by_email,
    get_user_group_by_name,
    create_user,
    create_activation_token,
    get_activation_token,
    get_user_by_id,
    get_activation_token_by_user_id,
    delete_activation_token,
    create_refresh_token_object,
    get_refresh_token_object_by_token,
    delete_refresh_token_object,
)
from src.accounts.models import UserGroupEnum
from src.accounts.schemas import (
    UserRegistrationResponseSchema,
    UserRegistrationRequestSchema,
    MessageResponseSchema,
    ResendActivationTokenRequestSchema,
    UserLoginRequestSchema,
    UserLoginResponseSchema,
    UserDetailResponseSchema,
    RefreshTokenRequestSchema,
    RefreshTokenResponseSchema,
)
from src.core.security import (
    verify_hashed_password,
    create_access_token,
    decode_token,
    TokenTypeEnum,
    InvalidTokenError,
)
from src.database.session import DbDep

router = APIRouter()
settings = get_settings()


def generate_activation_link(token: str) -> str:
    return (
        f"{settings.BASE_URL}{settings.API_VERSION_PREFIX}"
        f"/accounts/activate?token={token}"
    )


@router.post(
    "/register",
    status_code=201,
    summary="Register a new user",
    responses={
        409: {"model": ErrorResponseSchema, "description": "Email already registered"},
    },
)
async def register_user(
    db: DbDep,
    data: UserRegistrationRequestSchema,
    background_tasks: BackgroundTasks,
    email_sender: EmailSenderDep,
) -> UserRegistrationResponseSchema:
    """
    Create an inactive user account and send an activation link by email.

    The link is valid for 24 hours. If it expires, request a new one via
    `/resend_activation`.
    """
    existing_user = await get_user_by_email(db=db, email=data.email)
    if existing_user is not None:
        raise HTTPException(
            status_code=409, detail="A user with this email already exists"
        )
    user_group = await get_user_group_by_name(db=db, name=UserGroupEnum.USER)
    if user_group is None:
        raise HTTPException(status_code=500, detail="Default user group not found")

    try:
        new_user = await create_user(db=db, data=data, user_group=user_group)
        activation_token = await create_activation_token(db=db, user_id=new_user.id)
        await db.commit()
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="A user with this email already exists"
        )

    activation_link = generate_activation_link(activation_token.token)
    background_tasks.add_task(
        email_sender.send_email,
        to=new_user.email,
        subject="Account activation link",
        body=activation_link,
    )

    return UserRegistrationResponseSchema(id=new_user.id, email=new_user.email)


@router.get(
    "/activate",
    summary="Activate a registered user",
    responses={
        400: {
            "model": ErrorResponseSchema,
            "description": "Invalid or expired activation token",
        },
        404: {
            "model": ErrorResponseSchema,
            "description": "User not found",
        },
    },
)
async def activate_user(
    db: DbDep,
    token: Annotated[str, Query(description="Token from the activation email link")],
) -> MessageResponseSchema:
    """
    Activate an inactive user account with their activation token.

    Endpoint uses GET method because the link is opened from an email.

    An already active account gets 200 OK with 'User already active', not an error.

    An expired link gets 400, the user can use '/resend_activation'
    to get a new activation link.
    """
    activation_token = await get_activation_token(db=db, token=token)
    if activation_token is None:
        raise HTTPException(
            status_code=400, detail="Invalid or expired activation token"
        )

    user = await get_user_by_id(db=db, user_id=activation_token.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_active:
        return MessageResponseSchema(message="User already active")

    if activation_token.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400, detail="Invalid or expired activation token"
        )

    user.is_active = True
    await db.commit()
    return MessageResponseSchema(message="User activated successfully")


@router.post(
    "/resend_activation",
    summary="Resend activation email",
)
async def resend_activation_token(
    db: DbDep,
    email_data: ResendActivationTokenRequestSchema,
    background_tasks: BackgroundTasks,
    email_sender: EmailSenderDep,
) -> MessageResponseSchema:
    """
    Resend email with an activation link to an inactive account.

    Endpoint returns identical message in all cases
    to avoid revealing if an email is registered or already active.

    Active accounts receive no email.
    """
    user = await get_user_by_email(db=db, email=email_data.email)
    if user is None or user.is_active:
        return MessageResponseSchema(
            message="If the email belongs to an inactive account, "
            "a new activation link has been sent"
        )

    activation_token = await get_activation_token_by_user_id(db=db, user_id=user.id)
    if activation_token is None:
        activation_token = await create_activation_token(db=db, user_id=user.id)
    else:
        if activation_token.expires_at <= datetime.now(timezone.utc):
            await delete_activation_token(db=db, activation_token=activation_token)
            activation_token = await create_activation_token(db=db, user_id=user.id)
    await db.commit()

    activation_link = generate_activation_link(activation_token.token)
    background_tasks.add_task(
        email_sender.send_email,
        to=user.email,
        subject="New account activation link",
        body=activation_link,
    )

    return MessageResponseSchema(
        message="If the email belongs to an inactive account, "
        "a new activation link has been sent"
    )


@router.post("/login")
async def login_user(
    db: DbDep, login_data: UserLoginRequestSchema
) -> UserLoginResponseSchema:
    user = await get_user_by_email(db=db, email=login_data.email)
    if user is None:
        raise HTTPException(
            status_code=401, detail="Provided email or password is incorrect"
        )
    if not verify_hashed_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=401, detail="Provided email or password is incorrect"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="User account must be active to log in",
        )

    access_token = create_access_token(user_id=user.id)
    refresh_token = await create_refresh_token_object(db=db, user_id=user.id)
    await db.commit()

    return UserLoginResponseSchema(
        access_token=access_token, refresh_token=refresh_token.token
    )


@router.get("/me")
async def get_current_user_detail(
    current_user: CurrentUserDep,
) -> UserDetailResponseSchema:
    return UserDetailResponseSchema(
        id=current_user.id, email=current_user.email, group_name=current_user.group.name
    )


@router.post("/refresh")
async def refresh_access_token(
    db: DbDep, token_data: RefreshTokenRequestSchema
) -> RefreshTokenResponseSchema:
    try:
        user_id = decode_token(token_data.refresh_token, TokenTypeEnum.REFRESH)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    token_object = await get_refresh_token_object_by_token(
        db=db, token=token_data.refresh_token
    )
    if token_object is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await get_user_by_id(db=db, user_id=user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User not active")

    return RefreshTokenResponseSchema(access_token=create_access_token(user_id))


@router.post("/logout", status_code=204)
async def logout_user(db: DbDep, token_data: RefreshTokenRequestSchema) -> None:
    refresh_token_object = await get_refresh_token_object_by_token(
        db=db, token=token_data.refresh_token
    )
    if refresh_token_object is None:
        return

    await delete_refresh_token_object(db=db, refresh_token_object=refresh_token_object)
    await db.commit()
