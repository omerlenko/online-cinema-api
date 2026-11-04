import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, DateTime, ForeignKey, UniqueConstraint, Enum, DECIMAL
from sqlalchemy.orm import mapped_column, Mapped, relationship

from src.accounts.models import User
from src.database.base import Base
from src.movies.models import Movie


class OrderStatusEnum(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELED = "canceled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    status: Mapped[OrderStatusEnum] = mapped_column(
        Enum(OrderStatusEnum),
        default=OrderStatusEnum.PENDING,
        server_default="PENDING",
    )
    total_amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))

    user: Mapped[User] = relationship("User")
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="RESTRICT"), index=True
    )
    price_at_order: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))

    order: Mapped[Order] = relationship("Order", back_populates="items")
    movie: Mapped[Movie] = relationship("Movie")

    __table_args__ = (
        UniqueConstraint(
            "order_id", "movie_id", name="uq_order_items_order_id_movie_id"
        ),
    )
