import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from stripe import (
    StripeClient,
    InvalidRequestError,
    StripeError,
    Webhook,
    SignatureVerificationError,
)
from stripe.params.checkout import SessionCreateParamsLineItem

from src.core.config import get_settings, Settings

logger = logging.getLogger(__name__)

# Stripe's minimum total amount in USD,
# the value must change if STRIPE_CURRENCY changes.
MIN_STRIPE_TOTAL = Decimal("0.50")


class CheckoutSessionAlreadyPaidError(Exception):
    """
    Raised when trying to expire a complete (paid) Stripe session.
    """


class PaymentProviderError(Exception):
    """
    Raised when a request to Stripe fails.
    """


class InvalidWebhookError(Exception):
    """
    Raised when a webhook request has a missing or invalid signature,
    or a body that is not valid JSON.
    """


@dataclass
class CheckoutItem:
    name: str
    price: Decimal


@dataclass
class StripeSession:
    id: str
    url: str


@dataclass
class CheckoutCompletedEvent:
    event_id: str
    session_id: str
    order_id: int
    amount: int | None
    payment_intent_id: str | None
    payment_status: str


class StripeGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = StripeClient(settings.STRIPE_SECRET_KEY)
        self.base_url = settings.BASE_URL + settings.API_VERSION_PREFIX

    async def create_session(
        self, order_id: int, checkout_items: list[CheckoutItem]
    ) -> StripeSession:
        line_items: list[SessionCreateParamsLineItem] = []
        for checkout_item in checkout_items:
            line_item: SessionCreateParamsLineItem = {
                "price_data": {
                    "currency": self.settings.STRIPE_CURRENCY,
                    "unit_amount": int(checkout_item.price * 100),
                    "product_data": {"name": checkout_item.name},
                },
                "quantity": 1,
            }
            line_items.append(line_item)

        success_url = (
            f"{self.base_url}/payments/success?session_id={{CHECKOUT_SESSION_ID}}"
        )
        cancel_url = f"{self.base_url}/payments/cancel"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=35)

        try:
            session = await self.client.v1.checkout.sessions.create_async(
                params={
                    "mode": "payment",
                    "line_items": line_items,
                    "success_url": success_url,
                    "cancel_url": cancel_url,
                    "client_reference_id": str(order_id),
                    "metadata": {"order_id": str(order_id)},
                    "expires_at": int(expires_at.timestamp()),
                }
            )
        except StripeError as exc:
            logger.exception(
                "Failed to create a Stripe checkout session for order %s", order_id
            )
            raise PaymentProviderError() from exc

        if session.url is None:
            raise ValueError("Stripe session url is empty")

        return StripeSession(id=session.id, url=session.url)

    async def expire_session(self, session_id: str) -> None:
        try:
            await self.client.v1.checkout.sessions.expire_async(session_id)

        except InvalidRequestError:
            try:
                session = await self.client.v1.checkout.sessions.retrieve_async(
                    session_id
                )
            except StripeError as exc:
                logger.exception(
                    "Failed to check the status of Stripe checkout session %s",
                    session_id,
                )
                raise PaymentProviderError() from exc

            if session.status == "complete":
                raise CheckoutSessionAlreadyPaidError()

        except StripeError as exc:
            logger.exception("Failed to expire Stripe checkout session %s", session_id)
            raise PaymentProviderError() from exc


@lru_cache
def _create_stripe_gateway() -> StripeGateway:
    return StripeGateway(get_settings())


def get_stripe_gateway() -> StripeGateway:
    return _create_stripe_gateway()


StripeGatewayDep = Annotated[StripeGateway, Depends(get_stripe_gateway)]


def parse_webhook_event(
    payload: bytes, signature: str | None, secret: str
) -> CheckoutCompletedEvent | None:
    try:
        event = Webhook.construct_event(payload, signature, secret)
    except SignatureVerificationError as exc:
        logger.warning(
            "Rejected a webhook request with a missing or invalid Stripe signature"
        )
        raise InvalidWebhookError() from exc
    except ValueError as exc:
        logger.warning("Rejected a webhook request with a body that is not valid JSON")
        raise InvalidWebhookError() from exc

    if event.type == "checkout.session.completed":
        session = event.data.object
        metadata = session.metadata
        order_id = (
            metadata["order_id"]
            if metadata is not None and "order_id" in metadata
            else None
        )
        if order_id is None:
            logger.warning(
                "Ignored Stripe event %s: checkout session %s has no order_id",
                event.id,
                session.id,
            )
            return None

        return CheckoutCompletedEvent(
            event_id=event.id,
            session_id=session.id,
            order_id=int(order_id),
            amount=session.amount_total,
            payment_intent_id=session.payment_intent,
            payment_status=session.payment_status,
        )
    return None
