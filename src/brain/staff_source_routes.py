"""The Staff sources screen over HTTP, and the trial run that reads a source and writes nothing.

`brain.console.staff_source_view` opens by naming the caller it was written for: "the console
page that lets somebody choose a source and test it before it runs. This is that caller." It
was not, because nothing served it in a browser. `brain.ops.console_screens` counted it among
the console reads with no screen, which is its `A_READ_NOBODY_CAN_OPEN_IS_A_SCREEN_NOBODY_HAS`
measured rather than asserted, and `brain.ops.controls.chains_worth_checking` counted the roster
dry run as a control whose only caller was itself unreached. This is the half that makes the
screen openable, and it adds no second opinion about any of it.

**Nothing here decides anything, in the shape `brain.govern_routes` states about the four
screens next door.** `staff_source_view.choices` decides which sources a reader may be shown,
`selection` decides what the chosen one is and what stands in its way, `may_trial` decides
whether the trial is reachable at all, and `trial` decides what a run would change. Every route
below is a call into one of those and a projection of what came back. See
`THE_SCREEN_DECIDES_NOTHING_AND_THE_CONSOLE_MODULE_DECIDES_EVERYTHING`, which is that module's
sentence and is named rather than copied.

**There is no refusal on the listing route and that is the disclosure rule rather than an
oversight.** A source sits at `brain.console.govern.NOWHERE`, so a department-scoped grant of
this screen's capability reaches no source at all and `choices` answers the empty tuple for that
reader. A route that refused the caller holding nothing while answering that caller an empty
page would make the two distinguishable from outside, and the difference between them is whether
somebody holds a capability. So both are answered the page the module built, which is empty, and
`brain.govern_routes.capabilities` is the same decision taken on the same grounds one screen
along. See `A_REFUSED_READER_AND_A_READER_WHO_REACHES_NOTHING_ARE_ONE_ANSWER`.

**The trial is a second address because it is a thing somebody presses.** It is a wider read
than the page it sits on, at `Plane.CONTENT` rather than `Plane.CONFIGURATION`, because naming
who would be added and who has gone missing is a statement about the company's staff; and it is
the one read in this module that contacts a server outside this process. Loading it with the
page would contact the client's directory every time anybody opened the screen, and would give a
reader holding the configuration grant alone an answer assembled from a read they do not reach.
Both are `brain.install_routes`' argument against one address answering five surfaces, arriving
with the outbound call attached. See `A_TRIAL_IS_PRESSED_AND_A_PAGE_IS_LOADED`.

**A trial is a read and this module has no verb that could write.** `GET`, on both routes.
`dry_run` computes what a sync would change by calling `brain.identity.directory.reconcile` and
writing nothing, and `staff_sync` opens by saying so; what is missing here is not a safeguard
against applying a plan but any route that could. Applying one is a different act with a
different authority and it is not built. See `NOTHING_HERE_APPLIES_A_PLAN`.

**Nothing on this process can read a live staff source, and the trial says so rather than
answering an empty one.** This is the rule the module turns on and it is
`brain.install_routes.AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE` asked about a roster. Four things a
trial needs have no store in this repository and none of the four fails safely as a default:
`brain.identity.staff_adapters` parses pages a caller has already fetched and there is no
fetcher, no credential custody for one and no transport; nothing maps a work address to the
principal this system holds, so a trial run with an empty map proposes adding every person in
the company; nothing records when a sync was last applied; and nothing stores the group rules
that decide which roles a roster supports. So the inputs arrive together through one protocol on
`app.state`, absent today, and the route answers a sentence naming what is missing. The day
somebody attaches one the trial appears with no line here changing, which is
`brain.install_routes`' construction and the difference between a check and a comment.

**Choosing a source and pointing it somewhere cannot be written from a browser at all**, and
this module says so on the response rather than drawing a control that would fail. The choice is
`INSTALL_STAFF_SOURCE` and the location is `INSTALL_STAFF_SOURCE_LOCATION`, both installation
settings; `brain.setup_wizard` writes them once at first run into the install's own environment,
`brain.install.value_of` reads them, and no route in this application writes an installation
setting: `brain.install_routes` rejects a write anywhere in itself in those words. A form here
would post to nothing. See `CHOOSING_A_SOURCE_IS_NOT_A_WRITE_THIS_APPLICATION_HAS`.

Rejected: rendering what a setting is currently set to beside its name.
`staff_source_view.A_PAGE_THAT_RENDERS_A_SETTING_IS_A_PAGE_THAT_RENDERS_A_CREDENTIAL` is the
argument and the shape it takes is that `SourceOption` and `Selection` have nowhere to put a
value. This module copies those rows field by field and adds no field, so the property is
carried rather than re-argued, and `staff_source_gaps` is what measures it: the console's own
diagnostic scans the rows this page renders for the value of every setting a source names.

Rejected: a `total`, a `truncated` or any count on either response. The options are the whole of
`SELECTABLE` or none of it, and the trial is the whole plan or a refusal, so there is no partial
answer here for a number to sit beside. That is
`staff_source_view.A_SOURCE_SITS_NOWHERE_SO_THE_ANSWER_IS_EVERYTHING_OR_NOTHING` rather than a
rule this module keeps, and `hidden_count_fields` is already run over the rows by that module's
own diagnostic.

Rejected: mounting these on `brain.govern_routes`. That router is four screens with one refusal
shape and a database behind every listing, and this is one screen with no database, no refusal
on its listing at all and an outbound call on its second route. The `Asked` dependency is
imported from `brain.api_routes` rather than re-declared, so there is one spelling of `asking`
and a route here cannot acquire a subtly different one.

**Since 2026-09-21 the scheduled sync runs, and four addresses here show and serve it.**
`brain.ops.staff_sync_run` reads the chosen source in the worker and applies the plan; this
module still applies nothing. `/runs` is what each run added, marked as having left or held back,
at the trial's plane because it names people; `/credential` says whether the secret the worker
reads with is held and replaces it under `admin:credential` over everything, through the
credentials screen's own write; `/transfers` lists the agents whose owner a run marked as having
left and lets a reader who may adopt one take it on (M1.8.9). The trial below is unchanged.

**What has never run.** No live staff source has been read by anything in this repository, so
the trial's success path is exercised against a source built in a test and never against a
directory. What is tested is every refusal, the order the checks happen in, and that the plan a
wired process would produce is the plan `dry_run` produced.

**M27.7.2 is this screen and is deliberately not claimed, here or in the commit that adds it.**
The leaf reads "Staff source: choose it, configure it and try it before it runs", and on every
install today this answers none of the three: choosing and configuring are installation settings
no route in this application writes, and trying needs a gatherer nothing attaches. What is built
is the fourth thing the leaf assumes and does not say, which is a screen that tells somebody
which source this install is set to read and what it is still missing. That is worth having on
its own and it is not the leaf. `console/src/pages/Recovery.tsx` declines M27.7.26 in the same
words and for the same shape, and the rule both follow is that a screen which is reachable and
cannot answer is not the leaf.

Task ids: M1.6.12, M1.8.6, M1.8.9
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol, cast

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import record_of
from brain.agents.lifecycle import transfer_ownership
from brain.agents.model import AgentError, AgentRecord
from brain.api import API_PREFIX, COMMON_RESPONSES, NoEchoRoute
from brain.api_routes import Asked
from brain.console.staff_source_view import (
    THE_SCREEN,
    Selection,
    SourceOption,
    Trial,
    choices,
    may_trial,
    selection,
    transfers_for,
    trial,
)
from brain.core.errors import Absent, Failed
from brain.credential_routes import (
    NOT_KEPT_STATUS,
    CredentialNotKeptView,
    CredentialProblemsView,
    CredentialProblemView,
    credentials_of,
    may_manage,
)
from brain.identity.directory import DirectoryAssertion
from brain.identity.staff_roster import APPLIED_OUTCOMES
from brain.identity.staff_source import (
    STAFF_SOURCE_LOCATION_SETTING,
    STAFF_SOURCE_SETTING,
    GroupRule,
    StaffRecord,
    StaffSource,
)
from brain.identity.staff_sync import DryRun
from brain.install import value_of
from brain.ops.credentials import (
    TOLD,
    CredentialProblemError,
    CredentialsUnavailableError,
    VaultState,
    connector_key_slot,
)
from brain.ops.staff_sync_run import STAFF_SOURCE_SLOT
from brain.ops.staff_sync_store import RunRecord, read_leavers, read_runs
from brain.tables.agent import AgentRow

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why every route here is a call into the console module and a projection of the answer.
THE_SCREEN_DECIDES_NOTHING_AND_THE_CONSOLE_MODULE_DECIDES_EVERYTHING: Final = (
    "brain.console.staff_source_view decides which sources a reader is shown, what the "
    "chosen one is, whether the trial is reachable and what a run would change, against the "
    "reader's own entitlement and with no connection. Every route here hands it an "
    "entitlement and renders what comes back. A filter or a refusal written here would be a "
    "second answer to a question that module exists to answer, and the two would agree until "
    "somebody changed one of them."
)

#: Why the listing route refuses nobody.
A_REFUSED_READER_AND_A_READER_WHO_REACHES_NOTHING_ARE_ONE_ANSWER: Final = (
    "A staff source sits at brain.console.govern.NOWHERE, so a department-scoped grant of "
    "this screen's capability reaches no source and choices answers an empty page for a "
    "reader who genuinely holds it. If a caller holding nothing were refused instead, the "
    "difference between a 404 and an empty page would say whether the other reader holds a "
    "capability, which is DENIED and ABSENT told apart by anybody who can reach the port. So "
    "the module's answer is the response for both, and it is empty for both."
)

#: Why the trial has an address of its own rather than arriving with the page.
A_TRIAL_IS_PRESSED_AND_A_PAGE_IS_LOADED: Final = (
    "The trial reads the chosen source, which is a call to a server outside this process, and "
    "it names the company's staff, which is a content disclosure on a configuration screen. "
    "Loading it with the page would contact a client's directory every time anybody opened "
    "the screen, and would put an answer a reader may not reach behind a request they make by "
    "arriving. Two addresses make the outbound call something somebody asked for, and make "
    "the wider read a request of its own that can be refused on its own terms."
)

#: Why there is no route here that applies what a trial proposes.
NOTHING_HERE_APPLIES_A_PLAN: Final = (
    "brain.identity.staff_sync computes a diff by calling brain.identity.directory.reconcile "
    "and writes nothing, and a trial is that computation with a reader's entitlement checked "
    "first. Applying it provisions people, writes role assertions and removes them, which is "
    "a different authority from reading a configuration screen and belongs to whatever runs "
    "the scheduled sync. There is no verb here that could do it, which is the same shape "
    "brain.install_routes takes about the recovery drill it declines to claim."
)

#: What the trial answers while nothing on this process can read a roster.
#:
#: Written as the sentence a client reads rather than as a list of module names, for the reason
#: `brain.console.recovery_view.ANSWERS` are: the reader has a server and no source tree.
NOTHING_HERE_READS_A_LIVE_STAFF_SOURCE: Final = (
    "This install cannot try your staff source yet. Nothing here fetches a list from Google "
    "Workspace, Microsoft, Lark, a sheet or a directory, nothing here knows which of the "
    "people on such a list this system already holds, and nothing here records when a list "
    "was last applied. A trial run without those would say that every person in your company "
    "would be added, which is a sentence about this install rather than about your directory. "
    "So there is no trial rather than a misleading one. The rest of this screen is real: it "
    "says which source this install is set to read and what it is still missing."
)

#: Why the screen carries no control for choosing a source or pointing it anywhere.
CHOOSING_A_SOURCE_IS_NOT_A_WRITE_THIS_APPLICATION_HAS: Final = (
    f"Which staff list this install reads is {STAFF_SOURCE_SETTING} and where that list is "
    f"is {STAFF_SOURCE_LOCATION_SETTING}. Both are installation settings: brain.setup_wizard "
    "writes them once at first run, brain.install.value_of reads them, and no route in this "
    "application writes an installation setting at all. A control on this screen would "
    "therefore post to nothing, so the screen says where the values are set instead of "
    "offering a form that cannot work."
)


# ----------------------------------------------------------- what this process does not hold


@dataclass(frozen=True)
class TrialInputs:
    """Everything one trial needs that this repository has no store for, gathered together.

    Five fields and one protocol rather than five readers, because a caller holding some of
    them would have to invent the rest and every invention fails in a direction somebody would
    believe. An empty `known` makes a correct roster read as every person in the company
    arriving; a `last_applied` guessed as the present makes a first run look like a second,
    which is exactly what `THE_FIRST_RUN_OF_A_SOURCE_HAS_NOTHING_TO_BE_WRONG_AGAINST` says
    nothing may assume; and `held` without `rules` makes `dry_run` propose removing every role
    assertion the directory has ever conferred, because `reconcile` is a set difference and one
    side would be empty for want of a table rather than for want of a rule.

    The field names are `brain.identity.staff_sync.dry_run`'s own, so a process attaching one
    of these is assembling the arguments the scheduled sync will assemble, rather than a shape
    invented for a screen. That is `staff_source_view.trial`'s own argument for passing them
    straight through: a trial and the sync that follows it read the same inputs.
    """

    #: The chosen source, already wired to whatever fetches its pages. `roster()` is what
    #: contacts the far end and it is called inside `trial` and nowhere here.
    source: StaffSource
    #: Casefolded work address to the principal this system already holds for it.
    known: Mapping[str, str]
    #: When a sync from this source was last applied. `None` means never, which is the
    #: first-run case and suppresses every removal.
    last_applied: datetime | None
    #: The group-to-role mappings this install has configured.
    rules: tuple[GroupRule, ...] = ()
    #: What `auth.directory_role_grant` currently holds for this source.
    held: tuple[DirectoryAssertion, ...] = ()


class TrialSource(Protocol):
    """Whatever this process was built with that can gather a trial's inputs at one instant.

    A protocol read off `app.state` rather than a parameter, in the shape
    `brain.install_routes.BackupObjects` uses and for its reason: there is nothing to pass,
    because no module in this repository fetches a roster, maps an address to a principal or
    records an applied sync. What it buys is that the sentence above stops being returned on
    the day somebody attaches one, with nothing here changing.

    It takes `now` because `last_applied` is read against a clock somewhere and a gatherer that
    took none would read the process's, which is the parameter every decision in this
    repository takes rather than reads.
    """

    def __call__(self, now: datetime) -> TrialInputs: ...


def trial_source_of(request: Request) -> TrialSource | None:
    """The trial gatherer this process was built with, or None.

    `getattr` rather than attribute access, in the shape `brain.routing_routes.sessions_of`
    uses and for its reason: a test may construct a bare application to exercise one route, and
    an `AttributeError` there reaches a caller as a 500 that reads like a bug in the gate
    rather than like a process built without a gatherer.

    A `cast` after a `callable` check rather than an `isinstance` against the protocol, and the
    reason is `brain.install_routes.backup_objects_of`'s: a runtime-checkable protocol whose
    only member is `__call__` admits every function in the process, so the check would read as
    structural and be a callable check with more words. The attribute's name discriminates and
    this comment is the proof the structural match was not made rather than being assumed.
    """
    found = getattr(request.app.state, "staff_trial_source", None)
    return cast(TrialSource, found) if callable(found) else None


# ------------------------------------------------------------------------ the shapes


class SourceOptionView(BaseModel):
    """One answer this install could give to where it keeps its staff list.

    Every field is `brain.console.staff_source_view.SourceOption`'s, copied one at a time
    rather than dumped, for the reason `brain.routing_routes.view_of` gives about its own: a
    field added to that row would otherwise arrive in a response because a copy loop was
    generous. On this screen that matters more than elsewhere, because the field somebody would
    add is what a setting is currently set to.

    `needs` and `unsupplied` are setting names and never values. That is not a rule this model
    keeps: `SourceOption.__post_init__` refuses a name `brain.install` does not declare, which
    is a check no value can pass.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    meaning: str
    #: False for the one option that reads no list at all, so a screen can say there is
    #: nothing to try rather than offering a trial that would refuse.
    reads_a_list: bool
    needs: list[str]
    unsupplied: list[str]
    chosen: bool


