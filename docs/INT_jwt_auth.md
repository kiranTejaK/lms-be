# JWT & Authentication: Strategy & Implementation

## 1. Concept Overview

**What it is:**
Authentication is the process of verifying a user's identity. In this project, authentication is handled via **JSON Web Tokens (JWT)**. A JWT is a cryptographically signed, stateless token that allows the server to verify the user without needing to store server-side sessions.

**Why it is used:**
JWTs allow the backend to remain perfectly stateless, meaning API requests can be load-balanced across multiple servers without needing shared session state. The project implements an **Access/Refresh Token pair** pattern. Short-lived Access tokens (for immediate API access) limit the damage if stolen, while long-lived Refresh tokens (to obtain new Access tokens) provide a seamless user experience. Password security is managed using **bcrypt**.

---

## 2. Project Setup (Configuration & Core Utilities)

The authentication setup relies on standard libraries: `passlib` for hashing and `PyJWT` for token generation. These are configured in `app/core/security.py`.

### Password Hashing and Token Signing
The project uses `bcrypt` via `passlib`'s `CryptContext`. Tokens are signed using the HMAC-SHA256 algorithm.

```python
# app/core/security.py
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
import jwt
from app.core.config import settings

# bcrypt with auto-upgrade from deprecated schemes
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta if expires_delta else timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRY_IN_MINUTES))
    # Note the explicit 'type' claim to distinguish from refresh tokens
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
```

---

## 3. Key Code Walkthrough

### The Auth Service (Login Flow)
The `AuthService` validates credentials and issues the JWT token pair. If the login is successful, the `sub` (subject) claim in the JWT payload is set to the user's stringified ID.

```python
# app/services/auth_service.py
class AuthService:
    def login(self, form_data) -> dict:
        """Authenticate user and return JWT token pair."""
        user = self.db.execute(
            select(User).filter(User.email == form_data.username)
        ).scalar_one_or_none()

        if not user or not verify_password(form_data.password, user.password_hash):
            raise UnauthorizedException("Incorrect email or password")

        if not user.is_active:
            raise ForbiddenException("Account is deactivated")

        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }
```

### Dependency Injection (Route Protection)
FastAPI's dependency injection system is used to secure endpoints. The `get_current_user` dependency intercepts the request, verifies the token, and pulls the user from the database.

```python
# app/api/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

login_token = OAuth2PasswordBearer(tokenUrl=f"{settings.APP_PREFIX}/v1/auth/login")

def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(login_token),
) -> User:
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials")
    
    # 1. Verify the JWT signature and expiration
    payload = security.verify_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    # 2. Fetch the user to ensure they still exist and are active
    result = db.execute(select(User).filter(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    
    if not user:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user account")
        
    return user

def get_current_active_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require the current user to have an 'admin' role (RBAC)."""
    role_names = [role.name for role in current_user.roles] if current_user.roles else []
    if "admin" not in role_names:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user
```

---

## 4. End-to-End Flow

1. **Login Request:** A client sends a `POST` request to `/auth/login` with an email and password.
2. **Credential Validation:** The `AuthService` queries the DB for the user. It hashes the provided plain-text password using bcrypt and compares it against the stored hash.
3. **Token Issuance:** If valid, an Access Token (e.g. 15-minute expiry) and a Refresh Token (e.g. 7-day expiry) are created and returned to the client.
4. **Protected Resource Request:** The client requests a protected endpoint, placing the Access Token in the `Authorization: Bearer <token>` HTTP header.
5. **Route Interception:** FastAPI triggers the `Depends(get_current_user)` dependency.
6. **Token Verification:** The backend verifies the JWT signature using the `JWT_SECRET_KEY`. If it's valid and not expired, it extracts the `sub` (user_id).
7. **Database Hydration:** The backend queries the database for the user, ensures they aren't deactivated, and provides the `User` object directly to the route handler.

---

## 5. Design Decisions

