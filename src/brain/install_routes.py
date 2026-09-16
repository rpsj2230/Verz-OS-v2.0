"""The five install screens over HTTP: what this deployment is, and what it cannot say yet.

`brain.console.installation`, `brain.console.version_view` and `brain.console.recovery_view`
decide what these screens may show and render nothing. Until this module they were reachable
from no address at all: `brain.ops.console_screens` counts that as a screen nobody has, and it
named all three on every run of the traceability sweep. This is the half that makes them
openable, and it adds no second opinion about any of them. Every shape below is a projection
of a value one of those modules produced.

**A ninth router rather than more routes on `brain.api_routes`, and the refusal is why.**
`api_routes` answers about entities, where a name is a thing a caller can guess and enumeration
is the leak; `brain.routing_routes` answers about the model chain, where it is not. These
answer about the deployment itself: there is no name to guess, no row belonging to anybody, and
four of the five surfaces take no session because nothing they show is in the database. The
`asking` dependency is imported from `api_routes` rather than re-declared, so there is one
spelling of it and a route here cannot acquire a subtly different one.

**The capabilities are read out of the screen registry and are not declared again.**
`brain.console.screens` already says what each of these screens requires, `Screen.__post_init__`
holds a screen to a read that audits itself under the same key, and a capability spelled a
second time here is the copy that survives a change to the first. `MATRIX_READ` in
`brain.routing_routes` is a capability that belongs to no screen and is rightly declared where
it is used; these belong to five screens that already exist. See
`A_SECOND_SPELLING_OF_A_CAPABILITY_IS_THE_ONE_THAT_GOES_STALE`.

**The capability is checked before anything is read, and the order is the property.** Copied
from `brain.routing_routes` deliberately: a caller holding no grant is refused identically on an
install whose migration tree is readable and on one whose is not, and only somebody who may read
a surface can find out anything about how this process is wired. Checking the wiring first would
answer one thing to the unentitled on a healthy install and another on a broken one, which makes
the deployment's state readable by anybody who can reach the port.

**A source this process cannot reach answers with no panel and a sentence, never with an empty
one.** This is the rule the whole group turns on and it is the same rule
`brain.console.installation.A_FIELD_CHECKED_BEFORE_DECIDING_NOT_TO_WORRY_IS_MEASURED` states one
layer down. A recovery panel built from no observations answers `NOTHING_COPIED`, which is a
statement about an install rather than about a reader, and it is false here: nothing copied and
nobody looked are two different facts and only one of them was established. A throttling list
built from no window state is empty, and an empty list of who is being throttled reads as
nobody. So each surface that depends on something this process does not hold answers `unread`
with the reason, the panel is absent rather than defaulted, and the screen renders the sentence.
See `AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE`.

**Two of the five are unread on every install today and the module says which and why.** The
backup bucket has no reader: `brain.ops.storage.StorageBackend` is a protocol with no
implementation anywhere in this repository, which `brain.ops.retention_store` already records
about itself. The live rate-limit windows have no enumerator: `brain.ops.limit_store.
ValkeyWindowStore` checks and records the keys it is handed and offers no way to ask which
windows exist, so there is nothing to build a throttling list from. Both are read off
`app.state` through a protocol, so the day somebody wires either one the sentence stops being
returned without a line of this module changing. That is `brain.console.installation.
recovery_gaps`'s construction: a decision recorded as a check rather than as a sentence in a
commit message nobody re-reads.

**The migration level is answered as declared, and that is a choice with a cost.**
`brain.migrate.pending_revisions` opens a synchronous engine of its own, outside the application
pool, so calling it from a request would put a connection nobody budgeted for behind every load
of this screen and `brain.ops.connections` is the module that would be wrong about it
afterwards. Without a pending list `level_of` reports `DECLARED` and carries the sentence
`THE_HEAD_THE_CODE_CARRIES_IS_NOT_THE_REVISION_THE_DATABASE_IS_ON`, which is the honest weaker
answer rather than a plausible stronger one. `brain.app` measures the same thing once at startup
into `app.state.ready["migrations"]` as a boolean, which is a different question.

**One address per screen and no parameter on any of them.** `brain.routing_routes` gives a rung
an address because a rung is a thing a person opens and sends to somebody; none of these screens
has a sub-object, so a path segment here would be an address for something that does not exist.
The console's own addresses are the screen keys, which is what `brain.ops.console_screens.
routed_screen_keys` reads out of `console/src/App.tsx`, so the two lists are the same list.

**Rate limits is the one screen in this group withheld from a department admin's menu, and this
router is not where that happens.** `brain.console.screens.NOT_AT_DEPARTMENT_SCOPE` names it and
`brain.console.screens.for_department` drops it, and that function's own docstring says what it
is not: a caller holding `read:rate_limit` reaches the address whatever the menu says, because
the tool decides that. What narrows the answer is
`brain.console.installation.throttled_now`, which matches each row against the scope the
reader's own grant carries: `_limit_row` offers `{scope, subject}`, `Clause.matches` refuses a
field the row does not have, so a department-scoped grant matches no row and the list is empty
with no count of what was dropped. The other four screens in this group are offered at a
department's scope, deliberately, and
`tests/unit/test_screens.py::test_a_department_admin_is_offered_every_screen_but_the_one_that_
would_disclose` is where that decision is pinned. See
`AN_INSTALL_SCREEN_IS_THE_SAME_FACT_FOR_EVERYBODY_AND_A_THROTTLING_LIST_IS_NOT`.

**No count of anything, and no total on any of these.** The throttling list is the one
collection here a reader's grant narrows, so it is the one where a number would be a
subtraction; the ceilings, the copies and the connection budgets are identical for every caller
who may read them at all. The rule is kept on all four rather than on the one that needs it, for
the reason `brain.routing_routes.THE_MATRIX_IS_NOT_FILTERED_PER_CALLER` gives: a console keeps
one rule about counts, and a screen that counted where it was harmless is the worked example
somebody copies onto a screen where it is not.

Rejected: one `/install` answering all five surfaces. It is one request instead of five and it
makes the slowest surface the cost of the fastest: a release feed with a ten second timeout
would be in front of the capacity figures, which need nothing but arithmetic. It also gives a
caller holding one of the five capabilities an answer assembled from the other four or a refusal
that depends on which they hold, and both are worse than five addresses each with one refusal.

**The release list is never awaited here, and until 2026-09-16 it was.** The updates route
asked the list in a thread and waited, so a slow or silent list put its whole timeout in front of
the screen on every load. It now reads `brain.deployment.release_feed.ReleaseWatch`, which answers
from the last look that finished and starts the next one beside the request when one is due. The
watch is one per application object, attached the first time the screen is opened rather than
built with the application, so a process whose screen nobody opens holds nothing and asks
nothing. See `release_feed.A_PAGE_NEVER_WAITS_FOR_THE_RELEASE_LIST`.

Rejected: reading the release feed on a timer into a cache. A timer asks on a server nobody is
looking at, and the second item on `WHAT_A_RELEASE_CHECK_WOULD_SEND` is exactly that record of
when a server is up. A look started by opening the screen, and no more often than
`release_feed.LOOK_AGAIN_AFTER`, has a reader for every request that leaves. See
`release_feed.A_LOOK_IS_STARTED_BY_A_READER_AND_NOT_BY_A_TIMER`.

Rejected: a write anywhere in this module. M30.3.9 asks for a one-click drill and
`brain.console.recovery_view` declines to claim it in those words: the drill is a write, no
console module performs one, and what the panel answers is whether a drill is owed. A POST here
would be this module deciding that, from the side that renders.

Scope: five read-only routes. Nothing here writes, and the only session anything here would need
is the one it deliberately does not open.

Task ids: M27.7.25, M27.7.27, M42.3.9
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Final, Protocol, cast

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, model_validator

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.installation import (
    ConnectionCapacity,
    Fact,
    MemoryCapacity,
    ThrottleRow,
    connection_capacity,
    install_facts,
    memory_capacity,
    throttled_now,
)
from brain.console.reads import permitted
from brain.console.recovery_view import CopyState
from brain.console.recovery_view import Panel as RecoveryPanel
from brain.console.recovery_view import panel as recovery_panel
from brain.console.screens import screen
from brain.console.version_view import Panel as UpdatesPanel
from brain.console.version_view import Running, Told, Unanswered, running_release
from brain.console.version_view import panel as updates_panel
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.deployment.release_feed import ReleaseWatch, feed_address
from brain.ops.admission import Ceiling
from brain.ops.backup_manifest import read_drills, read_manifests
from brain.ops.install_from_empty import read_plan
from brain.ops.limits import Limit, LimiterState, ceilings
from brain.ops.release_manifest import read_manifest
from brain.settings import Settings

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why the capabilities are read out of the registry rather than written here.
A_SECOND_SPELLING_OF_A_CAPABILITY_IS_THE_ONE_THAT_GOES_STALE: Final = (
    "brain.console.screens already says what each of these five screens requires, and a "
    "Screen refuses to be built against a read that audits itself under another key, so the "
    "registry is the one place the pairing is held. A capability string retyped here would "
    "be correct on the day it was typed and would survive a change to the registry without "
    "anything comparing the two, and the failure is silent in the permissive direction: the "
    "route would go on answering under a capability the screen no longer requires."
)

#: Why the check is the registry's own function and not a `holds` call on the capability.
A_SCREENS_CAPABILITY_IS_HALF_OF_WHAT_IT_ASKS_FOR: Final = (
    "brain.console.reads.permitted takes two things and this router needs both: the tool's "
    "own capability, which is what an agent making the same call would need, and the console "
    "plane, which is what the console adds on top. A route checking only the first would "
    "answer a caller who may know that something exists with the configuration of it, which "
    "is the distinction the three planes exist to draw, and it would do so while looking "
    "exactly like a correct capability check. So the check is the registry's function, called "
    "once, and this module holds no opinion about what permits a console read."
)

#: Why a surface whose source is missing answers a sentence rather than an empty panel.
AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE: Final = (
    "A recovery panel built from no observations answers that nothing has been copied, and a "
    "throttling list built from no window state is empty, which reads as nobody being "
    "throttled. Both are statements about the install, and neither was established: what "
    "happened is that this process holds nothing that could look. Nothing copied and nobody "
    "looked are different facts, and on a screen somebody reads before deciding whether to "
    "worry the difference is the whole value of the screen. So a surface whose source is not "
    "on this process answers with no panel at all and a sentence naming what is missing, and "
    "the absence is refused in the model rather than left to whatever draws it."
)

#: Why four of these screens are a department admin's and the fifth is not.
AN_INSTALL_SCREEN_IS_THE_SAME_FACT_FOR_EVERYBODY_AND_A_THROTTLING_LIST_IS_NOT: Final = (
    "Which release is running, what the last backup reaches, and how many connections the "
    "declared clients want are one fact each about the deployment, identical for everybody on "
    "it and belonging to nobody. A department-scoped reader learns nothing from them that is "
    "not theirs. Who is currently being throttled is a list of people with a number beside "
    "each name, and brain.ops.limits.LimitScope has no department member, so a grant narrowed "
    "to one department matches no throttling row and an unrestricted one matches every row in "
    "the company. That is why brain.console.screens withholds exactly one of these five from a "
    "department admin's menu, and why this router refuses none of them: the menu is a menu, "
    "the rows are narrowed by the reader's own grant, and the answer at a department's scope "
    "is a page with nothing on it and no count of what was left off."
)

#: Why the migration level on this screen is declared rather than measured.
A_CONNECTION_OPENED_OUTSIDE_THE_POOL_IS_A_CONNECTION_NOBODY_BUDGETED: Final = (
    "brain.migrate.pending_revisions builds a synchronous engine, connects, asks the database "
    "what revision it is on and disposes of it. Called from a request that is the one "
    "connection on this process that brain.ops.connections did not count, arriving once per "
    "load of a screen whose whole subject is whether this deployment has headroom. So the "
    "pending list is not asked for here and the level is reported as declared, carrying the "
    "sentence that says the head the code holds is not the revision the database is on."
)


# ------------------------------------------------------------------ the capabilities

#: What is actually running: the release, the migration level, the profile.
INSTALL_READ: Final[Capability] = screen("install").read.requires

#: Which release this install is on and whether anything newer has been recorded. Shares
#: `read:release` with the screen above, which `brain.console.screens` argues for by name:
#: `Capability.covers` expands only a trailing `.*`, so a capability of its own would be
#: unreachable from every grant an install has already written.
UPDATES_READ: Final[Capability] = screen("updates").read.requires

#: The copies, the last verified restore and whether a rehearsal is owed.
RECOVERY_READ: Final[Capability] = screen("recovery").read.requires

#: The ceilings on requests, and who is behind one right now.
LIMITS_READ: Final[Capability] = screen("limits").read.requires

#: Connections, memory and pool sizes against what is deployed.
CAPACITY_READ: Final[Capability] = screen("connections").read.requires


# ------------------------------------------------------- what is not on this process

#: What the recovery surface answers while nothing here can read the backup bucket.
#:
#: Written as the sentence a client reads rather than as a module name, for the reason
#: `brain.console.recovery_view.ANSWERS` are: the reader has a server and no source tree.
NOTHING_HERE_READS_THE_BACKUP_BUCKET: Final = (
    "This process cannot read the place your copies and your rehearsal records are kept, so "
    "nothing on this screen is a statement about them. It is not that no copy exists and not "
    "that no rehearsal has run: it is that nothing here has looked. Until that is wired, find "
    "out by hand whether a restore has been rehearsed, and assume you cannot recover until one "
    "has."
)

#: What the rate limits surface answers about the throttling half while nothing enumerates it.
NOTHING_HERE_ENUMERATES_THE_LIVE_WINDOWS: Final = (
    "The ceilings above are what this install applies. Which of them is refusing somebody "
    "right now cannot be read here: the store that holds the counting windows answers about a "
    "window it is handed and offers no way to ask which windows exist. An empty list would "
    "read as nobody being throttled, so there is none."
)


class BackupObjects(Protocol):
    """Every object in the backup bucket, as name and content pairs.

    The shape `brain.ops.backup_manifest.read_manifests` and `read_drills` both take, so a
    process that grows one reader satisfies both halves at once and cannot end up confident
    about rehearsals and cautious about copies, which
    `brain.console.recovery_view.panel` names as the wrong way round.

    A protocol read off `app.state` rather than a parameter, because there is nothing to pass:
    `brain.ops.storage.StorageBackend` has no implementation in this repository and
    `brain.ops.retention_store` already records that about itself. What this buys is that the
    sentence above stops being returned on the day somebody attaches one, with nothing here
    changing, which is the difference between a check and a comment.
    """

    def __call__(self) -> Iterable[tuple[str, str]]: ...


class ThrottleSource(Protocol):
    """The live rate limits and the window state they are counted in, at one instant.

    Both together, because `brain.console.installation.throttled_now` needs both and a caller
    that had one would have to invent the other. `brain.ops.limit_store.ValkeyWindowStore`
    supplies neither: it checks and records the keys it is handed, which is the whole of what
    the request path needs, and enumerating the windows in the store is a different operation
    against a key space nobody has designed.
    """

    def __call__(self, now: datetime) -> tuple[Sequence[Limit], LimiterState]: ...


def backup_objects_of(request: Request) -> BackupObjects | None:
    """The bucket reader this process was built with, or None.

    `getattr` rather than attribute access, in the shape `brain.routing_routes.sessions_of`
    uses and for its reason: a test may construct a bare application to exercise one route,
    and an `AttributeError` there reaches a caller as a 500 that reads like a bug in the gate
    rather than like a process built without a reader.

    A `cast` after a `callable` check rather than an `isinstance` against the protocol, and the
    reason is that the `isinstance` would be weaker than it looks: a runtime-checkable protocol
    whose only member is `__call__` admits every function in the process, so the check would
    read as structural and be a callable check with more words. The attribute's name is what
    discriminates, the `callable` is what stops a string being invoked, and this comment is the
    proof the structural match was not made rather than being assumed.
    """
    found = getattr(request.app.state, "backup_objects", None)
    return cast(BackupObjects, found) if callable(found) else None


def throttle_source_of(request: Request) -> ThrottleSource | None:
    """The live-window reader this process was built with, or None. Same shape, same reason."""
    found = getattr(request.app.state, "throttle_source", None)
    return cast(ThrottleSource, found) if callable(found) else None


def release_watch_of(request: Request) -> ReleaseWatch:
    """This application's watch on the release list, attached the first time anybody asks.

    Attached here rather than in `brain.app.create_app`, because the only thing that reads it is
    this screen and a watch is state: a process whose updates screen is never opened holds
    none and starts nothing. Replaced when the attribute holds anything else, for the reason
    `backup_objects_of` treats a wrong shape as none: a test or a process that attached a value
    of the wrong kind gets a working watch rather than an `AttributeError` reaching a caller.
    """
    found = getattr(request.app.state, "release_watch", None)
    if isinstance(found, ReleaseWatch):
        return found
    made = ReleaseWatch()
    request.app.state.release_watch = made
    return made


def settings_of(request: Request) -> Settings:
    """The settings this application was created with, or a process-level fault.

    `brain.app.create_app` attaches them before any router is mounted, so unlike the readers
    above this is not optional: an absence is a process built by something other than
    `create_app`, which is broken rather than unconfigured. A `Settings()` constructed here
    instead would read the environment a second time and answer about a profile nobody
    deployed, which is the exact failure `install_facts` refuses when it checks the profile
    itself, and `brain.ops.independence` is the sweep that refuses a second reader.

    A `Failed` rather than an `Absent`, for the reason `brain.routing_routes._require_sessions`
    gives: only a caller who already holds the capability reaches this line.
    """
    found = getattr(request.app.state, "settings", None)
    if not isinstance(found, Settings):
        raise Failed("no settings on this process")
    return found


# ------------------------------------------------------------------------ the shapes


class FactView(BaseModel):
    """One statement about this deployment, with how firmly it is known.

    `brain.console.installation.Fact`, copied field by field. `source` travels beside the
    value rather than being implied by a heading, which is that class's whole argument: the
    same column holds a release measured from an image and a release nothing reported.

    `because` is carried on every fact and not only on the unknown ones. `Fact` requires it
    when nothing knows and permits it otherwise, and several of the facts this router returns
    use it to say what a measured value is a measurement of, which is the distinction between
    the commit an image was built from and the release a client can look up.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source: str
    value: str
    because: str


