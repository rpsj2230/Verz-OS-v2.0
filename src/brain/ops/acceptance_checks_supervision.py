"""Install checks for the thirty-day review of a pin, and the date the Leash screen shows.

A pinned agent is held at Shadow until its pin is reviewed, and the review is a measurement, never
a date. `brain.ops.supervision_review` asks it on a schedule as well as when a person presses
Review, and `brain.agent_leash_routes.agent_leash` is where the Leash screen reads when each pin
ends. The unit tests run over fakes. What they cannot show is that, on an install, over the real
catalogue template, the real pin table and the worker's own pass, a pin whose thirty days have
passed is reviewed and left held, that nothing is written while the switch is off, and that the
screen's reader is told the date and that it is due.

**The agent is the catalogue's own AR and renewal chaser, installed as the gallery installs it.**
A copy of the shipped template is signed with a key made for the check and installed through
`install_version`, so the agent carries the template's own leash: Shadow on each target. What the
chaser does not carry is a pin row. A person presses Pin on the agent's page, which writes one, so
the check writes it through `StoredLeash.write_pin`, the verb that route writes through, thirty-one
days back. Rejected: claiming the pin comes with the template. It does not, and the sentence says
the pin is written.

**The worker's pass is asked twice, once as the report it is while the switch is off and once as
the review it is when on.** Off, it decides and writes nothing, so the newest row is still the pin
as it was written. On (switched in the check's rolled-back transaction, so the install's own state
is never touched), the same pass writes the review in the system reviewer's name, and what it
writes is `EXTENDED`: the agent has been watched on nothing, which is a measured confidence of
nothing, and **a date that has passed is not a reason to let a pin go**. The check asserts the
outcome is not `ELIGIBLE` after thirty-one days, and that the leash still holds Shadow on every
target.

**Counts on an install are about every due pin, so the check reads its own agent.** The pass reads
every pin on the install that is due, so a count from it may include a real one; the assertions are
about the check's own agent's rows and never about a total.

**One date per agent, not one per rung.** The leash is held down for the agent as a whole while it
is pinned (`brain.agents.supervision`), and the Leash screen shows when that pin is reviewed
(`review_due_at`), whether it is due and whether the rungs are held. The leaf's words, "each pinned
rung", are met by that one date over every rung the agent holds.

Task ids: M13.5.18, M13.8.13
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Final

from sqlalchemy import insert, select

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 810

A, _ = RESERVED_DEPARTMENTS

#: How long a pin is held before its review, written out here and not read off the product.
THIRTY_DAYS: Final = timedelta(days=30)

#: How long ago the pin was written: past its thirty days, so a review is due.
PINNED_THIRTY_ONE_DAYS_AGO: Final = timedelta(days=31)


async def _chaser(h: Harness) -> tuple[str, str, Any, set[str]]:
    """The chaser installed from a copy of its template, its installer, the gallery's app and the
    rungs the install answered with."""
    import secrets

    from brain.agents.catalogue import ar_and_renewal_chaser
    from brain.agents.install_store import version_values
    from brain.agents.template import publish
    from brain.ops.acceptance_checks_templates import _administrator, _copy, _gallery, _install
    from brain.tables.template import TemplateVersionRow

    await h.found_departments()
    administrator = await _administrator(h)
    key = secrets.token_hex(32)
    app = _gallery(h, key)
    signed = publish(
        _copy(ar_and_renewal_chaser(), f"acceptance_{h.run}_chaser"),
        key=key,
        signed_by=administrator,
        at=h.now,
    )
    await h.execute(
        *h.attributed(administrator), insert(TemplateVersionRow).values(**version_values(signed))
    )
    made = await _install(h, app, administrator, signed)
    return (
        str(made["agent"]["agent_id"]),
        administrator,
        app,
        {str(one["rung"]) for one in made["leash"]},
    )


async def _pinned(h: Harness, agent: str, by: str) -> Any:
    """The pin a person's Pin press writes, written thirty-one days back; the store it went into."""
    from brain.agents.supervision import ShadowPin
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.ops.leash_store import StoredLeash
    from brain.tables.leash import PinOutcome

    started = h.now - PINNED_THIRTY_ONE_DAYS_AGO
    store = StoredLeash(h.sessions)
    await store.write_pin(
        ShadowPin(agent_id=agent, pinned_at=started, review_due_at=started + THIRTY_DAYS),
        PinOutcome.PINNED,
        by=by,
        counts=None,
        at=started,
        ent_hash=SET_UP_REACH,
        trace_id=h.trace_id,
    )
    return store


async def _switched(h: Harness, *, on: bool) -> None:
    """The review's switch set in the check's transaction, as the owner would set it, with the
    attribution every settings write carries. Rolled back with the rest of the check."""
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.ops.features import SUPERVISION_REVIEW, switch
    from brain.tables.audit import attributed_to

    async with h.sessions() as session:
        for statement in attributed_to(
            actor_id=h.actor, ent_hash=SET_UP_REACH, trace_id=h.trace_id
        ):
            await session.execute(statement)
        await switch(session, SUPERVISION_REVIEW, on=on, by=h.actor)
        await session.commit()


async def _stored_rungs(h: Harness, agent: str) -> set[str]:
    """The rungs the agent's own stored leash holds now, by the words the install answers in."""
    from sqlalchemy import text

    stored = (
        await h.execute(
            text(
                "SELECT effective_document -> 'guardrails.leash' FROM agent.template_instance"
                " WHERE id = :agent"
            ).bindparams(agent=agent)
        )
    ).scalar_one()
    return {str(one["rung"]) for one in (stored or [])}


