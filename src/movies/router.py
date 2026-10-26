from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.pagination import PaginationDep
from src.core.schemas import ErrorResponseSchema, Page
from src.accounts.dependencies import ModeratorUserDep
from src.database.session import DbDep
from src.movies import crud
from src.movies.models import (
    Genre,
    movie_genres,
    Star,
    movie_stars,
    Director,
    movie_directors,
    Certification,
    Movie,
    UniqueNameBase,
)
from src.movies.schemas import (
    NameCreateSchema,
    NameDetailSchema,
    MovieDetailSchema,
    MovieCreateSchema,
    MovieUpdateSchema,
    MovieQueryParameters,
    GenreWithCountSchema,
    MovieListItemSchema,
)

router = APIRouter()


async def get_all_objects_or_400[T: UniqueNameBase](
    db: AsyncSession, model: type[T], ids: list[int], label: str
) -> list[T]:
    objects = await crud.get_objects_by_ids(db=db, model=model, object_ids=ids)
    missing_ids = set(ids) - {obj.id for obj in objects}
    if missing_ids:
        raise HTTPException(
            status_code=400,
            detail=f"{label} with these ids not found: {sorted(missing_ids)}",
        )
    return objects


@router.get("/genres", summary="List genres", tags=["genres"])
async def list_genres(db: DbDep) -> list[GenreWithCountSchema]:
    """
    List genres in id order. Public.

    Shows the number of movies in each genre.
    """
    genres = await crud.list_genres(db=db)
    return [
        GenreWithCountSchema(id=genre.id, name=genre.name, movie_count=count)
        for genre, count in genres
    ]


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
) -> NameDetailSchema:
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

    return NameDetailSchema.model_validate(genre)


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
) -> NameDetailSchema:
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

    return NameDetailSchema.model_validate(genre)


@router.get("/stars", summary="List stars", tags=["stars"])
async def list_stars(db: DbDep) -> list[NameDetailSchema]:
    """
    List stars in id order. Public.
    """
    stars = await crud.list_objects(db=db, model=Star)
    return [NameDetailSchema.model_validate(star) for star in stars]


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
) -> NameDetailSchema:
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

    return NameDetailSchema.model_validate(star)


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
) -> NameDetailSchema:
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

    return NameDetailSchema.model_validate(star)


@router.get("/directors", summary="List directors", tags=["directors"])
async def list_directors(db: DbDep) -> list[NameDetailSchema]:
    """
    List directors in id order. Public.
    """
    directors = await crud.list_objects(db=db, model=Director)
    return [NameDetailSchema.model_validate(director) for director in directors]


@router.post(
    "/directors",
    status_code=201,
    summary="Create a director",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        409: {"model": ErrorResponseSchema, "description": "Director already exists."},
    },
    tags=["directors"],
)
async def create_director(
    db: DbDep, director_data: NameCreateSchema, moderator: ModeratorUserDep
) -> NameDetailSchema:
    """
    Create a director. Moderator/Admin only.
    """
    director = await crud.get_object_by_name(
        db=db, model=Director, name=director_data.name
    )
    if director is not None:
        raise HTTPException(
            status_code=409, detail="Director with this name already exists"
        )

    try:
        director = await crud.create_object(db=db, model=Director, data=director_data)
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Director with this name already exists"
        )
    await db.commit()

    return NameDetailSchema.model_validate(director)


@router.delete(
    "/directors/{director_id}",
    status_code=204,
    summary="Delete a director",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        404: {"model": ErrorResponseSchema, "description": "Director not found."},
        409: {
            "model": ErrorResponseSchema,
            "description": "Director cannot be deleted "
            "while connected to existing movies.",
        },
    },
    tags=["directors"],
)
async def delete_director(
    db: DbDep, director_id: int, moderator: ModeratorUserDep
) -> None:
    """
    Delete a director. Moderator/Admin only.
    """
    director = await crud.get_object_by_id(db=db, model=Director, object_id=director_id)
    if director is None:
        raise HTTPException(status_code=404, detail="Director not found")

    if await crud.object_has_movies(
        db=db, link_column=movie_directors.c.director_id, object_id=director_id
    ):
        raise HTTPException(
            status_code=409, detail="Director cannot be deleted while in use"
        )
    await db.delete(director)
    await db.commit()


@router.put(
    "/directors/{director_id}",
    summary="Update a director",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        404: {"model": ErrorResponseSchema, "description": "Director not found."},
        409: {
            "model": ErrorResponseSchema,
            "description": "Director with this name already exists.",
        },
    },
    tags=["directors"],
)
async def update_director(
    db: DbDep,
    director_id: int,
    director_data: NameCreateSchema,
    moderator: ModeratorUserDep,
) -> NameDetailSchema:
    """
    Update a director. Moderator/Admin only.
    """
    director = await crud.get_object_by_id(db=db, model=Director, object_id=director_id)
    if director is None:
        raise HTTPException(status_code=404, detail="Director not found")

    existing_director = await crud.get_object_by_name(
        db=db, model=Director, name=director_data.name
    )
    if existing_director is not None and existing_director.id != director_id:
        raise HTTPException(
            status_code=409, detail="Director with this name already exists"
        )

    try:
        director = await crud.update_object(db=db, obj=director, data=director_data)
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Director with this name already exists"
        )
    await db.commit()

    return NameDetailSchema.model_validate(director)


