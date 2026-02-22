# 🍖 fastapi-crudo

Auto-generate a full CRUD admin panel for any PostgreSQL database or SQLAlchemy application. Point it at a database and get a complete admin interface — no model code required.

## Features

- **Zero configuration** — auto-discovers tables from any PostgreSQL database, no model definitions needed
- **Two usage modes** — standalone (just a database URL) or embedded inside an existing FastAPI app
- **Full CRUD** — Create, Read, Update, Delete for every table
- **Authentication** — mandatory login via user/password and/or Google OAuth
- **Role-based access** — `admin` (full CRUD) and `viewer` (read-only) roles
- **Plugin actions** — register custom Python functions as row-level or bulk actions on any table
- **Pagination, sorting, search** — server-side pagination, column sorting, full-text search
- **Auto-generated forms** — input types inferred from column types (text, number, boolean, datetime, enum, JSON, geometry, etc.)
- **PostGIS support** — geometry columns are auto-detected and displayed as WKT
- **Composite PK support** — works with single and composite primary keys
- **Modern React UI** — clean, responsive admin interface served as static files
- **Type-safe schemas** — Pydantic schemas generated dynamically from your database schema

## Install

```bash
pip install fastapi-crudo
```

## Usage

fastapi-crudo can be used in two ways:

### Mode 1: Standalone (database URL only)

Connect directly to any PostgreSQL database. Tables are discovered automatically via SQLAlchemy automap — **no model code needed**.

```python
import os
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker

from fast_api_crudo import CrudoAdmin, CrudoAuth

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:pass@localhost/mydb")

engine = create_engine(DATABASE_URL)

# Reflect all tables automatically — no models to write
Base = automap_base()
Base.prepare(autoload_with=engine)

SessionLocal = sessionmaker(bind=engine)

app = FastAPI()

CrudoAdmin(
    app=app,
    base=Base,
    session_factory=SessionLocal,
    auth=CrudoAuth(
        secret_key="your-secret-key",
        basic_users={
            "admin": {"password": "changeme", "role": "admin"},
        },
    ),
)

# Run: uvicorn app:app --port 8001
# Visit: http://localhost:8001/crudo/
```

This is useful for:
- Quick database inspection and editing
- Adding an admin panel to a database that has no application code
- Running as a separate service alongside your main app

### Mode 2: Embedded in an existing FastAPI app

Import your SQLAlchemy `Base` and models directly. This lets you define **plugin actions** — custom Python functions that operate on your ORM objects.

```python
import os
from fastapi import FastAPI

# Import from your existing application
from myapp.database import Base, SessionLocal
import myapp.models  # ensures models are registered on Base

from fast_api_crudo import CrudoAdmin, CrudoAuth, CrudoAction


async def verify_email(records, db):
    from myapp.models import User
    count = 0
    for rec in records:
        user = db.query(User).filter(User.id == rec["id"]).first()
        if user and not user.email_verified:
            user.email_verified = True
            count += 1
    db.commit()
    return f"Verified {count} user(s)"


app = FastAPI()

CrudoAdmin(
    app=app,
    base=Base,
    session_factory=SessionLocal,
    auth=CrudoAuth(
        secret_key=os.environ["SECRET_KEY"],
        basic_users={
            "admin": {"password": os.environ["ADMIN_PASS"], "role": "admin"},
        },
    ),
    exclude_models=["alembic_version"],
    plugins={
        "users": [
            CrudoAction(
                name="verify_email",
                label="Verify Email",
                fn=verify_email,
                icon="✅",
                confirm="Verify email for {count} user(s)?",
            ),
        ],
    },
)
```

To run alongside your main app in the same container (on a separate port):

```bash
# Main app on port 8080, admin on port 8001
uvicorn main:app --port 8080 &
uvicorn admin:app --port 8001 &
wait
```

## Authentication

Authentication is **required** — there is no way to run CrudoAdmin without it.

### Basic Auth (user/password)

```python
CrudoAuth(
    secret_key="your-secret-key",
    basic_users={
        "admin": {"password": "secret", "role": "admin"},
        "viewer": {"password": "viewer123", "role": "viewer"},
    },
)
```

### Google OAuth

```python
CrudoAuth(
    secret_key="your-secret-key",
    google_oauth={
        "client_id": "your-google-client-id",
        "client_secret": "your-google-client-secret",
        "allowed_users": {
            "admin@example.com": "admin",
            "viewer@example.com": "viewer",
        },
    },
)
```

