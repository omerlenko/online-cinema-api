from typing import Annotated

from fastapi import APIRouter, Request, Header, HTTPException, BackgroundTasks, Depends

from src.accounts.dependencies import CurrentUserDep, ModeratorUserDep
from src.core.config import get_settings
from src.core.mailer import EmailSenderDep
from src.core.pagination import PaginationDep
from src.core.schemas import MessageResponseSchema, ErrorResponseSchema, Page
from src.database.session import DbDep
from src.payments import crud
from src.payments.gateway import parse_webhook_event, InvalidWebhookError
from src.payments.schemas import (
    PaymentDetailSchema,
    PaymentQueryParameters,
    AdminPaymentQueryParameters,
    AdminPaymentDetailSchema,
)
from src.payments.service import handle_checkout_completed

router = APIRouter()
settings = get_settings()


@router.get("/success", summary="Payment success page")
async def payment_success() -> MessageResponseSchema:
    """
    Stripe sends the user here after a successful payment. Public.

    This page changes nothing:
    the order becomes `paid` only once Stripe confirms the payment.
    """
    return MessageResponseSchema(
        message="Payment received. "
        "Your order will be marked as paid once the payment is confirmed."
    )


@router.get("/cancel", summary="Payment canceled page")
async def payment_cancel() -> MessageResponseSchema:
    """
    Stripe sends the user here when they leave the payment page without paying. Public.
    """
    return MessageResponseSchema(
        message="Payment was not completed. "
        "You can try again, or use a different payment method."
    )


@router.post(
    "/webhook",
    summary="Receive Stripe events",
    responses={
        400: {
            "model": ErrorResponseSchema,
            "description": "Missing or invalid Stripe signature, "
            "or a body that is not valid JSON.",
        },
    },
)
async def stripe_webhook(
    db: DbDep,
    request: Request,
    background_tasks: BackgroundTasks,
    email_sender: EmailSenderDep,
    stripe_signature: Annotated[str | None, Header()] = None,
) -> MessageResponseSchema:
    """
    Receives events from Stripe. Only Stripe calls this endpoint,
    and every request must carry a valid `Stripe-Signature` header.

    When a checkout is paid, the order becomes `paid`,
    its movies are removed from the cart, and a confirmation email is sent.
    Other events are ignored.
    """
    payload = await request.body()
    try:
        event = parse_webhook_event(
            payload=payload,
            signature=stripe_signature,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except InvalidWebhookError:
        raise HTTPException(status_code=400, detail="Invalid signature or body")
    if event is None:
        return MessageResponseSchema(message="Event ignored")

    order = await handle_checkout_completed(db=db, event=event)
    if order is None:
        return MessageResponseSchema(message="Event ignored")

    movie_names = ", ".join([item.movie.name for item in order.items])
    body = (
        f"Your payment for order {order.id} was received.\n"
        f"Purchased movies: {movie_names}.\n"
        f"Total amount paid: ${order.total_amount}."
    )
    background_tasks.add_task(
        email_sender.send_email,
        to=order.user.email,
        subject=f"Payment for order {order.id} confirmed",
        body=body,
    )

    return MessageResponseSchema(message="Event received")


@router.get(
    "",
    summary="List your payments",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "User is not active.",
        },
    },
)
async def list_payments(
    db: DbDep,
    pagination: PaginationDep,
    current_user: CurrentUserDep,
    params: Annotated[PaymentQueryParameters, Depends()],
) -> Page[PaymentDetailSchema]:
    """
    List the current user's payments.

    Filter payments by date range and status, using `date_from`, `date_to`
    and `status` query parameters.

    Payments are sorted by creation date, newest first.
    Use `sort_order=asc` for oldest first.

    Use `page` and `page_size` to page through the results (at most 100 per request).
    """
    payments = await crud.list_payments(
        db=db,
        user_id=current_user.id,
        offset=pagination.offset,
        limit=pagination.page_size,
        params=params,
    )
    items = [PaymentDetailSchema.model_validate(payment) for payment in payments]
    total = await crud.count_payments(db=db, user_id=current_user.id, params=params)

    return pagination.get_page(items=items, total=total)


@router.get(
    "/all",
    summary="List all payments",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin/moderator "
            "or their account is inactive.",
        },
    },
)
async def list_all_payments(
    db: DbDep,
    pagination: PaginationDep,
    moderator: ModeratorUserDep,
    params: Annotated[AdminPaymentQueryParameters, Depends()],
) -> Page[AdminPaymentDetailSchema]:
    """
    List all payments. Moderator/Admin only.

    Filter payments by user id, date range and status, using `user_id`, `date_from`,
    `date_to` and `status` query parameters.

    Payments are sorted by creation date, newest first.
    Use `sort_order=asc` for oldest first.

    Use `page` and `page_size` to page through the results (at most 100 per request).
    """
    payments = await crud.list_payments(
        db=db,
        user_id=params.user_id,
        offset=pagination.offset,
        limit=pagination.page_size,
        params=params,
    )
    items = [AdminPaymentDetailSchema.model_validate(payment) for payment in payments]
    total = await crud.count_payments(db=db, user_id=params.user_id, params=params)

    return pagination.get_page(items=items, total=total)
