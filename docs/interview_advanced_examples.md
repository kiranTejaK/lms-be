# Advanced Backend Interview Guide
*(Complete Implementation Examples from the Project)*

This document contains full, unabridged examples from the project architecture, directly mirroring the exact files and setups to help you prepare for advanced backend engineering interviews.

---

## 1. Advanced Service Logic (`advanced_service.py`)

Here are all 5 advanced database patterns explicitly implemented in the `advanced_service.py` file, showcasing how to handle multiple tables, concurrency, locking, and bulk operations.
# spend one round of coding 
### 1.1 Atomic Concurrent Enrollment (Transaction + Row Locking)
**Concept:** When multiple users try to enroll simultaneously, you must lock the course row to prevent exceeding `max_students`.
```python
def concurrent_enroll(self, req: BulkEnrollRequest, background_tasks: BackgroundTasks = None) -> dict:
    try:
        # Lock the course row to prevent race conditions
        stmt = (
            select(Course)
            .filter(Course.id == req.course_id)
            .with_for_update()
        )
        course = self.db.execute(stmt).scalar_one_or_none()

        # Check capacity safely within the lock
        current_count = self.db.scalar(
            select(func.count(Enrollment.id))
            .filter(Enrollment.course_id == req.course_id)
        )
        if current_count + len(req.user_ids) > course.max_students:
            raise ValidationException("Course is at maximum capacity")

        # Batch-insert enrollments
        new_enrollments = []
        for user_id in req.user_ids:
            enrollment = Enrollment(user_id=user_id, course_id=req.course_id)
            self.db.add(enrollment)
            new_enrollments.append(enrollment)

        self.db.commit() # Assigns IDs and releases lock
        clear_cache("*:courses:*")
        
        return {"status": "success", "enrolled_count": len(new_enrollments)}
    except Exception:
        self.db.rollback()
        raise
```
# spend 2 rounds of coding
### 1.2 Instructor Dashboard (N+1 Prevention with Multiple Tables)
**Concept:** Fetching nested relationships (Instructor -> Courses -> Lessons) can cause an N+1 query problem. Use `selectinload` and `joinedload` to resolve this into a fixed number of queries.
```python
def get_instructor_dashboard(self, instructor_id: int) -> dict:
    stmt = (
        select(Instructor)
        .options(
            joinedload(Instructor.user),
            selectinload(Instructor.courses)
            .selectinload(Course.lessons),
        )
        .filter(Instructor.id == instructor_id)
    )
    instructor = self.db.execute(stmt).unique().scalar_one_or_none()
    
    # Separate aggregate query for enrollment counts (avoids cartesian join)
    course_ids = [c.id for c in instructor.courses]
    rows = self.db.execute(
        select(Enrollment.course_id, func.count(Enrollment.id).label("cnt"))
        .filter(Enrollment.course_id.in_(course_ids))
        .group_by(Enrollment.course_id)
    ).all()
    # ... returns formatted dictionary
```
# spend one rpund of coding
### 1.3 Bulk Course Creation (Atomic Transaction + Rollback)
**Concept:** Batch insert records. If one fails (e.g., FK constraint), the entire batch must rollback so no partial state is left.
```python
def bulk_create_courses(self, req: BulkCourseCreateRequest) -> dict:
    try:
        new_courses = []
        for item in req.courses:
            course = Course(**item.model_dump())
            self.db.add(course)
            new_courses.append(course)

        self.db.flush()  # Assign IDs before commit
        course_ids = [c.id for c in new_courses]
        self.db.commit()
        return {"status": "success", "course_ids": course_ids}
    except Exception as exc:
        self.db.rollback()
        raise AppException(f"Bulk course creation failed: {exc}")
```
# spend 2 rounds of coding
### 1.4 Course Analytics (Aggregation + Subquery Optimization)
**Concept:** Push aggregation logic (averages, counts) into the database instead of pulling all rows into Python.
```python
def get_course_analytics(self) -> dict:
    stmt = (
        select(
            Course.id.label("course_id"),
            func.count(Enrollment.id).label("enrollment_count"),
            func.coalesce(
                func.avg(case((Enrollment.completed == True, 100.0), else_=0.0)), 
                0.0
            ).label("completion_rate"),
            func.coalesce(func.avg(Enrollment.progress), 0.0).label("avg_progress"),
        )
        .outerjoin(Enrollment, Course.id == Enrollment.course_id)
        .group_by(Course.id)
    )
    rows = self.db.execute(stmt).all()
    # ... returns formatted dictionary
```

