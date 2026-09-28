"""Install acceptance checks for oversight: unusual volume, repeated refusals, and a head's audit.

The three mechanisms somebody watching the install relies on, each asked on the install it runs on
as reserved principals of the reserved departments, inside the check's rolled-back transaction
(`brain.ops.acceptance.NOTHING_A_CHECK_WRITES_IS_EVER_COMMITTED`). A module of its own beside
`brain.ops.acceptance_checks`, named in `brain.ops.acceptance.CHECK_MODULES`, so a package adding
checks elsewhere does not edit these.

**Each reads only the reserved people's rows.** The volume statement, the denial statement and the
audit page all read the install's whole ledger when the product asks them, and a check has no
business reading a real person's volume, refusals or activity to prove a rule about its own. So
each is the product's own statement narrowed by one more condition to the reserved prefix (or, for
the audit page, the Audit screen's own actor filter), and what decides the answer is the product's
function over what that statement returned: `assess_volume` and `unusual_now`, `patterns_from` and
`digest`, `rewrite_head_audit_reach` and `AuditView`.

**Nothing is sent.** The denial check routes its pattern through the hourly digest's own function
and keeps what it raised in memory rather than in the cache the Notifications screen reads, so no
alert key outlives the check and nobody real is told about a reserved principal. The head check
asks the rewrite about its own head only (`head_audit_store.ONLY_THE_HEADS_NAMED_ARE_REWRITTEN`).

Task ids: M38.5.1
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Final, cast

from sqlalchemy import insert, text

from brain.core.scope import Clause, Op, Scope
from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    RESERVED_PRINCIPAL_PREFIX,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: The reach digest a synthetic request row is written under. The ledger requires the shape.
SYNTHETIC_REACH: Final = "0" * 32


# ------------------------------------------------------------------- M23.2.1 volume
@check(
    leaves=("M23.2.1",),
    sentence=(
        "A person asking twenty times today against a usual one a day is scored unusual from the "
        "install's own request ledger and shown on the Limits screen to a reader of rate limits, "
        "while a person asking as usual is not, machine traffic is not counted, and a reader "
        "whose grant does not reach the person is shown nobody."
    ),
)
async def unusual_volume_is_found_per_person(h: Harness) -> None:
    from brain.console.installation import unusual_now
    from brain.core.lane import Lane
    from brain.gate.context import TrafficClass
    from brain.ops.limits import (
        VOLUME_BASELINE_PERIODS,
        VOLUME_MIN_OBSERVATIONS,
        VOLUME_OBSERVED_PERIOD,
        VolumeBand,
    )
    from brain.ops.telemetry import RequestStatus
    from brain.ops.volume_store import PrincipalVolume, volumes_at
    from brain.tables.telemetry import RequestTelemetryRow

    await h.found_departments()
    spiking, steady, machine = (
        h.principal(A, "spiking"),
        h.principal(A, "steady"),
        h.principal(A, "machine"),
    )
    reader, narrow, nobody = (
        h.principal(A, "limits"),
        h.principal(A, "narrow"),
        h.principal(B, "user"),
    )
    for one in (spiking, steady, machine, nobody):
        await h.person(one, department=A if one != nobody else B)
    await h.person(reader, department=A, grants=(("read:rate_limit", Scope.unrestricted()),))
    only_steady = Scope(clauses=(Clause(field="subject", op=Op.EQ, value=steady),))
    await h.person(narrow, department=A, grants=(("read:rate_limit", only_steady),))

    today = VOLUME_MIN_OBSERVATIONS
    asked: list[tuple[str, int, int, TrafficClass]] = [
        # Who, how many today, how many across the week before, and as what kind of traffic.
        (spiking, today, VOLUME_BASELINE_PERIODS, TrafficClass.HUMAN_INTERACTIVE),
        (steady, today, today * VOLUME_BASELINE_PERIODS, TrafficClass.HUMAN_INTERACTIVE),
        (machine, today, 0, TrafficClass.AUTOMATION),
    ]
    rows: list[dict[str, Any]] = []
    for principal, recent, prior, traffic in asked:
        instants = [
            h.now - VOLUME_OBSERVED_PERIOD * (n / (recent + 1)) for n in range(1, recent + 1)
        ]
        instants += [
            h.now - VOLUME_OBSERVED_PERIOD * (1 + VOLUME_BASELINE_PERIODS * (n / (prior + 1)))
            for n in range(1, prior + 1)
        ]
        rows.extend(
            {
                "received_at": at,
                "trace_id": f"{h.trace_id}-{principal.rsplit('.', 1)[-1]}-{index}",
                "traffic_class": traffic.value,
                "principal": principal,
                "entitlement_hash": SYNTHETIC_REACH,
                "lane": Lane.ANSWER.value,
                "cache_hit": False,
                "status": RequestStatus.ANSWERED.value,
                "duration_ms": 1.0,
            }
            for index, at in enumerate(instants)
        )
    async with h.sessions() as session:
        await session.execute(insert(RequestTelemetryRow), rows)
        # The product's statement, narrowed to this check's people. See the module docstring.
        counted = (
            await session.execute(
                volumes_at(h.now).where(
                    RequestTelemetryRow.principal.startswith(RESERVED_PRINCIPAL_PREFIX)
                )
            )
        ).all()
        await session.commit()
    volumes = [
        PrincipalVolume(principal=str(who), observed=int(recent), prior=int(prior))
        for who, recent, prior in counted
    ]
    by_person = {one.principal: one for one in volumes}
    if machine in by_person:
        raise CheckFailedError("machine traffic was counted as a person asking")
    if spiking not in by_person or steady not in by_person:
        raise CheckFailedError("the request ledger did not count a person's own questions")
    if not by_person[spiking].assessed().is_notable:
        raise CheckFailedError("a person asking far beyond their own week was not scored unusual")
    if by_person[steady].assessed().band is not VolumeBand.ORDINARY:
        raise CheckFailedError("a person asking as they usually do was scored unusual")
    shown = unusual_now(volumes, await h.reach(reader), now=h.now)
    if [one.subject for one in shown] != [spiking]:
        raise CheckFailedError("the Limits screen did not show exactly the unusual person")
    for other in (narrow, nobody):
        if unusual_now(volumes, await h.reach(other), now=h.now):
            raise CheckFailedError("a reader whose grant does not reach the person was shown them")


# ------------------------------------------------------------------ M23.2.2 denials
class _HeldAlerts:
    """`brain.ops.denial_alert_store.AlertStore`'s two calls, kept in memory. See the module."""

    def __init__(self) -> None:
        from brain.ops.denial_alerts import AlertLog

        self.log = AlertLog()
        self.kept: list[Any] = []

    def load_log(self) -> Any:
        return self.log

    def keep(self, digest: Any) -> None:
        self.log = digest.log
        self.kept.extend(digest.alerts)