class SelectionView(BaseModel):
    """Which staff list this install has chosen, and what stands between it and being read.

    `refusal` is `selected_source`'s own message, carried whole. `ready` is derived on the row
    rather than in a browser, so a console cannot decide that a source with an unset setting is
    ready by reading a different field from the one that refused.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    meaning: str
    reads_a_list: bool
    unsupplied: list[str]
    refusal: str
    ready: bool


class StaffSourcesView(BaseModel):
    """What an install could read its staff list from, what it does, and what cannot be set here.

    `selection` is null for a reader who reaches nothing, which is the same answer they would
    get on an install with nothing to show. There is no field saying which, and there is no
    count anywhere on this model; see
    `A_REFUSED_READER_AND_A_READER_WHO_REACHES_NOTHING_ARE_ONE_ANSWER`.

    `not_written_here` is a constant of the product rather than a fact about this install,
    carried on the response so that one sentence about where these values are set is written
    once and rendered rather than composed in a browser. See
    `CHOOSING_A_SOURCE_IS_NOT_A_WRITE_THIS_APPLICATION_HAS`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    options: list[SourceOptionView]
    selection: SelectionView | None
    not_written_here: str = CHOOSING_A_SOURCE_IS_NOT_A_WRITE_THIS_APPLICATION_HAS


