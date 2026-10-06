"""Two role surfaces proved on an install: a person's own allowance, and an auditor's history.

M33 asks for a surface per role, and most of what it names is a decision in `brain.console` that no
route reaches yet (`brain.console.global_surfaces`, `brain.console.scoped_authority`). Two of its
leaves are on a page today and are proved here, each through the route its console page calls, as
the reader that page is for: `brain.mine_routes.workspace`, which My workspace reads, as a person
holding exactly the member grant a sign-in binding writes; and `brain.audit_routes.audit_history`,
which the Activity screen's subject page reads, as an auditor holding the Activity screen and every
audit noun. Every row is written in the check's rolled-back transaction, in acceptance_a, by and
about reserved principals.

**A person's allowance is appended through the one budget writer the product has.** No route
writes a person's allowance yet: `brain.agent_workspace_routes` sets an agent's, and the four-level
budget screen is M21's. So the check appends the person's ceilings through
`brain.ops.budget_store.append`, the verb that agent route writes through, whose `0098` trigger
records the change, and then reads them back only through the workspace route. Rejected: inserting
`ops.budget_version` rows by hand, which would prove the reader against a row no writer of the
product could have produced. What this check does not prove is that anybody can set the allowance
from a screen; see `NO_SCREEN_SETS_A_PERSONS_ALLOWANCE_YET`.

**A leash is moved by the one statement the ledger's trigger watches, because nothing else moves
one.** `brain.ops.acceptance_audit` found the same absence and answered it the same way: no route
changes `guardrails.leash`, so the check raises and lowers a target on its own agent with the
UPDATE `0104`'s trigger turns into a `leash_change` entry, attributed as a console request is. A
grant is written and taken away by `brain.govern_routes.add_grant` and `retire_grant`, the two
statements the People screen's grant and removal run.

**Order is not asserted, and the reason is the transaction rather than the route.** Every ledger
entry a trigger writes is stamped `now()`, which is the start of the transaction, and a check is one
transaction; so every entry the check causes has the same instant and the route's oldest-first
order is a tie the entry digest breaks. What is asserted is that each change is there, once, with
its actor and its rungs. See `ONE_TRANSACTION_STAMPS_EVERY_ENTRY_WITH_ONE_INSTANT`.

**The narrower reader is a department head's audit reach**, `actor_id IN (their people)`, the shape
`brain.identity.staff_sync.audit_reach_for_head` writes, over people who did none of the changes.
They hold the Activity screen and every audit noun, so the only thing standing between them and
the history is the scope, and what they are shown has to be exactly what a subject with no history
shows: DENIED and ABSENT are one answer.

Task ids: M38.5.1
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import insert, text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.mine_routes import MineWorkspaceView

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 442

A: Final = RESERVED_DEPARTMENTS[0]

# ------------------------------------------------------------------ written-down reasons
#: What the allowance check leaves unproved, said where the next reader of it looks.
NO_SCREEN_SETS_A_PERSONS_ALLOWANCE_YET: Final = (
    "A person's daily and monthly allowance has no writer on a screen: the agent budget route "
    "writes an agent's and nothing writes a person's. The check appends the person's ceilings "
    "through brain.ops.budget_store.append, the verb that route writes through, and proves what "
    "My workspace shows of them; until a screen sets one, an install's people all read that no "
    "budget of their own is set."
)

#: Why the history check asserts each change and not their order.
ONE_TRANSACTION_STAMPS_EVERY_ENTRY_WITH_ONE_INSTANT: Final = (
    "A ledger trigger stamps its entry now(), the start of its transaction, and a check is one "
    "transaction, so every entry the check causes carries the same instant and oldest-first is a "
    "tie the entry digest breaks. The check asserts that each change is in the history once, by "
    "its actor and with its rungs, and leaves the order to the requests that make changes apart."
)

# ------------------------------------------------------------------------ the figures
#: The member's daily and monthly ceilings, the alert fraction on each, and what they spend today.
MEMBER_DAY: Final = (400, 0.5)
MEMBER_MONTH: Final = (1000, 0.25)
MEMBER_SPENT: Final = 300

#: A colleague's ceilings and spend, each different from the member's so a mix-up shows.
COLLEAGUE_DAY: Final = 4000
COLLEAGUE_MONTH: Final = 7000
COLLEAGUE_SPENT: Final = 500

#: The capability the subject is granted and then has taken away.
GRANTED: Final = "read:knowledge"

#: The leash rungs `0104`'s trigger names, by `AutonomyTier` value.
SHADOW, ASSISTED = 0, 1

# ----------------------------------------------------------------------------- sentences
NOT_SHOWN: Final = "a person's own allowance was withheld from their workspace"
NOT_THEIR_ALLOWANCE: Final = "the allowance on a person's workspace was not the one set for them"
COUNTED_SOMEBODY_ELSES: Final = "a colleague's spend was counted against a person's own allowance"
NOT_COUNTED: Final = "what a person spent today was not counted against their own allowance"
HEADROOM_WRONG: Final = "the headroom or the alerts crossed did not follow from the allowance"
NONE_SET_NOT_SAID: Final = "a person with no allowance was not told that none is set"
SHOWN_WITHOUT_THE_MEMBER_GRANT: Final = "a workspace was shown to somebody without the member grant"

GRANT_HISTORY_INCOMPLETE: Final = (
    "a grant's history did not hold it being given and taken away, each by the person who did it"
)
LEASH_HISTORY_INCOMPLETE: Final = (
    "an agent's history did not hold its leash raised and lowered, with the rungs, by who moved it"
)
SHOWN_PAST_REACH: Final = (
    "a reader whose audit reach does not cover a change was told something a subject with no "
    "history does not tell"
)
SHOWN_WITHOUT_THE_SCREEN: Final = "a history was shown to somebody without the Activity screen"


# ------------------------------------------------------------------------ the wiring
def _app(h: Harness) -> FastAPI:
    from fastapi import FastAPI

    app = FastAPI()
    app.state.db_sessions = h.sessions
    return app


def _request(app: FastAPI) -> Any:
    from starlette.requests import Request

    return Request({"type": "http", "app": app, "headers": [], "method": "GET"})


async def _asking(h: Harness, principal_id: str) -> Any:
    """The caller a route is handed for this reserved person, signed in strongly at the console."""
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.STRONG)
    # A cast at the routes' boundary, as `acceptance_checks_review._reader` makes it.
    return cast(
        Any,
        SimpleNamespace(caller=SimpleNamespace(principal=person), reach=reach, now=h.now),
    )


# --------------------------------------------------- M33.3.1.5 usage against allowance
def _spend(principal_id: str, cost: int, at: datetime, trace: str) -> dict[str, Any]:
    """A run's cost as `brain.ops.usage_store` records one, made by this person at a console."""
    from brain.core.lane import Lane
    from brain.gate.context import TrafficClass

    return {
        "principal_id": principal_id,
        "principal_kind": "human",
        "traffic": TrafficClass.HUMAN_INTERACTIVE.value,
        "department": A,
        "agent_id": None,
        "model": "acceptance-model",
        "lane": Lane.ANSWER.value,
        "cost_minor": cost,
        "at": at,
        "trace_id": trace,
    }


