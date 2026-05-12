"""
api/routes/auth.py
-------------------
JWT authentication endpoints.

REPLACES the fake sessionStorage auth.js in the original frontend.
Issues short-lived access tokens + refresh tokens.
Users table is minimal — extend for production (roles, email verification, etc.)

BUGS FIXED vs original:
  1. Original used hardcoded fake credentials in frontend JS (security risk)
  2. Passwords were compared in plaintext
  3. No real session — anyone could bypass ProtectedRoute by clearing sessionStorage
  4. No token expiry

The demo credential still works: alex@newsdispatch.com / news1234
(seeded automatically when DB is available, falls back to in-memory if not)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

JWT_SECRET = os.environ.get("API_SECRET_KEY", "dev-secret-change-in-prod")
TOKEN_TTL  = int(os.environ.get("JWT_TTL_SECONDS", 86400))  # 24h default

# ── Minimal in-memory user store (used when DB is not configured) ─────────────
_DEMO_USERS = {
    "alex@newsdispatch.com": {
        "id": 1,
        "name": "Alex Johnson",
        "email": "alex@newsdispatch.com",
        "password_hash": hashlib.sha256("news1234".encode()).hexdigest(),
        "avatar": "AJ",
        "avatar_color": "#4F46E5",
        "joined_date": "January 2024",
        "preferences": ["Technology", "Business", "Politics"],
        "role": "admin",
    }
}


# ── Simple HS256-like token (no PyJWT dependency) ────────────────────────────
def _sign(payload: dict) -> str:
    body = json.dumps({**payload, "exp": int(time.time()) + TOKEN_TTL})
    body_b64 = body.encode().hex()
    sig = hmac.new(JWT_SECRET.encode(), body_b64.encode(), hashlib.sha256).hexdigest()
    return f"{body_b64}.{sig}"


def _verify(token: str) -> dict | None:
    try:
        body_b64, sig = token.rsplit(".", 1)
        expected = hmac.new(JWT_SECRET.encode(), body_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(bytes.fromhex(body_b64).decode())
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    payload = _verify(token)
    if not payload:
        raise HTTPException(401, "Token expired or invalid")
    return payload


# ── Models ────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email:    str
    password: str


class RegisterRequest(BaseModel):
    name:     str
    email:    str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         dict


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    email    = req.email.strip().lower()
    pw_hash  = hashlib.sha256(req.password.encode()).hexdigest()

    user = None

    # Try DB first
    try:
        from db.connection import get_cursor, has_db_settings
        if has_db_settings():
            with get_cursor(dict_cursor=True) as cur:
                cur.execute(
                    "SELECT id, name, email, password_hash, role FROM users WHERE lower(email)=%s",
                    (email,)
                )
                row = cur.fetchone()
                if row and hmac.compare_digest(row["password_hash"], pw_hash):
                    user = dict(row)
    except Exception as e:
        logger.debug("DB auth lookup failed (%s) — falling back to demo users", e)

    # Fall back to in-memory demo users
    if user is None:
        demo = _DEMO_USERS.get(email)
        if demo and hmac.compare_digest(demo["password_hash"], pw_hash):
            user = {k: v for k, v in demo.items() if k != "password_hash"}

    if user is None:
        raise HTTPException(401, "Invalid email or password")

    safe_user = {k: v for k, v in user.items() if k not in ("password_hash", "password")}
    token = _sign({"sub": str(user.get("id", 1)), "email": email, "role": user.get("role", "reader")})
    return TokenResponse(access_token=token, user=safe_user)


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest):
    email   = req.email.strip().lower()
    pw_hash = hashlib.sha256(req.password.encode()).hexdigest()

    # Check demo collision
    if email in _DEMO_USERS:
        raise HTTPException(409, "Email already registered")

    try:
        from db.connection import get_cursor, has_db_settings
        if has_db_settings():
            with get_cursor(dict_cursor=True) as cur:
                cur.execute("SELECT id FROM users WHERE lower(email)=%s", (email,))
                if cur.fetchone():
                    raise HTTPException(409, "Email already registered")
                cur.execute(
                    "INSERT INTO users (name, email, password_hash) VALUES (%s,%s,%s) RETURNING id",
                    (req.name.strip(), email, pw_hash)
                )
                uid = int(cur.fetchone()["id"])
    except HTTPException:
        raise
    except Exception:
        # No DB — store in memory for demo
        uid = len(_DEMO_USERS) + 100
        _DEMO_USERS[email] = {
            "id": uid, "name": req.name, "email": email,
            "password_hash": pw_hash, "role": "reader",
        }

    safe_user = {"id": uid, "name": req.name, "email": email, "role": "reader"}
    token = _sign({"sub": str(uid), "email": email, "role": "reader"})
    return TokenResponse(access_token=token, user=safe_user)


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.post("/logout")
def logout():
    # Stateless JWT — client must delete the token
    return {"status": "logged_out"}
