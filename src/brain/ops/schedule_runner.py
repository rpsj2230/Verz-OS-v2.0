"""The half of the scheduler that holds a connection, and what each control still needs.

`brain.ops.schedule` decides what is owed and reads no clock, opens no connection and starts
nothing. This is the other half: the lock that stops two replicas running one control, the two
queries that answer when each control last ran and last succeeded, and the loop that ticks.

**Two clocks, and reading one of them twice is the failure this is built around.** When a
control may next be *tried* is measured from its last attempt, so a control that fails does
not run again thirty seconds later and then two thousand eight hundred and eighty times a day.
How *late* it is, is measured from its last **success**, because a mechanism that has been
failing hourly for a week has not run for a week. Fold the two into one column and you get a
control that is permanently on time and permanently broken, which is precisely the shape
`brain.ops.controls` was written about. See `TRIED_RECENTLY_AND_WORKING_ARE_DIFFERENT_CLOCKS`.

**`pg_advisory_xact_lock`, not `pg_advisory_lock`, and it is not a preference.** The
application talks to PgBouncer in transaction mode, where consecutive statements from one
client can land on different server connections, so a session-level lock is taken on one
connection while every later statement runs somewhere else: mutual exclusion is gone and
nothing says so. `brain.migrate` learned this the expensive way and its comment is the record.
Transaction-scoped, and it is released when the transaction ends however it ends.

**Try, do not wait.** `brain.migrate` blocks, because a replica that loses the migration race
must not serve against an unmigrated schema. Here the opposite is right: a replica that cannot
take a control's lock means another replica is running that control, and waiting would hold a
connection open for the length of a sweep to then discover there is nothing to do. It moves on
and the control is picked up on a later tick by whoever is free. See
`A_LOCK_THIS_CANNOT_TAKE_MEANS_SOMEBODY_ELSE_IS_RUNNING_IT`.

**A lock per control, not one for the scheduler.** One lock would serialise thirteen unrelated
mechanisms behind whichever is slowest, and a retention sweep is the slowest thing here. The
identifier is derived from the control's name so it cannot be typed wrong and cannot collide
with `brain.migrate`'s.

**Thirteen controls are wired, and the rest are stated rather than implied.** `retention_sweep`,
`canary_run`, `knowledge_reverification`, `outbox_dispatch`, `spend_report_refresh`,
`erasure_queue`, `vault_token_renewal`, `automation_run`, `connector_sync`, `vault_audit_ship`,
since 2026-09-21 `directory_sync`, since 2026-09-22 `model_health_probes`, and since 2026-09-28
`denial_digest` have a runner that gathers what they need, and `brain.ops.worker` starts them on
the schedule through `start_control`. Every other control entry point is a policy function that
takes its inputs: `retention.enforcement_report` takes a census "the executor saw",
`recovery.alerts` takes backups and verifications. None of them gathers
anything. So the registry's orphans are not mechanisms waiting for a timer, they are mechanisms
whose policy is written and whose input gathering does not exist, and a scheduler alone does not
switch them on. `runner_gaps` reports each one by name, which turns a count of mechanisms nothing
runs into a list of named pieces of work, and no count is written here because this one went stale
twice. See
`A_SCHEDULER_WITH_NOTHING_TO_RUN_IS_HONEST_AND_A_SCHEDULER_THAT_PRETENDS_IS_NOT`.

**A runner has to call its control in a way `brain.ops.controls` can see.** That registry
reads `ast.Call` nodes to answer "does anything call this", and its own docstring says it
cannot resolve a callable passed as an argument or anything dynamic. So a dispatch table of
function references would run the controls while the registry went on reporting that nothing
calls them, which is the same lie one layer down. Each runner is therefore a function in this
module making a literal call, `RUNNERS` maps a name to one of those, and `start_control`
reaches each of them by name with a literal call of its own, which is the path the worker takes.
See `A_RUNNER_IS_STARTED_BY_A_CALL_THE_REGISTRY_CAN_READ`.

Rejected: a thread. The application is async and a thread would need its own engine, its own
session scope and its own error handling, and the two would drift. The loop is a task on the
running event loop, cancelled when the application stops.

Rejected: recording a run before taking the lock, so that a contended tick leaves a trace. It
would fill the table with rows for runs that never happened, and "this control has thousands
of attempts and no successes" would then mean two different things.

Task ids: M37.5.1.3, M34.2.1.3, M27.8.12, M27.7.19, M42.6.2, M38.2.2.5, M42.6.5, M1.6.12, M5.4.7
Task ids: M22.2.2
"""

from __future__ import annotations

import zlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import psycopg

from brain.db import libpq_conninfo
from brain.knowledge.item_store import run_reverification_now
from brain.ops.admission import WorkloadClass
from brain.ops.automation_run_store import run_automations_now
from brain.ops.canary_run import run_canaries_now
from brain.ops.connector_sync_run import run_connector_sync_now
from brain.ops.controls import Control
from brain.ops.denial_digest_run import run_denial_digest_now
from brain.ops.erasure_store import drain_erasure_queue
from brain.ops.escalation_store import run_expiry_now
from brain.ops.ledger_partitions import maintain as maintain_ledger_partitions
from brain.ops.model_probe_run import run_model_probes_now
from brain.ops.openbao import OpenBaoVault
from brain.ops.retention_store import run_retention_sweep
from brain.ops.schedule import TICK, AtTime, Owed, owed, schedulable, time_of_day
from brain.ops.secrets import VaultRole
from brain.ops.spend_store import refresh_spend_daily_now
from brain.ops.staff_sync_run import run_staff_sync_now
from brain.ops.vault_audit_ship import run_vault_audit_ship_now
from brain.ops.vault_renewal import run_renewal_now
from brain.ops.webhook_delivery import run_dispatch_now
from brain.resolution.calibration_store import run_calibration_now
from brain.resolution.registry_store import run_registry_now
from brain.settings import process_environment, settings_from

#: Why the two questions are two columns.
TRIED_RECENTLY_AND_WORKING_ARE_DIFFERENT_CLOCKS: Final = (
    "A control that fails every attempt has run recently and has not worked for however long "
    "it has been failing. Measuring dueness from the last attempt is what stops a broken "
    "control being retried on every tick; measuring lateness from the last success is what "
    "stops it reporting as healthy. One column cannot say both, and the version that says "
    "only the first is a mechanism that is permanently on time and permanently broken."
)

#: Why a lock that cannot be taken is not an error.
A_LOCK_THIS_CANNOT_TAKE_MEANS_SOMEBODY_ELSE_IS_RUNNING_IT: Final = (
    "Two replicas tick at the same time and both find the same control owed. The one that "
    "cannot take the lock has learned that the other is running it, which is the system "
    "working. Waiting would hold a connection for the length of a sweep to discover there is "
    "nothing to do, and treating it as a failure would record an attempt that never happened."
)