def fact_view(one: Fact) -> FactView:
    """One fact, copied field by field.

    Written out rather than built from `__dict__`, for the reason
    `brain.routing_routes.view_of` gives about its own: a field added to `Fact` would
    otherwise arrive in a response because a copy loop was generous.
    """
    return FactView(name=one.name, source=one.source.value, value=one.value, because=one.because)


class InstallView(BaseModel):
    """What is actually running, as a list of labelled statements.

    A list of facts rather than an object with a field per fact, which is
    `brain.console.installation`'s own rejected alternative and its reason: a typed slot is
    exactly where a renderer supplies a dash, a zero or the last known value, and a fact that
    says why it is unknown cannot be rendered as any of those.

    No count and no total. The facts are the same for every caller who may read them at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    facts: list[FactView]


class RunningView(BaseModel):
    """Which release this install is on, or why nothing here will name one.

    `brain.console.version_view.Running`, whose constructor refuses a tag and a reason
    together. The two fields travel as they were built rather than being collapsed into one
    nullable string, because a caveat beside a version number is read as a version number and
    a single field would leave whatever draws this deciding which of the two it had.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tag: str
    facts: list[FactView]
    cannot_say: str
    #: The commit the running image was built from. Drawn under its own label, never as `tag`.
    commit: str


class ToldView(BaseModel):
    """The newest release somebody has named, when they named it, and who they were.

    `by` is not decoration. `brain.console.version_view.Told` refuses a telling with nobody
    named, because an administrator who read the release notes this morning and a value typed
    once during setup are worth very different amounts and render identically without it.

    `notes` is an https address or empty, refused by `Told` before it reaches this model, so
    what a console draws as a link has had its scheme decided once, on the server.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tag: str
    at: str
    by: str
    notes: str


class UnansweredView(BaseModel):
    """An install that was set to ask and got no answer, with the reason.

    Kept apart from a telling rather than folded into its absence, because the remedy differs:
    nobody has said sends a reader to record a release, and the list did not answer sends them
    to check a firewall. Neither is a tick.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    why: str
    detail: str
    at: str


