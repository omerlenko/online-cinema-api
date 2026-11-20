import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.cart.crud import get_cart_by_user_id, delete_cart_items_by_movie_ids
from src.orders.crud import get_order_by_id, get_order_for_payment
from src.orders.models import OrderStatusEnum, Order
from src.payments.crud import (
    create_payment,
    get_payment_by_id,
    get_payment_by_external_payment_id,
)
from src.payments.gateway import (
    StripeGateway,
    CheckoutItem,
    MIN_STRIPE_TOTAL,
    CheckoutCompletedEvent,
    ChargeRefundedEvent,
)
from src.payments.models import Payment, PaymentStatusEnum

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


class PaymentNotFoundError(Exception):
    """
    Raised when the payment does not exist.
    """


class PaymentNotSuccessfulError(Exception):
    """
    Raised when a payment's status must be successful but is refunded or canceled.
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


async def start_refund(
    db: AsyncSession, payment_id: int, gateway: StripeGateway
) -> Payment:
    payment = await get_payment_by_id(db=db, payment_id=payment_id)
    if payment is None:
        raise PaymentNotFoundError()

    if payment.status != PaymentStatusEnum.SUCCESSFUL:
        raise PaymentNotSuccessfulError()

    await gateway.refund_payment(payment.external_payment_id)

    return payment


async def handle_charge_refunded(
    db: AsyncSession, event: ChargeRefundedEvent
) -> Payment | None:
    if not event.refunded:
        logger.warning(
            "Ignored Stripe event %s: payment intent %s is only partly refunded",
            event.event_id,
            event.payment_intent_id,
        )
        return None

    payment = await get_payment_by_external_payment_id(
        db=db, external_payment_id=event.payment_intent_id, locked=True
    )
    if payment is None:
        logger.error(
            "Could not record Stripe event %s: no payment for payment intent %s",
            event.event_id,
            event.payment_intent_id,
        )
        return None
    if payment.status == PaymentStatusEnum.REFUNDED:
        logger.warning(
            "Ignored Stripe event %s: payment %s is already refunded",
            event.event_id,
            payment.id,
        )
        return None

    payment.status = PaymentStatusEnum.REFUNDED
    payment.order.status = OrderStatusEnum.CANCELED
    await db.commit()

    return payment