#: Why the module ships with an empty dispatch table and says so.
A_SCHEDULER_WITH_NOTHING_TO_RUN_IS_HONEST_AND_A_SCHEDULER_THAT_PRETENDS_IS_NOT: Final = (
    "Every control entry point in the registry is a policy function taking its inputs, and "
    "nothing in this system gathers those inputs. Wiring a control means writing its "
    "gatherer, one at a time, each with its own tests. A dispatch table filled with calls "
    "that pass empty sequences would make every control report a successful run having "
    "examined nothing, which is worse than the state it replaced: the console would say the "
    "estate is protected and a run record would agree with it."
)

#: Why the worker reaches a runner by name rather than through `Runner.run`.
A_RUNNER_IS_STARTED_BY_A_CALL_THE_REGISTRY_CAN_READ: Final = (
    "brain.ops.controls decides whether a control is running by finding a call to it in the "
    "source, and it cannot follow a function stored in a table and called through a variable. "
    "A loop that started runners through Runner.run would run them while the registry reported "
    "nothing calling them, and the chain check would report every runner as unreached. So "
    "start_control names each wired runner in a match arm and calls it, and a test holds the "
    "arms to the runners that can run, so the table and the dispatch cannot disagree."
)

#: Why the retention runner is handed no legal holds and reads them itself.
THE_SWEEP_READS_ITS_OWN_HOLDS: Final = (
    "Holds live in obs.legal_hold and the release in ops.retention_release, both since 0049. "
    "brain.ops.retention_store.run_retention_sweep reads the holds inside the transaction that "
    "removes rows, so a hold committed before the run began is honoured by it, and a runner "
    "handing holds in would read them in a different transaction from the removal and open a "
    "window in which a hold placed between the two reads was a hold the sweep never saw."
)

#: Why the refresh does nothing in report-only mode.
A_REFRESH_IN_REPORT_ONLY_MODE_REBUILDS_NOTHING: Final = (
    "Report-only mode exists for controls that remove data, and the refresh removes nothing, "
    "so brain.ops.schedule never asks for it. A runner that rebuilt anyway when asked would be "
    "a runner that ignores the mode it was given, which is the one property a destructive "
    "control's safety rests on being true of every runner."
)

#: Why the re-verification nag records nothing in report-only mode.
A_NAG_IN_REPORT_ONLY_MODE_RECORDS_NOTHING: Final = (
    "Report-only mode exists for controls that remove data, and recording a nag removes nothing, "
    "so brain.ops.schedule never asks for it. A runner that recorded anyway when asked would be a "
    "runner that ignores the mode it was given, which is the property every runner has to keep "
    "for the one control whose safety rests on it."
)

#: Why the canaries ask nothing in report-only mode.
A_CANARY_RUN_IN_REPORT_ONLY_MODE_ASKS_NOTHING: Final = (
    "Report-only mode exists for controls that remove data, and the canaries remove nothing, so "
    "brain.ops.schedule never asks for it. A runner that asked its questions anyway when told "
    "to report would be a runner that ignores the mode it was given, which is the property "
    "every runner keeps for the one control whose safety rests on it."
)

#: Why the automation runner starts nothing in report-only mode.
AN_AUTOMATION_RUN_IN_REPORT_ONLY_MODE_RUNS_NOTHING: Final = (
    "Report-only mode exists for controls that remove data, and running an automation removes "
    "nothing, so brain.ops.schedule never asks for it. A runner that ran automations anyway when "
    "told to report would be a runner that ignores the mode it was given, which is the property "
    "every runner keeps for the one control whose safety rests on it."
)

#: The advisory lock namespace, so a control's lock cannot collide with `brain.migrate`'s.
#:
#: PostgreSQL's two-argument advisory lock takes a pair of 32-bit integers, and using the pair
#: rather than one 64-bit value is what makes the namespace visible in `pg_locks` instead of
#: being hidden inside an arithmetic combination somebody would have to reverse.
SCHEDULER_LOCK_NAMESPACE: Final = 0x5C4E

#: How long a run may hold its lock before the scheduler stops waiting for it to finish.
#:
#: Ten minutes, against a shortest cadence of one minute. Not a timeout on the control, which
#: this cannot enforce without killing work halfway: it is how long a row may sit with a
#: `started_at` and no `finished_at` before `stalled_runs` calls it stalled. A control that
#: legitimately takes longer than this needs its own figure beside it and an argument for it.
STALLED_AFTER: Final = timedelta(minutes=10)


#: Why every control that runs says which class it is in, and how the classes were chosen.
A_CONTROL_IS_CLASSED_BY_WHAT_IT_IS: Final = (
    "A control has no traffic class or lane, because nobody asked for it, so admission's "
    "workload_class_for has nothing to read. It is classed by what it does: a connector or "
    "directory sync, an ingestion of logs, a re-verification of knowledge, a sweep or a report "
    "is batch; tasks, agents, automations, deliveries, probes and the checks are background. "
    "Nothing a control does is interactive, so a control can never hold a connection the "
    "request path's pool keeps. A control that runs and names no class is refused, because a "
    "default would put the next sweep somebody writes on whichever pool the default named."
)


class RunnerError(Exception):
    """Raised when a schedule is asked to run something it cannot describe."""


@dataclass(frozen=True)
class Runner:
    """One control this process knows how to start, and what it needs to do it.

    `run` makes a literal call to the control's entry point, in this module, so
    `brain.ops.controls` can see it. A reference stored here and called through a variable
    would run the control while the registry went on reporting that nothing calls it.

    `needs` is the sentence naming what still has to exist before the control can be wired,
    and it is empty exactly when `run` is set. Keeping the two in one type is what makes
    `runner_gaps` a list of named work rather than a count.
    """

    #: The control's name in `brain.ops.controls.CONTROLS`.
    name: str
    #: What still has to be built before this can run, empty when it can.
    needs: str = ""
    #: The call, when there is one.
    run: Callable[[datetime, bool, str], str] | None = None
    #: Which class's connections the run is given, required exactly when there is a call. See
    #: `A_CONTROL_IS_CLASSED_BY_WHAT_IT_IS`.
    workload: WorkloadClass | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "a runner with no control name cannot be dispatched to or reported on"
            raise RunnerError(msg)
        if self.run is None and not self.needs.strip():
            msg = (
                f"{self.name!r} has nothing to run and does not say what it needs, so it is "
                "indistinguishable from a control somebody forgot. "
                f"{A_SCHEDULER_WITH_NOTHING_TO_RUN_IS_HONEST_AND_A_SCHEDULER_THAT_PRETENDS_IS_NOT}"
            )
            raise RunnerError(msg)
        if self.run is not None and self.needs.strip():
            msg = (
                f"{self.name!r} can be run and also says what it still needs, which reads as "
                "a control that is wired and is not"
            )
            raise RunnerError(msg)
        if self.run is not None and self.workload is None:
            msg = (
                f"{self.name!r} can be run and names no workload class, so nothing says which "
                f"connections it may hold. {A_CONTROL_IS_CLASSED_BY_WHAT_IT_IS}"
            )
            raise RunnerError(msg)


