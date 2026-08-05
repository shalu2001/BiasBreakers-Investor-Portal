"""
portal_auth.py -- password hashing (stdlib PBKDF2) + JWT sessions (PyJWT).

PBKDF2 is used deliberately instead of bcrypt/argon2 so there is NO native
extension to be blocked by Windows Smart App Control (the same policy that
blocked pandas' native DLL earlier). PyJWT with HS256 is pure Python too.
"""
import os
import base64
import hashlib
import hmac
import datetime as dt

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me-in-.env")
JWT_ALG = "HS256"
JWT_TTL_HOURS = 24 * 7
_PBKDF2_ITERS = 200_000


# ---- passwords --------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERS)
    return f"pbkdf2_sha256${_PBKDF2_ITERS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iters, salt_b64, hash_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# ---- tokens -----------------------------------------------------------------
def make_token(user_id: str) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + dt.timedelta(hours=JWT_TTL_HOURS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


_bearer = HTTPBearer(auto_error=False)


def get_current_user_id(cred: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(cred.credentials, JWT_SECRET, algorithms=[JWT_ALG])
        return payload["sub"]
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
