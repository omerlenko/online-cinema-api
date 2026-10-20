from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

from src.core.schemas import ErrorResponseSchema
from src.accounts.dependencies import ModeratorUserDep
from src.database.session import DbDep
from src.movies import crud
from src.movies.models import Genre, movie_genres, Star, movie_stars
from src.movies.schemas import (
    NameCreateSchema,
    NameReadSchema,
)

router = APIRouter()


@router.get("/genres", summary="List genres", tags=["genres"])
async def list_genres(db: DbDep) -> list[NameReadSchema]:
    """
    List genres in id order. Public.
    """
    genres = await crud.list_objects(db=db, model=Genre)
    return [NameReadSchema.model_validate(genre) for genre in genres]


@router.post(
    "/genres",
    status_code=201,
    summary="Create a genre",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        409: {"model": ErrorResponseSchema, "description": "Genre already exists."},
    },
    tags=["genres"],
)
async def create_genre(
    db: DbDep, genre_data: NameCreateSchema, moderator: ModeratorUserDep
) -> NameReadSchema:
    """
    Create a genre. Moderator/Admin only.
    """
    genre = await crud.get_object_by_name(db=db, model=Genre, name=genre_data.name)
    if genre is not None:
        raise HTTPException(
            status_code=409, detail="Genre with this name already exists"
        )

    try:
        genre = await crud.create_object(db=db, model=Genre, data=genre_data)
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Genre with this name already exists"
        )
    await db.commit()

    return NameReadSchema.model_validate(genre)


@router.delete(
    "/genres/{genre_id}",
    status_code=204,
    summary="Delete a genre",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        404: {"model": ErrorResponseSchema, "description": "Genre not found."},
        409: {
            "model": ErrorResponseSchema,
            "description": "Genre cannot be deleted "
            "while connected to existing movies.",
        },
    },
    tags=["genres"],
)
async def delete_genre(db: DbDep, genre_id: int, moderator: ModeratorUserDep) -> None:
    """
    Delete a genre. Moderator/Admin only.
    """
    genre = await crud.get_object_by_id(db=db, model=Genre, object_id=genre_id)
    if genre is None:
        raise HTTPException(status_code=404, detail="Genre not found")

    if await crud.object_has_movies(
        db=db, link_column=movie_genres.c.genre_id, object_id=genre_id
    ):
        raise HTTPException(
            status_code=409, detail="Genre cannot be deleted while in use"
        )
    await db.delete(genre)
    await db.commit()


@router.put(
    "/genres/{genre_id}",
    summary="Update a genre",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        404: {"model": ErrorResponseSchema, "description": "Genre not found."},
        409: {
            "model": ErrorResponseSchema,
            "description": "Genre with this name already exists.",
        },
    },
    tags=["genres"],
)
async def update_genre(
    db: DbDep, genre_id: int, genre_data: NameCreateSchema, moderator: ModeratorUserDep
) -> NameReadSchema:
    """
    Update a genre. Moderator/Admin only.
    """
    genre = await crud.get_object_by_id(db=db, model=Genre, object_id=genre_id)
    if genre is None:
        raise HTTPException(status_code=404, detail="Genre not found")

    existing_genre = await crud.get_object_by_name(
        db=db, model=Genre, name=genre_data.name
    )
    if existing_genre is not None and existing_genre.id != genre_id:
        raise HTTPException(
            status_code=409, detail="Genre with this name already exists"
        )

    try:
        genre = await crud.update_object(db=db, obj=genre, data=genre_data)
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Genre with this name already exists"
        )
    await db.commit()

    return NameReadSchema.model_validate(genre)


@router.get("/stars", summary="List stars", tags=["stars"])
async def list_stars(db: DbDep) -> list[NameReadSchema]:
    """
    List stars in id order. Public.
    """
    stars = await crud.list_objects(db=db, model=Star)
    return [NameReadSchema.model_validate(star) for star in stars]


@router.post(
    "/stars",
    status_code=201,
    summary="Create a star",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        409: {"model": ErrorResponseSchema, "description": "Star already exists."},
    },
    tags=["stars"],
)
async def create_star(
    db: DbDep, star_data: NameCreateSchema, moderator: ModeratorUserDep
) -> NameReadSchema:
    """
    Create a star. Moderator/Admin only.
    """
    star = await crud.get_object_by_name(db=db, model=Star, name=star_data.name)
    if star is not None:
        raise HTTPException(
            status_code=409, detail="Star with this name already exists"
        )

    try:
        star = await crud.create_object(db=db, model=Star, data=star_data)
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Star with this name already exists"
        )
    await db.commit()

    return NameReadSchema.model_validate(star)


@router.delete(
    "/stars/{star_id}",
    status_code=204,
    summary="Delete a star",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        404: {"model": ErrorResponseSchema, "description": "Star not found."},
        409: {
            "model": ErrorResponseSchema,
            "description": "Star cannot be deleted "
            "while connected to existing movies.",
        },
    },
    tags=["stars"],
)
async def delete_star(db: DbDep, star_id: int, moderator: ModeratorUserDep) -> None:
    """
    Delete a star. Moderator/Admin only.
    """
    star = await crud.get_object_by_id(db=db, model=Star, object_id=star_id)
    if star is None:
        raise HTTPException(status_code=404, detail="Star not found")

    if await crud.object_has_movies(
        db=db, link_column=movie_stars.c.star_id, object_id=star_id
    ):
        raise HTTPException(
            status_code=409, detail="Star cannot be deleted while in use"
        )
    await db.delete(star)
    await db.commit()


@router.put(
    "/stars/{star_id}",
    summary="Update a star",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        404: {"model": ErrorResponseSchema, "description": "Star not found."},
        409: {
            "model": ErrorResponseSchema,
            "description": "Star with this name already exists.",
        },
    },
    tags=["stars"],
)
async def update_star(
    db: DbDep, star_id: int, star_data: NameCreateSchema, moderator: ModeratorUserDep
) -> NameReadSchema:
    """
    Update a star. Moderator/Admin only.
    """
    star = await crud.get_object_by_id(db=db, model=Star, object_id=star_id)
    if star is None:
        raise HTTPException(status_code=404, detail="Star not found")

    existing_star = await crud.get_object_by_name(
        db=db, model=Star, name=star_data.name
    )
    if existing_star is not None and existing_star.id != star_id:
        raise HTTPException(
            status_code=409, detail="Star with this name already exists"
        )

    try:
        star = await crud.update_object(db=db, obj=star, data=star_data)
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Star with this name already exists"
        )
    await db.commit()

    return NameReadSchema.model_validate(star)
