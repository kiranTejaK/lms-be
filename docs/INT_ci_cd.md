# Continuous Integration & Deployment (CI/CD)

## 1. Concept Overview

**What it is:** CI/CD is an automated pipeline that runs whenever code is pushed to a repository. Continuous Integration (CI) automatically lints and tests the code to catch bugs early. Continuous Deployment/Delivery (CD) automates the process of building artifacts (like Docker images) and deploying them to production.

**Why it is used:** It eliminates the "works on my machine" problem by running tests in a sterile environment. It prevents broken code from being merged, enforces coding standards automatically, and makes the release process consistent and repeatable.

---

## 2. Project Setup

The project uses **GitHub Actions** for its CI/CD pipeline. The pipeline is defined in `.github/workflows/ci.yml` and is triggered on pushes to `main` and `develop` branches, as well as on any Pull Requests targeting `main`.

### Initialization & Triggers
```yaml
name: CI Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  PYTHON_VERSION: "3.12"
```
**Explanation:** 
*   **Triggers (`on`):** Ensures that all active development branches (`develop`, `main`) and incoming PRs are automatically verified.
*   **Global Environment (`env`):** Defines the Python version globally. If the project upgrades to Python 3.13, you only have to change it in one place instead of across multiple pipeline jobs.

---

## 3. Key Code Walkthrough

The pipeline is split into three distinct sequential jobs: **Lint**, **Test**, and **Docker Build**.

### Job 1: Linting (Fast Fail)
```yaml
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install ruff
      - name: Run Ruff linter
        run: ruff check app/ tests/
```
*Logic Flow:*
This is the first job because linting is fast. We use `ruff` to check for syntax and style errors. If this fails, the pipeline stops immediately, saving compute time and providing rapid feedback to the developer.

### Job 2: Testing (Isolated Environment)
```yaml
  test:
    name: Test
    runs-on: ubuntu-latest
    needs: lint  # Sequential dependency

    env:
      DB_HOST: localhost
      ENVIRONMENT: testing
      # ... other environment variables ...

    steps:
      - uses: actions/checkout@v4
      # ... setup python ...
      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Run tests with coverage
        run: pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=50
```
*Logic Flow:*
*   **Sequential Execution:** The `needs: lint` directive guarantees tests only run if the code passes the style check.
*   **Isolated Config (`env`):** We inject mock environment variables directly into the job. By setting `ENVIRONMENT: testing`, the application knows to use an in-memory SQLite database instead of trying to connect to a real PostgreSQL instance.
*   **Coverage Threshold:** `--cov-fail-under=50` ensures that the pipeline will fail if the test coverage drops below 50%, enforcing a minimum quality standard.

### Job 3: Docker Build (Conditional Delivery)
```yaml
  docker:
    name: Docker Build
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build -t lms-be:latest .
```
*Logic Flow:*
*   **Conditional Execution:** The `if: github.ref == 'refs/heads/main'` ensures that we only build the Docker image for production when code is merged into the `main` branch. It prevents wasting time building images for every minor PR or development push.

---

## 4. End-to-End Flow

**Request Lifecycle in the Pipeline:**
1.  **Code Push:** A developer pushes a commit to a PR branch targeting `main`.
2.  **Linting Phase:** GitHub Actions spins up an Ubuntu runner, checks out the code, installs `ruff`, and lints the code. 
3.  **Testing Phase:** If linting passes, a new runner starts. It sets testing-specific environment variables, installs the full application along with `pytest`, and runs the test suite. It checks that code coverage is above 50%.
4.  **Build Phase:** If tests pass, the pipeline evaluates the `if` condition. Since this is a PR (not the `main` branch), the Docker build job is skipped. 
5.  **Merge & Deliver:** Once the PR is merged into `main`, the pipeline runs again. This time, the `if` condition passes, the Docker image is built, and it is ready to be pushed to a container registry (like Docker Hub or AWS ECR) for deployment.

---

## 5. Design Decisions

*   **Job Separation:** Splitting Lint, Test, and Build into separate jobs rather than one giant script.
    *   *Benefit:* It makes debugging much easier (you know exactly which phase failed) and allows for parallel execution if desired in the future.
*   **Fail-Fast Strategy (`needs` keyword):** 
    *   *Benefit:* By making tests wait for linting, and builds wait for tests, we save CI compute minutes and prevent broken artifacts from being built.
*   **Strict Test Coverage Gates:** 
    *   *Benefit:* Prevents developers from merging new features without adding corresponding tests, maintaining project health over time.

---

## 6. Alternatives & Trade-offs

| Approach | Pros | Cons | When to choose |
| :--- | :--- | :--- | :--- |
| **GitHub Actions (Current)** | Deep integration with GitHub repos, massive marketplace of pre-built actions. | Tightly coupled to GitHub. | When your codebase is hosted on GitHub and you want a unified experience. |
| **GitLab CI/CD** | Excellent built-in container registry and Kubernetes integration. | Requires migrating code to GitLab. | Enterprise environments where you need strict self-hosted runners and built-in registries. |
| **Jenkins** | Highly customizable, completely free, runs on your own hardware. | High maintenance overhead; requires managing your own server, plugins, and security. | Legacy enterprise systems or when you need highly complex, custom hardware integrations. |

---

## 7. Interview Questions & Answers

**Q1: Why do we separate Linting and Testing into different jobs instead of putting them in one script?**
*Answer:* Separation of concerns. It provides a "fail-fast" mechanism. Linting takes seconds, while testing can take minutes. If there's a syntax error, the pipeline fails immediately at the Lint job, saving CI compute time and giving the developer faster feedback without waiting for the entire test suite to setup and fail.

**Q2: How does the pipeline know not to deploy code from a feature branch?**
*Answer:* In the Docker Build job, we use the conditional statement `if: github.ref == 'refs/heads/main'`. This ensures that the build (and subsequent deployment) phase is only triggered when code is officially merged into the `main` production branch.

**Q3: What happens if a developer writes new code but forgets to write tests for it?**
*Answer:* The pipeline will fail. In our `pytest` command, we included the flag `--cov-fail-under=50`. If the new untested code drops the overall project test coverage below 50%, the Test job will exit with an error, and the PR cannot be merged.

**Q4: How does the application connect to the database during the CI testing phase?**
*Answer:* We don't connect to a real database in CI to keep tests fast and deterministic. We inject `ENVIRONMENT: testing` via the `env` block in the test job. The application configuration is programmed to recognize this environment and fallback to a local, in-memory SQLite database instead of Postgres.

---

## 8. Bonus Insights

*   **Performance Insight - Dependency Caching:** Currently, `pip install` downloads packages from the internet every time the pipeline runs. A great optimization is using `actions/setup-python` with `cache: 'pip'`. This caches the downloaded dependencies across runs, significantly speeding up the pipeline execution time.
*   **Common Mistake - Artifact Uploads:** Building a Docker image in CI is great, but if it isn't pushed to a registry (like Docker Hub, GitHub Container Registry, or AWS ECR), the image is destroyed as soon as the runner stops. A complete CD pipeline requires a `docker push` step after the `docker build`.
*   **Security Insight:** Never hardcode secrets (like AWS keys or production database passwords) in the `ci.yml`. Always use GitHub Secrets (e.g., `${{ secrets.PROD_DB_PASSWORD }}`) to inject sensitive variables into the runner environment.
