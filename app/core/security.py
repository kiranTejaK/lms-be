"""
JWT authentication and password hashing utilities.

Password hashing uses bcrypt via passlib.  JWTs are signed with HMAC-SHA256
and include a ``type`` claim (``"access"`` or ``"refresh"``) so tokens
cannot be cross-used.

All functions are synchronous and stateless — they rely solely on the
settings loaded from ``app.core.config``.
"""

from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
import jwt

from app.core.config import settings

# bcrypt with auto-upgrade from deprecated schemes
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password Utilities ────────────────────────────────────────────────────

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return ``True`` if ``plain_password`` matches the stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Return a bcrypt hash of ``password``."""
    return pwd_context.hash(password)

# ── Token Creation ────────────────────────────────────────────────────────

def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a short-lived **access** JWT.

    The token payload includes:
      - all keys from ``data`` (typically ``{"sub": "<user_id>"}``),
      - ``exp`` — expiration timestamp,
      - ``type`` — literal ``"access"`` to distinguish from refresh tokens.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta if expires_delta else timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRY_IN_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """
    Create a long-lived **refresh** JWT.

    Identical to an access token except:
      - longer expiry (default 7 days),
      - ``type`` claim set to ``"refresh"``.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_REFRESH_TOKEN_EXPIRY_IN_MINUTES)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ── Token Verification ───────────────────────────────────────────────────

def verify_token(token: str) -> dict:
    """
    Decode and verify a JWT.

    Returns the payload dict on success, or an empty dict ``{}`` if
    the token is invalid, expired, or malformed.
    """
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM],)
    except jwt.PyJWTError:
        return {}

