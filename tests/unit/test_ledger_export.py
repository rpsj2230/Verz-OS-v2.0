"""Each run's masked trace sent to the trace ledger an install switched on, and nowhere else.

The ledger is an `httpx.MockTransport` here, which keeps every request it was sent, so what is
asserted is what would have crossed the network. The canary is a value no masked field may carry.

Task ids: M32.1.2.6, M32.1.1.4
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from brain.install import hold_saved
from brain.ops.leases import SealedSecret
from brain.ops.ledger_export import (
    INGESTION_PATH,
    KEYS_KEPT_FOR,
    LEDGER_KEY_SLOT,
    LEDGER_PORT,
    LEDGER_SERVICE,
    PRIVATE_FIELD,
    PUBLIC_FIELD,
    KeptKeys,
    LedgerError,
    LedgerKeys,
    LedgerShipper,
    destination_here,
    events_of,
    keep_keys,
    keys_from,
    ledger_address,
    read_keys,
)
from brain.ops.trace_store import Step
from brain.ops.tracing import Span, StepKind
from brain.ops.wiring import TRACE_LEDGER, trace_config_conflicts

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
CANARY = "canary-7f3a-not-for-any-ledger"
KEYS = LedgerKeys(public="pk-lf-0123", secret=SealedSecret("sk-lf-4567"))
SWITCHED = frozenset(TRACE_LEDGER)


def a_run(trace_id: str = "t-1") -> tuple[Step, ...]:
    return (
        Step(
            step=0,
            parent=None,
            kind=StepKind.REQUEST,
            span=Span(
                name="request",
                environment="production",
                attributes={"outcome": "answered", "principal": CANARY},
                payload_in=CANARY,
                payload_out=CANARY,
            ),
        ),
        Step(
            step=1,
            parent=0,
            kind=StepKind.MODEL_ATTEMPT,
            span=Span(name="model_attempt", environment="production", payload_out=CANARY),
        ),
        Step(
            step=2,
            parent=0,
            kind=StepKind.TOOL_CALL,
            span=Span(name="tool_call", environment="production"),
        ),
        Step(
            step=3,
            parent=2,
            kind=StepKind.RETRIEVAL,
            span=Span(name="retrieval", environment="production"),
        ),
    )


# ------------------------------------------------------------------ where spans go
def test_the_ledger_is_the_destination_exactly_when_it_runs() -> None:
    """The switch is the one source: on lite with the ledger switched on the product's own service
    is the destination, with it off there is none, whatever is configured. Delete this and a lite
    install ships spans to an address copied from another install's environment file."""
    own = f"http://{LEDGER_SERVICE}:{LEDGER_PORT}"
    assert ledger_address("lite", "", SWITCHED) == own
    assert ledger_address("lite", " http://elsewhere:3000 ", SWITCHED) == "http://elsewhere:3000"
    assert ledger_address("lite", "", frozenset()) is None
    assert ledger_address("lite", "http://elsewhere:3000", frozenset()) is None
    assert ledger_address("lite", "", frozenset({"presidio-analyzer"})) is None
    assert ledger_address("full", "", frozenset()) == own


def test_a_destination_on_lite_is_accepted_once_the_ledger_is_switched_on() -> None:
    """`trace_config_conflicts` refuses a destination where nothing runs a ledger and accepts it
    where the switch declares one. Delete this and the switch starts a ledger the startup check then
    refuses to let anything configure."""
    values = {"langfuse_host": "http://langfuse-web:3000"}
    assert trace_config_conflicts("lite", values)
    assert trace_config_conflicts("lite", values, SWITCHED) == ()


def test_the_destination_reads_the_switch_and_an_unreadable_one_sends_nowhere() -> None:
    """Read through the one installation reader, saved value first; a value nobody declared sends
    nothing rather than raising inside a send. Delete this and a typo in the setting either ships
    spans or breaks every finished request's recorder."""
    before = hold_saved({"INSTALL_SERVICES": "presidio,langfuse"})
    try:
        assert destination_here("lite", "") == f"http://{LEDGER_SERVICE}:{LEDGER_PORT}"
        hold_saved({"INSTALL_SERVICES": "presidio"})
        assert destination_here("lite", "") is None
        hold_saved({"INSTALL_SERVICES": "langfuse-typo"})
        assert destination_here("lite", "") is None
    finally:
        hold_saved(before)