def _ceiling(
    who: str, period: Any, ceiling: int, alerts: tuple[float, ...], by: str, at: datetime
) -> Any:
    from brain.ops.budgets import BudgetLevel, BudgetRow

    return BudgetRow(
        level=BudgetLevel.USER,
        subject=who,
        period=period,
        ceiling_minor=ceiling,
        version=1,
        author=by,
        effective_from=at,
        reason="Set by an install acceptance check",
        alert_fractions=alerts,
    )


def _held_to(page: MineWorkspaceView, ceilings: dict[str, int], spent: int) -> None:
    """Fail unless this page's budget card is exactly these ceilings, `spent` against each."""
    if page.budget is None:
        raise CheckFailedError(NOT_SHOWN)
    if {one.period: one.ceiling_minor for one in page.budget} != ceilings:
        raise CheckFailedError(NOT_THEIR_ALLOWANCE)
    if any(one.spent_minor > spent for one in page.budget):
        raise CheckFailedError(COUNTED_SOMEBODY_ELSES)
    if any(one.spent_minor != spent for one in page.budget):
        raise CheckFailedError(NOT_COUNTED)
    if any(one.headroom_minor != one.ceiling_minor - spent for one in page.budget):
        raise CheckFailedError(HEADROOM_WRONG)


@check(
    leaves=("M33.3.1.5",),
    sentence=(
        "A person on My workspace is shown their own daily and monthly allowance with what they "
        "spent today against each, the headroom left and the alerts crossed, and never a "
        "colleague's allowance or spend; a person with no allowance is told none is set, and "
        "somebody without the member grant is refused the page."
    ),
)
async def a_person_sees_their_own_spend_against_their_own_allowance(h: Harness) -> None:
    from brain.console.own_things import own_scope
    from brain.core.errors import Absent
    from brain.identity.sign_in_binding import MEMBER_SURFACE
    from brain.mine_routes import workspace
    from brain.ops.budget_store import append
    from brain.ops.budgets import BudgetPeriod
    from brain.tables.spend import SpendActualRow

    await h.found_departments()
    member, colleague, unset, outsider, setter = (
        h.principal(A, role) for role in ("member", "colleague", "unset", "outsider", "setter")
    )
    for one in (member, colleague, unset):
        # The grant a sign-in binding writes: the member surface over their own things.
        await h.person(one, department=A, grants=((MEMBER_SURFACE.value, own_scope(one)),))
    for one in (outsider, setter):
        await h.person(one, department=A)

    since = h.now - timedelta(seconds=1)
    setter_reach = await h.reach(setter)
    async with h.sessions() as session:
        await session.execute(
            insert(SpendActualRow),
            [
                _spend(member, MEMBER_SPENT, h.now, f"{h.trace_id}-s1"),
                _spend(colleague, COLLEAGUE_SPENT, h.now, f"{h.trace_id}-s2"),
            ],
        )
        for who, period, ceiling, alerts in (
            (member, BudgetPeriod.DAY, MEMBER_DAY[0], (MEMBER_DAY[1],)),
            (member, BudgetPeriod.MONTH, MEMBER_MONTH[0], (MEMBER_MONTH[1],)),
            (colleague, BudgetPeriod.DAY, COLLEAGUE_DAY, ()),
            (colleague, BudgetPeriod.MONTH, COLLEAGUE_MONTH, ()),
        ):
            await append(
                session,
                _ceiling(who, period, ceiling, alerts, setter, since),
                ent_hash=setter_reach.ent_hash(),
                trace_id=h.trace_id,
            )
        await session.commit()

    app = _app(h)
    mine = await workspace(_request(app), await _asking(h, member))
    theirs = await workspace(_request(app), await _asking(h, colleague))
    nothing = await workspace(_request(app), await _asking(h, unset))

    day, month = BudgetPeriod.DAY.value, BudgetPeriod.MONTH.value
    _held_to(mine, {day: MEMBER_DAY[0], month: MEMBER_MONTH[0]}, MEMBER_SPENT)
    _held_to(theirs, {day: COLLEAGUE_DAY, month: COLLEAGUE_MONTH}, COLLEAGUE_SPENT)
    assert mine.budget is not None
    crossed = {one.period: one.alerts_crossed for one in mine.budget}
    if crossed != {day: [MEMBER_DAY[1]], month: [MEMBER_MONTH[1]]}:
        raise CheckFailedError(HEADROOM_WRONG)
    if nothing.budget != [] or nothing.budget_unread:
        raise CheckFailedError(NONE_SET_NOT_SAID)
    try:
        await workspace(_request(app), await _asking(h, outsider))
    except Absent:
        pass
    else:
        raise CheckFailedError(SHOWN_WITHOUT_THE_MEMBER_GRANT)


