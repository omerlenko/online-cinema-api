from sqlalchemy import select, func, exists, Column, Select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload, joinedload

from src.core.schemas import SortOrderEnum
from src.movies.models import (
    UniqueNameBase,
    Movie,
    Certification,
    Genre,
    Star,
    Director,
    movie_genres,
)
from src.movies.schemas import (
    NameCreateSchema,
    MovieCreateSchema,
    MovieUpdateSchema,
    MovieQueryParameters,
    MovieSortField,
)


async def list_objects[T: UniqueNameBase](db: AsyncSession, model: type[T]) -> list[T]:
    result = await db.scalars(select(model).order_by(model.id))
    return list(result.all())


async def list_genres(db: AsyncSession) -> list[tuple[Genre, int]]:
    result = await db.execute(
        select(Genre, func.count(movie_genres.c.movie_id))
        .outerjoin(movie_genres, movie_genres.c.genre_id == Genre.id)
        .group_by(Genre.id)
        .order_by(Genre.id)
    )
    return list(result.tuples().all())


async def create_object[T: UniqueNameBase](
    db: AsyncSession, model: type[T], data: NameCreateSchema
) -> T:
    obj = model(**data.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)

    return obj


async def get_object_by_id[T: UniqueNameBase](
    db: AsyncSession, model: type[T], object_id: int
) -> T | None:
    obj = await db.scalar(select(model).where(model.id == object_id))
    return obj


async def get_object_by_name[T: UniqueNameBase](
    db: AsyncSession, model: type[T], name: str
) -> T | None:
    obj = await db.scalar(select(model).where(func.lower(model.name) == name.lower()))
    return obj


async def object_has_movies(
    db: AsyncSession,
    link_column: Column[int] | InstrumentedAttribute[int],
    object_id: int,
) -> bool:
    result = await db.execute(select(exists().where(link_column == object_id)))
    return result.scalar_one()


async def update_object[T: UniqueNameBase](
    db: AsyncSession, obj: T, data: NameCreateSchema
) -> T:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.flush()
    await db.refresh(obj)

    return obj


MOVIE_SORT_COLUMNS = {
    MovieSortField.ID: Movie.id,
    MovieSortField.NAME: Movie.name,
    MovieSortField.YEAR: Movie.year,
    MovieSortField.TIME: Movie.time,
    MovieSortField.IMDB: Movie.imdb,
    MovieSortField.VOTES: Movie.votes,
    MovieSortField.META_SCORE: Movie.meta_score,
    MovieSortField.GROSS: Movie.gross,
    MovieSortField.PRICE: Movie.price,
}


def apply_movie_filters(
    stmt: Select[tuple[Movie]], params: MovieQueryParameters
) -> Select[tuple[Movie]]:
    if params.year_from is not None:
        stmt = stmt.where(Movie.year >= params.year_from)
    if params.year_to is not None:
        stmt = stmt.where(Movie.year <= params.year_to)
    if params.min_imdb is not None:
        stmt = stmt.where(Movie.imdb >= params.min_imdb)
    if params.min_meta_score is not None:
        stmt = stmt.where(Movie.meta_score >= params.min_meta_score)
    if params.genre_id is not None:
        stmt = stmt.where(Movie.genres.any(Genre.id == params.genre_id))

    if params.search:
        pattern = f"%{params.search}%"
        stmt = stmt.where(
            or_(
                Movie.name.ilike(pattern),
                Movie.description.ilike(pattern),
                Movie.genres.any(Genre.name.ilike(pattern)),
                Movie.stars.any(Star.name.ilike(pattern)),
                Movie.directors.any(Director.name.ilike(pattern)),
            )
        )
    return stmt


def apply_movie_sorting(
    stmt: Select[tuple[Movie]], params: MovieQueryParameters
) -> Select[tuple[Movie]]:
    if params.order == SortOrderEnum.DESC:
        stmt = stmt.order_by(MOVIE_SORT_COLUMNS[params.sort_by].desc().nulls_last())
    else:
        stmt = stmt.order_by(MOVIE_SORT_COLUMNS[params.sort_by].nulls_last())
    return stmt.order_by(Movie.id)


async def list_movies(
    db: AsyncSession,
    params: MovieQueryParameters,
    offset: int = 0,
    limit: int = 20,
) -> list[Movie]:
    stmt = apply_movie_filters(select(Movie), params)
    stmt = apply_movie_sorting(stmt, params)

    stmt = (
        stmt.options(
            joinedload(Movie.certification),
            selectinload(Movie.genres),
        )
        .offset(offset)
        .limit(limit)
    )
    result = await db.scalars(stmt)
    return list(result.all())


async def count_movies(db: AsyncSession, params: MovieQueryParameters) -> int:
    stmt = apply_movie_filters(select(Movie), params)
    total_count = (
        await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    return total_count


async def get_movie_by_name_year_time(
    db: AsyncSession, name: str, year: int, time: int
) -> Movie | None:
    movie = await db.scalar(
        select(Movie).where(
            func.lower(Movie.name) == name.lower(),
            Movie.year == year,
            Movie.time == time,
        )
    )
    return movie


async def create_movie(
    db: AsyncSession,
    data: MovieCreateSchema,
    certification: Certification,
    genres: list[Genre],
    stars: list[Star],
    directors: list[Director],
) -> Movie:
    movie = Movie(
        **data.model_dump(
            exclude={"certification_id", "genre_ids", "star_ids", "director_ids"}
        ),
        certification=certification,
        genres=genres,
        stars=stars,
        directors=directors,
    )
    db.add(movie)
    await db.flush()

    return movie


async def get_movie_by_id(db: AsyncSession, movie_id: int) -> Movie | None:
    movie = await db.scalar(
        select(Movie)
        .where(Movie.id == movie_id)
        .options(
            joinedload(Movie.certification),
            selectinload(Movie.genres),
            selectinload(Movie.stars),
            selectinload(Movie.directors),
        )
    )
    return movie


async def get_objects_by_ids[T: UniqueNameBase](
    db: AsyncSession, model: type[T], object_ids: list[int]
) -> list[T]:
    result = await db.scalars(select(model).where(model.id.in_(object_ids)))
    return list(result.all())


async def update_movie(
    db: AsyncSession, movie: Movie, data: MovieUpdateSchema
) -> Movie:
    for field, value in data.model_dump(
        exclude_unset=True,
        exclude_none=True,
        exclude={"certification_id", "genre_ids", "star_ids", "director_ids"},
    ).items():
        setattr(movie, field, value)
    await db.flush()

    return movie
