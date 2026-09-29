"""The denial digest, run: the patterns of the hour, the people to tell, and the alerts kept.

`brain.ops.denial_alerts.digest` routes a run of refusals to whoever may hear about it and
gathers nothing, and `brain.ops.schedule_runner` recorded what its caller needed: "the denial
patterns of the window and the recipients to send to. The patterns come from the audit ledger
and nothing queries it for them; the recipients are entitlement sets and nothing resolves the
set of people who should receive a digest". This is both, and the store the alerts are kept in.

**The patterns are read from the ledger's `deny` entries and nowhere else.** `gate.record_denial`
writes one for every refusal the gate decides beside the answer, which a person was told as an
absence, so the ledger is the one place DENIED and ABSENT still differ, and this is what that
difference survives for (`limits.DenialAssessment`). One grouped statement per pass: per person
and capability, how many refusals and how many different things they reached for, which is all
`limits.assess_denials` reads. The counts go to the classifier and never further: the alert
carries a shape, and `denial_alerts.THE_ALERT_NAMES_A_SHAPE_AND_NEVER_A_THING` is why.

**A pattern carries no place, so only a company-wide holder of what was refused is told.** A
`deny` entry names the capability and the thing reached for, and nothing about which department
it sits in; inventing one from the thing's name would be a guess in the one input that decides
who hears. `DenialPattern.where` is therefore empty, which `Clause.matches` admits only for a
grant with no clause, and that is the direction to fail in: a department admin who could have
helped is not told, rather than a department admin who could not is. Recorded as a gap rather
than hidden: a refusal's place would have to be written with it.

**The recipients are every live person's reach, through the one resolver**, exactly as
`brain.ops.canary_run` loads its askers, and `digest` narrows them: nobody is told about
themselves, nobody is told what they could not have found out, and nobody is told twice in a
window. Service accounts are not asked, because an alert is for a person to act on.

**Every sender asks whether its notice is on.** `brain.ops.notices.notice_is_on` for
`DENIAL_PATTERN`, before anything is read, so switching the notice off on the Notifications
screen stops the next pass. See `brain.ops.notices`.

**What a pass says names nothing and counts nothing.** The run's detail is read by whoever reads
the control runs, which is not the set of people entitled to the alerts, so it says whether
alerts were raised and not how many or about whom.

Task ids: M23.2.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Final

import structlog
from sqlalchemy import Select, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.entitlement import Capability, EntitlementSet
from brain.core.principal import PrincipalKind
from brain.gate.entitlement_store import StoredEntitlements
from brain.ops.denial_alert_store import AlertStore
from brain.ops.denial_alerts import DIGEST_WINDOW, DenialPattern, digest
from brain.ops.limits import assess_denials
from brain.ops.notices import NoticeKind, notice_is_on
from brain.tables.audit import AuditEntryRow
from brain.tables.identity import PrincipalRow

log = structlog.get_logger()

#: The ledger's action for a refusal the gate decided. `gate.record_denial` writes it.
DENY_ACTION: Final = "deny"

#: What `gate.record_denial` marks an entry with when nobody could be attributed. A refusal
#: with no person behind it is a pattern about nobody, and `DenialPattern` refuses one.
UNATTRIBUTED: Final = "unattributed"

#: What a pass says, in words that name nobody and count nothing.
SWITCHED_OFF: Final = "the refusal-pattern notice is switched off, so nothing was read or raised"
NOTHING_WORTH_RAISING: Final = "no pattern of refusals in the window was worth raising"
NOBODY_NEW_TO_TELL: Final = "patterns were found and everybody entitled has already been told"
RAISED: Final = "alerts were raised and kept for the people entitled to them"

#: Why a pass is refused on a worker with no cache address, in the words the Errors and Jobs
#: screens show. Found on the owner's install on 2026-09-29: the old sentence said "no cache is
#: configured" beside a Dashboard showing the cache ready, because the application is given the
#: address and a deployment tool's stored copy of the compose file had not given the worker it.
THE_WORKER_WAS_GIVEN_NO_CACHE_ADDRESS: Final = (
    "this worker was not given the cache address the application uses, so there is nowhere to "
    "keep an alert. Add the application's VALKEY_URL line under the worker in the compose file "
    "this install runs, then restart the worker"
)


class DenialDigestError(Exception):
    """The pass could not be run. The text names nothing, because it is stored as a run's detail."""


def denials_between(since: datetime, until: datetime) -> Select[tuple[str, str, int, int]]:
    """Per person and capability: refusals, and different things reached for, in `[since, until)`.

    Grouped by the database, for `brain.operate_routes.requests_by_lane`'s reason. An entry
    marked unattributed is left out in the statement, since it is a pattern about nobody.
    """
    capability = AuditEntryRow.details["capability"].astext
    return (
        select(
            AuditEntryRow.actor_id,
            capability,
            func.count(),
            func.count(distinct(AuditEntryRow.subject)),
        )
        .where(
            AuditEntryRow.action == DENY_ACTION,
            AuditEntryRow.at >= since,
            AuditEntryRow.at < until,
            AuditEntryRow.details["actor"].astext.is_distinct_from(UNATTRIBUTED),
        )
        .group_by(AuditEntryRow.actor_id, capability)
    )


