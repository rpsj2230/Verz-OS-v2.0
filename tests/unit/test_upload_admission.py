"""The three document doors taking their slots of one budget, over HTTP and in the worker.

The single upload and the link are read in the request while their sender waits, so each takes a
slot as INTERACTIVE; the queued upload is read later by the worker, so it takes a place as BATCH,
and the worker turns that place into a slot while it reads. All three share the document-job
budget in `brain.ops.capacity_ledger`, which is attached to the application here over the literal
fake `test_capacity_ledger.LedgerFake`. Driven through the real application with the fixtures of
`test_knowledge_intake_routes.py`, whose stand-ins (the link's transport, the corpus write, the
job queue and the object store) are described there.

Task ids: M22.1.3, M22.1.4, M22.2.1, M22.2.3
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from brain import knowledge_routes
from brain.knowledge import ingest_queue
from brain.knowledge.ingest import MediaType
from brain.knowledge.ingest_queue import (
    INGEST_TASK,
    Ticket,
    TicketState,
    outcome_sentence,
    register_ingest_tasks,
)
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.visibility import Visibility
from brain.ops.admission import CapacityRefused, Resource
from brain.ops.capacity_ledger import LIVE, CapacityLedger, Hold, Kept, render_key
from brain.ops.limits import wait_in_words, when_again
from brain.ops.queue import queue_app
from tests.fixtures.memory_store import MemoryStore
from tests.unit.test_capacity_ledger import LedgerFake
from tests.unit.test_knowledge_intake_routes import (
    MARKDOWN,
    Served,
    add_link,
    problem,
    queue,
    served,
)
from tests.unit.test_knowledge_routes import upload

KEY = (Resource.DOCUMENT_JOBS, "")
HELD = render_key(LIVE, KEY, Kept.HELD)
WAITING = render_key(LIVE, KEY, Kept.WAITING)

__all__ = ["served"]


@pytest.fixture
def cache(served: Served) -> Iterator[LedgerFake]:
    """The application's cache, holding the ledger every door on it asks."""
    fake = LedgerFake()
    served.client.app.state.capacity_ledger = CapacityLedger(client=fake)  # type: ignore[attr-defined]
    yield fake


def fill(cache: LedgerFake, slots: int, *, prefix: str = "other") -> None:
    """Slots held by other work, lapsing well after the test ends."""
    lapses = time.time() + 3600
    cache.sets.setdefault(HELD, {}).update({f"{prefix}{n}/0": lapses for n in range(slots)})


