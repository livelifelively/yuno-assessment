"""Event-persistence tests — sequence numbering, step/usage/cost accumulation,
and verbatim payload storage."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.event_bus import Event, bus
from app.runs import service
from app.runs.domain import LimitName, Run, RunStatus
from app.runs.persistence.row import RunEventRow
from app.runs.pricing import PRICE_TABLE


def _make_run(agent_id) -> Run:
    return Run(
        id=uuid4(),
        agent_id=agent_id,
        status=RunStatus.pending,
        input="hi",
        created_at=datetime.now(UTC),
    )


async def _publish(event_type: str, payload: dict) -> None:
    await bus.publish(Event(type=event_type, payload=payload))


# ---------- sequence_number ----------


async def test_first_event_has_sequence_number_one(
    db_session, seed_agent, runs_subscriber
):
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))

    await _publish(
        "run.started",
        {"run_id": str(run.id), "occurred_at": datetime.now(UTC).isoformat()},
    )

    events = service.get_run_events(db_session, run.id)
    assert len(events) == 1
    assert events[0].sequence_number == 1


async def test_sequence_numbers_are_monotonic_per_run(
    db_session, seed_agent, runs_subscriber
):
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))

    await _publish(
        "run.started",
        {"run_id": str(run.id), "occurred_at": datetime.now(UTC).isoformat()},
    )
    await _publish(
        "llm.call.started",
        {
            "run_id": str(run.id),
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite-preview",
            "step_index": 1,
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    await _publish(
        "llm.call.completed",
        {
            "run_id": str(run.id),
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite-preview",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )

    events = service.get_run_events(db_session, run.id)
    assert [e.sequence_number for e in events] == [1, 2, 3]


async def test_sequence_numbers_are_independent_per_run(
    db_session, seed_agent, runs_subscriber
):
    """Two runs interleave; per-run counters are dense and independent."""
    agent_id = seed_agent()
    run_a = service.create_run(db_session, _make_run(agent_id))
    run_b = service.create_run(db_session, _make_run(agent_id))

    for r in (run_a, run_a, run_b, run_a, run_b):
        await _publish(
            "llm.call.started",
            {
                "run_id": str(r.id),
                "provider": "gemini",
                "model": "gemini-3.1-flash-lite-preview",
                "step_index": 0,
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        )

    events_a = service.get_run_events(db_session, run_a.id)
    events_b = service.get_run_events(db_session, run_b.id)
    assert [e.sequence_number for e in events_a] == [1, 2, 3]
    assert [e.sequence_number for e in events_b] == [1, 2]


def test_unique_constraint_enforces_per_run_seq(db_session, seed_agent):
    """Defence-in-depth: the (run_id, sequence_number) UNIQUE constraint
    rejects a manual duplicate insert."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))

    now = datetime.now(UTC)
    row1 = RunEventRow(
        run_id=run.id,
        sequence_number=1,
        event_type="run.started",
        payload={},
        occurred_at=now,
    )
    row2 = RunEventRow(
        run_id=run.id,
        sequence_number=1,  # duplicate
        event_type="run.started",
        payload={},
        occurred_at=now,
    )
    db_session.add(row1)
    db_session.commit()
    db_session.add(row2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------- step_count ----------


async def test_step_count_increments_on_llm_call_started(
    db_session, seed_agent, runs_subscriber
):
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))
    assert run.step_count == 0

    for _ in range(3):
        await _publish(
            "llm.call.started",
            {
                "run_id": str(run.id),
                "provider": "gemini",
                "model": "gemini-3.1-flash-lite-preview",
                "step_index": 0,
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        )

    updated = service.get_run(db_session, run.id)
    assert updated.step_count == 3


async def test_step_count_does_not_change_on_llm_call_completed_or_failed(
    db_session, seed_agent, runs_subscriber
):
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))

    await _publish(
        "llm.call.completed",
        {
            "run_id": str(run.id),
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite-preview",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    await _publish(
        "llm.call.failed",
        {
            "run_id": str(run.id),
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite-preview",
            "error_code": "x",
            "error_message": "y",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )

    updated = service.get_run(db_session, run.id)
    assert updated.step_count == 0


# ---------- token_usage_* + cost_usd ----------


async def test_token_usage_accumulates_from_llm_call_completed(
    db_session, seed_agent, runs_subscriber
):
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))

    await _publish(
        "llm.call.completed",
        {
            "run_id": str(run.id),
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite-preview",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    await _publish(
        "llm.call.completed",
        {
            "run_id": str(run.id),
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite-preview",
            "usage": {"prompt_tokens": 3, "completion_tokens": 7},
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )

    updated = service.get_run(db_session, run.id)
    assert updated.token_usage_prompt == 13
    assert updated.token_usage_completion == 12


@pytest.mark.parametrize(
    "row",
    PRICE_TABLE.items(),
    ids=[f"{p.value}/{m}" for (p, m) in PRICE_TABLE.keys()],
)
async def test_cost_usd_matches_price_table_lookup(
    db_session, seed_agent, runs_subscriber, row
):
    """Parametrized over every (provider, model) in PRICE_TABLE — no model
    name is baked into the test code. Adding a row to PRICE_TABLE auto-
    covers that model."""
    (provider, model), (price_in, price_out) = row
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))

    await _publish(
        "llm.call.completed",
        {
            "run_id": str(run.id),
            "provider": provider.value,
            "model": model,
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )

    updated = service.get_run(db_session, run.id)
    expected = (100 * price_in + 50 * price_out) / 1000
    assert updated.cost_usd == pytest.approx(expected)


async def test_cost_usd_accumulates_across_calls(
    db_session, seed_agent, runs_subscriber
):
    """Multiple llm.call.completed events sum cost_usd."""
    (provider, model), (price_in, price_out) = next(iter(PRICE_TABLE.items()))
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))

    for _ in range(3):
        await _publish(
            "llm.call.completed",
            {
                "run_id": str(run.id),
                "provider": provider.value,
                "model": model,
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        )

    updated = service.get_run(db_session, run.id)
    expected = 3 * ((10 * price_in + 5 * price_out) / 1000)
    assert updated.cost_usd == pytest.approx(expected)


async def test_unknown_model_does_not_change_cost_but_appends_event(
    db_session, seed_agent, runs_subscriber, caplog
):
    """(provider, model) NOT in PRICE_TABLE: cost stays at 0.0; a WARNING
    is logged; the event row is still appended."""
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))

    import logging

    with caplog.at_level(logging.WARNING):
        await _publish(
            "llm.call.completed",
            {
                "run_id": str(run.id),
                "provider": "gemini",
                "model": "never-heard-of-this-model",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        )

    updated = service.get_run(db_session, run.id)
    assert updated.cost_usd == 0.0
    # Event still appended
    events = service.get_run_events(db_session, run.id)
    assert any(e.event_type == "llm.call.completed" for e in events)
    # And a warning was emitted
    assert any(
        "never-heard-of-this-model" in rec.message and rec.levelname == "WARNING"
        for rec in caplog.records
    )


# ---------- llm.call.failed ----------


async def test_llm_call_failed_appends_event_but_no_row_mutation(
    db_session, seed_agent, runs_subscriber
):
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))

    await _publish(
        "llm.call.failed",
        {
            "run_id": str(run.id),
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite-preview",
            "error_code": "provider_timeout",
            "error_message": "boom",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )

    updated = service.get_run(db_session, run.id)
    assert updated.step_count == 0
    assert updated.token_usage_prompt == 0
    assert updated.token_usage_completion == 0
    assert updated.cost_usd == 0.0
    # But the event row exists
    events = service.get_run_events(db_session, run.id)
    assert any(e.event_type == "llm.call.failed" for e in events)


# ---------- Verbatim payload ----------


@pytest.mark.parametrize(
    "event_type,payload_extras",
    [
        ("run.started", {}),
        ("run.completed", {"output": "x"}),
        ("run.failed", {"error_code": "e", "error_message": "m"}),
        (
            "run.aborted",
            {
                "abort_reason": {
                    "limit": "max_run_tokens",
                    "value": 5000.0,
                    "cap": 4000.0,
                }
            },
        ),
        (
            "run.cancelled",
            {
                "initiated_by": "operator",
                "requested_at": datetime.now(UTC).isoformat(),
            },
        ),
        (
            "llm.call.started",
            {
                "provider": "gemini",
                "model": "gemini-3.1-flash-lite-preview",
                "step_index": 0,
            },
        ),
        (
            "llm.call.completed",
            {
                "provider": "gemini",
                "model": "gemini-3.1-flash-lite-preview",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        ),
        (
            "llm.call.failed",
            {
                "provider": "gemini",
                "model": "gemini-3.1-flash-lite-preview",
                "error_code": "x",
                "error_message": "y",
            },
        ),
    ],
)
async def test_run_events_payload_stored_verbatim(
    db_session, seed_agent, runs_subscriber, event_type, payload_extras
):
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))

    # Drive any prerequisite to make terminal events legal where needed
    if event_type in {"run.completed", "run.failed", "run.aborted", "run.cancelled"}:
        service.transition_run_state(
            db_session, run.id, RunStatus.active, started_at=datetime.now(UTC)
        )

    payload = {
        "run_id": str(run.id),
        "occurred_at": datetime.now(UTC).isoformat(),
        **payload_extras,
    }
    await _publish(event_type, payload)

    # Fetch from DB and assert payload stored byte-for-byte
    rows = db_session.exec(
        select(RunEventRow).where(RunEventRow.run_id == run.id)
    ).all()
    matching = [r for r in rows if r.event_type == event_type]
    assert len(matching) == 1
    assert matching[0].payload == payload


