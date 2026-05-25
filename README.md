# yuno-assessment

Implementation repo for [yuno](../) — a visual platform for non-technical operators to build multi-agent workflows and reach users via messaging channels.

This repo is the **code** that the specs at `../yuno/` describe. Both repos evolve batch by batch — see [`../yuno/3-how/specs/01-user-stories/README.md`](../3-how/specs/01-user-stories/README.md) for the batch roadmap and [`../yuno/3-how/specs/03-architecture/README.md`](../3-how/specs/03-architecture/README.md) for the canonical architecture index.

## Status

**Batch 0 — scaffold.** Empty FastAPI + Vite skeletons, Postgres container, and 5 CrewAI capability spikes that gate downstream batch designs.

## Stack

- **Backend**: Python 3.12 · FastAPI · SQLModel · Alembic · CrewAI · in-process asyncio event bus (per [ADR-001](../3-how/adr/001-backend-typescript-frontend-react.md), [ADR-002](../3-how/adr/002-postgres-sqlmodel.md), [ADR-003](../3-how/adr/003-crewai-runtime.md), [ADR-004](../3-how/adr/004-in-process-event-bus.md))
- **Frontend**: Node 22 · Vite · React · Mantine v7 · React Flow (per [ADR-006](../3-how/adr/006-vite-react-flow.md))
- **LLM**: Gemini `gemini-2.0-flash` via LiteLLM (per [ADR-007](../3-how/adr/007-gemini-llm-provider.md))
- **Package managers**: `uv` (backend), `pnpm` (frontend)

## Quick start

```bash
cp .env.example .env
# Edit .env and add GEMINI_API_KEY (https://aistudio.google.com/apikey)

docker compose up --build
```

When it's up:

- Backend health: `curl http://localhost:8000/health` → `{"status":"ok"}`
- Frontend splash: open `http://localhost:5173`
- Database: Postgres on `localhost:5432` (user/password `yuno`/`yuno`, DB `yuno`)

## Layout

```
yuno/implementation/
├── backend/                 FastAPI app + spikes
│   ├── app/                 application code (app factory, db, event bus, runtime)
│   ├── alembic/             migrations
│   ├── spikes/              CrewAI capability tests (batch 0)
│   ├── tests/               pytest harness (PG + rollback, mock_llm, bus_events)
│   ├── pyproject.toml       uv project file
│   └── Dockerfile
├── frontend/                Vite + React + Mantine + React Flow
│   ├── src/                 src + src/__tests__ for Vitest
│   ├── package.json
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   └── Dockerfile
├── docker-compose.yml
└── .env.example
```

## CrewAI capability spikes (Batch 0)

Each script verifies one CrewAI capability that a later batch's design depends on. See [`../3-how/specs/03-architecture/batches/0-scaffold/README.md`](../3-how/specs/03-architecture/batches/0-scaffold/README.md) for context.

```bash
# All five
docker compose run --rm backend uv run python spikes/run_all.py

# Or one at a time (filenames start with digits, so use the script path, not -m)
docker compose run --rm backend uv run python spikes/01_llm_tokens.py
```

Each prints `PASS` or `FAIL: <reason>`; `run_all` exits non-zero if any failed.

## Tests

### Backend (pytest)

```bash
# All tests (needs Postgres up — `docker compose up -d postgres` first)
docker compose run --rm backend uv run pytest

# One file
docker compose run --rm backend uv run pytest tests/test_smoke.py -v
```

Fixtures provided by [`backend/tests/conftest.py`](backend/tests/conftest.py):

- `client` — FastAPI `TestClient` with the DB session overridden to share the test's transaction
- `db_session` — SQLModel session inside a connection-level transaction (rolled back at teardown; auto-creates the `yuno_test` database)
- `mock_llm` — monkeypatches `litellm.completion`; CrewAI's Agent/Task/Crew orchestration still runs real
- `bus_events` — captures every event published on the in-process bus

### Frontend (Vitest)

```bash
pnpm test:run            # CI mode (exits)
pnpm test                # watch mode
pnpm test:ui             # open the Vitest UI
```

## Development workflows

Run services individually outside Docker for hot reload + faster iteration:

```bash
# Backend
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
pnpm install
pnpm dev
```

Postgres is still easiest in Docker:

```bash
docker compose up postgres -d
```

### Intel Mac note

CrewAI transitively depends on `lancedb`, which doesn't ship wheels for macOS x86_64 (Intel) — only Apple Silicon and Linux. Local `uv sync` on Intel Macs will therefore fail. Use Docker for backend dev on Intel hardware; the container is Linux x86_64 and installs cleanly. Apple Silicon (arm64) Macs are unaffected.
