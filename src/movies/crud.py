from sqlalchemy import select, func, exists
from sqlalchemy.ext.asyncio import AsyncSession

from src.movies.models import Genre, movie_genres
from src.movies.schemas import GenreCreateSchema


async def create_genre(db: AsyncSession, data: GenreCreateSchema) -> Genre:
    genre = Genre(**data.model_dump())
    db.add(genre)
    await db.flush()
    await db.refresh(genre)

    return genre


async def get_genre_by_id(db: AsyncSession, genre_id: int) -> Genre | None:
    genre = await db.scalar(select(Genre).where(Genre.id == genre_id))
    return genre


async def genre_has_movies(db: AsyncSession, genre_id: int) -> bool:
    result = await db.execute(
        select(exists().where(movie_genres.c.genre_id == genre_id))
    )
    return result.scalar_one()


async def get_genre_by_name(db: AsyncSession, name: str) -> Genre | None:
    genre = await db.scalar(select(Genre).where(func.lower(Genre.name) == name.lower()))
    return genre


async def get_genres_list(db: AsyncSession) -> list[Genre]:
    result = await db.scalars(select(Genre).order_by(Genre.id))
    return list(result.all())


async def update_genre(
    db: AsyncSession, genre: Genre, data: GenreCreateSchema
) -> Genre:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(genre, field, value)
    await db.flush()
    await db.refresh(genre)

    return genre
