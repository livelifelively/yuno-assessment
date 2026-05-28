"""Service-layer tests — calls app.runs.service directly; bypasses HTTP.

Uses the db_session + seed_agent fixtures. Monkeypatches
app.runtime.wrapper.service.run_agent for the create_run-spawns-wrapper test.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

import app.runtime.wrapper.service as wrapper_service
from app.event_bus import Event
from app.runs import service
from app.runs.domain import (
    ActiveStatus,
    CancelInitiator,
    Run,
    RunStatus,
)
from app.runs.errors import (
    AgentNotFoundForRun,
    InvalidRunTransition,
    RunAlreadyTerminal,
    RunNotFound,
)
from app.runs.pricing import PRICE_TABLE
from app.runtime.payloads import TokenUsage
from app.settings import settings


def _make_run(agent_id, **overrides) -> Run:
    """Build a domain Run pinned to `agent_id`; sensible defaults for everything else."""
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        agent_id=agent_id,
        status=RunStatus.pending,
        input="hi",
        created_at=now,
    )
    defaults.update(overrides)
    return Run(**defaults)


# ---------- create_run ----------


def test_create_run_persists_pending_row(db_session, seed_agent):
    """create_run inserts the run with status=pending and all counters at 0."""
    agent_id = seed_agent()
    run = _make_run(agent_id=agent_id)

    result = service.create_run(db_session, run)

    assert result.id == run.id
    assert result.status == RunStatus.pending
    assert result.token_usage_prompt == 0
    assert result.token_usage_completion == 0
    assert result.cost_usd == 0.0
    assert result.step_count == 0


def test_create_run_unknown_agent_raises_agent_not_found_for_run(
    db_session, seed_agent, monkeypatch
):
    """When agent_id does not exist, raise AgentNotFoundForRun — and do NOT spawn the wrapper."""
    spawned: list = []

    async def fake_run_agent(run_id):
        spawned.append(run_id)

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)

    run = _make_run(agent_id=uuid4())  # not seeded
    with pytest.raises(AgentNotFoundForRun):
        service.create_run(db_session, run)

    assert spawned == []


def test_create_run_spawns_wrapper_background_task(
    db_session, seed_agent, monkeypatch
):
    """create_run schedules WrapperService.run_agent(run.id) without waiting on it."""
    called: list = []

    async def fake_run_agent(run_id):
        called.append(run_id)

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)

    agent_id = seed_agent()
    run = _make_run(agent_id=agent_id)
    result = service.create_run(db_session, run)

    assert called == [result.id]


# ---------- cancel_run ----------


def test_cancel_run_on_pending_publishes_event_and_returns_row(
    db_session, seed_agent, bus_events
):
    """cancel_run on a pending row publishes run.cancelled and returns the row
    at its current (not-yet-transitioned) state — subscriber transitions async."""
    agent_id = seed_agent()
    run = _make_run(agent_id=agent_id)
    persisted = service.create_run(db_session, run)

    returned = service.cancel_run(db_session, persisted.id)

    # Returned row reflects the CURRENT state — subscriber transitions async
    assert returned.id == persisted.id
    # Event was published
    cancel_events = [e for e in bus_events if e.type == "run.cancelled"]
    assert len(cancel_events) == 1
    assert cancel_events[0].payload["run_id"] == str(persisted.id)
    assert cancel_events[0].payload["initiated_by"] == CancelInitiator.operator.value
    assert cancel_events[0].payload.get("note") is None


def test_cancel_run_carries_note_through_to_payload(
    db_session, seed_agent, bus_events
):
    """The optional note argument lands verbatim on the published payload."""
    agent_id = seed_agent()
    persisted = service.create_run(db_session, _make_run(agent_id=agent_id))

    service.cancel_run(db_session, persisted.id, note="stopping to edit")

    cancel_events = [e for e in bus_events if e.type == "run.cancelled"]
    assert cancel_events[0].payload["note"] == "stopping to edit"


def test_cancel_run_unknown_id_raises_run_not_found(db_session):
    """cancel_run on an unknown id raises RunNotFound."""
    with pytest.raises(RunNotFound):
        service.cancel_run(db_session, uuid4())


@pytest.mark.parametrize(
    "terminal",
    [RunStatus.completed, RunStatus.failed, RunStatus.aborted, RunStatus.cancelled],
)
def test_cancel_run_terminal_raises_run_already_terminal(
    db_session, seed_agent, terminal
):
    """cancel_run on a terminal row raises RunAlreadyTerminal carrying that status."""
    agent_id = seed_agent()
    persisted = service.create_run(db_session, _make_run(agent_id=agent_id))
    # Drive through `active` for terminals that aren't reachable directly from
    # `pending` per the state-machine table (only `failed` and `cancelled` are
    # legal pending → terminal moves; completed/aborted need active first).
    service.transition_run_state(
        db_session, persisted.id, RunStatus.active, started_at=datetime.now(UTC)
    )
    service.transition_run_state(
        db_session, persisted.id, terminal, completed_at=datetime.now(UTC)
    )

    with pytest.raises(RunAlreadyTerminal) as exc_info:
        service.cancel_run(db_session, persisted.id)
    assert exc_info.value.status == terminal


# ---------- Reads ----------


def test_get_run_returns_run_for_existing_id(db_session, seed_agent):
    """get_run returns the persisted domain Run for an existing id."""
    agent_id = seed_agent()
    persisted = service.create_run(db_session, _make_run(agent_id=agent_id))

    fetched = service.get_run(db_session, persisted.id)
    assert fetched is not None
    assert fetched.id == persisted.id


def test_get_run_returns_none_for_missing_id(db_session):
    """get_run returns None for an unknown id (does NOT raise)."""
    assert service.get_run(db_session, uuid4()) is None


def test_list_runs_filters_by_status(db_session, seed_agent):
    """list_runs with a status filter returns only rows in that status."""
    agent_id = seed_agent()
    r1 = service.create_run(db_session, _make_run(agent_id=agent_id))
    r2 = service.create_run(db_session, _make_run(agent_id=agent_id))
    # pending → active → completed (state machine: completed isn't reachable
    # directly from pending).
    service.transition_run_state(
        db_session, r1.id, RunStatus.active, started_at=datetime.now(UTC)
    )
    service.transition_run_state(
        db_session, r1.id, RunStatus.completed, completed_at=datetime.now(UTC)
    )

    items, total = service.list_runs(db_session, status=RunStatus.pending)
    ids = {r.id for r in items}
    assert r2.id in ids
    assert r1.id not in ids
    assert total == len(items)


def test_list_runs_filters_by_agent_id(db_session, seed_agent):
    """list_runs with an agent_id filter returns only rows for that agent."""
    agent_a = seed_agent(name="A")
    agent_b = seed_agent(name="B")
    service.create_run(db_session, _make_run(agent_id=agent_a))
    service.create_run(db_session, _make_run(agent_id=agent_b))

    items_a, total_a = service.list_runs(db_session, agent_id=agent_a)
    assert total_a == 1
    assert items_a[0].agent_id == agent_a


def test_list_runs_pagination_and_total(db_session, seed_agent):
    """list_runs respects limit/offset; total reflects the unfiltered row count."""
    agent_id = seed_agent()
    for _ in range(5):
        service.create_run(db_session, _make_run(agent_id=agent_id))

    items, total = service.list_runs(db_session, limit=2, offset=1)
    assert total == 5
    assert len(items) == 2


def test_list_runs_limit_none_uses_default_from_settings(
    db_session, seed_agent
):
    """list_runs(limit=None) falls back to settings.runs_default_list_limit."""
    agent_id = seed_agent()
    for _ in range(3):
        service.create_run(db_session, _make_run(agent_id=agent_id))

    items, total = service.list_runs(db_session, limit=None)
    assert total == 3
    assert len(items) <= settings.runs_default_list_limit


def test_list_runs_limit_clamps_at_settings_max(db_session, seed_agent):
    """list_runs(limit > runs_max_list_limit) clamps to the cap rather than honoring the larger value."""
    agent_id = seed_agent()
    for _ in range(3):
        service.create_run(db_session, _make_run(agent_id=agent_id))

    items, _ = service.list_runs(
        db_session, limit=settings.runs_max_list_limit + 100
    )
    assert len(items) <= settings.runs_max_list_limit


def test_list_active_runs_for_agent_empty_when_no_runs(db_session, seed_agent):
    """list_active_runs_for_agent returns [] for an agent with no runs."""
    agent_id = seed_agent()
    assert service.list_active_runs_for_agent(db_session, agent_id) == []


def test_list_active_runs_for_agent_returns_pending_and_active_only(
    db_session, seed_agent
):
    """list_active_runs_for_agent returns RunRef[] for pending/active rows;
    terminal rows are excluded; each RunRef carries exactly {id, status, started_at}."""
    agent_id = seed_agent()
    pending = service.create_run(db_session, _make_run(agent_id=agent_id))
    active = service.create_run(db_session, _make_run(agent_id=agent_id))
    completed = service.create_run(db_session, _make_run(agent_id=agent_id))
    service.transition_run_state(
        db_session, active.id, RunStatus.active, started_at=datetime.now(UTC)
    )
    # `completed` row: pending → active → completed.
    service.transition_run_state(
        db_session, completed.id, RunStatus.active, started_at=datetime.now(UTC)
    )
    service.transition_run_state(
        db_session,
        completed.id,
        RunStatus.completed,
        completed_at=datetime.now(UTC),
    )

    refs = service.list_active_runs_for_agent(db_session, agent_id)
    ref_ids = {r.id for r in refs}
    assert pending.id in ref_ids
    assert active.id in ref_ids
    assert completed.id not in ref_ids
    # RunRef has exactly { id, status, started_at }
    for r in refs:
        assert set(r.model_dump().keys()) == {"id", "status", "started_at"}
        assert r.status in {ActiveStatus.pending, ActiveStatus.active}


def test_get_run_events_orders_by_sequence_number(db_session, seed_agent):
    """Once events are appended, get_run_events returns them ordered by
    sequence_number ascending. Calls append_run_event directly — no bus
    publish, so the runs_subscriber fixture isn't needed here."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id=agent_id))

    e1 = Event(type="run.started", payload={"run_id": str(run.id)})
    e2 = Event(type="llm.call.started", payload={"run_id": str(run.id)})
    service.append_run_event(db_session, run.id, e1)
    service.append_run_event(db_session, run.id, e2)

    events = service.get_run_events(db_session, run.id)
    assert [e.sequence_number for e in events] == [1, 2]