def retention_sweep(now: datetime, report_only: bool, database_url: str) -> str:
    """The retention sweep over PostgreSQL, for the stores it can count, as report lines.

    Passes no holds. See `THE_SWEEP_READS_ITS_OWN_HOLDS`. `prepare_threshold=None` for the reason
    `brain.session.make_app_engine` gives: the URL is the application's, behind a transaction
    pooler, and a statement prepared on one server connection is executed on another.

    Then the metadata ledger's monthly partitions, on the same connection and under the same
    release: `brain.ops.ledger_partitions.maintain` creates the months ahead in either mode and
    detaches a month past its horizon only when the sweep is released. After the sweep rather
    than before, so the sweep's report is written whatever the partitions do, and a failure in
    either is the run's failure.
    """
    with psycopg.connect(libpq_conninfo(database_url), prepare_threshold=None) as conn:
        swept = run_retention_sweep(conn, now=now, report_only=report_only)
        partitions = maintain_ledger_partitions(conn, now=now, report_only=report_only)
    return f"{swept}\n{partitions.summary()}"


def spend_report_refresh(now: datetime, report_only: bool, database_url: str) -> str:
    """Rebuild the materialised spend report, and say what its figures are now as of.

    Declines in report-only mode. See `A_REFRESH_IN_REPORT_ONLY_MODE_REBUILDS_NOTHING`.

    The event loop is the worker's, imported when the refresh runs rather than when this module
    is: `brain.ops.worker` imports this module, and which loop psycopg accepts on a development
    machine is decided there once rather than twice.
    """
    if report_only:
        return (
            "report only: ops.spend_daily was not rebuilt. "
            f"{A_REFRESH_IN_REPORT_ONLY_MODE_REBUILDS_NOTHING}"
        )
    from brain.ops.worker import _loop_factory

    as_of = refresh_spend_daily_now(database_url, loop_factory=_loop_factory())
    return (
        f"ops.spend_daily rebuilt at {now.isoformat()}; its figures are as of {as_of.isoformat()}"
    )


#: Why the dispatch sends nothing in report-only mode.
A_DISPATCH_IN_REPORT_ONLY_MODE_SENDS_NOTHING: Final = (
    "Report-only mode exists for controls that remove data, and a delivery removes nothing, so "
    "brain.ops.schedule never asks for it. A runner that sent anyway when asked would be a runner "
    "that ignores the mode it was given, which is the property every runner has to keep for the "
    "one control whose safety rests on it."
)


def outbox_dispatch(now: datetime, report_only: bool, database_url: str) -> str:
    """Send what is due to webhook subscribers, and say what the run came to in counts.

    `brain.ops.webhook_delivery.run_dispatch_now` claims, signs, sends through `issue_once` and
    records; this is the literal call the registry reads. The vault is the worker's own, read
    from this process's settings, because the worker is the one process that signs: see
    `brain.ops.webhook_delivery.THE_PROCESS_THAT_SIGNS_READS_THE_KEY_AND_NO_OTHER_DOES`.
    Declines in report-only mode, see `A_DISPATCH_IN_REPORT_ONLY_MODE_SENDS_NOTHING`, and takes
    the worker's event loop for the reason `spend_report_refresh` gives.
    """
    if report_only:
        return (
            "report only: no webhook delivery was sent. "
            f"{A_DISPATCH_IN_REPORT_ONLY_MODE_SENDS_NOTHING}"
        )
    from brain.ops.worker import _loop_factory

    settings = settings_from(process_environment())
    ran = run_dispatch_now(
        database_url,
        now=now,
        vault_address=settings.vault_address,
        vault_token=settings.vault_token,
        loop_factory=_loop_factory(),
    )
    return ran.summary()


#: Why the expiry declines in report-only mode, though it removes nothing.
AN_EXPIRY_IN_REPORT_ONLY_MODE_MARKS_NOTHING: Final = (
    "Marking an escalation expired changes what its asker is told, so a run asked to only report "
    "marks nothing and says so, as every runner keeps the mode it was given."
)


def escalation_expiry(now: datetime, report_only: bool, database_url: str) -> str:
    """Mark every escalation whose deadline has passed as expired, and say how many (M8.3.4).

    `brain.ops.escalation_store.run_expiry_now` does it as the worker's login; this is the literal
    call the registry reads. Declines in report-only mode, see
    `AN_EXPIRY_IN_REPORT_ONLY_MODE_MARKS_NOTHING`, and takes the worker's event loop for the
    reason `spend_report_refresh` gives.
    """
    if report_only:
        return (
            "report only: no escalation was marked expired. "
            f"{AN_EXPIRY_IN_REPORT_ONLY_MODE_MARKS_NOTHING}"
        )
    from brain.ops.worker import _loop_factory

    expired = run_expiry_now(database_url, now=now, loop_factory=_loop_factory())
    if expired == 0:
        return "no escalation was due to expire"
    return f"{expired} escalation(s) past their deadline marked expired; each asker is told so"


#: Why the registry declines in report-only mode, though it removes nothing.
A_REGISTRY_RUN_IN_REPORT_ONLY_MODE_WRITES_NOTHING: Final = (
    "The registry only adds: an entity, its names, its keys. Report-only mode exists for controls "
    "that remove data, so brain.ops.schedule never asks for it here, and asked anyway the run "
    "writes nothing and says so rather than ignoring the mode it was given."
)


def entity_resolution(now: datetime, report_only: bool, database_url: str) -> str:
    """Give every record a connector declares for resolution its entity, and say how many (M14.1).

    `brain.resolution.registry_store.run_registry_now` does it as the worker's login, with the
    install's join-key pepper read from the vault with the worker's own token
    (`brain.ops.join_key_pepper`); this is the literal call the registry reads. A pepper that
    cannot be read stops the run with the vault's reason and never a value, because hashing with
    anything else would write digests that join nothing the next run writes. Declines in
    report-only mode, see `A_REGISTRY_RUN_IN_REPORT_ONLY_MODE_WRITES_NOTHING`.
    """
    if report_only:
        return (
            "report only: no record was registered. "
            f"{A_REGISTRY_RUN_IN_REPORT_ONLY_MODE_WRITES_NOTHING}"
        )
    from brain.ops.join_key_pepper import pepper_vault, read_pepper
    from brain.ops.secrets import VaultRole
    from brain.ops.worker import _loop_factory

    settings = settings_from(process_environment())
    pepper = read_pepper(
        pepper_vault(settings.vault_address, settings.vault_token, VaultRole.WORKER)
    )
    ran = run_registry_now(
        database_url, now=now, pepper=pepper.reveal(), loop_factory=_loop_factory()
    )
    return ran.summary()


#: Why the calibration declines in report-only mode, though it removes nothing.
A_FIT_IN_REPORT_ONLY_MODE_KEEPS_NOTHING: Final = (
    "A fit only adds a setting row a reviewer may promote. Report-only mode exists for controls "
    "that remove data, so brain.ops.schedule never asks for it here, and asked anyway the run "
    "fits nothing and says so rather than ignoring the mode it was given."
)


