"""
Example standalone CrudoAdmin app.

Connects to a database, auto-discovers all tables via automap,
and serves the admin panel with authentication.
"""

import os

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker

from fast_api_crudo import CrudoAdmin, CrudoAuth

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://user:password@localhost:5432/mydb"
)
SECRET_KEY = os.environ.get("SECRET_KEY", "crudo-dev-secret-change-me")

# Admin credentials from env (with defaults for dev)
ADMIN_USER = os.environ.get("CRUDO_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("CRUDO_ADMIN_PASS", "admin")
VIEWER_USER = os.environ.get("CRUDO_VIEWER_USER", "viewer")
VIEWER_PASS = os.environ.get("CRUDO_VIEWER_PASS", "viewer")

engine = create_engine(DATABASE_URL, pool_size=3, pool_pre_ping=True)

# Reflect all tables automatically
Base = automap_base()
Base.prepare(autoload_with=engine)

SessionLocal = sessionmaker(bind=engine)

app = FastAPI(title="Crudo Admin")

CrudoAdmin(
    app=app,
    base=Base,
    session_factory=SessionLocal,
    prefix="/crudo",
    title="Crudo Admin",
    exclude_models=["alembic_version"],
    auth=CrudoAuth(
        secret_key=SECRET_KEY,
        basic_users={
            ADMIN_USER: {"password": ADMIN_PASS, "role": "admin"},
            VIEWER_USER: {"password": VIEWER_PASS, "role": "viewer"},
        },
    ),
)


@app.get("/")
def root():
    return {"message": "Go to /crudo/ for the admin panel"}
