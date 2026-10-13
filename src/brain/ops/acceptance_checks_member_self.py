"""Install acceptance checks for the member's own application: signing in, what a member is shown,
and what they are never shown.

M40 is the application a person who administers nothing uses. Most of its leaves were written as
functions in `brain.member`, `brain.member_activity` and `brain.member_library`, and the behaviour
they describe is served by routes that never call them: `GET /me`, `GET /console/navigation`,
`GET /me/workspace`, `GET /me/accounts` and the Knowledge lifecycle's own list. **So every check
here calls the route a page calls, as a member who signed in through the install's own gate**
(`brain.ops.acceptance_people_signed_in`), and a leaf is named by the route that serves it rather
than by the dead function that carries its id. Rejected: calling `brain.member.shell` and
`member_activity`, which is a check of a function nothing on the install reads.

**A member here holds exactly the grant a sign-in writes and nothing else.** The person is
reserved, and the member surface over their own things is what `SignInBindings.bind` gives them
on the first request; a check that gave a member an administrator's grants would prove the refusal
of nothing.

**Every refusal is asked beside the act that succeeds.** The menu a member is given is empty and
an administrator's is not, a member is refused the governance routes and an administrator in the
same department is not, a colleague is not shown a document the author is, and an agent a person
used twice is counted twice for them and for nobody else. A guard asked only for its refusal is
satisfied by a product that refuses everything.

**What is not proved here, and why.** M40.1.2.3 (a phone-width page) needs a browser, so its proof
is a console test. M40.7.4 is a person's walk through the application on the install.

Task ids: M40.1.1.1, M40.1.1.5, M40.1.2.1, M40.1.2.2, M40.1.2.4, M40.2.2.1
Task ids: M40.3.1.1, M40.3.1.5, M40.5.1.2, M40.6.1.1
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert, update

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import traced
from brain.ops.acceptance_people_signed_in import administrator, console, everywhere, within
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.ops.acceptance_people_signed_in import Console

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1900

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why every reader here signs in with a token and is not handed an `Asking`.
A_MEMBER_SIGNS_IN_THROUGH_THE_INSTALLS_OWN_GATE: Final = (
    "Each reader presents a token signed with a key the check made, which the install's own "
    "verifier accepts, so who is asking and at what reach is decided by the gate and not by "
    "the check. A reader built by hand would prove the screens against somebody the install can "
    "never produce."
)

# ------------------------------------------------------------------------ the figures
#: How many times the person used the agent, and how many times a colleague did.
USED_BY_THE_PERSON: Final = 2
USED_BY_A_COLLEAGUE: Final = 3

#: The authority a Features screen's reader holds, restated so a change to the route fails here.
SWITCHES_FEATURES: Final = "admin:feature"

#: The chat channel the busy agent is switched on for, beside the console.
WHERE_IT_RUNS: Final = "lark"

#: How far ahead a document's review date lies.
REVIEW_AHEAD: Final = timedelta(days=180)

#: What the member's own page says about connecting an account, in the words that matter.
CONNECTING_NEVER_WIDENS: Final = "never widens what you can see"


# ------------------------------------------------------------------------ the helpers
async def _refused(call: Any) -> bool:
    """Whether a route call was answered with the one refusal, `Absent`, and nothing else."""
    from brain.core.errors import Absent

    try:
        await call
    except Absent:
        return True
    return False


async def _member(h: Harness, c: Console, role: str, department: str = A) -> str:
    """A reserved person holding nothing a sign-in does not write, and the first sign-in made."""
    person = h.principal(department, role)
    await h.person(person, department=department)
    await c.asked(person, strong=False)
    return person


async def _workspace_of(h: Harness, c: Console, who: str) -> Any:
    """`GET /me/workspace` as `who` signed in, read as a request's own transaction reads it."""
    from sqlalchemy import func, select

    from brain.knowledge.search import PRINCIPAL_SETTING
    from brain.mine_routes import workspace

    asked = await c.asked(who, strong=False)
    # The check's transaction names the reader to the database while it resolves their reach,
    # which a request's own transaction is never told until the route tells it. Cleared first, so
    # that what the route finds is what the route named.
    await h.execute(select(func.set_config(PRINCIPAL_SETTING, "", True)))
    with c.as_route():
        return await workspace(c.request(), asked)


