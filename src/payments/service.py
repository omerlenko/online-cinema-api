import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.cart.crud import get_cart_by_user_id, delete_cart_items_by_movie_ids
from src.orders.crud import get_order_by_id, get_order_for_payment
from src.orders.models import OrderStatusEnum, Order
from src.payments.crud import create_payment
from src.payments.gateway import (
    StripeGateway,
    CheckoutItem,
    MIN_STRIPE_TOTAL,
    CheckoutCompletedEvent,
)

logger = logging.getLogger(__name__)


class OrderNotFoundError(Exception):
    """
    Raised when the order does not exist or belongs to another user.
    """


class OrderNotPendingError(Exception):
    """
    Raised when an order must be pending but is paid or canceled.
    """


class OrderPriceChangedError(Exception):
    """
    Raised when the price of at least one item within the order has changed
    since the order was placed.
    """


class OrderTotalTooLowError(Exception):
    """
    Raised when order's total amount is lower than Stripe's minimum.
    """


async def start_checkout(
    db: AsyncSession, order_id: int, user_id: int, gateway: StripeGateway
) -> str:
    order = await get_order_by_id(
        db=db, order_id=order_id, user_id=user_id, locked=True
    )
    if order is None:
        raise OrderNotFoundError()

    if order.status != OrderStatusEnum.PENDING:
        raise OrderNotPendingError()

    if order.checkout_session_id is not None:
        await gateway.expire_session(session_id=order.checkout_session_id)

    price_changed = False
    updated_total = Decimal("0.00")
    for item in order.items:
        if item.price_at_order != item.movie.price:
            price_changed = True
            item.price_at_order = item.movie.price

        updated_total += item.price_at_order

    if price_changed:
        order.total_amount = updated_total
        await db.commit()
        raise OrderPriceChangedError()

    if order.total_amount < MIN_STRIPE_TOTAL:
        raise OrderTotalTooLowError()

    checkout_items = [
        CheckoutItem(name=item.movie.name, price=item.price_at_order)
        for item in order.items
    ]
    session = await gateway.create_session(
        order_id=order.id, checkout_items=checkout_items
    )

    order.checkout_session_id = session.id
    await db.commit()

    return session.url


async def cancel_order(
    db: AsyncSession, order_id: int, user_id: int, gateway: StripeGateway
) -> Order:
    order = await get_order_by_id(
        db=db, order_id=order_id, user_id=user_id, locked=True
    )
    if order is None:
        raise OrderNotFoundError()

    if order.status == OrderStatusEnum.PAID:
        raise OrderNotPendingError()

    if order.status == OrderStatusEnum.CANCELED:
        return order

    if order.checkout_session_id is not None:
        await gateway.expire_session(order.checkout_session_id)

    order.status = OrderStatusEnum.CANCELED
    await db.commit()

    return order


async def handle_checkout_completed(
    db: AsyncSession, event: CheckoutCompletedEvent
) -> Order | None:
    if event.payment_status != "paid":
        logger.warning(
            "Ignored Stripe event %s: payment status is %s",
            event.event_id,
            event.payment_status,
        )
        return None

    order = await get_order_for_payment(db=db, order_id=event.order_id)
    if order is None:
        logger.error(
            "Could not record Stripe event %s: order %s not found",
            event.event_id,
            event.order_id,
        )
        return None
    if order.status == OrderStatusEnum.PAID:
        logger.warning(
            "Ignored Stripe event %s: order %s is already paid",
            event.event_id,
            order.id,
        )
        return None

    if order.checkout_session_id != event.session_id:
        logger.error(
            "Could not record Stripe event %s: "
            "session %s is not the current checkout session %s of order %s",
            event.event_id,
            event.session_id,
            order.checkout_session_id,
            order.id,
        )
        return None
    if order.status == OrderStatusEnum.CANCELED:
        logger.error(
            "Could not record Stripe event %s: order %s is canceled",
            event.event_id,
            order.id,
        )
        return None

    if event.amount is None or int(order.total_amount * 100) != event.amount:
        logger.error(
            "Could not record Stripe event %s: "
            "amount %s does not match the total %s of order %s",
            event.event_id,
            event.amount,
            int(order.total_amount * 100),
            order.id,
        )
        return None

    if event.payment_intent_id is None:
        logger.error(
            "Could not record Stripe event %s: no payment intent", event.event_id
        )
        return None

    await create_payment(
        db=db,
        user_id=order.user_id,
        order_id=order.id,
        amount=order.total_amount,
        external_payment_id=event.payment_intent_id,
        order_items=order.items,
    )
    order.status = OrderStatusEnum.PAID

    cart = await get_cart_by_user_id(db=db, user_id=order.user_id)
    if cart is not None:
        paid_movie_ids = [item.movie_id for item in order.items]
        await delete_cart_items_by_movie_ids(
            db=db, cart_id=cart.id, movie_ids=paid_movie_ids
        )

    await db.commit()
    return order
