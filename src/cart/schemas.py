from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.movies.schemas import NameDetailSchema


class CartItemCreateSchema(BaseModel):
    movie_id: int


class CartMovieSchema(BaseModel):
    id: int
    name: str
    year: int
    price: Decimal

    genres: list[NameDetailSchema]

    model_config = ConfigDict(from_attributes=True)


class CartItemDetailSchema(BaseModel):
    movie: CartMovieSchema
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)