def resolution_calibration(now: datetime, report_only: bool, database_url: str) -> str:
    """Fit the week's candidate pairs into a weight table and keep it for a reviewer (M14.4.4).

    `brain.resolution.calibration_store.run_calibration_now` does it as the worker's login; this is
    the literal call the registry reads. Nothing it keeps is in force until a reviewer promotes
    it, so a run can never change how records are scored. Declines in report-only mode, see
    `A_FIT_IN_REPORT_ONLY_MODE_KEEPS_NOTHING`.
    """
    if report_only:
        return f"report only: nothing was fitted. {A_FIT_IN_REPORT_ONLY_MODE_KEEPS_NOTHING}"
    from brain.ops.worker import _loop_factory

    return run_calibration_now(database_url, now=now, loop_factory=_loop_factory()).summary()


def knowledge_reverification(now: datetime, report_only: bool, database_url: str) -> str:
    """Record the re-verification nags owed at `now`, and say what the run did.

    `brain.knowledge.item_store.run_reverification_now` reads what is due, asks whether each
    owner can still reach it and records the nag; this is the literal call the registry reads.
    Declines in report-only mode, see `A_NAG_IN_REPORT_ONLY_MODE_RECORDS_NOTHING`, and takes the
    worker's event loop for the reason `spend_report_refresh` gives.
    """
    if report_only:
        return (
            "report only: no re-verification nag was recorded. "
            f"{A_NAG_IN_REPORT_ONLY_MODE_RECORDS_NOTHING}"
        )
    from brain.ops.worker import _loop_factory

    ran = run_reverification_now(database_url, now=now, loop_factory=_loop_factory())
    return ran.summary(now)


def erasure_queue(now: datetime, report_only: bool, database_url: str) -> str:
    """Carry out the erasure requests filed by `now`, as report lines.

    On the worker's own connection, which is the database owner's: `brain.ops.erasure_store` refuses
    a connection row-level security narrows, because a row a policy hides is a row the erasure
    would neither count nor retire. `prepare_threshold=None` for the reason `retention_sweep` gives.
    The vault is the worker's own, read from this process's settings, and removes the refresh tokens
    a person's own consents bought (`brain.ops.erasure_store.
    ERASING_A_PERSON_REMOVES_THEIR_OWN_REFRESH_TOKENS`); a worker with none says so in the report.
    """
    settings = settings_from(process_environment())
    vault: OpenBaoVault | None = None
    if settings.vault_address and settings.vault_token:
        try:
            vault = OpenBaoVault(
                settings.vault_address, settings.vault_token, role=VaultRole.WORKER
            )
        except ValueError:
            vault = None
    with psycopg.connect(libpq_conninfo(database_url), prepare_threshold=None) as conn:
        return drain_erasure_queue(conn, now=now, report_only=report_only, own_tokens=vault)


def canary_run(now: datetime, report_only: bool, database_url: str) -> str:
    """Ask the permission canaries as every reach on the install, and say what they found.

    `brain.ops.canary_run.run_canaries_now` is the literal call the registry reads. A red run
    raises `CanariesFoundError`, whose text names nothing, so the worker records it as failed with
    no subject in the detail. The registry's source is read from this process's settings, as
    `outbox_dispatch` reads the vault, because the registry the canaries ask is the one the
    application builds.
    Declines in report-only mode, see `A_CANARY_RUN_IN_REPORT_ONLY_MODE_ASKS_NOTHING`, and takes
    the worker's event loop for the reason `spend_report_refresh` gives.
    """
    if report_only:
        return (
            "report only: the permission canaries asked nothing. "
            f"{A_CANARY_RUN_IN_REPORT_ONLY_MODE_ASKS_NOTHING}"
        )
    from brain.ops.worker import _loop_factory

    return run_canaries_now(
        database_url,
        now=now,
        tool_source=settings_from(process_environment()).tool_source,
        loop_factory=_loop_factory(),
    )


#: Why a renewal is not held back in report-only mode.
A_RENEWAL_IN_REPORT_ONLY_MODE_STILL_RENEWS: Final = (
    "Report-only mode exists for controls that remove data, and a renewal removes nothing, so "
    "brain.ops.schedule never asks for it. Declining when asked would be the one refusal here that "
    "does harm: a token not renewed lapses for good, and every signed delivery with it. So the "
    "mode is honoured by saying so, and the renewal runs."
)


def vault_token_renewal(now: datetime, report_only: bool, database_url: str) -> str:
    """Renew the worker's own vault token when it is owed, and say what was done.

    `brain.ops.vault_renewal.run_renewal_now` is the literal call the registry reads, with the
    worker's settings, because a token is renewed by the process that holds it: see
    `brain.ops.vault_renewal.RENEWAL_TAKES_THE_CREDENTIAL_SO_EACH_HOLDER_RENEWS_ITS_OWN`. The
    application renews its own from its lifespan. Touches no database, and renews in report-only
    mode too, see `A_RENEWAL_IN_REPORT_ONLY_MODE_STILL_RENEWS`.
    """
    settings = settings_from(process_environment())
    said = run_renewal_now(settings.vault_address, settings.vault_token)
    return f"report only, renewed anyway: {said}" if report_only else said


def automation_run(now: datetime, report_only: bool, database_url: str) -> str:
    """Run every installed automation due at `now` as its owner, and say what the tick came to.

    `brain.ops.automation_run_store.run_automations_now` is the literal call the registry reads.
    On the worker's own connection, for the reason `erasure_queue` gives. Declines in report-only
    mode, see `AN_AUTOMATION_RUN_IN_REPORT_ONLY_MODE_RUNS_NOTHING`, and takes the worker's event
    loop for the reason `spend_report_refresh` gives.
    """
    if report_only:
        return (
            "report only: no automation was run. "
            f"{AN_AUTOMATION_RUN_IN_REPORT_ONLY_MODE_RUNS_NOTHING}"
        )
    from brain.ops.worker import _loop_factory

    return run_automations_now(database_url, now=now, loop_factory=_loop_factory())


#: Why a sync reads nothing in report-only mode.
A_READ_IN_REPORT_ONLY_MODE_READS_NOTHING: Final = (
    "Report-only mode exists for controls that remove data, and a sync removes nothing, so "
    "brain.ops.schedule never asks for it. A runner that read anyway when asked would ignore the "
    "mode it was given, which is the property every runner keeps for the one control whose safety "
    "rests on it."
)


def connector_sync(now: datetime, report_only: bool, database_url: str) -> str:
    """Read every connected source that is due, and say what the run came to in counts.

    `brain.ops.connector_sync_run.run_connector_sync_now` reads, writes each source's minimal index
    to the projection and records each attempt; this is the literal call the registry reads.
    The vault is the worker's own, read from this process's settings, because the worker is the one
    process that reads a source's key: see `brain.ops.connector_sync_run.
    THE_PROCESS_THAT_RUNS_A_CONNECTOR_READS_ITS_KEY_AND_NO_OTHER_DOES`. Declines in report-only
    mode, see `A_READ_IN_REPORT_ONLY_MODE_READS_NOTHING`, and takes the worker's event loop for the
    reason `spend_report_refresh` gives.
    """
    if report_only:
        return (
            f"report only: no connected source was read. {A_READ_IN_REPORT_ONLY_MODE_READS_NOTHING}"
        )
    from brain.ops.worker import _loop_factory

    settings = settings_from(process_environment())
    ran = run_connector_sync_now(
        database_url,
        now=now,
        vault_address=settings.vault_address,
        vault_token=settings.vault_token,
        loop_factory=_loop_factory(),
    )
    return ran.summary()


