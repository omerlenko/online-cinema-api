from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    AliasPath,
)

from src.core.schemas import DateQueryParameters
from src.payments.models import PaymentStatusEnum


class PaymentItemMovieSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class PaymentItemSchema(BaseModel):
    movie: PaymentItemMovieSchema = Field(
        validation_alias=AliasPath("order_item", "movie")
    )
    price_at_payment: Decimal

    model_config = ConfigDict(from_attributes=True, validate_by_name=True)


class PaymentDetailSchema(BaseModel):
    id: int
    created_at: datetime
    status: PaymentStatusEnum
    amount: Decimal
    order_id: int
    items: list[PaymentItemSchema]

    model_config = ConfigDict(from_attributes=True)


class AdminPaymentDetailSchema(PaymentDetailSchema):
    user_id: int


class PaymentQueryParameters(DateQueryParameters):
    status: PaymentStatusEnum | None = None


class AdminPaymentQueryParameters(PaymentQueryParameters):
    user_id: int | None = None