class UpdatesView(BaseModel):
    """Where this install stands against the newest release anybody has named.

    `says` and `what_to_do` are `brain.console.version_view.ANSWERS`, sent rather than derived
    in a browser. A console mapping a standing to a sentence would be a second vocabulary for
    a closed set of nine, out of step with this one within a release, and the one screen where
    that matters most is the one a client reads before deciding they are patched.

    `told` and `unanswered` are never both set. The panel holds one value of a union and
    splitting it here rather than sending a tagged object keeps the two shapes distinct in the
    schema a console generates its types from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    running: RunningView
    told: ToldView | None
    unanswered: UnansweredView | None
    standing: str
    says: str
    what_to_do: str
    told_days_ago: int | None
    goes_off_after_days: int


class CopyStateView(BaseModel):
    """One coverage: what the schedule intends, what has been copied, and whether that is inside
    the promise.

    Always present for every coverage, including the ones nothing copies.
    `brain.console.recovery_view.copy_states` returns a row per coverage for that reason: a
    coverage left out is an absence a reader has to notice by counting, and every absence on
    this screen is one somebody would read as a blank.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    coverage: str
    facts: list[FactView]
    within_objective: bool
    objective_seconds: int


class UnreadableView(BaseModel):
    """One record in the bucket that could not be read, named so somebody can go and look."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    where: str
    why: str


class RecoveryPanelView(BaseModel):
    """The copies, the last verified restore, and one verdict computed from both.

    `last_verified` is a fact rather than a nullable timestamp, which is the single decision
    `brain.console.recovery_view` exists to make: a renderer handed `None` under this heading
    draws a dash, a dash reads as not applicable beside a fresh backup date, and the reader
    stops looking at the worst state this system has.

    There is no boolean anywhere on this model. A boolean is what a renderer draws as a tick,
    and seven of the eight answers would collapse into its false branch and draw the same grey
    nothing for a rehearsal that failed last night and one that is three days overdue.
    `drill_is_due` is the exception and is not that: it is one of the panel's inputs rather
    than its verdict, and it is refused in the reassuring answer rather than summarising it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: str
    copies: list[CopyStateView]
    last_verified: FactView
    measured_rto_seconds: float | None
    assurance: str
    says: str
    what_to_do: str
    drill_is_due: bool
    unreadable: list[UnreadableView]


