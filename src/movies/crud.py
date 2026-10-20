from sqlalchemy import select, func, exists, Column
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from src.movies.models import UniqueNameBase
from src.movies.schemas import NameCreateSchema


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