@router.get("/certifications", summary="List certifications", tags=["certifications"])
async def list_certifications(db: DbDep) -> list[NameDetailSchema]:
    """
    List certifications in id order. Public.
    """
    certifications = await crud.list_objects(db=db, model=Certification)
    return [
        NameDetailSchema.model_validate(certification)
        for certification in certifications
    ]


@router.post(
    "/certifications",
    status_code=201,
    summary="Create a certification",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        409: {
            "model": ErrorResponseSchema,
            "description": "Certification already exists.",
        },
    },
    tags=["certifications"],
)
async def create_certification(
    db: DbDep, certification_data: NameCreateSchema, moderator: ModeratorUserDep
) -> NameDetailSchema:
    """
    Create a certification. Moderator/Admin only.
    """
    certification = await crud.get_object_by_name(
        db=db, model=Certification, name=certification_data.name
    )
    if certification is not None:
        raise HTTPException(
            status_code=409, detail="Certification with this name already exists"
        )

    try:
        certification = await crud.create_object(
            db=db, model=Certification, data=certification_data
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Certification with this name already exists"
        )
    await db.commit()

    return NameDetailSchema.model_validate(certification)


@router.delete(
    "/certifications/{certification_id}",
    status_code=204,
    summary="Delete a certification",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        404: {"model": ErrorResponseSchema, "description": "Certification not found."},
        409: {
            "model": ErrorResponseSchema,
            "description": "Certification cannot be deleted "
            "while connected to existing movies.",
        },
    },
    tags=["certifications"],
)
async def delete_certification(
    db: DbDep, certification_id: int, moderator: ModeratorUserDep
) -> None:
    """
    Delete a certification. Moderator/Admin only.
    """
    certification = await crud.get_object_by_id(
        db=db, model=Certification, object_id=certification_id
    )
    if certification is None:
        raise HTTPException(status_code=404, detail="Certification not found")

    if await crud.object_has_movies(
        db=db, link_column=Movie.certification_id, object_id=certification_id
    ):
        raise HTTPException(
            status_code=409, detail="Certification cannot be deleted while in use"
        )
    await db.delete(certification)
    await db.commit()


@router.put(
    "/certifications/{certification_id}",
    summary="Update a certification",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        404: {"model": ErrorResponseSchema, "description": "Certification not found."},
        409: {
            "model": ErrorResponseSchema,
            "description": "Certification with this name already exists.",
        },
    },
    tags=["certifications"],
)
async def update_certification(
    db: DbDep,
    certification_id: int,
    certification_data: NameCreateSchema,
    moderator: ModeratorUserDep,
) -> NameDetailSchema:
    """
    Update a certification. Moderator/Admin only.
    """
    certification = await crud.get_object_by_id(
        db=db, model=Certification, object_id=certification_id
    )
    if certification is None:
        raise HTTPException(status_code=404, detail="Certification not found")

    existing_certification = await crud.get_object_by_name(
        db=db, model=Certification, name=certification_data.name
    )
    if (
        existing_certification is not None
        and existing_certification.id != certification_id
    ):
        raise HTTPException(
            status_code=409, detail="Certification with this name already exists"
        )

    try:
        certification = await crud.update_object(
            db=db, obj=certification, data=certification_data
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Certification with this name already exists"
        )
    await db.commit()

    return NameDetailSchema.model_validate(certification)


@router.get("", summary="List movies", tags=["movies"])
async def list_movies(
    db: DbDep,
    pagination: PaginationDep,
    params: Annotated[MovieQueryParameters, Depends()],
) -> Page[MovieListItemSchema]:
    """
    List movies. Public.

    Filter movies by year range, minimum IMDB or MetaScore rating and genre,
    using 'year_from', 'year_to', 'min_imdb', 'min_meta_score' and 'genre_id'
    query parameters.

    Search movies by matches in their name, description, genres, actors
    and directors, using 'search' query parameter.

    Sort movies by id(default), name, year, duration, IMDB rating,
    votes (popularity), MetaScore rating, gross earnings, price,
    using 'sort_by' and 'order' with 'asc'(default) or 'desc'
    for ascending or descending order.

    Use `page` and `page_size` to page through the results (at most 100 per request).
    """
    movies = await crud.list_movies(
        db=db, offset=pagination.offset, limit=pagination.page_size, params=params
    )
    items = [MovieListItemSchema.model_validate(movie) for movie in movies]
    total = await crud.count_movies(db=db, params=params)

    return pagination.get_page(items=items, total=total)