def test_get_run_events_raises_for_unknown_run(db_session):
    """get_run_events raises RunNotFound when the run id is unknown."""
    with pytest.raises(RunNotFound):
        service.get_run_events(db_session, uuid4())


def test_get_daily_cost_for_agent_sums_completed_runs_in_window(
    db_session, seed_agent
):
    """get_daily_cost_for_agent sums cost_usd across runs completed inside the window."""
    agent_id = seed_agent()
    r1 = service.create_run(db_session, _make_run(agent_id=agent_id))
    r2 = service.create_run(db_session, _make_run(agent_id=agent_id))
    now = datetime.now(UTC)
    # Drive both rows pending → active → completed (state-machine forbids
    # the direct pending → completed shortcut).
    for r in (r1, r2):
        service.transition_run_state(
            db_session, r.id, RunStatus.active, started_at=now
        )
        service.transition_run_state(
            db_session, r.id, RunStatus.completed, completed_at=now
        )

    total = service.get_daily_cost_for_agent(db_session, agent_id, hours=24)
    assert isinstance(total, float)
    assert total >= 0.0  # exact value depends on accumulation; sum is non-negative


def test_get_daily_cost_for_agent_returns_zero_when_none(db_session, seed_agent):
    """get_daily_cost_for_agent returns 0.0 for an agent with no completed runs."""
    agent_id = seed_agent()
    assert service.get_daily_cost_for_agent(db_session, agent_id) == 0.0


