from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.orders.models import OrderItem
from src.payments.models import Payment, PaymentItem


async def create_payment(
    db: AsyncSession,
    user_id: int,
    order_id: int,
    amount: Decimal,
    external_payment_id: str,
    order_items: list[OrderItem],
) -> Payment:
    payment_items = [
        PaymentItem(order_item=item, price_at_payment=item.price_at_order)
        for item in order_items
    ]
    payment = Payment(
        user_id=user_id,
        order_id=order_id,
        amount=amount,
        external_payment_id=external_payment_id,
        items=payment_items,
    )
    db.add(payment)
    await db.flush()

    return payment