# spend 2 rounds of coding
### 1.5 Transfer Enrollment (Deadlock Avoidance)
**Concept:** When moving a record between two locked rows (Course A to Course B), order lock acquisition by ID to prevent cross-locking deadlocks.
```python
def transfer_enrollment(self, req: TransferEnrollmentRequest) -> dict:
    try:
        # Order lock acquisition by ID to prevent deadlocks
        first_id, second_id = sorted([req.from_course_id, req.to_course_id])

        self.db.execute(select(Course).filter(Course.id == first_id).with_for_update()).scalar_one_or_none()
        self.db.execute(select(Course).filter(Course.id == second_id).with_for_update()).scalar_one_or_none()

        # Perform the transfer: delete old → create new
        enrollment = self.db.execute(
            select(Enrollment).filter(Enrollment.user_id == req.user_id, Enrollment.course_id == req.from_course_id)
        ).scalar_one_or_none()
        
        self.db.delete(enrollment)
        new_enrollment = Enrollment(user_id=req.user_id, course_id=req.to_course_id)
        self.db.add(new_enrollment)
        
        self.db.commit()
        return {"status": "success", "new_enrollment_id": new_enrollment.id}
    except Exception:
        self.db.rollback()
        raise
```

### 1.6 Bulk Update using Native SQL Update (No Iteration)
**Source:** `course_service.py`
**Concept:** Instead of pulling all courses into memory to update their category ID via a Python for-loop, construct a native SQL `UPDATE` statement. This is drastically faster and atomic.
```python
def bulk_update_course_categories(self, old_category_id: int, new_category_id: int) -> dict:
    stmt = (
        update(Course)
        .where(Course.category_id == old_category_id)
        .values(category_id=new_category_id)
    )
    result = self.db.execute(stmt)
    self.db.commit()
    
    clear_cache("*:courses:*")
    return {"updated_count": result.rowcount}
```

### 1.7 Safe Single Enrollment with Background Tasks
**Source:** `course_service.py` / `user_service.py`
**Concept:** Utilizing `with_for_update()` to prevent race conditions on a single enrollment, and delegating the non-blocking email sending process to FastAPI's `BackgroundTasks` via a custom retry manager.
```python
def enroll_in_course(self, course_id: int, current_user: User, background_tasks: BackgroundTasks = None) -> dict:
    try:
        # Lock the row for concurrency safety
        stmt = select(Course).filter(Course.id == course_id).with_for_update()
        course = self.db.execute(stmt).scalar_one_or_none()

        # Check existing enrollment
        existing = self.db.execute(
            select(Enrollment).filter(
                Enrollment.user_id == current_user.id,
                Enrollment.course_id == course_id,
            )
        ).scalar_one_or_none()
        if existing: raise ConflictException("Already enrolled")

        enrollment = Enrollment(user_id=current_user.id, course_id=course_id)
        self.db.add(enrollment)
        self.db.commit()

        # Send email in background to prevent blocking HTTP response
        task_manager = BackgroundTaskManager(self.db)
        if background_tasks:
            background_tasks.add_task(
                task_manager.execute_with_retry, 
                self._send_enrollment_email, 
                current_user.email, 
                course.title
            )

        return {"status": "success"}
    except Exception:
        self.db.rollback()
        raise
```

---

## 2. Isolated Logging

### 2.1 The Setup (`app/core/logging.py`)
The project configures `structlog` alongside Python's standard `logging` library. It uses a processor chain to ensure every log entry receives standard keys (like ISO timestamps, logger names, and log levels). It dynamically uses a `JSONRenderer` in production for easy ingestion by Datadog/ELK, and `ConsoleRenderer` for local development.

```python
import logging
import structlog

def setup_logging() -> None:
    processors = [
        structlog.contextvars.merge_contextvars, # Crucial for isolated request IDs
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer() # Or ConsoleRenderer
    ]
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
```

### 2.2 The Middleware (`app/middleware/RequestLoggingMiddleware.py`)
To isolate logs per-request in high-concurrency async apps, it uses `structlog.contextvars`.
```python
from starlette.middleware.base import BaseHTTPMiddleware
import structlog
import uuid

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        
        # Bind the correlation ID so all subsequent logs in this request include it
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        
        try:
            response = await call_next(request)
            return response
        finally:
            # Always clear context vars to prevent leaking to other requests in async workers
            structlog.contextvars.clear_contextvars()
```

