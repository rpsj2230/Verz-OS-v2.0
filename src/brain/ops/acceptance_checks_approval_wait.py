"""The install acceptance check for the approval wait: one typical figure, from times alone, and
whether push for approvals is now due.

Three approvals are raised in `acceptance_a` at distinct instants hours ago and approved through
the Approvals route's own `take_decision`, so each has waited a known time. The check then reads
`gate.approval_wait`, the view `0227` adds, as the application reads it, and takes from it only
the rows carrying the check's own raised instants (the view names nobody, so the instant is how a
row is told from the install's real ones). It asks three things. The view carries exactly two
columns and the base table shows the same reader nothing, so the view reaches what the read policy
withholds and discloses no more than two times. The typical wait of the check's three is their
median and past the stated hours, so `locale.triggered` fires; and the shortest one alone is not
past them, so it does not. The install's real approvals are never measured by this check.

Task ids: M35.4.5, M35.3.2.2
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from sqlalchemy import text

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2060

#: How long ago each approval was raised: past the stated hours twice, and inside them once. The
#: odd seconds are what tell the check's rows from the install's own in a view that names nobody.
WAITED: Final = (
    timedelta(hours=6, seconds=17, microseconds=13),
    timedelta(hours=5, seconds=29, microseconds=71),
    timedelta(hours=1, seconds=41, microseconds=37),
)

#: Long enough that none of the three has lapsed, and inside the store's own maximum.
WINDOW: Final = timedelta(hours=12)


@check(
    leaves=("M35.4.5", "M35.3.2.2"),
    sentence=(
        "The view of approval waits carries two times and the same reader sees no approval in the "
        "table itself; the typical wait of three approvals that waited six, five and one hours is "
        "the median and past four hours, so push for approvals is reported as due, and the one "
        "hour approval alone is not."
    ),
)
async def the_approval_wait_is_measured_and_push_is_reported(
    h: Harness,
) -> None:
    from brain.approval_routes import DecidableVerdict, DecisionAsked, take_decision
    from brain.console.installation import Source, approval_wait_facts
    from brain.gate.suspension_store import StoredSuspensions
    from brain.ops.acceptance_checks_governance_2 import _raised, _two_people
    from brain.ops.approval_wait import push_is_wanted, typical_wait, waits_since

    asker, approver, _ = await _two_people(h)
    store = StoredSuspensions(h.sessions)
    raised_at = []
    for n, waited in enumerate(WAITED):
        at = h.now - waited
        one = await _raised(h, asker, f"wait{n}", at=at, window=WINDOW, args={"status": h.word()})
        raised_at.append(at)
        await take_decision(
            store,
            one.id,
            await h.reach(approver),
            DecisionAsked(verdict=DecidableVerdict.APPROVED),
            trace_id=h.trace_id,
            now=h.now,
        )

    columns = (
        await h.execute(
            text(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = 'gate' AND table_name = 'approval_wait'"
                " ORDER BY column_name"
            )
        )
    ).all()
    if [one[0] for one in columns] != ["decided_at", "raised_at"]:
        raise CheckFailedError("the view of approval waits carries more than two times")
    # The approvals above were decided at somebody's reach, which the transaction still holds; the
    # question is what a reader with no reach sees.
    await h.execute(text("SELECT set_config('app.principal_id', '', true)"))
    visible = (await h.execute(text("SELECT count(*) FROM gate.suspension"))).scalar_one()
    if visible != 0:
        raise CheckFailedError("a reader with no reach saw an approval in the table itself")

    async with h.sessions() as session:
        pairs = await waits_since(session, now=h.now)
    mine = [one for one in pairs if one[0] in raised_at]
    if len(mine) != len(WAITED):
        raise CheckFailedError("an approval decided in the check was missing from the view")
    typical = typical_wait(mine)
    if typical is None or not (
        WAITED[1] - timedelta(minutes=1) < typical < WAITED[1] + timedelta(minutes=1)
    ):
        raise CheckFailedError("the typical wait of three approvals was not their median")
    if not push_is_wanted(typical):
        raise CheckFailedError("a typical wait past four hours did not report push as due")
    shortest = [one for one in mine if one[0] == raised_at[2]]
    if push_is_wanted(typical_wait(shortest)):
        raise CheckFailedError("a typical wait inside four hours reported push as due")
    facts = approval_wait_facts(typical)
    if [one.source for one in facts] != [Source.MEASURED, Source.MEASURED]:
        raise CheckFailedError("the Install page was not given a measured wait and a verdict")