#: Why shipping the vault's log runs in report-only mode too.
SHIPPING_A_LOG_IN_REPORT_ONLY_MODE_STILL_SHIPS: Final = (
    "Report-only mode exists for controls that remove data, and shipping removes nothing: it "
    "copies what the vault already wrote into the ledger. Declining when asked would leave a "
    "stretch of the vault's log unrecorded for no safety gained, so the mode is honoured by "
    "saying so."
)


def vault_audit_ship(now: datetime, report_only: bool, database_url: str) -> str:
    """Ship the vault's audit log into the ledger from where the last run left it.

    `brain.ops.vault_audit_ship.run_vault_audit_ship_now` is the literal call the registry reads,
    on the worker's own connection, with the worker's vault address to tell an install with no
    vault from one whose log is missing. Ships in report-only mode too, see
    `SHIPPING_A_LOG_IN_REPORT_ONLY_MODE_STILL_SHIPS`.
    """
    from brain.ops.worker import _loop_factory

    settings = settings_from(process_environment())
    said = run_vault_audit_ship_now(
        database_url, vault_address=settings.vault_address, loop_factory=_loop_factory()
    )
    return f"report only, shipped anyway: {said}" if report_only else said


#: Why the staff sync reads nothing in report-only mode.
A_STAFF_READ_IN_REPORT_ONLY_MODE_READS_NOTHING: Final = (
    "The staff sync marks leavers and never deletes, so brain.ops.schedule never asks it to "
    "report only. Asked anyway, it declines rather than reading the directory and then ignoring "
    "the mode, for A_READ_IN_REPORT_ONLY_MODE_READS_NOTHING's reason."
)


def directory_sync(now: datetime, report_only: bool, database_url: str) -> str:
    """Read the chosen staff list with the kept credential and apply it, once.

    `brain.ops.staff_sync_run.run_staff_sync_now` reads the source, makes the dry run, writes the
    roster and appends the run the Staff sources screen shows; this is the literal call the
    registry reads. The vault is the worker's own, for `connector_sync`'s reason.
    """
    if report_only:
        said = A_STAFF_READ_IN_REPORT_ONLY_MODE_READS_NOTHING
        return f"report only: no staff list was read. {said}"
    from brain.ops.worker import _loop_factory

    settings = settings_from(process_environment())
    ran = run_staff_sync_now(
        database_url,
        now=now,
        vault_address=settings.vault_address,
        vault_token=settings.vault_token,
        loop_factory=_loop_factory(),
    )
    return ran.summary()


#: Why a probe tick does not hold back in report-only mode.
A_PROBE_IN_REPORT_ONLY_MODE_STILL_PROBES: Final = (
    "Report-only mode exists for controls that remove data, and a probe removes nothing: it sends "
    "one fixed sentence and appends whether the provider answered. brain.ops.schedule never asks "
    "for it, and declining when asked would leave a dead provider in rotation for no safety "
    "gained, so the mode is honoured by saying so."
)


def model_health_probes(now: datetime, report_only: bool, database_url: str) -> str:
    """Probe the providers nobody has asked lately, and say what the tick came to.

    `brain.ops.model_probe_run.run_model_probes_now` is the literal call the registry reads, on the
    worker's own connection, with the worker's vault for the provider keys it reads under its own
    policy (`ops/openbao/policies/worker.hcl`). With no key held it opens nothing and says so.
    Probes in report-only mode too, see `A_PROBE_IN_REPORT_ONLY_MODE_STILL_PROBES`, and takes the
    worker's event loop for the reason `spend_report_refresh` gives.
    """
    from brain.ops.worker import _loop_factory

    settings = settings_from(process_environment())
    said = run_model_probes_now(
        database_url,
        now=now,
        vault_address=settings.vault_address,
        vault_token=settings.vault_token,
        loop_factory=_loop_factory(),
    ).summary()
    return f"report only, probed anyway: {said}" if report_only else said


#: Why the denial digest raises nothing in report-only mode.
A_DIGEST_IN_REPORT_ONLY_MODE_RAISES_NOTHING: Final = (
    "Report-only mode exists for controls that remove data, and keeping an alert removes nothing, "
    "so brain.ops.schedule never asks for it. A runner that raised alerts anyway when told to "
    "report would be a runner that ignores the mode it was given, which is the property every "
    "runner keeps for the one control whose safety rests on it."
)


def denial_digest(now: datetime, report_only: bool, database_url: str) -> str:
    """Read the hour's refusal patterns from the ledger and keep an alert for whoever may hear it.

    `brain.ops.denial_digest_run.run_denial_digest_now` is the literal call the registry reads, with
    the cache this process's settings name, where the alerts are kept for the Notifications screen.
    Declines in report-only mode, see `A_DIGEST_IN_REPORT_ONLY_MODE_RAISES_NOTHING`, and takes the
    worker's event loop for the reason `spend_report_refresh` gives.
    """
    if report_only:
        return (
            "report only: the denial digest raised nothing. "
            f"{A_DIGEST_IN_REPORT_ONLY_MODE_RAISES_NOTHING}"
        )
    from brain.ops.worker import _loop_factory

    return run_denial_digest_now(
        database_url,
        now=now,
        valkey_url=settings_from(process_environment()).valkey_url,
        loop_factory=_loop_factory(),
    )


def queue_redrive(now: datetime, report_only: bool, database_url: str) -> str:
    """Re-drive what a dead worker or a transient failure left behind, and say what it came to.

    `brain.ops.recovery_run.run_queue_redrive_now` is the literal call the registry reads, on the
    queue's own connection (`QUEUE_URL`, which the worker already needs to run at all) rather than
    `database_url`, because the queue's tables are the driver's and the driver is the one client
    that may move a row. Declines in report-only mode, see
    `brain.ops.recovery_run.A_RECOVERY_SWEEP_IN_REPORT_ONLY_MODE_MOVES_NOTHING`, and takes the
    worker's event loop for the reason `spend_report_refresh` gives.
    """
    from brain.ops.recovery_run import (
        A_RECOVERY_SWEEP_IN_REPORT_ONLY_MODE_MOVES_NOTHING,
        run_queue_redrive_now,
    )
    from brain.ops.worker import QUEUE_URL_ENV, _loop_factory

    if report_only:
        return (
            f"report only: no job was moved. {A_RECOVERY_SWEEP_IN_REPORT_ONLY_MODE_MOVES_NOTHING}"
        )
    queue_url = process_environment().get(QUEUE_URL_ENV, "").strip()
    if not queue_url:
        return f"no job was moved: {QUEUE_URL_ENV} is not set on this worker, so it has no queue"
    return run_queue_redrive_now(queue_url, now=now, loop_factory=_loop_factory()).summary()


