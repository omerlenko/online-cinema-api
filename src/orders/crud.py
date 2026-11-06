from datetime import timedelta

from sqlalchemy import select, func, Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.schemas import SortOrderEnum
from src.movies.models import Movie
from src.orders.models import Order, OrderItem, OrderStatusEnum
from src.orders.schemas import OrderQueryParameters


async def get_movie_ids_by_order_status(
    db: AsyncSession, user_id: int, status: OrderStatusEnum, movie_ids: list[int]
) -> set[int]:
    stmt = (
        select(OrderItem.movie_id)
        .join(Order)
        .where(
            OrderItem.movie_id.in_(movie_ids),
            Order.user_id == user_id,
            Order.status == status,
        )
    )
    result = await db.scalars(stmt)
    return set(result.all())


def apply_order_filters(
    stmt: Select[tuple[Order]], params: OrderQueryParameters, user_id: int | None
) -> Select[tuple[Order]]:
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    if params.date_from is not None:
        stmt = stmt.where(Order.created_at >= params.date_from)
    if params.date_to is not None:
        end_date = params.date_to + timedelta(days=1)
        stmt = stmt.where(Order.created_at < end_date)
    if params.status is not None:
        stmt = stmt.where(Order.status == params.status)

    if params.search:
        pattern = f"%{params.search}%"
        stmt = stmt.where(
            Order.items.any(OrderItem.movie.has(Movie.name.ilike(pattern)))
        )
    return stmt


def apply_order_sorting(
    stmt: Select[tuple[Order]], params: OrderQueryParameters
) -> Select[tuple[Order]]:
    if params.sort_order == SortOrderEnum.ASC:
        stmt = stmt.order_by(Order.created_at)
    else:
        stmt = stmt.order_by(Order.created_at.desc())
    return stmt.order_by(Order.id)


async def list_orders(
    db: AsyncSession,
    offset: int,
    limit: int,
    params: OrderQueryParameters,
    user_id: int | None = None,
) -> list[Order]:
    stmt = apply_order_filters(stmt=select(Order), params=params, user_id=user_id)
    stmt = apply_order_sorting(stmt, params=params)

    stmt = (
        stmt.options(selectinload(Order.items).selectinload(OrderItem.movie))
        .offset(offset)
        .limit(limit)
    )

    result = await db.scalars(stmt)
    return list(result.all())


async def count_orders(
    db: AsyncSession,
    params: OrderQueryParameters,
    user_id: int | None = None,
) -> int:
    stmt = apply_order_filters(stmt=select(Order), params=params, user_id=user_id)
    total_count = (
        await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )

    return total_count


async def create_order(db: AsyncSession, user_id: int, movies: list[Movie]) -> Order:
    total_amount = sum(movie.price for movie in movies)
    order_items = [
        OrderItem(movie=movie, price_at_order=movie.price) for movie in movies
    ]
    order = Order(user_id=user_id, total_amount=total_amount, items=order_items)
    db.add(order)
    await db.flush()

    return order


async def get_order_by_id(
    db: AsyncSession, order_id: int, user_id: int
) -> Order | None:
    order = await db.scalar(
        select(Order)
        .where(Order.id == order_id, Order.user_id == user_id)
        .options(selectinload(Order.items).selectinload(OrderItem.movie))
    )
    return order


async def count_orders_with_movie(db: AsyncSession, movie_id: int) -> int:
    result = await db.execute(
        select(func.count()).where(OrderItem.movie_id == movie_id)
    )
    return result.scalar_one()
