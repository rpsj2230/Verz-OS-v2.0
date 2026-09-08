"""Six governance listings, and the disclosure each one settles that its owner cannot.

`brain.console.govern` registers eighteen surfaces, claims six of them, and declines twelve on
the grounds that each is "a listing over machinery that exists with only the screen missing".
That is right about the screen and incomplete about the work, and the six below are the ones
where the missing half is a decision rather than a renderer. Every one of them reads a module
that already exists and none of them reimplements one: `brain.core.department` and
`brain.core.scope_sql` decide containment, `brain.identity.staff_source` decides trust,
`brain.console.role_surfaces` and `brain.console.scoped_authority` decide an approval,
`brain.ops.export` builds the export row, `brain.ops.retention` and `brain.ops.erasure` decide
what is kept and what is removed, and `brain.audit.view` is the audit view and there is not a
second one.

**The narrowing is `brain.console.govern._in_reach` and it is imported rather than copied.**
That function is `EntitlementSet.scope_for` followed by `Scope.matches`, the pair of public
calls `brain.console.role_surfaces._may_approve` makes about an approver, and
`brain.console.scoped_authority` already names it in its own docstring as the row form of the
rule `within_reach` asks about a predicate. The underscore says it is not part of the govern
screens' API; it does not say write a second one, and a second one is the thing that would go
wrong here. Nothing below restates any part of it: every narrowing is that call or
`within_reach`, which is the same first half followed by `scope_narrows`.

**A scope's name is its predicate spelled in words, so a scope row is whole or absent.** This
is the one place the People screen's shape is wrong. There, a subject appears and their
capabilities are withheld, because the existence of a colleague is not a secret and the
vocabulary is. Here the row is `finance_shared` over `department = finance`, and blanking the
predicate leaves the slug, which is the department named in a slightly friendlier font. So
`scope_rows` filters whole rows by `within_reach`, which asks whether the reader's own grant
of the Scopes screen's capability contains the predicate being listed. See
`A_SCOPE_NAME_IS_THE_PREDICATE_SPELLED_IN_WORDS`.

**A staff source sits nowhere, and that is the answer rather than a gap.** A roster is the
whole company's list, `brain.console.screens` marks the screen `company_wide`, and
`brain.console.govern.NOWHERE` fails closed: a record with no place satisfies no scoped grant.
So a department-scoped `read:staff_source` grant reaches no source at all, which is correct
and is worth a test, because the reading that looks helpful is to show a department admin the
sources feeding their own department, and no such thing exists.

**A staff source row carries no headcount.** `brain.identity.staff_source.Roster` holds the
people; the row holds the source, what it is trusted to assert and whether the run promised to
be complete. Two sources' counts side by side are the people one has and the other does not,
which is a set nobody granted anybody, and a single count is a headcount on a plumbing screen.
See `A_HEADCOUNT_IS_A_COMPANY_FACT_AND_THIS_IS_A_SCREEN_ABOUT_PLUMBING`.

**Three different things wait on a human and each keeps its own authority.** The Approvals
screen's purpose sentence names an action above its rung, a grant and a promotion.
`brain.console.role_surfaces.pending_for` filters the first by the capability the action
requires, `brain.console.scoped_authority.grantable` filters the second by containment, and
`brain.knowledge.visibility.approve_promotion` decides the third. One queue filtered by one
capability would offer somebody a decision they could not make, which is the failure
`AN_APPROVER_MAY_NOT_WAVE_THROUGH_WHAT_THEY_COULD_NOT_DO_THEMSELVES` names, arriving through
the arrangement of the screen rather than through the filter. And a kind the reader may decide
none of is absent rather than empty, because a heading with nothing under it is
`brain.console.workspace.A_TAB_HEADING_WITH_NOTHING_UNDER_IT_IS_A_COUNT_IN_WORDS`.

**Reading that an export happened is not the same question as being able to have made one.**
An export log is a record of a disclosure and is therefore itself one. The capability that
lists it is the Exports screen's own, `read:export`, and it is deliberately not derived from
what the export contained: somebody holding `read:client.*` company-wide could have taken the
export and may not read the log, and somebody holding `read:export` may read the log while
holding nothing over a single row that left. Both directions are tested, because the natural
edit is the first one, written by whoever thinks the log should follow the data. The second
way in is that the reader is named among the export's own subjects, which is the branch
`brain.audit.view.AuditView._may_see` and `brain.console.agent_output.may_see` both have: a
person may learn that their own data left the building.

**The deletion queue does not drain, and saying so is most of the leaf.**
`brain.ops.erasure.StoreEraser` and `brain.ops.retention.StoreSweeper` are protocols and both
of their modules state plainly that nothing implements them. A queue rendered with a due date
and no executor behind it is a compliance claim nobody is keeping, in the one place somebody
would go to check. `drain_gaps` reports it, separately from `surface_gaps` for the reason
`brain.console.agent_output.retention_enforcement_gaps` is separate from `artifact_gaps`: a
deployment check that is red on the day it lands is a check somebody switches off.

**A retention report cannot be narrowed, so it is shown whole or withheld.**
`brain.ops.retention.RetentionReport` carries no subject anywhere and no field one could go
in, which is that module's own decision. A surface that narrowed it would have to invent
per-subject rows, and inventing them is the second implementation this module exists not to
be. So a company-wide reader gets the report and everybody else gets `None`.

**The audit filter's options are the disclosure, and the actor list is the one that has none.**
`brain.audit.view.AuditFilter` refuses an actor filter that is not an identifier, in its own
words a filter is a reference and not a search, and nothing anywhere decides where the list of
references a screen offers comes from. Populated from the ledger it is a directory of everyone
who has ever acted; populated from the page it is a directory of everyone on it. There is no
version of an actor dropdown that is not one, so `AuditFilterOptions` has no field an actor
could arrive in and `surface_gaps` reports one. The two closed vocabularies are offerable, and
the subject kinds are narrowed to the ones the reader holds a capability over, which is their
own reach read back to them.

**Rejected: a second audit view.** `brain.audit.view.AuditView` filters per reader, pages by
cursor, and M33.4.1.1 asserts that no actor is exempt including the most privileged. Nothing
here reads an entry, and the one thing this adds is the options a screen may put in front of
somebody before they read any.

**Rejected: a capability of this module's own, anywhere.** Every capability used below is a
screen's own requirement, read off `brain.console.screens` at the call site rather than
written out, which is `brain.console.govern.VOCABULARY_SCREEN`'s construction. The four screen
keys held as constants are pinned against the capability each screen requires by a test that
spells that capability out, for the reason `brain.console.scoped_authority.REACH_AUTHORITY` is
pinned that way: read off the registry on both sides, the comparison would be a constant
against itself and repointing the key would move both. A mutation proved it: repointing
`SCOPES_SCREEN` is invisible to every narrowing test in the file, because those read the
requirement off whatever key the constant holds, and only the spelled-out pin fails.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock; `now` is a
parameter, as in every sibling in this package. Nothing writes: `deletion_rows` returns the
queue and removes nothing, and `approval_sections` offers decisions and takes none.

**No console screen exists behind any of these six**, exactly as `brain.console.govern`,
`brain.console.workspace` and `brain.console.screens` each say of their own. What is claimed
is the disclosure decision, which is the half a screen cannot supply.

Task ids: M27.3.2, M27.3.5, M27.3.7, M27.3.9
Task ids: M27.3.10, M27.3.18
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.audit.ledger import SUBJECT_KINDS, AuditAction
from brain.audit.view import CAPABILITY_BY_KIND
from brain.console.govern import NOWHERE, Placed, _in_reach
from brain.console.reads import permitted
from brain.console.role_surfaces import pending_for
from brain.console.scoped_authority import grantable, within_reach
from brain.console.screens import offerable, screen
from brain.core.department import ScopeRecord, admits_department
from brain.core.entitlement import EntitlementSet
from brain.gate.leash import SuspendedAction
from brain.identity.packs import SubjectGrant
from brain.identity.staff_source import Asserts, Roster, source_gaps
from brain.knowledge.visibility import PromotionProposal, VisibilityError, approve_promotion
from brain.ops.erasure import deletion_order
from brain.ops.export import ExportAudit, withheld_names_on
from brain.ops.jobs import hidden_count_fields
from brain.ops.retention import RetentionReport, Store

# ------------------------------------------------------------------ written-down reasons
#: Why a scope row is shown whole or not at all, with no blanked predicate.
A_SCOPE_NAME_IS_THE_PREDICATE_SPELLED_IN_WORDS: Final = (
    "The People screen shows a subject and withholds their capabilities, because the "
    "existence of a colleague is not a secret and the vocabulary is. A scope row is not that "
    "shape: finance_shared is department = finance with a friendlier font on it, and web_tree "
    "is the prefix over scope_path written as a name. Blanking the predicate and keeping the "
    "slug therefore discloses exactly what the blanking was for, so the row is filtered whole "
    "by whether the reader's own grant of the Scopes screen's capability contains it."
)

#: Why a department listing is filtered by satisfiability rather than by a registry.
A_LISTING_OF_DEPARTMENTS_IS_AN_ORG_CHART_A_REFUSAL_HANDED_OVER: Final = (
    "brain.core.department.plan_cross_department refuses to be handed the department "
    "registry, in its own words, because the gap list would become an inventory of the "
    "departments the asker cannot see and they would learn the org chart from a refusal. A "
    "Scopes and departments screen is that registry with a heading on it. The names offered "
    "are therefore the ones the reader's own scope admits, decided by admits_department, "
    "which asks satisfiability rather than looking for a department clause: most scopes carry "
    "none and do reach every department, and a test for the clause would report the opposite."
)

#: Why a staff source row carries no number of people.
A_HEADCOUNT_IS_A_COMPANY_FACT_AND_THIS_IS_A_SCREEN_ABOUT_PLUMBING: Final = (
    "The obvious column on a staff sources screen is how many people each source returned, "
    "and it is two disclosures. One count is a headcount, which is a fact about the company "
    "on a screen about where a list is read from. Two counts side by side are the people one "
    "source has and the other does not, which is a set difference nobody granted anybody and "
    "which moves when somebody joins or leaves. The row carries the source, what it may "
    "assert and whether the run promised to be whole, and there is no field a number fits in."
)

#: Why a source with no place is reached only by a company-wide grant.
A_ROSTER_IS_THE_WHOLE_COMPANYS_LIST_AND_SITS_IN_NO_DEPARTMENT: Final = (
    "brain.console.screens marks the staff sources screen company_wide, and the reading that "
    "looks helpful is to show a department admin the sources feeding their own department. No "
    "such thing exists: a roster is one list for the whole company and the department is a "
    "column inside it. So a source is placed at brain.console.govern.NOWHERE, which fails "
    "closed because Clause.matches refuses a field the row does not have, and a "
    "department-scoped grant over staff sources therefore reaches none of them."
)

#: Why the approvals queue is three lists rather than one.
THREE_THINGS_WAIT_ON_A_HUMAN_AND_EACH_KEEPS_ITS_OWN_AUTHORITY: Final = (
    "The Approvals screen's purpose sentence names an action above its rung, a grant and a "
    "promotion, and the three are decided by three different modules with three different "
    "capabilities: the capability the action itself requires, containment of the scope the "
    "grant is written over, and approve:knowledge.visibility. One queue filtered by the "
    "screen's own capability would offer an approver decisions they could not make and hide "
    "ones they could, which is the failure the role filter would have produced, arriving "
    "through the arrangement of the screen instead of through the filter."
)

#: Why a kind the reader may decide none of has no heading.
A_SECTION_HEADING_WITH_NOTHING_UNDER_IT_IS_A_COUNT_IN_WORDS: Final = (
    "A heading reading Grants above an empty list tells the reader that grants are waiting "
    "which they may not see, which is the subtraction disclosure spelled out rather than "
    "counted. brain.console.workspace makes the same argument about a tab strip and "
    "brain.console.screens.grouped about an empty menu section. A kind with nothing in it and "
    "a kind the reader may decide none of are one absence, so the section is dropped."
)

#: Why the export log follows the screen's capability and never the exported data's.
WHO_MAY_READ_THAT_AN_EXPORT_HAPPENED_IS_NOT_WHO_COULD_HAVE_MADE_IT: Final = (
    "An export log is a record of a disclosure and is therefore itself a disclosure, and the "
    "natural edit is to say that whoever could have taken an export may read that one was "
    "taken. That is a different question with a different answer in both directions: it hands "
    "the log to everybody holding a wide read capability, who are the people the log exists "
    "to watch, and it withholds the log from an auditor who holds nothing over the rows. The "
    "capability is the Exports screen's own and is read off the registry at the call site."
)

#: Why a person may read an export row that names them.
A_PERSON_MAY_LEARN_THAT_THEIR_OWN_DATA_LEFT_THE_BUILDING: Final = (
    "brain.audit.view.AuditView admits an entry whose subject is the reader, and "
    "brain.console.agent_output.may_see admits an artifact whose caller is the reader, both "
    "on the same grounds: it is what a subject access request asks for and every fact in it "
    "is a fact about them. An export naming somebody is the sharpest instance of it, because "
    "the row says their data was collected, under which reason and against which written "
    "authorisation, and the person with the strongest claim to that row is its subject."
)

#: Why the deletion queue's rows say nothing about when anything will be removed.
A_QUEUE_NOTHING_DRAINS_IS_A_COMPLIANCE_CLAIM_NOBODY_IS_KEEPING: Final = (
    "brain.ops.erasure.StoreEraser and brain.ops.retention.StoreSweeper are protocols, and "
    "both modules say in their own docstrings that the executor is not built. A row reading "
    "due for deletion, in the one screen somebody opens to check that deletion happens, is "
    "therefore a statement about the future that nothing in this system will make true. The "
    "row carries when the request was made and when it completed, which are both facts, and "
    "the absence of an executor is reported by a diagnostic rather than implied by a blank."
)

#: Why a list of people who asked to be erased is a list about those people.
AN_ERASURE_REQUEST_IS_A_FACT_ABOUT_THE_PERSON_WHO_MADE_IT: Final = (
    "Somebody exercising a right over their own data is usually doing it at the end of "
    "something: a dispute, a departure, a complaint. A queue of erasure requests read by "
    "whoever can open the retention screen is that list of endings, and none of it is a fact "
    "about the estate. So the queue is narrowed by the reader's own grant against the row the "
    "subject sits in, and a subject reaches their own request whatever their grants say, "
    "because a request nobody can follow up is a right nobody can exercise."
)

#: Why a retention report is shown whole or withheld and never narrowed.
A_REPORT_WITH_NO_SUBJECT_ON_IT_CANNOT_BE_NARROWED_TO_ONE: Final = (
    "brain.ops.retention.RetentionReport carries counts per store and there is no subject "
    "anywhere on it and no field one could go in, which is that module's decision and the "
    "reason it is safe to put on a dashboard. Narrowing it to a department would mean "
    "inventing per-subject rows to narrow, and inventing them is a second implementation of "
    "what is kept where. So the report is handed whole to a reader whose grant is "
    "company-wide and withheld from everybody else, which is what a figure about the estate is."
)

#: Why there is no dropdown of actors on the audit screen.
AN_ACTOR_DROPDOWN_IS_A_DIRECTORY_OF_EVERYBODY_WHO_HAS_ACTED: Final = (
    "brain.audit.view.AuditFilter refuses an actor filter that is not an identifier, saying a "
    "filter is a reference and not a search, and it has no opinion about where a screen got "
    "the reference. Built from the ledger the list is everybody who has ever acted; built "
    "from the page it is everybody on it, which turns a page of rows the reader may see into "
    "the set of people behind them. There is no third source, so the options carry the two "
    "closed vocabularies and there is no field an actor could arrive in."
)

#: Why the audit screen's own capability confers no entry.
READ_AUDIT_OPENS_THE_PAGE_AND_READ_AUDIT_DOT_KIND_FILLS_IT: Final = (
    "The Activity screen requires read:audit and brain.audit.view asks read:audit.<kind> per "
    "entry, and Capability.covers does not expand an entity-level grant: read:audit covers "
    "read:audit.* and read:audit itself and neither of the kinds. So a grant of read:audit "
    "alone opens the screen and shows the reader their own entries and nothing else, which is "
    "correct and reads as a broken page. That is a grant somebody stopped writing halfway, "
    "and it is reported as a finding rather than repaired by widening anything."
)


class GovernSurfaceError(Exception):
    """A governance listing was asked for something that would show the wrong person a row.

    Outside `brain.core.errors` for the reason `brain.console.govern.GovernError` gives about
    itself: those five outcomes describe an answer given to somebody asking a question, and
    this is a refusal to assemble an administrative surface. Nobody asking a question sees one.
    """


# ------------------------------------------------ scopes and departments (M27.3.2)
#: The screen whose grant decides whether a scope predicate may be read at all.
#:
#: A screen key rather than a capability written out, so that nothing here can drift from the
#: registry: `scope_rows` asks `screen(...)` at the call site, exactly as
#: `brain.console.govern.VOCABULARY_SCREEN` is asked. `surface_gaps` checks the key resolves.
SCOPES_SCREEN: Final = "scopes"


def scope_rows(
    records: Sequence[ScopeRecord],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> tuple[ScopeRecord, ...]:
    """The scopes this reader may be shown, whole rows only (M27.3.2).

    **Whole or absent, and there is no row with the predicate blanked.** See
    `A_SCOPE_NAME_IS_THE_PREDICATE_SPELLED_IN_WORDS`. That is the opposite arrangement from
    `brain.console.govern.people`, which shows the subject and withholds the capabilities, and
    the difference is that a subject's name says nothing on its own while a scope's name is
    the predicate in other words.

    The test is `brain.console.scoped_authority.within_reach`, which is `scope_for` followed
    by `scope_narrows`: the reader holds the Scopes screen's capability in a scope containing
    the one being listed. It is the predicate form of `brain.console.govern._in_reach` and it
    is imported rather than restated, because a containment test written here would be the
    second implementation `THE_ROW_FORM_AND_THE_PREDICATE_FORM_ARE_ONE_RULE` names.

    `scope_narrows` is sound and incomplete and fails towards False, so a scope the reader
    could in principle have written may be absent because the analysis cannot prove it. That
    is the right direction on a listing as much as on a write: an absent row costs a person a
    question and a wrongly present one is a department name they now have.

    `ScopeRecord` is returned rather than a row type of this module's own, because the record
    already carries the slug, the label, the department flag and the predicate, and a second
    shape would be a second answer to what a scope is.

    Order follows `records`, for the reason `brain.console.screens.offerable` gives: the
    caller's order is usually meaningful and re-sorting discards it. One value comes back and
    there is nowhere in it for what was dropped.
    """
    required = screen(SCOPES_SCREEN).read.requires
    return tuple(one for one in records if within_reach(entitlement, required, one.scope, now))


def departments_offered(
    names: Sequence[str],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> tuple[str, ...]:
    """The department names a filter on this screen may list (M27.3.2).

    `brain.core.department.admits_department` against the scope the reader holds the Scopes
    screen's capability in, then `brain.console.screens.offerable`, which is the console's own
    statement that a dropdown is a listing like any other and returns no count of what it
    dropped. Both are called rather than reimplemented: the first asks satisfiability, which
    is the only correct reading, and the second is where the rule about filter lists lives.

    See `A_LISTING_OF_DEPARTMENTS_IS_AN_ORG_CHART_A_REFUSAL_HANDED_OVER`. `names` is what a
    screen is about to offer, which is usually the departments already on the rows in front of
    the reader; handing in the department registry would produce the inventory
    `plan_cross_department` refuses to produce, and nothing in this signature can stop that,
    which is why it is said here.

    A reader holding nothing gets an empty tuple rather than a refusal, because a filter with
    no options and a filter on a screen nobody opened are the same absence.
    """
    held = entitlement.scope_for(screen(SCOPES_SCREEN).read.requires, now)
    if held is None:
        return ()
    reachable = [one for one in names if admits_department(held, one)]
    return offerable(names, reachable)


# ------------------------------------------------------------ staff sources (M27.3.5)
#: Field names that would put the roster's contents back on a source row.
#:
#: Restated here rather than imported from `brain.ops.jobs`, whose list is about counts a
#: reader was not shown, for the reason `brain.console.govern.NAMES_THAT_WOULD_NAME_THE_THING`
#: is restated: the word somebody reaches for differs by surface, and the field that breaks
#: this one is called `people` or `headcount` rather than `hidden`.
NAMES_THAT_WOULD_BE_THE_ROSTER: Final[frozenset[str]] = frozenset(
    {
        "credential",
        "endpoint",
        "headcount",
        "members",
        "password",
        "people",
        "person_count",
        "secret",
        "staff",
        "token",
        "url",
    }
)


@dataclass(frozen=True)
class StaffSourceRow:
    """One roster source: where it is, what it may say, and whether it answered in full.

    Four fields and no fifth. There is no count of people, no credential and no endpoint,
    which is `A_HEADCOUNT_IS_A_COMPANY_FACT_AND_THIS_IS_A_SCREEN_ABOUT_PLUMBING` expressed as
    a shape rather than as a rule somebody remembers, and `surface_gaps` reports one if a
    later edit adds it.

    `asserts` is what the source is *trusted* to say, from `Roster.asserts`, and never what
    its rows happened to contain. The two look the same on a screen and only the first is a
    decision somebody made: a spreadsheet whose rows all carry a department still asserts
    existence alone, and a row built from the people would say otherwise.
    """

    source: str
    #: `brain.identity.staff_source.Asserts` values, sorted, so two readings agree.
    asserts: tuple[str, ...]
    #: Whether the run promised to be the whole list. `Roster.complete`, which is what decides
    #: whether anybody may be removed on the strength of it.
    complete: bool
    #: When the source last ran, where anything recorded it. `None` otherwise, which is not a
    #: statement that it never ran.
    last_run_at: datetime | None = None


def staff_source_rows(
    rosters: Sequence[Roster],
    entitlement: EntitlementSet,
    now: datetime | None = None,
    *,
    last_run: Mapping[str, datetime] | None = None,
) -> tuple[StaffSourceRow, ...]:
    """Where the staff list is linked from and what each source may assert (M27.3.5).

    **Every source sits at `NOWHERE`**, so only a company-wide grant of the Staff sources
    screen's capability reaches any of them. See
    `A_ROSTER_IS_THE_WHOLE_COMPANYS_LIST_AND_SITS_IN_NO_DEPARTMENT`. The narrowing is still
    asked per row rather than once, because the interesting failure is somebody later placing
    a source in a department to make the screen useful for a department admin, and the check
    that would then decide is this one.

    Ordered by source name, so two readings of an unchanged configuration are the same list.
    A source configured twice appears twice, which is not tidied here: `source_gaps` is where
    a configuration is judged, and collapsing two rows would hide the second authority it
    warns about.
    """
    when = last_run or {}
    required = screen("staff_sources").read.requires
    rows = [
        StaffSourceRow(
            source=one.source,
            asserts=tuple(sorted(name.value for name in one.asserts)),
            complete=one.complete,
            last_run_at=when.get(one.source),
        )
        for one in rosters
        if _in_reach(entitlement, required, NOWHERE, now)
    ]
    return tuple(sorted(rows, key=lambda one: one.source))


def source_warnings(rosters: Iterable[Roster]) -> tuple[str, ...]:
    """What is wrong with this set of sources, in the words of the module that decides.

    `brain.identity.staff_source.source_gaps`, called and not restated. It knows the three
    findings that matter, including the one nobody thinks of, which is two sources both
    trusted to assert roles reconciling their own rows and neither seeing the other's. A copy
    of any of that here would be a second opinion about a configuration, and the console's is
    the one an administrator reads, so it is the one that would look authoritative.
    """
    return source_gaps(rosters)


# ------------------------------------------------------------- approvals queue (M27.3.7)
class Waiting(enum.StrEnum):
    """What can be waiting on a human. Three members, from the screen's own purpose sentence.

    There is deliberately no fourth for "other". A kind nobody named is a kind nobody decided
    an authority for, and it would arrive on this screen filtered by whatever the screen
    itself requires, which is `THREE_THINGS_WAIT_ON_A_HUMAN_AND_EACH_KEEPS_ITS_OWN_AUTHORITY`
    broken by the member that was added to save writing a fourth function.
    """

    #: An action above its rung, suspended by `brain.gate.leash`.
    ACTION = "action"
    #: A grant somebody proposed, waiting for an admin who could have written it.
    GRANT = "grant"
    #: A knowledge item somebody proposed widening.
    PROMOTION = "promotion"


#: What one section of the queue can hold. A union rather than a common base class, because
#: the three come from three packages and a base class here would be this module asking them
#: to agree about something none of them needs to know.
type WaitingItem = SuspendedAction | SubjectGrant | PromotionProposal


@dataclass(frozen=True)
class ApprovalSection:
    """One kind of waiting thing, and the ones this approver may decide.

    Never empty: `approval_sections` drops a section rather than rendering a heading over
    nothing. See `A_SECTION_HEADING_WITH_NOTHING_UNDER_IT_IS_A_COUNT_IN_WORDS`. The
    constructor refuses one, so a caller assembling sections by hand cannot produce the shape
    either, which is `brain.console.govern.Certification`'s argument about where a refusal goes.
    """

    kind: Waiting
    items: tuple[WaitingItem, ...]

    def __post_init__(self) -> None:
        if not self.items:
            msg = (
                f"the {self.kind.value} section is empty, and a heading with nothing under it "
                f"says something is waiting that this reader may not see. "
                f"{A_SECTION_HEADING_WITH_NOTHING_UNDER_IT_IS_A_COUNT_IN_WORDS}"
            )
            raise GovernSurfaceError(msg)


def may_approve_promotion(
    proposal: PromotionProposal,
    approver_id: str,
    entitlement: EntitlementSet,
    now: datetime,
) -> bool:
    """Whether this person may approve this widening (M27.3.7).

    Asked by calling `brain.knowledge.visibility.approve_promotion` and catching its refusal,
    rather than by restating its three checks here. That is deliberate and it is the only
    reuse in this module that costs something to read: the alternative is three conditions
    copied out of another package, and the day a fourth is added there this listing would
    offer a control the submit path then refuses. An `Approval` is a value and building one
    writes nothing, so the call has no effect beyond the verdict.

    The three that function refuses are the approver being the proposer, an entitlement
    belonging to somebody other than the named approver, and the absence of
    `approve:knowledge.visibility`. Only the first is specific to a promotion, and it is the
    one a queue would otherwise get wrong: a proposer's own proposal in their own queue is the
    gate defeated with every record looking correct.
    """
    try:
        approve_promotion(
            proposal,
            approver_id=approver_id,
            entitlement=entitlement,
            now=now,
        )
    except VisibilityError:
        return False
    return True


def approval_sections(
    entitlement: EntitlementSet,
    now: datetime,
    *,
    approver_id: str = "",
    suspensions: Sequence[SuspendedAction] = (),
    grants: Sequence[SubjectGrant] = (),
    promotions: Sequence[PromotionProposal] = (),
) -> tuple[ApprovalSection, ...]:
    """What is waiting on this human, by kind, with nothing they cannot decide (M27.3.7).

    Three filters and three modules, none of them written here. `pending_for` is
    `brain.console.role_surfaces`' answer about a suspended action, already built and tested
    as M33.6.1.1; `grantable` is `brain.console.scoped_authority`'s answer about a proposed
    grant, which asks containment of the scope and of the capability; `may_approve_promotion`
    is `brain.knowledge.visibility`'s answer about a widening. See
    `THREE_THINGS_WAIT_ON_A_HUMAN_AND_EACH_KEEPS_ITS_OWN_AUTHORITY`.

    **A kind with nothing in it is absent.** See
    `A_SECTION_HEADING_WITH_NOTHING_UNDER_IT_IS_A_COUNT_IN_WORDS`. The empty and the withheld
    are one absence, which is `brain.console.workspace.tab_strip`'s conjunction one surface
    over, and it is why `ApprovalSection` refuses to hold no items.

    `approver_id` defaults to empty and a blank one decides no promotion, because
    `approve_promotion` compares it against the entitlement's own principal and an unstated
    approver is not the entitlement's owner. It is a separate argument rather than read off
    the entitlement because that is the pair the promotion gate checks, and reading one from
    the other here would remove the check by supplying its answer.

    Sections come back in `Waiting`'s declaration order, which is the order the screen's own
    purpose sentence names them in, and each section keeps its source's order.
    """
    found: list[ApprovalSection] = []
    by_kind: tuple[tuple[Waiting, tuple[WaitingItem, ...]], ...] = (
        (Waiting.ACTION, pending_for(entitlement, suspensions, now)),
        (Waiting.GRANT, grantable(grants, entitlement, now)),
        (
            Waiting.PROMOTION,
            tuple(
                one
                for one in promotions
                if may_approve_promotion(one, approver_id, entitlement, now)
            ),
        ),
    )
    found.extend(ApprovalSection(kind=kind, items=items) for kind, items in by_kind if items)
    return tuple(found)


# ------------------------------------------------------------------- exports (M27.3.9)
#: The screen whose grant decides whether an export row may be read.
#:
#: A screen key, asked at the call site, so the log cannot acquire a capability of its own.
#: See `WHO_MAY_READ_THAT_AN_EXPORT_HAPPENED_IS_NOT_WHO_COULD_HAVE_MADE_IT`.
EXPORT_LOG_SCREEN: Final = "exports"


def export_log(
    entries: Sequence[Placed[ExportAudit]],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> tuple[ExportAudit, ...]:
    """What left the building and who took it, as this reader may see it (M27.3.9).

    Two ways in and no third, which is the shape `brain.audit.view.AuditView._may_see` and
    `brain.console.agent_output.may_see` both have.

    **The reader is one of the subjects.** See
    `A_PERSON_MAY_LEARN_THAT_THEIR_OWN_DATA_LEFT_THE_BUILDING`. An export covering everybody
    does not admit anybody this way, because `all_subjects` means the request named no
    shortlist and there is nobody on the row for the reader to be. An export of the whole
    company reaching every employee's screen would be the log becoming a company-wide read.

    **This read `not one.record.all_subjects and ...` until 2026-09-08, and the term is gone
    because the rule moved to where it cannot be bypassed.** `ExportAudit` now refuses a row
    that both covers everybody and names a shortlist, in the same words `BulkExportRequest`
    already used, so there is no such row for this filter to meet. Keeping the term as well
    would be two checks nothing can separate, which is the finding `friction` made about its
    own pair in `brain.console.govern`.

    **A grant covers export rows, in a scope that admits the row.** The capability is the
    Exports screen's own and is deliberately not the capability the export's contents needed;
    see `WHO_MAY_READ_THAT_AN_EXPORT_HAPPENED_IS_NOT_WHO_COULD_HAVE_MADE_IT`.

    `ExportAudit` comes back unchanged rather than through a row type of this module's own.
    `brain.ops.export` already decided that the row carries identifiers, a reason and counts
    and nothing exported, and `withheld_names_on` is that decision as a check; a second shape
    here would be a second answer to what an export log row is, and the field somebody would
    add to it is the one that shortcut ended.

    Order follows `entries`, which is usually newest first and is information. One value, and
    no count of the exports this reader was not shown.
    """
    required = screen(EXPORT_LOG_SCREEN).read.requires
    return tuple(
        one.record
        for one in entries
        if entitlement.principal_id in one.record.subjects
        or _in_reach(entitlement, required, one.where, now)
    )


# ----------------------------------------------------- retention and erasure (M27.3.10)
#: The screen whose grant decides whether the retention report and the queue may be read.
RETENTION_SCREEN: Final = "retention"


@dataclass(frozen=True)
class DeletionRow:
    """One erasure request, and what has actually happened to it (M27.3.10).

    Four fields and none of them a promise. There is no `due_at` and no `will_complete_at`,
    which is `A_QUEUE_NOTHING_DRAINS_IS_A_COMPLIANCE_CLAIM_NOBODY_IS_KEEPING` expressed as a
    shape: a date that says when something will be removed is a statement about a future
    nothing in this repository brings about, and it would be read on the one screen somebody
    opens to check that removal happens.

    `stores` is `brain.ops.erasure.deletion_order`, which puts sources before the copies drawn
    from them, and it is called rather than listed: a copy of the order here would be the one
    that got a store added to it late, and a purge in the wrong order leaves a deleted person
    answerable from cache with every log line saying the deletion succeeded.
    """

    subject_id: str
    requested_at: datetime
    #: The order the stores would be worked through, from `erasure.deletion_order`.
    stores: tuple[Store, ...]
    #: When the request was completed, where anything completed it. `None` is the ordinary
    #: state and says nothing about when it will change.
    completed_at: datetime | None = None


def deletion_rows(
    requests: Sequence[Placed[DeletionRow]],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> tuple[DeletionRow, ...]:
    """The erasure queue, as this reader may see it (M27.3.10).

    Two ways in, on the same argument as the export log and for a sharper reason. The reader
    is the subject, because a request nobody can follow up is a right nobody can exercise; or
    a grant of the Retention screen's capability admits the row the subject sits in. See
    `AN_ERASURE_REQUEST_IS_A_FACT_ABOUT_THE_PERSON_WHO_MADE_IT`.

    Order follows `requests`. Nothing here drains anything and there is no control on the row:
    see `drain_gaps`, which reports what is missing rather than leaving a screen to imply it.
    """
    required = screen(RETENTION_SCREEN).read.requires
    return tuple(
        one.record
        for one in requests
        if one.record.subject_id == entitlement.principal_id
        or _in_reach(entitlement, required, one.where, now)
    )


def erasure_request(subject_id: str, requested_at: datetime) -> DeletionRow:
    """One row of the queue, with the store order filled in from the module that owns it.

    A constructor rather than a caller assembling the tuple, so that `deletion_order` is
    called once here instead of at every call site, where one of them would eventually be a
    literal list. Refuses a subject nobody named and a naive instant, on the same grounds
    `brain.console.govern.Certification` refuses both: a queue entry belonging to nobody
    cannot be followed up, and a naive time compares wrongly against an aware boundary.
    """
    if not subject_id.strip():
        msg = "an erasure request naming no subject is a row nobody can act on or answer for"
        raise GovernSurfaceError(msg)
    if requested_at.tzinfo is None:
        msg = "a naive request time compares wrongly against an aware completion time"
        raise GovernSurfaceError(msg)
    return DeletionRow(
        subject_id=subject_id,
        requested_at=requested_at,
        stores=deletion_order(),
    )


def retention_view(
    report: RetentionReport,
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> RetentionReport | None:
    """The retention report, whole, or `None` (M27.3.10).

    **Withheld rather than narrowed**, which is
    `brain.console.workspace.projection`'s decision about a figure made of everybody's spend,
    reached here for a different reason: there is nothing on a `RetentionReport` to narrow.
    See `A_REPORT_WITH_NO_SUBJECT_ON_IT_CANNOT_BE_NARROWED_TO_ONE`.

    The report is placed at `NOWHERE`, so only a company-wide grant of the Retention screen's
    capability reaches it. A department admin therefore sees the deletion queue for their own
    people and no estate counts, which is the honest split: the queue is about people they
    administer and the counts are about stores nobody administers per department.
    """
    if not _in_reach(entitlement, screen(RETENTION_SCREEN).read.requires, NOWHERE, now):
        return None
    return report


def drain_gaps(*, eraser: object | None = None, sweeper: object | None = None) -> tuple[str, ...]:
    """Where the deletion queue and the retention horizons are decided and not applied.

    **This one reports today and is meant to**, which is why it is not part of `surface_gaps`:
    that is a deployment check, and a check that is red on the day it lands is a check
    somebody switches off, which `brain.console.agent_output.retention_enforcement_gaps`
    records about its own finding and `brain.ops.sweeps.sweep_house_style` about its scope.

    Both findings are real. `brain.ops.erasure.StoreEraser` is the protocol an executor must
    satisfy for anything to be deleted and `brain.ops.retention.StoreSweeper` is the one for
    anything to be expired, and both modules state that the executor is not built. Passing
    `None` is the deployment call, because there is nothing to pass; a test hands in a stub
    for one and gets the other finding, which is what makes the two separable.
    """
    findings: list[str] = []
    if eraser is None:
        findings.append(
            "nothing implements brain.ops.erasure.StoreEraser, so an erasure request in this "
            "queue is decided, ordered and never carried out. "
            f"{A_QUEUE_NOTHING_DRAINS_IS_A_COMPLIANCE_CLAIM_NOBODY_IS_KEEPING}"
        )
    if sweeper is None:
        findings.append(
            "nothing implements brain.ops.retention.StoreSweeper, so a horizon in this report "
            "is a window nothing applies and the counts beside it only ever grow"
        )
    return tuple(findings)


# --------------------------------------------------------------------- audit (M27.3.18)
#: The screen the Activity page is registered as.
AUDIT_SCREEN: Final = "audit"

#: Field names by which a list of people could reach the audit filter's options.
#:
#: Names rather than a rule about values, because the failure arrives as a field somebody adds
#: to make the screen usable, and it arrives with one of these on it. See
#: `AN_ACTOR_DROPDOWN_IS_A_DIRECTORY_OF_EVERYBODY_WHO_HAS_ACTED`.
NAMES_THAT_WOULD_BE_AN_ACTOR_LIST: Final[frozenset[str]] = frozenset(
    {"actor", "actors", "people", "principals", "subjects", "users", "who"}
)


@dataclass(frozen=True)
class AuditFilterOptions:
    """What an Activity screen may offer a reader to narrow by (M27.3.18).

    Two fields and no third. There is no list of actors and nowhere to put one, which is
    `AN_ACTOR_DROPDOWN_IS_A_DIRECTORY_OF_EVERYBODY_WHO_HAS_ACTED` expressed as a shape rather
    than as a rule somebody remembers; `surface_gaps` reports one if a later edit adds it. An
    actor filter is still available and is still typed, which is what
    `brain.audit.view.AuditFilter` means by a reference rather than a search.

    Both fields are closed vocabularies the source already declares, so offering them
    discloses nothing that reading `brain.audit.ledger` would not. `subject_kinds` is narrowed
    to the kinds this reader holds a capability over, which is their own reach handed back:
    offering a kind that admits no entry is a filter that returns an empty page for a reason
    the reader cannot see, and that is the shape somebody reads as a bug in the ledger.
    """

    actions: tuple[AuditAction, ...]
    subject_kinds: tuple[str, ...]


def audit_kinds(entitlement: EntitlementSet, now: datetime | None = None) -> tuple[str, ...]:
    """The audit subject kinds this reader holds a capability over, sorted (M27.3.18).

    `brain.audit.view.CAPABILITY_BY_KIND` is asked rather than the capability strings being
    rebuilt from `SUBJECT_KINDS` here, because that mapping is built from the kinds precisely
    so a new kind cannot arrive with no capability governing it, and a second construction
    would be a second place for the noun to be spelled.

    This is the reader's own entitlement read back to them, so it discloses nothing: they
    already hold every grant it reports.
    """
    return tuple(
        kind
        for kind, capability in sorted(CAPABILITY_BY_KIND.items())
        if entitlement.holds(capability, now)
    )


def audit_filter_options(
    entitlement: EntitlementSet,
    now: datetime | None = None,
    *,
    actions: Iterable[AuditAction] = tuple(AuditAction),
) -> AuditFilterOptions:
    """The options this reader's Activity screen may show (M27.3.18).

    `actions` is handed in with the whole closed vocabulary as its default, on
    `brain.console.govern.catalogue`'s argument about a vocabulary: what a particular install
    records is a question for that install, and a function that worked it out would be a
    second answer. It is not narrowed by the reader, because an action is a verb the source
    declares and narrowing it would be the reader's own entitlement wearing the vocabulary's
    heading, which is
    `brain.console.govern.A_CATALOGUE_FILTERED_TO_THE_READER_IS_THEIR_OWN_ENTITLEMENT_RELABELLED`.

    Subject kinds are narrowed, and the asymmetry is deliberate: a kind is not a vocabulary of
    verbs, it is the axis every audit grant is written on, so the kinds a reader holds none of
    are filters that would return an empty page.

    Sorted, because the order of a vocabulary carries no information and two readings of an
    unchanged install should be the same list.
    """
    return AuditFilterOptions(
        actions=tuple(sorted(frozenset(actions), key=lambda one: one.value)),
        subject_kinds=audit_kinds(entitlement, now),
    )


def audit_grant_gaps(
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> tuple[str, ...]:
    """A grant set that opens the Activity screen and reaches no entry on it.

    The same shape as `brain.console.reads.console_gaps`' finding about a caller who reaches
    content and not existence: a combination nobody meant to write, reported rather than
    repaired, because repairing it would mean this module deciding somebody reaches more than
    their grants say. See `READ_AUDIT_OPENS_THE_PAGE_AND_READ_AUDIT_DOT_KIND_FILLS_IT`.

    Their own entries are still visible, which is `AuditView`'s first branch, so the page is
    not empty and that is what makes this worth reporting: it reads as an auditor's screen
    showing one person's activity rather than as a grant somebody stopped writing.
    """
    if not permitted(screen(AUDIT_SCREEN).read, entitlement, now):
        return ()
    if audit_kinds(entitlement, now):
        return ()
    return (
        f"{entitlement.principal_id} may open the {AUDIT_SCREEN} screen and holds no "
        f"capability over any of {sorted(SUBJECT_KINDS)}, so it shows their own entries and "
        f"nothing else. {READ_AUDIT_OPENS_THE_PAGE_AND_READ_AUDIT_DOT_KIND_FILLS_IT}",
    )


# ------------------------------------------------------------------------- the diagnostic
#: The screens these six surfaces read, so a test can hold each key to the registry.
SURFACE_SCREENS: Final[tuple[str, ...]] = (
    SCOPES_SCREEN,
    "staff_sources",
    "approvals",
    EXPORT_LOG_SCREEN,
    RETENTION_SCREEN,
    AUDIT_SCREEN,
)

#: The types a reader of these surfaces is handed. Listed rather than discovered, following
#: `brain.console.govern.GOVERN_ROWS`: a type added here and not to this tuple is a type the
#: checks below never see.
SURFACE_ROWS: Final[tuple[type, ...]] = (
    StaffSourceRow,
    ApprovalSection,
    DeletionRow,
    AuditFilterOptions,
)


def surface_gaps(
    *,
    keys: Sequence[str] = SURFACE_SCREENS,
    rows: Sequence[type] = SURFACE_ROWS,
    source_row: type = StaffSourceRow,
    options_type: type = AuditFilterOptions,
    export_row: type = ExportAudit,
) -> tuple[str, ...]:
    """Everything about these six that would show somebody more than they hold.

    Takes its inputs rather than reading the module's own constants, and a mutation is the
    reason `brain.console.govern.govern_gaps` gives about itself: a diagnostic that can only
    run against the healthy tree has nothing to report on today's data, so switching off any
    of its refusals changes nothing observable and every one of them survives. Calling it with
    no arguments is the deployment check and calling it with a constructed set is the test.

    Six checks. The first holds every screen key to the registry, which is what stops a
    surface asking for a capability nobody registered; the rest hold the row types, and the
    vocabulary a staff source may assert, to their own shape.
    """
    gaps: list[str] = []

    for key in keys:
        try:
            screen(key)
        except KeyError:
            gaps.append(
                f"{key!r} is not a screen, so the surface reading it has no registered "
                "capability and whatever it asks for is a grant nobody reviews"
            )

    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(rows)
    )
    gaps.extend(
        f"{source_row.__name__}.{name} puts the roster back on a plumbing screen. "
        f"{A_HEADCOUNT_IS_A_COMPANY_FACT_AND_THIS_IS_A_SCREEN_ABOUT_PLUMBING}"
        for name in getattr(source_row, "__dataclass_fields__", {})
        if name in NAMES_THAT_WOULD_BE_THE_ROSTER
    )
    gaps.extend(
        f"{options_type.__name__}.{name} is a list of people offered as a filter. "
        f"{AN_ACTOR_DROPDOWN_IS_A_DIRECTORY_OF_EVERYBODY_WHO_HAS_ACTED}"
        for name in getattr(options_type, "__dataclass_fields__", {})
        if name in NAMES_THAT_WOULD_BE_AN_ACTOR_LIST
    )
    gaps.extend(
        f"{export_row.__name__} carries {found}, which travels into this log. "
        f"{WHO_MAY_READ_THAT_AN_EXPORT_HAPPENED_IS_NOT_WHO_COULD_HAVE_MADE_IT}"
        for found in withheld_names_on(export_row)
    )

    # Asked of the enum rather than of a list here, so a fourth member added to `Asserts`
    # fails this rather than quietly becoming a column nobody argued about. A staff source's
    # trust is three declarations and a capability is not one of them, which is that module's
    # rule and the reason it has no fourth member.
    for name in Asserts:
        if name.value in NAMES_THAT_WOULD_BE_THE_ROSTER:
            gaps.append(
                f"a staff source may assert {name.value}, which is the roster's contents "
                "rather than a fact about the source"
            )

    return tuple(gaps)


#: How many surfaces are claimed here, so a test can pin it and a person can quote it.
#:
#: Pinned rather than computed, for the reason `brain.console.govern.GOVERN_SURFACE_COUNT` is:
#: the interesting failure is a surface disappearing in a refactor, and `len(x) == len(x)`
#: would not notice. It is also the number of `Task ids` claimed above, which is what makes it
#: a statement about the work breakdown rather than about this file.
SURFACE_COUNT: Final = 6