# ------------------------------------------------- 1. one person on the web and in chat (M40.1.1)
@check(
    leaves=("M40.1.1.1", "M40.1.1.5"),
    sentence=(
        "A person whose Lark account was bound from a code minted in their sign-in signs in "
        "again on the web with a token the install's gate verifies: it names the same person "
        "the chat account is bound to, at the same reach the chat account resolves to, and a "
        "second person's token names the second person."
    ),
)
async def a_person_known_in_chat_signs_in_on_the_web_as_that_one_person(h: Harness) -> None:
    from brain.api_routes import me
    from brain.binding_routes import binding_codes_of
    from brain.channels.binding import mint_code
    from brain.channels.inbound import LINKED_TOLD
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.ops.acceptance_checks import _in
    from brain.ops.acceptance_checks_channel_framework import (
        _bound_to,
        _member_surface,
        _sent_alone,
        _signed_in,
    )
    from brain.ops.acceptance_checks_chat import lark_app, open_id

    await h.found_departments()
    chat = await lark_app(h)
    person, other = h.principal(A, "chat_first"), h.principal(A, "web_only")
    for one in (person, other):
        await h.person(one, department=A, grants=_in(A, _member_surface()))
    session = await _signed_in(h, person, f"acceptance-{h.run}-member-chat", h.now)
    minted = await mint_code(
        session, Channel.LARK, now=h.now, codes=binding_codes_of(chat.request())
    )
    sender = open_id()
    if await _sent_alone(chat, sender, minted.nonce.value) != [LINKED_TOLD]:
        raise CheckFailedError(
            "a code minted in a person's sign-in did not bind their chat account"
        )
    bound = await _bound_to(h, sender)

    c = await console(h)
    with c.as_route():
        theirs = await me(await c.asked(person, strong=False))
        others = await me(await c.asked(other, strong=False))
    if bound != person or theirs.principal_id != bound:
        raise CheckFailedError("a person's chat account and their web sign-in were not one person")
    if others.principal_id != other or others.principal_id == theirs.principal_id:
        raise CheckFailedError("a second person's web sign-in did not name the second person")
    at_console = admit(await h.reach(bound), Channel.CONSOLE, Assurance.AUTHENTICATED)
    if theirs.ent_hash != at_console.ent_hash():
        raise CheckFailedError("a person signing in on the web did not hold what chat resolves to")


# -------------------------------------------------------- 2. a short menu, no governance (M40.1.2)
@check(
    leaves=("M40.1.2.1", "M40.1.2.2"),
    sentence=(
        "A member who administers nothing is given a console with no menu entries, where an "
        "administrator of the same department is given one with entries; the same member is "
        "refused, with the one refusal, a job's pause, a feature's switch and a grant, which "
        "the administrator is not refused."
    ),
)
async def a_member_is_given_no_governance_menu_and_no_governance_route(h: Harness) -> None:
    from brain.feature_routes import SwitchAsked, switch_feature
    from brain.govern_routes import GrantProposal, grant
    from brain.jobs_routes import pause_job
    from brain.navigation_routes import console_navigation
    from brain.ops.acceptance_operations_console_2 import a_job
    from brain.ops.features import SCHEDULE_CONTROL

    await h.found_departments()
    c = await console(h)
    member = await _member(h, c, "member")
    admin = h.principal(A, "admin")
    # The feature switch is held over the whole install, as the Features screen asks it.
    others = [one for one in administrator() if one != SWITCHES_FEATURES]
    await h.person(
        admin,
        department=A,
        grants=(*within(A, *others), *everywhere(SWITCHES_FEATURES)),
    )

    def entries(page: Any) -> int:
        return sum(len(section.entries) for section in page.sections)

    with c.as_route():
        small = await console_navigation(await c.asked(member, strong=False))
        large = await console_navigation(await c.asked(admin))
    if entries(small) != 0 or small.stop:
        raise CheckFailedError("a member who administers nothing was given a governance menu")
    if entries(large) == 0:
        raise CheckFailedError(
            "an administrator was given an empty menu, so a member's proves nothing"
        )

    job = a_job().name
    weak = await c.asked(member, strong=False)
    strong = await c.asked(admin)
    with c.as_route():
        refused = [
            await _refused(pause_job(c.request("POST"), job, weak)),
            await _refused(
                switch_feature(c.request("POST"), SCHEDULE_CONTROL.name, SwitchAsked(on=True), weak)
            ),
            await _refused(
                grant(
                    c.request("POST"),
                    GrantProposal(
                        principal_id=member,
                        capability="read:document",
                        scope_slug=A,
                        reason="Asked by an install acceptance check",
                        not_after=h.now + timedelta(minutes=30),
                    ),
                    weak,
                )
            ),
        ]
    if not all(refused):
        raise CheckFailedError("a member was not refused a governance route they asked for by URL")
    async with traced(h, 1):
        with c.as_route():
            switched = await switch_feature(
                c.request("POST"), SCHEDULE_CONTROL.name, SwitchAsked(on=True), strong
            )
    if not switched.on:
        raise CheckFailedError("an administrator could not do what a member was refused")


