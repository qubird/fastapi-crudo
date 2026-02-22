"""
Fast API Crudo - Auto-generate CRUD admin interfaces for SQLAlchemy models.

Usage:
    from fast_api_crudo import CrudoAdmin, CrudoAuth, CrudoAction

    app = FastAPI()
    crudo = CrudoAdmin(
        app, base=Base, session_factory=SessionLocal,
        auth=CrudoAuth(secret_key="...", basic_users={...}),
        plugins={"users": [CrudoAction(name="...", label="...", fn=my_fn)]},
    )
"""

from .actions import CrudoAction
from .admin import CrudoAdmin
from .auth import CrudoAuth

__version__ = "0.3.0"
__all__ = ["CrudoAdmin", "CrudoAuth", "CrudoAction"]