# ------------------------------------------------------------------------ the events
def test_every_field_sent_is_what_mask_leaves_and_the_canary_is_in_none() -> None:
    """`brain.ops.tracing.mask` is the only way a span leaves this process, so nothing the ledger
    is sent may carry a value the run held. Delete this and a field built from the span rather than
    from its masked copy sends a client's answer to the ledger."""
    batch = events_of("t-1", a_run(), at=LONG_AGO)
    assert CANARY not in json.dumps(batch)
    assert batch[0]["body"]["output"].startswith("[masked:")


def test_a_run_is_a_trace_with_its_model_call_as_a_generation_hung_where_it_ran() -> None:
    """The ledger's screen lists generations as model calls, so a model attempt is one; a read hangs
    from the tool call that made it, and the ids are the trace's and the step's, so a run sent twice
    is the same events again. Delete this and the screen the owner gave memory to shows no model
    call, or two copies of every run."""
    batch = events_of("t-1", a_run(), at=LONG_AGO)
    kinds = [(one["type"], one["body"].get("parentObservationId")) for one in batch]
    assert kinds == [
        ("trace-create", None),
        ("generation-create", None),
        ("span-create", None),
        ("span-create", "t-1-2"),
    ]
    assert batch[0]["body"]["id"] == "t-1"
    assert all(one["body"].get("traceId", "t-1") == "t-1" for one in batch)
    assert batch == events_of("t-1", a_run(), at=LONG_AGO)
    assert batch[0]["timestamp"] == "2019-03-06T09:00:00Z"
    assert events_of("t-1", (), at=LONG_AGO) == []


# -------------------------------------------------------------------------- the keys
def test_the_keys_handed_over_must_be_the_ledger_s_shapes() -> None:
    """A public and a secret key, in that order, each in the ledger's own shape. Delete this and
    a deploy that handed over a blank or swapped pair keeps it, and every send is refused with no
    sentence anywhere saying why."""
    assert keys_from(["pk-lf-0123\n", "sk-lf-4567\n"]).public == "pk-lf-0123"
    shapes = (
        ["sk-lf-4567", "pk-lf-0123"],
        ["xx-lf-0123", "sk-lf-4567"],
        ["pk-lf-0123"],
        ["pk-lf-0123", "sk-lf-"],
        [],
    )
    for lines in shapes:
        with pytest.raises(LedgerError):
            keys_from(lines)


class Vault:
    def __init__(self) -> None:
        self.slots: dict[str, dict[str, Any]] = {}
        self.reads = 0

    def write_static_kv(self, path: str, fields: Mapping[str, str]) -> datetime | None:
        self.slots[path] = dict(fields)
        return LONG_AGO

    def read_static_kv(self, path: str) -> dict[str, Any]:
        self.reads += 1
        return dict(self.slots.get(path, {}))

    def static_kv_version(self, path: str) -> None:
        del path


def test_the_keys_are_kept_in_their_slot_and_read_back_and_nothing_else_reads_as_keys() -> None:
    """Delete this and the keys can be written where the worker's policy does not read, or a slot
    of the wrong shape read as keys."""
    vault = Vault()
    keep_keys(vault, KEYS)
    assert vault.slots[LEDGER_KEY_SLOT] == {PUBLIC_FIELD: "pk-lf-0123", PRIVATE_FIELD: "sk-lf-4567"}
    back = read_keys(vault)
    assert back is not None and back.public == "pk-lf-0123"
    assert back.secret.reveal() == "sk-lf-4567"
    vault.slots[LEDGER_KEY_SLOT] = {PUBLIC_FIELD: "pk-lf-0123"}
    assert read_keys(vault) is None
    assert "sk-lf-4567" not in repr(KEYS)


def test_a_process_keeps_the_keys_a_quarter_of_an_hour_and_then_asks_again() -> None:
    """Delete this and every finished request asks the vault, or a key the deploy replaced is never
    picked up."""
    vault = Vault()
    keep_keys(vault, KEYS)
    now = [LONG_AGO]
    kept = KeptKeys(vault, clock=lambda: now[0])
    assert kept() is not None and kept() is not None
    assert vault.reads == 1
    now[0] = LONG_AGO + KEYS_KEPT_FOR
    kept()
    assert vault.reads == 2
    assert KeptKeys(None, clock=lambda: LONG_AGO)() is None


