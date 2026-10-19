"""The install acceptance check for one agent's slice of learning, memory and artifacts.

An agent's Memory and Artifacts sections show that agent's slice, and the company-wide reads can be
asked for the same slice with an `agent` (M27.15.34). What an install shows is the product's own
routes, called as the Memory, Learning and Artifacts pages call them, as a reserved reader of
acceptance_a over three agents: two the reader's audience covers and one personal agent of somebody
else, which it does not.

**What is asked is the slice and the one answer a hidden agent shares with a missing one.** A person
has memories formed with each of the three agents and one formed in a plain conversation with none,
and each of the three agents has an artifact. The Learning read cut to the first agent holds that
agent's learning and nothing of the second agent's or the conversation's, the Memory read about that
person cut to it holds the memories that agent formed, and the Artifacts read cut to it holds its
artifact alone. Cut to the personal agent, each read is answered exactly as it is for an agent that
was never made, field for field, so the filter is no way to ask which agents exist.

**The install is not assumed empty.** Every list the install returns is read for the ids this check
wrote and no others, because an install in use holds other agents' learning and other people's
artifacts. An install that holds as many agents as the Learning read considers is not run, because
the read could then leave this check's agents out of what it looks at.

**Files are kept in memory.** The artifacts are written through the product's own store over an
object store held in this process, so nothing reaches a bucket and the rows are rolled back with
the check.

Task ids: M27.15.34
"""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import func, select

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_operations_console import asking_as, console_for, screen_grants
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2634

A, _ = RESERVED_DEPARTMENTS

# What the check says, one sentence for each way the property can fail.
TOO_MANY_AGENTS_TO_LOOK_AT_ALL_OF_THEM: Final = (
    "this install holds as many agents as the Learning read looks at, so it could leave this "
    "check's own agents out of what it reads"
)
NOT_FORMED: Final = "a person's turn with an agent did not form the memory the check reads"
WHOLE_READ_LACKS_AN_AGENT: Final = (
    "a read with no agent named left out what one of the reader's agents had formed or produced"
)
LEARNING_NOT_CUT: Final = "the Learning read cut to one agent held more than that agent's learning"
LEARNING_CUT_EMPTY: Final = "the Learning read cut to one agent held none of that agent's learning"
MEMORY_NOT_CUT: Final = "the Memory read cut to one agent held more than what that agent formed"
MEMORY_CUT_EMPTY: Final = "the Memory read cut to one agent held nothing that agent formed"
ARTIFACTS_NOT_CUT: Final = "the Artifacts read cut to one agent held more than that agent's files"
ARTIFACTS_CUT_EMPTY: Final = "the Artifacts read cut to one agent held none of that agent's files"
HIDDEN_AGENT_TOLD_APART: Final = (
    "a read cut to an agent the reader may not see was answered differently from one cut to an "
    "agent never made"
)
HIDDEN_AGENT_SHOWN: Final = "a read cut to an agent the reader may not see held what it holds"


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


def _unstamped(view: Any) -> dict[str, Any]:
    """A route's answer without the instant it was read, which two requests never share."""
    return dict(view.model_dump(mode="json", exclude={"as_of"}))