class RosterPersonView(BaseModel):
    """One person as the chosen source describes them, in a plan that would add them.

    `brain.identity.staff_source.StaffRecord`, copied field by field. The department and the
    groups are what the source's payload carried and not what it is trusted to assert, which is
    `staff_adapters.THE_PARSER_READS_AND_THE_TRUST_DECIDES`: what may be read back out of them
    is `Roster.asserts`, and the plan beside this row is where that has already been applied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    work_address: str
    display_name: str
    department: str
    groups: list[str]
    active: bool


class RoleAssertionView(BaseModel):
    """One sentence the roster supports: this group gives this person this role.

    The three fields `brain.identity.directory.DirectoryAssertion` carries and no fourth. That
    type's docstring says why there is no timestamp on it, and a response adding one would make
    two rows saying the same thing unequal to whatever compares them next.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    role: str
    source_group: str


class TrialPlanView(BaseModel):
    """What one real run would change, as the code that would change it computed it.

    `brain.identity.staff_sync.DryRun`, copied field by field, plus its two derived properties.
    Every field is a list of things rather than a count of them, which is that class's own
    decision: an operator reading "four people would be removed" cannot tell whether the four
    are the four they expect, and that is the only question a trial exists to answer.

    `would_remove` is always a subset of `absent` and never wider; `withheld` is why it is
    narrower, in words. The two travel together because a shorter removal list with nothing
    saying why is a person looking for a setting that would not have helped.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    would_add: list[RosterPersonView]
    absent: list[str]
    would_remove: list[str]
    would_deactivate: list[str]
    withheld: list[str]
    role_grants_to_add: list[RoleAssertionView]
    role_grants_to_remove: list[RoleAssertionView]
    refusals: list[str]
    gaps: list[str]
    #: Derived on `DryRun` rather than here, so a plan cannot say it may be applied while
    #: carrying the reason it may not.
    safe_to_apply: bool
    changes_nothing: bool


class TrialRunView(BaseModel):
    """One run of the chosen source that wrote nothing, or the refusal that stopped it.

    Exactly one of `plan` and `refusals` is set, which is
    `brain.console.staff_source_view.Trial`'s constructor and is not re-checked here: a plan
    shown next to a refusal is a plan somebody applies. This model carries the pair as it was
    built, so the refusal cannot be dropped by a projection.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    plan: TrialPlanView | None
    refusals: list[str]
    safe_to_apply: bool


