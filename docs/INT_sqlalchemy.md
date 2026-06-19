# SQLAlchemy Schema Design & Advanced Queries: Strategy & Implementation

## 1. Concept Overview

**What it is:**
SQLAlchemy is an Object-Relational Mapper (ORM) for Python. This project utilizes the modern **SQLAlchemy 2.0** paradigm, characterized by strict type-hinting (`Mapped[]`), declarative mappings, and explicitly compiled 2.0-style select statements.

**Why it is used:**
SQLAlchemy abstracts away raw SQL, allowing us to manage complex relationships, execute atomic bulk operations, and enforce database constraints via Python. The 2.0 style drastically improves IDE auto-completion and static type checking. Furthermore, utilizing SQLAlchemy's advanced features (eager loading, row-level locks, and subqueries) allows the backend to be heavily optimized for production concurrency without N+1 query bottlenecks.

---

## 2. Project Setup (Configuration & Core Utilities)

The database core is initialized with a connection pool and standard naming conventions to ensure smooth Alembic migrations.

### Engine and Session Factory
The engine is configured with connection pooling (`pool_size` and `max_overflow`) to handle high concurrency efficiently. `pool_pre_ping` prevents the application from using stale database connections.

```python
# app/db/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URI,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

### Declarative Base & Naming Conventions
A unified naming convention is passed to the `MetaData`. This is critical: if constraints aren't explicitly named, auto-generated Alembic migrations can fail when attempting to drop or alter tables later.

```python
# app/db/base.py
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

class BaseModel(DeclarativeBase):
    """Base class for all SQLAlchemy 2.0 mapped models."""
    metadata = MetaData(naming_convention=convention)
    __abstract__ = True
```

### Mixins
Mixins apply common columns (like IDs and timestamps) automatically to models.

```python
# app/db/mixins.py
from sqlalchemy import Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, declarative_mixin
from sqlalchemy.sql import func
from datetime import datetime

@declarative_mixin
class TimeStampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

---

## 3. Key Code Walkthrough: Schema Design

The project uses SQLAlchemy 2.0 type hinting (`Mapped[type]`) and explicit relationships.

### One-to-Many & Many-to-Many Relationships
The `User` model demonstrates standard columns, a Many-to-Many relationship (via an Association Table `user_roles`), and One-to-Many relationships with cascading deletes.

```python
# app/models/user.py
user_roles = Table(
    'user_roles', BaseModel.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True)
)

class User(BaseModel, IDMixin, TimeStampMixin):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    
    # Many-to-Many
    roles: Mapped[List["Role"]] = relationship("Role", secondary=user_roles, back_populates="users")
    
    # One-to-One (uselist=False)
    profile: Mapped[Optional["UserProfile"]] = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    # One-to-Many
    enrollments: Mapped[List["Enrollment"]] = relationship("Enrollment", back_populates="user", cascade="all, delete-orphan")
```

### Constraints
Database-level constraints enforce data integrity before the application logic even runs.

```python
# app/models/course.py
class Enrollment(BaseModel, IDMixin, TimeStampMixin):
    __tablename__ = 'enrollments'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    course_id: Mapped[int] = mapped_column(ForeignKey('courses.id', ondelete='CASCADE'))

    # Prevent a user from enrolling in the same course twice at the DB schema level
    __table_args__ = (UniqueConstraint('user_id', 'course_id', name='uq_enrollments_user_id'),)
```

---

## 4. Key Code Walkthrough: Query Strategies

The Service layer utilizes highly optimized queries. Here are the core patterns used:

### A. Preventing N+1 Queries (Eager Loading)
To load an instructor, their associated user object, their courses, AND the lessons within those courses efficiently:
* `joinedload` is used for single-row mappings (One-to-One / Many-to-One) via a SQL `LEFT OUTER JOIN`.
* `selectinload` is used for collections (One-to-Many) by emitting a second `SELECT ... IN (...)` query, avoiding cartesian explosions.

```python
# app/services/advanced_service.py
stmt = (
    select(Instructor)
    .options(
        joinedload(Instructor.user),
        selectinload(Instructor.courses).selectinload(Course.lessons),
    )
    .filter(Instructor.id == instructor_id)
)
instructor = self.db.execute(stmt).unique().scalar_one_or_none()
```

### B. Pessimistic Row Locking (`with_for_update`)
When modifying critical data concurrently (like transferring an enrollment or checking course capacity), rows are locked at the database level using `SELECT ... FOR UPDATE`.

```python
# app/services/advanced_service.py -> transfer_enrollment
# We sort IDs before locking to prevent deadlocks when concurrent requests transfer in opposite directions!
first_id, second_id = sorted([req.from_course_id, req.to_course_id])

first_course = self.db.execute(
    select(Course).filter(Course.id == first_id).with_for_update()
).scalar_one_or_none()

second_course = self.db.execute(
    select(Course).filter(Course.id == second_id).with_for_update()
).scalar_one_or_none()
```