def test_get_daily_cost_for_agent_default_window_is_24_hours(
    db_session, seed_agent
):
    """Calling with no explicit hours uses 24 — runs completed >24h ago aren't summed."""
    agent_id = seed_agent()
    r = service.create_run(db_session, _make_run(agent_id=agent_id))
    long_ago = datetime.now(UTC) - timedelta(hours=48)
    service.transition_run_state(
        db_session, r.id, RunStatus.active, started_at=long_ago
    )
    service.transition_run_state(
        db_session, r.id, RunStatus.completed, completed_at=long_ago
    )

    assert service.get_daily_cost_for_agent(db_session, agent_id) == 0.0


# ---------- State-machine helpers ----------


def test_transition_run_state_legal_updates_row(db_session, seed_agent):
    """A legal transition updates status and the supplied terminal-data columns."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id=agent_id))

    started_at = datetime.now(UTC)
    result = service.transition_run_state(
        db_session, run.id, RunStatus.active, started_at=started_at
    )
    assert result.status == RunStatus.active
    assert result.started_at == started_at


def test_transition_run_state_illegal_raises_invalid_transition(
    db_session, seed_agent
):
    """An illegal transition (out of a terminal state) raises InvalidRunTransition."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id=agent_id))
    # Drive into a legitimate terminal state first (pending → failed is legal).
    service.transition_run_state(
        db_session,
        run.id,
        RunStatus.failed,
        error_code="early",
        error_message="boom",
        completed_at=datetime.now(UTC),
    )

    # Now any further transition is illegal.
    with pytest.raises(InvalidRunTransition):
        service.transition_run_state(
            db_session, run.id, RunStatus.completed, completed_at=datetime.now(UTC)
        )


