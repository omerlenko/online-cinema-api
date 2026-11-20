from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from src.core.schemas import DateQueryParameters
from src.orders.models import OrderStatusEnum


class ExcludedMovieReasonEnum(str, Enum):
    PURCHASED = "already_purchased"
    PENDING = "in_pending_order"


class OrderMovieSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class ExcludedMovieSchema(OrderMovieSchema):
    reason: ExcludedMovieReasonEnum


class OrderItemSchema(BaseModel):
    movie: OrderMovieSchema
    price_at_order: Decimal

    model_config = ConfigDict(from_attributes=True)


class OrderDetailSchema(BaseModel):
    id: int
    created_at: datetime
    status: OrderStatusEnum
    total_amount: Decimal
    items: list[OrderItemSchema]

    model_config = ConfigDict(from_attributes=True)


class AdminOrderDetailSchema(OrderDetailSchema):
    user_id: int


class OrderCreateResponseSchema(BaseModel):
    order: OrderDetailSchema
    excluded_movies: list[ExcludedMovieSchema]


class OrderQueryParameters(DateQueryParameters):
    status: OrderStatusEnum | None = None

    search: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None
    ) = None


class AdminOrderQueryParameters(OrderQueryParameters):
    user_id: int | None = None


class CheckoutResponseSchema(BaseModel):
    checkout_url: str