@check(
    leaves=("M13.5.18",),
    sentence=(
        "The receivables and renewal chaser, installed from the gallery, is disabled at Shadow on "
        "every target; its pin, written thirty days long and left thirty-one days, is read by the "
        "worker's pass as a report while the switch is off and changes nothing, and reviewed once "
        "it is on, in the system reviewer's name, to extended and not released, the leash still "
        "at Shadow."
    ),
)
async def the_chasers_pin_is_reviewed_at_thirty_days_and_never_lapses(h: Harness) -> None:
    from brain.ops.supervision_review import (
        SYSTEM_REVIEWER,
        StoredReviews,
        run_supervision_review,
    )
    from brain.tables.agent import AgentRow
    from brain.tables.leash import PinOutcome, SupervisionPinRow

    agent, installer, _app, installed_at = await _chaser(h)
    row = (await h.execute(select(AgentRow).where(AgentRow.id == agent))).scalar_one()
    stored_at = await _stored_rungs(h, agent)
    if row.disabled_at is None or installed_at != {"shadow"} or len(stored_at) != 1:
        raise CheckFailedError("the chaser was not installed disabled at Shadow on every target")

    store = await _pinned(h, agent, installer)
    state = await store.state(agent)
    if state.pin is None or state.pin.pin.review_due_at - state.pin.pin.pinned_at != THIRTY_DAYS:
        raise CheckFailedError("a pin was not kept thirty days long")

    reviews = StoredReviews(h.sessions)
    await _switched(h, on=False)
    reported = await run_supervision_review(reviews, now=h.now, report_only=True)
    after_report = await store.state(agent)
    if reported.wrote or reported.due < 1:
        raise CheckFailedError("the worker's pass did not report a pin past its thirty days")
    if after_report.pin is None or after_report.pin.outcome is not PinOutcome.PINNED:
        raise CheckFailedError("a pass that only reports changed the pin")
    await _switched(h, on=False)
    off = await run_supervision_review(reviews, now=h.now)
    if off.wrote or (await store.state(agent)).pin != after_report.pin:
        raise CheckFailedError("a pass wrote while its switch was off")

    await _switched(h, on=True)
    reviewed = await run_supervision_review(reviews, now=h.now)
    final = await store.state(agent)
    if not reviewed.wrote or final.pin is None:
        raise CheckFailedError(
            "a pass with its switch on did not review a pin past its thirty days"
        )
    newest = (
        await h.execute(
            select(SupervisionPinRow.decided_by)
            .where(SupervisionPinRow.agent_id == agent)
            .order_by(SupervisionPinRow.decided_at.desc())
            .limit(1)
        )
    ).scalar_one()
    if final.pin.outcome is not PinOutcome.EXTENDED or newest != SYSTEM_REVIEWER:
        raise CheckFailedError(
            "a pin past its thirty days with nothing measured was not extended by the system"
        )
    if await _stored_rungs(h, agent) != stored_at:
        raise CheckFailedError("a reviewed pin let the agent's leash go from Shadow")


@check(
    leaves=("M13.8.13",),
    sentence=(
        "The Leash screen's reader, holding the agent's Settings tab, is told the pin's start, "
        "the date it is reviewed (thirty days on) and that it is due once that date has passed, "
        "and that the rungs are held, before and after the review extends it; a reader without "
        "the tab is told what a reader is told of an agent that does not exist."
    ),
)
async def the_leash_screen_shows_when_a_pin_ends_and_when_it_has_come(h: Harness) -> None:
    from brain.agent_leash_routes import agent_leash
    from brain.console.reads import Plane, plane_capability
    from brain.ops.acceptance_checks_agent_page import _tab_read
    from brain.ops.acceptance_checks_governance import _asking, _refused
    from brain.ops.acceptance_checks_templates import _request
    from brain.ops.supervision_review import StoredReviews, run_supervision_review
    from brain.tables.leash import PinOutcome

    agent, installer, app, _rungs = await _chaser(h)
    reader, outsider = h.principal(A, "leashreader"), h.principal(A, "leashoutsider")
    planes = tuple(plane_capability(one).value for one in Plane)
    await h.person(
        reader,
        department=A,
        grants=tuple((one, Scope.unrestricted()) for one in (_tab_read("settings"), *planes)),
    )
    await h.person(outsider, department=A)
    await _pinned(h, agent, installer)
    request = _request(app)

    before = await agent_leash(request, agent, await _asking(h, reader))
    shown = before.supervision
    if shown is None:
        raise CheckFailedError("the Leash screen showed no pin for a pinned agent")
    if shown.review_due_at - shown.pinned_at != THIRTY_DAYS or not shown.due or not shown.held:
        raise CheckFailedError(
            "the Leash screen did not show a pin's date, that it is due and held"
        )
    if not before.entries:
        raise CheckFailedError("the Leash screen showed no rung for a pinned agent")

    await _switched(h, on=True)
    await run_supervision_review(StoredReviews(h.sessions), now=h.now)
    after = (await agent_leash(request, agent, await _asking(h, reader))).supervision
    if after is None or after.outcome != PinOutcome.EXTENDED.value or not after.held:
        raise CheckFailedError("the Leash screen did not show an extended pin as held")
    if after.review_due_at <= shown.review_due_at:
        raise CheckFailedError("the Leash screen did not show the new date a review set")

    if not await _refused(agent_leash(request, agent, await _asking(h, outsider))):
        raise CheckFailedError("a reader without the Settings tab was shown an agent's leash")
    if not await _refused(
        agent_leash(request, f"acceptance_{h.run}_nobody", await _asking(h, reader))
    ):
        raise CheckFailedError("an agent that does not exist was answered")
