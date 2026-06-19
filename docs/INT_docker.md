# Docker & Docker Compose Setup

## 1. Concept Overview

**What it is:** Docker is a containerization platform that packages applications and their dependencies into standardized units (containers). Docker Compose is an orchestration tool used to define and run multi-container applications locally using a single YAML file.

**Why it is used:** It guarantees consistency across different environments (local, CI/CD, production). By spinning up the application, database, cache, and third-party service mocks in isolated containers, it entirely eliminates the "it works on my machine" problem.

---

## 2. Project Setup

### `Dockerfile` (Multi-stage Build)
```dockerfile
# ── Stage 1: Builder ─────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

# ── Stage 2: Runtime ─────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd --create-home appuser && \
    mkdir -p /app/logs && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
**Explanation:** 
*   **Multi-stage build:** First, it uses a `builder` stage to install system dependencies (`gcc`) and python packages. Then, it copies only the installed libraries (`/install`) into a fresh, clean `Runtime` stage.
*   **Non-root user (`appuser`):** Creates a dedicated user and grants ownership only to the `/app` folder. This is a crucial security practice to prevent the app from having root filesystem access.
*   **Container Healthcheck:** Uses `curl` to poll the `/health` endpoint. This lets container orchestrators know if the FastAPI app has successfully initialized and is ready for traffic.

### `docker-compose.yml` (Core Services & Healthchecks)
```yaml
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password1234
      POSTGRES_DB: prac_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
```
**Explanation:**
*   **Persistent Volumes (`postgres_data`):** Maps the database's internal storage to a Docker volume so data isn't lost when the container is destroyed.
*   **`pg_isready` Healthcheck:** Instead of just checking if the container is "running", it uses Postgres's native utility to verify it is actually ready to accept TCP connections.

---

## 3. Key Code Walkthrough

### Managing Startup Dependencies
The `app` container must wait for its dependencies to boot:
```yaml
  app:
    build:
      context: .
      dockerfile: Dockerfile
    # ...
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
```
*Logic Flow:*
By using `condition: service_healthy`, Docker Compose continuously polls the `healthcheck` defined in the `db` and `redis` blocks. The `app` container will not even attempt to start until those services return a healthy status. This gracefully solves the notorious issue of an app crashing on startup because the database is still initializing.

### Network Resolution & Environment Injection
```yaml
    environment:
      DB_HOST: db
      DB_PORT: 5432
      REDIS_HOST: redis
      REDIS_PORT: 6379
```
*Logic Flow:*
Inside Docker's internal network, containers don't use `localhost` to talk to each other. They use service names as hostnames. The config injects `DB_HOST: db`, allowing the FastAPI SQLAlchemy engine to automatically route traffic to the IP address of the `db` container.

### Comprehensive Local Mocking
```yaml
  mailhog:
    image: mailhog/mailhog:latest
    ports:
      - "1025:1025" # SMTP
      - "8025:8025" # HTTP UI

  moto:
    image: motoserver/moto:latest
    ports:
      - "5000:5000"
```
*Integration:*
The compose file spins up `MailHog` (an SMTP sink for intercepting emails) and `Moto` (a mock AWS S3 server). This means developers can test password reset emails and file uploads locally without needing real AWS credentials or accidentally spamming actual email addresses.

---

## 4. End-to-End Flow

**Application Lifecycle in Docker Compose:**
1.  **Build Phase:** When `docker compose up` is executed, it reads the `Dockerfile`. It builds the python dependencies in the `builder` stage, copies them to the runtime stage, and produces the final `app` image.
2.  **Infrastructure Initialization:** Compose starts the supporting containers: `db`, `redis`, `mailhog`, and `moto`.
3.  **Health Verification:** Compose continuously runs the health check commands (e.g., `pg_isready`) against the infrastructure containers.
4.  **App Startup:** Once `db` and `redis` report "healthy", Compose starts the `app` container.
5.  **Runtime Request:** A user hits `http://localhost:8000`. The request enters the `app` container, queries the `db` container via Docker DNS, and caches results in `redis`.
6.  **Graceful Shutdown:** On `docker compose down`, Compose sends SIGTERM signals, gracefully stopping the web server and the databases in reverse dependency order.

---

## 5. Design Decisions

*   **Alpine & Slim Base Images:** Uses `python:3.12-slim`, `postgres:16-alpine`, and `redis:7-alpine`. 
    *   *Benefit:* Greatly reduces the surface area for security vulnerabilities and speeds up image pull times.
*   **Separation of Build & Runtime (Multi-stage):** 
    *   *Benefit:* Keeps compilers and build tools out of production, minimizing image size and reducing security risks.
*   **Explicit Healthchecks & `depends_on`:** 
    *   *Benefit:* Prevents connection-refused errors and retry-loop hacks by strictly ordering the startup sequence.

---

## 6. Alternatives & Trade-offs

| Approach | Pros | Cons | When to choose |
| :--- | :--- | :--- | :--- |
| **Single-stage Dockerfile** | Simpler to read and write. | Larger final image size; ships build tools to production (security risk). | Quick scripts or apps with pure-Python dependencies (no C-extensions). |
| **Local Bare-Metal Services (No Docker)** | Native speed, no container overhead or networking complexities. | "Works on my machine" issues; conflicting port configurations; messy local OS state. | Developing on a strictly standardized OS setup where every developer uses the same OS. |
| **Kubernetes (Minikube/Kind)** | Matches production K8s orchestration exactly. | Heavy on local CPU/RAM; steep learning curve for developers. | High-complexity microservice architectures that require local cluster testing. |

---

## 7. Interview Questions & Answers

**Q1: Why did you use a multi-stage build in your Dockerfile?**
*Answer:* Multi-stage builds allow us to separate the environment used to compile dependencies (which requires tools like `gcc` and `libpq-dev`) from the final runtime environment. This drastically reduces the final image size and improves security by not shipping compilation tools to the production container.

**Q2: How do you prevent your FastAPI app from crashing if the database takes too long to start up?**
*Answer:* I defined a `healthcheck` in the PostgreSQL service using `pg_isready`. Then, in the FastAPI app service, I configured `depends_on` with `condition: service_healthy`. This explicitly instructs Docker Compose to wait until Postgres is fully ready to accept connections before booting the application container.

**Q3: What is the purpose of the `USER appuser` directive?**
*Answer:* By default, Docker containers run as the root user. Creating and switching to a non-root user (`appuser`) follows the principle of least privilege. If there is a vulnerability in the application, the attacker would not automatically gain root access to the container's file system.

**Q4: How do the containers communicate with each other? For example, how does the app find the database?**
*Answer:* Docker Compose automatically creates a private bridge network for the stack. Containers can resolve each other by the service names defined in the YAML file (like `db` or `redis`). The app connects using the hostname `db`, which Docker's internal DNS resolves to the database container's internal IP.

---

## 8. Bonus Insights

*   **Common Mistake - Volume Mapping:** Forgetting to map volumes for databases (`postgres_data:/var/lib/postgresql/data`). Without this, the database is ephemeral, resulting in total data loss every time the container is recreated.
*   **Common Mistake - Layer Caching:** Putting `COPY . .` *before* `RUN pip install`. Doing this invalidates the Docker cache for the pip installation every single time a line of application code changes, making rebuilds extremely slow. The current `Dockerfile` correctly copies `pyproject.toml` and installs dependencies first.
*   **Performance Insight:** Using a `.dockerignore` file is crucial. It prevents copying massive local directories like `.venv` or `.git` into the Docker build context, which saves memory, speeds up the build, and keeps the image clean.
