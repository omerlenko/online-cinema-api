from datetime import datetime, timezone
import smtplib
from email.message import EmailMessage

from fastapi import APIRouter, HTTPException, BackgroundTasks
from sqlalchemy.exc import IntegrityError

from src.accounts.crud import (
    get_user_by_email,
    get_user_group_by_name,
    create_user,
    create_activation_token,
    get_activation_token,
    get_user_by_id,
    get_activation_token_by_user_id,
    delete_activation_token,
)
from src.accounts.models import UserGroupEnum
from src.accounts.schemas import (
    UserRegistrationResponseSchema,
    UserRegistrationRequestSchema,
    MessageResponseSchema,
    ResendActivationTokenRequestSchema,
)
from src.core.config import get_settings
from src.database.session import DbDep

router = APIRouter()
settings = get_settings()


def send_email(to_email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "noreply@example.com"
    msg["To"] = to_email

    msg.set_content(body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()

        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)


@router.post("/register", status_code=201)
async def register_user(
    db: DbDep, data: UserRegistrationRequestSchema, background_tasks: BackgroundTasks
) -> UserRegistrationResponseSchema:
    existing_user = await get_user_by_email(db=db, email=data.email)
    if existing_user is not None:
        raise HTTPException(
            status_code=409, detail="A user with this email already exist"
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
            status_code=409, detail="A user with this email already exist"
        )

    activation_link = (
        f"http://127.0.0.1:8000/api/v1/accounts/activate?token={activation_token.token}"
    )
    background_tasks.add_task(
        send_email,
        to_email=new_user.email,
        subject="Account activation link",
        body=activation_link,
    )

    return UserRegistrationResponseSchema(email=new_user.email)


@router.get("/activate")
async def activate_user(db: DbDep, token: str) -> MessageResponseSchema:
    activation_token = await get_activation_token(db=db, token=token)
    if activation_token is None:
        raise HTTPException(
            status_code=400, detail="Invalid or expired activation token"
        )

    user = await get_user_by_id(db=db, id=activation_token.user_id)
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


@router.post("/resend_activation")
async def resend_activation_token(
    db: DbDep,
    email_data: ResendActivationTokenRequestSchema,
    background_tasks: BackgroundTasks,
) -> MessageResponseSchema:
    user = await get_user_by_email(db=db, email=email_data.email)
    if user is None or user.is_active:
        return MessageResponseSchema(
            message="Activation token has been resent to the provided email "
            "if it's valid"
        )

    activation_token = await get_activation_token_by_user_id(db=db, user_id=user.id)
    if activation_token is None:
        activation_token = await create_activation_token(db=db, user_id=user.id)
    else:
        if activation_token.expires_at <= datetime.now(timezone.utc):
            await delete_activation_token(db=db, activation_token=activation_token)
            activation_token = await create_activation_token(db=db, user_id=user.id)
    await db.commit()

    activation_link = (
        f"http://127.0.0.1:8000/api/v1/accounts/activate?token={activation_token.token}"
    )
    background_tasks.add_task(
        send_email,
        to_email=user.email,
        subject="New account activation link",
        body=activation_link,
    )

    return MessageResponseSchema(
        message="Activation token has been resent to the provided email "
        "if it's valid"
    )