class RecoveryView(BaseModel):
    """The recovery panel, or the admission that nothing here looked.

    Exactly one of the two is set, refused here rather than left to whatever draws it. See
    `AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE`: the failure this refuses is a panel assembled from
    no observations, which answers that nothing has been copied and is a statement nobody
    established.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    panel: RecoveryPanelView | None = None
    #: Why there is no panel. Required when there is none, and empty when there is one.
    unread: str = ""

    @model_validator(mode="after")
    def _exactly_one(self) -> RecoveryView:
        if self.panel is not None and self.unread:
            msg = (
                "a recovery panel is set and a reason for having none is set beside it, and a "
                "caveat beside a verdict about backups is read as a verdict about backups"
            )
            raise ValueError(msg)
        if self.panel is None and not self.unread:
            msg = (
                "no recovery panel and nothing saying why, which renders as a screen that has "
                f"not loaded. {AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE}"
            )
            raise ValueError(msg)
        return self


class CeilingView(BaseModel):
    """One external ceiling requests run into, with whether money moves it.

    `derived` is on the model because a daily figure calculated from a per-minute one always
    flatters the source: it assumes traffic arrives evenly across the day and office traffic
    does not. `brain.ops.admission.Ceiling` argues it at length, and a screen showing a derived
    figure as though a vendor published it is how a source is declared safe at forty times and
    starts refusing at eight.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    per_day: int
    raisable: bool
    derived: bool