def side_effect_resume(now: datetime, report_only: bool, database_url: str) -> str:
    """Read back every interrupted side effect a connector can answer for, and list the rest.

    `brain.ops.recovery_run.run_side_effect_resume_now` is the literal call the registry reads, on
    the worker's own connection to `ops.operation`. Declines in report-only mode for the queue
    sweep's reason, and takes the worker's event loop for the reason `spend_report_refresh` gives.
    """
    from brain.ops.recovery_run import (
        A_RECOVERY_SWEEP_IN_REPORT_ONLY_MODE_MOVES_NOTHING,
        run_side_effect_resume_now,
    )
    from brain.ops.worker import _loop_factory

    if report_only:
        return (
            "report only: no operation was read back. "
            f"{A_RECOVERY_SWEEP_IN_REPORT_ONLY_MODE_MOVES_NOTHING}"
        )
    return run_side_effect_resume_now(database_url, now=now, loop_factory=_loop_factory()).summary()


#: Why the evening digest sends nothing in report-only mode.
A_DIGEST_IN_REPORT_ONLY_MODE_SENDS_NOTHING: Final = (
    "Report-only mode exists for controls that remove data, and a message removes nothing, so "
    "brain.ops.schedule never asks for it. A runner that sent anyway when told to report would "
    "ignore the mode it was given."
)


def evening_digest(now: datetime, report_only: bool, database_url: str) -> str:
    """Send today's build digest once, to the conversation the install chose, or say why not.

    `brain.ops.digest_run.run_evening_digest_now` is the literal call the registry reads, with the
    worker's vault for the send's borrowed key (`brain.ops.channel_lease`). The schedule owes it
    once a day at `INSTALL_DIGEST_TIME` in the install's zone (`Control.daily_at`). Declines in
    report-only mode, see `A_DIGEST_IN_REPORT_ONLY_MODE_SENDS_NOTHING`, and takes the worker's
    event loop for the reason `spend_report_refresh` gives.
    """
    if report_only:
        return f"report only: no digest was sent. {A_DIGEST_IN_REPORT_ONLY_MODE_SENDS_NOTHING}"
    from brain.ops.digest_run import run_evening_digest_now
    from brain.ops.worker import _loop_factory

    settings = settings_from(process_environment())
    return run_evening_digest_now(
        database_url,
        now=now,
        vault_address=settings.vault_address,
        vault_token=settings.vault_token,
        loop_factory=_loop_factory(),
    )


#: Why approved actions run nothing in report-only mode.
AN_APPROVED_ACTION_IN_REPORT_ONLY_MODE_RUNS_NOTHING: Final = (
    "Running an approved action changes a system somebody else owns, so a run asked to only "
    "report runs none and says so; the approvals stay approved, inside their windows."
)


def approved_actions(now: datetime, report_only: bool, database_url: str) -> str:
    """Run every approved action that is waiting, each once, and say what the runs came to.

    `brain.ops.approved_runs.run_approved_now` is the literal call the registry reads, with the
    worker's vault for a write's own key. Declines in report-only mode, see
    `AN_APPROVED_ACTION_IN_REPORT_ONLY_MODE_RUNS_NOTHING`, and takes the worker's event loop for
    the reason `spend_report_refresh` gives.
    """
    if report_only:
        return (
            "report only: no approved action was run. "
            f"{AN_APPROVED_ACTION_IN_REPORT_ONLY_MODE_RUNS_NOTHING}"
        )
    from brain.ops.approved_runs import run_approved_now
    from brain.ops.worker import _loop_factory

    settings = settings_from(process_environment())
    return run_approved_now(
        database_url,
        now=now,
        vault_address=settings.vault_address,
        vault_token=settings.vault_token,
        loop_factory=_loop_factory(),
    ).summary()


#: Why the acceptance checks run nothing in report-only mode.
AN_ACCEPTANCE_RUN_IN_REPORT_ONLY_MODE_CHECKS_NOTHING: Final = (
    "Report-only mode exists for controls that remove data, and the acceptance checks remove "
    "nothing: every write they make is rolled back. brain.ops.schedule never asks for it, and a "
    "runner that checked anyway when told to report would ignore the mode it was given."
)


def acceptance_run(now: datetime, report_only: bool, database_url: str) -> str:
    """Run the install acceptance checks when this commit is owed a run, and say what they found.

    `brain.ops.acceptance_run.run_acceptance_now` is the literal call the registry reads, with this
    process's settings for the cache, the vault and the tool source the checks ask. A run with a
    failed check raises after its results are written, so the worker records it as failed.
    Declines in report-only mode, see `AN_ACCEPTANCE_RUN_IN_REPORT_ONLY_MODE_CHECKS_NOTHING`, and
    takes the worker's event loop for the reason `spend_report_refresh` gives. `now` is the tick's;
    each check reads its own clock, because a check measures a window in real seconds.
    """
    del now
    if report_only:
        said = AN_ACCEPTANCE_RUN_IN_REPORT_ONLY_MODE_CHECKS_NOTHING
        return f"report only: no acceptance check was run. {said}"
    from brain.ops.acceptance_run import run_acceptance_now
    from brain.ops.worker import _loop_factory

    return run_acceptance_now(
        database_url, settings=settings_from(process_environment()), loop_factory=_loop_factory()
    )


#: Why a runner's `needs` names no function, task, person or decision.
A_JOBS_NEEDS_IS_WRITTEN_FOR_AN_ADMINISTRATOR: Final = (
    "A job's page shows what it is waiting for under Cannot start yet, on every install. Found "
    "on the owner's install on 2026-09-29: the restore rehearsal's sentence named the owner, two "
    "functions and an option letter. So the sentence says what is missing in words an "
    "administrator reads, and what a developer needs to build it is a comment in the source."
)


