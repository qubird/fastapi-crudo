"""
Authentication and authorization for CrudoAdmin.

Supports basic user/password auth and Google OAuth.
Uses Starlette SessionMiddleware with signed cookies.
"""

import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse


@dataclass
class CrudoAuth:
    """
    Authentication configuration for CrudoAdmin.

    At least one of ``basic_users`` or ``google_oauth`` must be provided.

    Parameters
    ----------
    basic_users : dict
        ``{"username": {"password": "...", "role": "admin"|"viewer"}}``
    google_oauth : dict
        ``{"client_id": "...", "client_secret": "...",
          "allowed_users": {"email": "role"}}``
    secret_key : str
        Secret for signing session cookies. **Required.**
    """

    secret_key: str
    basic_users: Optional[Dict[str, Dict[str, str]]] = None
    google_oauth: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not self.secret_key:
            raise ValueError("CrudoAuth: secret_key is required")

        has_basic = bool(self.basic_users)
        has_oauth = bool(self.google_oauth)

        if not has_basic and not has_oauth:
            raise ValueError(
                "CrudoAuth: at least one of basic_users or google_oauth "
                "must be configured"
            )

        # Validate basic users
        if self.basic_users:
            for username, info in self.basic_users.items():
                if not info.get("password"):
                    raise ValueError(
                        f"CrudoAuth: empty password for user '{username}'"
                    )
                role = info.get("role", "viewer")
                if role not in ("admin", "viewer"):
                    raise ValueError(
                        f"CrudoAuth: invalid role '{role}' for user "
                        f"'{username}' (must be 'admin' or 'viewer')"
                    )

        # Validate google oauth
        if self.google_oauth:
            for key in ("client_id", "client_secret", "allowed_users"):
                if not self.google_oauth.get(key):
                    raise ValueError(
                        f"CrudoAuth: google_oauth.{key} is required"
                    )
            for email, role in self.google_oauth["allowed_users"].items():
                if role not in ("admin", "viewer"):
                    raise ValueError(
                        f"CrudoAuth: invalid role '{role}' for "
                        f"'{email}' (must be 'admin' or 'viewer')"
                    )

    @property
    def has_basic(self) -> bool:
        return bool(self.basic_users)

    @property
    def has_google(self) -> bool:
        return bool(self.google_oauth)


def _get_session_user(request: Request) -> Optional[Dict[str, str]]:
    """Extract the authenticated user from the session, or None."""
    return request.session.get("crudo_user")


def create_auth_router(auth: CrudoAuth, prefix: str) -> APIRouter:
    """
    Build the authentication routes for CrudoAdmin.

    Routes
    ------
    - POST {prefix}/auth/login       — basic auth
    - GET  {prefix}/auth/google      — start Google OAuth
    - GET  {prefix}/auth/google/callback — OAuth callback
    - GET  {prefix}/auth/me          — current user info
    - GET  {prefix}/auth/logout      — logout
    """

    router = APIRouter()

    # ── Basic auth login ──────────────────────────────────────────

    @router.post("/auth/login")
    async def basic_login(request: Request):
        body = await request.json()
        username = body.get("username", "").strip()
        password = body.get("password", "")

        if not auth.basic_users:
            return JSONResponse(
                {"detail": "Basic auth is not enabled"},
                status_code=400,
            )

        user_info = auth.basic_users.get(username)
        if not user_info or not secrets.compare_digest(
            user_info["password"], password
        ):
            return JSONResponse(
                {"detail": "Invalid username or password"},
                status_code=401,
            )

        role = user_info.get("role", "viewer")
        request.session["crudo_user"] = {
            "email": username,
            "name": username,
            "role": role,
        }

        return {"ok": True, "user": request.session["crudo_user"]}

    # ── Google OAuth start ────────────────────────────────────────

    @router.get("/auth/google")
    async def google_start(request: Request):
        if not auth.has_google:
            return JSONResponse(
                {"detail": "Google OAuth is not enabled"},
                status_code=400,
            )

        from authlib.integrations.starlette_client import OAuth

        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=auth.google_oauth["client_id"],
            client_secret=auth.google_oauth["client_secret"],
            server_metadata_url=(
                "https://accounts.google.com/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile"},
        )

        callback_url = str(request.url_for("crudo_google_callback"))
        return await oauth.google.authorize_redirect(
            request, callback_url
        )

    # ── Google OAuth callback ─────────────────────────────────────

    @router.get("/auth/google/callback", name="crudo_google_callback")
    async def google_callback(request: Request):
        if not auth.has_google:
            return RedirectResponse(f"{prefix}/login")

        from authlib.integrations.starlette_client import OAuth

        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=auth.google_oauth["client_id"],
            client_secret=auth.google_oauth["client_secret"],
            server_metadata_url=(
                "https://accounts.google.com/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile"},
        )

        try:
            token = await oauth.google.authorize_access_token(request)
        except Exception:
            return RedirectResponse(
                f"{prefix}/login?error=oauth_failed"
            )

        userinfo = token.get("userinfo", {})
        email = userinfo.get("email", "")
        name = userinfo.get("name", email)

        allowed = auth.google_oauth.get("allowed_users", {})
        role = allowed.get(email)

        if role is None:
            return RedirectResponse(
                f"{prefix}/login?error=not_allowed"
            )

        request.session["crudo_user"] = {
            "email": email,
            "name": name,
            "role": role,
        }

        return RedirectResponse(f"{prefix}/")

    # ── Current user info ─────────────────────────────────────────

    @router.get("/auth/me")
    async def auth_me(request: Request):
        user = _get_session_user(request)
        if not user:
            return JSONResponse(
                {"detail": "Not authenticated"}, status_code=401
            )
        return user

    # ── Logout ────────────────────────────────────────────────────

    @router.get("/auth/logout")
    async def auth_logout(request: Request):
        request.session.pop("crudo_user", None)
        return RedirectResponse(f"{prefix}/login")

    return router


def require_auth(request: Request) -> Dict[str, str]:
    """
    FastAPI dependency: returns the current user dict or raises 401.
    Used by the CRUD router to enforce authentication.
    """
    user = _get_session_user(request)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin_dep(request: Request) -> Dict[str, str]:
    """
    FastAPI dependency: returns admin user or raises 401/403.
    Use as a Depends() so it runs before body validation.
    """
    user = require_auth(request)
    if user.get("role") != "admin":
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )
    return user


def require_admin(user: Dict[str, str]):
    """
    Check that the user has admin role. Raises 403 if viewer.
    """
    if user.get("role") != "admin":
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )
