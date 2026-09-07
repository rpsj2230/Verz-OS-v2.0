"""The three install screens that can be built honestly, and the one that cannot.

An install screen is read by somebody deciding whether to worry. That is what separates this
group from the other three: nobody opens "This install" out of curiosity, they open it because
something is wrong or because they are about to promise a client that something is fine. So
the failure mode here is not a disclosure, it is a **field that is inferred and reads as
measured**, and the reader's whole reason for looking at it is that they intend to stop
looking after they have.

**Every fact on these screens is measured, declared, or absent, and the three are never
collapsed.** `Source` is that distinction and `Fact` carries it beside the value. A release
number read from the built image is measured. A migration head read out of the source tree is
declared: it is what the code expects the database to be on, and the interesting case is
exactly the one where those differ. A value nothing can supply is `UNKNOWN` and shows no
number at all, because a plausible number in that slot is worse than a blank one. See
`A_FIELD_CHECKED_BEFORE_DECIDING_NOT_TO_WORRY_IS_MEASURED`.

**M27.6.2 is not claimed, and that is the finding rather than an omission.** The leaf asks for
the last verified restore. Nothing in this repository takes a backup, nothing restores one, and
nothing records that a restore was ever tried: `brain.ops.storage` declares a `backups` bucket
and `ops/seaweedfs/provision.sh` creates it with a 35 day lifecycle rule, `brain.ops.retention`
derives `BACKUP_RETENTION_DAYS` from that rule, and `brain.ops.erasure.backup_horizon` does
arithmetic on the number so an erasure certificate can say what a deletion has not reached.
Every one of those is a statement about a lifecycle policy on an empty bucket. There is no
producer, no store, no verifier and no timestamp, and `brain.ops.install_from_empty.
RESTORE_SHAPED` is the only place `pg_restore` appears at all, in a guard that refuses an
install step naming somebody else's dump.

So a recovery panel built today would show a backup age it cannot compute beside a verified
restore that never happened, and it would be read as an assurance. `recovery_gaps` reports the
four things that have to exist first and a test asserts the finding is there, which is
`brain.console.agent_output.retention_enforcement_gaps`'s construction: a decision recorded as
a check rather than as a sentence in a commit message nobody re-reads. The leaf's id is not
repeated below, because those lines are parsed for ids and a sentence declining a leaf reads
to the parser exactly like claiming it.

**The migration level is the same trap one screen over, and it is nearly invisible.**
`brain.migrate.pending_revisions` opens a connection, asks the database what revision it is on,
computes the pending list and returns only the pending list; the current revision is read and
discarded. So the only runtime evidence anywhere is a boolean in the readiness check. A screen
that printed the head from `brain.ops.install_from_empty.read_plan` and headed the column
"migration level" would be printing what the code carries, which is the answer to a different
question and is right on every machine except the one where somebody is looking. `level_of`
takes the pending list when a caller has one and reports `DECLARED` when it does not, and it
reports `UNKNOWN` rather than a revision when the chain it was handed is not a single line.

**Capacity has the same shape a third time.** `brain.ops.wiring.budget_breaches` costs the
components a profile declares; `brain.ops.compose.deployment_mib` costs what the compose files
actually reserve. Those are two different numbers and `brain.ops.compose.unbudgeted_services`
exists because they disagree today. A capacity screen showing one of them under a heading that
implies the other is the same false assurance, so `memory_capacity` reports both, labelled,
and never derives one from the other.

**These screens are about the installation and never about the company's data**, which is why
almost nothing here filters by reach. `brain.console.screens` marks all four `company_wide` and
`for_department` leaves them out, which is M27.5.10 and is already built. The exception is the
throttling list: a rate limit names its subject, and `brain.ops.limits.LimitScope.PRINCIPAL`
means that subject is a person. A screen listing who is currently being throttled is a
directory of who is busy, so `throttled_now` filters by the limits screen's own capability in a
scope matching the row.

**Nothing here reads the environment.** `brain.install.value_of` is the one reader of an
installation value and `brain.ops.independence.second_readers` refuses a second, so the
identity of this install arrives through that function or not at all. That rule is why
`install_facts` takes an `env` mapping and hands it straight on rather than reaching for
`os.environ` itself.

Rejected: calling `brain.ops.release_manifest.read_manifest` from these functions. It reads a
file at a fixed path and returns `None` outside a built image, which is correct for it and
wrong here: a domain function that opened a file could not be tested for the case that
matters, which is the image where the manifest is missing and the screen must say so rather
than fall back to something plausible. The manifest is a parameter.

Rejected: a single `Install` record with a field per fact. It reads better and it makes the
absent case a `None` in a typed slot, which is exactly where a renderer supplies a dash, a
zero or the last known value. A tuple of `Fact` makes an absent fact a row that says why.

Scope: domain logic. Nothing here opens a connection, reads a clock or renders anything.

Task ids: M27.6.1, M27.6.3, M27.6.4
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.console.screens import screen
from brain.core.entitlement import EntitlementSet
from brain.core.scope import Scope
from brain.install import INSTALLATION, Belongs, belonging_to
from brain.ops.compose import ComposeFiles, deployment_mib, unbudgeted_services
from brain.ops.connections import DATABASES, demand_on, headroom_on
from brain.ops.inference import runs_inference_server
from brain.ops.install_from_empty import Revision
from brain.ops.limits import Limit, LimiterState, check
from brain.ops.release_manifest import ReleaseManifest
from brain.ops.wiring import (
    HOST_TOTAL_MIB,
    assert_known_profile,
    budget_breaches,
    components_for,
    runs_trace_ledger,
    wave_two_mib,
)

# ----------------------------------------------------------------- written-down reasons
#: Why every field on an install screen says where it came from.
A_FIELD_CHECKED_BEFORE_DECIDING_NOT_TO_WORRY_IS_MEASURED: Final = (
    "Nobody opens an install screen out of curiosity. They open it because something is "
    "wrong, or because they are about to tell somebody that nothing is, and then they stop "
    "looking. A field that was inferred from the source tree and rendered like a "
    "measurement is therefore not a small inaccuracy: it is the exact input to a decision "
    "to stop investigating. Measured, declared and unknown are three different answers and "
    "the third one shows no number, because a plausible number in that slot is worse than a "
    "blank one."
)

#: Why the recovery screen is not built.
A_BACKUP_TIMESTAMP_IS_NOT_A_VERIFIED_RESTORE: Final = (
    "A backup that has never been restored is a file whose readability nobody has tested, "
    "and the field on a console reading last verified restore is the one somebody checks "
    "before deciding not to worry. Nothing in this repository takes a backup, restores one "
    "or records that a restore succeeded. Showing the age of the newest object in a bucket "
    "under that heading would be a screen that answers the question it was not asked, in "
    "the reassuring direction, to the one reader who will act on it."
)

#: Why the migration level is not read out of the source tree.
THE_HEAD_THE_CODE_CARRIES_IS_NOT_THE_REVISION_THE_DATABASE_IS_ON: Final = (
    "brain.migrate.pending_revisions asks the database what revision it is on, computes the "
    "difference against the head the source declares, and returns only the difference; the "
    "current revision is read and discarded. So a console has no measured migration level "
    "to show, and the head from the source tree is right on every machine except one where "
    "somebody is looking, which is the machine where they are looking because it is behind."
)

#: Why capacity carries two figures rather than one.
WHAT_A_PROFILE_DECLARES_AND_WHAT_THE_COMPOSE_FILES_RESERVE_ARE_TWO_FIGURES: Final = (
    "brain.ops.wiring costs the components a profile declares and brain.ops.compose costs "
    "what the compose files actually reserve. They are different numbers and "
    "unbudgeted_services exists because they disagree today. A capacity screen showing one "
    "under a heading implying the other tells an operator they have headroom they do not "
    "have, or that they are over a ceiling they are not, and both send them to change the "
    "wrong thing."
)

#: Why a throttling list is filtered when the rest of this group is not.
A_RATE_LIMIT_NAMES_ITS_SUBJECT_AND_A_SUBJECT_IS_OFTEN_A_PERSON: Final = (
    "The other screens in this group are about the deployment and about nobody, which is "
    "why brain.console.screens marks them company_wide. A rate limit is different: its "
    "scope may be a principal, and a list of who is currently being throttled is a list of "
    "who is busy, with a number beside each name. So the rows are narrowed by the limits "
    "screen's own capability in a scope that matches the row, exactly as any other listing "
    "of people would be."
)


class InstallationError(Exception):
    """Raised when a fact about this deployment would be stated more firmly than it is known."""


# --------------------------------------------------------------------- how a fact is known
class Source(enum.StrEnum):
    """Where a statement about this deployment came from. Three, and the third shows nothing.

    Ordered narrow to wide in confidence, though nothing here compares them: an ordering
    would invite `>= DECLARED` to be written somewhere and read as "good enough", and the
    whole point is that a declared value answers a different question rather than the same
    question less well.
    """

    #: Read from the running system. A release stamped into the image, a pending list read
    #: from the database this process is connected to.
    MEASURED = "measured"
    #: Read from the source tree or the configuration. What this deployment is supposed to
    #: be, which is the answer to a different question.
    DECLARED = "declared"
    #: Nothing can supply this. Shows no value.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Fact:
    """One statement about this deployment, and how firmly it is known (M27.6.1).

    `source` is carried beside the value rather than left to a heading, because a heading is
    written once and the values under it change: the release is measured on a built image and
    unknown on a developer's machine, and the same column holds both.

    An unknown fact carries no value, refused in the constructor rather than left to a
    renderer. A renderer handed an unknown fact with a plausible string in it will show the
    string, and every one of the three ways it might mark it as uncertain is a convention
    somebody has to keep.
    """

    name: str
    source: Source
    value: str = ""
    #: One sentence saying what would have to exist for this to be measured. Required when
    #: nothing knows, because "unknown" alone sends the reader to look for a setting.
    because: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "a fact about nothing is not a fact"
            raise InstallationError(msg)
        if self.source is Source.UNKNOWN:
            if self.value:
                msg = (
                    f"{self.name} is unknown and carries {self.value!r}, which a renderer "
                    f"will show. {A_FIELD_CHECKED_BEFORE_DECIDING_NOT_TO_WORRY_IS_MEASURED}"
                )
                raise InstallationError(msg)
            if not self.because.strip():
                msg = (
                    f"{self.name} is unknown and does not say why, so the reader goes "
                    "looking for a setting that would not have helped"
                )
                raise InstallationError(msg)
            return
        if not self.value.strip():
            msg = (
                f"{self.name} claims to be {self.source.value} and carries no value, which "
                "is an unknown fact wearing a confident label"
            )
            raise InstallationError(msg)


# --------------------------------------------------- the migration level (M27.6.1)
@dataclass(frozen=True)
class MigrationLevel:
    """Which revision this database is on, or the admission that nothing here knows.

    `pending` is the count of revisions the database has not applied, and it is present only
    when a caller measured it. `head` is always the head the source declares, which is safe
    to show because it is labelled as what the code carries.
    """

    #: The revision the database is on, when that is measurable. Empty otherwise.
    revision: str
    #: The newest revision the source tree declares.
    head: str
    source: Source
    #: How many declared revisions have not been applied, when that was measured.
    pending: int = 0


def _chain(revisions: Sequence[Revision]) -> tuple[Revision, ...] | None:
    """The declared revisions in order, or `None` when they are not a single line.

    `None` rather than a best effort, because the interesting failure is a branch: two
    revisions sharing a parent is an alembic history somebody merged badly, and the head is
    then ambiguous. A screen picking one of two heads is picking the wrong one half the time
    and saying so with no qualification.
    """
    # Indexed by parent, so two revisions sharing one collapse into a single entry and the
    # walk below comes up short. There is no separate check for a duplicate parent, and that
    # is deliberate rather than an omission: the index can only lose entries, so the length
    # comparison at the end catches every branch, and a second guard would be a branch no
    # input could reach. `brain.console.reads.ConsoleRead` records removing the same shape.
    by_parent: dict[str | None, Revision] = {}
    for one in revisions:
        by_parent[one.down_revision] = one
    ordered: list[Revision] = []
    parent: str | None = None
    while parent in by_parent:
        found = by_parent[parent]
        ordered.append(found)
        parent = found.revision
    if len(ordered) != len(revisions):
        return None
    return tuple(ordered)


def level_of(
    revisions: Sequence[Revision], *, pending: Sequence[str] | None = None
) -> MigrationLevel:
    """What revision this install is on, as firmly as anything can say (M27.6.1).

    `pending` is what `brain.migrate.pending_revisions` returns, handed in by whoever opened
    the connection. Given it, the level is measured: the applied head is the last declared
    revision that is not waiting, which is exact for a linear history and is why `_chain`
    refuses a branched one.

    Without it the level is `DECLARED` and carries the source's head and no revision, because
    the head the code carries is not the revision the database is on. See
    `THE_HEAD_THE_CODE_CARRIES_IS_NOT_THE_REVISION_THE_DATABASE_IS_ON`.

    `UNKNOWN` for a history that is not a single line, with no head at all: a branched history
    has more than one and a screen showing either is showing a coin toss.
    """
    ordered = _chain(revisions)
    if ordered is None:
        return MigrationLevel(
            revision="",
            head="",
            source=Source.UNKNOWN,
        )
    head = ordered[-1].revision
    if pending is None:
        return MigrationLevel(revision="", head=head, source=Source.DECLARED)
    waiting = set(pending)
    applied = [one for one in ordered if one.revision not in waiting]
    return MigrationLevel(
        revision=applied[-1].revision if applied else "",
        head=head,
        source=Source.MEASURED,
        pending=len(waiting),
    )


# ------------------------------------------------- what a profile turns on (M27.6.1)
@dataclass(frozen=True)
class Feature:
    """One thing this profile turns on, and what runs because of it (M27.6.1).

    Named from the profile's own consequences rather than from a list written here, so a
    component added to `brain.ops.wiring.COMPONENTS` for a profile appears without anybody
    editing a second list. A feature list maintained by hand is one that is right on the day
    it is written.
    """

    name: str
    #: Whether this profile turns it on.
    on: bool
    #: The components that carry it, in registry order.
    components: tuple[str, ...] = ()


def features_of(profile: str) -> tuple[Feature, ...]:
    """What this profile turns on, derived from the modules that decide it (M27.6.1).

    `brain.ops.wiring.runs_trace_ledger` and `brain.ops.inference.runs_inference_server` are
    the two functions that already answer this, called rather than restated: each of them
    carries an argument about what the lite profile keeps and what it does without, and a
    console list repeating their answers would be a third opinion that drifts.

    Refuses an unknown profile, and refuses it through `brain.ops.wiring.components_for`
    rather than through a check of its own. That matters more than it looks: a mapping with a
    `get` and a default would report a mistyped profile as an install with every feature off,
    which reads as a broken deployment rather than as a broken argument. A second
    `assert_known_profile` here would be a guard no input could reach, which is the shape
    `brain.console.reads.ConsoleRead` records having removed, and a mutation of it survives
    because there is nothing behind it.
    """
    running = {one.name for one in components_for(profile)}
    return (
        Feature(
            name="trace ledger",
            on=runs_trace_ledger(profile),
            components=tuple(sorted(one for one in running if one.startswith("langfuse"))),
        ),
        Feature(
            name="local inference",
            on=runs_inference_server(profile),
            components=tuple(sorted(one for one in running if one == "inference-server")),
        ),
        Feature(
            name="background workers",
            on=any(one.startswith("brain-") for one in running),
            components=tuple(sorted(one for one in running if one.startswith("brain-"))),
        ),
    )


# ------------------------------------------------------------ this install (M27.6.1)
#: The installation surfaces an install screen may name, and the one it may not.
#:
#: Branding, models and storage say what this deployment is made of. Identity is left out on
#: purpose: `brain.install` marks the issuer and the redirect URIs required precisely because
#: a wrong one is a sign-in page that authenticates against somewhere else, and reading them
#: here would make `value_of` raise on an install that has not finished being set up, which is
#: the install whose screen somebody is most likely to be looking at.
NAMEABLE_SURFACES: Final[tuple[Belongs, ...]] = (Belongs.BRANDING, Belongs.MODELS, Belongs.STORAGE)


def install_facts(
    *,
    profile: str,
    manifest: ReleaseManifest | None,
    revisions: Sequence[Revision],
    pending: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[Fact, ...]:
    """What is actually running, each fact labelled with how firmly it is known (M27.6.1).

    `manifest` is `brain.ops.release_manifest.read_manifest`'s result, handed in. `None` is
    the ordinary case outside a built image and produces an unknown release rather than a
    fallback: a console that showed the working tree's commit on a developer's machine and
    the image's commit in production would be showing two different things under one heading.

    `env` is passed straight to `brain.install.belonging_to`, which calls `value_of`, which is
    the one reader of an installation value in this repository. Nothing here reads the
    environment and `brain.ops.independence.second_readers` is what holds that.

    Identity settings are not named. See `NAMEABLE_SURFACES`.

    **This is the one function here that has to check the profile itself.** It puts the
    profile on the screen and calls nothing that would refuse an unknown one, so without the
    check a mistyped deployment variable would be reported back as a fact about the install,
    and the screen would be the thing confirming the typo.
    """
    assert_known_profile(profile)
    facts: list[Fact] = [
        Fact(name="profile", source=Source.DECLARED, value=profile),
    ]
    if manifest is None:
        facts.append(
            Fact(
                name="release",
                source=Source.UNKNOWN,
                because=(
                    "no release manifest was written into this image, so nothing here can "
                    "say which commit is running"
                ),
            )
        )
    else:
        facts.append(Fact(name="release", source=Source.MEASURED, value=manifest.commit))
        facts.append(
            Fact(
                name="built at",
                source=Source.MEASURED,
                value=manifest.built_at.isoformat(),
            )
        )
    level = level_of(revisions, pending=pending)
    if level.source is Source.UNKNOWN:
        facts.append(
            Fact(
                name="migration level",
                source=Source.UNKNOWN,
                because=(
                    "the declared revisions are not a single line, so there is more than one "
                    "head and no single answer to show"
                ),
            )
        )
    elif level.source is Source.DECLARED:
        facts.append(
            Fact(
                name="migration level",
                source=Source.DECLARED,
                value=level.head,
                because=THE_HEAD_THE_CODE_CARRIES_IS_NOT_THE_REVISION_THE_DATABASE_IS_ON,
            )
        )
    else:
        facts.append(Fact(name="migration level", source=Source.MEASURED, value=level.revision))
    for surface in NAMEABLE_SURFACES:
        for name, value in sorted(belonging_to(surface, env).items()):
            facts.append(Fact(name=name, source=Source.DECLARED, value=value))
    return tuple(facts)


# ------------------------------------------------- rate limits and throttling (M27.6.3)
@dataclass(frozen=True)
class ThrottleRow:
    """One ceiling that is currently refusing, as this reader may see it (M27.6.3).

    Carries the limit and how long the subject has to wait, and no count of the requests that
    were refused. `brain.ops.limits.REFUSED_REQUESTS_DO_NOT_EXTEND_THE_WINDOW` is the rule
    about what a refusal does to the window; the rule here is about what a screen may say
    about somebody else's afternoon, and a refusal count beside a person's name is that.
    """

    scope: str
    subject: str
    limit: int
    retry_after_seconds: float


def _limit_row(one: Limit) -> dict[str, str]:
    """The fields a rate limit grant's scope may be written against.

    The scope and the subject, which are the two things a limit names. The period is left out:
    a grant scoped to per-minute limits and not per-day ones would hide the ceiling somebody
    is actually stuck behind, and there is no reason anybody would write one on purpose.
    """
    return {"scope": one.scope.value, "subject": one.subject}


def throttled_now(
    limits: Sequence[Limit],
    state: LimiterState,
    reader: EntitlementSet,
    *,
    now: datetime,
) -> tuple[ThrottleRow, ...]:
    """Which ceilings are refusing right now, filtered to what this reader may see (M27.6.3).

    `brain.ops.limits.check` decides whether a limit is over, called once per limit rather
    than reimplemented: the sliding window's pruning and its retry arithmetic are the audited
    part, and a console that counted hits itself would be a second window that disagrees at
    the boundary, which is the only place it matters.

    Narrowed by the limits screen's own capability in a scope matching the row. See
    `A_RATE_LIMIT_NAMES_ITS_SUBJECT_AND_A_SUBJECT_IS_OFTEN_A_PERSON`: this is the one screen
    in the group whose rows are about people rather than about the machine.
    """
    where: Scope | None = reader.scope_for(screen("limits").read.requires, now)
    if where is None:
        return ()
    found: list[ThrottleRow] = []
    for one in limits:
        if not where.matches(_limit_row(one)):
            continue
        decision = check(now=now, limits=(one,), state=state)
        if decision.allowed:
            continue
        found.append(
            ThrottleRow(
                scope=one.scope.value,
                subject=one.subject,
                limit=one.limit,
                retry_after_seconds=decision.retry_after_seconds,
            )
        )
    return tuple(found)


# -------------------------------------------------------------------- capacity (M27.6.4)
@dataclass(frozen=True)
class MemoryCapacity:
    """What this profile wants against what the host has, and what is deployed (M27.6.4).

    Two figures for what is running rather than one. See
    `WHAT_A_PROFILE_DECLARES_AND_WHAT_THE_COMPOSE_FILES_RESERVE_ARE_TWO_FIGURES`: the declared
    figure is what `brain.ops.wiring` costs from the component register and the deployed
    figure is what the compose files actually reserve, and the gap between them is a real
    finding rather than rounding.

    `breaches` carries the sentences `budget_breaches` produces, unchanged. Rewording them
    would put the arithmetic's conclusion in two places.
    """

    profile: str
    host_total_mib: int
    #: What the components this profile declares cost on top of the baseline. Zero for the
    #: lite profile, which declares none: `brain.ops.wiring.PRODUCTION_BASELINE_MIB` already
    #: holds what the base compose file costs, and adding it here would count the same
    #: containers twice on every profile.
    declared_mib: int
    #: What the compose files reserve, when compose files were handed in.
    deployed_mib: int | None
    #: The budget findings, verbatim.
    breaches: tuple[str, ...]
    #: Services that reserve memory and are in no component's budget, verbatim.
    unbudgeted: tuple[str, ...]


def memory_capacity(profile: str, files: ComposeFiles | None = None) -> MemoryCapacity:
    """Memory, declared against deployed, for one profile (M27.6.4).

    `files` is optional and its absence produces `None` rather than a copy of the declared
    figure, which is the same rule `Fact` applies to an unknown value: a deployed figure equal
    to the declared one by construction would read as agreement between two independent
    numbers, and agreement is exactly what somebody opens this screen to check.

    An unknown profile is refused by `wave_two_mib` and by `budget_breaches`, both of which
    assert it, so there is no check of its own here for the reason `features_of` gives.
    """
    return MemoryCapacity(
        profile=profile,
        host_total_mib=HOST_TOTAL_MIB,
        declared_mib=wave_two_mib(profile),
        deployed_mib=None if files is None else deployment_mib(files),
        breaches=budget_breaches(profile),
        unbudgeted=() if files is None else unbudgeted_services(profile, files),
    )


@dataclass(frozen=True)
class ConnectionCapacity:
    """One database's connection ceiling against what its declared clients want (M27.6.4).

    `demand` is over the clients this repository declares. A client nothing declares is not
    counted and cannot be: `brain.ops.connections.undeclared_clients` is the check for that
    and it takes the connection strings somebody parsed out of a compose file, which is a
    different input from anything available here.
    """

    database: str
    #: What the server will admit, after its own reserved connections.
    admissible: int
    #: What the declared clients would open at full pool.
    demand: int
    #: What is left for a backup, a migration or a diagnosis.
    headroom: int


def connection_capacity() -> tuple[ConnectionCapacity, ...]:
    """Every database's connection budget, in declaration order (M27.6.4).

    `brain.ops.connections` holds the arithmetic and this reads it. There is no branch here
    and no second sum: `demand_on` and `headroom_on` are the module's own functions, and a
    console recomputing either would be a second answer to how close this deployment is to
    running out of connections.
    """
    return tuple(
        ConnectionCapacity(
            database=one.name,
            admissible=one.admissible(),
            demand=demand_on(one.name),
            headroom=headroom_on(one.name),
        )
        for one in DATABASES
    )


# ------------------------------------------------------------------------- the diagnostic
#: What would have to exist before a recovery screen could be built.
#:
#: Four things, in the order they have to happen. Written as a list rather than a paragraph
#: so a later reader can tell how much of it has appeared since, which a paragraph makes
#: surprisingly hard.
RECOVERY_NEEDS: Final[tuple[str, ...]] = (
    "something that takes a backup and records when it did",
    "something that restores the newest backup into a scratch database",
    "a smoke query and a permission canary run against the restored copy",
    "a record of when that last succeeded, and how long it took",
)


def recovery_gaps() -> tuple[str, ...]:
    """Why the backup and recovery screen is not built. See
    `A_BACKUP_TIMESTAMP_IS_NOT_A_VERIFIED_RESTORE`.

    Kept apart from every check that must be green, exactly as
    `brain.console.screens.unregistered_tools` is: this one is expected to stay non-empty
    until M30 lands, and a diagnostic that is red for a month is one somebody switches off.

    Returns one finding per missing piece rather than one summary, so the day two of the four
    exist the list gets shorter and says which two.
    """
    return tuple(
        f"the recovery screen needs {one}, and nothing in this repository does it"
        for one in RECOVERY_NEEDS
    )


def installation_gaps(
    *,
    facts: Iterable[Fact] = (),
    profiles: Iterable[str] = (),
) -> tuple[str, ...]:
    """Everything about an install screen that would state a fact more firmly than it is known.

    Takes its inputs rather than reading module constants, for the reason
    `brain.console.govern.govern_gaps` gives: a diagnostic that can only run against the
    healthy tree has nothing to report, so switching off any of its refusals changes nothing
    observable and every one of them survives a mutation.

    Three checks. The first two are about facts a caller assembled; the third is about a
    profile whose declared components cost more than the host has, which is the finding
    `budget_breaches` produces and which an install screen is the natural place to ignore.
    """
    findings: list[str] = []
    identity = {one.name for one in INSTALLATION if one.belongs is Belongs.IDENTITY}
    seen: dict[str, int] = {}
    for one in facts:
        seen[one.name] = seen.get(one.name, 0) + 1
        if one.name in identity:
            findings.append(
                f"{one.name} is an identity setting and is on the install screen. The issuer "
                "and the redirect URIs have no safe default precisely because a wrong one "
                "signs people in against somewhere this install does not own, and naming "
                "them here raises on the half-configured install this screen is opened on"
            )
    findings.extend(
        f"{name} appears on the install screen {count} times, and which value a reader "
        "believes depends on which row they read first"
        for name, count in seen.items()
        if count > 1
    )
    for profile in profiles:
        findings.extend(f"profile {profile!r}: {one}" for one in budget_breaches(profile))
    return tuple(findings)
