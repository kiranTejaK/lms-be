# Endpoints Full Flow

## Purpose

This document traces the **full lifecycle of a request** through the application to illustrate how all architectural layers interact.  It covers 3 representative flows: a simple read, an authenticated write, and a transactional operation.

---

## Application Layers

```
┌────────────────────────────────────────────┐
│  1. FastAPI Router (app/api/v1/endpoints/) │  HTTP parsing, validation, dependencies
│  2. Dependencies (app/api/deps.py)         │  Auth, DB session injection
│  3. Service Layer (app/services/)          │  Business logic, caching, integrations
│  4. Database / ORM (SQLAlchemy 2.0+)       │  Queries, transactions, relationships
│  5. External Services (Redis, S3, SMTP)    │  Caching, file storage, email
└────────────────────────────────────────────┘
```

---

## Flow 1: Listing Courses (Public, Cached)

**`GET /doit/v1/courses/?skip=0&limit=10`**

```
1. RequestLoggingMiddleware → logs "request_started"
2. FastAPI matches route → courses.get_courses()
3. Depends(get_db) → yields a SQLAlchemy Session
4. CourseService(db).get_courses(skip=0, limit=10) is called
5. @redis_cache decorator:
   a. Generates key: "doit:v1:courses:get_courses:query:<hash>"
   b. cache_get(key) → None (cache miss)
6. Service executes:
   SELECT * FROM courses
   LEFT JOIN categories ON ...
   LEFT JOIN instructors ON ...
   OFFSET 0 LIMIT 10
   (with selectinload + joinedload to avoid N+1)
7. Result serialised → cache_set(key, json, 3600)
8. FastAPI converts ORM objects → CourseResponse (via Pydantic)
9. JSON response sent to client (200 OK)
10. RequestLoggingMiddleware → logs "request_finished" with process_time
```

---

## Flow 2: Enrolling in a Course (Authenticated, Transactional)

**`POST /doit/v1/courses/5/enroll`** with `Authorization: Bearer <token>`

```
1. RequestLoggingMiddleware → logs "request_started"

2. FastAPI matches route → courses.enroll_in_course()

3. Dependencies resolve (in order):
   a. Depends(get_db) → yields DB session
   b. Depends(get_current_user):
      - Extracts token from Authorization header
      - verify_token(token) → {"sub": "42", "type": "access"}
      - SELECT * FROM users WHERE id = 42
      - Checks is_active = True
      - Returns User object

4. CourseService(db).enroll_in_course(course_id=5, current_user=User(42))

5. Transaction begins:
   a. SELECT * FROM courses WHERE id = 5 FOR UPDATE  ← row lock
   b. SELECT * FROM enrollments WHERE user_id = 42 AND course_id = 5
      → None (not enrolled yet)
   c. SELECT COUNT(*) FROM enrollments WHERE course_id = 5
      → 23 (below max_students = 50)
   d. INSERT INTO enrollments (user_id, course_id) VALUES (42, 5)
   e. COMMIT

6. Cache invalidation: clear_cache for course 5
7. Returns {"status": "success", "enrollment_id": 101}
8. RequestLoggingMiddleware → logs "request_finished"
```

**Race condition protection:**
The `FOR UPDATE` lock on step 5a prevents concurrent enrollments from exceeding `max_students`.  If two requests arrive simultaneously, the second one blocks until the first commits.

---

## Flow 3: Admin Dashboard (Protected, Aggregated)

**`GET /doit/v1/admin/dashboard`** with admin token

```
1. Dependencies resolve:
   a. Depends(get_db) → DB session
   b. Depends(get_current_active_admin):
      - Calls get_current_user() → loads User with roles
      - Checks "admin" in user.roles → passes
      - Returns admin User object

2. AdminService(db).get_dashboard_stats()

3. Executes 5 COUNT queries:
   - SELECT COUNT(*) FROM users
   - SELECT COUNT(*) FROM courses
   - SELECT COUNT(*) FROM enrollments
   - SELECT COUNT(*) FROM categories
   - SELECT COUNT(*) FROM lessons

4. Returns:
   {
     "total_users": 150,
     "total_courses": 45,
     "total_enrollments": 1200,
     "total_categories": 12,
     "total_lessons": 340
   }
```

---

## Complete Endpoint Reference

### Auth (6 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | No | Login with email + password |
| POST | `/auth/register` | No | Create new account |
| POST | `/auth/refresh` | No | Exchange refresh token |
| GET | `/auth/me` | Yes | Current user details |
| POST | `/auth/change-password` | Yes | Change password |
| POST | `/auth/logout` | No | Client-side logout |

### Users (5 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/users/` | No | List all users (paginated) |
| GET | `/users/{id}/profile` | No | Get user profile |
| PUT | `/users/{id}/profile` | Yes | Update own profile |
| PUT | `/users/{id}/profile/avatar` | Yes | Upload avatar to S3 |
| PUT | `/users/{id}/deactivate` | Admin | Deactivate user |

### Courses (8 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/courses/` | No | List courses (cached) |
| GET | `/courses/{id}` | No | Get single course (cached) |
| GET | `/courses/{id}/detailed` | No | Course with all relations |
| POST | `/courses/` | No | Create course |
| PUT | `/courses/{id}` | No | Update course |
| DELETE | `/courses/{id}` | No | Delete course |
| POST | `/courses/{id}/enroll` | Yes | Enroll with row locking |
| POST | `/courses/bulk-update-category` | No | Bulk reassign categories |

### Categories (5 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/categories/` | No | List categories |
| GET | `/categories/{id}` | No | Get category |
| POST | `/categories/` | No | Create category |
| PUT | `/categories/{id}` | No | Update category |
| DELETE | `/categories/{id}` | No | Delete category |

### Lessons (5 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/lessons/by-course/{id}` | No | List lessons for a course |
| GET | `/lessons/{id}` | No | Get single lesson |
| POST | `/lessons/` | No | Create lesson |
| PUT | `/lessons/{id}` | No | Update lesson |
| DELETE | `/lessons/{id}` | No | Delete lesson |

### Enrollments (4 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/enrollments/user/{id}` | No | User's enrollments |
| GET | `/enrollments/course/{id}` | No | Course's enrollments |
| PUT | `/enrollments/{id}` | No | Update progress |
| DELETE | `/enrollments/{id}` | Yes | Unenroll (owner only) |

### Instructors (4 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/instructors/` | No | List instructors |
| GET | `/instructors/{id}` | No | Get instructor |
| POST | `/instructors/` | No | Create instructor |
| PUT | `/instructors/{id}` | No | Update instructor |

### Roles (3 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/roles/` | No | List roles |
| POST | `/roles/` | No | Create role |
| POST | `/roles/assign` | No | Assign role to user |

### Admin (3 endpoints)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/admin/dashboard` | Admin | Aggregate stats |
| GET | `/admin/failed-tasks` | Admin | List failed tasks |
| DELETE | `/admin/failed-tasks/{id}` | Admin | Retry/clear task |

### Health (1 endpoint)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | No | Liveness probe |

**Total: 44 endpoints** (39 API + 1 health + 4 implicit OpenAPI/docs)