### 2.3 Example Use Case
In `advanced_service.py`, when calling `logger.info("bulk_enrollment_success", count=10)`, you do not need to pass the `correlation_id` manually. Because of the middleware and `merge_contextvars` setup, the final JSON log automatically looks like this:
```json
{
  "event": "bulk_enrollment_success",
  "count": 10,
  "correlation_id": "8a32f91-uuid-42",
  "timestamp": "2026-05-31T01:12:00Z"
}
```

---

## 3. Isolated Redis Cache

### 3.1 The Setup (`app/core/redis.py`)
The Redis setup is designed with Graceful Degradation. We use strict timeouts (`socket_timeout=5`) and wrap `get`/`set` in try-except blocks. If Redis crashes, it falls back to the database automatically.
```python
import redis
import structlog

logger = structlog.get_logger(__name__)
redis_client = redis.Redis(host='localhost', port=6379, socket_timeout=5)

def cache_get(key: str):
    try:
        return redis_client.get(key)
    except redis.RedisError as exc:
        logger.warning("redis_get_failed", key=key, error=str(exc))
        return None # Graceful failure
```

### 3.2 Decorator Implementation
The decorator dynamically builds keys using MD5 hashes for queries (to handle kwargs) or deterministic IDs for entities.
```python
import json
from functools import wraps

def redis_cache(key_generator_func, expire_seconds: int = 3600):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = key_generator_func("module", func.__name__, *args, **kwargs)

            # Attempt to read cache gracefully
            cached = cache_get(key)
            if cached is not None:
                return json.loads(cached)

            # Cache Miss -> Execute DB query
            result = func(*args, **kwargs)

            # Serialize & save to cache gracefully
            serialized = json.dumps(result, default=str)
            cache_set(key, serialized, expire_seconds)

            return result
        return wrapper
    return decorator
```

### 3.3 Cache Stampede Explanation
**What is it?** When a high-traffic key (e.g., "global_site_stats") expires, hundreds of concurrent requests will suddenly "miss" the cache at the exact same millisecond. They all proceed to execute the heavy database query, crashing the database.
**How to fix it:** Implement a Distributed Lock. Before hitting the DB, the first request acquires a lock (e.g., Redis `SETNX lock_key 1 EX 10`). The other requests fail to acquire the lock and instead wait (sleep) and retry the cache read in 50ms, successfully getting the data the first request populated.

### 3.4 Example Use Case
In the API routes, fetching heavy paginated data is wrapped:
```python
@redis_cache(key_generator_func=query_key_generator, module="courses")
def get_courses_list(self, skip=0, limit=100):
    return self.db.query(Course).offset(skip).limit(limit).all()
```

---

## 4. Advanced Pydantic Validation (V2)

Demonstrating `Optional`, nested schemas, and conditional custom validation using `mode='after'`.

```python
from pydantic import BaseModel, Field, EmailStr, model_validator
from typing import List, Optional

class Address(BaseModel):
    street: str
    city: str
    zipcode: str = Field(pattern=r"^\d{5}(?:-\d{4})?$")

class AdvancedUserProfileUpdate(BaseModel):
    # Optional fields (client can omit them entirely)
    first_name: Optional[str] = Field(None, min_length=2, max_length=50)
    last_name: Optional[str] = Field(None, min_length=2, max_length=50)
    email: Optional[EmailStr] = None
    
    # Nested Object definition
    address: Optional[Address] = None
    
    # List constraint
    skills: List[str] = Field(default_factory=list, max_length=10)
    
    # Related constraints requiring cross-field validation
    is_freelancer: bool = False
    hourly_rate: Optional[float] = None

    @model_validator(mode='after')
    def validate_freelancer_rate(self):
        """
        Custom Validator: if user is a freelancer, hourly_rate is strictly required.
        """
        if self.is_freelancer and self.hourly_rate is None:
            raise ValueError("hourly_rate must be provided if is_freelancer is true")
        if not self.is_freelancer and self.hourly_rate is not None:
            raise ValueError("hourly_rate should not be provided if not a freelancer")
            
        # Data sanitization / coercion
        if self.first_name:
            self.first_name = self.first_name.title()
            
        return self
```
