# Transactions API

An asynchronous transaction webhook service built with FastAPI, SQLAlchemy,
PostgreSQL, Pydantic, Uvicorn, and `asyncio`.

The service accepts a transaction immediately, persists it as `PROCESSING`, and
returns `202 Accepted`. A background task then performs five external API calls
over at least 30 seconds and stores the final status as either `PROCESSED` or
`FAILED`. Transaction IDs are primary keys, so repeated webhook deliveries are
idempotent and return the current persisted status without starting another job.

## Run with Docker Compose

Docker Compose is the recommended way to run the assessment because it starts
both the API and PostgreSQL with matching configuration.

### Prerequisites

- Docker Desktop or Docker Engine with Compose support
- Ports `8000` and `5432` available

### Start the service

From the `Server` directory:

```bash
docker compose up --build
```

On installations that use the standalone Compose command:

```bash
docker-compose up --build
```

Compose waits for PostgreSQL to become healthy before starting the API. Once
startup completes, use:

- API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>
- OpenAPI document: <http://localhost:8000/openapi.json>

Run in the background with `docker compose up --build -d` and inspect logs with
`docker compose logs -f api`.

When source code changes, rebuild and recreate the API container so Docker does
not continue serving an older image:

```bash
docker compose up --build -d --force-recreate api
```

Do not run a local `uvicorn` process on port `8000` at the same time as the
Compose API. Check the active Compose services with `docker compose ps`.

### Stop the service

```bash
docker compose down
```

PostgreSQL data remains in the named `postgres_data` volume. To intentionally
delete all stored transactions and recreate the database from scratch, use:

```bash
docker compose down -v
```

The `-v` form is destructive and should only be used when the stored data is no
longer needed.

## Test the API

### Health check

```bash
curl http://localhost:8000/
```

Example response:

```json
{
  "status": "HEALTHY",
  "current_time": "2024-01-15T10:30:00Z"
}
```

### Submit a transaction

The webhook must be called with `POST`. Opening its URL directly in a browser
sends `GET` and therefore returns `405 Method Not Allowed`.

```bash
curl -i -X POST http://localhost:8000/v1/webhooks/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "txn_abc123def456",
    "source_account": "acc_user_789",
    "destination_account": "acc_merchant_456",
    "amount": 1500,
    "currency": "INR"
  }'
```

The response has status `202 Accepted`:

```json
{
  "transaction_id": "txn_abc123def456",
  "status": "PROCESSING",
  "already_exists": false,
  "message": "Transaction accepted for processing"
}
```

Submitting the same `transaction_id` again does not create or process another
transaction. It returns `already_exists: true` together with the row's current
status, including `PROCESSED` or `FAILED` when background processing has ended.

### Retrieve a transaction

```bash
curl http://localhost:8000/v1/transactions/txn_abc123def456
```

While work is running, `status` is `PROCESSING` and `processed_at` is `null`.
After approximately 30 seconds, the response contains the persisted final state:

```json
{
  "transaction_id": "txn_abc123def456",
  "source_account": "acc_user_789",
  "destination_account": "acc_merchant_456",
  "amount": 1500.0,
  "currency": "INR",
  "status": "PROCESSED",
  "created_at": "2024-01-15T10:30:00Z",
  "processed_at": "2024-01-15T10:30:30Z"
}
```

An unknown transaction ID returns `404 Not Found`.

## Run the automated tests

The Docker image contains runtime dependencies only. Install the development
extras locally to run tests and lint checks:

```bash
python -m venv .venv
```

Activate the environment on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Activate it on Linux or macOS:

```bash
source .venv/bin/activate
```

Then run:

```bash
pip install -e ".[dev]"
pytest -q
ruff check app tests
```

The endpoint and worker tests mock external I/O, so they do not take 30 seconds
and do not require a running PostgreSQL server.

## Optional local development

Docker Compose is preferred, but the API can run directly when PostgreSQL is
already available:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Configuration is loaded from `.env` or environment variables prefixed with
`TRANSACTIONS_`. Copy `.env.example` to `.env` as a starting point. If a database
password contains reserved URL characters such as `@`, the configuration layer
encodes them before SQLAlchemy creates the connection.


## Technical choices

- **FastAPI** provides async request handling, dependency injection, validation
  integration, automatic OpenAPI generation, and the Swagger UI used to test
  the endpoints.
- **Uvicorn** is a lightweight ASGI server designed to run asynchronous FastAPI
  applications efficiently.
- **Pydantic** defines and validates the webhook and response contracts. It
  rejects malformed identifiers, unsupported currencies, non-positive amounts,
  excessive decimal precision, unknown fields, and identical source and
  destination accounts before business logic runs.
- **SQLAlchemy 2 async ORM** provides typed models and non-blocking database
  access while keeping persistence logic separate from HTTP routing.
- **PostgreSQL** provides durable storage, native enums, fixed-precision numeric
  amounts, constraints, and atomic conflict handling. `transaction_id` is the
  primary key, and `INSERT ... ON CONFLICT DO NOTHING` enforces idempotency even
  for concurrent webhook requests.
- **asyncpg** is the asynchronous PostgreSQL driver used by SQLAlchemy. It keeps
  database operations from blocking the event loop.
- **asyncio** schedules transaction processing with `asyncio.create_task()`, so
  external work does not delay the webhook response. Strong task references are
  retained, tasks are cancelled cleanly during shutdown, and unfinished
  `PROCESSING` rows are rescheduled when the application starts again.
- **HTTPX** provides the asynchronous HTTP client used for the five calls to
  JSONPlaceholder. Non-success responses and transport errors mark the final
  transaction as `FAILED`.
- **Docker Compose** makes the API and PostgreSQL environment reproducible and
  includes database health gating plus a persistent named volume.
- **Pytest and Ruff** provide automated behavior checks and consistent static
  code quality verification.

## Project structure

```text
app/
  api/          HTTP routers and endpoint handlers
  core/         configuration and logging
  db/           SQLAlchemy engine, sessions, and database initialization
  models/       persistent SQLAlchemy models and enums
  schemas/      Pydantic request and response models
  services/     idempotency and background-processing logic
tests/          endpoint and worker tests
Dockerfile      API container image
docker-compose.yml
```
