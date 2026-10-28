from enum import Enum

from pydantic import BaseModel


class HealthResponseSchema(BaseModel):
    status: str
    database: str


class ErrorResponseSchema(BaseModel):
    detail: str


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
