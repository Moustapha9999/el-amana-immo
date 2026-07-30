from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


def page_offset(page: int, size: int) -> int:
    return (page - 1) * size
