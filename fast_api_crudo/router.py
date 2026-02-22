"""
Generic CRUD router factory.

Creates a full set of List / Get / Create / Update / Delete endpoints
for any SQLAlchemy model. Write endpoints enforce admin role via session.
"""

from typing import Any, Callable, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from .auth import require_auth, require_admin_dep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _convert_pk_value(value_str: str, col_obj) -> Any:
    """Convert a PK string from the URL to the correct Python type."""
    type_name = type(col_obj.type).__name__.upper()
    if "INT" in type_name:
        try:
            return int(value_str)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid integer PK: {value_str}",
            )
    return value_str


def _build_pk_filters(
    record_id: str,
    model: Any,
    pk_columns: List[str],
) -> list:
    """
    Parse a (possibly composite) PK string and return a list of
    SQLAlchemy filter expressions.

    Composite keys are encoded as ``val1--val2`` in the URL.
    """
    parts = record_id.split("--") if len(pk_columns) > 1 else [record_id]

    if len(parts) != len(pk_columns):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Expected {len(pk_columns)} PK value(s), "
                f"got {len(parts)}"
            ),
        )

    filters = []
    for pk_name, pk_value in zip(pk_columns, parts):
        col_attr = getattr(model, pk_name)
        col_obj = model.__table__.columns[pk_name]
        converted = _convert_pk_value(pk_value, col_obj)
        filters.append(col_attr == converted)

    return filters


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_crud_router(
    model: Any,
    schemas: Dict[str, Any],
    get_db: Callable,
) -> APIRouter:
    """
    Build a FastAPI ``APIRouter`` with CRUD endpoints for *model*.

    Authentication is enforced on all endpoints via session.
    Write endpoints (POST/PUT/DELETE) require ``admin`` role.
    """

    router = APIRouter()

    ReadSchema = schemas["read"]
    CreateSchema = schemas["create"]
    UpdateSchema = schemas["update"]
    pk_columns: List[str] = schemas["pk_columns"]

    # ── LIST (paginated) ──────────────────────────────────────────

    @router.get("")
    def list_records(
        request: Request,
        page: int = Query(1, ge=1, description="Page number"),
        per_page: int = Query(25, ge=1, le=500, description="Items per page"),
        sort_by: str = Query(None, description="Column to sort by"),
        sort_dir: str = Query("asc", description="asc or desc"),
        search: str = Query(None, description="Search string columns"),
        db: Session = Depends(get_db),
    ):
        require_auth(request)  # any authenticated user can read

        query = db.query(model)

        # Global search across string columns
        if search:
            from sqlalchemy import String, or_, cast

            conditions = []
            for col in model.__table__.columns:
                type_name = type(col.type).__name__.upper()
                if type_name in (
                    "VARCHAR",
                    "STRING",
                    "TEXT",
                    "NVARCHAR",
                    "CHAR",
                    "UNICODE",
                    "UNICODETEXT",
                    "CLOB",
                ):
                    conditions.append(col.ilike(f"%{search}%"))
                elif type_name == "ENUM":
                    conditions.append(
                        cast(col, String).ilike(f"%{search}%")
                    )
            if conditions:
                query = query.filter(or_(*conditions))

        total = query.count()

        # Sorting
        if sort_by:
            sort_col = getattr(model, sort_by, None)
            if sort_col is not None:
                from sqlalchemy import desc as sa_desc

                if sort_dir == "desc":
                    query = query.order_by(sa_desc(sort_col))
                else:
                    query = query.order_by(sort_col)

        # Pagination
        items = query.offset((page - 1) * per_page).limit(per_page).all()

        serialized = []
        for item in items:
            serialized.append(
                ReadSchema.model_validate(item).model_dump(mode="json")
            )

        pages = max(1, (total + per_page - 1) // per_page)

        return {
            "items": serialized,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    # ── GET single record ─────────────────────────────────────────

    @router.get("/{record_id:path}")
    def get_record(
        record_id: str,
        request: Request,
        db: Session = Depends(get_db),
    ):
        require_auth(request)  # any authenticated user can read

        filters = _build_pk_filters(record_id, model, pk_columns)
        record = db.query(model).filter(*filters).first()
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")
        return ReadSchema.model_validate(record).model_dump(mode="json")

    # ── CREATE ────────────────────────────────────────────────────

    @router.post("", status_code=201, dependencies=[Depends(require_admin_dep)])
    def create_record(
        data: CreateSchema,
        db: Session = Depends(get_db),
    ):

        values = data.model_dump(exclude_unset=True)
        record = model(**values)
        db.add(record)
        try:
            db.commit()
            db.refresh(record)
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc))
        return ReadSchema.model_validate(record).model_dump(mode="json")

    # ── UPDATE ────────────────────────────────────────────────────

    @router.put("/{record_id:path}", dependencies=[Depends(require_admin_dep)])
    def update_record(
        record_id: str,
        data: UpdateSchema,
        db: Session = Depends(get_db),
    ):

        filters = _build_pk_filters(record_id, model, pk_columns)
        record = db.query(model).filter(*filters).first()
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(record, key, value)

        try:
            db.commit()
            db.refresh(record)
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc))
        return ReadSchema.model_validate(record).model_dump(mode="json")

    # ── DELETE ────────────────────────────────────────────────────

    @router.delete("/{record_id:path}", status_code=204, dependencies=[Depends(require_admin_dep)])
    def delete_record(
        record_id: str,
        db: Session = Depends(get_db),
    ):

        filters = _build_pk_filters(record_id, model, pk_columns)
        record = db.query(model).filter(*filters).first()
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")

        try:
            db.delete(record)
            db.commit()
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc))
        return None

    return router
