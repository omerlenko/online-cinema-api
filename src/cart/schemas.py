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
    id: int
    movie: CartMovieSchema

    model_config = ConfigDict(from_attributes=True)
