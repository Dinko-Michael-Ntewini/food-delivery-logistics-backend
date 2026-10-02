"""Shared bounded pagination and allowlisted SQLAlchemy sorting."""
from typing import Annotated

from fastapi import Query, Request
from sqlalchemy import func, select

from app.core.exceptions import ApplicationError

PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def resolve_list_aliases(request: Request, page_size: int, sort: str, *,
                         limit: int | None, sort_by: str | None, order: str | None):
    """Keep canonical parameters; reject ambiguous, conflicting legacy aliases."""
    if limit is not None:
        if "page_size" in request.query_params and page_size != limit:
            raise ApplicationError("limit conflicts with page_size")
        page_size = limit
    if sort_by is not None or order is not None:
        field = sort_by if sort_by is not None else sort.lstrip("-")
        descending = order == "desc" if order is not None else sort.startswith("-")
        alias_sort = ("-" if descending else "") + field
        if "sort" in request.query_params and alias_sort != sort:
            raise ApplicationError("sort aliases conflict with sort")
        sort = alias_sort
    return page_size, sort


def sorted_query(query, sort: str, allowed: dict, tie_breaker):
    descending = sort.startswith("-")
    field = sort[1:] if descending else sort
    if field not in allowed:
        raise ApplicationError("Unsupported sort field")
    column = allowed[field]
    return query.order_by(column.desc() if descending else column.asc(),
                          tie_breaker.desc() if descending else tie_breaker.asc())


def paginate(db, query, page: int, page_size: int):
    if page < 1 or not 1 <= page_size <= 100:
        raise ApplicationError("Invalid pagination bounds")
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    return {"items": db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all(),
            "page": page, "page_size": page_size, "total": total,
            "total_pages": (total + page_size - 1) // page_size}
