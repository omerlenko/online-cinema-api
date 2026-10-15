from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from sqlalchemy.exc import IntegrityError

from src.accounts.dependencies import CurrentUserDep, AdminUserDep
from src.core.schemas import ErrorResponseSchema
from src.core.config import get_settings
from src.core.mailer import EmailSenderDep
from src.accounts.crud import (
    get_user_by_email,
    get_user_group_by_name,
    create_user,
    create_activation_token,
    get_activation_token,
    get_activation_token_by_user_id,
    delete_activation_token,
    create_refresh_token_object,
    get_refresh_token_object_by_token,
    delete_refresh_token_object,
    delete_refresh_token_objects_by_user_id,
    create_password_reset_token,
    delete_password_reset_token_by_user_id,
    get_password_reset_token,
    get_user_by_id,
    get_users,
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
    ChangePasswordRequestSchema,
    ForgotPasswordRequestSchema,
    ResetPasswordRequestSchema,
    ChangeGroupRequestSchema,
)
from src.core.security import (
    verify_hashed_password,
    create_access_token,
    decode_token,
    TokenTypeEnum,
    InvalidTokenError,
    hash_password,
    generate_token,
    hash_token,
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
    `/resend-activation`.
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

    An expired link gets 400, the user can use '/resend-activation'
    to get a new activation link.
    """
    activation_token = await get_activation_token(db=db, token=token)
    if activation_token is None:
        raise HTTPException(
            status_code=400, detail="Invalid or expired activation token"
        )

    user = activation_token.user
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
    "/resend-activation",
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


@router.post(
    "/login",
    summary="Log in a registered user",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Provided email or password is incorrect",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Account is not activated",
        },
    },
)
async def login_user(
    db: DbDep, login_data: UserLoginRequestSchema
) -> UserLoginResponseSchema:
    """
    Log in a registered user if their email and password are correct.

    User account must be activated to log in.

    An unknown email and a wrong password return the same 401,
    so the response does not reveal whether an email is registered.

    Returns access and refresh tokens if login is successful.
    """
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
            detail="Account is not activated",
        )

    access_token = create_access_token(user_id=user.id)
    refresh_token = await create_refresh_token_object(db=db, user_id=user.id)
    await db.commit()

    return UserLoginResponseSchema(
        access_token=access_token, refresh_token=refresh_token.token
    )


@router.get(
    "/me",
    summary="Get current user details",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "User is not active",
        },
    },
)
async def get_current_user_detail(
    current_user: CurrentUserDep,
) -> UserDetailResponseSchema:
    """
    Return current user details, including id, email, user group
    and whether the account is active.
    """
    return UserDetailResponseSchema.model_validate(current_user)


@router.post(
    "/refresh",
    summary="Get a new access token",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Refresh token is invalid, expired, revoked, "
            "or not a refresh token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "User is not active",
        },
    },
)
async def refresh_access_token(
    db: DbDep, token_data: RefreshTokenRequestSchema
) -> RefreshTokenResponseSchema:
    """
    Exchange a valid refresh token for a new access token.

    The refresh token is not replaced;
    it stays valid until it expires or the user logs out.
    """
    try:
        user_id = decode_token(token_data.refresh_token, TokenTypeEnum.REFRESH)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    token_object = await get_refresh_token_object_by_token(
        db=db, token=token_data.refresh_token
    )
    if token_object is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = token_object.user
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User not active")

    return RefreshTokenResponseSchema(access_token=create_access_token(user_id))


@router.post(
    "/logout",
    status_code=204,
    summary="Log out user",
)
async def logout_user(db: DbDep, token_data: RefreshTokenRequestSchema) -> None:
    """
    Log out the user by deleting the provided refresh token.

    Endpoint is idempotent - repeated requests will return 204.

    The access token remains valid until it expires.
    """
    refresh_token_object = await get_refresh_token_object_by_token(
        db=db, token=token_data.refresh_token
    )
    if refresh_token_object is None:
        return

    await delete_refresh_token_object(db=db, refresh_token_object=refresh_token_object)
    await db.commit()


@router.post(
    "/change-password",
    summary="Change password",
    responses={
        400: {
            "model": ErrorResponseSchema,
            "description": "Old password is incorrect, "
            "or new password is the same as old one",
        },
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "User is not active",
        },
    },
)
async def change_password(
    db: DbDep, password_data: ChangePasswordRequestSchema, current_user: CurrentUserDep
) -> MessageResponseSchema:
    """
    Set a new password if the old one is provided and valid.

    Logs out all of the user’s sessions.

    If refresh_token is provided, that session stays logged in.

    Access tokens already issued remain valid until they expire.
    """
    if not verify_hashed_password(
        password_data.old_password, current_user.hashed_password
    ):
        raise HTTPException(status_code=400, detail="The old password is incorrect")

    if verify_hashed_password(password_data.new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=400, detail="New password can not be the same as previous one"
        )

    current_user.hashed_password = hash_password(password_data.new_password)

    await delete_refresh_token_objects_by_user_id(
        db=db,
        user_id=current_user.id,
        current_token=password_data.refresh_token,
    )
    await db.commit()

    return MessageResponseSchema(message="New password set successfully")


@router.post(
    "/forgot-password",
    summary="Request password reset email",
)
async def forgot_password(
    db: DbDep,
    email_data: ForgotPasswordRequestSchema,
    email_sender: EmailSenderDep,
    background_tasks: BackgroundTasks,
) -> MessageResponseSchema:
    """
    Request a password reset email containing a short-lived password reset token.

    The token is valid for 15 minutes by default,
    is single-use, and is used with /reset-password.

    Each request replaces any previous token.

    Endpoint returns identical message in all cases
    to avoid revealing if an email is registered and active.
    """
    user = await get_user_by_email(db=db, email=email_data.email)
    if user is None or not user.is_active:
        return MessageResponseSchema(
            message="If the email belongs to an active account, "
            "password reset instructions have been sent"
        )

    await delete_password_reset_token_by_user_id(db=db, user_id=user.id)
    plain_token = generate_token()
    await create_password_reset_token(db=db, user_id=user.id, plain_token=plain_token)
    await db.commit()

    password_reset_email_body = (
        f"Password reset token: {plain_token}\n\n"
        f"Token is valid for {settings.PASSWORD_RESET_TOKEN_LIFETIME_MINUTES} minutes."
    )
    background_tasks.add_task(
        email_sender.send_email,
        to=user.email,
        subject="Password reset token",
        body=password_reset_email_body,
    )

    return MessageResponseSchema(
        message="If the email belongs to an active account, "
        "password reset instructions have been sent"
    )


@router.post(
    "/reset-password",
    summary="Reset password",
    responses={
        400: {
            "model": ErrorResponseSchema,
            "description": "Password reset token is invalid or expired",
        },
    },
)
async def reset_password(
    db: DbDep, data: ResetPasswordRequestSchema
) -> MessageResponseSchema:
    """
    Set a new password with a valid password reset token.

    The token can be used once.

    All of the user’s sessions are logged out.
    """
    plain_token = data.password_reset_token
    hashed_token = hash_token(plain_token)

    password_reset_token = await get_password_reset_token(db=db, token=hashed_token)
    if password_reset_token is None or password_reset_token.expires_at <= datetime.now(
        timezone.utc
    ):
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = password_reset_token.user
    user.hashed_password = hash_password(data.new_password)

    await delete_refresh_token_objects_by_user_id(db=db, user_id=user.id)
    await delete_password_reset_token_by_user_id(db=db, user_id=user.id)
    await db.commit()

    return MessageResponseSchema(message="Password reset successfully")


@router.post(
    "/users/{user_id}/activate",
    summary="Activate a user’s account manually",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin, or their account is inactive.",
        },
        404: {
            "model": ErrorResponseSchema,
            "description": "User is not found.",
        },
    },
)
async def admin_activate_user(
    db: DbDep,
    user_id: int,
    admin: AdminUserDep,
) -> UserDetailResponseSchema:
    """
    Activate a user's account without the activation email. Admin only.

    Activating an account that is already active changes nothing and returns
    200 OK with the user's details.
    """
    user = await get_user_by_id(db=db, user_id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_active:
        user.is_active = True
        await db.commit()

    return UserDetailResponseSchema.model_validate(user)


@router.post(
    "/users/{user_id}/change-group",
    summary="Change a user’s group",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin, their account is inactive, "
            "or they tried to change their own group.",
        },
        404: {
            "model": ErrorResponseSchema,
            "description": "User is not found",
        },
    },
)
async def admin_change_user_group(
    db: DbDep,
    user_id: int,
    data: ChangeGroupRequestSchema,
    admin: AdminUserDep,
) -> UserDetailResponseSchema:
    """
    Move a user to another group. Admin only.

    Admins can change the group of any user except themselves, including
    demoting other admins.

    Requesting the group the user already has changes nothing and returns
    200 OK with the user's details.
    """
    if admin.id == user_id:
        raise HTTPException(
            status_code=403,
            detail="You cannot change your own group",
        )
    user = await get_user_by_id(db=db, user_id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.group.name != data.group_name:
        user_group = await get_user_group_by_name(db=db, name=data.group_name)
        if user_group is None:
            raise HTTPException(status_code=500, detail="User group not found")

        user.group = user_group
        await db.commit()

    return UserDetailResponseSchema.model_validate(user)


@router.get(
    "/users",
    summary="List users",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or their account is inactive.",
        },
    },
)
async def admin_list_users(
    db: DbDep,
    admin: AdminUserDep,
    email: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[UserDetailResponseSchema]:
    """
    List users in id order. Admin only.

    Filter users by email with the email query parameter.

    Use `limit` and `offset` to page through the results (at most 100 per request),
    and `email` to look up a single user by their email address.
    """
    return [
        UserDetailResponseSchema.model_validate(user)
        for user in await get_users(db=db, offset=offset, limit=limit, email=email)
    ]