### Both (user picks on login page)

```python
CrudoAuth(
    secret_key="your-secret-key",
    basic_users={...},
    google_oauth={...},
)
```

### Roles

| Role     | Permissions                    |
|----------|--------------------------------|
| `admin`  | List, Get, Create, Update, Delete, Run actions |
| `viewer` | List, Get (read-only)          |

## Plugins (Custom Actions)

Define Python functions in your application code and plug them into CrudoAdmin. Crudo handles the UI (checkboxes, dropdowns, confirmation dialogs) and calls your function when the user triggers an action.

### Defining actions

Action functions receive a list of record dicts and a SQLAlchemy session, and return a message string:

```python
# Signature: async def fn(records: list[dict], db: Session) -> str

async def send_welcome_email(records, db):
    from myapp.email import send_email
    for rec in records:
        await send_email(rec["email"], template="welcome")
    return f"Sent {len(records)} email(s)"

async def activate_premium(records, db):
    from myapp.models import CompanyProfile
    from datetime import datetime, timedelta
    for rec in records:
        profile = db.query(CompanyProfile).get(rec["id"])
        profile.premium_expires_at = datetime.utcnow() + timedelta(days=30)
    db.commit()
    return f"Activated premium for {len(records)} company(ies)"
```

### Registering actions

Pass a `plugins` dict to `CrudoAdmin`. Keys are **table names**, values are lists of `CrudoAction`:

```python
CrudoAdmin(
    ...,
    plugins={
        "users": [
            CrudoAction(
                name="send_welcome",
                label="Send Welcome Email",
                fn=send_welcome_email,
                icon="📧",
                confirm="Send welcome email to {count} user(s)?",
            ),
        ],
        "company_profiles": [
            CrudoAction(
                name="activate_premium",
                label="Activate Premium",
                fn=activate_premium,
                icon="⭐",
                confirm="Activate 30-day premium for {count} company(ies)?",
            ),
        ],
    },
)
```

### How it works

1. Select one or more records using checkboxes in the admin UI
2. Click the "Actions" dropdown and pick an action
3. A confirmation dialog appears (if `confirm` is set)
4. Crudo calls your function with `(records, db)`
5. Your function returns a message string, shown as a toast notification

### CrudoAction reference

| Parameter  | Type       | Default    | Description |
|-----------|------------|------------|-------------|
| `name`    | `str`      | required   | Unique action ID, used in the API URL |
| `label`   | `str`      | required   | Human-readable label shown in the UI |
| `fn`      | `callable` | required   | `async def fn(records: list[dict], db: Session) -> str` |
| `icon`    | `str`      | `""`       | Emoji or icon shown in the action button |
| `confirm` | `str\|None` | `None`    | Confirmation message. `{count}` = number of selected records |
| `role`    | `str`      | `"admin"`  | Required role: `"admin"` or `"viewer"` |

## Configuration

```python
CrudoAdmin(
    app=app,                       # FastAPI application instance
    base=Base,                     # SQLAlchemy declarative or automap base
    session_factory=SessionLocal,  # sessionmaker or callable returning Session
    auth=CrudoAuth(...),           # authentication config (required)
    prefix="/admin",               # URL prefix (default: /crudo)
    title="My Admin Panel",        # page title (default: Crudo Admin)
    include_models=["users"],      # only show these tables (default: all)
    exclude_models=["alembic_version"],  # hide these tables (default: none)
    plugins={...},                 # custom actions per table (default: none)
)
```

## API Endpoints

For each registered table (e.g. `users`), Crudo generates:

| Method   | Path                            | Description             |
|----------|---------------------------------|-------------------------|
| `GET`    | `/crudo/api/_meta/models`       | List all models + schema + actions |
| `GET`    | `/crudo/api/{table}?page=1&per_page=25` | List records (paginated) |
| `GET`    | `/crudo/api/{table}/{pk}`       | Get single record       |
| `POST`   | `/crudo/api/{table}`            | Create record (admin)   |
| `PUT`    | `/crudo/api/{table}/{pk}`       | Update record (admin)   |
| `DELETE` | `/crudo/api/{table}/{pk}`       | Delete record (admin)   |
| `POST`   | `/crudo/api/{table}/_action/{name}` | Run a plugin action  |

## Requirements

- Python >= 3.9
- FastAPI >= 0.100
- SQLAlchemy >= 1.4
- Pydantic >= 2.0

## License

MIT
