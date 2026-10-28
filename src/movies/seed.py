import asyncio
import sys
from pathlib import Path

from pydantic import ValidationError, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from src.movies import crud
from src.database.session import TaskSession
from src.movies.models import Certification, Genre, Star, Director, UniqueNameBase
from src.movies.schemas import MovieSeedSchema, NameCreateSchema

SEED_DATA_PATH = Path(__file__).parent / "seed_data.json"


async def get_or_create_object_by_name[T: UniqueNameBase](
    db: AsyncSession, model: type[T], name: str
) -> T:
    obj = await crud.get_object_by_name(db=db, model=model, name=name)
    if obj is None:
        obj_data = NameCreateSchema(name=name)
        obj = await crud.create_object(db=db, model=model, data=obj_data)

    return obj


async def seed_movie(db: AsyncSession, movie_data: MovieSeedSchema) -> bool:
    existing_movie = await crud.get_movie_by_name_year_time(
        db=db, name=movie_data.name, year=movie_data.year, time=movie_data.time
    )
    if existing_movie is not None:
        return False

    certification = await get_or_create_object_by_name(
        db=db, model=Certification, name=movie_data.certification
    )

    genres = [
        await get_or_create_object_by_name(db=db, model=Genre, name=name)
        for name in movie_data.genres
    ]
    stars = [
        await get_or_create_object_by_name(db=db, model=Star, name=name)
        for name in movie_data.stars
    ]
    directors = [
        await get_or_create_object_by_name(db=db, model=Director, name=name)
        for name in movie_data.directors
    ]

    await crud.create_movie(
        db=db,
        data=movie_data,
        certification=certification,
        genres=genres,
        stars=stars,
        directors=directors,
    )
    return True


async def _run(movies: list[MovieSeedSchema]) -> list[bool]:
    async with TaskSession() as session:
        results = []
        for movie in movies:
            results.append(await seed_movie(db=session, movie_data=movie))
        await session.commit()
        return results


def load_movies(path: Path) -> list[MovieSeedSchema]:
    return TypeAdapter(list[MovieSeedSchema]).validate_json(path.read_bytes())


def main() -> None:
    try:
        movies = load_movies(SEED_DATA_PATH)
    except ValidationError as exc:
        error = exc.errors()[0]
        sys.exit(f"Validation error at {error["loc"]}: {error["msg"]}")

    results = asyncio.run(_run(movies))

    total_movies = len(movies)
    created_count = sum(results)
    ignored_count = total_movies - created_count

    print("\n--- Seeding Summary ---")
    print(f"Total processed: {total_movies}")
    print(f"Movies created:  {created_count}")
    print(f"Movies ignored:  {ignored_count}")


if __name__ == "__main__":
    main()
