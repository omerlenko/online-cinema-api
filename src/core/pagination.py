from typing import Annotated

from fastapi import Depends, Query, Request

from src.core.schemas import Page


class Pagination:
    def __init__(
        self,
        request: Request,
        page: Annotated[int, Query(ge=1, description="Page number")] = 1,
        page_size: Annotated[
            int, Query(ge=1, le=100, description="Items per page")
        ] = 20,
    ):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * self.page_size
        self.current_url = request.url

    def previous_page(self) -> str | None:
        if self.page > 1:
            return str(
                self.current_url.include_query_params(
                    page=self.page - 1, page_size=self.page_size
                )
            )
        return None

    def next_page(self, total: int) -> str | None:
        if (self.page * self.page_size) < total:
            return str(
                self.current_url.include_query_params(
                    page=self.page + 1, page_size=self.page_size
                )
            )
        return None

    def get_page[T](self, items: list[T], total: int) -> Page[T]:
        return Page(
            items=items,
            total=total,
            page=self.page,
            page_size=self.page_size,
            previous_page=self.previous_page(),
            next_page=self.next_page(total=total),
        )


PaginationDep = Annotated[Pagination, Depends()]
