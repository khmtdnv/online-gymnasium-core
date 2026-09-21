# Document Generation Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python 3.13 document service that asynchronously produces a
certificate PDF through Celery/RabbitMQ, stores it in private MinIO, and lets a
client query and download the completed document.

**Architecture:** A synchronous FastAPI API persists a durable document job and
Celery-delivery outbox row in one PostgreSQL transaction. A dispatcher sends
the job ID to Celery, and a worker renders a certificate, uploads the stable
object key to MinIO, then records the terminal job state.

**Tech Stack:** Python 3.13, FastAPI, Uvicorn, SQLAlchemy, psycopg, Alembic,
Celery, RabbitMQ, MinIO, Jinja2, WeasyPrint, Pytest, Ruff, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-21-document-generation-service-design.md`

## Global Constraints

- Create `services/documents` as an independent Poetry project with
  `requires-python = ">=3.13,<3.14"` and Ruff target `py313`, line length 88.
- Use `python:3.13-slim`; install the Debian Pango libraries needed by
  WeasyPrint in the image.
- Use synchronous SQLAlchemy and `psycopg` throughout this service; FastAPI
  route functions are ordinary `def` functions.
- Keep one private MinIO bucket named `documents`; object keys are always
  `certificates/{job_id}.pdf`.
- Do not add authentication, student-service calls, public/presigned URLs, or
  types other than `certificate`.
- The Celery message contains only the document UUID. Job payload remains in
  PostgreSQL.
- A job plus its outbox row must be inserted in one database transaction.
- At-least-once Celery delivery is expected; repeat worker execution must not
  create a second object key or regress a completed job.

## Review Focus

- Broker unavailable after the job transaction: the outbox remains unpublished
  and dispatcher retry eventually sends the same job ID.
- Dispatcher crashes after publish but before `published_at`: worker may get a
  duplicate task, which remains safe.
- Worker crashes after MinIO upload but before database completion: retry
  repairs the same job and same object key.
- `GET /documents/{id}/content` before completion returns `409`, never a
  partial file or a MinIO public URL.
- A non-retryable rendering failure becomes `failed`; a temporary MinIO error
  retries with bounded Celery retries and ultimately becomes `failed`.

## File structure

```text
services/documents/
  Dockerfile
  .dockerignore
  .env.example
  pyproject.toml
  alembic.ini
  migrations/
  src/document_service/
    api/{health.py,documents.py,dependencies.py,router.py}
    application/{create_certificate.py,dispatch_jobs.py,generate_certificate.py,errors.py}
    domain/{document.py,certificate.py}
    infrastructure/{database.py,repositories.py,celery_app.py,minio_storage.py,renderer.py}
    infrastructure/models/{base.py,document_job.py,document_task_outbox.py}
    workers/{dispatcher.py,tasks.py}
    app.py
    config.py
    main.py
  templates/certificate.html
  tests/
```

### Task 1: Bootstrap the document service and its database schema

**Files:**
- Create: `services/documents/pyproject.toml`, `poetry.lock`, `.dockerignore`,
  `.env.example`, `Dockerfile`, `alembic.ini`, `migrations/env.py`,
  `migrations/script.py.mako`
- Create: `services/documents/src/document_service/config.py`,
  `infrastructure/database.py`, `infrastructure/models/base.py`,
  `infrastructure/models/document_job.py`,
  `infrastructure/models/document_task_outbox.py`
- Create: `services/documents/migrations/versions/<revision>_create_document_jobs.py`
- Create: `services/documents/tests/test_config.py`, `tests/test_models.py`
- Modify: `compose.yaml`

**Interfaces:**
- Produces `DocumentSettings`, `create_engine(url)`, `SessionFactory`,
  `DocumentJobRow`, and `DocumentTaskOutboxRow` for all following tasks.
- Produces `documents-postgres`, `rabbitmq`, `minio`, and `minio-init` Compose
  services for later API, dispatcher, and worker services.

- [ ] **Step 1: Write configuration and model tests first**

```python
def test_settings_read_document_urls_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DOCUMENT_DATABASE_URL", "postgresql+psycopg://u:p@db/documents")
    monkeypatch.setenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//")
    monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
    settings = DocumentSettings()
    assert settings.document_database_url.endswith("/documents")
    assert settings.minio_bucket == "documents"