@check(
    leaves=("M23.2.2",),
    sentence=(
        "A person refused the same records again and again is written to the install's audit "
        "ledger as refused each time, read back as a pattern by the hourly digest's own "
        "statement and routed by its own function to a company-wide holder of what was refused, "
        "naming a shape and never the thing; a person refused twice raises nothing, and neither "
        "the person refused nor a holder in one department is told."
    ),
)
async def repeated_refusals_raise_a_denial_notice(h: Harness) -> None:
    from brain.audit.record import DenyReason
    from brain.knowledge.row_store import SessionRowSource
    from brain.knowledge.rows import entity_capability, row_scope_for
    from brain.ops.denial_alerts import ALERT_TEXT
    from brain.ops.denial_digest_run import (
        RAISED,
        denials_between,
        digest_pass,
        patterns_from,
    )
    from brain.ops.denial_store import Denial, StoredDenials
    from brain.ops.limits import DENIALS_WORTH_NOTICING
    from brain.ops.notices import NoticeKind, notice_is_on
    from brain.tables.audit import AuditEntryRow
    from brain.tools.startup import build_registry, classification_for

    async with h.sessions() as session:
        if not await notice_is_on(session, NoticeKind.DENIAL_PATTERN):
            raise CheckNotRunError("the refusal-pattern notice is switched off on this install")
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
    holder, local = h.principal(A, "holder"), h.principal(A, "local")
    for one in (persistent, occasional):
        await h.person(one, department=A)
    await h.person(holder, department=A, grants=((capability.value, Scope.unrestricted()),))
    await h.person(local, department=A, grants=((capability.value, Scope.department(A)),))

    denials = StoredDenials(h.sessions)
    for who, times in ((persistent, DENIALS_WORTH_NOTICING), (occasional, 2)):
        reach = await h.reach(who)
        if row_scope_for(entity, reach, h.now) is not None:
            raise CheckFailedError("a person holding no grant was found to reach the records")
        for n in range(times):
            # What the records route writes beside its one refusal, awaited here.
            await denials.denied(
                Denial(
                    actor_id=who,
                    ent_hash=reach.ent_hash(),
                    trace_id=f"{h.trace_id}-{n}",
                    subject_kind="entity",
                    subject_id=entity,
                    capability=capability,
                    reason=DenyReason.NO_GRANT,
                )
            )
    if row_scope_for(entity, await h.reach(holder), h.now) is None:
        raise CheckFailedError("a holder of the grant was refused the records")

    async with h.sessions() as session:
        # The digest's own statement, narrowed to this check's people. See the module docstring.
        found = await session.execute(
            denials_between(h.now - timedelta(hours=1), h.now + timedelta(hours=1)).where(
                AuditEntryRow.actor_id.startswith(RESERVED_PRINCIPAL_PREFIX)
            )
        )
        rows = [row._tuple() for row in found.all()]
    patterns = patterns_from(rows)
    if {one.subject_id for one in patterns} != {persistent}:
        raise CheckFailedError("repeated refusals were not read back as exactly one pattern")
    recipients = [await h.reach(one) for one in (persistent, occasional, holder, local)]
    kept = _HeldAlerts()
    # `digest_pass` calls the store's two methods and no other; a cast at that boundary.
    said = digest_pass(now=h.now, patterns=patterns, recipients=recipients, alerts=cast(Any, kept))
    if said != RAISED or [(one.recipient_id, one.subject_id) for one in kept.kept] != [
        (holder, persistent)
    ]:
        raise CheckFailedError("the notice did not reach exactly the company-wide holder")
    [alert] = kept.kept
    if alert.text != ALERT_TEXT[alert.shape] or entity in alert.text:
        raise CheckFailedError("the notice named what was refused rather than a shape")


