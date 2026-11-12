from typing import Annotated

from fastapi import APIRouter, Request, Header, HTTPException, BackgroundTasks

from src.core.config import get_settings
from src.core.mailer import EmailSenderDep
from src.core.schemas import MessageResponseSchema, ErrorResponseSchema
from src.database.session import DbDep
from src.payments.gateway import parse_webhook_event, InvalidWebhookError
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
