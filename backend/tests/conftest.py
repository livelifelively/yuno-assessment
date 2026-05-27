"""
Test harness fixtures for yuno backend.

Strategy:
- DB: real Postgres + transactional rollback per test. A session-scoped fixture
  creates a separate `yuno_test` database, runs SQLModel.metadata.create_all,
  then each test runs inside a connection-level transaction rolled back at teardown.
- LLM: `mock_llm` monkeypatches litellm.completion to return canned ModelResponse
  shapes. CrewAI's orchestration and callback machinery still run real.
- Event bus: `bus_events` monkeypatches bus.publish to record every event for
  assertion.
- FastAPI: `client` wires a TestClient with get_session overridden to the test
  session, so endpoint reads/writes share the test's transaction.

Pytest fixtures 101 (so the rest of this file reads cleanly):
- @pytest.fixture turns a function into a fixture. Tests get it by listing its
  name as a parameter — pytest matches argument name → fixture name.
- scope="session" means "build once per `pytest` invocation". Default is "function"
  (rebuilt per test). "session" is for expensive things like a DB engine.
- autouse=True means "apply to every test even if not requested as a parameter".
- A fixture with `yield` is a setup/teardown pair: code before yield = setup,
  code after yield (typically in finally) = teardown.
- `monkeypatch` is a built-in pytest fixture that replaces attributes safely
  (undoes itself at test end).
"""

# `from __future__ import annotations` defers all type hints to strings (PEP 563).
# Means we can write `list[Run]` etc. on Python 3.12 without runtime cost, and
# forward references just work. Effectively annotation-only.
from __future__ import annotations

# Standard library `os` — used here only to read env vars (os.getenv).
import os
# Iterator[X] is the type for a generator that yields X then stops. Fixtures
# that use `yield` have this return type so type checkers know the shape.
from collections.abc import Iterator
# `Any` = "no type constraint". Used on **kwargs where we don't care about the shape.
from typing import Any
# MagicMock = a callable stand-in for anything. Records calls; you can swap out
# its return value or `side_effect`. We use it to replace litellm.completion.
from unittest.mock import MagicMock

# `litellm` is the unified LLM-client library CrewAI uses under the hood
# (one API for OpenAI / Anthropic / Gemini / …). We patch `litellm.completion`
# (its main call) to fake LLM responses in tests.
import litellm
# `pytest` itself — provides @pytest.fixture, the test runner, monkeypatch, etc.
import pytest
# FastAPI's in-process test client. Calling .get/.post/.put on it dispatches
# directly into the app (no real socket). Returns a Response with .json(), etc.
from fastapi.testclient import TestClient
# The Pydantic models LiteLLM returns from .completion(). We construct them to
# build fake responses for mock_llm:
#   - ModelResponse : the full response (choices, usage, model, …)
#   - Choices       : wraps one completion candidate (index, message, finish_reason)
#   - Message       : { role: "assistant"|"user"|…, content: str }
#   - Usage         : { prompt_tokens, completion_tokens, total_tokens }
from litellm.types.utils import Choices, Message, ModelResponse, Usage
# SQLAlchemy's `create_engine` — builds a DB connection pool object that knows
# how to talk to Postgres. Aliased to sa_create_engine because sqlmodel re-exports
# its own create_engine below (same role, thin wrapper).
from sqlalchemy import create_engine as sa_create_engine
# `text()` wraps a raw SQL string so SQLAlchemy executes it verbatim (rather than
# parsing it as an ORM construct). We use it to run literal admin SQL.
from sqlalchemy import text
# SQLModel essentials:
#   - Session      : per-request DB handle (transaction context, query API)
#   - SQLModel     : base class for table models (Pydantic + SQLAlchemy combined)
#   - create_engine: SQLModel's thin wrapper over SQLAlchemy's create_engine
from sqlmodel import Session, SQLModel, create_engine

# `models` is a side-effect import: importing it triggers every
# `class Foo(SQLModel, table=True)` to register itself on SQLModel.metadata.
# Without that, SQLModel.metadata.create_all wouldn't know what tables to make.
# `event_bus` is imported here so the bus_events fixture can use it without
# an in-function import. noqa: F401 = tell ruff "don't flag `models` as unused".
from app import event_bus, models  # noqa: F401  -- `models` populates SQLModel.metadata before create_all
# The dependency function our FastAPI handlers depend on (via Depends(get_session)).
# We override it in the `client` fixture so endpoint code shares the test's session.
from app.db import get_session
# The actual FastAPI app instance. Imported as fastapi_app so we don't shadow
# the common name `app` inside fixtures.
from app.main import app as fastapi_app

