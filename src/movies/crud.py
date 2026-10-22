from sqlalchemy import select, func, exists, Column
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload, joinedload

from src.movies.models import (
    UniqueNameBase,
    Movie,
    Certification,
    Genre,
    Star,
    Director,
)
from src.movies.schemas import NameCreateSchema, MovieCreateSchema, MovieUpdateSchema


async def list_objects[T: UniqueNameBase](db: AsyncSession, model: type[T]) -> list[T]:
    result = await db.scalars(select(model).order_by(model.id))
    return list(result.all())


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


async def list_movies(db: AsyncSession) -> list[Movie]:
    result = await db.scalars(
        select(Movie)
        .options(
            joinedload(Movie.certification),
            selectinload(Movie.genres),
            selectinload(Movie.stars),
            selectinload(Movie.directors),
        )
        .order_by(Movie.id)
    )
    return list(result.all())


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