class ThrottleView(BaseModel):
    """One ceiling that is refusing right now, as this reader may see it.

    No count of refused requests. `brain.console.installation.ThrottleRow` gives the reason:
    the rule here is about what a screen may say about somebody else's afternoon, and a refusal
    count beside a person's name is that.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: str
    subject: str
    limit: int
    retry_after_seconds: float


class LimitsView(BaseModel):
    """The ceilings this install applies, and who is behind one, when that can be read.

    The two halves are answered separately because they come from different places and only
    one of them is narrowed by the reader's grant. The ceilings are a declaration every caller
    who may read this screen sees whole; the throttling list is
    `brain.console.installation.throttled_now`'s answer at this reader's scope, and it carries
    no count of the rows a scope dropped.

    `throttled` and `unread` follow `RecoveryView`'s rule and for its reason: an empty list of
    who is being throttled reads as nobody, so there is no list at all when nothing looked.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ceilings: list[CeilingView]
    throttled: list[ThrottleView] | None = None
    #: Why there is no throttling list. Required when there is none, empty when there is one.
    unread: str = ""

    @model_validator(mode="after")
    def _exactly_one(self) -> LimitsView:
        if self.throttled is not None and self.unread:
            msg = (
                "a throttling list is set and a reason for having none is set beside it, so a "
                "reader cannot tell an install with nobody throttled from one nothing looked at"
            )
            raise ValueError(msg)
        if self.throttled is None and not self.unread:
            msg = (
                "no throttling list and nothing saying why, which renders as nobody being "
                f"throttled. {AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE}"
            )
            raise ValueError(msg)
        return self


