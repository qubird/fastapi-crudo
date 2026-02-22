"""
Plugin action system for CrudoAdmin.

Define custom Python functions and register them as row-level or bulk
actions on specific models. Crudo provides the UI; you provide the logic.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .auth import require_auth


@dataclass
class CrudoAction:
    """
    A pluggable action that can be executed on one or more records.

    Parameters
    ----------
    name : str
        Unique identifier (used in the API URL).
    label : str
        Human-readable label shown in the UI.
    fn : callable
        ``async def fn(records: list[dict], db: Session) -> str``
    icon : str
        Emoji or icon string shown in the UI.
    confirm : str | None
        Confirmation message template. Use ``{count}`` placeholder.
    role : str
        Required role: ``"admin"`` or ``"viewer"``. Default ``"admin"``.
    """

    name: str
    label: str
    fn: Callable
    icon: str = ""
    confirm: Optional[str] = None
    role: str = "admin"


def actions_to_meta(actions: List[CrudoAction]) -> List[Dict[str, Any]]:
    """Serialize actions to JSON-safe dicts for the ``_meta/models`` response."""
    return [
        {
            "name": a.name,
            "label": a.label,
            "icon": a.icon,
            "confirm": a.confirm,
            "role": a.role,
        }
        for a in actions
    ]


def create_action_router(
    model: Any,
    pk_columns: List[str],
    read_schema: Any,
    actions: List[CrudoAction],
    get_db: Callable,
) -> APIRouter:
    """
    Build a router with ``POST /_action/{action_name}`` for each action.
    """
    router = APIRouter()
    action_map = {a.name: a for a in actions}

    @router.post("/_action/{action_name}")
    async def execute_action(
        action_name: str,
        request: Request,
        db: Session = Depends(get_db),
    ):
        user = require_auth(request)

        action = action_map.get(action_name)
        if not action:
            raise HTTPException(
                status_code=404,
                detail=f"Action '{action_name}' not found",
            )

        # Role check
        if action.role == "admin" and user.get("role") != "admin":
            raise HTTPException(
                status_code=403, detail="Admin access required"
            )

        body = await request.json()
        pks = body.get("pks", [])
        if not pks:
            raise HTTPException(
                status_code=400, detail="No records selected"
            )

        # Fetch records by PK
        from .router import _build_pk_filters

        records = []
        for pk_str in pks:
            filters = _build_pk_filters(str(pk_str), model, pk_columns)
            record = db.query(model).filter(*filters).first()
            if record:
                records.append(
                    read_schema.model_validate(record).model_dump(
                        mode="json"
                    )
                )

        if not records:
            raise HTTPException(
                status_code=404, detail="No matching records found"
            )

        # Execute the action
        try:
            message = await action.fn(records, db)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Action failed: {exc}",
            )

        return {"message": message or "Action completed", "count": len(records)}

    return router