class TrialView(BaseModel):
    """The trial, or the admission that nothing here could run one.

    Exactly one of the two is set, refused here rather than left to whatever draws it, which is
    `brain.install_routes.RecoveryView`'s construction and for the same argument: a trial
    assembled from no roster would report that every person in the company would be added,
    which is an alarming statement about a directory nobody read. See
    `NOTHING_HERE_READS_A_LIVE_STAFF_SOURCE`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    trial: TrialRunView | None = None
    unread: str = ""
    #: What happened to the credential a first-run trial read with, or empty. See
    #: `brain.setup_staff_routes.keep_for_the_schedule`; the console's trial never keeps one.
    credential: str = ""

    @model_validator(mode="after")
    def _one_or_the_other(self) -> TrialView:
        if (self.trial is None) == (self.unread == ""):
            msg = (
                "a trial response carries a run or the reason there is none, and never both "
                "and never neither: both is a plan beside a refusal, and neither is a reader "
                "looking for a setting that would not have helped. "
                f"{NOTHING_HERE_READS_A_LIVE_STAFF_SOURCE}"
            )
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------- the projections


def option_view(one: SourceOption) -> SourceOptionView:
    """One selectable source, copied field by field. See `SourceOptionView` on why not a dump."""
    return SourceOptionView(
        name=one.name,
        meaning=one.meaning,
        reads_a_list=one.reads_a_list,
        needs=list(one.needs),
        unsupplied=list(one.unsupplied),
        chosen=one.chosen,
    )


def selection_view(one: Selection) -> SelectionView:
    """The chosen source, copied field by field, with `ready` asked of the row."""
    return SelectionView(
        name=one.name,
        meaning=one.meaning,
        reads_a_list=one.reads_a_list,
        unsupplied=list(one.unsupplied),
        refusal=one.refusal,
        ready=one.ready,
    )


def person_view(one: StaffRecord) -> RosterPersonView:
    """One person the source described, copied field by field."""
    return RosterPersonView(
        work_address=one.work_address,
        display_name=one.display_name,
        department=one.department,
        groups=list(one.groups),
        active=one.active,
    )


def assertion_view(one: DirectoryAssertion) -> RoleAssertionView:
    """One role assertion, copied field by field."""
    return RoleAssertionView(
        principal_id=one.principal_id,
        role=str(one.role.value),
        source_group=one.source_group,
    )


def plan_view(one: DryRun) -> TrialPlanView:
    """One dry run, copied field by field, with its two derived properties asked of it."""
    return TrialPlanView(
        source=one.source,
        would_add=[person_view(person) for person in one.would_add],
        absent=list(one.absent),
        would_remove=list(one.would_remove),
        would_deactivate=list(one.would_deactivate),
        withheld=list(one.withheld),
        role_grants_to_add=[assertion_view(row) for row in one.role_grants_to_add],
        role_grants_to_remove=[assertion_view(row) for row in one.role_grants_to_remove],
        refusals=list(one.refusals),
        gaps=list(one.gaps),
        safe_to_apply=one.safe_to_apply,
        changes_nothing=one.changes_nothing,
    )


def run_view(one: Trial) -> TrialRunView:
    """One trial, copied field by field, with the plan projected when there is one."""
    return TrialRunView(
        source=one.source,
        plan=None if one.plan is None else plan_view(one.plan),
        refusals=list(one.refusals),
        safe_to_apply=one.safe_to_apply,
    )


# -------------------------------------------------------------------- the routes

router = APIRouter(prefix=API_PREFIX, tags=["staff sources"], route_class=NoEchoRoute)

#: Where this screen lives, which is the screen's own key so that
#: `brain.ops.console_screens.routed_screen_keys` matches the console's address against the
#: registry. A prettier address would take the screen off that list while leaving it reachable,
#: which is `console/src/App.tsx`'s own rule about the install screens' addresses.
SCREEN_PATH: Final = f"/govern/{THE_SCREEN}"


@router.get(SCREEN_PATH, response_model=StaffSourcesView, responses=COMMON_RESPONSES)
async def staff_sources(asked: Asked) -> StaffSourcesView:
    """Where this install reads its staff list from, and what each option would need.

    No database and no session, because there is nothing stored to read: the choice and the
    location are installation settings and `brain.install.value_of` is the one reader of them.
    That is the same shape `brain.govern_routes.roles` has and states about itself.

    No refusal either, and that is the decision this route exists to make rather than an
    omission. `choices` answers an empty tuple and `selection` answers `None` for a reader who
    does not reach a source, and a reader whose grant is scoped to a department is exactly such
    a reader because a source sits nowhere. Refusing the caller who holds nothing while
    answering that one an empty page would tell either of them something about the other. See
    `A_REFUSED_READER_AND_A_READER_WHO_REACHES_NOTHING_ARE_ONE_ANSWER`.

    `env` is not passed, so the settings are this process's own, which is what makes this route
    a reading of the deployment rather than of whatever a caller sent.
    """
    chosen = selection(asked.reach, asked.now)
    return StaffSourcesView(
        options=[option_view(one) for one in choices(asked.reach, asked.now)],
        selection=None if chosen is None else selection_view(chosen),
    )


@router.get(f"{SCREEN_PATH}/trial", response_model=TrialView, responses=COMMON_RESPONSES)
async def staff_source_trial(request: Request, asked: Asked) -> TrialView:
    """Read the chosen source once, change nothing, and say what a run would change.

    **The reader is asked before anything is gathered, and the order is the property.**
    `may_trial` is `staff_source_view`'s own decision about `TRIAL_READ`, asked here so that a
    caller who reaches nothing cannot decide when this install contacts a company's directory.
    `trial` asks the same question again, with the same function, on the same read: this is that
    refusal moved one step earlier than the work rather than a second copy of it.

    **A reader who may not reach the trial is answered exactly what an install with no gatherer
    is answered.** One sentence, one shape, and nothing on the response that differs between
    them. The alternative is a refusal for the first and a sentence for the second, which is the
    difference between DENIED and ABSENT rendered as two status codes.

    **Nothing writes.** `trial` calls `roster_from`, which calls the source, and hands what
    comes back to `dry_run`, which computes a diff by calling `reconcile` and stores nothing.
    See `NOTHING_HERE_APPLIES_A_PLAN` for why there is no route that would.
    """
    if not may_trial(asked.reach, asked.now):
        log.info("staff source trial not answerable", principal=asked.caller.principal.id)
        return TrialView(unread=NOTHING_HERE_READS_A_LIVE_STAFF_SOURCE)

    gather = trial_source_of(request)
    if gather is None:
        return TrialView(unread=NOTHING_HERE_READS_A_LIVE_STAFF_SOURCE)

    ready = gather(asked.now)
    found = trial(
        ready.source,
        asked.reach,
        asked.now,
        known=ready.known,
        last_applied=ready.last_applied,
        rules=ready.rules,
        held=ready.held,
    )
    if found is None:
        # Unreachable through `may_trial` above and kept, because the two are the same question
        # asked by the same function and a refactor that changed one of them would otherwise
        # return a `TrialView` with neither half set, which the model refuses as a 500.
        return TrialView(unread=NOTHING_HERE_READS_A_LIVE_STAFF_SOURCE)
    return TrialView(trial=run_view(found))


#: What a caller may ask of this screen, named so a test can hold the two addresses to the
#: registry rather than to a string typed twice.
ADDRESSES: Final[tuple[str, ...]] = (SCREEN_PATH, f"{SCREEN_PATH}/trial")


def sources_offered(rows: Sequence[SourceOptionView]) -> tuple[str, ...]:
    """The names this screen offered, in the order it offered them.

    A function rather than a comprehension in a test, because the order is information:
    `SELECTABLE` is declared in the order a refusal lists its members in, so the screen and the
    message somebody gets when they mistype agree without either being sorted.
    """
    return tuple(one.name for one in rows)


# ================================================================ what the scheduled sync did
# Added on 2026-09-21 with `brain.ops.staff_sync_run`. Four addresses, and none of them applies a
# plan: the worker applies, and these show what it did, keep the credential it reads, and hand a
# leaver's agent to whoever takes it on.

#: Why the runs are read at the trial's plane and not the page's.
A_RUN_NAMES_PEOPLE_SO_IT_IS_READ_AS_THE_TRIAL_IS: Final = (
    "A run's record names who joined, who left and who moved, which is the same statement about "
    "the company's staff a trial makes. So it is answered to whoever may run the trial and to "
    "nobody else, and a reader who may not is answered what an install that has never run is "
    "answered: no runs."
)

#: Why the credential is managed under admin:credential held over everything.
THE_STAFF_SOURCE_CREDENTIAL_IS_A_CREDENTIAL: Final = (
    "The secret the staff sync reads the directory with is a credential like a provider key: it "
    "reaches every person in the company, so a grant scoped to one department is not a grant "
    "here. It is written with the credentials screen's own authority and its own write, "
    "recorded in the ledger by that write, and never read back."
)

#: What the credential is for each source, in the words the screen shows.
CREDENTIAL_FORMS: Final[Mapping[str, str]] = {
    "lark": (
        "The custom app's App ID, a colon, then its App Secret. The app needs the contact "
        "permissions to read users and departments, published."
    ),
    "microsoft_entra": (
        "The application's client ID, a colon, then a client secret. Give it the application "
        "(not delegated) Microsoft Graph permission User.Read.All, with admin consent."
    ),
    "google_sheet": "A Google API key with the Sheets API enabled, for a sheet shared by link.",
}

#: Said when this install's chosen source has no scheduled reader and so takes no credential.
NO_CREDENTIAL_NEEDED: Final = (
    "The chosen staff list is not read on a schedule, so it takes no credential here."
)


class StaffSyncRunView(BaseModel):
    """One scheduled run, as `auth.staff_sync_run` holds it. Names and sentences, no address."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    started_at: datetime
    finished_at: datetime
    outcome: str
    detail: str
    added: list[str]
    marked_left: list[str]
    renamed: list[str]
    withheld: list[str]
    #: True for every outcome but applied and unchanged: the run wrote no member.
    changed_nobody: bool