def test_document_models_expose_expected_table_names() -> None:
    assert DocumentJobRow.__tablename__ == "document_jobs"
    assert DocumentTaskOutboxRow.__tablename__ == "document_task_outbox"
```

- [ ] **Step 2: Run RED**

Run: `poetry -C services/documents run pytest tests/test_config.py tests/test_models.py -q`
Expected: import failure because the project and models do not exist.

- [ ] **Step 3: Create project, configuration, synchronous database factory, and ORM rows**

Use dependencies: `fastapi`, `uvicorn[standard]`, `pydantic-settings`,
`sqlalchemy`, `psycopg[binary]`, `alembic`, `celery[amqp]`, `minio`,
`jinja2`, `weasyprint`; dev: `pytest`, `httpx`, `ruff`.

Define the ORM rows with UUID primary keys, JSONB payload, nullable object and
error fields, server-side timestamps, one-to-one `document_job_id` outbox
foreign key, and the fixed task name `documents.generate_certificate`.

Create an Alembic revision explicitly creating both tables, constraints, and
indexes. Import both ORM rows in `migrations/env.py` before `target_metadata`.

Create Compose infrastructure only: `documents-postgres`, `rabbitmq`, `minio`,
and idempotent `minio-init` that creates `documents` with `mc mb --ignore-existing`.
Use persistent `documents_postgres_data` and `minio_data` volumes; do not expose
PostgreSQL publicly.

- [ ] **Step 4: Run GREEN and schema checks**

Run:

```bash
poetry -C services/documents lock
poetry -C services/documents install
poetry -C services/documents run pytest tests/test_config.py tests/test_models.py -q
poetry -C services/documents run ruff check .
poetry -C services/documents run ruff format --check .
docker compose config --quiet
docker compose up -d documents-postgres rabbitmq minio minio-init
```

Expected: tests and Ruff pass; all long-running dependencies are healthy and
`minio-init` exits 0.

- [ ] **Step 5: Commit**

```bash
git add services/documents compose.yaml
git commit -m "feat: add document service infrastructure"
```

### Task 2: Persist certificate jobs and the transactional outbox

**Files:**
- Create: `services/documents/src/document_service/domain/document.py`,
  `domain/certificate.py`, `application/create_certificate.py`,
  `infrastructure/repositories.py`
- Create: `services/documents/tests/test_create_certificate.py`,
  `tests/test_document_repositories.py`

**Interfaces:**
- Consumes `DocumentJobRow`, `DocumentTaskOutboxRow`, and `DocumentStatus`.
- Produces `CreateCertificateCommand`, `CreateCertificateHandler`,
  `DocumentJob`, and `SqlAlchemyDocumentRepository`.

- [ ] **Step 1: Write failing handler tests**

```python
def test_create_certificate_stores_pending_job_and_outbox() -> None:
    result = CreateCertificateHandler(fake_repository).handle(
        CreateCertificateCommand(
            student_full_name="Иван Петров",
            class_name="7А",
            academic_year="2026/2027",
        )
    )
    assert result.status is DocumentStatus.PENDING
    assert fake_repository.jobs[0].payload["class_name"] == "7А"
    assert fake_repository.outbox[0].document_job_id == result.id


def test_create_certificate_rejects_blank_student_name() -> None:
    with pytest.raises(InvalidCertificateData):
        CertificateData(" ", "7А", "2026/2027")
```

- [ ] **Step 2: Run RED**

Run: `poetry -C services/documents run pytest tests/test_create_certificate.py -q`
Expected: import failure for the application/domain modules.

- [ ] **Step 3: Implement the smallest domain and repository contract**

`CertificateData` validates non-blank strings. `CreateCertificateHandler` opens
one SQLAlchemy transaction and calls repository `create_job_with_outbox(data)`.
The repository creates one `document_jobs` row with `pending`, a payload
snapshot, and one `document_task_outbox` row before transaction commit.

Expose only these domain values to the API:

```python
@dataclass(frozen=True, slots=True)
class DocumentJob:
    id: UUID
    document_type: str
    status: DocumentStatus
    object_key: str | None
    error_message: str | None
    created_at: datetime
