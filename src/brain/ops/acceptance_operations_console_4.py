"""Install acceptance checks for the routing matrix written from the console and for what each
channel says it carries.

Every check calls the route the console page calls, as the reader that page serves, in the shape
`brain.ops.acceptance_operations_console` sets out (`A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`).

**The matrix gate is a stand-in that passes, and that is the whole of what is stood in.** A step
added, moved or retired from the Routing screen first passes the gate, which asks the install's
golden questions of the changed ladder; whether the gate passes a change is proved by the routing
checks of `brain.ops.acceptance_routing` and its own tests. What this check proves is what the
console writes once a change has passed: the new position row, the change record and its ledger
entry under the administrator, the step's place after a move, its absence after retirement, and
an export of the configuration that holds no key. So the application here is handed a gate that
passes every change, and nothing else is stood in. See `THE_GATE_IS_PROVED_ELSEWHERE`.

**Every write is a step of the check's own, on a level of the install's ladder, inside the
check's transaction.** No real question is routed by it, because no other connection can read an
uncommitted row, and the rollback takes it away with its change record and ledger entries.

**A channel is switched off through the console's route and then sent a message through the
function its events address calls.** The webhook channel's record is set up inside the check's
transaction, as `brain.ops.acceptance_checks.a_webhook_channel_receives_once_and_stops_both_ways`
sets it up, so the install's real channels are never touched.

Task ids: M27.15.38, M27.15.43
"""

from __future__ import annotations

import json
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    screen_grants,
    traced,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.ops.matrix_gate import GateVerdict, MatrixChange

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 323

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the matrix gate is the one thing stood in.
THE_GATE_IS_PROVED_ELSEWHERE: Final = (
    "Whether the gate passes a change is the routing checks' to prove, over stand-in providers "
    "that answer the golden questions. This check proves what the console writes once a change "
    "has passed, so the application is handed a gate that passes every change and nothing else "
    "is stood in."
)

# ------------------------------------------------------------------------ the figures
#: The authorities the checks' people hold. Restated rather than imported, so a change to a
#: route's authority fails its check instead of moving with it.
WRITES_THE_MATRIX: Final = "admin:routing_matrix"
READS_THE_MATRIX: Final = "read:routing_matrix"
MANAGES_CHANNELS: Final = "admin:connector"

#: The model the check's own step names. Nothing serves it; no question is routed to it.
MODEL: Final = "acceptance-step"

#: Field names a document carrying a credential would hold, any one of which an export refuses.
KEY_FIELD_WORDS: Final = ("key", "secret", "token", "password", "credential")


# ------------------------------------------------------------------------ the helpers
@dataclass
class Passing:
    """A matrix gate that passes every change, and counts what it was asked."""

    asked: int = 0

    async def decide(self, change: MatrixChange, *, now: datetime, new_rung_id: str) -> GateVerdict:
        from brain.ops.matrix_gate import GateVerdict

        del change, now, new_rung_id
        self.asked += 1
        return GateVerdict(may_apply=True, failing=(), reasons=(), quality_share=None)