class RunsView(BaseModel):
    """The newest runs, newest first. Empty for a reader who may not see them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runs: list[StaffSyncRunView]


class StaffCredentialView(BaseModel):
    """Whether the staff source's credential is held and when it was written. Never the value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: str
    #: None when the vault could not be asked, which `told` says in words.
    held: bool | None
    set_at: datetime | None
    vault: str
    told: str
    #: What to paste for the chosen source, or why nothing is needed.
    form: str


class StaffCredentialAsked(BaseModel):
    """The one field a write carries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str


class TransferView(BaseModel):
    """One agent whose steward the roster marks as having left, which this reader may take on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str
    owner_id: str
    #: False when somebody had already stopped it. The listing itself stops nothing.
    running: bool


class TransfersView(BaseModel):
    """The agents waiting for a new owner, in id order, with no count of any left out."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    transfers: list[TransferView]


class TransferTakenView(BaseModel):
    """An agent that now answers to the reader who took it on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    owner_id: str


def run_record_view(one: RunRecord) -> StaffSyncRunView:
    """One stored run, copied field by field."""
    return StaffSyncRunView(
        source=one.source,
        started_at=one.started_at,
        finished_at=one.finished_at,
        outcome=one.outcome.value,
        detail=one.detail,
        added=list(one.added),
        marked_left=list(one.marked_left),
        renamed=list(one.renamed),
        withheld=list(one.withheld),
        changed_nobody=one.outcome not in APPLIED_OUTCOMES,
    )