# Admin connection URL — connects to the `postgres` database (always exists), used
# only to CREATE DATABASE yuno_test if missing. Default points at the docker-compose
# postgres service; override via env var for local-without-docker development.
ADMIN_URL = os.getenv(
    "TEST_ADMIN_DATABASE_URL",
    "postgresql+psycopg://yuno:yuno@postgres:5432/postgres",
)
# Name of the separate database we run tests against — separate so test data
# never touches the dev `yuno` database.
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "yuno_test")
# Connection URL for the test database itself, built from TEST_DB_NAME.
TEST_URL = os.getenv(
    "TEST_DATABASE_URL",
    f"postgresql+psycopg://yuno:yuno@postgres:5432/{TEST_DB_NAME}",
)


# scope="session" : run once per `pytest` invocation, not per test.
# autouse=True    : applied to every test automatically — no need to list it as a parameter.
# Together they mean: "before any test runs, ensure the DB exists; do nothing on teardown".
@pytest.fixture(scope="session", autouse=True)
def _ensure_test_database() -> Iterator[None]:
    """Create yuno_test database if missing. Idempotent across runs."""
    # AUTOCOMMIT isolation level : Postgres forbids CREATE DATABASE inside a transaction.
    # AUTOCOMMIT tells SQLAlchemy "don't wrap statements in a transaction".
    admin = sa_create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    # `with admin.connect()` : open one connection, auto-close at end of block.
    with admin.connect() as conn:
        # Query pg_database (Postgres' catalog table) for our test DB name.
        # text(...) : raw SQL. `:n` is a bound-parameter placeholder, second dict binds it.
        # .scalar() : return the first column of the first row, or None if no rows.
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"),
            {"n": TEST_DB_NAME},
        ).scalar()
        # If not found, create it. f-string interpolation is safe here because
        # TEST_DB_NAME comes from env (we control it) — not user input.
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    # dispose() releases all pooled connections — we won't use the admin engine again.
    admin.dispose()
    # `yield` with no value : fixture-pattern marker between setup (above) and
    # teardown (below). Nothing to tear down here, so the function ends right after.
    yield


# scope="session" : build the engine once per pytest invocation. Engines manage
# connection pools, which are expensive to construct repeatedly.
@pytest.fixture(scope="session")
def engine():
    """Session-scoped engine bound to the test database, with schema created."""
    # create_engine returns a connection-pool object pointed at TEST_URL.
    #   echo=False         : don't log every SQL statement to stdout (set True to debug).
    #   pool_pre_ping=True : run a tiny health-check before reusing a connection
    #                        (handles dead connections after a docker restart).
    eng = create_engine(TEST_URL, echo=False, pool_pre_ping=True)
    # Create every table SQLModel knows about (populated by the `models` import at top).
    # Idempotent — skips tables that already exist.
    SQLModel.metadata.create_all(eng)
    # Hand the engine to fixtures that depend on it (e.g., db_session below).
    yield eng
    # After all tests finish, drop the connection pool.
    eng.dispose()


# Default scope ("function") : a fresh db_session is built for every test.
# The `engine` parameter : pytest sees the name matches the `engine` fixture above
# and injects it automatically.
@pytest.fixture
def db_session(engine) -> Iterator[Session]:
    """Per-test session inside a transaction that rolls back at teardown.

    Uses SQLAlchemy 2.x `join_transaction_mode="create_savepoint"` so any
    `session.commit()` inside endpoint handlers creates/releases SAVEPOINTs
    instead of committing the outer transaction. The outer rollback wipes
    everything on teardown.
    """
    # Grab one connection from the engine's pool.
    connection = engine.connect()
    # Start a real transaction on that connection. We control when it ends.
    transaction = connection.begin()
    # Build a Session bound to this exact connection (not the pool generally), so
    # all queries this test runs share the same transaction.
    #
    # join_transaction_mode="create_savepoint" is the load-bearing trick:
    # when application code calls session.commit() (e.g., inside a router handler),
    # SQLAlchemy emits SAVEPOINT/RELEASE instead of an actual COMMIT. The outer
    # transaction stays open — only WE can end it.
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        # Hand the session to the test.
        yield session
    finally:
        # Teardown runs no matter what (even on test failure).
        # 1) Close the session (release ORM state).
        session.close()
        # 2) Roll back the outer transaction → discards everything the test wrote,
        #    even "committed" writes (they were SAVEPOINTs).
        transaction.rollback()
        # 3) Return the connection to the pool.
        connection.close()