### C. Advanced Aggregation & Math in SQL
Instead of pulling rows into Python and looping, operations are pushed down to the SQL engine using `func`, `group_by`, and `case`.

```python
# app/services/advanced_service.py
stmt = (
    select(
        Course.id,
        func.count(Enrollment.id).label("enrollment_count"),
        # SQL: AVG(CASE WHEN completed = TRUE THEN 100 ELSE 0 END)
        func.coalesce(
            func.avg(
                case((Enrollment.completed == True, 100.0), else_=0.0)
            ), 0.0
        ).label("completion_rate")
    )
    .outerjoin(Enrollment, Course.id == Enrollment.course_id)
    .group_by(Course.id)
)
rows = self.db.execute(stmt).all()
```

### D. Bulk Updates (No ORM Instantiation)
To update thousands of rows instantly, the ORM is bypassed in favor of an explicit `UPDATE` statement.

```python
# app/services/course_service.py
stmt = (
    update(Course)
    .where(Course.category_id == old_category_id)
    .values(category_id=new_category_id)
)
result = self.db.execute(stmt)
self.db.commit()
```

---

## 5. End-to-End Flow

1. **Request Arrives:** An endpoint requesting complex data (e.g., "Instructor Dashboard") is hit.
2. **Dependency Injection:** FastAPI injects a clean, scoped `db` session (from `SessionLocal`) into the route.
3. **Query Construction:** The service layer builds a SQLAlchemy 2.0 `select()` statement, explicitly defining eager loads (`selectinload` / `joinedload`) to prevent N+1 queries.
4. **Execution:** The session executes the query. SQLAlchemy translates the Python logic into a highly optimized raw SQL string.
5. **Serialization:** The resulting models are mapped directly to Pydantic schemas and returned.
6. **Teardown:** The route finishes, and FastAPI's `yield` dependency block closes the session, returning the connection to the pool.

---

## 6. Design Decisions

1. **SQLAlchemy 2.0 Paradigm:** We utilize `select(Model).where(...)` instead of the legacy `session.query(Model).filter(...)`. This ensures compatibility with asyncio in the future and provides strict static type checking.
2. **Pessimistic Locking vs Optimistic Locking:** For enrollments, we use `with_for_update()` (Pessimistic) rather than version counters (Optimistic) because the collision rate on a highly sought-after course dropping new seats is incredibly high.
3. **Deadlock Prevention Strategy:** When locking two rows simultaneously (e.g., transferring an enrollment between courses), the service explicitly sorts the IDs numerically and acquires the locks in ascending order. This guarantees multiple concurrent threads can never form a cyclical deadlock.

---

## 7. Interview Questions & Answers

**Q1: What is the N+1 query problem, and how do you solve it in SQLAlchemy?**
*Answer:* The N+1 problem occurs when you fetch a list of items (1 query), and then loop through them, fetching their related children (N queries). In SQLAlchemy, we solve this using Eager Loading: `joinedload` (which does a SQL JOIN for single-item relationships) or `selectinload` (which does a separate `SELECT ... IN (...)` query for collections). 

**Q2: Why wouldn't you use `joinedload` for a collection (One-to-Many)?**
*Answer:* Using a `joinedload` on a One-to-Many relationship duplicates the parent data for every child row returned (Cartesian product). If you load 100 courses and each has 50 lessons, the DB returns 5000 rows over the network, wasting massive bandwidth. `selectinload` is far more efficient for collections.

**Q3: Explain the purpose of `with_for_update()`. When would you use it?**
*Answer:* `with_for_update()` translates to a SQL `SELECT ... FOR UPDATE`. It tells the database to place a lock on those specific rows for the duration of the current transaction. No other transaction can modify (or in some DBs, even read) those rows until we `commit()` or `rollback()`. We use it to prevent race conditions, such as multiple users enrolling in a course with only 1 seat left at the exact same millisecond.

**Q4: How do you perform a bulk update without loading models into memory?**
*Answer:* We use SQLAlchemy's explicit `update()` statement (`update(Model).where(...).values(...)`) followed by `db.execute()`. This translates to a direct SQL `UPDATE` statement, entirely bypassing the ORM's object instantiation. It updates millions of rows in milliseconds instead of hours.

---

## 8. Bonus: Common Mistakes & Performance Insights

* **`unique()` missing after `joinedload`:** When using `joinedload` in a 2.0 `select()` statement, SQLAlchemy requires you to call `.unique()` on the result before fetching scalars (`db.execute(stmt).unique().scalar_one_or_none()`). Failing to do so will raise an exception.
* **Cascading Deletes:** A massive performance killer is relying entirely on SQLAlchemy's ORM `cascade="all, delete-orphan"` without setting `ondelete='CASCADE'` on the physical Foreign Key constraint in the database schema. If the DB handles the cascade, it's virtually instantaneous. If the ORM handles it, it has to `SELECT` every single child row and issue individual `DELETE` statements. We implement both in this project for maximum safety and performance.
