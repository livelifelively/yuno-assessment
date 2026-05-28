"""State-machine tests — drive transitions by publishing events on the bus
and asserting the resulting row state.

The `runs_subscriber` fixture registers the RunsEventSubscriber on the global
bus for the duration of the test — that's a pure side effect (no value is
read in the body), so tests below request it via @pytest.mark.usefixtures
rather than as a function parameter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.event_bus import Event, bus
from app.runs import service
from app.runs.domain import LimitName, Run, RunStatus


def _make_run(agent_id, status=RunStatus.pending) -> Run:
    """Build a domain Run pinned to `agent_id` with the given status (default pending)."""
    return Run(
        id=uuid4(),
        agent_id=agent_id,
        status=status,
        input="hi",
        created_at=datetime.now(UTC),
    )


async def _publish(bus_, event_type: str, payload: dict) -> None:
    """Publish an Event onto the bus and await its dispatch (subscribers finish first)."""
    await bus_.publish(Event(type=event_type, payload=payload))


async def _create_terminal_run(db_session, agent_id, target: RunStatus) -> Run:
    """Helper: insert a pending row then force-transition it to `target` (a terminal state)."""
    run = service.create_run(
        db_session, _make_run(agent_id, status=RunStatus.pending)
    )
    service.transition_run_state(
        db_session, run.id, target, completed_at=datetime.now(UTC)
    )
    return service.get_run(db_session, run.id)


# ---------- Legal transitions ----------


def test_create_run_inserts_pending_with_zero_counters(db_session, seed_agent):
    """create_run inserts a row in status=pending with all counters at zero."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))
    assert run.status == RunStatus.pending
    assert run.token_usage_prompt == 0
    assert run.token_usage_completion == 0
    assert run.cost_usd == 0.0
    assert run.step_count == 0


@pytest.mark.usefixtures("runs_subscriber")
async def test_pending_to_active_on_run_started(db_session, seed_agent):
    """pending → active on run.started: status flips and started_at is set from payload.occurred_at."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))
    started_at = datetime.now(UTC)

    await _publish(
        bus,
        "run.started",
        {"run_id": str(run.id), "occurred_at": started_at.isoformat()},
    )

    updated = service.get_run(db_session, run.id)
    assert updated is not None
    assert updated.status == RunStatus.active
    assert updated.started_at == started_at


@pytest.mark.usefixtures("runs_subscriber")
async def test_pending_to_failed_on_run_failed(db_session, seed_agent):
    """pending → failed (early-failure path): error_code, error_message, and completed_at land from the payload."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))
    completed_at = datetime.now(UTC)

    await _publish(
        bus,
        "run.failed",
        {
            "run_id": str(run.id),
            "error_code": "compile_failed",
            "error_message": "boom",
            "occurred_at": completed_at.isoformat(),
        },
    )

    updated = service.get_run(db_session, run.id)
    assert updated.status == RunStatus.failed
    assert updated.error_code == "compile_failed"
    assert updated.error_message == "boom"
    assert updated.completed_at == completed_at


@pytest.mark.usefixtures("runs_subscriber")
async def test_pending_to_cancelled_on_run_cancelled(db_session, seed_agent):
    """pending → cancelled (operator cancels before wrapper starts): cancel_reason populated, completed_at set."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))
    requested_at = datetime.now(UTC)

    await _publish(
        bus,
        "run.cancelled",
        {
            "run_id": str(run.id),
            "initiated_by": "operator",
            "requested_at": requested_at.isoformat(),
            "note": None,
            "occurred_at": requested_at.isoformat(),
        },
    )

    updated = service.get_run(db_session, run.id)
    assert updated.status == RunStatus.cancelled
    assert updated.cancel_reason is not None
    assert updated.completed_at is not None


@pytest.mark.usefixtures("runs_subscriber")
async def test_active_to_completed_on_run_completed(db_session, seed_agent):
    """active → completed on run.completed: output is set from payload, completed_at from payload.occurred_at."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))
    service.transition_run_state(
        db_session, run.id, RunStatus.active, started_at=datetime.now(UTC)
    )

    completed_at = datetime.now(UTC)
    await _publish(
        bus,
        "run.completed",
        {
            "run_id": str(run.id),
            "output": "the answer",
            "occurred_at": completed_at.isoformat(),
        },
    )

    updated = service.get_run(db_session, run.id)
    assert updated.status == RunStatus.completed
    assert updated.output == "the answer"
    assert updated.completed_at == completed_at


