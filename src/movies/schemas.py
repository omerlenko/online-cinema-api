from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, Field

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class NameCreateSchema(BaseModel):
    name: Name


class NameDetailSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class MovieCreateSchema(BaseModel):
    name: Name
    year: int = Field(ge=1895)
    time: int = Field(ge=1)
    imdb: float = Field(ge=0, le=10)
    votes: int = Field(ge=0)
    meta_score: float | None = Field(default=None, ge=0, le=100)
    gross: float | None = None
    description: str
    price: Decimal = Field(ge=0)

    certification_id: int
    genre_ids: list[int]
    star_ids: list[int]
    director_ids: list[int]


class MovieUpdateSchema(BaseModel):
    name: Name | None = None
    year: int | None = Field(default=None, ge=1895)
    time: int | None = Field(default=None, ge=1)
    imdb: float | None = Field(default=None, ge=0, le=10)
    votes: int | None = Field(default=None, ge=0)
    meta_score: float | None = Field(default=None, ge=0, le=100)
    gross: float | None = None
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=0)

    certification_id: int | None = None
    genre_ids: list[int] | None = None
    star_ids: list[int] | None = None
    director_ids: list[int] | None = None


class MovieDetailSchema(BaseModel):
    id: int
    uuid: UUID
    name: str
    year: int
    time: int
    imdb: float
    votes: int
    meta_score: float | None = None
    gross: float | None = None
    description: str
    price: Decimal

    certification: NameDetailSchema
    genres: list[NameDetailSchema]
    stars: list[NameDetailSchema]
    directors: list[NameDetailSchema]

    model_config = ConfigDict(from_attributes=True)
