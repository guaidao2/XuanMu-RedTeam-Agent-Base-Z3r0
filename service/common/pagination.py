from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from sqlalchemy import func, select

from database import get_async_session


T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    page: int
    size: int
    total: int
    items: list[T]


def page_offset(page: int, size: int) -> int:
    return (page - 1) * size


async def paginate_statement(statement, *, page: int, size: int) -> Page:
    count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    page_statement = statement.offset(page_offset(page, size)).limit(size)

    async with get_async_session() as session:
        total = int((await session.execute(count_statement)).scalar_one())
        items = list((await session.exec(page_statement)).all())

    return Page(page=page, size=size, total=total, items=items)


def paginated_payload(page: Page[T], items: Sequence) -> dict:
    return {
        "page": page.page,
        "size": page.size,
        "total": page.total,
        "items": list(items),
    }