# ------------------------------------------------------ 3. what is said about reach (M40.1.2.4)
@check(
    leaves=("M40.1.2.4", "M40.5.1.2"),
    sentence=(
        "My workspace says what a person may ask about from their own grants and not from "
        "words written by hand: a person holding a department's reads and one holding nothing "
        "are told different lines, and each says that connecting an account never widens what "
        "they can see, which the account list carries as well."
    ),
)
async def the_workspace_line_follows_grants_and_connecting_widens_nothing(
    h: Harness,
) -> None:
    from brain.connector_routes import my_accounts
    from brain.member.connections import connection_gaps
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in

    await h.found_departments()
    c = await console(h)
    wide, narrow = h.principal(A, "wide"), h.principal(A, "narrow")
    await h.person(wide, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(narrow, department=A)
    first = await _workspace_of(h, c, wide)
    second = await _workspace_of(h, c, narrow)
    if not first.can_ask_about or first.can_ask_about == second.can_ask_about:
        raise CheckFailedError("two people with different grants were told the same line")
    for page in (first, second):
        if CONNECTING_NEVER_WIDENS not in page.accounts:
            raise CheckFailedError("My workspace did not say that connecting never widens reach")
    with c.as_route():
        listed = await my_accounts(c.request(), await c.asked(wide, strong=False))
    if CONNECTING_NEVER_WIDENS not in listed.told and "never for anybody else's" not in listed.told:
        raise CheckFailedError("the account list did not say what connecting an account does")
    if connection_gaps():
        raise CheckFailedError("a connection could carry a capability into somebody's reach")


# ------------------------------------------------ 4. each agent, where it runs, used (M40.2.2.1)
@check(
    leaves=("M40.2.2.1",),
    sentence=(
        "A person who ran an agent twice is shown it with a count of two and where it runs, an "
        "agent they never ran with none, and a colleague's three runs of the first are counted "
        "for the colleague and not for them."
    ),
)
async def each_agent_shows_where_it_runs_and_how_often_the_person_used_it(
    h: Harness,
) -> None:
    from brain.ops.acceptance_checks_role_surfaces import _spend
    from brain.ops.acceptance_workspace import installed_agent
    from brain.tables.agent import AgentRow
    from brain.tables.spend import SpendActualRow

    await h.found_departments()
    c = await console(h)
    person, colleague = await _member(h, c, "used"), await _member(h, c, "colleague")
    busy = await installed_agent(h, person, suffix="_busy")
    idle = await installed_agent(h, person, suffix="_idle")
    runs = [
        *(_spend(person, 1, h.now, f"{h.trace_id}-p{n}") for n in range(USED_BY_THE_PERSON)),
        *(_spend(colleague, 1, h.now, f"{h.trace_id}-c{n}") for n in range(USED_BY_A_COLLEAGUE)),
    ]
    async with h.sessions() as session:
        await session.execute(insert(SpendActualRow), [{**one, "agent_id": busy} for one in runs])
        await session.commit()
    # Switched on for the one chat channel, beside the console it was installed on: a console is
    # not a chat channel, so it is the chat channels an agent is listed as running on.
    await h.execute(
        *h.attributed(person),
        update(AgentRow).where(AgentRow.id == busy).values(channels=["console", WHERE_IT_RUNS]),
    )

    mine = {one.agent_id: one for one in (await _workspace_of(h, c, person)).agents}
    theirs = {one.agent_id: one for one in (await _workspace_of(h, c, colleague)).agents}
    if busy not in mine or idle not in mine:
        raise CheckFailedError("an agent a person may call was not listed for them")
    if mine[busy].uses != USED_BY_THE_PERSON or mine[idle].uses != 0:
        raise CheckFailedError("a person was not told how often they themselves used each agent")
    if theirs[busy].uses != USED_BY_A_COLLEAGUE:
        raise CheckFailedError("a colleague's runs were counted for somebody else")
    if mine[busy].channels != [WHERE_IT_RUNS] or mine[idle].channels:
        raise CheckFailedError("an agent was not listed with where it runs, or the wrong one was")


# ------------------------------------------- 5. a member's own documents (M40.3.1.1, M40.3.1.5)
@check(
    leaves=("M40.3.1.1", "M40.3.1.5"),
    sentence=(
        "A member who added a document and verified it with a review date ahead finds it on their "
        "own list with that date, its verification and nothing due; a colleague of the same "
        "department who added one for themselves alone finds theirs and not the first member's, "
        "and a person in another department is shown nothing of either."
    ),
)
async def a_member_s_documents_show_their_review_and_no_colleague_s(h: Harness) -> None:
    from brain.knowledge.ingest import MediaType
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.knowledge.visibility import Visibility
    from brain.knowledge_lifecycle_routes import looked_after
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _upload
    from brain.ops.acceptance_checks_lifecycle import FILE_NAME, _added, _as, _body, _verify

    await h.found_departments()
    c = await console(h)
    author, colleague = h.principal(A, "author"), h.principal(A, "neighbour")
    elsewhere = h.principal(B, "elsewhere")
    for one, where in ((author, A), (colleague, A), (elsewhere, B)):
        await h.person(
            one, department=where, grants=_in(where, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value)
        )
    theirs = await _added(h, author, h.word())
    review = h.now + REVIEW_AHEAD
    if await _verify(h, await _as(h, author), theirs, review_by=review) is None:
        raise CheckFailedError("an author could not verify their own document with a review date")
    read = await _upload(
        h,
        colleague,
        filename=FILE_NAME,
        declared=MediaType.MARKDOWN.value,
        body=_body(h.word()),
        level=Visibility.PERSONAL,
    )
    item = getattr(read, "item", None)
    if item is None:
        raise CheckFailedError("a colleague could not add a document for themselves alone")
    neighbours = str(item.item_id)

    async def listed(who: str) -> dict[str, Any]:
        asked = await c.asked(who, strong=False)
        with c.as_route():
            page = await looked_after(c.request(), asked)
        return {one.item_id: one for one in page.items}

    mine, neighbour, away = await listed(author), await listed(colleague), await listed(elsewhere)
    row = mine.get(theirs)
    if row is None or row.review_by is None or row.due or row.verified_at is None:
        raise CheckFailedError("an author's own document did not show its review date and standing")
    if abs(row.review_by - review) > timedelta(seconds=1):
        raise CheckFailedError("a document showed a review date other than the one it was set to")
    if neighbours in mine or theirs in neighbour or neighbours not in neighbour:
        raise CheckFailedError("a member's list held a colleague's document, or lost their own")
    if away:
        raise CheckFailedError("a person in another department was shown a document of this one")


# ------------------------------------------- 6. an approval says what will happen (M40.6.1.1)
@check(
    leaves=("M40.6.1.1",),
    sentence=(
        "An action held for a person is on its approver's list before anything has happened, with "
        "the request in words, who it runs as and when it lapses, and an approver of another "
        "department is shown nothing."
    ),
)
async def an_approval_says_what_will_happen_before_it_is_decided(h: Harness) -> None:
    from brain.approval_routes import approvals
    from brain.gate.suspension_store import StoredSuspensions
    from brain.listing import ListAsked
    from brain.ops.acceptance_checks_console_approvals import ACTION_CAPABILITY, _held

    await h.found_departments()
    c = await console(h)
    asker, approver, elsewhere = (
        h.principal(A, "asker"),
        h.principal(A, "approver"),
        h.principal(B, "other"),
    )
    await h.person(asker, department=A, grants=within(A, ACTION_CAPABILITY))
    for one, where in ((approver, A), (elsewhere, B)):
        await h.person(
            one, department=where, grants=within(where, ACTION_CAPABILITY, "approve:action")
        )
    agent = f"acceptance_{h.run}_member_agent"
    waiting = await _held(h, asker, agent, 1)
    c.app.state.suspensions = StoredSuspensions(h.sessions)

    async def queued(who: str) -> dict[str, Any]:
        asked = await c.asked(who)
        with c.as_route():
            page = await approvals(c.request(), asked, ListAsked(limit=200))
        return {one.suspension_id: one for one in page.items}

    theirs, away = await queued(approver), await queued(elsewhere)
    card = theirs.get(waiting)
    if card is None:
        raise CheckFailedError("an action held for a person was not on its approver's list")
    if not card.request.strip() or card.runs_as != asker or card.expires_at <= card.raised_at:
        raise CheckFailedError(
            "an approval did not say what it was, who it ran as and when it ends"
        )
    if waiting in away:
        raise CheckFailedError("an approver of another department was shown an approval")
