"""Install acceptance checks for a member's own account pages: devices, reads, artifacts, storage.

Each is the route My workspace's account cards call, as a reserved member signed in through the
install's own gate (`brain.ops.acceptance_people_signed_in`), beside a refusal for somebody holding
nothing, which is the one answer an unknown page gets: DENIED and ABSENT are indistinguishable.

**Every row a page shows is the person's own, and each check asks a colleague for the same page.**
A list that showed everybody's rows to everybody would pass a check that only read one person's.

Task ids: M40.1.1.3, M40.4.2.4, M40.3.3.1, M40.4.2.1
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import asking_as
from brain.ops.acceptance_people_signed_in import console
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.ops.acceptance_people_signed_in import Console

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1910

A, B = RESERVED_DEPARTMENTS


class _Shelf:
    """An object store held in memory: a produced file is kept nowhere but this process."""

    def __init__(self) -> None:
        self.kept: dict[str, bytes] = {}

    def put_object(self, bucket_name: str, key: str, body: bytes, content_type: str) -> None:
        self.kept[f"{bucket_name}/{key}"] = body

    def get_object(self, bucket_name: str, key: str) -> bytes:
        return self.kept[f"{bucket_name}/{key}"]

    def delete_object(self, bucket_name: str, key: str) -> None:
        self.kept.pop(f"{bucket_name}/{key}", None)

    def list_objects(self, bucket_name: str, prefix: str) -> Any:
        return iter(())


async def _refused(call: Any) -> bool:
    """Whether a call was answered with the one refusal, `Absent`, and nothing else."""
    from brain.core.errors import Absent

    try:
        await call
    except Absent:
        return True
    return False


async def _member(h: Harness, c: Console, role: str) -> str:
    """A reserved person holding nothing a first sign-in does not write, not yet signed in."""
    del c
    person = h.principal(A, role)
    await h.person(person, department=A)
    return person


# ----------------------------------------------------------------- 1. devices (M40.1.1.3)
@check(
    leaves=("M40.1.1.3",),
    sentence=(
        "A member signed in twice is shown both sign-ins with the one asking marked; "
        "a colleague's sign-in is not listed; ending one of their own stops it being listed; "
        "ending a colleague's, one already ended and one that never existed are the one refusal; "
        "and a person holding nothing is refused the list."
    ),
)
async def a_member_sees_and_ends_their_own_sign_ins_and_nobody_elses(h: Harness) -> None:
    from brain.member_self_routes import MyDeviceEnding, end_my_device, my_devices

    await h.found_departments()
    c = await console(h)
    member, colleague = await _member(h, c, "devices"), await _member(h, c, "neighbour")
    here, there = c.session(), c.session()
    other = c.session()
    first = await c.asked(member, strong=False, session=there)
    second = await c.asked(member, strong=False, session=here)
    await c.asked(colleague, strong=False, session=other)

    with c.as_route():
        listed = await my_devices(c.request(), second)
        theirs = await my_devices(
            c.request(), await c.asked(colleague, strong=False, session=other)
        )
    if {one.session_id for one in listed.devices} != {here, there}:
        raise CheckFailedError("a member was not shown exactly their own two sign-ins")
    if [one.session_id for one in listed.devices if one.is_this_one] != [here]:
        raise CheckFailedError("a member was not told which sign-in was the one asking")
    if {one.session_id for one in theirs.devices} != {other}:
        raise CheckFailedError("a colleague's device list held somebody else's sign-in")

    async def ending(session_id: str, asked: Any) -> Any:
        with c.as_route():
            return await end_my_device(
                c.request("POST"), MyDeviceEnding(session_id=session_id), asked
            )

    outcomes = [
        await _refused(ending(other, second)),
        await _refused(ending(f"acceptance-{h.run}-never", second)),
    ]
    if not all(outcomes):
        raise CheckFailedError("a member could end, or probe, a sign-in that was not theirs")
    ended = await ending(there, second)
    if ended.session_id != there:
        raise CheckFailedError("a member could not end their own other sign-in")
    if not await _refused(ending(there, second)):
        raise CheckFailedError(
            "a sign-in already ended was answered differently from a missing one"
        )
    with c.as_route():
        after = await my_devices(c.request(), second)
    if {one.session_id for one in after.devices} != {here}:
        raise CheckFailedError("a sign-in a member ended was still listed")
    del first
    nobody = h.principal(A, "nobody")
    await h.person(nobody, department=A)
    if not await _refused(my_devices(c.request(), await asking_as(h, nobody))):
        raise CheckFailedError("a person holding nothing was shown a device list")


# ----------------------------------------------------------------- 2. reads (M40.4.2.4)
@check(
    leaves=("M40.4.2.4",),
    sentence=(
        "When an administrator reads a member's personnel record the member's page lists who read "
        "it and when, with the kind of record and never what was shown; a colleague's page lists "
        "nothing of it; and a person holding nothing is refused the page."
    ),
)
async def a_member_sees_who_read_their_record_and_not_what_was_shown(h: Harness) -> None:
    from brain.core.lane import Lane
    from brain.core.redaction import ChannelPayload
    from brain.gate.context import Channel
    from brain.gate.finish import Finished, Origin, ToolCallOutcome, finish
    from brain.identity.principal_store import StoredPrincipals
    from brain.member_self_routes import my_reads
    from brain.ops.sensitive_read_store import SensitiveReadRecorder
    from brain.ops.telemetry_store import TelemetryRecorder
    from brain.ops.trace_store import TraceRecorder

    await h.found_departments()
    c = await console(h)
    member, colleague = await _member(h, c, "subject"), await _member(h, c, "neighbour")
    reader = h.principal(A, "reader")
    await h.person(reader, department=A)
    who = await StoredPrincipals(h.sessions).live_principal(reader)
    if who is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    canary = h.word()
    record = {"@entity": "personnel", "principal_id": member, "name": canary}
    await finish(
        (
            TelemetryRecorder(h.sessions),
            SensitiveReadRecorder(h.sessions),
            TraceRecorder(h.sessions, environment=h.settings.env),
        ),
        Finished(
            Origin(trace_id=f"{h.trace_id}-read", principal=who, channel=Channel.CONSOLE),
            h.now,
            ToolCallOutcome(refused=False, disclosed=ChannelPayload(records=(record,))),
            completed_at=h.now,
            entitlement_hash=(await h.reach(reader)).ent_hash(),
            lane=Lane.TASK,
            tool_calls=1,
        ),
    )

    async def page(person: str) -> Any:
        with c.as_route():
            return await my_reads(c.request(), await c.asked(person, strong=False))

    mine, theirs = await page(member), await page(colleague)
    if [(one.actor_id, one.record_kind) for one in mine.reads] != [(reader, "personnel")]:
        raise CheckFailedError("a member was not shown who read their record and what kind it was")
    if canary in repr(mine):
        raise CheckFailedError("a member's list of reads carried what was shown")
    if theirs.reads:
        raise CheckFailedError("a colleague was shown reads of somebody else's record")
    nobody = h.principal(A, "nobody")
    await h.person(nobody, department=A)
    if not await _refused(my_reads(c.request(), await asking_as(h, nobody))):
        raise CheckFailedError("a person holding nothing was shown a list of reads")


# -------------------------------------------------------------- 3. artifacts (M40.3.3.1)
@check(
    leaves=("M40.3.3.1",),
    sentence=(
        "A member is shown what two different agents produced for them, newest first, and not what "
        "an agent produced for a colleague; and a person holding nothing is refused the list."
    ),
)
async def a_member_sees_what_agents_made_for_them_and_no_colleague_s(
    h: Harness,
) -> None:
    from datetime import timedelta

    from brain.console.agent_output import ArtifactInput, ArtifactKind
    from brain.core.field_policy import Classification
    from brain.member_self_routes import my_artifacts
    from brain.ops.acceptance_workspace import installed_agent
    from brain.ops.artifact_store import Produced, StoredArtifacts
    from brain.ops.retention import DataClass

    await h.found_departments()
    c = await console(h)
    member, colleague = await _member(h, c, "maker"), await _member(h, c, "neighbour")
    first = await installed_agent(h, member, suffix="_one")
    second = await installed_agent(h, member, suffix="_two")
    kind = next(iter(ArtifactKind))
    shelf = _Shelf()
    store = StoredArtifacts(h.sessions, shelf, "acceptance")
    made: dict[str, str] = {}
    for number, (agent, caller) in enumerate(
        ((first, member), (second, member), (first, colleague))
    ):
        one = await store.keep(
            Produced(
                agent_id=agent,
                kind=kind,
                run_id=f"acceptance_{h.run}_run_{number}",
                agent_version="1",
                caller_id=caller,
                reach=await h.reach(caller),
                inputs=(
                    ArtifactInput(
                        label="ticket",
                        data_class=DataClass.BUSINESS_RECORD,
                        classification=Classification.INTERNAL,
                    ),
                ),
                body=b"acceptance",
                content_type="text/plain",
            ),
            at=h.now - timedelta(minutes=number),
        )
        made[one.artifact_id] = caller
    c.app.state.artifact_source = store.every

    async def listed(person: str) -> list[str]:
        with c.as_route():
            page = await my_artifacts(c.request(), await c.asked(person, strong=False))
        return [one.artifact_id for one in page.artifacts]

    mine, theirs = await listed(member), await listed(colleague)
    wanted = [key for key, who in made.items() if who == member]
    if mine != wanted:
        raise CheckFailedError(
            "a member was not shown what every agent made for them, newest first"
        )
    if theirs != [key for key, who in made.items() if who == colleague]:
        raise CheckFailedError("a colleague was shown what was made for somebody else")
    nobody = h.principal(A, "nobody")
    await h.person(nobody, department=A)
    if not await _refused(my_artifacts(c.request(), await asking_as(h, nobody))):
        raise CheckFailedError("a person holding nothing was shown a list of artifacts")


# ----------------------------------------------------------------- 4. stored (M40.4.2.1)
@check(
    leaves=("M40.4.2.1",),
    sentence=(
        "A member is told, for every place the install keeps data about a person, what it holds "
        "and what a deletion does there, with no figure; and a person holding nothing is refused."
    ),
)
async def a_member_is_told_everywhere_data_about_them_is_kept(h: Harness) -> None:
    from brain.member_self_routes import my_stored
    from brain.ops.retention import STORES

    await h.found_departments()
    c = await console(h)
    member = await _member(h, c, "stored")
    with c.as_route():
        page = await my_stored(await c.asked(member, strong=False))
    if [one.store for one in page.stores] != [one.store.value for one in STORES]:
        raise CheckFailedError("a place data is kept was left off the page")
    if any(not one.holds.strip() or not one.deletion for one in page.stores):
        raise CheckFailedError(
            "a place was listed without saying what it holds or what deletion does"
        )
    if any(ch.isdigit() for one in page.stores for ch in one.holds + one.deletion):
        raise CheckFailedError("the page carried a figure it cannot count")
    nobody = h.principal(A, "nobody")
    await h.person(nobody, department=A)
    if not await _refused(my_stored(await asking_as(h, nobody))):
        raise CheckFailedError("a person holding nothing was told where data is kept")
