from fastapi import APIRouter

from src.core.schemas import MessageResponseSchema

router = APIRouter()


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
