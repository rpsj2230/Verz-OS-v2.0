"""Install acceptance checks for what the governance screens say about refusals and the canaries.

Each check calls the route the console page calls, as the reader that page serves, in the shape
`brain.ops.acceptance_checks_governance` sets out, over the check's own transaction. The refusals
the check writes are ledger entries of that transaction, so **none is kept and none reaches a
person**.

Task ids: M27.3.11, M27.13.6
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import insert

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_company_views import _audit_over
from brain.ops.acceptance_checks_governance import _app, _asking, _refused, _request
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 940

A, B = RESERVED_DEPARTMENTS

#: What a reader of the canaries' evaluations holds. Restated rather than imported, so a change to
#: the route's authority fails the check instead of moving with it.
READS_EVALUATION: Final = "read:evaluation"


# ----------------------------------------------- 1. friction by shape, and the canaries (M27.3.11)
@check(
    leaves=("M27.3.11", "M27.13.6"),
    sentence=(
        "A person refused the same records again and again is shown to a company-wide holder of "
        "them on the Activity screen as a shape of refusal and how often, naming neither the "
        "person nor the records, and a person refused twice adds none; the canaries' newest run "
        "is shown on Quality to a reader of evaluations and to nobody else."
    ),
)
async def refusals_are_shown_by_shape_and_the_canaries_last_run_is_shown(
    h: Harness,
) -> None:
    from brain.audit.record import DenyReason
    from brain.audit_statistics_routes import audit_statistics
    from brain.console.quality_view import CANARY_CONTROL
    from brain.knowledge.row_store import SessionRowSource
    from brain.knowledge.rows import entity_capability, row_scope_for
    from brain.ops.acceptance_operations_console import asking_as, console_for
    from brain.ops.acceptance_operations_console_2 import as_login
    from brain.ops.denial_alerts import ALERT_TEXT
    from brain.ops.denial_store import Denial, StoredDenials
    from brain.ops.limits import DENIALS_WORTH_NOTICING
    from brain.report_routes import quality
    from brain.tables.schedule import ControlRunRow
    from brain.tools.startup import build_registry, classification_for

    registry = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    entities = sorted(
        {
            one.entity
            for one in registry.definitions()
            if one.entity and classification_for(one.entity) is not None
        }
    )
    if not entities:
        raise CheckNotRunError("this install serves no records, so nobody can be refused one")
    entity = entities[0]
    capability = entity_capability(entity)

    await h.found_departments()
    persistent, occasional = h.principal(A, "persistent"), h.principal(A, "occasional")
    holder, bystander = h.principal(A, "holder"), h.principal(A, "bystander")
    for one in (persistent, occasional, bystander):
        await h.person(one, department=A)
    await h.person(
        holder,
        department=A,
        grants=(
            *_audit_over(Scope.unrestricted()),
            (capability.value, Scope.unrestricted()),
            (READS_EVALUATION, Scope.unrestricted()),
        ),
    )
    request = _request(_app(h))
    # The refusals are written as the check runs, a moment after the instant it was admitted at.
    until = h.now + timedelta(hours=1)

    async def refusals(reader: str) -> dict[str, int]:
        found = await audit_statistics(request, await _asking(h, reader), until=until)
        return {one.shape: one.occurrences for one in found.refusals}

    before = await refusals(holder)
    denials = StoredDenials(h.sessions)
    for who, times in ((persistent, DENIALS_WORTH_NOTICING), (occasional, 2)):
        reach = await h.reach(who)
        if row_scope_for(entity, reach, h.now) is not None:
            raise CheckFailedError("a person holding no grant was found to reach the records")
        for n in range(times):
            await denials.denied(
                Denial(
                    actor_id=who,
                    ent_hash=reach.ent_hash(),
                    trace_id=f"{h.trace_id}-{who[-4:]}-{n}",
                    subject_kind="entity",
                    subject_id=entity,
                    capability=capability,
                    reason=DenyReason.NO_GRANT,
                )
            )
    shown = await audit_statistics(request, await _asking(h, holder), until=until)
    after = {one.shape: one.occurrences for one in shown.refusals}
    if sum(after.values()) != sum(before.values()) + DENIALS_WORTH_NOTICING:
        raise CheckFailedError("one person refused again and again was not shown as one pattern")
    sayings = {one.reads_as for one in shown.refusals}
    if not sayings <= set(ALERT_TEXT.values()):
        raise CheckFailedError("a refusal was described in words the product does not hold")
    named = (persistent, occasional, entity, capability.value)
    if any(
        one in text for one in named for text in (*sayings, *(one.shape for one in shown.refusals))
    ):
        raise CheckFailedError("a refusal shape named the person or the records it was about")
    if not await _refused(audit_statistics(request, await _asking(h, bystander), until=until)):
        raise CheckFailedError("a person with no audit screen was shown refusals")

    started = datetime.now(UTC) - timedelta(seconds=30)
    await as_login(
        h,
        insert(ControlRunRow).values(
            name=CANARY_CONTROL,
            started_at=started,
            finished_at=started + timedelta(seconds=1),
            outcome="ok",
        ),
    )
    console = console_for(h)
    canaries = await quality(console.request(), await asking_as(h, holder), days=1)
    if canaries.last_canary_run is None or canaries.last_canary_run.started_at != started:
        raise CheckFailedError("Quality did not show the canaries' newest run")
    hidden = await quality(console.request(), await asking_as(h, bystander), days=1)
    if hidden.last_canary_run is not None or hidden.runs:
        raise CheckFailedError("Quality showed the canaries' runs to a person without the grant")