# `db_session` parameter : pytest injects the per-test session fixture above.
@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """FastAPI TestClient with get_session overridden to share the test session."""

    # Replacement for app.db.get_session. FastAPI expects a generator (with `yield`)
    # for its DB dependency, so we mirror that shape — yield the test's session
    # so endpoint code reads/writes inside the same transaction we'll roll back.
    def _override() -> Iterator[Session]:
        yield db_session

    # FastAPI's override hook: every `Depends(get_session)` in the app now calls
    # _override() instead of the real one.
    fastapi_app.dependency_overrides[get_session] = _override
    try:
        # TestClient(app) makes the app callable like an HTTP client. Using `with`
        # so the app's startup/shutdown events fire (matches production lifecycle).
        with TestClient(fastapi_app) as c:
            yield c
    finally:
        # Wipe overrides so the next test starts with a clean app.
        fastapi_app.dependency_overrides.clear()


# monkeypatch : pytest's built-in fixture for safely replacing attributes.
# Whatever you set/replace via monkeypatch is automatically reverted at test end.
@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch):
    """Mock litellm.completion. CrewAI's Agent/Task/Crew run real on top of this.

    Returns a MagicMock whose `.return_value` can be reassigned per test via
    `mock_llm.set_response(content=..., prompt_tokens=..., completion_tokens=...)`.
    """

    # Factory: builds a fake ModelResponse with the same shape LiteLLM returns
    # for a real completion. Defaults are sensible canned values; tests override
    # via set_response below.
    def make_response(
        content: str = "ok",
        prompt_tokens: int = 10,
        completion_tokens: int = 5,
        model: str = "gemini/gemini-3.1-flash-lite-preview",
    ) -> ModelResponse:
        # Populate every field a real ModelResponse has so downstream code
        # (CrewAI's callbacks, our event subscribers) sees a "normal" response.
        return ModelResponse(
            id="test-completion",
            choices=[
                Choices(
                    index=0,
                    # The assistant's reply text.
                    message=Message(content=content, role="assistant"),
                    # "stop" = model finished normally (not "length" / "tool_calls" / etc.).
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            model=model,
        )

    # MagicMock(side_effect=fn) : when the mock is called, it runs `fn(*args, **kwargs)`
    # and returns its result. *a, **kw : accept anything (litellm.completion takes
    # many kwargs we don't care about — model, messages, temperature, max_tokens, …).
    mock = MagicMock(side_effect=lambda *a, **kw: make_response())
    # Attach the factory as an attribute so tests can reach it directly if needed:
    # `mock_llm.make_response(content="x")`.
    mock.make_response = make_response

    # Helper a test can call mid-flight to swap the canned response. Reassigning
    # side_effect changes what subsequent calls return.
    def set_response(**kwargs: Any) -> None:
        mock.side_effect = lambda *a, **kw: make_response(**kwargs)

    # Attach the helper too: `mock_llm.set_response(content="hi", prompt_tokens=3)`.
    mock.set_response = set_response

    # The actual patch: replace litellm.completion with our mock for the test's duration.
    # monkeypatch automatically restores the original at teardown.
    monkeypatch.setattr(litellm, "completion", mock)
    # Return so tests get the mock object via `def test_x(mock_llm): …`.
    return mock


@pytest.fixture
def bus_events(monkeypatch: pytest.MonkeyPatch) -> list:
    """Capture every event published on the in-process bus during a test.

    Returns a list that's appended to in-order as events are published.
    The original `publish` still runs, so subscribers still fire.
    """
    # The list tests will inspect after running their code.
    captured: list = []
    # Save the original publish — we'll still call it so subscribers run as normal.
    original_publish = event_bus.bus.publish

    # Replacement publish: record the event in `captured`, then delegate to the
    # real publish. `async` because bus.publish is async (subscribers awaited).
    async def capturing_publish(event) -> None:
        captured.append(event)
        await original_publish(event)

    # Swap publish on the bus singleton. Auto-restored at teardown.
    monkeypatch.setattr(event_bus.bus, "publish", capturing_publish)
    # Tests use this list: `assert bus_events[0].type == "run.started"`, etc.
    return captured