#: What each schedulable control still needs before it can be started, by name.
#:
#: Thirteen with a `run` since 2026-09-28, which the worker's schedule starts, and the rest saying
#: what they wait for, which is the point of the module header. Each `needs` is shown to an
#: administrator on the job's page, so since 2026-09-29 it is one plain sentence with no person,
#: code name or option letter in it (`A_JOBS_NEEDS_IS_WRITTEN_FOR_AN_ADMINISTRATOR`), and the
#: piece of work behind it, read from the entry point's own signature, is the comment above it.
RUNNERS: Final[tuple[Runner, ...]] = (
    Runner(name="retention_sweep", run=retention_sweep, workload=WorkloadClass.BATCH),
    # Wired on 2026-09-17. The askers are every live reach through the one resolver and one
    # the directory does not hold, and what they are compared over is the answer lane itself:
    # `brain.ops.canary_run` says why the store scan is the fixture suite's and not this run's.
    Runner(name="canary_run", run=canary_run, workload=WorkloadClass.BACKGROUND),
    # For whoever builds it: `drill_due` takes the last verification and `verification_of` reads
    # one, and no backup or verification is written by anything yet; needs-rupash item 44.
    Runner(
        name="restore_drill",
        needs=(
            "a record of each restore rehearsal and whether the copy it used could be read "
            "back, which this install does not keep yet"
        ),
    ),
    # For whoever builds it: the backup and verification sequences `alerts` takes, the rows the
    # nightly dump of needs-rupash item 44 would produce.
    Runner(
        name="backup_exposure",
        needs=(
            "a record of each backup taken and each check that one can be read back, which "
            "this install does not keep yet"
        ),
    ),
    # Wired on 2026-09-28: `brain.ops.denial_digest_run` reads the hour's refusals from the
    # ledger, resolves every live person's reach, and keeps what `digest` raises in the cache.
    Runner(name="denial_digest", run=denial_digest, workload=WorkloadClass.BATCH),
    # Wired on 2026-09-21 with `auth.staff_member`, `auth.staff_sync_run` and the staff source's
    # slot among the connector keys. See `brain.ops.staff_sync_run`.
    Runner(name="directory_sync", run=directory_sync, workload=WorkloadClass.BATCH),
    # Wired on 2026-09-15. `know.item` holds the items, the outbox is the log, and the rule
    # this sentence asked for is `brain.knowledge.item_store.route_for`. What it still does not
    # do is send: `brain.knowledge.item_store.NOTHING_SENDS_A_NAG_YET`.
    Runner(
        name="knowledge_reverification", run=knowledge_reverification, workload=WorkloadClass.BATCH
    ),
    # Wired on 2026-09-30 with `gate.escalation` (`0168`). See `brain.ops.escalation_store`.
    Runner(name="escalation_expiry", run=escalation_expiry, workload=WorkloadClass.BACKGROUND),
    # Wired on 2026-10-06 with `er.observation` (`0182`). See `brain.resolution.registry_store`.
    Runner(name="entity_resolution", run=entity_resolution, workload=WorkloadClass.BATCH),
    # Wired on 2026-10-06: the weekly fit over the registry's candidate pairs, kept as a setting
    # until a reviewer promotes it. See `brain.resolution.calibration_store`.
    Runner(
        name="resolution_calibration",
        run=resolution_calibration,
        workload=WorkloadClass.BATCH,
    ),
    # Wired on 2026-09-30: `brain.ops.recovery_run.sweep_queue` re-drives an orphaned or failed
    # job its task declares safe and sets aside the rest, over the worker's own queue connection.
    Runner(name="queue_redrive", run=queue_redrive, workload=WorkloadClass.BACKGROUND),
    # Wired on 2026-09-30: `brain.ops.recovery_run.resume_side_effects` reads back an interrupted
    # operation where its connector declares a read-back and lists the rest for a person.
    Runner(name="side_effect_resume", run=side_effect_resume, workload=WorkloadClass.BACKGROUND),
    # Wired on 2026-09-22 with `ops.provider_health` and the worker's read of the model provider
    # slots. See `brain.ops.model_probe_run`.
    Runner(name="model_health_probes", run=model_health_probes, workload=WorkloadClass.BACKGROUND),
    # For whoever builds it: the closest to wireable. `correct` already has a caller in
    # `brain.console.spend_view`; the estimate and actual figures for the period are assembled
    # when somebody opens the usage screen and by nothing on a schedule.
    Runner(
        name="spend_correction",
        needs=(
            "each period's estimated and actual spend, side by side, which is put together today "
            "only when somebody opens the Usage screen"
        ),
    ),
    # Wired on 2026-09-17, with the sender, the worker's reader of signing secrets and the
    # resolver `brain.ops.webhook_delivery` implements.
    Runner(name="outbox_dispatch", run=outbox_dispatch, workload=WorkloadClass.BACKGROUND),
    Runner(name="spend_report_refresh", run=spend_report_refresh, workload=WorkloadClass.BATCH),
    # Wired on 2026-09-17 with `ops.erasure_request`. See `brain.ops.erasure_store`.
    Runner(name="erasure_queue", run=erasure_queue, workload=WorkloadClass.BATCH),
    # Wired on 2026-09-17 with the installer's vault, the day it was registered.
    Runner(name="vault_token_renewal", run=vault_token_renewal, workload=WorkloadClass.BACKGROUND),
    # Wired on 2026-09-17 with `agent.automation_run`. See `brain.ops.automation_run_store`.
    Runner(name="automation_run", run=automation_run, workload=WorkloadClass.BACKGROUND),
    # Wired on 2026-09-17 with `ops.connector_sync`, the worker's reader of connector keys and the
    # readings `brain.ops.connector_sync` declares. See `brain.ops.connector_sync_run`.
    Runner(name="connector_sync", run=connector_sync, workload=WorkloadClass.BATCH),
    # Wired on 2026-09-17 with `ops.vault_access` and the worker overlay's read-only mount of the
    # vault's log. See `brain.ops.vault_audit_ship`.
    Runner(name="vault_audit_ship", run=vault_audit_ship, workload=WorkloadClass.BATCH),
    # Wired on 2026-09-28 with `ops.acceptance_result`. See `brain.ops.acceptance_run`.
    Runner(name="acceptance_run", run=acceptance_run, workload=WorkloadClass.BACKGROUND),
    # Wired on 2026-09-30 with its destination (`brain.ops.digest_destination`), the worker's
    # borrowed channel key (`brain.ops.channel_lease`) and the send (`brain.ops.digest_run`).
    Runner(name="evening_digest", run=evening_digest, workload=WorkloadClass.BATCH),
    # Wired on 2026-10-06 with `gate.approved_to_run` (`0176`). See `brain.ops.approved_runs`.
    Runner(name="approved_actions", run=approved_actions, workload=WorkloadClass.BACKGROUND),
)


def runner_for(name: str, runners: Sequence[Runner] = RUNNERS) -> Runner:
    """One runner by name, refusing an unknown one rather than answering None.

    Refuses for the reason `brain.deployment.installer.step_named` refuses: a caller handed
    None writes `if runner is None: return` and the control silently stops being scheduled,
    which is the failure this whole area exists to report.
    """
    for one in runners:
        if one.name == name:
            return one
    msg = f"no runner named {name!r}; the schedulable controls are {[r.name for r in runners]}"
    raise RunnerError(msg)


def start_control(name: str, *, now: datetime, report_only: bool, database_url: str) -> str:
    """Start one control by name, with a literal call the registry can read.

    See `A_RUNNER_IS_STARTED_BY_A_CALL_THE_REGISTRY_CAN_READ`. A name with a runner that cannot
    run yet is refused with the sentence saying what it needs, and a name with no runner at all
    is refused by `runner_for`, so a control added to the registry and not wired is a refusal
    that names the work rather than a run that silently does nothing.
    """
    match name:
        case "retention_sweep":
            return retention_sweep(now, report_only, database_url)
        case "knowledge_reverification":
            return knowledge_reverification(now, report_only, database_url)
        case "escalation_expiry":
            return escalation_expiry(now, report_only, database_url)
        case "entity_resolution":
            return entity_resolution(now, report_only, database_url)
        case "resolution_calibration":
            return resolution_calibration(now, report_only, database_url)
        case "spend_report_refresh":
            return spend_report_refresh(now, report_only, database_url)
        case "outbox_dispatch":
            return outbox_dispatch(now, report_only, database_url)
        case "erasure_queue":
            return erasure_queue(now, report_only, database_url)
        case "canary_run":
            return canary_run(now, report_only, database_url)
        case "vault_token_renewal":
            return vault_token_renewal(now, report_only, database_url)
        case "automation_run":
            return automation_run(now, report_only, database_url)
        case "connector_sync":
            return connector_sync(now, report_only, database_url)
        case "vault_audit_ship":
            return vault_audit_ship(now, report_only, database_url)
        case "directory_sync":
            return directory_sync(now, report_only, database_url)
        case "model_health_probes":
            return model_health_probes(now, report_only, database_url)
        case "denial_digest":
            return denial_digest(now, report_only, database_url)
        case "acceptance_run":
            return acceptance_run(now, report_only, database_url)
        case "queue_redrive":
            return queue_redrive(now, report_only, database_url)
        case "side_effect_resume":
            return side_effect_resume(now, report_only, database_url)
        case "evening_digest":
            return evening_digest(now, report_only, database_url)
        case "approved_actions":
            return approved_actions(now, report_only, database_url)
        case _:
            runner = runner_for(name)
            msg = (
                f"{name!r} cannot be started by this process: it needs {runner.needs}"
                if runner.run is None
                else f"{name!r} has a runner and no arm in start_control, so nothing starts it"
            )
            raise RunnerError(msg)


