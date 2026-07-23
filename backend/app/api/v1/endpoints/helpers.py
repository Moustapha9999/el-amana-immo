from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel

from app.schemas.common import PaginatedResponse

T = TypeVar("T")
S = TypeVar("S", bound=BaseModel)


def to_paginated(items: list[T], total: int, page: int, size: int, mapper: Callable[[T], S]) -> PaginatedResponse[S]:
    return PaginatedResponse(items=[mapper(i) for i in items], total=total, page=page, size=size)