# ---------- JSONB round-trip for AbortReason / CancelReason ----------


async def test_abort_reason_round_trips_through_get_run(
    db_session, seed_agent, runs_subscriber
):
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))
    service.transition_run_state(
        db_session, run.id, RunStatus.active, started_at=datetime.now(UTC)
    )

    await _publish(
        "run.aborted",
        {
            "run_id": str(run.id),
            "abort_reason": {
                "limit": "daily_cost_usd",
                "value": 0.002,
                "cap": 0.001,
            },
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )

    updated = service.get_run(db_session, run.id)
    assert updated.abort_reason is not None
    assert updated.abort_reason.limit == LimitName.daily_cost_usd
    assert updated.abort_reason.value == 0.002
    assert updated.abort_reason.cap == 0.001


async def test_cancel_reason_round_trips_through_get_run(
    db_session, seed_agent, runs_subscriber
):
    agent_id = seed_agent()
    run = service.create_run(db_session, _make_run(agent_id))
    service.transition_run_state(
        db_session, run.id, RunStatus.active, started_at=datetime.now(UTC)
    )

    requested_at = datetime.now(UTC)
    await _publish(
        "run.cancelled",
        {
            "run_id": str(run.id),
            "initiated_by": "operator",
            "requested_at": requested_at.isoformat(),
            "note": "stopping",
            "occurred_at": requested_at.isoformat(),
        },
    )

    updated = service.get_run(db_session, run.id)
    assert updated.cancel_reason is not None
    assert updated.cancel_reason.note == "stopping"
    assert updated.cancel_reason.requested_at == requested_at