def patterns_from(rows: Sequence[tuple[str, str, int, int]]) -> tuple[DenialPattern, ...]:
    """The grouped counts, classified, keeping the patterns worth an alert.

    A row whose capability does not parse is passed over rather than failing the pass:
    `gate.record_denial` refuses such a capability on the way in, so one here was written by
    something else, and a digest that stopped for it would stop telling anybody anything.
    """
    found: list[DenialPattern] = []
    for actor, capability, denials, targets in rows:
        if not actor or capability is None:
            continue
        try:
            pattern = DenialPattern(
                subject_id=str(actor),
                capability=Capability(value=str(capability)),
                assessment=assess_denials(denials=int(denials), distinct_targets=int(targets)),
            )
        except ValueError:
            continue
        if pattern.assessment.is_worth_alerting:
            found.append(pattern)
    return tuple(found)


async def patterns_on(session: AsyncSession, *, now: datetime) -> tuple[DenialPattern, ...]:
    """The patterns of the last digest window, read from the ledger."""
    found = await session.execute(denials_between(now - DIGEST_WINDOW, now))
    return patterns_from([row._tuple() for row in found.all()])


async def people_on_this_install(
    sessions: async_sessionmaker[AsyncSession], *, now: datetime
) -> tuple[EntitlementSet, ...]:
    """Every live person's reach through the one resolver. Not a service account's."""
    async with sessions() as session:
        ids = (
            (
                await session.execute(
                    select(PrincipalRow.id)
                    .where(
                        PrincipalRow.deleted_at.is_(None),
                        PrincipalRow.disabled_at.is_(None),
                        PrincipalRow.kind == PrincipalKind.HUMAN.value,
                    )
                    .order_by(PrincipalRow.id)
                )
            )
            .scalars()
            .all()
        )
    store = StoredEntitlements(sessions)
    return tuple([await store.load(one, now) for one in ids])


def digest_pass(
    *,
    now: datetime,
    patterns: Sequence[DenialPattern],
    recipients: Sequence[EntitlementSet],
    alerts: AlertStore,
) -> str:
    """Route the patterns through `denial_alerts.digest`, keep what it raised, and say so."""
    if not patterns:
        return NOTHING_WORTH_RAISING
    raised = digest(now=now, patterns=patterns, recipients=recipients, log=alerts.load_log())
    if not raised.alerts:
        return NOBODY_NEW_TO_TELL
    alerts.keep(raised)
    return RAISED


async def run_denial_digest(
    sessions: async_sessionmaker[AsyncSession], *, alerts: AlertStore, now: datetime
) -> str:
    """One pass: ask whether the notice is on, read the hour's patterns, tell who may hear."""
    async with sessions() as session:
        if not await notice_is_on(session, NoticeKind.DENIAL_PATTERN):
            return SWITCHED_OFF
        patterns = await patterns_on(session, now=now)
    if not patterns:
        return NOTHING_WORTH_RAISING
    recipients = await people_on_this_install(sessions, now=now)
    return digest_pass(now=now, patterns=patterns, recipients=recipients, alerts=alerts)


def run_denial_digest_now(
    database_url: str,
    *,
    now: datetime,
    valkey_url: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> str:
    """`run_denial_digest` from a thread with no event loop of its own, with the worker's parts.

    A worker with no cache address has nowhere to keep an alert, so the pass is refused rather
    than run: a pass that raised alerts into nothing would record a success for telling nobody.
    See `THE_WORKER_WAS_GIVEN_NO_CACHE_ADDRESS` for what the refusal says.
    """
    from brain.cache import make_client
    from brain.ops.denial_alert_store import make_alert_store
    from brain.session import make_app_engine, make_session_factory

    if not valkey_url:
        raise DenialDigestError(THE_WORKER_WAS_GIVEN_NO_CACHE_ADDRESS)
    client = make_client(valkey_url)

    async def once() -> str:
        engine = make_app_engine(database_url)
        try:
            return await run_denial_digest(
                make_session_factory(engine), alerts=make_alert_store(client), now=now
            )
        finally:
            await engine.dispose()

    try:
        return asyncio.run(once(), loop_factory=loop_factory)
    except DenialDigestError:
        raise
    except Exception as exc:
        log.warning("denial digest could not finish", error=type(exc).__name__)
        msg = "the denial digest could not finish; the worker's log says why"
        raise DenialDigestError(msg) from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
