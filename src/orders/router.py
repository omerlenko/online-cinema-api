from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends

from src.orders.schemas import (
    ExcludedMovieSchema,
    ExcludedMovieReasonEnum,
    OrderDetailSchema,
    OrderQueryParameters,
    OrderCreateResponseSchema,
    AdminOrderQueryParameters,
    AdminOrderDetailSchema,
)
from src.accounts.dependencies import CurrentUserDep, ModeratorUserDep
from src.cart.crud import get_cart_by_user_id, list_cart_items
from src.orders import crud
from src.core.pagination import PaginationDep
from src.core.schemas import ErrorResponseSchema, Page
from src.database.session import DbDep
from src.orders.models import OrderStatusEnum

router = APIRouter()


def get_exclusion_reason(
    movie_id: int, purchased_movie_ids: set[int], pending_movie_ids: set[int]
) -> ExcludedMovieReasonEnum | None:
    if movie_id in purchased_movie_ids:
        return ExcludedMovieReasonEnum.PURCHASED
    if movie_id in pending_movie_ids:
        return ExcludedMovieReasonEnum.PENDING
    return None


@router.post(
    "",
    status_code=201,
    summary="Place an order",
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token is invalid, expired, or not an access token.",
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "User is not active.",
        },
        400: {
            "model": ErrorResponseSchema,
            "description": "Cart is empty.",
        },
        409: {
            "model": ErrorResponseSchema,
            "description": "All movies in the cart are already purchased "
            "or are in pending orders.",
        },
    },
)
async def create_order(
    db: DbDep, current_user: CurrentUserDep
) -> OrderCreateResponseSchema:
    """
    Place an order for the movies in your cart.

    Movies you already bought, or that are in another of your pending orders,
    are left out and listed in `excluded_movies` with the reason.

    Your cart is not changed.
    Placing the same cart twice at the same time creates only one order.
    """
    cart = await get_cart_by_user_id(db=db, user_id=current_user.id, locked=True)
    if cart is None:
        raise HTTPException(status_code=400, detail="Cart is empty")
    cart_items = await list_cart_items(db=db, cart_id=cart.id)
    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    movie_ids = [item.movie_id for item in cart_items]
    purchased_movie_ids = await crud.get_movie_ids_by_order_status(
        db=db,
        user_id=current_user.id,
        status=OrderStatusEnum.PAID,
        movie_ids=movie_ids,
    )
    pending_movie_ids = await crud.get_movie_ids_by_order_status(
        db=db,
        user_id=current_user.id,
        status=OrderStatusEnum.PENDING,
        movie_ids=movie_ids,
    )

    movies_to_order = []
    excluded_movies = []
    for item in cart_items:
        reason = get_exclusion_reason(
            item.movie_id, purchased_movie_ids, pending_movie_ids
        )
        if reason is None:
            movies_to_order.append(item.movie)
        else:
            excluded_movies.append(
                ExcludedMovieSchema(
                    id=item.movie.id,
                    name=item.movie.name,
                    reason=reason,
                )
            )
    if not movies_to_order:
        raise HTTPException(
            status_code=409,
            detail="All movies in the cart are already purchased "
            "or are in pending order",
        )

    order = await crud.create_order(
        db=db, user_id=current_user.id, movies=movies_to_order
    )
    await db.commit()

    return OrderCreateResponseSchema(
        order=OrderDetailSchema.model_validate(order), excluded_movies=excluded_movies
    )


@router.get(
    "",
    summary="List your orders",
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
async def list_orders(
    db: DbDep,
    pagination: PaginationDep,
    current_user: CurrentUserDep,
    params: Annotated[OrderQueryParameters, Depends()],
) -> Page[OrderDetailSchema]:
    """
    List the current user's orders.

    Filter orders by date range and status, using `date_from`, `date_to`
    and `status` query parameters.

    Use `search` to find orders that contain a movie whose name matches.

    Orders are sorted by creation date, newest first.
    Use `sort_order=asc` for oldest first.

    Use `page` and `page_size` to page through the results (at most 100 per request).
    """
    orders = await crud.list_orders(
        db=db,
        user_id=current_user.id,
        offset=pagination.offset,
        limit=pagination.page_size,
        params=params,
    )
    items = [OrderDetailSchema.model_validate(order) for order in orders]
    total = await crud.count_orders(db=db, user_id=current_user.id, params=params)

    return pagination.get_page(items=items, total=total)


@router.get(
    "/all",
    summary="List all orders",
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
    },
)
async def list_all_orders(
    db: DbDep,
    pagination: PaginationDep,
    moderator: ModeratorUserDep,
    params: Annotated[AdminOrderQueryParameters, Depends()],
) -> Page[AdminOrderDetailSchema]:
    """
    List all orders. Moderator/Admin only.

    Filter orders by user id, date range and status, using `user_id`, `date_from`,
    `date_to` and `status` query parameters.

    Use `search` to find orders that contain a movie whose name matches.

    Orders are sorted by creation date, newest first.
    Use `sort_order=asc` for oldest first.

    Use `page` and `page_size` to page through the results (at most 100 per request).
    """
    orders = await crud.list_orders(
        db=db,
        user_id=params.user_id,
        offset=pagination.offset,
        limit=pagination.page_size,
        params=params,
    )
    items = [AdminOrderDetailSchema.model_validate(order) for order in orders]
    total = await crud.count_orders(db=db, user_id=params.user_id, params=params)

    return pagination.get_page(items=items, total=total)


@router.get(
    "/{order_id}",
    summary="Get order details",
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
            "description": "Order is not found.",
        },
    },
)
async def get_order_details(
    db: DbDep, order_id: int, current_user: CurrentUserDep
) -> OrderDetailSchema:
    """
    Get own order details. Another user's order returns 404 Not Found.
    """
    order = await crud.get_order_by_id(
        db=db, order_id=order_id, user_id=current_user.id
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    return OrderDetailSchema.model_validate(order)


@router.post(
    "/{order_id}/cancel",
    summary="Cancel an order",
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
            "description": "Order is not found.",
        },
        409: {
            "model": ErrorResponseSchema,
            "description": "Paid orders cannot be canceled.",
        },
    },
)
async def cancel_pending_order(
    db: DbDep, order_id: int, current_user: CurrentUserDep
) -> OrderDetailSchema:
    """
    Cancel an order if its status is `pending`.

    Cannot cancel an order that is already paid.

    Canceling an already canceled order returns 200 with the order unchanged.
    """
    order = await crud.get_order_by_id(
        db=db, order_id=order_id, user_id=current_user.id
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status == OrderStatusEnum.PAID:
        raise HTTPException(
            status_code=409,
            detail="Paid orders cannot be canceled",
        )

    if order.status == OrderStatusEnum.CANCELED:
        return OrderDetailSchema.model_validate(order)

    order.status = OrderStatusEnum.CANCELED
    await db.commit()

    return OrderDetailSchema.model_validate(order)
