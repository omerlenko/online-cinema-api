from datetime import datetime

from sqlalchemy import func, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped, relationship

from src.accounts.models import User
from src.database.base import Base
from src.movies.models import Movie


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )

    user: Mapped[User] = relationship("User")
    items: Mapped[list["CartItem"]] = relationship(
        "CartItem",
        back_populates="cart",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CartItem(Base):
    __tablename__ = "cart_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"))
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), index=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    cart: Mapped[Cart] = relationship("Cart", back_populates="items")
    movie: Mapped[Movie] = relationship("Movie")

    __table_args__ = (
        UniqueConstraint("cart_id", "movie_id", name="uq_cart_items_cart_id_movie_id"),
    )
