from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.orders.crud import get_order_by_id
from src.orders.models import OrderStatusEnum, Order
from src.payments.gateway import StripeGateway, CheckoutItem, MIN_STRIPE_TOTAL


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