@pytest.mark.usefixtures("runs_subscriber")
async def test_active_to_failed_on_run_failed(db_session, seed_agent):
    """active → failed on run.failed: error_code and error_message land from the payload."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))
    service.transition_run_state(
        db_session, run.id, RunStatus.active, started_at=datetime.now(UTC)
    )

    await _publish(
        bus,
        "run.failed",
        {
            "run_id": str(run.id),
            "error_code": "llm_provider_error",
            "error_message": "rate limited",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )

    updated = service.get_run(db_session, run.id)
    assert updated.status == RunStatus.failed
    assert updated.error_code == "llm_provider_error"


@pytest.mark.usefixtures("runs_subscriber")
async def test_active_to_aborted_on_run_aborted(db_session, seed_agent):
    """active → aborted on run.aborted: abort_reason (limit/value/cap) populated as a nested object, completed_at set."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))
    service.transition_run_state(
        db_session, run.id, RunStatus.active, started_at=datetime.now(UTC)
    )

    await _publish(
        bus,
        "run.aborted",
        {
            "run_id": str(run.id),
            "abort_reason": {
                "limit": "max_run_tokens",
                "value": 4500.0,
                "cap": 4000.0,
            },
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )

    updated = service.get_run(db_session, run.id)
    assert updated.status == RunStatus.aborted
    assert updated.abort_reason is not None
    assert updated.abort_reason.limit == LimitName.max_run_tokens
    assert updated.abort_reason.value == 4500.0
    assert updated.abort_reason.cap == 4000.0


@pytest.mark.usefixtures("runs_subscriber")
async def test_active_to_cancelled_on_run_cancelled(db_session, seed_agent):
    """active → cancelled mid-run on run.cancelled: cancel_reason populated, completed_at set."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))
    service.transition_run_state(
        db_session, run.id, RunStatus.active, started_at=datetime.now(UTC)
    )

    await _publish(
        bus,
        "run.cancelled",
        {
            "run_id": str(run.id),
            "initiated_by": "operator",
            "requested_at": datetime.now(UTC).isoformat(),
            "note": "stop",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )

    updated = service.get_run(db_session, run.id)
    assert updated.status == RunStatus.cancelled
    assert updated.cancel_reason is not None
    assert updated.cancel_reason.note == "stop"


# ---------- Illegal transitions ----------


@pytest.mark.usefixtures("runs_subscriber")
@pytest.mark.parametrize(
    "event_type,extra_payload",
    [
        ("run.completed", {"output": "x"}),
        ("run.failed", {"error_code": "e", "error_message": "m"}),
        ("run.cancelled", {"initiated_by": "operator"}),
    ],
)
async def test_event_after_terminal_completed_is_dropped(
    db_session, seed_agent, event_type, extra_payload
):
    """An event that would move OUT of `completed` is illegal → subscriber
    catches InvalidRunTransition, row state is unchanged."""
    agent_id = seed_agent()
    run = await _create_terminal_run(db_session, agent_id, RunStatus.completed)
    before = run.completed_at

    payload = {
        "run_id": str(run.id),
        "occurred_at": datetime.now(UTC).isoformat(),
        **extra_payload,
    }
    # Should not raise to the bus caller (subscriber swallows)
    await _publish(bus, event_type, payload)

    after = service.get_run(db_session, run.id)
    assert after.status == RunStatus.completed
    assert after.completed_at == before


@pytest.mark.usefixtures("runs_subscriber")
async def test_event_after_terminal_failed_is_dropped(db_session, seed_agent):
    """A run.completed event arriving at a `failed` row is illegal — row stays `failed`."""
    agent_id = seed_agent()
    run = await _create_terminal_run(db_session, agent_id, RunStatus.failed)

    await _publish(
        bus,
        "run.completed",
        {
            "run_id": str(run.id),
            "output": "x",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )

    assert service.get_run(db_session, run.id).status == RunStatus.failed


@pytest.mark.usefixtures("runs_subscriber")
async def test_event_after_terminal_aborted_is_dropped(db_session, seed_agent):
    """A run.completed event arriving at an `aborted` row is illegal — row stays `aborted`."""
    agent_id = seed_agent()
    run = await _create_terminal_run(db_session, agent_id, RunStatus.aborted)

    await _publish(
        bus,
        "run.completed",
        {
            "run_id": str(run.id),
            "output": "x",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )

    assert service.get_run(db_session, run.id).status == RunStatus.aborted


@pytest.mark.usefixtures("runs_subscriber")
async def test_event_after_terminal_cancelled_is_dropped(db_session, seed_agent):
    """A run.completed event arriving at a `cancelled` row is illegal — row stays `cancelled`."""
    agent_id = seed_agent()
    run = await _create_terminal_run(db_session, agent_id, RunStatus.cancelled)

    await _publish(
        bus,
        "run.completed",
        {
            "run_id": str(run.id),
            "output": "x",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )

    assert service.get_run(db_session, run.id).status == RunStatus.cancelled


@pytest.mark.usefixtures("runs_subscriber")
async def test_re_emitting_run_started_on_active_is_illegal(
    db_session, seed_agent
):
    """active → active via run.started is not in the legal-transitions table.
    started_at must not be overwritten."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))
    first_start = datetime.now(UTC)
    service.transition_run_state(
        db_session, run.id, RunStatus.active, started_at=first_start
    )

    await _publish(
        bus,
        "run.started",
        {"run_id": str(run.id), "occurred_at": datetime.now(UTC).isoformat()},
    )

    updated = service.get_run(db_session, run.id)
    assert updated.status == RunStatus.active
    assert updated.started_at == first_start  # unchanged


# ---------- Subscriber error containment ----------


@pytest.mark.usefixtures("runs_subscriber")
async def test_subscriber_swallows_invalid_transition(db_session, seed_agent):
    """When _handle_* raises InvalidRunTransition, the exception is caught
    inside _on_run_event and bus.publish returns normally."""
    agent_id = seed_agent()
    run = await _create_terminal_run(db_session, agent_id, RunStatus.completed)

    # This would be illegal; should NOT raise out of publish
    await _publish(
        bus,
        "run.completed",
        {
            "run_id": str(run.id),
            "output": "x",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    # Made it here without raising — the assertion is that publish completed


@pytest.mark.usefixtures("runs_subscriber")
async def test_subscriber_swallows_unknown_run_id():
    """Event for a run_id that does not exist is logged at ERROR but not raised."""
    await _publish(
        bus,
        "run.started",
        {"run_id": str(uuid4()), "occurred_at": datetime.now(UTC).isoformat()},
    )
    # No exception propagated — the test passes if publish returned