def credential_form(env: Mapping[str, str] | None = None) -> str:
    """What the chosen source's credential is, or that it takes none."""
    return CREDENTIAL_FORMS.get(value_of(STAFF_SOURCE_SETTING, env), NO_CREDENTIAL_NEEDED)


def sessions_of(request: Request) -> async_sessionmaker[AsyncSession] | None:
    """The session factory this process was built with, or None, in `routing_routes`' shape."""
    found = getattr(request.app.state, "db_sessions", None)
    return found if isinstance(found, async_sessionmaker) else None


RUNS_PATH: Final = f"{SCREEN_PATH}/runs"
CREDENTIAL_PATH: Final = f"{SCREEN_PATH}/credential"
TRANSFERS_PATH: Final = f"{SCREEN_PATH}/transfers"

#: The slot the staff source's credential is kept in, which the worker's reader names too.
STAFF_CREDENTIAL_SLOT: Final = connector_key_slot(STAFF_SOURCE_SLOT)


@router.get(RUNS_PATH, response_model=RunsView, responses=COMMON_RESPONSES)
async def staff_sync_runs(request: Request, asked: Asked) -> RunsView:
    """The newest scheduled runs: who each added, marked as having left or moved, and why not.

    Asked with `may_trial` before the database is touched. See
    `A_RUN_NAMES_PEOPLE_SO_IT_IS_READ_AS_THE_TRIAL_IS`.
    """
    if not may_trial(asked.reach, asked.now):
        return RunsView(runs=[])
    factory = sessions_of(request)
    if factory is None:
        return RunsView(runs=[])
    async with factory() as session, session.begin():
        found = await read_runs(session)
    return RunsView(runs=[run_record_view(one) for one in found])


