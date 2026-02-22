"""
CrudoAdmin — the main entry point.

Mount a complete CRUD admin panel on any FastAPI application:

    from fast_api_crudo import CrudoAdmin, CrudoAuth

    crudo = CrudoAdmin(
        app, base=Base, session_factory=SessionLocal,
        auth=CrudoAuth(secret_key="...", basic_users={...}),
    )
"""

import warnings
from pathlib import Path
from typing import Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .actions import CrudoAction, actions_to_meta, create_action_router
from .auth import (
    CrudoAuth,
    create_auth_router,
    require_auth,
    _get_session_user,
)
from .router import create_crud_router
from .schema_factory import (
    create_schemas_for_model,
    get_column_metadata,
    get_pk_columns,
)

_HERE = Path(__file__).resolve().parent
_VERSION = "0.3.0"


class CrudoAdmin:
    """
    Auto-generate a CRUD admin panel for every SQLAlchemy model
    registered on *base*.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.
    base : declarative base
        SQLAlchemy declarative base that holds your models.
    session_factory : callable
        A ``sessionmaker`` (or anything callable that returns a ``Session``).
    auth : CrudoAuth
        Authentication configuration. **Required.**
    prefix : str
        URL prefix for the admin panel (default ``"/crudo"``).
    title : str
        Title shown in the admin UI.
    include_models : list[str] | None
        If set, only register models whose ``__tablename__`` is in this list.
    exclude_models : list[str] | None
        Exclude models whose ``__tablename__`` is in this list.
    """

    def __init__(
        self,
        app: FastAPI,
        base,
        session_factory: Callable,
        auth: CrudoAuth,
        prefix: str = "/crudo",
        title: str = "Crudo Admin",
        include_models: Optional[List[str]] = None,
        exclude_models: Optional[List[str]] = None,
        plugins: Optional[Dict[str, List[CrudoAction]]] = None,
    ):
        if not isinstance(auth, CrudoAuth):
            raise TypeError(
                "CrudoAdmin requires an auth=CrudoAuth(...) parameter. "
                "Unauthenticated admin panels are not supported."
            )

        self.app = app
        self.base = base
        self.session_factory = session_factory
        self.auth = auth
        self.prefix = prefix.rstrip("/")
        self.title = title
        self.include_models = set(include_models) if include_models else None
        self.exclude_models = set(exclude_models) if exclude_models else set()
        self.plugins = plugins or {}

        self.models: Dict[str, dict] = {}

        # Add session middleware for signed cookies
        app.add_middleware(
            SessionMiddleware,
            secret_key=auth.secret_key,
            session_cookie="crudo_session",
            max_age=60 * 60 * 24 * 7,  # 7 days
        )

        self._discover_models()
        self._setup_routes()

    # ------------------------------------------------------------------
    # DB dependency
    # ------------------------------------------------------------------

    def _get_db(self):
        """FastAPI dependency that yields a SQLAlchemy session."""
        db: Session = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Model discovery
    # ------------------------------------------------------------------

    @staticmethod
    def _all_subclasses(cls):
        """Recursively collect every subclass of *cls*."""
        result = []
        for sub in cls.__subclasses__():
            result.append(sub)
            result.extend(CrudoAdmin._all_subclasses(sub))
        return result

    @staticmethod
    def _get_tablename(cls) -> "Optional[str]":
        """Get the table name from a model class (works with automap too)."""
        name = getattr(cls, "__tablename__", None)
        if name:
            return name
        # automap classes don't set __tablename__ but have __table__
        table = getattr(cls, "__table__", None)
        if table is not None:
            return table.name
        return None

    def _discover_models(self):
        """Scan the Base for mapped models and register them."""
        found: Dict[str, type] = {}

        # Strategy 1 — SQLAlchemy >= 1.4 registry
        if hasattr(self.base, "registry") and hasattr(
            self.base.registry, "mappers"
        ):
            for mapper in self.base.registry.mappers:
                cls = mapper.class_
                tablename = self._get_tablename(cls)
                if tablename and cls is not self.base:
                    found[tablename] = cls

        # Strategy 2 — recursive __subclasses__
        if not found:
            for cls in self._all_subclasses(self.base):
                tablename = self._get_tablename(cls)
                if tablename:
                    found[tablename] = cls

        for tablename, cls in sorted(found.items()):
            if self.include_models and tablename not in self.include_models:
                continue
            if tablename in self.exclude_models:
                continue

            # Skip models without a primary key
            pk_cols = get_pk_columns(cls)
            if not pk_cols:
                continue

            try:
                schemas = create_schemas_for_model(cls)
                columns = get_column_metadata(cls)
                self.models[tablename] = {
                    "model": cls,
                    "model_name": cls.__name__,
                    "schemas": schemas,
                    "columns": columns,
                }
            except Exception as exc:
                warnings.warn(
                    f"Crudo: skipping model {cls.__name__} — {exc}"
                )

    # ------------------------------------------------------------------
    # Route setup
    # ------------------------------------------------------------------

    def _setup_routes(self):
        """Wire up auth + API + UI routes on the FastAPI app."""

        # ── Auth routes ───────────────────────────────────────────
        auth_router = create_auth_router(self.auth, self.prefix)
        self.app.include_router(
            auth_router, prefix=self.prefix
        )

        # ── API routes (require authentication) ───────────────────
        api_router = APIRouter()

        # Meta endpoint
        @api_router.get("/_meta/models")
        def list_models(
            request: Request,
            db: Session = Depends(self._get_db),
        ):
            user = require_auth(request)
            result = []
            for name, info in sorted(self.models.items()):
                try:
                    count = db.query(info["model"]).count()
                except Exception:
                    count = -1
                model_actions = self.plugins.get(name, [])
                result.append(
                    {
                        "name": name,
                        "model_name": info["model_name"],
                        "columns": info["columns"],
                        "pk_columns": info["schemas"]["pk_columns"],
                        "count": count,
                        "actions": actions_to_meta(model_actions),
                    }
                )
            return result

        # CRUD + action routes per model
        for name, info in self.models.items():
            # Action router first (fixed /_action/ path must match
            # before the {record_id:path} catch-all in CRUD router)
            model_actions = self.plugins.get(name, [])
            if model_actions:
                action_router = create_action_router(
                    model=info["model"],
                    pk_columns=info["schemas"]["pk_columns"],
                    read_schema=info["schemas"]["read"],
                    actions=model_actions,
                    get_db=self._get_db,
                )
                api_router.include_router(
                    action_router,
                    prefix=f"/{name}",
                    tags=[f"crudo:{info['model_name']}:actions"],
                )

            # CRUD router
            model_router = create_crud_router(
                model=info["model"],
                schemas=info["schemas"],
                get_db=self._get_db,
            )
            api_router.include_router(
                model_router,
                prefix=f"/{name}",
                tags=[f"crudo:{info['model_name']}"],
            )

        self.app.include_router(
            api_router, prefix=f"{self.prefix}/api"
        )

        # ── HTML admin UI ─────────────────────────────────────────
        templates = Jinja2Templates(
            directory=str(_HERE / "templates")
        )

        @self.app.get(
            f"{self.prefix}/login", response_class=HTMLResponse
        )
        async def crudo_login(request: Request):
            # If already authenticated, redirect to main panel
            user = _get_session_user(request)
            if user:
                return RedirectResponse(f"{self.prefix}/")
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "title": self.title,
                    "prefix": self.prefix,
                    "static_base": f"{self.prefix}/static",
                    "has_basic": self.auth.has_basic,
                    "has_google": self.auth.has_google,
                },
            )

        @self.app.get(
            f"{self.prefix}/", response_class=HTMLResponse
        )
        @self.app.get(self.prefix, response_class=HTMLResponse)
        async def crudo_ui(request: Request):
            user = _get_session_user(request)
            if not user:
                return RedirectResponse(f"{self.prefix}/login")
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "title": self.title,
                    "api_base": f"{self.prefix}/api",
                    "static_base": f"{self.prefix}/static",
                    "version": _VERSION,
                    "user_name": user.get("name", ""),
                    "user_email": user.get("email", ""),
                    "user_role": user.get("role", "viewer"),
                    "logout_url": f"{self.prefix}/auth/logout",
                },
            )

        # ── Static files (mount AFTER routes) ─────────────────────
        self.app.mount(
            f"{self.prefix}/static",
            StaticFiles(directory=str(_HERE / "static")),
            name="crudo_static",
        )