def runner_gaps(
    controls: Sequence[Control] | None = None, runners: Sequence[Runner] = RUNNERS
) -> tuple[str, ...]:
    """Every schedulable control this process cannot actually start, and what each needs.

    A report rather than a gate, in the shape `brain.ops.controls.orphans` takes and for the
    same reason: twelve of twelve are unwired today and a check asserting otherwise would be
    red on arrival and switched off within the week. What is a gate is the pair of
    disagreements below, which are green today and go red the moment the two lists drift.

    Reported in registry order rather than sorted, so the output reads in the same order as
    `handover_lines` and the two can be put beside each other.
    """
    every = schedulable(controls)
    known = {one.name for one in runners}
    found: list[str] = []

    for one in every:
        if one.name not in known:
            found.append(
                f"{one.name!r} is scheduled by this process and has no runner at all, so it "
                "would be found owed on every tick and started by nothing"
            )
            continue
        runner = runner_for(one.name, runners)
        if runner.run is None:
            found.append(f"{one.name!r} cannot be started yet: it needs {runner.needs}")

    for name in sorted(known - {one.name for one in every}):
        found.append(
            f"{name!r} has a runner and is not a control this process schedules, so the "
            "runner is either dead or the registry has moved it onto an external timer"
        )
    return tuple(found)


def lock_id(name: str) -> tuple[int, int]:
    """The advisory lock a control takes, as PostgreSQL's pair of 32-bit integers.

    Derived from the name with CRC32 rather than from a hand-kept table of numbers, because a
    table of numbers is a second place a control exists and the failure of a duplicate is two
    unrelated mechanisms silently serialising behind one lock.

    CRC32 rather than a cryptographic digest: this needs a stable 32-bit integer and nothing
    about it is a security property, and `hash()` is salted per process, which would give two
    replicas two different locks for one control. That is the bug this function exists to
    make impossible, so it is worth saying out loud.
    """
    if not name.strip():
        msg = "an unnamed control has no lock, and every caller of this would share one"
        raise RunnerError(msg)
    # Signed, because PostgreSQL's advisory lock arguments are signed 32-bit integers and a
    # value above 2^31 is refused rather than wrapped.
    unsigned = zlib.crc32(name.encode("utf-8"))
    return SCHEDULER_LOCK_NAMESPACE, unsigned - (1 << 32) if unsigned >= (1 << 31) else unsigned


def times_of_day(
    controls: Sequence[Control] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, AtTime]:
    """The time and zone each control owed at a time of day is read in, from the install's
    settings as saved, the environment, or the setting's own default, in that order.

    A value that is not a time on the 24-hour clock falls back to the declared default rather
    than stopping the control: the Settings screen refuses such a value, so one here came from an
    environment file, and a daily message at its default hour is better than none.
    """
    from brain.install import BY_NAME, value_of
    from brain.locale import time_zone

    found: dict[str, AtTime] = {}
    for one in schedulable(controls):
        if not one.daily_at:
            continue
        at = time_of_day(value_of(one.daily_at, env)) or time_of_day(BY_NAME[one.daily_at].default)
        if at is None:
            msg = f"{one.daily_at} declares a default that is not a time of day"
            raise RunnerError(msg)
        found[one.name] = AtTime(at=at, zone=time_zone(env))
    return found


def due_now(
    *,
    now: datetime,
    last_attempt: Mapping[str, datetime],
    last_success: Mapping[str, datetime],
    controls: Sequence[Control] | None = None,
    released: Sequence[str] = (),
    at: Mapping[str, AtTime] | None = None,
) -> tuple[Owed, ...]:
    """What is owed at `now`, with dueness on one clock and lateness on the other.

    `owed` is asked twice rather than given both maps, and that is deliberate: the policy
    module has one notion of a last run and giving it two would put this module's argument
    about failures inside a module that must not know what an outcome is. The dueness answer
    decides *what* is returned; the lateness answer supplies `late_by` and `first_run` for the
    ones that survived. See `TRIED_RECENTLY_AND_WORKING_ARE_DIFFERENT_CLOCKS`.
    """
    trying = owed(now=now, last_run=last_attempt, controls=controls, released=released, at=at)
    by_success = {
        one.name: one
        for one in owed(now=now, last_run=last_success, controls=controls, released=released, at=at)
    }
    # `report_only` is taken from this run's answer, and a mutation says the choice does not
    # matter today: `owed` computes it from the control's name and the released set, neither
    # of which depends on the instant or on the map it was given, so both answers agree for
    # every input. Recorded rather than tested around, because the equivalence is a property
    # of `owed` rather than of this line, and it would stop holding the day a release became
    # something with a date on it.
    return tuple(
        Owed(
            name=one.name,
            due_since=one.due_since,
            late_by=by_success[one.name].late_by if one.name in by_success else one.late_by,
            first_run=by_success[one.name].first_run if one.name in by_success else one.first_run,
            report_only=one.report_only,
        )
        for one in trying
    )


def stalled_runs(
    started: Mapping[str, datetime], *, now: datetime, after: timedelta = STALLED_AFTER
) -> tuple[str, ...]:
    """Controls whose newest run began and never recorded finishing, in name order.

    A row with a `started_at` and no `finished_at` is either a run still going or a process
    that died holding it. This does not distinguish them and does not pretend to: the lock
    does, because a dead process released its transaction and a live one has not. What this
    answers is which rows are old enough to be worth asking about, so a console can show the
    question rather than a number nobody can interpret.
    """
    if after <= timedelta(0):
        msg = f"a run is stalled after {after}, which is every run the moment it starts"
        raise RunnerError(msg)
    return tuple(sorted(name for name, at in started.items() if now - at > after))


def next_tick(*, now: datetime, tick: timedelta = TICK) -> datetime:
    """When the loop should wake next.

    Aligned to the tick rather than added to the current instant, so a tick that took four
    seconds does not push every later tick four seconds further out. Drift accumulated that
    way is what makes a one-minute control run every seventy seconds by the end of a day, and
    nothing reports it because every individual tick was on time.
    """
    if tick <= timedelta(0):
        msg = f"a tick of {tick} would wake the loop continuously"
        raise RunnerError(msg)
    since = (now - datetime.min.replace(tzinfo=UTC)) % tick
    return now + (tick - since)