def field_names(value: Any) -> set[str]:
    """Every key of every mapping anywhere in a JSON document."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, inner in value.items():
            found.add(str(key).lower())
            found |= field_names(inner)
    elif isinstance(value, list):
        for inner in value:
            found |= field_names(inner)
    return found


async def routing_entries(h: Harness, actor: str) -> int:
    """How many ledger entries about the routing matrix this actor left in the check."""
    return int(
        (
            await h.execute(
                text(
                    "SELECT count(*) FROM obs.audit_entry WHERE actor_id = :actor"
                    " AND subject LIKE 'routing:%'"
                ).bindparams(actor=actor)
            )
        ).scalar_one()
    )


# ------------------------------------------- 1. a step written from the console (M27.15.38)
@check(
    leaves=("M27.15.38",),
    sentence=(
        "An administrator adds three steps of the check's own to a level of the ladder, moves "
        "the last to the first step and retires two, each through the Routing screen's routes "
        "once the gate passes it: each is a new position row, applied and in the ledger under "
        "them; the configuration exports with the steps and no key; anybody else is refused."
    ),
)
async def a_step_is_added_moved_and_retired_and_exported_without_keys(h: Harness) -> None:
    from brain.listing import ListAsked
    from brain.models.routing import Tier
    from brain.ops.acceptance_models import models_for
    from brain.provider_routes import export_routing
    from brain.routing_routes import RungAdd, RungMoveAsked, add, move, retire, rungs
    from brain.tables.model_registry import ChangeStatus

    await h.found_departments()
    admin, reader, other = (h.principal(A, role) for role in ("routing", "models", "other"))
    await h.person(
        admin,
        department=A,
        grants=(
            (WRITES_THE_MATRIX, Scope.unrestricted()),
            (READS_THE_MATRIX, Scope.unrestricted()),
        ),
    )
    await h.person(reader, department=A, grants=screen_grants("models"))
    await h.person(other, department=A)
    console = console_for(h)
    gate = Passing()
    console.app.state.matrix_gate = gate
    console.app.state.models = await models_for(h)
    asked_to_add = RungAdd(
        tier=Tier.MAIN,
        provider="openai",
        model=MODEL,
        attempts=1,
        timeout_seconds=5.0,
        max_concurrency=1,
    )
    if not await refused(add(console.request("POST"), asked_to_add, await asking_as(h, other))):
        raise CheckFailedError("a person without the matrix authority added a step")
    if not await refused(export_routing(console.request(), await asking_as(h, other))):
        raise CheckFailedError("a person who may not read the models was given the export")

    administrator = await asking_as(h, admin, strong=True)
    added = []
    for n in range(3):
        async with traced(h, n + 1):
            one = await add(
                console.request("POST"),
                asked_to_add.model_copy(update={"model": f"{MODEL}-{n}"}),
                administrator,
            )
        if one.status is not ChangeStatus.APPLIED or one.rung is None:
            raise CheckFailedError("a step added from the console after the gate was not applied")
        added.append(one.rung)
    if gate.asked != len(added):
        raise CheckFailedError("a step was added from the console without the gate being asked")

    exported = await export_routing(console.request(), await asking_as(h, reader))
    document = json.loads(exported.model_dump_json())
    if not any(
        one["model"] == f"{MODEL}-0" and one["tier"] == Tier.MAIN.value for one in document["steps"]
    ):
        raise CheckFailedError("the routing export did not carry the step just added")
    if any(word in name for name in field_names(document) for word in KEY_FIELD_WORDS):
        raise CheckFailedError("the routing export carried a field a credential would be in")

    async def live_models() -> dict[str, Any]:
        page = await rungs(console.request(), administrator, ListAsked(limit=200))
        return {one.model: one for one in page.items if one.tier == Tier.MAIN.value}

    async with traced(h, 4):
        moved = await move(
            console.request("POST"),
            uuid.UUID(added[2].id),
            RungMoveAsked(tier=Tier.MAIN, step=1),
            administrator,
        )
    if moved.status is not ChangeStatus.APPLIED or moved.rung is None:
        raise CheckFailedError("a step moved from the console after the gate was not applied")
    if moved.rung.id == added[2].id:
        raise CheckFailedError("a moved step was not written as a new position row")
    ordered = sorted((await live_models()).values(), key=lambda one: one.position)
    if not ordered or ordered[0].model != f"{MODEL}-2":
        raise CheckFailedError("a step moved to the first step was not tried first")

    for n, model in ((5, f"{MODEL}-2"), (6, f"{MODEL}-1")):
        async with traced(h, n):
            retired = await retire(
                console.request("POST"), uuid.UUID((await live_models())[model].id), administrator
            )
        if retired.status is not ChangeStatus.APPLIED:
            raise CheckFailedError("a step retired from the console after the gate was not applied")
    left = await live_models()
    if f"{MODEL}-2" in left or f"{MODEL}-1" in left or f"{MODEL}-0" not in left:
        raise CheckFailedError("a retired step was still on the matrix")
    if await routing_entries(h, admin) < 6:
        raise CheckFailedError("a step written from the console is not in the ledger under them")


# ------------------------------------ 2. what each channel carries, and off (M27.15.43)
@check(
    leaves=("M27.15.43",),
    sentence=(
        "An administrator of channels is shown, for every channel an adapter declares, the "
        "verbs it may carry and how a group on it is answered at its floor; the webhook channel "
        "switched off through the Channels route then refuses a signed message without reading "
        "it; a person without the authority is shown no channel."
    ),
)
async def each_channel_says_what_it_carries_and_off_refuses_inbound(h: Harness) -> None:
    from brain.binding_routes import ROOMS_TOLD, RoomAnswer, _declared, health
    from brain.channel_routes import SwitchAsked, switch
    from brain.channels.adapter import channel_wires
    from brain.channels.inbound import receive
    from brain.channels.webhook import REPLY_URL, SIGNATURE_HEADER, TIMESTAMP_HEADER, sign
    from brain.gate.admission import CHANNEL_VERBS
    from brain.gate.context import Channel
    from brain.ops.acceptance_checks import _Secret, _Spy
    from brain.ops.channel_store import StoredChannels, StoredClaims, StoredDeliveries
    from brain.tables.channel import RefusedBecause

    await h.found_departments()
    admin, other = h.principal(A, "channels"), h.principal(A, "other")
    await h.person(admin, department=A, grants=((MANAGES_CHANNELS, Scope.unrestricted()),))
    await h.person(other, department=A)
    console = console_for(h)
    if not await refused(
        health(Channel.WEBHOOK.value, console.request(), await asking_as(h, other))
    ):
        raise CheckFailedError("a person without the authority was shown a channel")

    administrator = await asking_as(h, admin, strong=True)
    for channel in _declared():
        shown = await health(channel.value, console.request(), administrator)
        if shown.verbs != sorted(CHANNEL_VERBS.get(channel, frozenset())):
            raise CheckFailedError("a channel did not say the verbs it may carry")
        if shown.rooms_told != ROOMS_TOLD[shown.rooms]:
            raise CheckFailedError("a channel did not say how a group on it is answered")
        if (shown.rooms is RoomAnswer.NOT_RECEIVED) == (channel in channel_wires()):
            raise CheckFailedError("a channel's group answer disagreed with what it receives")

    channels = StoredChannels(h.sessions)
    await channels.save(
        Channel.WEBHOOK,
        enabled=True,
        tenant={REPLY_URL: f"https://acceptance.invalid/{h.run}"},
        actor=admin,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )
    async with traced(h, 1):
        await switch(
            Channel.WEBHOOK.value,
            SwitchAsked(enabled=False),
            console.request("POST"),
            administrator,
        )
    off = await channels.get(Channel.WEBHOOK)
    if off is None or off.enabled:
        raise CheckFailedError("a channel switched off from the console was still on")

    made = _Secret(secrets.token_hex(32))
    spy = _Spy(channel_wires()[Channel.WEBHOOK])
    message = json.dumps(
        {"id": f"acceptance-{h.run}", "sender": f"acceptance-{h.run}", "text": h.word()}
    ).encode()
    read: list[int] = []

    async def body() -> bytes:
        read.append(1)
        return message

    stamp = str(int(time.time()))
    receipt = await receive(
        spy,
        record=off,
        headers={TIMESTAMP_HEADER: stamp, SIGNATURE_HEADER: sign(made.value, stamp, message)},
        declared_length=len(message),
        body=body,
        secrets=made,
        claims=StoredClaims(h.sessions),
        deliveries=StoredDeliveries(h.sessions),
        now=h.now,
    )
    if receipt.reason is not RefusedBecause.SWITCHED_OFF or read or spy.reads:
        raise CheckFailedError("a channel switched off from the console read a message")