@router.get(
    "/{movie_id}",
    summary="Get movie details",
    responses={
        404: {
            "model": ErrorResponseSchema,
            "description": "Movie not found.",
        },
    },
    tags=["movies"],
)
async def get_movie_details(db: DbDep, movie_id: int) -> MovieDetailSchema:
    """
    Get movie details. Public.
    """
    movie = await crud.get_movie_by_id(db=db, movie_id=movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    return MovieDetailSchema.model_validate(movie)


@router.post(
    "",
    status_code=201,
    summary="Create a movie",
    responses={
        400: {
            "model": ErrorResponseSchema,
            "description": "One or more of genres, stars, directors "
            "or a certification is not found.",
        },
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        409: {
            "model": ErrorResponseSchema,
            "description": "Movie with this name, year and duration already exists.",
        },
    },
    tags=["movies"],
)
async def create_movie(
    db: DbDep, movie_data: MovieCreateSchema, moderator: ModeratorUserDep
) -> MovieDetailSchema:
    """
    Create a movie. Moderator/Admin only.
    """
    movie = await crud.get_movie_by_name_year_time(
        db=db, name=movie_data.name, year=movie_data.year, time=movie_data.time
    )
    if movie is not None:
        raise HTTPException(
            status_code=409,
            detail="Movie with this name, year and duration already exists.",
        )

    certification = await crud.get_object_by_id(
        db=db, model=Certification, object_id=movie_data.certification_id
    )
    if certification is None:
        raise HTTPException(status_code=400, detail="Certification not found")

    genres = await get_all_objects_or_400(
        db=db, model=Genre, ids=movie_data.genre_ids, label="Genres"
    )
    stars = await get_all_objects_or_400(
        db=db, model=Star, ids=movie_data.star_ids, label="Stars"
    )
    directors = await get_all_objects_or_400(
        db=db, model=Director, ids=movie_data.director_ids, label="Directors"
    )

    try:
        movie = await crud.create_movie(
            db=db,
            data=movie_data,
            certification=certification,
            genres=genres,
            stars=stars,
            directors=directors,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Movie with this name, year and duration already exists.",
        )
    await db.commit()

    return MovieDetailSchema.model_validate(movie)


@router.delete(
    "/{movie_id}",
    status_code=204,
    summary="Delete a movie",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        404: {"model": ErrorResponseSchema, "description": "Movie not found."},
    },
    tags=["movies"],
)
async def delete_movie(db: DbDep, movie_id: int, moderator: ModeratorUserDep) -> None:
    """
    Delete a movie. Moderator/Admin only.
    """
    movie = await crud.get_movie_by_id(db=db, movie_id=movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    await db.delete(movie)
    await db.commit()


@router.patch(
    "/{movie_id}",
    summary="Update a movie",
    responses={
        400: {
            "model": ErrorResponseSchema,
            "description": "One or more of genres, stars, directors "
            "or a certification is not found.",
        },
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin or moderator.",
        },
        404: {"model": ErrorResponseSchema, "description": "Movie not found."},
        409: {
            "model": ErrorResponseSchema,
            "description": "Movie with this name, year and duration already exists.",
        },
    },
    tags=["movies"],
)
async def update_movie(
    db: DbDep,
    movie_id: int,
    movie_data: MovieUpdateSchema,
    moderator: ModeratorUserDep,
) -> MovieDetailSchema:
    """
    Update a movie. Moderator/Admin only.
    """
    movie = await crud.get_movie_by_id(db=db, movie_id=movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    existing_movie = await crud.get_movie_by_name_year_time(
        db=db,
        name=movie_data.name or movie.name,
        year=movie_data.year or movie.year,
        time=movie_data.time or movie.time,
    )
    if existing_movie is not None and existing_movie.id != movie_id:
        raise HTTPException(
            status_code=409,
            detail="Movie with this name, year and duration already exists.",
        )

    if movie_data.certification_id is not None:
        certification = await crud.get_object_by_id(
            db=db, model=Certification, object_id=movie_data.certification_id
        )
        if certification is None:
            raise HTTPException(status_code=400, detail="Certification not found")
        movie.certification = certification

    if movie_data.genre_ids is not None:
        genres = await get_all_objects_or_400(
            db=db, model=Genre, ids=movie_data.genre_ids, label="Genres"
        )
        movie.genres = genres

    if movie_data.star_ids is not None:
        stars = await get_all_objects_or_400(
            db=db, model=Star, ids=movie_data.star_ids, label="Stars"
        )
        movie.stars = stars

    if movie_data.director_ids is not None:
        directors = await get_all_objects_or_400(
            db=db, model=Director, ids=movie_data.director_ids, label="Directors"
        )
        movie.directors = directors

    try:
        movie = await crud.update_movie(db=db, movie=movie, data=movie_data)
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Movie with this name, year and duration already exists.",
        )
    await db.commit()

    return MovieDetailSchema.model_validate(movie)