@check(
    leaves=("M27.15.34",),
    sentence=(
        "The Learning, Memory and Artifacts reads, each cut to one agent a reader may see, hold "
        "that agent's learning, the memories it formed about a person and the files it produced "
        "and none of another agent's or a plain conversation's; cut to an agent the reader may "
        "not see, each is answered exactly as for an agent that was never made."
    ),
)
async def an_estate_read_cut_to_an_agent_is_its_slice_and_hides_the_rest(
    h: Harness,
) -> None:
    from brain.artifact_routes import artifacts
    from brain.console.agent_output import ArtifactInput, ArtifactKind
    from brain.console.reach_view import run_reach
    from brain.core.field_policy import Classification
    from brain.estate_routes import MAX_AGENTS_CONSIDERED, learning, memory
    from brain.listing import ListAsked
    from brain.memory.turn import Turn
    from brain.ops.acceptance_workspace import (
        LOCAL_READ,
        LOCAL_TOOL,
        _everywhere,
        _planes,
        installed_agent,
        stored_agent,
    )
    from brain.ops.artifact_store import Produced, StoredArtifacts
    from brain.ops.memory_store import StoredFormations
    from brain.ops.retention import DataClass
    from brain.tables.agent import AgentRow

    held = (await h.execute(select(func.count()).select_from(AgentRow))).scalar()
    if (held or 0) >= MAX_AGENTS_CONSIDERED - 3:
        raise CheckNotRunError(TOO_MANY_AGENTS_TO_LOOK_AT_ALL_OF_THEM)

    await h.found_departments()
    steward, person, reader, stranger = (
        h.principal(A, role) for role in ("steward", "person", "reader", "stranger")
    )
    await h.person(steward, department=A)
    await h.person(stranger, department=A)
    # One grant to each capability: the screens' planes are among the planes granted whole.
    reads = dict(
        (
            *_everywhere(LOCAL_READ, *_planes()),
            *screen_grants("learning"),
            *screen_grants("memory"),
            *screen_grants("artifacts"),
        )
    )
    await h.person(reader, department=A, grants=tuple(reads.items()))
    await h.person(
        person,
        department=A,
        grants=((LOCAL_READ, Scope.department(A)), *_everywhere(*_planes())),
    )

    async def an_agent(suffix: str, owner: str, *, personal: bool = False) -> str:
        return await installed_agent(
            h,
            owner,
            capabilities=(LOCAL_READ,),
            allowed_tools=(LOCAL_TOOL,),
            scope=Scope.unrestricted(),
            suffix=suffix,
            personal=personal,
        )

    first = await an_agent("_slice_first", steward)
    second = await an_agent("_slice_second", steward)
    private = await an_agent("_slice_private", stranger, personal=True)
    missing = f"acceptance_{h.run}_slice_never_made"

    # One stated memory formed through each agent and one formed with none, by the product's own
    # formation step, under the reach the turn was answered at.
    forms = StoredFormations(h.sessions)
    ids: dict[str, str] = {}
    statements: dict[str, str] = {}
    for label, agent_id in (
        ("first", first),
        ("second", second),
        ("private", private),
        ("plain", None),
    ):
        statements[label] = f"my {h.word().lower()} is kept in the {label} place"
        reach = await h.reach(person)
        if agent_id is not None:
            reach = run_reach(reach, await stored_agent(h, agent_id))
        formed = await forms.form(
            Turn(
                trace_id=f"{h.trace_id}-{label}",
                principal_id=person,
                said=f"Remember that {statements[label]}.",
                answered=True,
                reach=reach,
                at=h.now,
                agent_id=agent_id,
            )
        )
        if len(formed.memory_ids) != 1:
            raise CheckFailedError(NOT_FORMED)
        ids[label] = formed.memory_ids[0]

    # One file through each of the three agents, kept in memory.
    store = StoredArtifacts(h.sessions, _Shelf(), "acceptance")
    files: dict[str, str] = {}
    for label, agent_id in (("first", first), ("second", second), ("private", private)):
        kept = await store.keep(
            Produced(
                agent_id=agent_id,
                kind=next(iter(ArtifactKind)),
                run_id=f"acceptance_{h.run}_slice_{label}",
                agent_version="1",
                caller_id=person,
                reach=await h.reach(person),
                inputs=(
                    ArtifactInput(
                        label="ticket",
                        data_class=DataClass.BUSINESS_RECORD,
                        classification=Classification.INTERNAL,
                    ),
                ),
                body=label.encode(),
                content_type="text/plain",
            ),
            at=h.now,
        )
        files[label] = kept.artifact_id
    console = console_for(h)
    console.app.state.artifact_source = store.every
    asking = await asking_as(h, reader)
    wanted = set(ids.values())
    mine = set(files.values())

    async def learnt(agent: str | None) -> Any:
        return await learning(console.request(), asking, agent=agent)

    async def remembered(agent: str | None) -> Any:
        return await memory(console.request(), asking, subject=person, agent=agent)

    async def produced(agent: str | None) -> Any:
        return await artifacts(console.request(), asking, ListAsked(), agent=agent)

    def learning_ids(view: Any) -> set[str]:
        return {one.memory_id for one in (*view.tier_one, *view.tier_two)} & wanted

    def memory_ids(view: Any) -> set[str]:
        return {one.memory_id for one in (*view.curated, *view.extracted)} & wanted

    def file_ids(view: Any) -> set[str]:
        return {one.artifact_id for one in view.items} & mine

    # With no agent named, everything the reader may see of the three: the personal agent's
    # learning and file are not among it, and the plain conversation's learning is.
    # The whole artifacts read is a page of the install's, which may be somebody else's, so it is
    # the second agent's slice that shows the reader may see its file.
    whole_learning, whole_memory, second_files = (
        await learnt(None),
        await remembered(None),
        await produced(second),
    )
    if (
        not {ids["first"], ids["second"], ids["plain"]} <= learning_ids(whole_learning)
        or not {ids["first"], ids["second"]} <= memory_ids(whole_memory)
        or files["second"] not in file_ids(second_files)
    ):
        raise CheckFailedError(WHOLE_READ_LACKS_AN_AGENT)

    # Cut to the first agent: its slice, and neither the second agent's nor the conversation's.
    cut_learning = learning_ids(await learnt(first))
    if not cut_learning:
        raise CheckFailedError(LEARNING_CUT_EMPTY)
    if cut_learning != {ids["first"]}:
        raise CheckFailedError(LEARNING_NOT_CUT)
    cut_memory = memory_ids(await remembered(first))
    if not cut_memory:
        raise CheckFailedError(MEMORY_CUT_EMPTY)
    if cut_memory != {ids["first"]}:
        raise CheckFailedError(MEMORY_NOT_CUT)
    cut_files = file_ids(await produced(first))
    if not cut_files:
        raise CheckFailedError(ARTIFACTS_CUT_EMPTY)
    if cut_files != {files["first"]}:
        raise CheckFailedError(ARTIFACTS_NOT_CUT)

    # Cut to the personal agent the reader may not see: what a missing agent is answered.
    for read in (learnt, remembered, produced):
        hidden, never = await read(private), await read(missing)
        if _unstamped(hidden) != _unstamped(never):
            raise CheckFailedError(HIDDEN_AGENT_TOLD_APART)
    if (
        learning_ids(await learnt(private))
        or memory_ids(await remembered(private))
        or file_ids(await produced(private))
    ):
        raise CheckFailedError(HIDDEN_AGENT_SHOWN)
