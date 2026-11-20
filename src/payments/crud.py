from datetime import timedelta
from decimal import Decimal

from sqlalchemy import Select, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.schemas import SortOrderEnum
from src.orders.models import OrderItem, Order
from src.payments.models import Payment, PaymentItem
from src.payments.schemas import PaymentQueryParameters


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


async def get_payment_by_id(db: AsyncSession, payment_id: int) -> Payment | None:
    stmt = select(Payment).where(Payment.id == payment_id)
    payment = await db.scalar(stmt)
    return payment


async def get_payment_by_external_payment_id(
    db: AsyncSession, external_payment_id: str, locked: bool = False
) -> Payment | None:
    stmt = (
        select(Payment)
        .where(Payment.external_payment_id == external_payment_id)
        .options(selectinload(Payment.order).selectinload(Order.user))
    )
    if locked:
        stmt = stmt.with_for_update()
    payment = await db.scalar(stmt)
    return payment


def apply_payment_filters(
    stmt: Select[tuple[Payment]], params: PaymentQueryParameters, user_id: int | None
) -> Select[tuple[Payment]]:
    if user_id is not None:
        stmt = stmt.where(Payment.user_id == user_id)
    if params.date_from is not None:
        stmt = stmt.where(Payment.created_at >= params.date_from)
    if params.date_to is not None:
        end_date = params.date_to + timedelta(days=1)
        stmt = stmt.where(Payment.created_at < end_date)
    if params.status is not None:
        stmt = stmt.where(Payment.status == params.status)

    return stmt


def apply_payment_sorting(
    stmt: Select[tuple[Payment]], params: PaymentQueryParameters
) -> Select[tuple[Payment]]:
    if params.sort_order == SortOrderEnum.ASC:
        stmt = stmt.order_by(Payment.created_at)
    else:
        stmt = stmt.order_by(Payment.created_at.desc())
    return stmt.order_by(Payment.id)


async def list_payments(
    db: AsyncSession,
    offset: int,
    limit: int,
    params: PaymentQueryParameters,
    user_id: int | None = None,
) -> list[Payment]:
    stmt = apply_payment_filters(stmt=select(Payment), params=params, user_id=user_id)
    stmt = apply_payment_sorting(stmt, params=params)

    stmt = (
        stmt.options(
            selectinload(Payment.items)
            .joinedload(PaymentItem.order_item)
            .joinedload(OrderItem.movie)
        )
        .offset(offset)
        .limit(limit)
    )

    result = await db.scalars(stmt)
    return list(result.all())


async def count_payments(
    db: AsyncSession,
    params: PaymentQueryParameters,
    user_id: int | None = None,
) -> int:
    stmt = apply_payment_filters(stmt=select(Payment), params=params, user_id=user_id)
    total_count = (
        await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )

    return total_count