```

- [ ] **Step 4: Add failing repository transaction test and make it pass**

Test that a real session commit yields exactly one job and exactly one matching
outbox row. Test a duplicate `document_job_id` outbox insertion fails the unique
constraint. Use a PostgreSQL test database or focused SQLAlchemy statement tests;
do not use SQLite because JSONB and PostgreSQL UUID constraints are part of the
contract.

- [ ] **Step 5: Run focused suite and commit**

```bash
poetry -C services/documents run pytest tests/test_create_certificate.py tests/test_document_repositories.py -q
poetry -C services/documents run ruff check .
poetry -C services/documents run ruff format --check .
git add services/documents
git commit -m "feat: create certificate jobs with outbox"
```

### Task 3: Add HTTP creation, status, content state semantics, and health

**Files:**
- Create: `services/documents/src/document_service/api/health.py`,
  `api/documents.py`, `api/dependencies.py`, `api/router.py`, `app.py`, `main.py`
- Modify: `services/documents/src/document_service/infrastructure/repositories.py`
- Create: `services/documents/tests/test_documents_api.py`, `tests/test_app.py`

**Interfaces:**
- Consumes `CreateCertificateHandler` and repository `get_job(job_id)`.
- Produces `POST /documents/certificates`, `GET /documents/{job_id}`,
  `GET /documents/{job_id}/content`, and `GET /health/live`.

- [ ] **Step 1: Write API RED tests using a fake repository**

```python
def test_post_certificate_returns_pending_job() -> None:
    response = client.post(
        "/documents/certificates",
        json={
            "student_full_name": "Иван Петров",
            "class_name": "7А",
            "academic_year": "2026/2027",
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "pending"


def test_content_returns_409_for_pending_job() -> None:
    response = client.get(f"/documents/{pending_job.id}/content")
    assert response.status_code == 409
    assert response.json() == {"detail": "Document is not ready"}
```

Also pin `404` for an unknown job and status response containing `download_url`
only for a completed job.

- [ ] **Step 2: Run RED**

Run: `poetry -C services/documents run pytest tests/test_documents_api.py tests/test_app.py -q`
Expected: module/route collection failure.

- [ ] **Step 3: Implement API composition and route behavior**

`create_app(settings, session_factory, storage)` stores dependencies in app
state. Keep FastAPI routes as synchronous `def`. `POST` maps domain validation
to `422`; it returns a response model with `202`. `GET` maps absent jobs to
the exact `404` detail. Content route rejects `pending`/`processing` and
`failed` with the two exact `409` details from the spec; completed download
calls a storage port and returns `StreamingResponse(..., media_type="application/pdf")`.

- [ ] **Step 4: Run GREEN**

```bash
poetry -C services/documents run pytest tests/test_documents_api.py tests/test_app.py -q
poetry -C services/documents run ruff check .
poetry -C services/documents run ruff format --check .
```

- [ ] **Step 5: Commit**

```bash
git add services/documents
git commit -m "feat: add document job API"
```

### Task 4: Render certificates and store one stable MinIO object

**Files:**
- Create: `services/documents/templates/certificate.html`,
  `src/document_service/infrastructure/renderer.py`,
  `infrastructure/minio_storage.py`, `application/generate_certificate.py`,
  `workers/tasks.py`, `infrastructure/celery_app.py`
- Modify: `services/documents/src/document_service/infrastructure/repositories.py`
- Create: `services/documents/tests/test_renderer.py`, `tests/test_generate_certificate.py`,
  `tests/test_minio_storage.py`

**Interfaces:**
- Consumes `DocumentJob` and a `CertificateRenderer.render(payload) -> bytes`;
  consumes `DocumentStorage.put_pdf(key, pdf_bytes)` and `get_pdf(key)`.
- Produces Celery task `documents.generate_certificate(job_id: str) -> None`.

- [ ] **Step 1: Write renderer and worker RED tests**

```python
def test_renderer_returns_pdf_bytes_for_valid_certificate() -> None:
    pdf = CertificateRenderer(template_dir).render(certificate_payload)
    assert pdf.startswith(b"%PDF-")


def test_repeat_delivery_of_completed_job_does_not_upload_again() -> None:
    handler.handle(completed_job.id)
    storage.put_pdf.assert_not_called()


def test_worker_uploads_stable_object_key_before_completion() -> None:
    handler.handle(pending_job.id)
    storage.put_pdf.assert_called_once_with(f"certificates/{pending_job.id}.pdf", ANY)
    assert repository.saved.status is DocumentStatus.COMPLETED
```

- [ ] **Step 2: Run RED**

Run: `poetry -C services/documents run pytest tests/test_renderer.py tests/test_generate_certificate.py tests/test_minio_storage.py -q`
Expected: imports fail because renderer, storage, and task do not exist.

- [ ] **Step 3: Implement renderer, storage adapter, and idempotent worker handler**

Render only the application-owned Jinja2 template and pass its HTML to
`weasyprint.HTML(string=html).write_pdf()`. `MinioDocumentStorage` ensures the
`documents` bucket exists only through `minio-init`; it uploads PDF bytes under
the supplied key and returns a binary stream for downloads.

Worker behavior:

```python
if job.status is DocumentStatus.COMPLETED:
    return
repository.mark_processing(job.id)
pdf_bytes = renderer.render(job.payload)
storage.put_pdf(f"certificates/{job.id}.pdf", pdf_bytes)
repository.mark_completed(job.id, f"certificates/{job.id}.pdf")
```

Configure Celery retries only around a dedicated `TemporaryStorageError`, with
three attempts and exponential backoff. Catch permanent template/data errors,
call `mark_failed(job.id, "Document generation failed")`, then return without
retry.

- [ ] **Step 4: Run GREEN and inspect an actual PDF**

```bash
poetry -C services/documents run pytest tests/test_renderer.py tests/test_generate_certificate.py tests/test_minio_storage.py -q
poetry -C services/documents run ruff check .
poetry -C services/documents run ruff format --check .
```

Use a test fixture or temporary directory to assert produced bytes begin with
`%PDF-`; do not hard-code full binary output.

- [ ] **Step 5: Commit**

```bash
git add services/documents
git commit -m "feat: generate and store certificate PDFs"
```

### Task 5: Publish document outbox rows through Celery

**Files:**
- Create: `services/documents/src/document_service/application/dispatch_jobs.py`,
  `workers/dispatcher.py`
- Modify: `services/documents/src/document_service/infrastructure/repositories.py`,
  `infrastructure/celery_app.py`
- Create: `services/documents/tests/test_dispatch_jobs.py`, `tests/test_dispatcher_worker.py`

**Interfaces:**
- Consumes repository `get_pending_outbox(limit: int)` and
  `mark_outbox_published(outbox_id: UUID)`.
- Produces `DocumentDispatcher.run_once() -> int` and publishes
  `documents.generate_certificate` with the string UUID job ID.

- [ ] **Step 1: Write RED tests for successful publish and publish failure**

```python
def test_dispatcher_marks_outbox_after_celery_accepts_task() -> None:
    published = dispatcher.run_once()
    assert published == 1
    celery.send_task.assert_called_once_with(
        "documents.generate_certificate", args=[str(outbox.document_job_id)]
    )
    repository.mark_outbox_published.assert_called_once_with(outbox.id)


def test_dispatcher_leaves_outbox_pending_when_celery_publish_fails() -> None:
    celery.send_task.side_effect = OSError("broker unavailable")
    with pytest.raises(OSError):
        dispatcher.run_once()
    repository.mark_outbox_published.assert_not_called()
```

- [ ] **Step 2: Run RED**

Run: `poetry -C services/documents run pytest tests/test_dispatch_jobs.py tests/test_dispatcher_worker.py -q`
Expected: import failure for dispatcher modules.

- [ ] **Step 3: Implement bounded dispatcher polling**

`run_once()` obtains pending rows ordered by creation, invokes
`celery_app.send_task(row.task_name, args=[str(row.document_job_id)])`, then
marks exactly that row published in a new transaction. The process loops with
a one-second sleep only when no row was published. Log a publish exception and
retry on the next loop; do not mark failed publication as delivered.

- [ ] **Step 4: Run GREEN and regression checks**

```bash
poetry -C services/documents run pytest tests/test_dispatch_jobs.py tests/test_dispatcher_worker.py -q
poetry -C services/documents run pytest -q
poetry -C services/documents run ruff check .
poetry -C services/documents run ruff format --check .
```

- [ ] **Step 5: Commit**

```bash
git add services/documents
git commit -m "feat: dispatch document jobs through Celery"
```

### Task 6: Containerize all service processes and prove the full workflow

**Files:**
- Modify: `services/documents/Dockerfile`, `.dockerignore`, `.env.example`,
  `compose.yaml`
- Create: `services/documents/tests/test_compose_config.py`
- Modify: `services/documents/tests/test_documents_api.py`

**Interfaces:**
- Consumes the API, dispatcher, worker, migrations, PostgreSQL, RabbitMQ, and
  MinIO components from Tasks 1–5.
- Produces runnable `document-api`, `document-dispatcher`, `document-worker`,
  and `document-migrations` Compose services.

- [ ] **Step 1: Write configuration RED tests**

```python
def test_docker_image_uses_python_313_and_installs_pango_runtime() -> None:
    dockerfile = Path("Dockerfile").read_text()
    assert "FROM python:3.13-slim" in dockerfile
    assert "libpango-1.0-0" in dockerfile


def test_compose_declares_api_worker_dispatcher_and_migrations() -> None:
    compose = Path("../../compose.yaml").read_text()
    for service in (
        "document-api:",
        "document-worker:",
        "document-dispatcher:",
        "document-migrations:",
    ):
        assert service in compose
```

- [ ] **Step 2: Run RED**

Run: `poetry -C services/documents run pytest tests/test_compose_config.py -q`
Expected: fail until all document Compose services and image setup exist.

- [ ] **Step 3: Complete Compose topology**

Build all document processes from `services/documents`. Use an entry command
for migrations that runs `alembic upgrade head`; make API, dispatcher, and
worker depend on its successful completion. Give API host port `8002` and a
`/health/live` healthcheck. Worker and dispatcher use `restart: unless-stopped`.
Pass only service-specific environment values; credentials remain in ignored
local env files.

- [ ] **Step 4: Run automated checks**

```bash
poetry -C services/documents run pytest -q
poetry -C services/documents run ruff check .
poetry -C services/documents run ruff format --check .
docker compose config --quiet
git diff --check
```

- [ ] **Step 5: Run live end-to-end proof**

```bash
docker compose up --build -d document-api document-dispatcher document-worker
curl -i -X POST http://127.0.0.1:8002/documents/certificates \
  -H 'content-type: application/json' \
  -d '{"student_full_name":"Иван Петров","class_name":"7А","academic_year":"2026/2027"}'
```

Poll `GET /documents/{id}` until `completed`; then download
`GET /documents/{id}/content` and assert the response begins with `%PDF-`.
Use `mc ls` in `minio-init` or `minio` to verify the private object key
`documents/certificates/{id}.pdf` exists. Also inspect `document_task_outbox`
to confirm its row has `published_at` set.

- [ ] **Step 6: Commit**

```bash
git add services/documents compose.yaml
git commit -m "feat: run document generation service"
```

## Plan self-review

- Spec coverage: Tasks 1–2 implement separate PostgreSQL, job/outbox schema,
  rendering snapshots, and atomic creation. Task 3 implements the complete
  HTTP contract. Task 4 implements private PDF rendering/storage and worker
  idempotency. Task 5 implements retryable broker publication. Task 6 creates
  all Compose processes and performs the live proof.
- Type consistency: API, dispatcher, and worker share UUID job IDs; the Celery
  boundary transports `str(job_id)` only; MinIO key construction is identical
  in worker and verification.
- Review focus coverage: dispatcher failure is Task 5; duplicate dispatch and
  crash-after-upload are Task 4; pre-completion download is Task 3; permanent
  versus temporary generation failures are Task 4.
- Placeholder scan: no deferred requirements or unspecified interfaces remain.
