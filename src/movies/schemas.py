from decimal import Decimal
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, Field

from src.core.schemas import SortOrderEnum

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]

Year = Annotated[int, Field(ge=1895, le=2100)]
Time = Annotated[int, Field(ge=1, le=600)]
Imdb = Annotated[float, Field(ge=0, le=10)]
Votes = Annotated[int, Field(ge=0, le=2**31 - 1)]
MetaScore = Annotated[float, Field(ge=0, le=100)]
Price = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]


class NameCreateSchema(BaseModel):
    name: Name


class NameDetailSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class GenreWithCountSchema(NameDetailSchema):
    movie_count: int


class MovieBaseSchema(BaseModel):
    name: Name
    year: Year
    time: Time
    imdb: Imdb
    votes: Votes
    meta_score: MetaScore | None = None
    gross: float | None = None
    description: str
    price: Price


class MovieSeedSchema(MovieBaseSchema):
    certification: Name
    genres: list[Name]
    stars: list[Name]
    directors: list[Name]


class MovieCreateSchema(MovieBaseSchema):
    certification_id: int
    genre_ids: list[int]
    star_ids: list[int]
    director_ids: list[int]


class MovieUpdateSchema(BaseModel):
    name: Name | None = None
    year: Year | None = None
    time: Time | None = None
    imdb: Imdb | None = None
    votes: Votes | None = None
    meta_score: MetaScore | None = None
    gross: float | None = None
    description: str | None = None
    price: Price | None = None

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
