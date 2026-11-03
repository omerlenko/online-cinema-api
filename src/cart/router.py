from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

from src.accounts.crud import get_user_by_id
from src.accounts.dependencies import ModeratorUserDep, CurrentUserDep
from src.cart.schemas import CartItemDetailSchema, CartItemCreateSchema
from src.cart import crud
from src.core.schemas import ErrorResponseSchema
from src.database.session import DbDep
from src.movies.crud import get_movie_by_id

router = APIRouter()


@router.get(
    "",
    summary="List cart items",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "User is not active.",
        },
    },
)
async def list_cart_items(
    db: DbDep,
    current_user: CurrentUserDep,
) -> list[CartItemDetailSchema]:
    """
    List the current user’s cart items. Returns an empty list if the cart is empty.
    """
    cart = await crud.get_cart_by_user_id(db=db, user_id=current_user.id)
    if cart is None:
        return []

    items = await crud.list_cart_items(db=db, cart_id=cart.id)
    return [CartItemDetailSchema.model_validate(item) for item in items]


@router.post(
    "/items",
    status_code=201,
    summary="Add a movie to the cart",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "User is not active.",
        },
        404: {"model": ErrorResponseSchema, "description": "Movie not found."},
        409: {
            "model": ErrorResponseSchema,
            "description": "Movie is already in the cart.",
        },
    },
)
async def create_cart_item(
    db: DbDep,
    item_data: CartItemCreateSchema,
    current_user: CurrentUserDep,
) -> CartItemDetailSchema:
    """
    Add a movie to the current user’s cart.
    A 401 means the client should ask the user to sign up or log in.
    """
    movie = await get_movie_by_id(db=db, movie_id=item_data.movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    cart = await crud.get_or_create_cart(db=db, user_id=current_user.id)

    item = await crud.get_cart_item(db=db, cart_id=cart.id, movie_id=movie.id)
    if item is not None:
        raise HTTPException(status_code=409, detail="Movie already in cart")

    try:
        item = await crud.create_cart_item(db=db, cart_id=cart.id, movie=movie)
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Movie already in cart",
        )
    await db.commit()

    return CartItemDetailSchema.model_validate(item)


@router.delete(
    "/items/{movie_id}",
    status_code=204,
    summary="Remove a movie from the cart",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "User is not active.",
        },
        404: {
            "model": ErrorResponseSchema,
            "description": "Movie is not in the cart.",
        },
    },
)
async def delete_cart_item(
    db: DbDep, movie_id: int, current_user: CurrentUserDep
) -> None:
    """
    Remove a movie from the current user’s cart.
    """
    cart = await crud.get_cart_by_user_id(db=db, user_id=current_user.id)
    if cart is None:
        raise HTTPException(status_code=404, detail="Movie not in cart")

    item = await crud.get_cart_item(db=db, cart_id=cart.id, movie_id=movie_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not in cart")

    await db.delete(item)
    await db.commit()


@router.delete(
    "",
    status_code=204,
    summary="Clear the cart",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "User is not active.",
        },
    },
)
async def clear_cart(db: DbDep, current_user: CurrentUserDep) -> None:
    """
    Remove all movies from the current user’s cart.
    """
    cart = await crud.get_cart_by_user_id(db=db, user_id=current_user.id)
    if cart is None:
        return

    await crud.delete_cart_items_by_cart_id(db=db, cart_id=cart.id)
    await db.commit()


@router.get(
    "/users/{user_id}",
    summary="List a user’s cart items",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Caller is not an admin/moderator "
            "or their account is inactive.",
        },
        404: {
            "model": ErrorResponseSchema,
            "description": "User not found.",
        },
    },
)
async def list_cart_items_by_user(
    db: DbDep,
    user_id: int,
    moderator: ModeratorUserDep,
) -> list[CartItemDetailSchema]:
    """
    List cart items of any user. Moderator/Admin only.
    """
    user = await get_user_by_id(db=db, user_id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    cart = await crud.get_cart_by_user_id(db=db, user_id=user.id)
    if cart is None:
        return []

    items = await crud.list_cart_items(db=db, cart_id=cart.id)
    return [CartItemDetailSchema.model_validate(item) for item in items]