# -------------------------------------------------------------------------- the send
def shipper(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    destination: str | None = "http://langfuse-web:3000",
    keys: LedgerKeys | None = KEYS,
) -> tuple[LedgerShipper, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return (
        LedgerShipper(
            destination=lambda: destination,
            keys=lambda: keys,
            clock=lambda: LONG_AGO,
            client=lambda: httpx.AsyncClient(transport=httpx.MockTransport(recording)),
        ),
        seen,
    )


def test_a_run_is_posted_to_the_ingestion_route_with_the_ledger_s_keys() -> None:
    """The positive case, on the wire. Delete this and a sender that never sends passes the rest."""
    ship, seen = shipper(lambda request: httpx.Response(207, json={"successes": [1], "errors": []}))

    assert asyncio.run(ship.ship("t-1", a_run())) is True
    [request] = seen
    assert request.url.path == INGESTION_PATH
    expected = "Basic " + base64.b64encode(b"pk-lf-0123:sk-lf-4567").decode()
    assert request.headers["Authorization"] == expected
    assert json.loads(request.content)["batch"] == events_of("t-1", a_run(), at=LONG_AGO)


@pytest.mark.parametrize(
    "answer",
    [
        lambda request: httpx.Response(207, json={"successes": [], "errors": [{"id": "x"}]}),
        lambda request: httpx.Response(401),
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("down")),
    ],
    ids=["an event refused", "the keys refused", "the ledger down"],
)
def test_a_ledger_that_does_not_take_the_run_is_said_and_never_raised(answer: Any) -> None:
    """`A_LEDGER_THAT_DOES_NOT_ANSWER_COSTS_A_RUN_NOTHING`. Delete this and a ledger fault becomes a
    fault in every finished request."""
    ship, _ = shipper(answer)
    assert asyncio.run(ship.ship("t-1", a_run())) is False


@pytest.mark.parametrize(
    ("destination", "keys"), [(None, KEYS), ("http://langfuse-web:3000", None)]
)
def test_with_no_destination_or_no_keys_nothing_is_sent(
    destination: str | None, keys: LedgerKeys | None
) -> None:
    """M32.1.1.4's half: no ledger, nothing sent; and keys not yet handed over are not a send with
    none. Delete this and an install without a ledger sends to whatever resolves."""
    ship, seen = shipper(
        lambda request: httpx.Response(207, json={}), destination=destination, keys=keys
    )
    assert asyncio.run(ship.ship("t-1", a_run())) is False
    assert seen == []


def test_a_send_beside_the_request_returns_at_once_and_still_reaches_the_ledger() -> None:
    """`ship_beside` returns before the send finishes, and the send still happens. Delete this and a
    slow ledger holds every answer up, or the send is started and dropped."""
    gate = asyncio.Event()
    seen: list[str] = []

    async def scenario() -> None:
        async def slow(request: httpx.Request) -> httpx.Response:
            await gate.wait()
            seen.append(request.url.path)
            return httpx.Response(207, json={"errors": []})

        ship = LedgerShipper(
            destination=lambda: "http://langfuse-web:3000",
            keys=lambda: KEYS,
            clock=lambda: LONG_AGO,
            client=lambda: httpx.AsyncClient(transport=httpx.MockTransport(slow)),
        )
        ship.ship_beside("t-1", a_run())
        assert seen == []
        gate.set()
        for _ in range(50):
            if seen:
                break
            await asyncio.sleep(0.01)

    asyncio.run(scenario())
    assert seen == [INGESTION_PATH]


def test_the_keys_kept_for_figure_is_the_worker_s_provider_key_window() -> None:
    """The same quarter of an hour the worker keeps a provider key, held against that module's own
    figure. Delete this and the two drift into two answers to one question about the vault."""
    from brain.ops.model_probe_run import KEY_REREAD_SECONDS

    assert timedelta(seconds=KEY_REREAD_SECONDS) == KEYS_KEPT_FOR
