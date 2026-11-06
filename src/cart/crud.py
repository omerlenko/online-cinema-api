from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.cart.models import Cart, CartItem
from src.movies.models import Movie


async def get_cart_by_user_id(
    db: AsyncSession, user_id: int, locked: bool = False
) -> Cart | None:
    stmt = select(Cart).where(Cart.user_id == user_id)
    if locked:
        stmt = stmt.with_for_update()
    cart = await db.scalar(stmt)
    return cart


async def get_or_create_cart(db: AsyncSession, user_id: int) -> Cart:
    await db.execute(
        insert(Cart)
        .values(user_id=user_id)
        .on_conflict_do_nothing(index_elements=[Cart.user_id])
    )

    cart = await db.scalars(select(Cart).where(Cart.user_id == user_id))
    return cart.one()


async def get_cart_item(
    db: AsyncSession,
    cart_id: int,
    movie_id: int,
) -> CartItem | None:
    cart_item = await db.scalar(
        select(CartItem).where(
            CartItem.cart_id == cart_id, CartItem.movie_id == movie_id
        )
    )
    return cart_item


async def list_cart_items(
    db: AsyncSession,
    cart_id: int,
) -> list[CartItem]:
    stmt = (
        select(CartItem)
        .where(CartItem.cart_id == cart_id)
        .options(selectinload(CartItem.movie).selectinload(Movie.genres))
        .order_by(CartItem.id)
    )

    result = await db.scalars(stmt)
    return list(result.all())


async def create_cart_item(db: AsyncSession, cart_id: int, movie: Movie) -> CartItem:
    cart_item = CartItem(cart_id=cart_id, movie=movie)
    db.add(cart_item)
    await db.flush()

    return cart_item


async def delete_cart_items_by_cart_id(db: AsyncSession, cart_id: int) -> None:
    await db.execute(delete(CartItem).where(CartItem.cart_id == cart_id))
    await db.flush()


async def count_carts_with_movie(db: AsyncSession, movie_id: int) -> int:
    result = await db.execute(select(func.count()).where(CartItem.movie_id == movie_id))
    return result.scalar_one()
