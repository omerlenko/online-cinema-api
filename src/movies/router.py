from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

from src.core.schemas import ErrorResponseSchema
from src.accounts.dependencies import ModeratorUserDep
from src.database.session import DbDep
from src.movies import crud
from src.movies.schemas import GenreCreateSchema, GenreReadSchema

router = APIRouter()


@router.get("/genres", summary="List genres", tags=["genres"])
async def list_genres(db: DbDep) -> list[GenreReadSchema]:
    """
    List genres in id order. Public.
    """
    genres = await crud.get_genres_list(db=db)
    return [GenreReadSchema.model_validate(genre) for genre in genres]


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
    db: DbDep, genre_data: GenreCreateSchema, moderator: ModeratorUserDep
) -> GenreReadSchema:
    """
    Create a genre. Moderator/Admin only.
    """
    genre = await crud.get_genre_by_name(db=db, name=genre_data.name)
    if genre is not None:
        raise HTTPException(
            status_code=409, detail="Genre with this name already exists"
        )

    try:
        genre = await crud.create_genre(db=db, data=genre_data)
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Genre with this name already exists"
        )
    await db.commit()

    return GenreReadSchema.model_validate(genre)


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
    genre = await crud.get_genre_by_id(db=db, genre_id=genre_id)
    if genre is None:
        raise HTTPException(status_code=404, detail="Genre not found")

    if await crud.genre_has_movies(db=db, genre_id=genre_id):
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
    db: DbDep, genre_id: int, genre_data: GenreCreateSchema, moderator: ModeratorUserDep
) -> GenreReadSchema:
    """
    Update a genre. Moderator/Admin only.
    """
    genre = await crud.get_genre_by_id(db=db, genre_id=genre_id)
    if genre is None:
        raise HTTPException(status_code=404, detail="Genre not found")

    existing_genre = await crud.get_genre_by_name(db=db, name=genre_data.name)
    if existing_genre is not None and existing_genre.id != genre_id:
        raise HTTPException(
            status_code=409, detail="Genre with this name already exists"
        )

    try:
        genre = await crud.update_genre(db=db, genre=genre, data=genre_data)
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Genre with this name already exists"
        )
    await db.commit()

    return GenreReadSchema.model_validate(genre)