# ------------------------------------------------------ M33.4.1.2 grant and leash history
async def _leash_set(h: Harness, admin: str, agent_id: str, target: str, rung: int) -> None:
    """One target of the check's own agent set to `rung`, as an operator's statement sets it."""
    before = (
        await h.execute(
            text(
                "SELECT effective_document -> 'guardrails.leash' FROM agent.template_instance"
                " WHERE id = :agent"
            ).bindparams(agent=agent_id)
        )
    ).scalar_one_or_none()
    rungs = [
        *(
            one
            for one in (before if isinstance(before, list) else [])
            if one.get("target") != target
        ),
        {"target": target, "scope": Scope().model_dump(mode="json"), "rung": rung},
    ]
    await h.execute(
        *h.attributed(admin),
        text(
            "UPDATE agent.template_instance SET effective_document ="
            " jsonb_set(effective_document, '{guardrails.leash}', CAST(:rungs AS jsonb))"
            " WHERE id = :agent"
        ).bindparams(rungs=json.dumps(rungs), agent=agent_id),
    )


@check(
    leaves=("M33.4.1.2",),
    sentence=(
        "An auditor opening a grant from the Activity screen is shown it given and taken away, "
        "and opening an agent is shown its leash raised and lowered with the rungs, each by who "
        "did it; a reader whose audit reach does not cover them is shown what a subject with no "
        "history shows, and somebody without the Activity screen is refused."
    ),
)
async def an_auditor_reads_a_grants_and_an_agents_leash_history(h: Harness) -> None:
    from brain.audit.ledger import AuditAction
    from brain.audit.view import CAPABILITY_BY_KIND
    from brain.audit_routes import audit_history
    from brain.console.reads import plane_capability_for
    from brain.console.screens import screen
    from brain.core.entitlement import Capability
    from brain.core.errors import Absent
    from brain.core.scope import Clause, Op
    from brain.govern_routes import add_grant, retire_grant
    from brain.identity.packs import SubjectGrant
    from brain.identity.staff_sync import ACTOR_FIELD
    from brain.identity.teams import PrincipalSubject
    from brain.ops.acceptance_workspace import installed_agent
    from brain.tables.audit import attributed_to

    await h.found_departments()
    admin, subject, auditor, head, member = (
        h.principal(A, role) for role in ("admin", "subject", "auditor", "head", "member")
    )
    for one in (admin, subject, member):
        await h.person(one, department=A)
    read = screen("audit").read
    everywhere = Scope.unrestricted()
    opens = (
        (read.requires.value, everywhere),
        (plane_capability_for(read, read.plane).value, everywhere),
    )
    nouns = tuple(one.value for one in CAPABILITY_BY_KIND.values())
    await h.person(auditor, department=A, grants=(*opens, *((one, everywhere) for one in nouns)))
    # A head's audit reach: every noun, over the people of their department who changed nothing.
    theirs = Scope(clauses=(Clause(field=ACTOR_FIELD, op=Op.IN, value=(member,)),))
    await h.person(head, department=A, grants=(*opens, *((one, theirs) for one in nouns)))

    # A grant given and taken away, by the statements the People screen runs.
    reach = await h.reach(admin)
    attributed = attributed_to(actor_id=admin, ent_hash=reach.ent_hash(), trace_id=h.trace_id)
    async with h.sessions() as session:
        for statement in attributed:
            await session.execute(statement)
        given = await session.execute(
            add_grant(
                SubjectGrant(
                    subject=PrincipalSubject(principal_id=subject),
                    capability=Capability(value=GRANTED),
                    scope=Scope.department(A),
                    granted_by=admin,
                    reason="Granted by an install acceptance check for the length of the check",
                    granted_at=h.now,
                    not_after=h.now + timedelta(hours=1),
                ),
                principal_id=subject,
            )
        )
        grant_id = str(given.scalar_one().id)
        await session.execute(retire_grant(subject, GRANTED))
        await session.commit()

    # A leash raised and lowered on the check's own agent.
    agent_id = await installed_agent(h, admin)
    target = f"acceptance_{h.run}"
    await _leash_set(h, admin, agent_id, target, ASSISTED)
    await _leash_set(h, admin, agent_id, target, SHADOW)

    app = _app(h)
    by_auditor, by_head = await _asking(h, auditor), await _asking(h, head)
    granted = await audit_history(_request(app), by_auditor, "grant", grant_id)
    if sorted((one.action.value, one.actor_id) for one in granted.events) != sorted(
        ((AuditAction.GRANT.value, admin), (AuditAction.REVOKE.value, admin))
    ):
        raise CheckFailedError(GRANT_HISTORY_INCOMPLETE)
    leashed = await audit_history(_request(app), by_auditor, "agent", agent_id)
    moves = sorted(
        (one.details.get("target"), one.details.get("from_rung"), one.details.get("to_rung"))
        for one in leashed.events
        if one.action is AuditAction.LEASH_CHANGE and one.actor_id == admin
    )
    if moves != sorted(((target, "shadow", "assisted"), (target, "assisted", "shadow"))):
        raise CheckFailedError(LEASH_HISTORY_INCOMPLETE)

    nobody_grant = str(uuid.uuid4())
    nobody_agent = f"acceptance_{h.run}_none"
    for kind, real, absent in (
        ("grant", grant_id, nobody_grant),
        ("agent", agent_id, nobody_agent),
    ):
        denied = await audit_history(_request(app), by_head, kind, real)
        missing = await audit_history(_request(app), by_auditor, kind, absent)
        if denied.model_dump(exclude={"subject_id"}) != missing.model_dump(exclude={"subject_id"}):
            raise CheckFailedError(SHOWN_PAST_REACH)

    try:
        await audit_history(_request(app), await _asking(h, member), "grant", grant_id)
    except Absent:
        pass
    else:
        raise CheckFailedError(SHOWN_WITHOUT_THE_SCREEN)
