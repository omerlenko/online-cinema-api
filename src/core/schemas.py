from datetime import date
from enum import Enum
from typing import Self

from fastapi import HTTPException
from pydantic import BaseModel, model_validator


class HealthResponseSchema(BaseModel):
    status: str
    database: str


class ErrorResponseSchema(BaseModel):
    detail: str


class MessageResponseSchema(BaseModel):
    message: str


class Page[T](BaseModel):
    items: list[T]

    total: int
    page: int
    page_size: int

    previous_page: str | None
    next_page: str | None


class SortOrderEnum(str, Enum):
    ASC = "asc"
    DESC = "desc"


class DateQueryParameters(BaseModel):
    date_from: date | None = None
    date_to: date | None = None

    sort_order: SortOrderEnum = SortOrderEnum.DESC

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.date_to and self.date_from and self.date_to < self.date_from:
            raise HTTPException(
                status_code=422, detail="date_to must be on or after date_from"
            )

        return self
