# Learning Platform API

A production-grade, synchronous FastAPI backend for an online learning platform.  Implements **39 API endpoints** with JWT authentication, Redis caching, PostgreSQL persistence, and full Docker support.

---

## Architecture Overview

The application follows a **4-layer synchronous architecture**:

```
┌───────────────────────────────────────────────────────┐
│  API Layer        (app/api/)        HTTP + validation  │
│  Service Layer    (app/services/)   Business logic     │
│  CRUD Layer       (app/crud/)       Generic DB ops     │
│  Model Layer      (app/models/)     SQLAlchemy ORM     │
└───────────────────────────────────────────────────────┘
        External: Redis │ PostgreSQL │ AWS S3 │ SMTP
```

**Why synchronous?** — Simplifies the stack, avoids async footguns, and is performant for I/O-bound workloads when paired with connection pooling and Redis caching.

---

## Technology Stack

| Component | Technology |
|---|---|
| Framework | FastAPI (sync mode) |
| ORM | SQLAlchemy 2.0+ |
| Database | PostgreSQL 16 (psycopg driver) |
| Caching | Redis 7 |
| Auth | JWT (PyJWT) + bcrypt |
| Email | SMTP via Brevo + Jinja2 templates |
| File Storage | AWS S3 (boto3) |
| Logging | structlog + stdlib RotatingFileHandler |
| Testing | pytest + TestClient (SQLite) |
| CI/CD | GitHub Actions |
| Containerisation | Docker + Docker Compose |

---

## Project Structure

```
fullstack_prod/
├── app/
│   ├── api/
│   │   ├── deps.py                  # Auth & DB dependencies
│   │   └── v1/
│   │       ├── api.py               # Router aggregation
│   │       └── endpoints/           # 9 endpoint modules (39 total)
│   ├── core/
│   │   ├── config.py                # Pydantic settings (env vars)
│   │   ├── exceptions.py            # Centralised exception hierarchy
│   │   ├── logging.py               # structlog configuration
│   │   ├── redis.py                 # Cache layer with graceful degradation
│   │   ├── security.py              # JWT + bcrypt utilities
│   │   └── tasks.py                 # Sync background task retry manager
│   ├── crud/base.py                 # Generic CRUD base class
│   ├── db/
│   │   ├── base.py                  # SQLAlchemy Base with naming conventions
│   │   ├── mixins.py                # Timestamp mixin
│   │   └── session.py               # Engine + SessionLocal factory
│   ├── middleware/
│   │   └── RequestLoggingMiddleware.py
│   ├── models/                      # User, Role, Course, Lesson, etc.
│   ├── schemas/                     # Pydantic V2 request/response schemas
│   ├── services/                    # Business logic (auth, user, course, etc.)
│   ├── templates/                   # Jinja2 email templates
│   └── main.py                      # Application entry point
├── tests/                           # 58 pytest tests (9 test files)
├── alembic/                         # Database migrations
├── docs/                            # Integration documentation
├── .github/workflows/ci.yml         # CI pipeline
├── Dockerfile                       # Multi-stage production build
├── docker-compose.yml               # Full stack (app + PostgreSQL + Redis)
├── pyproject.toml                    # Dependencies and tool config
└── .env.example                     # Environment variable template
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL 16+ (or Docker)
- Redis 7+ (or Docker)

### 1. Clone the Repository

```bash
git clone <repository-url>
cd fullstack_prod
```

### 2. Environment Variables

```bash
cp .env.example .env
# Edit .env with your local PostgreSQL and Redis credentials
```

Key variables to set:
```env
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=prac_db
REDIS_HOST=localhost
REDIS_PORT=6379
JWT_SECRET_KEY=a-strong-random-secret-key
```

### 3. Install Dependencies

```bash
pip install -e ".[dev]"
```

### 4. Run Database Migrations

```bash
alembic upgrade head
```

### 5. Start the Server

```bash
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

---

## Running with Docker

### Quick Start (recommended)

```bash
docker compose up --build
```

This starts:
- **PostgreSQL 16** on port 5432
- **Redis 7** on port 6379
- **FastAPI app** on port 8000

All services have health checks — the app waits for PostgreSQL and Redis to be ready before starting.

### Build Image Only

```bash
docker build -t fullstack-prod:latest .
```

### Stop Services

```bash
docker compose down          # Stop containers
docker compose down -v       # Stop + remove volumes (data reset)
```

---

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=app --cov-report=term-missing

# Specific test file
pytest tests/test_auth.py -v
```

Tests use SQLite (in-memory) and mocked Redis — no external services needed.

---

## Deployment Guide

### 1. Prepare Environment

Set all production environment variables (see `.env.example`):
```bash
export ENVIRONMENT=production
export JWT_SECRET_KEY=$(openssl rand -hex 32)
export DB_HOST=your-rds-endpoint
# ... other variables
```

### 2. Build and Push Docker Image

```bash
docker build -t your-registry/fullstack-prod:latest .
docker push your-registry/fullstack-prod:latest
```

### 3. Deploy with Docker Compose

```bash
# On the server:
docker compose -f docker-compose.yml up -d
```

### 4. Run Migrations

```bash
docker compose exec app alembic upgrade head
```

### 5. Verify Deployment

```bash
curl http://your-server:8000/health
# {"status":"ok","environment":"production"}
```

---

## Useful Commands

| Command | Description |
|---|---|
| `uvicorn app.main:app --reload` | Run dev server |
| `pytest tests/ -v` | Run test suite |
| `alembic revision --autogenerate -m "message"` | Create migration |
| `alembic upgrade head` | Apply migrations |
| `alembic downgrade -1` | Rollback last migration |
| `docker compose up --build` | Start full stack |
| `docker compose logs -f app` | Tail app logs |
| `docker compose exec app alembic upgrade head` | Migrate in Docker |

---

## API Documentation

When the server is running, interactive documentation is available at:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **OpenAPI JSON**: `http://localhost:8000/doit/v1/openapi.json`

See [`docs/endpoints_full_flow.md`](docs/endpoints_full_flow.md) for detailed request flow documentation.

---

## Integration Documentation

Detailed docs for each integration are in the [`docs/`](docs/) directory:

| Document | Topic |
|---|---|
| [`redis_integration.md`](docs/redis_integration.md) | Caching layer architecture |
| [`logging_system.md`](docs/logging_system.md) | Structured logging setup |
| [`s3_storage_integration.md`](docs/s3_storage_integration.md) | AWS S3 file storage |
| [`smtp_email_system.md`](docs/smtp_email_system.md) | Transactional email system |
| [`jwt_auth.md`](docs/jwt_auth.md) | JWT authentication flow |
| [`rbac.md`](docs/rbac.md) | Role-based access control |
| [`endpoints_full_flow.md`](docs/endpoints_full_flow.md) | Full endpoint reference and request flows |