def _credential_not_answerable() -> Absent:
    return Absent("the staff source credential is not answerable for this caller")


@router.get(CREDENTIAL_PATH, response_model=StaffCredentialView, responses=COMMON_RESPONSES)
async def staff_credential(request: Request, asked: Asked) -> StaffCredentialView:
    """Whether the credential the staff sync reads with is held. Reads the vault's metadata only.

    See `THE_STAFF_SOURCE_CREDENTIAL_IS_A_CREDENTIAL` for the authority.
    """
    if not may_manage(asked.reach, asked.now):
        raise _credential_not_answerable()
    store = credentials_of(request)
    try:
        held = await asyncio.to_thread(store.held, STAFF_CREDENTIAL_SLOT)
    except CredentialsUnavailableError as unavailable:
        return StaffCredentialView(
            slot=STAFF_CREDENTIAL_SLOT.path,
            held=None,
            set_at=None,
            vault=unavailable.state.value,
            told=TOLD[unavailable.state],
            form=credential_form(),
        )
    return StaffCredentialView(
        slot=STAFF_CREDENTIAL_SLOT.path,
        held=held.held,
        set_at=held.set_at,
        vault=VaultState.READY.value,
        told=TOLD[VaultState.READY],
        form=credential_form(),
    )


#: What a person is told when the credential was kept.
CREDENTIAL_KEPT: Final = (
    "The credential is held in the vault. The next scheduled run reads with it."
)


