"""Choosing a staff list, seeing what is unset, and running it once before it runs nightly.

`brain.identity.staff_source` landed the choice and says plainly that **nothing in the product
calls it**: `roster_from` names "the console page that lets somebody choose a source and test it
before it runs" as the caller it was written for. This is that caller. Until it existed an
install could name its staff source in an environment file and nothing read it, which is a
setting with a writer and no reader, and three refusals nobody could meet.

**Nothing here decides anything about a source, and that is the design rather than modesty.**
The sources are `SELECTABLE`, what each means is its own `meaning`, what is unset is
`SelectableSource.unsupplied`, whether the choice can be used at all is `selected_source`,
whether an answer may be believed is `roster_from`, and what a run would change is
`brain.identity.staff_sync.dry_run`. Every refusal a reader sees here is the words of the module
that refused. That is `brain.console.govern_surfaces.source_warnings`' argument about
`source_gaps` applied to the other five answers, and it is
`A_SECOND_OPINION_ABOUT_A_CONFIGURATION_IS_THE_ONE_AN_ADMINISTRATOR_READS`.

**A console page that renders a setting is a console page that renders a credential**, and the
answer taken here is that there is nowhere on it for a value to go. Three pieces of evidence
pointed the same way and all three are somebody else's:

*A rule that filtered on the name would print the value that carries one today.*
`brain.deployment.variables.is_secret_name` answers False for `INSTALL_STAFF_SOURCE_LOCATION`,
correctly, because the name states a place. The values that go in it are a directory address
carrying the base a search starts from, a sheet identifier that is half of a share link, and a
tenant. `selected_source`'s own docstring says the obvious next source to add is one needing an
address **and a credential**, and on the day that lands the guard that would have to catch it is
the one returning False today.

*A value read out of a file and rendered is a value printed, whatever route it took.*
`brain.deployment.installer.value_leaks_in` looked for `$NAME` in its first version, and the one
step in the installer that certainly prints a credential reads it out of a file with `grep` and
went past unnoticed. A screen reading `value_of` is that same route with a stylesheet on it.

*The shape that works is having nowhere to put it.* `brain.firstrun` does not rule that a secret
must not be stored, it scans its own models for a field one could live in and there is none.

So this page renders the **names** of settings and never their values, `SourceOption` and
`Selection` refuse a name `brain.install` does not declare, which is a check no value can pass,
and `staff_source_gaps` compares what a row carries against the values of the settings it names,
so a later edit interpolating one into a sentence is reported rather than reviewed. See
`A_PAGE_THAT_RENDERS_A_SETTING_IS_A_PAGE_THAT_RENDERS_A_CREDENTIAL`. A `Trial` is scanned
through that function's `shown` parameter rather than built by it, because building one means
calling a live staff source: `Trial.refusals` is the one long string on this page that no
constructor here checks, since another module wrote it.

The one value this page does render is the name the install chose, and that is deliberate: it is
one of seven product words, `selected_source`'s refusal quotes it verbatim when it is none of
them, and a page showing that refusal while withholding what it is about would be a reader
looking at an argument with the subject removed.

**The trial is the interesting half and it is a wider read than the page it sits on.** Naming
who would be added and who has gone missing is a statement about people, and the Staff sources
screen is a configuration screen: `brain.console.reads` separates existence, configuration and
content precisely so that reaching the third is a grant somebody wrote. `TRIAL_READ` is the
screen's own read at `Plane.CONTENT`, derived from it rather than respelled, so a renamed tool
or capability moves both. See
`NAMING_WHO_WOULD_JOIN_IS_A_CONTENT_DISCLOSURE_ON_A_CONFIGURATION_SCREEN`.

**There is no count of what was withheld anywhere here, and the reason is structural rather than
remembered.** A source sits at `brain.console.govern.NOWHERE`, which is
`brain.console.govern_surfaces.A_ROSTER_IS_THE_WHOLE_COMPANYS_LIST_AND_SITS_IN_NO_DEPARTMENT`,
so a scoped grant matches no source and the answer to every function here is the whole page or
none of it. There is no partial trial for a count to sit beside. See
`A_SOURCE_SITS_NOWHERE_SO_THE_ANSWER_IS_EVERYTHING_OR_NOTHING`.

Rejected: naming this module `staff_sources`. That is the screen key, and
`brain.console.govern_surfaces.staff_source_rows` already answers for that screen with the
sources that have run. A module named for the screen reads as the screen's module and this is
half of it, which is the confusion `brain.console.version_view` records about not calling itself
`release_view`.

Rejected: naming it `staff_source_setup`. `brain.setup_wizard` is first run and closes for ever
once an administrator exists; this page is opened afterwards and opened again, and a console
module called setup reads as part of the thing it is not.

Rejected: copying `DryRun`'s fields onto a row of this module's own. `Trial` carries the plan
`dry_run` produced. Restating nine fields would be a second answer to what a sync proposes, and
`brain.identity.staff_sync` opens by saying a dry run assembled by a different code path is a
rehearsal of a different performance.

Rejected: taking a `Roster` rather than a `StaffSource`. It is the easier parameter and it walks
past `roster_from`, which is the function that checks the source that answered against the
source this install chose, refuses a widening, and refuses a roster of nobody. A page that took
the roster would be testing an answer somebody else had already accepted.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock. `now` is a
parameter, the environment arrives as a mapping and is read only through `brain.install.value_of`,
and the one call that reaches a server is `roster_from`'s call to the source handed in.

Task ids: M1.6.11
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Final

from brain.console.govern import NOWHERE, _in_reach
from brain.console.reads import ConsoleRead, Plane, permitted
from brain.console.screens import screen
from brain.core.entitlement import EntitlementSet
from brain.identity.directory import DirectoryAssertion
from brain.identity.staff_source import (
    SELECTABLE,
    SELECTABLE_BY_NAME,
    STAFF_SOURCE_SETTING,
    GroupRule,
    SelectableSource,
    StaffSource,
    StaffSourceError,
    roster_from,
    selected_source,
)
from brain.identity.staff_sync import DryRun, dry_run
from brain.install import BY_NAME, value_of
from brain.ops.jobs import hidden_count_fields

# ------------------------------------------------------------------ written-down reasons
#: Why this page shows the names of settings and never what they are set to.
A_PAGE_THAT_RENDERS_A_SETTING_IS_A_PAGE_THAT_RENDERS_A_CREDENTIAL: Final = (
    "A staff source is pointed somewhere, and the obvious field beside the name of a setting "
    "is what it is currently set to. brain.deployment.variables.is_secret_name answers False "
    "for the location setting, correctly, because the name states a place; the values that go "
    "in it are a directory address carrying the base a search starts from, a sheet identifier "
    "that is half a share link, and a tenant that is paired with a client secret the moment a "
    "source needs two settings. So a rule filtering on the name would print the one value that "
    "carries a credential today, and brain.deployment.installer.value_leaks_in already learned "
    "the sibling of that lesson: a value read out of a file and rendered is a value printed. "
    "The answer is brain.firstrun's, which is to have nowhere to put one: this page carries "
    "setting names, every name is checked against brain.install's declaration, and a value is "
    "not a declared setting name."
)

#: Why every refusal on this page is the refusing module's own words.
A_SECOND_OPINION_ABOUT_A_CONFIGURATION_IS_THE_ONE_AN_ADMINISTRATOR_READS: Final = (
    "Six modules already answer the questions this page asks: which sources exist, what each "
    "means, what is unset, whether the choice can be used, whether the answer may be believed, "
    "and what a run would change. A console that restated any of them would be a second "
    "opinion about a configuration, and the console's is the one an administrator reads before "
    "wiring a source, so it is the one that would look authoritative while being the copy that "
    "drifts. Every sentence a reader sees here is carried, not composed."
)

#: Why the preview needs a wider grant than the page it sits on.
NAMING_WHO_WOULD_JOIN_IS_A_CONTENT_DISCLOSURE_ON_A_CONFIGURATION_SCREEN: Final = (
    "The Staff sources screen is on the configuration plane, and its row deliberately carries "
    "no headcount at all: brain.console.govern_surfaces.A_HEADCOUNT_IS_A_COMPANY_FACT_AND_THIS"
    "_IS_A_SCREEN_ABOUT_PLUMBING is that decision. A trial is the opposite shape on purpose, "
    "because a preview that names nobody proves nothing about whether a source is pointed at "
    "the right place, and the names it carries are the company's staff. Existence, "
    "configuration and content are three disclosures for exactly this reason, so the trial is "
    "the same screen's read at the content plane and reaching it is a grant somebody wrote."
)

#: Why nothing here reports what it did not show.
A_SOURCE_SITS_NOWHERE_SO_THE_ANSWER_IS_EVERYTHING_OR_NOTHING: Final = (
    "A roster is one list for the whole company and the department is a column inside it, so "
    "brain.console.govern_surfaces places a source at brain.console.govern.NOWHERE and "
    "Clause.matches refuses a field the row does not have. A department-scoped grant over "
    "staff sources therefore reaches no source, which makes every answer on this page the "
    "whole of it or none of it. That is what removes the count rather than a rule somebody "
    "keeps: there is no partial trial for a number to sit beside, and no subtraction between "
    "two readings that could stand in for one."
)


# ------------------------------------------------------------------ the two reads
#: The screen this page is, named once so the reads below and a test read the same registry.
THE_SCREEN: Final = "staff_sources"

#: What the page itself needs: the Staff sources screen's own read, at its own plane.
PAGE_READ: Final[ConsoleRead] = screen(THE_SCREEN).read

#: What the trial needs: the same screen, the same tool and the same capability, one plane
#: wider.
#:
#: Derived from `PAGE_READ` rather than spelled again, so a renamed tool or a changed
#: capability moves both and cannot leave the trial reachable through a grant the page is not.
#: The tool is deliberately the screen's own rather than a second one: a tool outside `SCREENS`
#: is a tool `brain.console.screens.unregistered_tools` never looks at, which is a console read
#: with nothing watching whether anything answers it.
TRIAL_READ: Final[ConsoleRead] = ConsoleRead(
    screen=PAGE_READ.screen,
    tool=PAGE_READ.tool,
    requires=PAGE_READ.requires,
    plane=Plane.CONTENT,
)


def _undeclared(names: Iterable[str]) -> tuple[str, ...]:
    """Every one of these that `brain.install` does not declare as a setting.

    The check a value cannot pass, and the whole of this page's answer about credentials
    expressed as a comparison rather than as a rule. `brain.install.BY_NAME` holds the settings
    an install can set; a sheet identifier, a directory address and a client secret are none of
    them. See `A_PAGE_THAT_RENDERS_A_SETTING_IS_A_PAGE_THAT_RENDERS_A_CREDENTIAL`.
    """
    return tuple(sorted({one for one in names if one not in BY_NAME}))


def _strings_on(row: object) -> Iterator[str]:
    """Every string one of this page's rows carries, whatever field it sits in.

    Walked rather than listed, so a field added later is scanned by the credential check
    without anybody remembering to add it there. Tuples are looked inside because `needs` and
    `unsupplied` are tuples of names and a value would arrive in one of them.
    """
    for declared in fields(row):  # type: ignore[arg-type]
        value = getattr(row, declared.name)
        if isinstance(value, str):
            yield value
        elif isinstance(value, tuple):
            yield from (one for one in value if isinstance(one, str))


def _may_read(read: ConsoleRead, entitlement: EntitlementSet, now: datetime | None) -> bool:
    """Whether this reader may make this read of a source that sits nowhere.

    Two questions and neither answers the other. `permitted` asks whether the caller holds the
    tool's capability and reaches the plane; `_in_reach` asks whether the scope that capability
    was granted in admits a row placed at `NOWHERE`, which is the pair of public calls
    `brain.console.govern_surfaces.staff_source_rows` makes about a source that has run. A
    department-scoped grant passes the first and fails the second, and it is the second that
    makes every answer here whole or absent. See
    `A_SOURCE_SITS_NOWHERE_SO_THE_ANSWER_IS_EVERYTHING_OR_NOTHING`.
    """
    if not permitted(read, entitlement, now):
        return False
    return _in_reach(entitlement, read.requires, NOWHERE, now)


# ------------------------------------------------------------------ what can be chosen
@dataclass(frozen=True)
class SourceOption:
    """One answer this install could give to where it keeps its staff list.

    Every field is `SelectableSource`'s own except `chosen` and `unsupplied`, and neither of
    those is computed here: the first is the setting compared with the name, the second is
    `SelectableSource.unsupplied`. There is no field for a location, an address, a credential or
    a value of any kind, which is
    `A_PAGE_THAT_RENDERS_A_SETTING_IS_A_PAGE_THAT_RENDERS_A_CREDENTIAL` expressed as a shape.
    """

    name: str
    #: What choosing it means, in `SelectableSource`'s own words and never a summary of them.
    meaning: str
    #: False for the one option that reads no list at all, so a page can say there is nothing
    #: to test rather than offering a trial that would refuse.
    reads_a_list: bool
    #: The installation settings that must carry a value before this source can be read, by
    #: name. Never a value, and `__post_init__` is what makes that true rather than a habit.
    needs: tuple[str, ...]
    #: The subset of `needs` this installation has left at its declared default.
    unsupplied: tuple[str, ...]
    #: Whether `INSTALL_STAFF_SOURCE` names this one. Not whether it can be used: that is
    #: `Selection`, because a chosen source with a setting unset is chosen and refused.
    chosen: bool

    def __post_init__(self) -> None:
        undeclared = _undeclared((*self.needs, *self.unsupplied))
        if undeclared:
            msg = (
                f"{self.name!r} offers {list(undeclared)} as settings somebody can set and "
                "brain.install declares none of them, so this row is carrying values where it "
                "should carry names. "
                + A_PAGE_THAT_RENDERS_A_SETTING_IS_A_PAGE_THAT_RENDERS_A_CREDENTIAL
            )
            raise ValueError(msg)
        loose = sorted(set(self.unsupplied) - set(self.needs))
        if loose:
            msg = (
                f"{self.name!r} reports {loose} unset and does not need them, so the page asks "
                "somebody to set a value that would change nothing about whether this source "
                "can be read"
            )
            raise ValueError(msg)


def choices(
    entitlement: EntitlementSet,
    now: datetime | None = None,
    *,
    env: Mapping[str, str] | None = None,
    sources: Sequence[SelectableSource] = SELECTABLE,
) -> tuple[SourceOption, ...]:
    """Every staff list this install could choose, what each means, and what each still needs.

    Read out of `SELECTABLE` in its declared order, which is the order a refusal lists them in,
    so the page and the message somebody gets when they mistype agree without either being
    sorted. A seventh source is a row in that tuple and nothing here.

    Empty for a reader who may not read this screen, and empty is also what an install with no
    sources would show: see `A_SOURCE_SITS_NOWHERE_SO_THE_ANSWER_IS_EVERYTHING_OR_NOTHING` for
    why there is no partial answer between those and therefore nothing to count.

    `sources` is a parameter for the reason `selected_source` has one, which is that every
    source declared today needs at most one setting: a page built only from the module's own
    tuple could never be shown a source needing two, and the test that proves several unset
    settings are all reported is the test that cannot be written.
    """
    if not _may_read(PAGE_READ, entitlement, now):
        return ()
    named = value_of(STAFF_SOURCE_SETTING, env)
    return tuple(_option(one, named=named, env=env) for one in sources)


def _option(one: SelectableSource, *, named: str, env: Mapping[str, str] | None) -> SourceOption:
    """One row, built where `staff_source_gaps` can build it too.

    Private and shared rather than inlined into `choices`, because the credential check reads
    the rows this page renders and a check that built its own would be checking a shape nobody
    is shown.
    """
    return SourceOption(
        name=one.name,
        meaning=one.meaning,
        reads_a_list=one.reads_a_list,
        needs=one.needs,
        unsupplied=one.unsupplied(env),
        chosen=one.name == named,
    )


# ------------------------------------------------------------------ what has been chosen
@dataclass(frozen=True)
class Selection:
    """Which staff list this install has chosen, and what stands between it and being read.

    **`refusal` is `selected_source`'s own message and this module composes none of it.** The
    two refusals that function raises are the two states worth showing: a name outside the set,
    and a recognised name whose settings nobody supplied. Rewriting either into console prose
    would produce a second description of a configuration, which is
    `A_SECOND_OPINION_ABOUT_A_CONFIGURATION_IS_THE_ONE_AN_ADMINISTRATOR_READS`.

    `ready` is derived rather than stored, so a row cannot say it is ready while carrying the
    reason it is not.
    """

    #: What `INSTALL_STAFF_SOURCE` is set to, whether or not it names a source that exists.
    name: str
    #: `SelectableSource.meaning` when the name is one, and empty when it is not, because there
    #: is no source to be meaningful about and inventing a sentence would answer a refusal.
    meaning: str
    #: Whether the chosen source reads a list at all. False for the name an install that has
    #: chosen nothing carries, which is a decision rather than an absence.
    reads_a_list: bool
    #: The settings this choice needs and this installation has left at their default, by name.
    unsupplied: tuple[str, ...]
    #: Why this choice cannot be used, in the words of the module that refused it. Empty when
    #: it can.
    refusal: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = (
                "a selection naming nothing cannot be read against the setting that made it, "
                "and INSTALL_STAFF_SOURCE always carries a value because it has a default"
            )
            raise ValueError(msg)
        undeclared = _undeclared(self.unsupplied)
        if undeclared:
            msg = (
                f"{self.name!r} reports {list(undeclared)} unset and brain.install declares "
                "none of them, so this row is carrying values where it should carry names. "
                f"{A_PAGE_THAT_RENDERS_A_SETTING_IS_A_PAGE_THAT_RENDERS_A_CREDENTIAL}"
            )
            raise ValueError(msg)
        if self.ready and self.unsupplied:
            msg = (
                f"{self.name!r} is shown as ready to read with {list(self.unsupplied)} unset, "
                "and selected_source refuses exactly that, so this page would be contradicting "
                "the refusal it exists to display"
            )
            raise ValueError(msg)

    @property
    def ready(self) -> bool:
        """Whether this choice can be read. Derived, so it cannot disagree with the refusal."""
        return not self.refusal


def selection(
    entitlement: EntitlementSet,
    now: datetime | None = None,
    *,
    env: Mapping[str, str] | None = None,
    sources: Sequence[SelectableSource] = SELECTABLE,
) -> Selection | None:
    """Which source this install reads, or the refusal standing in the way (M1.6.11).

    **The name is read and the verdict is not.** `brain.install.value_of` says which name is
    configured and `selected_source` says whether it can be used, and reading one setting twice
    is not a second copy of a refusal: a page that worked out for itself that a source was
    pointed nowhere would be the second implementation this module exists not to be.

    `None` for a reader who may not read this screen. That is the same answer they would get
    from an install with nothing to show, which is
    `A_SOURCE_SITS_NOWHERE_SO_THE_ANSWER_IS_EVERYTHING_OR_NOTHING`.
    """
    if not _may_read(PAGE_READ, entitlement, now):
        return None
    return _selection(env=env, sources=sources)


def _selection(*, env: Mapping[str, str] | None, sources: Sequence[SelectableSource]) -> Selection:
    """The chosen source as a row, built where `staff_source_gaps` can build it too.

    Shared with the diagnostic for the reason `_option` is: the credential check reads the rows
    this page renders, and the refusal is the longest string on the page.
    """
    named = value_of(STAFF_SOURCE_SETTING, env)
    known = SELECTABLE_BY_NAME.get(named)
    try:
        chosen = selected_source(env, sources=sources)
    except StaffSourceError as why:
        # Carried rather than rephrased, and the unsupplied settings come from the same source
        # the message named. See `A_SECOND_OPINION_ABOUT_A_CONFIGURATION_IS_THE_ONE_AN_
        # ADMINISTRATOR_READS`.
        return Selection(
            name=named,
            meaning="" if known is None else known.meaning,
            reads_a_list=known is not None and known.reads_a_list,
            unsupplied=() if known is None else known.unsupplied(env),
            refusal=str(why),
        )
    return Selection(
        name=chosen.name,
        meaning=chosen.meaning,
        reads_a_list=chosen.reads_a_list,
        unsupplied=(),
    )


# ------------------------------------------------------------------ testing it before it runs
@dataclass(frozen=True)
class Trial:
    """One run of the chosen source that writes nothing, or the refusal that stopped it.

    **Exactly one of `plan` and `refusals` is set**, refused here rather than left to whatever
    draws this, on `brain.console.version_view.Running`'s argument about a caveat beside a
    version number: a plan shown next to a refusal is a plan somebody applies, and a missing
    plan with nothing saying why sends the reader looking for a setting that would not have
    helped.

    `plan` is `brain.identity.staff_sync.dry_run`'s answer carried whole. Nine fields restated
    here would be a second account of what a sync proposes, and that module opens by saying a
    dry run assembled by a different code path is a rehearsal of a different performance.
    """

    #: The source this trial was against: the chosen name, or what the setting carries when the
    #: refusal is that no such source exists.
    source: str
    #: What a real run would change, computed by the code that would change it. `None` when
    #: nothing could be computed.
    plan: DryRun | None
    #: Why no plan was computed, in the words of the module that refused. Empty when one was.
    refusals: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source.strip():
            msg = (
                "a trial naming no source cannot be read against the setting that chose it, "
                "and the refusal for a name nobody recognises quotes that name"
            )
            raise ValueError(msg)
        if self.plan is not None and self.refusals:
            msg = (
                f"{self.source} was refused and a plan is set beside the refusal. A plan beside "
                "a refusal is a plan somebody applies, and the refusal becomes a note next to "
                "the rows rather than a refusal"
            )
            raise ValueError(msg)
        if self.plan is None and not self.refusals:
            msg = (
                f"{self.source} produced no plan and nothing says why, so the reader is left "
                "looking for a setting that would not have helped"
            )
            raise ValueError(msg)

    @property
    def safe_to_apply(self) -> bool:
        """Whether a caller may execute what this trial describes.

        Asks the plan rather than repeating its rule, so a refusal `dry_run` reported inside
        the plan, such as role rules wired to a source not trusted to assert them, closes this
        as firmly as a refusal that stopped the trial before a plan existed.
        """
        return self.plan is not None and self.plan.safe_to_apply


def trial(
    source: StaffSource,
    entitlement: EntitlementSet,
    now: datetime | None = None,
    *,
    known: Mapping[str, str],
    last_applied: datetime | None,
    rules: Sequence[GroupRule] = (),
    held: Iterable[DirectoryAssertion] = (),
    env: Mapping[str, str] | None = None,
    sources: Sequence[SelectableSource] = SELECTABLE,
) -> Trial | None:
    """Run the chosen source once, change nothing, and say what running it would change.

    The leaf's own word is test, and this is what testing a staff source amounts to: ask the
    source for its roster through `roster_from`, which is the only thing that checks the answer
    against the choice this install made, and hand what comes back to `dry_run`, which is what
    the scheduled sync will hand it to. A trial computed any other way would be a rehearsal of a
    different performance.

    **Three refusals are caught and reported rather than raised**, which is
    `A_DRY_RUN_THAT_CANNOT_SURVIVE_A_BAD_CONFIGURATION_IS_NO_USE_AT_ALL` one layer up: a trial
    is read at exactly the moment somebody is finding out whether a source is wired correctly,
    so the one tool for finding a misconfiguration must survive every misconfiguration.
    `selected_source` refuses a name nobody recognises and a source pointed nowhere;
    `roster_from` refuses a source that reads no list, a roster from somewhere else, a roster
    claiming more than its source is trusted with, and a roster of nobody.

    `None` for a reader who does not reach the content plane. See
    `NAMING_WHO_WOULD_JOIN_IS_A_CONTENT_DISCLOSURE_ON_A_CONFIGURATION_SCREEN`: the rows name
    the company's staff, and a reader holding the configuration grant alone is shown the choice
    and what is unset by the two functions above, with no count beside the absent trial.

    `known`, `last_applied`, `rules` and `held` are `dry_run`'s parameters and are passed
    straight through rather than rebuilt, so a trial and the sync that follows it read the same
    inputs.
    """
    if not _may_read(TRIAL_READ, entitlement, now):
        return None
    try:
        chosen = selected_source(env, sources=sources)
    except StaffSourceError as why:
        return Trial(source=value_of(STAFF_SOURCE_SETTING, env), plan=None, refusals=(str(why),))
    try:
        roster = roster_from(source, chosen)
    except StaffSourceError as why:
        return Trial(source=chosen.name, plan=None, refusals=(str(why),))
    return Trial(
        source=chosen.name,
        plan=dry_run(roster, known=known, last_applied=last_applied, rules=rules, held=held),
        refusals=(),
    )


# ------------------------------------------------------------------------- the diagnostics
#: The rows this page renders, so one check can hold all three to the same shape.
PAGE_ROWS: Final[tuple[type, ...]] = (SourceOption, Selection, Trial)


def staff_source_gaps(
    env: Mapping[str, str] | None = None,
    *,
    sources: Sequence[SelectableSource] = SELECTABLE,
    rows: Sequence[type] = PAGE_ROWS,
    shown: Sequence[object] = (),
    page_read: ConsoleRead = PAGE_READ,
    trial_read: ConsoleRead = TRIAL_READ,
) -> tuple[str, ...]:
    """Everything about this page that would show somebody more than they hold.

    Takes its inputs rather than reading this module's own constants, for the reason
    `brain.console.govern_surfaces.surface_gaps` gives about itself: a diagnostic that can only
    be run against the healthy tree has nothing to report today, so switching off any of its
    refusals changes nothing observable and every one survives a mutation. Calling it with no
    arguments is the deployment question and calling it with constructed inputs is the test.

    Four checks. The first holds the rows to carrying no count of what a reader was not shown.
    The second is the credential answer as a measurement rather than as a rule: every setting a
    source names is read, the rows this page would render are built, and a row carrying that
    value anywhere in it is reported. The third and fourth hold the trial's read to being wider
    than the page's and to being the same read otherwise, because a trial readable by whoever
    can read the page turns naming the company's staff into a configuration disclosure, and a
    trial wired to a second tool is a console read
    `brain.console.screens.unregistered_tools` never looks at.

    **`shown` is how a `Trial` gets scanned, and it exists because this function cannot build
    one.** Building a trial means calling a live staff source and a diagnostic must not, so a
    caller holding one hands it over and the same scan runs on it. That matters more than it
    sounds: `Trial.refusals` is the one long string on this page that neither constructor
    checks, because it is written by another module, and a mutation found the tuple walk in
    `_strings_on` unreachable until this parameter existed.
    """
    gaps: list[str] = []

    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(rows)
    )

    named = value_of(STAFF_SOURCE_SETTING, env)
    rendered: list[object] = [_option(one, named=named, env=env) for one in sources]
    rendered.append(_selection(env=env, sources=sources))
    rendered.extend(shown)
    for one in sources:
        for name in one.needs:
            # Only a supplied value can leak: a setting left at its declared default has no
            # value of this install's in it, and `SelectableSource.unsupplied` reports it by
            # name already. The comparison is a containment rather than an equality, because
            # the likely edit is a sentence reading "currently set to ..." rather than a field
            # assigned the value whole, and it errs towards reporting, which is the right
            # direction for a check about a credential.
            value = value_of(name, env)
            if value == BY_NAME[name].default:
                continue
            gaps.extend(
                f"a row of this page carries what {name} is set to rather than its name. "
                f"{A_PAGE_THAT_RENDERS_A_SETTING_IS_A_PAGE_THAT_RENDERS_A_CREDENTIAL}"
                for row in rendered
                for carried in _strings_on(row)
                if value in carried
            )

    if trial_read.plane <= page_read.plane:
        gaps.append(
            f"the trial reads at the {trial_read.plane.name.lower()} plane and the page reads "
            f"at the {page_read.plane.name.lower()} plane, so naming who would be added and who "
            "has gone missing is reachable by everybody who can read the screen. "
            f"{NAMING_WHO_WOULD_JOIN_IS_A_CONTENT_DISCLOSURE_ON_A_CONFIGURATION_SCREEN}"
        )

    if (trial_read.tool, trial_read.requires) != (page_read.tool, page_read.requires):
        gaps.append(
            f"the trial is wired to {trial_read.tool} requiring {trial_read.requires.value} and "
            f"the page to {page_read.tool} requiring {page_read.requires.value}, so the trial "
            "is behind a grant nobody writes and a tool no screen registry holds"
        )

    return tuple(gaps)