class MemoryView(BaseModel):
    """What this profile wants against what the host has, and what the compose files reserve.

    Two figures for what is running rather than one, and `deployed_mib` is null rather than a
    copy of the declared figure when no compose file was read. `brain.console.installation.
    WHAT_A_PROFILE_DECLARES_AND_WHAT_THE_COMPOSE_FILES_RESERVE_ARE_TWO_FIGURES` is the reason:
    two numbers equal by construction read as agreement between independent measurements, and
    agreement is exactly what somebody opens this screen to check.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: str
    host_total_mib: int
    declared_mib: int
    deployed_mib: int | None
    breaches: list[str]
    unbudgeted: list[str]


class ConnectionView(BaseModel):
    """One database's connection ceiling against what its declared clients want."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    database: str
    admissible: int
    demand: int
    headroom: int


class CapacityView(BaseModel):
    """Memory and connections, from `brain.ops.wiring`, `brain.ops.compose` and
    `brain.ops.connections`.

    The one surface in this group that needs nothing outside the process: every figure is
    arithmetic over what the source tree declares, so there is no unread shape here and there
    never will be one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory: MemoryView
    connections: list[ConnectionView]


# ---------------------------------------------------------------------- the projections


def running_view(one: Running) -> RunningView:
    return RunningView(
        tag=one.tag,
        facts=[fact_view(fact) for fact in one.facts],
        cannot_say=one.cannot_say,
        commit=one.commit,
    )


def updates_view(one: UpdatesPanel) -> UpdatesView:
    """The version panel as a response, with the union split into two nullable fields."""
    return UpdatesView(
        running=running_view(one.running),
        told=(
            ToldView(
                tag=one.told.tag, at=one.told.at.isoformat(), by=one.told.by, notes=one.told.notes
            )
            if isinstance(one.told, Told)
            else None
        ),
        unanswered=(
            UnansweredView(
                why=one.told.why.value, detail=one.told.detail, at=one.told.at.isoformat()
            )
            if isinstance(one.told, Unanswered)
            else None
        ),
        standing=one.standing.value,
        says=one.answer.says,
        what_to_do=one.answer.what_to_do,
        told_days_ago=one.told_days_ago,
        goes_off_after_days=one.goes_off_after_days,
    )


def copy_state_view(one: CopyState) -> CopyStateView:
    """One coverage, with both of its facts and the comparison it was judged by.

    `within_objective` is read off the property rather than recomputed, which is the whole
    point of that property being a property: a stored boolean is a slot in which a coverage
    nothing has copied can be recorded as inside its recovery point.
    """
    return CopyStateView(
        coverage=one.coverage.value,
        facts=[fact_view(fact) for fact in one.facts],
        within_objective=one.within_objective,
        objective_seconds=one.objective_seconds,
    )


def recovery_panel_view(one: RecoveryPanel) -> RecoveryPanelView:
    return RecoveryPanelView(
        profile=one.profile,
        copies=[copy_state_view(copy) for copy in one.copies],
        last_verified=fact_view(one.last_verified_fact),
        measured_rto_seconds=one.measured_rto_seconds,
        assurance=one.assurance.value,
        says=one.answer.says,
        what_to_do=one.answer.what_to_do,
        drill_is_due=one.drill_is_due,
        unreadable=[UnreadableView(where=bad.where, why=bad.why) for bad in one.unreadable],
    )


def ceiling_view(one: Ceiling) -> CeilingView:
    return CeilingView(
        name=one.name, per_day=one.per_day, raisable=one.raisable, derived=one.derived
    )


def throttle_view(one: ThrottleRow) -> ThrottleView:
    return ThrottleView(
        scope=one.scope,
        subject=one.subject,
        limit=one.limit,
        retry_after_seconds=one.retry_after_seconds,
    )


def memory_view(one: MemoryCapacity) -> MemoryView:
    return MemoryView(
        profile=one.profile,
        host_total_mib=one.host_total_mib,
        declared_mib=one.declared_mib,
        deployed_mib=one.deployed_mib,
        breaches=list(one.breaches),
        unbudgeted=list(one.unbudgeted),
    )


def connection_view(one: ConnectionCapacity) -> ConnectionView:
    return ConnectionView(
        database=one.database,
        admissible=one.admissible,
        demand=one.demand,
        headroom=one.headroom,
    )


# ---------------------------------------------------------------------- the refusals


def _not_answerable(surface: str) -> Absent:
    """The one refusal this router makes, for every surface.

    One function rather than five, so the five refusals are the same refusal and no surface
    can acquire a message of its own that says more than its neighbours. `surface` reaches a
    log and never a response: `brain.app.handle_brain_error` sends `Absent.public_message`,
    and a body naming the screen would tell a caller which of five capabilities they are
    short of.
    """
    log.info("install surface not answerable", surface=surface)
    return Absent("this part of the console is not answerable for this caller")


def _permitted(reach: EntitlementSet, key: str, now: datetime) -> None:
    """Refuse unless this caller may open this screen, before anything is read.

    `brain.console.reads.permitted` rather than a `holds` call on the capability, because the
    capability is half of what a console read asks for. See
    `A_SCREENS_CAPABILITY_IS_HALF_OF_WHAT_IT_ASKS_FOR`: the plane is the other half, and a
    route that checked only the first would answer somebody who may know a thing exists with
    the configuration of it while looking like a correct check.

    Written as one function every route calls rather than as five copies of an `if`, because
    the order is the property and a copy is where the order gets reversed. See the module
    docstring: an unentitled caller must be refused identically whatever this process can and
    cannot read.
    """
    if not permitted(screen(key).read, reach, now):
        raise _not_answerable(key)


# ----------------------------------------------------------------------- the routes

router = APIRouter(prefix=API_PREFIX, tags=["install"])


@router.get("/install", response_model=InstallView, responses=COMMON_RESPONSES)
async def install(request: Request, asked: Asked) -> InstallView:
    """What is actually running: the release, the migration level, the profile and its features.

    The capability first and the file system second, for the reason the module docstring gives.

    `read_manifest()` returns `None` outside a built image, which produces an unknown release
    rather than a fallback: a console showing a developer's working tree commit and an image's
    commit under one heading would be showing two different things. `read_plan` parses the
    migration tree on every request, which is affordable because this screen is opened rarely
    and because a cache of it would be a copy of the image's own content whose staleness nobody
    could observe or test.

    `pending` is deliberately not measured. See
    `A_CONNECTION_OPENED_OUTSIDE_THE_POOL_IS_A_CONNECTION_NOBODY_BUDGETED`.
    """
    _permitted(asked.reach, "install", asked.now)
    settings = settings_of(request)
    facts = install_facts(
        profile=settings.profile,
        manifest=read_manifest(),
        revisions=read_plan().revisions,
        pending=None,
    )
    return InstallView(facts=[fact_view(one) for one in facts])


@router.get("/install/updates", response_model=UpdatesView, responses=COMMON_RESPONSES)
async def updates(request: Request, asked: Asked) -> UpdatesView:
    """Which release this install is on, and whether a newer one has been published (M42.3.9).

    **The release comes from the image reference this container was started with, and the
    commit from the image itself.** `Settings.app_image` is the `APP_IMAGE` the compose files
    hand the application, the same value its `image:` line selected it by, and the manifest is
    the file CI wrote into the image. The release marker is not handed in, on purpose; see
    `brain.console.version_view.A_RELEASE_TAG_IS_A_NAME_GIVEN_AFTER_THE_BUILD`. A deployment
    whose compose file predates the line hands in no reference, and the panel says so and names
    the commit instead of a release.

    **Nothing here waits for the release list.** `release_watch_of` answers from the last look
    that finished and starts the next one beside this request when it is due, so the page is as
    fast with a silent list as with none. The capability is checked first, so a caller who may
    not open this screen cannot make this server ask anything outside its network either.
    """
    _permitted(asked.reach, "updates", asked.now)
    settings = settings_of(request)
    manifest = read_manifest()
    told = release_watch_of(request).answer(
        feed_address(switched_on=settings.release_check, url=settings.release_feed_url),
        now=asked.now,
    )
    return updates_view(
        updates_panel(
            running_release(
                pinned_image=settings.app_image,
                built_commit="" if manifest is None else manifest.commit,
            ),
            told,
            now=asked.now,
        )
    )


@router.get("/install/recovery", response_model=RecoveryView, responses=COMMON_RESPONSES)
async def recovery(request: Request, asked: Asked) -> RecoveryView:
    """The copies, the last verified restore, and whether a rehearsal is owed (M27.6.2).

    **No panel while nothing here can read the bucket**, and that is the whole of what this
    route has to get right. See `AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE`: a panel over no
    observations answers that nothing has been copied, which is the alarming word for a fact
    nobody established, and it would be believed.

    The reader is a protocol on `app.state`. Nothing attaches one today, so this answers the
    sentence on every install, and the day something does the panel appears with no line here
    changing. Both halves of the bucket go into one `unreadable` argument for the reason
    `brain.console.recovery_view.panel` gives: a caller passing only the manifests would
    produce a panel confident about rehearsals and cautious about copies.

    There is no drill control here. M30.3.9 asks for one, it is a write, and
    `brain.console.recovery_view` declines the leaf in those words.
    """
    _permitted(asked.reach, "recovery", asked.now)
    objects = backup_objects_of(request)
    if objects is None:
        return RecoveryView(panel=None, unread=NOTHING_HERE_READS_THE_BACKUP_BUCKET)
    # Read twice rather than once into a list, because the two readers filter the bucket by
    # different suffixes and a caller holding one listing would have to know that. Both halves
    # are handed to the panel together for the reason `recovery_panel` gives about its own
    # `unreadable` argument: a panel given only the manifests is confident about rehearsals and
    # cautious about copies, which is the wrong way round.
    backups, bad_manifests = read_manifests(objects())
    verifications, bad_drills = read_drills(objects())
    return RecoveryView(
        panel=recovery_panel_view(
            recovery_panel(
                backups=backups,
                verifications=verifications,
                profile=settings_of(request).profile,
                now=asked.now,
                unreadable=(*bad_manifests, *bad_drills),
            )
        )
    )


@router.get("/install/limits", response_model=LimitsView, responses=COMMON_RESPONSES)
async def limits(request: Request, asked: Asked) -> LimitsView:
    """The ceilings requests run into, and who is behind one right now (M27.6.3).

    The ceilings are `brain.ops.limits.ceilings()`, which is every verified source ceiling with
    the derived ones marked. They are a declaration rather than a measurement and are the same
    for every caller who may read this screen.

    The throttling half is the one collection in this router a reader's own grant narrows.
    `brain.console.installation.throttled_now` matches each row against the scope on the
    reader's `read:rate_limit` grant and returns what matched, with no count of what did not.
    A department-scoped grant matches nothing, which is the answer rather than a refusal; see
    `AN_INSTALL_SCREEN_IS_THE_SAME_FACT_FOR_EVERYBODY_AND_A_THROTTLING_LIST_IS_NOT`.

    Nothing on this process enumerates the live windows, so the list is absent with its reason
    on every install today, through the same protocol the recovery route uses and for the same
    argument.
    """
    _permitted(asked.reach, "limits", asked.now)
    declared = [ceiling_view(one) for one in ceilings()]
    source = throttle_source_of(request)
    if source is None:
        return LimitsView(ceilings=declared, unread=NOTHING_HERE_ENUMERATES_THE_LIVE_WINDOWS)
    live, state = source(asked.now)
    return LimitsView(
        ceilings=declared,
        throttled=[
            throttle_view(one) for one in throttled_now(live, state, asked.reach, now=asked.now)
        ],
    )


@router.get("/install/capacity", response_model=CapacityView, responses=COMMON_RESPONSES)
async def capacity(request: Request, asked: Asked) -> CapacityView:
    """Connections, memory and pool sizes against what is deployed (M27.6.4).

    Every figure here is arithmetic over what the source tree declares, so this is the one
    surface in the group with nothing to be unread. `files` is not supplied to
    `memory_capacity`, so `deployed_mib` is null: the compose documents are files beside the
    install on the host and this container mounts none of them, and a deployed figure defaulted
    to the declared one would read as two independent numbers agreeing.
    """
    _permitted(asked.reach, "connections", asked.now)
    return CapacityView(
        memory=memory_view(memory_capacity(settings_of(request).profile)),
        connections=[connection_view(one) for one in connection_capacity()],
    )
