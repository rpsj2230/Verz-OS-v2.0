"""Install acceptance check: the card for a browser write says what changed since the last run a
person approved, and compares only with what was approved.

**What this joins.** `approval.envelope_changes` is a pure function over two sets of sealed parts,
and `envelope_store.last_approved_parts` reads a row. The claim is the whole path on the install's
own database: `driver.prepare_run` compiles an envelope, looks up the asker's last approved
envelope for this agent and website, raises the card with the difference in it, and a second
person's approval of a run is what the next card is compared with. Eight runs over two made-up
websites:

- **The first card says it is the first approval** (M19.7.2, M19.9.2).
- **An approved run is what the next is compared with:** a repeat says nothing differs, and a run
  with one more write says which.
- **A run nobody approved is not what is compared with:** a second run with the extra write, raised
  while the first is still pending, is compared with the approved one and not with the pending one.
- **Another person's, agent's and website's history is not mine:** a different asker's, a
  different agent's and a different website's first card says it is the first.
- **The latest approved run is the one compared with**, not an older one.

Each card is read back as the approver is shown it (`brain.console.approvals.card`), so what is
checked is what a person deciding is shown and not the requester's own rendering. The approval is
by a second reserved person through the approvals route's own function (`take_decision`), as
`acceptance_checks_browser` does.

The check writes under reserved principals and rolls nothing back by hand: the harness leaves no
row it did not own, and the test file holds that.

Task ids: M19.7.2, M19.9.2
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's check stands on the Install page, after the credential check's (2308).
CHECK_ORDER: Final = 2309

A, _B = RESERVED_DEPARTMENTS

#: The origin the check's made-up website allows. `.invalid` is reserved and never resolves.
ORIGIN: Final = "https://acceptance-check.invalid"

THE_FIRST_CARD_WAS_NOT_THE_FIRST: Final = (
    "the card for the first write of an agent on a website did not say it was the first"
)
A_REPEAT_WAS_REPORTED_AS_A_CHANGE: Final = "a run that repeated an approved one was said to differ"
A_NEW_WRITE_WAS_NOT_REPORTED: Final = "a write that was not in the approved run was not named"
A_PENDING_RUN_WAS_COMPARED_WITH: Final = (
    "a card was compared with a run nobody had approved, or with none"
)
AN_AGENTS_HISTORY_WAS_ANOTHERS: Final = (
    "an agent's first card on a website was compared with another agent's run"
)
A_WEBSITES_HISTORY_WAS_ANOTHERS: Final = (
    "a first card on a website was compared with a run on another website"
)
THE_LATEST_APPROVED_RUN_WAS_NOT_THE_ONE_COMPARED: Final = (
    "a card was compared with an older approved run and not the latest"
)
ANOTHER_PERSONS_HISTORY_WAS_READ: Final = (
    "a person's first card was compared with a run somebody else asked for"
)


@check(
    leaves=("M19.7.2", "M19.9.2"),
    sentence=(
        "The card for a browser write says whether it is the first approval of an agent's writes "
        "on a website, or what it adds or drops since the last run the same asker had approved, "
        "and compares only with a run a person approved."
    ),
)
async def a_card_says_what_changed_since_the_last_approved_run(h: Harness) -> None:
    from brain.approval_routes import DecidableVerdict, DecisionAsked, take_decision
    from brain.browsing.approval import FIRST_APPROVAL, NOTHING_CHANGED
    from brain.browsing.driver import prepare_run
    from brain.browsing.planning import Goal, PlanRequest, plan
    from brain.browsing.sessions import ACT_ON_SURFACE_CAPABILITY, BROWSE_SURFACE, TARGET_FIELD
    from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
    from brain.console.approvals import card as card_for
    from brain.core.scope import Clause, Op, Scope
    from brain.gate.injection import AutonomyTier
    from brain.gate.suspension_store import StoredSuspensions

    await h.found_departments()
    asker, other, approver = (
        h.principal(A, "changes_asker"),
        h.principal(A, "changes_other"),
        h.principal(A, "changes_approver"),
    )
    target = Target(
        name=f"acceptance_{h.run}_changes",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="filing",
                origin=ORIGIN,
                path="/filing",
                verbs=frozenset({Verb.OPEN, Verb.SUBMIT}),
                capability=ACT_ON_SURFACE_CAPABILITY,
            ),
            Surface(
                name="payroll",
                origin=ORIGIN,
                path="/payroll",
                verbs=frozenset({Verb.OPEN, Verb.CLICK}),
                capability=ACT_ON_SURFACE_CAPABILITY,
            ),
        ),
    )
    elsewhere = Target(
        name=f"acceptance_{h.run}_changes_elsewhere",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="filing",
                origin=ORIGIN,
                path="/filing",
                verbs=frozenset({Verb.OPEN, Verb.SUBMIT}),
                capability=ACT_ON_SURFACE_CAPABILITY,
            ),
        ),
    )
    # One grant of each capability, over both websites: a capability is granted once per person.
    narrowed = Scope(
        clauses=(Clause(field=TARGET_FIELD, op=Op.IN, value=(target.name, elsewhere.name)),)
    )
    for who in (asker, other):
        await h.person(
            who,
            department=A,
            grants=((BROWSE_SURFACE.value, narrowed), (ACT_ON_SURFACE_CAPABILITY.value, narrowed)),
        )
    await h.person(approver, department=A, grants=((ACT_ON_SURFACE_CAPABILITY.value, narrowed),))
    store = StoredSuspensions(h.sessions)
    approving = await h.reach(approver)
    agent = f"acceptance_{h.run}_agent"

    async def card(
        who: str, number: int, *surfaces: str, on: Target = target, by: str = agent
    ) -> str:
        """Raise a card for `who`'s run over these surfaces and read back what they are shown."""
        asking = await h.reach(who)
        run_id = f"acceptance_{h.run}_changes_{number}"
        async with store.holding(asking, h.now) as rows:
            await prepare_run(
                rows.session,
                plan(
                    PlanRequest(
                        goal=Goal(text="File the check's return", asked_by=who),
                        target=on.name,
                        surfaces=surfaces,
                    ),
                    TargetRegistry(targets=(on,)),
                ),
                on,
                run_id=run_id,
                agent_id=by,
                reach=asking,
                ceiling=AutonomyTier.AUTONOMOUS,
                trace_id=h.trace_id,
                now=h.now,
            )
        # What the approver is shown, drawn the way every approver surface draws it, and not the
        # requester's own rendering of the action (`brain.gate.approval_request`).
        suspension = await store.reading_as(asking, h.now).suspension(run_id)
        shown = None if suspension is None else card_for(suspension, approving, h.now)
        if shown is None:
            raise CheckFailedError(THE_FIRST_CARD_WAS_NOT_THE_FIRST)
        return str(shown.request.text)

    async def approve(run_number: int) -> None:
        # Each approval a second later than the one before, so "the latest" is not a tie.
        await take_decision(
            store,
            f"acceptance_{h.run}_changes_{run_number}",
            await h.reach(approver),
            DecisionAsked(verdict=DecidableVerdict.APPROVED),
            trace_id=h.trace_id,
            now=h.now + timedelta(seconds=run_number),
        )

    first = await card(asker, 1, "filing")
    if f"changes: {FIRST_APPROVAL}" not in first:
        raise CheckFailedError(THE_FIRST_CARD_WAS_NOT_THE_FIRST)
    await approve(1)

    repeat = await card(asker, 2, "filing")
    if f"changes: {NOTHING_CHANGED}" not in repeat:
        raise CheckFailedError(A_REPEAT_WAS_REPORTED_AS_A_CHANGE)
    await approve(2)

    wider = await card(asker, 3, "filing", "payroll")
    if "adds payroll click x1" not in wider:
        raise CheckFailedError(A_NEW_WRITE_WAS_NOT_REPORTED)

    # Run 3 is pending and run 4 asks for the same: it is compared with run 2, which was approved.
    still_wider = await card(asker, 4, "filing", "payroll")
    if "adds payroll click x1" not in still_wider:
        raise CheckFailedError(A_PENDING_RUN_WAS_COMPARED_WITH)

    # Somebody else's first card, for the same agent and website.
    theirs = await card(other, 5, "filing")
    if f"changes: {FIRST_APPROVAL}" not in theirs:
        raise CheckFailedError(ANOTHER_PERSONS_HISTORY_WAS_READ)

    # The same asker's first card for another agent, and for another website.
    if f"changes: {FIRST_APPROVAL}" not in await card(asker, 6, "filing", by=f"{agent}_two"):
        raise CheckFailedError(AN_AGENTS_HISTORY_WAS_ANOTHERS)
    if f"changes: {FIRST_APPROVAL}" not in await card(asker, 7, "filing", on=elsewhere):
        raise CheckFailedError(A_WEBSITES_HISTORY_WAS_ANOTHERS)

    # The latest approved run is the one compared with: approve the wider run and ask for it again.
    await approve(3)
    if f"changes: {NOTHING_CHANGED}" not in await card(asker, 8, "filing", "payroll"):
        raise CheckFailedError(THE_LATEST_APPROVED_RUN_WAS_NOT_THE_ONE_COMPARED)