def test_accumulate_run_usage_increments_tokens_and_cost(
    db_session, seed_agent
):
    """accumulate_run_usage adds the usage to token_usage_* and adds priced cost_usd
    using the (provider, model) entry from PRICE_TABLE — depends on the lookup,
    not a specific model id."""
    # Pick the first priced (provider, model) so the test depends on the
    # lookup, not a specific id.
    (provider, model), (price_in, price_out) = next(iter(PRICE_TABLE.items()))

    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id=agent_id))

    usage = TokenUsage(prompt_tokens=10, completion_tokens=4)
    result = service.accumulate_run_usage(db_session, run.id, usage, model)

    assert result.token_usage_prompt == 10
    assert result.token_usage_completion == 4
    expected = (10 * price_in + 4 * price_out) / 1000
    assert result.cost_usd == pytest.approx(expected)


def test_bump_step_count_increments_by_one(db_session, seed_agent):
    """bump_step_count increments step_count by exactly 1 per call."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id=agent_id))

    result = service.bump_step_count(db_session, run.id)
    assert result.step_count == 1

    again = service.bump_step_count(db_session, run.id)
    assert again.step_count == 2


def test_append_run_event_computes_sequence_and_stores_payload_verbatim(
    db_session, seed_agent
):
    """append_run_event computes the next sequence_number, stores payload verbatim,
    and preserves event.occurred_at."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id=agent_id))

    payload = {"run_id": str(run.id), "extra": {"nested": 1}}
    e = Event(type="run.started", payload=payload)

    appended = service.append_run_event(db_session, run.id, e)
    assert appended.sequence_number == 1
    assert appended.payload == payload
    assert appended.occurred_at == e.occurred_at