@router.put(CREDENTIAL_PATH, response_model=StaffCredentialView, responses=COMMON_RESPONSES)
async def replace_staff_credential(
    request: Request, body: StaffCredentialAsked, asked: Asked
) -> JSONResponse:
    """Replace the staff source's credential. The next scheduled run reads with it.

    The credentials screen's own write, `Credentials.keep`, so the ledger records it as every
    other credential write is recorded, and nothing sent comes back.
    """
    if not may_manage(asked.reach, asked.now):
        raise _credential_not_answerable()
    store = credentials_of(request)
    trace_id = str(structlog.contextvars.get_contextvars().get("trace_id", ""))
    try:
        kept = await store.keep(
            STAFF_CREDENTIAL_SLOT,
            body.value,
            actor=asked.reach.principal_id,
            trace_id=trace_id,
            ent_hash=asked.reach.ent_hash(),
        )
    except CredentialProblemError as refused:
        told = CredentialProblemsView(
            problems=tuple(
                CredentialProblemView(field="value", code=one.code, message=one.message)
                for one in refused.problems
            )
        )
        return JSONResponse(status_code=422, content=told.model_dump(mode="json"))
    except CredentialsUnavailableError as unavailable:
        view = CredentialNotKeptView(
            message=TOLD[unavailable.state],
            trace_id=trace_id,
            slot=STAFF_CREDENTIAL_SLOT.path,
            vault=unavailable.state,
        )
        return JSONResponse(
            status_code=NOT_KEPT_STATUS[unavailable.state], content=view.model_dump(mode="json")
        )
    answered = StaffCredentialView(
        slot=kept.slot,
        held=True,
        set_at=kept.set_at,
        vault=VaultState.READY.value,
        told=CREDENTIAL_KEPT,
        form=credential_form(),
    )
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))


async def _leavers_agents(session: AsyncSession) -> tuple[frozenset[str], list[AgentRecord]]:
    """The roster's leavers and every agent any of them owns, as records."""
    leavers = await read_leavers(session)
    if not leavers:
        return leavers, []
    rows = (
        await session.execute(
            select(AgentRow).where(AgentRow.owner_id.in_(sorted(leavers))).order_by(AgentRow.id)
        )
    ).scalars()
    return leavers, [one for one in (record_of(row) for row in rows) if one is not None]


@router.get(TRANSFERS_PATH, response_model=TransfersView, responses=COMMON_RESPONSES)
async def staff_transfers(request: Request, asked: Asked) -> TransfersView:
    """The agents whose owner the staff sync marked as having left, that this reader may take.

    No refusal, for `A_REFUSED_READER_AND_A_READER_WHO_REACHES_NOTHING_ARE_ONE_ANSWER`: a reader
    who may take none of them is answered the empty list an install with no leavers answers.
    """
    factory = sessions_of(request)
    if factory is None:
        return TransfersView(transfers=[])
    async with factory() as session, session.begin():
        leavers, records = await _leavers_agents(session)
    return TransfersView(
        transfers=[
            TransferView(
                agent_id=one.agent_id,
                display_name=one.display_name,
                owner_id=one.audience.owner_id,
                running=one.disabled_at is None,
            )
            for one in transfers_for(records, leavers=leavers, reader=asked.reach, now=asked.now)
        ]
    )


@router.post(
    TRANSFERS_PATH + "/{agent_id}", response_model=TransferTakenView, responses=COMMON_RESPONSES
)
async def take_transfer(request: Request, agent_id: str, asked: Asked) -> TransferTakenView:
    """Become the owner of a leaver's agent. The steward moves and the ceiling does not.

    Decided again under a lock on the agent row, so the owner this reader was shown is the owner
    replaced. An agent this reader may not take, one whose owner has not left, and one that does
    not exist are one refusal. See
    `staff_source_view.A_LEAVERS_AGENT_RUNS_AT_THE_REACH_IT_HAD_UNTIL_SOMEBODY_TAKES_IT`.
    """
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    refused = Absent("that agent is not waiting for a new owner you may be")
    async with factory() as session, session.begin():
        leavers = await read_leavers(session)
        row = (
            await session.execute(select(AgentRow).where(AgentRow.id == agent_id).with_for_update())
        ).scalar_one_or_none()
        record = None if row is None else record_of(row)
        if record is None or not transfers_for(
            [record], leavers=leavers, reader=asked.reach, now=asked.now
        ):
            raise refused
        try:
            moved = transfer_ownership(record, to_owner=asked.caller.principal, now=asked.now)
        except AgentError as why:
            raise refused from why
        await session.execute(
            update(AgentRow).where(AgentRow.id == agent_id).values(owner_id=moved.audience.owner_id)
        )
    log.info("leaver's agent taken on", agent=agent_id, principal=asked.caller.principal.id)
    return TransferTakenView(agent_id=moved.agent_id, owner_id=moved.audience.owner_id)
