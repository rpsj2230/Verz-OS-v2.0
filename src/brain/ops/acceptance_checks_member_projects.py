"""Install acceptance check for a person's own project (M40.7.7).

A member makes a project, lists a document of their own and one of their threads in it, and asks
a question inside it, as the routes and `/answer`'s own deciding function are called with the
install's database under them. **What the check is for is the four things a project must not
do**: be seen or changed by anybody else, make a document readable that the reader could not
already read, keep being read after the right to read it is gone, and become memory. Each is asked
beside the act that works, so a project that refuses everything does not pass.

**The reading is the real one.** The files a question inside the project brings are decided by
`brain.api_routes.follow_up_for` over the install's tables, and read through the tool registry's own
`knowledge.read_document` handler at the reach handed to it, the way the answer lane calls it. No
model is run: the lane's use of what is read is `tests/unit/test_project_context.py`'s, and the
question here is only what is read and at whose reach.

Task ids: M40.7.7
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import func, select

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1950

A, _B = RESERVED_DEPARTMENTS

#: The reasons a check fails, one literal sentence each: a reason is served on a public page.
MADE_WITH_THE_SWITCH_OFF: Final = "a project was made while the switch was off"
NOT_MADE: Final = "a person could not make a project of their own with the switch on"
NOT_LISTED: Final = "a project a person made was not listed for them"
SEEN_BY_ANOTHER: Final = "a person saw or changed another person's project"
LISTED_WHAT_COULD_NOT_BE_READ: Final = "a person listed a document they could not read"
NOT_FILLED: Final = "a document and a thread of a person's own could not be listed in their project"
NOT_BROUGHT: Final = "a question inside a project did not bring its document"
BROUGHT_TO_ANOTHER: Final = "a question brought another person's project"
NOT_READ_BY_THE_TOOL: Final = "the project's document was not read at its owner's reach"
READ_PAST_THE_REACH: Final = "a document was read for someone who could not read it"
LEFT_THE_LIST: Final = "a document the person could no longer read was dropped from the list"
STILL_READ_AFTER_AWAY: Final = "a project put away was still read"
STILL_READ_WITH_SWITCH_OFF: Final = "a project was read with the switch off"
TRAPPED_BY_THE_SWITCH: Final = "turning the switch off stopped a person tidying their projects"
AWAY_BUT_STILL_CHANGED: Final = "a project put away was added to or put away again"
FULL_SHELF_NOT_SAID: Final = (
    "a person made more projects than may be kept, or could not make one after putting one away"
)
BECAME_MEMORY: Final = "a project's document was kept as a memory of the person"


def _member(scope: Scope) -> tuple[tuple[str, Scope], ...]:
    """What a member holds to open the member application: the home read and the content plane."""
    from brain.member.shell import member_capability

    return ((member_capability("home").value, scope), ("read:member.content", scope))


async def _refused(call: Any) -> bool:
    """Whether a call was answered with the one refusal, `Absent`, and nothing else."""
    from brain.core.errors import Absent

    try:
        await call
    except Absent:
        return True
    return False


def _status(answered: Any) -> int:
    return int(getattr(answered, "status_code", 200))


@check(
    leaves=("M40.7.7",),
    sentence=(
        "A member lists a document and a thread of theirs in a project and a question inside it "
        "reads the document at their reach; a colleague sees and borrows nothing; a document the "
        "member can no longer read stays listed and is not read; a project put away, or the switch "
        "off, reads nothing; nothing becomes memory."
    ),
)
async def a_member_asks_inside_a_project_and_it_reads_what_they_may_read(h: Harness) -> None:
    from brain.api_routes import Answering, Question, follow_up_for
    from brain.chat.thread_store import Exchange, StoredThreads
    from brain.feature_routes import SwitchAsked, switch_feature
    from brain.gate.context import Channel
    from brain.govern_routes import retire_grant
    from brain.knowledge.document_tools import READ_DOCUMENT
    from brain.knowledge.ingest import MediaType, ParseFailure
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.knowledge.visibility import Visibility
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _upload
    from brain.ops.acceptance_documents import a_markdown_document
    from brain.ops.acceptance_operations_console import asking_as, console_for, traced
    from brain.ops.acceptance_threads import _asking, _request, _web
    from brain.ops.features_declared.personal_projects import PERSONAL_PROJECTS
    from brain.project_routes import (
        ItemAsked,
        NameAsked,
        add_to_my_project,
        make_my_project,
        my_project,
        my_projects,
        put_my_project_away,
        rename_my_project,
        take_out_of_my_project,
    )
    from brain.tables.memory import AdaptiveMemoryRow, PersistentMemoryRow

    await h.found_departments()
    owner, colleague, administrator = (
        h.principal(A, role) for role in ("projects", "friend", "projects_admin")
    )
    everywhere = Scope.unrestricted()
    await h.person(
        owner,
        department=A,
        grants=(*_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value), *_member(everywhere)),
    )
    await h.person(
        colleague, department=A, grants=(*_in(A, *KNOWLEDGE_READS), *_member(everywhere))
    )
    await h.person(administrator, department=A, grants=(("admin:feature", everywhere),))

    app: FastAPI = await _web(h)

    async def switched(on: bool, n: int) -> None:
        async with traced(h, n):
            await switch_feature(
                console_for(h).request("POST"),
                PERSONAL_PROJECTS.name,
                SwitchAsked(on=on),
                await asking_as(h, administrator, strong=True),
            )

    async def asked(who: str) -> Any:
        return await _asking(h, who)

    async def listed(who: str) -> list[str]:
        shown = await my_projects(_request(app), await asked(who))
        return [one.project_id for one in shown.projects]

    word = h.word()
    uploaded = await _upload(
        h,
        owner,
        filename="Acceptance project.md",
        declared=MediaType.MARKDOWN.value,
        body=a_markdown_document("Acceptance project", f"This project file says {word}."),
        level=Visibility.PERSONAL,
    )
    if isinstance(uploaded, ParseFailure):
        raise CheckFailedError("a well-formed Markdown document could not be added")
    document = str(uploaded.item.item_id)
    thread = "00000000-0000-4000-8000-" + h.run.replace("-", "")[:12].ljust(12, "0")
    await StoredThreads(h.sessions).record(
        owner,
        thread_id=thread,
        channel=Channel.CONSOLE,
        exchange=Exchange(
            question="What is in the project file?", answer="It says what it says.", refs=()
        ),
        now=h.now,
    )

    # With the switch off nothing is made. Turned on, the same request makes a project.
    await switched(False, 1)
    off = await make_my_project(_request(app), NameAsked(name="Acceptance"), await asked(owner))
    if _status(off) != 409 or await listed(owner):
        raise CheckFailedError(MADE_WITH_THE_SWITCH_OFF)
    await switched(True, 2)
    made = await make_my_project(
        _request(app), NameAsked(name="  Acceptance   plan "), await asked(owner)
    )
    project_id = getattr(made, "project_id", "")
    if not project_id:
        raise CheckFailedError(NOT_MADE)
    if await listed(owner) != [project_id] or await listed(colleague):
        raise CheckFailedError(NOT_LISTED)

    # What a person may list: a document they can read and a thread of their own, nothing else.
    colleagues_try = (
        add_to_my_project(
            _request(app), project_id, ItemAsked(kind="file", ref=document), await asked(colleague)
        ),
        rename_my_project(
            _request(app), project_id, NameAsked(name="Mine"), await asked(colleague)
        ),
        put_my_project_away(_request(app), project_id, await asked(colleague)),
        my_project(_request(app), project_id, await asked(colleague)),
    )
    for call in colleagues_try:
        if not await _refused(call):
            raise CheckFailedError(SEEN_BY_ANOTHER)
    theirs = await make_my_project(_request(app), NameAsked(name="Theirs"), await asked(colleague))
    if not await _refused(
        add_to_my_project(
            _request(app),
            getattr(theirs, "project_id", ""),
            ItemAsked(kind="file", ref=document),
            await asked(colleague),
        )
    ) or not await _refused(
        add_to_my_project(
            _request(app),
            getattr(theirs, "project_id", ""),
            ItemAsked(kind="thread", ref=thread),
            await asked(colleague),
        )
    ):
        raise CheckFailedError(LISTED_WHAT_COULD_NOT_BE_READ)
    for item in (ItemAsked(kind="file", ref=document), ItemAsked(kind="thread", ref=thread)):
        done = await add_to_my_project(_request(app), project_id, item, await asked(owner))
        if getattr(done, "project_id", "") != project_id:
            raise CheckFailedError(NOT_FILLED)

    # A question inside the project brings its document, and reading goes through the registered
    # tool at the reach the run holds.
    registry = app.state.tools
    reach = await h.reach(owner)

    async def following(who: str, ask: Question) -> Any:
        was = await asked(who)
        answering = Answering(
            principal=was.caller.principal, reach=was.reach, channel=Channel.CONSOLE, now=was.now
        )
        return await follow_up_for(app.state, answering, ask, registry)

    for ask in (
        Question(question="what does it say", project=project_id),
        Question(question="and then", thread=thread),
    ):
        follow = await following(owner, ask)
        if (
            follow is None
            or follow.project_files != (document,)
            or follow.read_project_file is None
        ):
            raise CheckFailedError(NOT_BROUGHT)
    if await following(colleague, Question(question="x", project=project_id)) is not None:
        raise CheckFailedError(BROUGHT_TO_ANOTHER)

    async def read_as(reach_of: Any) -> str:
        follow = await following(owner, Question(question="x", project=project_id))
        assert follow is not None and follow.read_project_file is not None
        result = await follow.read_project_file(document, entitlement=reach_of, now=h.now)
        return " ".join(one.document for one in result.records)

    if word not in await read_as(reach):
        raise CheckFailedError(NOT_READ_BY_THE_TOOL)
    if await read_as(await h.reach(colleague)):
        raise CheckFailedError(READ_PAST_THE_REACH)
    if not registry.has(READ_DOCUMENT):
        raise CheckFailedError(NOT_BROUGHT)

    # The member loses the right to read the document: it stays on the list and is not read.
    for capability in KNOWLEDGE_READS:
        await h.execute(*h.attributed(), retire_grant(owner, capability))
    if await read_as(await h.reach(owner)):
        raise CheckFailedError(READ_PAST_THE_REACH)
    after = await my_project(_request(app), project_id, await asked(owner))
    if [(one.kind, one.ref) for one in after.items] != [("file", document), ("thread", thread)]:
        raise CheckFailedError(LEFT_THE_LIST)

    # Taking something out and putting the project away are never behind the switch; away or with
    # the switch off, nothing is read.
    await switched(False, 3)
    if await following(owner, Question(question="x", project=project_id)) is not None:
        raise CheckFailedError(STILL_READ_WITH_SWITCH_OFF)
    taken = await take_out_of_my_project(
        _request(app), project_id, ItemAsked(kind="thread", ref=thread), await asked(owner)
    )
    renamed = await rename_my_project(
        _request(app), project_id, NameAsked(name="Tidied"), await asked(owner)
    )
    if (
        getattr(taken, "project_id", "") != project_id
        or getattr(renamed, "project_id", "") != project_id
    ):
        raise CheckFailedError(TRAPPED_BY_THE_SWITCH)
    await switched(True, 4)
    if await following(owner, Question(question="x", project=project_id)) is None:
        raise CheckFailedError(NOT_BROUGHT)
    # The conversation goes back in, so a question that only continues it is the one asked below.
    await add_to_my_project(
        _request(app), project_id, ItemAsked(kind="thread", ref=thread), await asked(owner)
    )
    continued = await following(owner, Question(question="x", thread=thread))
    if continued is None or continued.project_files != (document,):
        raise CheckFailedError(NOT_BROUGHT)
    await put_my_project_away(_request(app), project_id, await asked(owner))
    for ask in (Question(question="x", project=project_id), Question(question="x", thread=thread)):
        brought = await following(owner, ask)
        if brought is not None and brought.project_files:
            raise CheckFailedError(STILL_READ_AFTER_AWAY)
    if project_id in await listed(owner):
        raise CheckFailedError(STILL_READ_AFTER_AWAY)
    # A project put away takes nothing more and cannot be put away twice.
    if not await _refused(
        add_to_my_project(
            _request(app), project_id, ItemAsked(kind="thread", ref=thread), await asked(owner)
        )
    ) or not await _refused(put_my_project_away(_request(app), project_id, await asked(owner))):
        raise CheckFailedError(AWAY_BUT_STILL_CHANGED)

    # The most projects a person keeps is a limit in words, and putting one away makes room.
    from brain.member_projects import MOST_PROJECTS

    for number in range(MOST_PROJECTS):
        shelf = await make_my_project(
            _request(app), NameAsked(name=f"P{number}"), await asked(owner)
        )
        if not getattr(shelf, "project_id", ""):
            raise CheckFailedError(FULL_SHELF_NOT_SAID)
    over = await make_my_project(_request(app), NameAsked(name="Over"), await asked(owner))
    if _status(over) != 422:
        raise CheckFailedError(FULL_SHELF_NOT_SAID)
    first = (await my_projects(_request(app), await asked(owner))).projects[0].project_id
    await put_my_project_away(_request(app), first, await asked(owner))
    again = await make_my_project(_request(app), NameAsked(name="Room"), await asked(owner))
    if not getattr(again, "project_id", ""):
        raise CheckFailedError(FULL_SHELF_NOT_SAID)

    # Never memory: the person's two memory tables hold nothing from any of this.
    for held_by in (PersistentMemoryRow, AdaptiveMemoryRow):
        held = (
            await h.execute(
                select(func.count()).select_from(held_by).where(held_by.principal_id == owner)
            )
        ).scalar_one()
        if cast("int", held):
            raise CheckFailedError(BECAME_MEMORY)
