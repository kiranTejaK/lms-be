# Role-Based Access Control (RBAC)

## Purpose

RBAC controls **what actions a user can perform** based on their assigned roles.  The system uses a many-to-many relationship between users and roles, enforced through FastAPI dependencies at the endpoint level.

---

## Architecture Overview

```
Database:
    users ←→ user_role_association ←→ roles

Endpoint Protection:
    @router.get("/admin/dashboard")
    def dashboard(current_user = Depends(deps.get_current_active_admin)):
        ...

Dependency Chain:
    get_current_active_admin()
        └── get_current_user()
                └── verify JWT token
                └── load User with roles
        └── Check "admin" in user.roles
        └── If missing → 403 Forbidden
```

---

## Implementation Details

### Database Model

```python
# Many-to-many association table
user_role_association = Table(
    "user_role_association",
    BaseModel.metadata,
    Column("user_id", Integer, ForeignKey("users.id")),
    Column("role_id", Integer, ForeignKey("roles.id")),
)

class User(BaseModel):
    roles = relationship("Role", secondary=user_role_association, back_populates="users")

class Role(BaseModel):
    name: str  # e.g. "admin", "instructor", "student"
    users = relationship("User", secondary=user_role_association, back_populates="roles")
```

### Dependency Functions

| Dependency | Purpose | HTTP Error |
|---|---|---|
| `get_current_user` | Validates JWT, loads user, checks `is_active` | 401 / 403 |
| `get_current_active_admin` | Calls `get_current_user` + checks for `admin` role | 403 |

```python
def get_current_active_admin(current_user: User = Depends(get_current_user)) -> User:
    role_names = [role.name for role in current_user.roles]
    if "admin" not in role_names:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
```

### Role Management Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/roles/` | GET | List all roles |
| `/roles/` | POST | Create a new role |
| `/roles/assign` | POST | Assign a role to a user |

### Protected Endpoints

The following endpoints require admin role:
- `GET /admin/dashboard` — aggregate statistics
- `GET /admin/failed-tasks` — list failed background tasks
- `DELETE /admin/failed-tasks/{id}` — retry/clear a failed task
- `PUT /users/{id}/deactivate` — deactivate a user account

---

## Interaction with Other Systems

- **JWT Auth** — RBAC builds on top of JWT authentication; the user is authenticated first, then roles are checked
- **Database** — roles are eagerly loaded with `selectinload(User.roles)` to avoid N+1 queries
- **Service Layer** — role assignment is handled by `RoleService` with idempotent assignment (no error if already assigned)

---

## Error Handling Strategy

| Scenario | HTTP Status |
|---|---|
| No token provided | 401 |
| Valid token but inactive user | 403 |
| Valid user but not admin | 403 |
| Role not found during assignment | 404 |
| User not found during assignment | 404 |

---

## Production Considerations

- **Role hierarchy** — current system is flat (no inheritance); for complex permissions, consider a permission-based model
- **Caching** — user roles are loaded from DB on every request; for high-traffic systems, cache the user's role set in Redis
- **Audit logging** — log all role assignment/removal events for compliance
- **Principle of least privilege** — assign the minimum required role to each user

---

## Example Flow

1. Admin creates a new role: `POST /roles/ { "name": "instructor" }`
2. Admin assigns role to user: `POST /roles/assign { "user_id": 5, "role_id": 2 }`
3. User 5 now has the "instructor" role
4. When a protected admin endpoint is hit:
   - JWT is validated → User loaded → `user.roles` checked
   - If `"admin"` role is present → access granted
   - If `"admin"` role is missing → `403 Forbidden`