1. **Access / Refresh Token Split:** 
   Storing a long-lived token directly in a client makes token revocation difficult. By keeping the access token short-lived, an admin deactivating a user only has to wait minutes before the token expires. The refresh route validates the user is still active before issuing a new access token.
2. **Strict Claims (`type="access"`):** 
   A common security flaw is users submitting a long-lived refresh token to endpoints that expect an access token. By baking a `"type": "access"` claim directly into the payload, cross-use is completely prevented.
3. **Database Hydration on Every Request:**
   While JWTs are completely stateless, we still query the database in `get_current_user` to ensure the user hasn't been deleted or deactivated *since* the token was issued. If we didn't do this, a deleted user's token would remain valid until it expired.

---

## 6. Alternatives & Trade-offs

* **JWT vs. Session Cookies (Stateful):**
  * *Alternative:* Using traditional server-side sessions (e.g., storing session IDs in Redis).
  * *Trade-off:* Sessions require a central Redis/Database lookup for *every* request simply to verify who the user is. JWTs avoid this lookup (verifying via cryptographic signature instead), making microservices easier to scale. However, JWTs cannot be instantly revoked without creating a "Token Blocklist".
* **Caching the User Object in Redis:**
  * *Alternative:* Instead of querying the SQL database in `get_current_user`, we could cache the user object in Redis.
  * *Trade-off:* This significantly reduces SQL load on every protected route. It requires careful cache invalidation if the user's role or active status changes. (Currently, the project queries SQL, but this is a prime candidate for the `@redis_cache` implementation).

---

## 7. Interview Questions & Answers

**Q1: Since JWTs are stateless, how do you handle immediate token revocation (e.g., if an account is compromised)?**
*Answer:* Immediate revocation is the primary weakness of JWTs. In this project, because we look up the user in the database in `get_current_user`, we can instantly revoke access by setting `user.is_active = False`. If we wanted to keep the user active but kill specific tokens, we would need to implement a Redis-based "Blocklist" storing the `jti` (JWT ID) of revoked tokens.

**Q2: Why use bcrypt over fast hashing algorithms like MD5 or SHA-256 for passwords?**
*Answer:* MD5 and SHA-256 are designed to be fast, which is terrible for passwords because attackers can brute-force them rapidly using GPUs. Bcrypt is intentionally slow and includes a configurable "work factor" (cost) and built-in "salting". This makes dictionary attacks and rainbow table attacks computationally infeasible.

**Q3: How do you prevent a refresh token from being used in place of an access token?**
*Answer:* When we generate tokens, we embed a custom `type` claim into the payload (`{"type": "access"}` or `{"type": "refresh"}`). The endpoints that expect access tokens (like `get_current_user`) could explicitly assert that `payload["type"] == "access"`.

**Q4: Explain how FastAPI handles the Dependency Injection for routes that require an Admin?**
*Answer:* We use chained dependencies. The `get_current_active_admin` dependency itself depends on `get_current_user`. When an endpoint requires an admin, FastAPI first executes `get_current_user` (which verifies the JWT and fetches the user). Then, `get_current_active_admin` receives that user object, checks their roles for the "admin" string, and raises a 403 Forbidden exception if it's missing.

---

## 8. Bonus: Common Mistakes & Insights

* **Symmetric vs Asymmetric Signing:** This project uses HMAC (HS256) which requires the same secret key to sign and verify. In a microservice architecture, it's safer to use RSA (RS256) so auth-services can sign with a private key, and resource-services can verify with a public key.
* **Storing JWTs in LocalStorage:** Storing tokens in a browser's LocalStorage leaves them vulnerable to XSS (Cross-Site Scripting). For maximum security in SPAs, tokens should be stored in `HttpOnly, Secure` cookies.
* **Token Expiration Gotcha:** If the timezone isn't explicitly set to `timezone.utc` when creating the `exp` claim, server timezone discrepancies can cause tokens to immediately expire upon creation.