# ------------------------------------------------------------ the single upload (INTERACTIVE)
def test_a_document_read_in_the_request_holds_a_slot_while_it_is_parsed_and_gives_it_back(
    served: Served, cache: LedgerFake, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive case: inside the budget the upload is added, its parse ran holding one slot,
    and the slot is free once the response is sent. Delete this and a door that refuses every
    upload, or one that never gives its slot back, passes the refusal below."""
    during: list[int] = []
    original = knowledge_routes.read_one_at_a_time

    def watched(*args: Any, **kwargs: Any) -> Any:
        during.append(len(cache.sets.get(HELD, {})))
        return original(*args, **kwargs)

    monkeypatch.setattr(knowledge_routes, "read_one_at_a_time", watched)

    response = upload(served.client, "u_admin", MARKDOWN)

    assert response.status_code == 201, response.text
    assert during == [1]
    assert cache.sets.get(HELD, {}) == {}


def test_a_document_read_in_the_request_is_refused_as_capacity_only_past_the_whole_budget(
    served: Served, cache: LedgerFake
) -> None:
    """M22.1.3 at the door a person waits at: with three of four slots held it is admitted,
    because INTERACTIVE may use the whole budget; with four it is refused at once with
    `CapacityRefused`'s sentence and when to try again, a 503 and never a 404, and nothing is
    stored. Delete this and a busy afternoon reads as a place the person may not add to, or the
    person is queued for an answer they are sitting in front of."""
    fill(cache, 3)
    assert upload(served.client, "u_admin", MARKDOWN).status_code == 201
    fill(cache, 4)

    refused = upload(served.client, "u_admin", MARKDOWN, name="Second.md")
    code, said = problem(refused, 503)

    assert code == "busy"
    assert said.startswith(CapacityRefused.public_message)
    assert said.removeprefix(CapacityRefused.public_message).strip().startswith("You can ask again")
    assert int(refused.headers["retry-after"]) >= 1
    assert len(served.kept.stored) == 1


def test_a_document_read_in_the_request_is_added_when_the_cache_does_not_answer(
    served: Served, cache: LedgerFake
) -> None:
    """`AN_UNANSWERED_LEDGER_DECIDES_ON_WHAT_THE_CALLER_COUNTED` at the door: the parse lock still
    bounds the process, so an outage of the cache is not an outage of uploading. Delete this and
    a cache restart refuses every document added from the console."""
    cache.raises = RedisConnectionError("down")

    assert upload(served.client, "u_admin", MARKDOWN).status_code == 201
    assert len(served.kept.stored) == 1


def test_a_link_is_read_holding_a_slot_and_refused_as_capacity_when_there_is_none(
    served: Served, cache: LedgerFake
) -> None:
    """The link is read in the request too, so it takes a slot the same way and is refused in the
    same words, beside its own field. Delete this and a link's parse is the one document read on
    an install that no budget counts."""
    assert add_link(served, "u_admin").status_code == 201
    assert cache.sets.get(HELD, {}) == {}
    fill(cache, 4)

    code, said = problem(add_link(served, "u_admin"), 503)

    assert code == "busy"
    assert said.startswith(CapacityRefused.public_message)


# ------------------------------------------------------------------ the queued upload (BATCH)
def test_a_queued_file_inside_the_batch_share_starts_with_no_place_and_holds_a_slot(
    served: Served, cache: LedgerFake
) -> None:
    """Inside BATCH's share the file is told only that it is queued, and a slot is held under its
    ticket for the worker to read it in. Delete this and every queued file is told a place in
    line on an idle install."""
    response = queue(served, "u_admin")

    assert response.status_code == 202, response.text
    body = response.json()
    assert (body["position"], body["expected_wait_seconds"]) == (None, None)
    assert body["said"] == "Site handover.md is queued to be read."
    assert list(cache.sets[HELD]) == [f"{body['ticket']}/0"]


def test_a_queued_file_past_the_batch_share_is_given_its_place_and_wait_not_refused(
    served: Served, cache: LedgerFake
) -> None:
    """M22.1.4, as the uploader sees it: with the batch share of four in use by documents people
    are reading, the file is kept and queued, and the answer carries its place and expected wait
    in numbers and in the sentence the page shows; the next file stands second. Delete this and
    the queued upload tells everybody they are first, which it did until this change, or refuses
    work nobody is waiting on."""
    fill(cache, 2)

    first = queue(served, "u_admin").json()
    second = queue(served, "u_admin", MARKDOWN + b"\nmore", name="Other.md").json()

    assert (first["position"], second["position"]) == (1, 2)
    assert 0 < first["expected_wait_seconds"] <= second["expected_wait_seconds"]
    wait = wait_in_words(first["expected_wait_seconds"])
    assert first["said"] == (
        "Site handover.md is queued to be read, number 1 in line, and should start in about "
        f"{wait}."
    )
    assert set(cache.sets[WAITING]) == {first["ticket"], second["ticket"]}
    assert len(served.queue.jobs) == 2


def test_with_no_cache_the_queued_files_place_is_the_job_queues_own_count(served: Served) -> None:
    """Where the install has no cache the job queue's counts decide: two running (the batch share
    of four) and three waiting puts the next file fourth. Delete this and an install without a
    cache is back to a place that is always first."""
    served.queue.running, served.queue.waiting = 2, 3

    body = queue(served, "u_admin").json()

    assert body["position"] == 4


def test_a_file_that_never_reached_the_queue_gives_its_place_back(
    served: Served, cache: LedgerFake
) -> None:
    """A place held for a file the queue did not take would stand in front of every later file
    until it lapsed. Delete this and one queue outage moves every upload after it back a place."""
    fill(cache, 2)

    async def refuse(job: Any) -> None:
        raise ConnectionRefusedError

    served.queue.enqueue = refuse  # type: ignore[method-assign]

    code, _ = problem(queue(served, "u_admin"), 503)

    assert code == "queue_unavailable"
    assert cache.sets.get(WAITING, {}) == {}


def test_the_status_of_a_queued_file_says_no_place_after_the_answer_that_gave_one() -> None:
    """A place is true when it is given and nothing keeps it current, so only the answer to the
    upload carries one. Delete this and a later look repeats a place the queue has moved past."""
    ticket = Ticket(
        ticket="a" * 40,
        digest="d",
        media_type=MediaType.MARKDOWN,
        size_bytes=1,
        filename="notes.md",
        kind=KnowledgeKind.SOP,
        level=Visibility.DEPARTMENT,
        department="web",
        owner_id="u_admin",
        trace_id="t",
        queued_at=datetime(2999, 1, 1, tzinfo=UTC),
    )

    assert ticket.state is TicketState.QUEUED
    assert outcome_sentence(ticket) == "notes.md is queued to be read."
    assert wait_in_words(90) == "90 seconds"
    assert when_again(90) == "You can ask again in 90 seconds."


def test_a_process_finds_its_ledger_over_the_answer_cache_and_keeps_one() -> None:
    """`brain.api_routes.capacity_ledger_of`: none without a cache, and over the answer cache's
    client once, kept, so its health counters span requests. Delete this and every request builds
    a fresh ledger, or a process with no cache is handed one over nothing."""
    from types import SimpleNamespace

    from brain.api_routes import capacity_ledger_of

    assert capacity_ledger_of(SimpleNamespace(answer_client=None)) is None
    state = SimpleNamespace(answer_client=LedgerFake())
    first = capacity_ledger_of(state)
    assert first is not None and first.client is state.answer_client
    assert capacity_ledger_of(state) is first


# ------------------------------------------------------------------------ the worker
def test_the_worker_holds_a_slot_under_the_ticket_while_it_reads_and_gives_it_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`A_FILE_BEING_READ_IS_COUNTED_WHERE_THE_DOOR_COUNTED_IT`: the ticket's place becomes a slot
    for the run and is freed at the end, even when the run fails. Delete this and a file being
    read by the worker is invisible to a person's own upload, or its slot is held for a lease."""
    fake = LedgerFake()
    fake.sets[WAITING] = {"t" * 40: time.time() + 3600}
    ledger = CapacityLedger(client=fake)
    seen: list[tuple[list[str], list[str]]] = []

    async def reading(ticket: str, run: Any) -> Any:
        seen.append((list(fake.sets.get(HELD, {})), list(fake.sets.get(WAITING, {}))))
        raise RuntimeError("the parse failed")

    monkeypatch.setattr(ingest_queue, "run_ingest_job", reading)
    app = queue_app("postgresql://brain@db:5432/brain", pool_max=1)
    register_ingest_tasks(
        app,
        database_url="postgresql+psycopg://brain@db:5432/brain",
        env={},
        make_store=lambda: (MemoryStore(), "brain", ""),
        make_ledger_for=lambda: ledger,
    )

    with pytest.raises(RuntimeError):
        asyncio.run(app.tasks[INGEST_TASK].func(ticket="t" * 40))

    assert seen == [([f"{'t' * 40}/0"], [])]
    assert fake.sets.get(HELD, {}) == {}
    assert ingest_queue.start_reading(None, "t" * 40, now=datetime.now(tz=UTC)) is None


def test_a_worker_whose_cache_does_not_answer_reads_the_file_uncounted() -> None:
    """The worker's outage answer: nothing held, nothing to give back, and the file still read.
    Delete this and a cache restart fails every queued file the worker picks up meanwhile."""
    ledger = CapacityLedger(client=LedgerFake(raises=OSError("down")))

    assert ingest_queue.start_reading(ledger, "t" * 40, now=datetime.now(tz=UTC)) is None
    assert not ledger.give_back(Hold(budget_key=KEY, member="t" * 40))
