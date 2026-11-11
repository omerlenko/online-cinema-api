import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, DateTime, ForeignKey, UniqueConstraint, Enum, DECIMAL
from sqlalchemy.orm import mapped_column, Mapped, relationship

from src.accounts.models import User
from src.database.base import Base
from src.orders.models import Order, OrderItem


class PaymentStatusEnum(str, enum.Enum):
    SUCCESSFUL = "successful"
    CANCELED = "canceled"
    REFUNDED = "refunded"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    status: Mapped[PaymentStatusEnum] = mapped_column(
        Enum(PaymentStatusEnum),
        default=PaymentStatusEnum.SUCCESSFUL,
        server_default="SUCCESSFUL",
    )
    amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    external_payment_id: Mapped[str] = mapped_column(unique=True)

    user: Mapped[User] = relationship("User")
    order: Mapped[Order] = relationship("Order")
    items: Mapped[list["PaymentItem"]] = relationship(
        "PaymentItem",
        back_populates="payment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PaymentItem.id",
    )


class PaymentItem(Base):
    __tablename__ = "payment_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE")
    )
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="RESTRICT")
    )
    price_at_payment: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))

    payment: Mapped[Payment] = relationship("Payment", back_populates="items")
    order_item: Mapped[OrderItem] = relationship("OrderItem")

    __table_args__ = (
        UniqueConstraint(
            "payment_id",
            "order_item_id",
            name="uq_payment_items_payment_id_order_item_id",
        ),
    )
