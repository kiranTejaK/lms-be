# JWT Authentication

## Purpose

JWT (JSON Web Tokens) provides **stateless authentication** for the API.  After a successful login, the client receives a token pair (access + refresh) and includes the access token in subsequent requests.  The server validates the token's signature and expiry without needing a database lookup on every request.

---

## Architecture Overview

```
Login Request (email + password)
    └── AuthService.login()
            ├── Verify password against bcrypt hash
            ├── create_access_token(sub=user_id, type="access")   → 30 min
            └── create_refresh_token(sub=user_id, type="refresh") → 7 days

Authenticated Request
    └── Authorization: Bearer <access_token>
            └── deps.get_current_user()
                    └── verify_token(token) → payload → db.get(User, id)
```

Core modules:
- **`app/core/security.py`** — token creation/verification, password hashing
- **`app/services/auth_service.py`** — login, refresh, change-password logic
- **`app/api/deps.py`** — FastAPI dependencies for auth enforcement

---

## Implementation Details

### Token Structure

Both access and refresh tokens contain:

```json
{
  "sub": "42",          // User ID (string)
  "exp": 1711234567,    // Expiration timestamp (UTC)
  "type": "access"      // "access" or "refresh"
}
```

The `type` claim prevents refresh tokens from being used as access tokens and vice versa.

### Password Hashing

```python
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
```

- **bcrypt** — slow-by-design hash function resistant to brute-force attacks
- **`deprecated="auto"`** — automatically re-hashes on login if the hash scheme is outdated

### Token Lifecycle

| Token | Default Expiry | Purpose |
|---|---|---|
| Access Token | 30 minutes | Short-lived; sent with every API request |
| Refresh Token | 7 days | Long-lived; exchanged for a new token pair |

### Refresh Flow

```
POST /auth/refresh  { "refresh_token": "..." }
    └── verify_token() → extract user_id
    └── Verify user exists and is active
    └── Issue new access + refresh tokens
```

### Protected Endpoints

Any endpoint that declares `current_user: User = Depends(deps.get_current_user)` requires a valid access token.

```python
@router.get("/me")
def get_current_user_info(current_user: User = Depends(deps.get_current_user)):
    return current_user
```

---

## Configuration Variables

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET_KEY` | `change-me-in-production` | HMAC signing key (min 32 bytes recommended) |
| `JWT_ALGORITHM` | `HS256` | Signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRY_IN_MINUTES` | `30` | Access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRY_IN_MINUTES` | `10080` | Refresh token TTL (7 days) |

---

## Interaction with Other Systems

- **Database** — `get_current_user` loads the `User` model from PostgreSQL using the token's `sub` claim
- **RBAC** — `get_current_active_admin` extends auth with role checks
- **Middleware** — token validation happens in the dependency layer, before the endpoint handler runs

---

## Error Handling Strategy

| Scenario | HTTP Status | Response |
|---|---|---|
| Missing `Authorization` header | 401 | `Not authenticated` |
| Invalid / expired token | 401 | `Could not validate credentials` |
| Inactive user | 403 | `Account is deactivated` |
| Wrong password on login | 400 | `Incorrect email or password` |
| Invalid refresh token | 401 | `Invalid refresh token` |

---

## Production Considerations

- **Secret key** — use a strong, random key (e.g. `openssl rand -hex 32`); never commit to version control
- **HTTPS only** — tokens in transit must be encrypted; enforce HTTPS in production
- **Token blacklist** — for server-side logout, implement a Redis-backed blacklist of revoked tokens
- **Key rotation** — periodically rotate `JWT_SECRET_KEY`; old tokens will naturally expire
- **Short access TTL** — keep access tokens short-lived (15–30 min) to limit the damage window from stolen tokens

---

## Example Flow

1. `POST /doit/v1/auth/login` with `email` + `password`
2. Server verifies password → issues `access_token` (30 min) + `refresh_token` (7 days)
3. Client stores both tokens
4. `GET /doit/v1/auth/me` with `Authorization: Bearer <access_token>`
5. `deps.get_current_user()` decodes token → loads User from DB → returns user data
6. When access token expires → `POST /doit/v1/auth/refresh` with `refresh_token`
7. Server issues new token pair → client updates stored tokens
