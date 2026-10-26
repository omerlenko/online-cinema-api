from decimal import Decimal
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, Field

from src.core.schemas import SortOrderEnum

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class NameCreateSchema(BaseModel):
    name: Name


class NameDetailSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class GenreWithCountSchema(NameDetailSchema):
    movie_count: int


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


class MovieListItemSchema(BaseModel):
    id: int
    name: str
    year: int
    time: int
    imdb: float
    votes: int
    meta_score: float | None = None
    gross: float | None = None
    price: Decimal

    certification: NameDetailSchema
    genres: list[NameDetailSchema]

    model_config = ConfigDict(from_attributes=True)


class MovieSortField(str, Enum):
    ID = "id"
    NAME = "name"
    YEAR = "year"
    TIME = "time"
    IMDB = "imdb"
    VOTES = "votes"
    META_SCORE = "meta_score"
    GROSS = "gross"
    PRICE = "price"


class MovieQueryParameters(BaseModel):
    year_from: int | None = Field(default=None, ge=1895)
    year_to: int | None = Field(default=None, ge=1895)
    min_imdb: float | None = Field(default=None, ge=0, le=10)
    min_meta_score: float | None = Field(default=None, ge=0, le=100)
    genre_id: int | None = None

    search: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None
    ) = None

    sort_by: MovieSortField = MovieSortField.ID
    order: SortOrderEnum = SortOrderEnum.ASC