# -------------------------------------------------------------- M1.8.3 a head's audit
@check(
    leaves=("M1.8.3",),
    sentence=(
        "The head of acceptance_a, given audit reads by the staff sync's own rewrite, reads the "
        "entries of the people the roster places there and nobody else's; a person joining is "
        "read the next night, a person leaving is not, a member reads nothing, and no entry the "
        "rewrite causes records a department."
    ),
)
async def a_head_reads_their_own_peoples_audit_entries_only(h: Harness) -> None:
    from brain.audit.view import MAX_PAGE_SIZE, AuditFilter, AuditView
    from brain.audit_routes import StoredLedger, read_page
    from brain.console.organisation import COMPANY_ID
    from brain.console.reads import permitted
    from brain.console.screens import screen
    from brain.gate.context import Channel
    from brain.identity.organisation_store import Attribution, StoredOrganisation
    from brain.identity.staff_roster import digest_of
    from brain.identity.staff_source import Asserts, Roster, StaffRecord
    from brain.identity.staff_sync import ROSTER_PREFIX
    from brain.identity.teams import Team
    from brain.ops.head_audit_store import rewrite_head_audit_reach
    from brain.tables.audit import attributed_to
    from brain.tables.identity import PrincipalIdentityRow

    await h.found_departments()
    head = h.principal(A, "head")
    first, joiner, outsider = (
        h.principal(A, "first"),
        h.principal(A, "joiner"),
        h.principal(B, "outsider"),
    )
    for one in (head, first, joiner):
        await h.person(one, department=A)
    await h.person(outsider, department=B)
    address = {
        one: f"{one.rsplit('.', 1)[-1]}.{h.run}@acceptance.invalid"
        for one in (first, joiner, outsider)
    }
    await h.execute(
        *h.attributed(),
        insert(PrincipalIdentityRow).values(
            [
                {
                    "channel": Channel.EMAIL.value,
                    "identity_hash": digest_of(mail),
                    "principal_id": who,
                    "bound_at": h.now,
                }
                for who, mail in address.items()
            ]
        ),
    )
    store = StoredOrganisation(h.sessions)

    def anyone(*_: object) -> bool:
        """Every structural question here is the run's own, about its own reserved rows."""
        return True

    if (
        await store.appoint(
            department=A,
            principal_id=head,
            actor=h.actor,
            ent_hash=SYNTHETIC_REACH,
            trace_id=h.trace_id,
            may=anyone,
        )
        is None
    ):
        raise CheckFailedError("the head could not be appointed to lead the department")
    by = Attribution(actor=h.actor, ent_hash=SYNTHETIC_REACH, trace_id=h.trace_id)
    for department in RESERVED_DEPARTMENTS:
        team = Team(company_id=COMPANY_ID, department_slug=department, slug="checks", name="Checks")
        if not isinstance(await store.add_team(team=team, by=by), datetime):
            raise CheckFailedError("a team could not be added to a reserved department")
    for who, department in ((first, A), (joiner, A), (outsider, B)):
        # Each person does one audited thing, so each is the actor of an entry.
        placed = await store.place(
            department=department,
            team="checks",
            principal_id=who,
            actor=who,
            ent_hash=SYNTHETIC_REACH,
            trace_id=h.trace_id,
            may=anyone,
        )
        if placed is None:
            raise CheckFailedError("a person could not be placed in a team")

    source = "acceptance"
    trusted = frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT})

    def roster(*people: tuple[str, str, bool]) -> Roster:
        return Roster(
            source=source,
            people=tuple(
                StaffRecord(
                    work_address=address[who],
                    display_name="Acceptance check",
                    department=department,
                    active=active,
                )
                for who, department, active in people
            ),
            complete=True,
            asserts=trusted,
        )

    async def night(listed: Roster) -> set[str]:
        async with h.sessions() as session:
            # The scheduled run's transaction names nobody, so its grants are the roster's. This
            # one shares the check's transaction, so the last actor set in it is cleared first.
            for statement in attributed_to(actor_id="", ent_hash="", trace_id=""):
                await session.execute(statement)
            await rewrite_head_audit_reach(session, listed, read_at=h.now, only=frozenset({head}))
            await session.commit()
        return await actors_read_by(head)

    async def actors_read_by(reader_id: str) -> set[str]:
        reader = await h.reach(reader_id)
        page = await read_page(
            StoredLedger(h.sessions),
            lambda loaded: AuditView(loaded, reader=reader, now=h.now),
            AuditFilter(actors=frozenset({first, joiner, outsider})),
            limit=MAX_PAGE_SIZE,
            cursor=None,
            newest_first=True,
        )
        return {one.actor_id for one in page.rows if one.subject_id != reader_id}

    if await actors_read_by(head):
        raise CheckFailedError("a head read their people's entries before the sync gave them reach")
    if await night(roster((first, A, True), (outsider, B, True))) != {first}:
        raise CheckFailedError("the head did not read exactly their own people's entries")
    if not permitted(screen("audit").read, await h.reach(head), h.now):
        raise CheckFailedError("the head's reach did not open the Audit screen")
    joined = roster((first, A, True), (joiner, A, True), (outsider, B, True))
    if await night(joined) != {first, joiner}:
        raise CheckFailedError("a person joining the department was not read by its head")
    left = roster((first, A, False), (joiner, A, True), (outsider, B, True))
    if await night(left) != {joiner}:
        raise CheckFailedError("a person leaving the department was still read by its head")
    if await actors_read_by(joiner):
        raise CheckFailedError("a member who leads nothing read somebody else's entries")
    written = (
        await h.execute(
            text(
                "SELECT subject, details FROM obs.audit_entry WHERE actor_id = :grantor"
            ).bindparams(grantor=f"{ROSTER_PREFIX}{source}")
        )
    ).all()
    if not written:
        raise CheckFailedError("the rewrite's grants did not reach the audit ledger")
    for subject, details in written:
        said = f"{subject} {details}".casefold()
        if not str(subject).startswith("grant:") or any(
            one in said for one in RESERVED_DEPARTMENTS
        ):
            raise CheckFailedError("an entry the rewrite caused records a department")
