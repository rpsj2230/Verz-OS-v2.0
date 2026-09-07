"""The eighteen governance surfaces: what each shows, to whom, and what it must never show.

Govern is the group where a console is at its most dangerous, because every screen in it is a
screen *about* the permission system rather than a screen the permission system protects. A
report of client revenue discloses revenue. A report of who may read client revenue discloses
that revenue exists, that somebody reaches it, and which of a reader's colleagues does not.
The second is the leak `CLAUDE.md` names in its retrieval example, restated in the permission
vocabulary rather than the data vocabulary, and it is the one nobody reviews because it looks
like administration.

**Almost none of the machinery is here, and that is the design rather than a gap.** Grants are
`brain.identity.packs`, scopes and departments are `brain.core.department`, roles are
`brain.identity.roles`, the vocabulary is `brain.core.entitlement`, staff sources are
`brain.identity.staff_source`, sessions are `brain.identity.sessions`, exports are
`brain.ops.export`, retention and the deletion queue are `brain.ops.retention`, denial patterns
are `brain.ops.denial_alerts`, the approvals queue is `brain.console.role_surfaces.pending_for`,
leash state and the learning tiers are `brain.console.reach_view`, the skill review queue is
`brain.tools.review`, per-item visibility is `brain.knowledge.visibility`, and the client-facing
audit view is `brain.audit.view`. `GOVERN_SURFACES` names the owner of each of the eighteen and
`govern_gaps` imports every one of them, so "this is already built in X" is a check rather than
a sentence in a commit message. A second implementation of any of them is the thing this module
exists not to be.

**What is left after that is the disclosure decision, and it is written down nowhere else.**
Which rows a governance screen shows, whether the capability vocabulary may be named on it, and
which control it may offer. Six of the eighteen have one of those built here, and each is a rule
somebody could get wrong in a way that looks like the screen working.

**A governance record is not a row, so it arrives with the row it sits in.** A scope is a
predicate over rows; a grant, a role grant and a session are records about people and none of
them carries the department a person sits in. `Placed` is the pairing and `_in_reach` is the
narrowing: `EntitlementSet.scope_for` followed by `Scope.matches`, which is the pair of public
calls `brain.console.role_surfaces._may_approve` makes about an approver, asked here about a
reader. There is one of it and four surfaces call it.

**The menu decides whether a screen opens and nothing here repeats that.**
`brain.console.screens.navigation` already answers "may this person open the Sessions screen",
by the tool's capability and the console plane together. Asking it again in every function
below would be a second copy of it, and the copy is the one that falls behind. What these
functions decide is which rows the screen shows once it is open, which is a different question
with a different answer for the same person.

**Naming somebody's capabilities is a disclosure of the vocabulary, not of their grants.** The
People screen lists subjects and what each holds, and the second half of that is a list of
capability strings, which is a subset of everything that can be granted at all, which is the
Capabilities screen. The People screen may therefore not be a shortcut past the Capabilities
screen's grant: `may_name_capabilities` asks `brain.console.reads.permitted` about that
screen's own read rather than inventing a capability for this one. That is
`brain.console.workspace.basis_for`'s rule one surface over, and
`brain.console.reach_view.THE_GRANT_OVER_THE_VOCABULARY_IS_THE_DECISION_ALREADY_MADE` reached
it first about an agent's ceiling. A subject whose capabilities are withheld and a subject who
holds nothing produce an identical row.

**The catalogue is disclosed whole or not at all, and filtering it to the reader is the
attractive mistake.** Showing somebody the capabilities they themselves hold, under a heading
reading everything that can be granted, is their own entitlement wearing the vocabulary's
label: it discloses nothing, and it tells the reader the vocabulary is smaller than it is.
That is `reach_view.A_CEILING_FILTERED_TO_THE_READER_IS_THE_COLLAPSE_WEARING_A_CEILING_LABEL`
about a ceiling and it is the same mistake here.

**Access review widens by showing, which is not a failure anybody expects from a read.** A
recertification round puts a department admin in front of what their people hold. A round that
showed them a grant outside their scope has widened them without writing a grant: they now know
a capability exists, that it is held, and by whom. And an admin who could not have written a
grant must not be able to confirm one, because a confirmation is the grant made again by
somebody the decision was never theirs to make. Both are `_in_reach`, asked twice with two
different capabilities.

**Certifying your own grant is a self-grant with a review round attached.**
`brain.console.reads.is_self_grant` names the same failure on the ledger side and recognises it
from the entry rather than trusting a declaration; `Certification` refuses it in the
constructor, for the reason that module gives: the grant that must never be missed is the one
somebody made to themselves.

**Revoking a grant does not close a session, which is why the Sessions screen has a control.**
The leaf says so and it is true today. `brain.identity.packs.revoke_capability` removes rows
from a grant table and `brain.identity.sessions.SessionRegistry` is a different structure that
has not been told, so a person keeps working at their old reach until the session lapses on its
own, which is up to ten hours. `brain.identity.lifecycle.disable` is the one path that does
both and it is a leaver transition rather than something an administrator reaches from a
screen. The control is therefore `SessionRegistry.end_session`, called and not reimplemented,
and what is decided here is who may press it.

**Rejected: a capability of this module's own for ending a session.** `read:session` is the
only capability over that noun anywhere in this repository, and inventing a second one from a
console module puts a grant into the system from the rendering layer, where the administrator
who reviews grants would never meet it.
The authority to end a session is the authority to remove the grant the session outlived, which
is `approve:grant`, the capability the Access review screen already requires. `SESSION_CONTROL`
is written out and pinned against that screen by a test rather than derived from it, so
repointing either one fails.

**The control refuses identically whether the session is out of reach or not there.** A control
that raised for one and returned nothing for the other would answer "does this session id
exist" for anybody able to type one, which is
`brain.console.workspace.A_DEEP_LINK_THAT_REFUSES_DIFFERENTLY_IS_AN_ORACLE` with a button
instead of an address.

**Access friction is the sharpest of the eighteen, and the count leaks more than the name
would.** `brain.ops.denial_alerts` already refuses to name the capability or the object. What
it does carry is a `DenialAssessment`, which is two counts and a sentence quoting them, and
"forty denials across nine targets" on a screen is forty facts about things the reader cannot
see. So a row carries the shape and `ALERT_TEXT`'s sentence, there is nowhere on it for an
assessment, and repeated runs collapse to one row per subject and shape, because two identical
rows are the same count spelled with repetition.

**Rejected: rendering the friction screen by calling `digest`.** It is the same routing and it
would be one line. `digest` returns a log the caller stores, and writing a debounce row because
somebody opened a screen would suppress the alert that would otherwise have been raised: a read
would spend the alert budget. `friction` calls `reach` and reads `ALERT_TEXT`, which are the two
parts that decide, and writes nothing.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock; `now` is a
parameter, as in every sibling in this package. `apply_round` returns the grants that remain
and writes nothing either.

**No console screen exists behind any of the eighteen.** `brain.console.screens` says so about
its own registry, `role_surfaces` and `workspace` say it about theirs, and it is still true.
Twelve of the eighteen leaves are not claimed below. Every one of them is a listing over a
module named in `GOVERN_SURFACES`, the screen is the only thing missing, and claiming one here
would have the traceability sweep counting a page nobody can open.

Task ids: M27.3.1, M27.3.3, M27.3.4, M27.3.6, M27.3.8, M27.3.11
"""

from __future__ import annotations

import enum
import importlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final

from brain.console.reads import permitted
from brain.console.screens import SCREENS, Group, Screen, screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.identity.packs import SubjectGrant, revoke_capability
from brain.identity.roles import ROLE_SPECS, Role, RoleGrant, RoleSpec, role_capability_leaks
from brain.identity.sessions import Session, SessionRegistry
from brain.identity.teams import PrincipalSubject
from brain.ops.denial_alerts import ALERT_TEXT, DenialPattern, reach
from brain.ops.jobs import hidden_count_fields
from brain.ops.limits import DenialShape

# ------------------------------------------------------------------ written-down reasons
#: Why every surface names the module that already does the work.
A_GOVERNANCE_SCREEN_IS_A_VIEW_OF_A_MODULE_THAT_ALREADY_EXISTS: Final = (
    "Seventeen of the eighteen surfaces are a listing over machinery that was built and "
    "argued about somewhere else, and the one failure this group can produce cheaply is a "
    "second implementation of one of them: a grant reader that does not expire a grant, a "
    "denial listing that names what was denied, a retention view with its own horizons. "
    "Each copy reads as reasonable in the file it appears in and the damage is that they "
    "drift, with the permissive one winning. So the owner is a field, govern_gaps imports "
    "every one of them, and a surface whose owner does not exist is a build failure."
)

#: Why the row functions here do not ask again whether the screen may be opened.
THE_MENU_DECIDES_THE_SCREEN_AND_THIS_DECIDES_THE_ROWS: Final = (
    "brain.console.screens.navigation already answers whether this person may open this "
    "screen, by the tool's capability and the console plane together, and it is the only "
    "place that answers it. Repeating that check in every listing below would be a second "
    "copy of it, and a second copy of a permission check is a place for the two to disagree "
    "about the plane. What is decided here is which rows a screen shows once it is open, "
    "which is the same capability asked with the reader's scope against the row."
)

#: Why naming a person's capabilities needs the Capabilities screen's own grant.
A_LIST_OF_SOMEBODY_ELSES_CAPABILITIES_IS_A_LIST_OF_CAPABILITIES: Final = (
    "The second column of a people-and-grants screen is capability strings, and a capability "
    "string is a fact about what exists rather than about the person holding it: read:client."
    "contract_value discloses that contract values exist and that somebody reaches them. That "
    "is the disclosure the Capabilities screen governs, so the People screen may not be a "
    "shortcut past its grant. A reader without it sees the subjects and no capabilities, and "
    "a subject whose capabilities are withheld is indistinguishable from one holding none."
)

#: Why the catalogue is never narrowed to what the reader holds.
A_CATALOGUE_FILTERED_TO_THE_READER_IS_THEIR_OWN_ENTITLEMENT_RELABELLED: Final = (
    "Filtering the vocabulary to the capabilities a reader already holds is the option that "
    "discloses nothing and is the worst one available, because it puts their entitlement "
    "under a heading reading everything that can be granted at all and nothing on the screen "
    "says so. An administrator then writes a grant for a capability the screen told them did "
    "not exist. brain.console.reach_view makes the same argument about an agent's ceiling and "
    "reaches the same answer: the whole set, or a lock, and no third rendering."
)

#: Why a recertification round is narrowed before it is shown.
A_REVIEW_THAT_SHOWS_A_GRANT_OUTSIDE_A_SCOPE_WIDENS_BY_SHOWING: Final = (
    "A department admin put in front of a grant held in another department has been widened "
    "without a grant being written: they now know that capability exists, that it is held, "
    "and by whom, and none of the three was theirs to learn. The widening happens at the "
    "moment of rendering, which is why it survives a review of the grant tables, and it is "
    "the reason the round is filtered by the reader's own scope rather than presented whole "
    "with the out-of-scope rows greyed out."
)

#: Why an admin may not confirm a grant they could not have made.
AN_ADMIN_MAY_NOT_CERTIFY_WHAT_THEY_COULD_NOT_HAVE_GRANTED: Final = (
    "A recertification is the grant made again. Somebody who could not have written it in "
    "the first place confirming it a year later is the original decision laundered through a "
    "process, and the process is what everybody points at afterwards. The test is the one "
    "brain.console.role_surfaces applies to an approver, in that module's words: an approver "
    "may not wave through what they could not do themselves. Here it is the capability the "
    "grant carries, held by the certifier, in a scope that admits the row it is written over."
)

#: Why a certification of your own grant is refused in the constructor.
A_CERTIFICATION_OF_YOUR_OWN_GRANT_IS_A_SELF_GRANT_WITH_A_ROUND_ATTACHED: Final = (
    "brain.console.reads recognises a self-grant from the ledger entry rather than trusting "
    "somebody to declare one, because the grant that must never be missed is the one somebody "
    "made to themselves. A recertification round is the same act with a calendar in front of "
    "it: an admin who keeps their own grant every year has renewed it annually with nobody "
    "ever deciding. The refusal is in the constructor rather than in certify, so a hand-built "
    "Certification cannot go around it, which is the shape StewardNotice already uses."
)

#: Why the Sessions screen carries a control at all.
REVOKING_A_GRANT_DOES_NOT_CLOSE_A_SESSION: Final = (
    "brain.identity.packs.revoke_capability deletes rows from a grant table and returns the "
    "rows that remain. brain.identity.sessions.SessionRegistry is a separate structure and "
    "nothing in the revocation reaches it, so somebody whose grant was taken away keeps "
    "working at the reach the session was opened with, for up to the ten hours "
    "SESSION_ABSOLUTE_MAX allows. brain.identity.lifecycle.disable is the only path that does "
    "both and it is a leaver transition. So the screen needs a control, and the control is "
    "SessionRegistry.end_session rather than a second way of ending one."
)

#: Why every refusal of that control is the same refusal.
A_CONTROL_THAT_REFUSES_DIFFERENTLY_SAYS_THE_SESSION_IS_THERE: Final = (
    "Three things can be wrong when somebody presses end: the session is not one this reader "
    "may see, it is one they may see and not end, and there is no such session. Answering "
    "those differently turns the control into a way of asking which sessions exist, which is "
    "brain.console.workspace's argument about a deep link with a button instead of an "
    "address. end_one answers None to all three and there is no field on the answer a reason "
    "could be written into."
)

#: Why a role listing is not a statement about anybody's reach.
A_ROLE_LISTING_IS_NOT_A_REACH: Final = (
    "brain.identity.roles opens with the rule that no role implies a capability, including "
    "Super Admin, and role_capability_leaks refuses a module that maps one to the other. A "
    "screen headed Roles, listing six names and the people holding them, is the most natural "
    "place in the product for somebody to read the table as an answer to what those people "
    "can see. Nothing here can produce that answer: role_holders returns role grants and "
    "never an entitlement, role_catalogue takes no entitlement at all, and govern_gaps runs "
    "roles' own leak check over this module's namespace so a convenience mapping cannot "
    "arrive later under a friendlier name."
)

#: Why a friction row carries a shape and not the assessment behind it.
A_FRICTION_ROW_CARRIES_A_SHAPE_AND_NOT_THE_COUNT_THAT_PRODUCED_IT: Final = (
    "brain.ops.denial_alerts already refuses to name the capability or the object, and the "
    "thing left over is DenialAssessment: a count of denials, a count of distinct targets, "
    "and a note quoting both. Forty denials across nine targets on a screen is forty facts "
    "about things the reader may not see and nine about how many of them there are, which is "
    "the count rule broken by the field nobody thought of as a name. FrictionRow carries the "
    "subject, the shape and ALERT_TEXT's sentence, and has nowhere to put an assessment."
)

#: Why two identical friction rows are collapsed into one.
A_ROW_PER_RUN_IS_A_COUNT_OF_RUNS_WITH_THE_NUMBER_LEFT_OFF: Final = (
    "Three rows reading the same subject and the same shape publish the number three. It is "
    "the subtraction disclosure spelled with repetition rather than with a digit, and it "
    "survives every check that looks for a field holding a number. A_DIGEST_IS_LOSSLESS_"
    "BECAUSE_THERE_IS_NO_COUNT makes the same argument about collapsing several runs into one "
    "alert: there is no number to lose, because the row never carried one."
)

#: Why the friction screen is not rendered by calling the alert digest.
A_READ_OF_THE_FRICTION_SCREEN_MUST_NOT_SPEND_THE_ALERT_BUDGET: Final = (
    "digest routes exactly the same patterns to exactly the same recipients and rendering the "
    "screen through it would be one line. What comes back with the alerts is a log the caller "
    "stores, and a debounce row written because somebody opened a screen suppresses the alert "
    "that would otherwise have been raised for the next hour. A screen would then silence the "
    "notification, and the more often somebody watched, the less often they were told. So the "
    "two parts that decide are reused, reach and ALERT_TEXT, and nothing here writes a log."
)


class GovernError(Exception):
    """A governance surface was asked for something that would show the wrong person a row.

    Outside `brain.core.errors` for the reason `brain.console.workspace.WorkspaceError` gives
    about itself: those five outcomes describe an answer given to somebody asking a question,
    and this is a refusal to assemble an administrative surface. Nobody asking a question
    ever sees one.
    """


# --------------------------------------------------------------- the record and its place
#: The row a governance record carries when nothing says where its subject sits.
#:
#: Empty rather than absent, and it fails closed: `Clause.matches` refuses a field that is not
#: in the row, so a record with no place satisfies no scoped grant and reaches only a reader
#: whose grant is company-wide. `brain.ops.denial_alerts.DenialPattern.where` takes the same
#: default and records the same reasoning.
NOWHERE: Final[Mapping[str, str]] = MappingProxyType({})


@dataclass(frozen=True)
class Placed[T]:
    """One governance record, and the row that says where its subject sits.

    A scope is a predicate over rows and a governance record is not a row: `SubjectGrant`
    carries a capability and a scope, `RoleGrant` carries a role, `Session` carries a sign-in,
    and none of the three says which department the person is in. Pairing the record with the
    row is what lets one narrowing serve every surface here rather than each of them inventing
    a way to decide whether a record is in reach.

    Generic rather than three near-identical types, because three copies of two fields is
    three places for the second one to be forgotten, and forgetting it fails open: a listing
    that ignored `where` would show every row to whoever could open the screen.
    """

    record: T
    where: Mapping[str, str] = NOWHERE


def _in_reach(
    entitlement: EntitlementSet,
    capability: Capability,
    where: Mapping[str, str],
    now: datetime | None = None,
) -> bool:
    """Whether this reader holds `capability` in a scope that admits this row.

    `EntitlementSet.scope_for` followed by `Scope.matches`, which is the pair of public calls
    `brain.console.role_surfaces._may_approve` makes about an approver and
    `brain.ops.denial_alerts.reach` makes about an alert recipient. One narrowing, four
    surfaces, and no arithmetic of its own: `scope_for` decides what holding it means and
    refuses an expired principal, and `matches` decides whether the grant admits the place.
    """
    scope = entitlement.scope_for(capability, now)
    if scope is None:
        return False
    return scope.matches(dict(where))


# ------------------------------------------------------------------- the eighteen surfaces
@dataclass(frozen=True)
class GovernSurface:
    """One governance screen: which module already does the work, and what it may say.

    `owner` is a dotted module path rather than prose, because the claim "this is already
    built" is worth exactly as much as the last time somebody checked it, and `govern_gaps`
    imports it. `shows` and `never` are the two sentences a reviewer needs in front of them
    when the screen is finally written, and `never` is the one that gets left out of a ticket.
    """

    #: The `brain.console.screens` key. Checked against that registry rather than restated.
    key: str
    #: The module holding the machinery this surface reads.
    owner: str
    #: What the surface puts in front of a reader.
    shows: str
    #: What it must never put in front of one, however useful that would be.
    never: str

    def __post_init__(self) -> None:
        if not self.owner.strip():
            msg = f"{self.key} names no owner, so nothing says which module it reads"
            raise GovernError(msg)
        if not self.shows.strip() or not self.never.strip():
            msg = (
                f"{self.key} does not say both what it shows and what it must never show; "
                "the second sentence is the one a screen gets built without"
            )
            raise GovernError(msg)


#: Every govern screen, its owning module, and the two sentences about it.
#:
#: In the order `brain.console.screens.SCREENS` registers them, which is the order of the menu.
#: A tuple rather than a mapping for the reason that registry gives: the order is information.
GOVERN_SURFACES: Final[tuple[GovernSurface, ...]] = (
    GovernSurface(
        key="people",
        owner="brain.identity.packs",
        shows="every subject holding a grant, and what each one holds",
        never=(
            "a capability string to a reader who could not open the Capabilities screen, and "
            "no distinction between a subject whose grants are withheld and one holding none"
        ),
    ),
    GovernSurface(
        key="staff_sources",
        owner="brain.identity.staff_source",
        shows="where the staff list is linked from and what each source is trusted to assert",
        never=(
            "a source's credentials, and never a roster read as complete when the adapter "
            "could not say that it was; brain.identity.staff_adapters records the truncation"
        ),
    ),
    GovernSurface(
        key="roles",
        owner="brain.identity.roles",
        shows="the six roles, what each exists to do, and who currently holds each one",
        never=(
            "a capability beside a role, in any arrangement; no role implies a capability and "
            "a table that put the two side by side would be read as though one did"
        ),
    ),
    GovernSurface(
        key="capabilities",
        owner="brain.core.entitlement",
        shows="everything that can be granted at all, whole, to a reader granted that",
        never="the vocabulary narrowed to what the reader themselves holds",
    ),
    GovernSurface(
        key="scopes",
        owner="brain.core.department",
        shows="the row predicates a grant can carry and the departments they are written over",
        never=(
            "a department a reader's own scopes do not admit, because a listing of "
            "departments is a listing like any other and screens.offerable is what filters it"
        ),
    ),
    GovernSurface(
        key="access_review",
        owner="brain.identity.packs",
        shows="the grants this admin's own scope admits, for them to confirm or remove",
        never=(
            "a grant outside their scope, and no control to confirm one whose capability they "
            "do not themselves hold in a scope that admits the same row"
        ),
    ),
    GovernSurface(
        key="approvals",
        owner="brain.console.role_surfaces",
        shows="the suspended actions this approver could have performed themselves",
        never=(
            "a count of the ones they may not see, and nothing that has already lapsed; "
            "role_surfaces.pending_for and expiring_within are the two calls"
        ),
    ),
    GovernSurface(
        key="sessions",
        owner="brain.identity.sessions",
        shows="who is signed in within the reader's scope, and the control to end one",
        never=(
            "a different refusal for a session out of reach and a session that is not there, "
            "because the difference between the two answers which sessions exist"
        ),
    ),
    GovernSurface(
        key="agents",
        owner="brain.console.reach_view",
        shows="each agent's ceiling, its rung per operation, and every promotion and demotion",
        never=(
            "a cell filled in from its neighbour, because a matrix that inherits puts the "
            "per-agent default back at the rendering layer where it looks like the table working"
        ),
    ),
    GovernSurface(
        key="skills",
        owner="brain.tools.review",
        shows="what agents can be taught, with the queue of skills waiting for a reader",
        never=(
            "an unreviewed skill's body rendered as though it had been approved; "
            "tools.skills.is_executable is what decides and the queue only says it is waiting"
        ),
    ),
    GovernSurface(
        key="library",
        owner="brain.knowledge.visibility",
        shows="every knowledge item that exists, with the visibility scope on each",
        never=(
            "the content of an item, because this is the existence plane, and never a "
            "widening as a side effect of being looked at; promotion is proposed and approved"
        ),
    ),
    GovernSurface(
        key="learning",
        owner="brain.console.reach_view",
        shows="the three tiers separately, with the undo control on the automatic ones",
        never=(
            "tier three shown as active learning, because a gated change waits for a person; "
            "and no evidence row naming whose conversation produced a proposed rule"
        ),
    ),
    GovernSurface(
        key="memory",
        owner="brain.console.reach_view",
        shows="what is remembered about a person or a department, and every revision of it",
        never=(
            "a diff whose older side the reader was not separately admitted to, and no note "
            "saying a revision was withheld, because that note is the count with the digit off"
        ),
    ),
    GovernSurface(
        key="artifacts",
        owner="brain.audit.record",
        shows="what was produced, the publish entry it came from, and when it is deleted",
        never=(
            "the artefact's contents, which live in their own store under their own "
            "retention; the ledger proves a publish happened and names fields, never values"
        ),
    ),
    GovernSurface(
        key="exports",
        owner="brain.ops.export",
        shows="what left the building, who took it, and the reason they recorded",
        never=(
            "the exported content itself, and no count of the rows an export omitted; "
            "ops.export refuses a lock count travelling with a conversation for the same reason"
        ),
    ),
    GovernSurface(
        key="retention",
        owner="brain.ops.retention",
        shows="how long each class is kept, what is due, and the erasure queue behind it",
        never=(
            "what is in the rows it is about to delete; a retention report counts and never "
            "names, which is that module's own rule, and erasure certificates carry no copy"
        ),
    ),
    GovernSurface(
        key="access_friction",
        owner="brain.ops.denial_alerts",
        shows="which colleagues keep hitting a boundary, by the shape of the run",
        never=(
            "the capability, the object, the number of denials, the number of distinct "
            "targets, or one row per run, because repetition publishes the count as surely"
        ),
    ),
    GovernSurface(
        key="audit",
        owner="brain.audit.view",
        shows="every recorded act, filtered to the one reader, page by page",
        never=(
            "an entry whose subject kind no capability governs, and no total; audit.view "
            "pages by cursor rather than by offset so a page number cannot become a count"
        ),
    ),
)

#: How many governance surfaces there are, so a test can pin it and a person can quote it.
#:
#: Pinned rather than computed at the call site for the reason `screens.SCREEN_COUNT` is: the
#: interesting failure is a surface disappearing in a refactor, and `len(x) == len(x)` would
#: not notice. It is also the number of leaves under M27.3, which is what makes this a
#: statement about the work breakdown rather than about the menu: a nineteenth govern screen
#: is a leaf nobody wrote down, and an eighteenth surface with no screen is a claim about a
#: page that does not exist.
GOVERN_SURFACE_COUNT: Final = 18


def surface_for(key: str) -> GovernSurface:
    """One governance surface by its screen key, or a failure naming it."""
    for one in GOVERN_SURFACES:
        if one.key == key:
            return one
    msg = f"no governance surface named {key!r}"
    raise KeyError(msg)


def owners() -> tuple[str, ...]:
    """Every module the governance screens read, deduplicated, in registry order.

    Deduplicated because three surfaces read `brain.console.reach_view` and a reader asking
    what this group depends on wants the modules rather than the joins.
    """
    seen: dict[str, None] = {}
    for one in GOVERN_SURFACES:
        seen[one.owner] = None
    return tuple(seen)


# ------------------------------------------------------- the vocabulary (M27.3.4, M27.3.1)
#: The screen whose grant decides whether a capability may be named anywhere in this group.
#:
#: A screen key rather than a capability written out, so that no surface here can drift from
#: it: `may_name_capabilities` asks `permitted` about that screen's own read, which is the
#: tool's capability and the console plane together, exactly as opening the screen would be.
#: `brain.console.workspace.SPEND_OF_OTHERS_SCREEN` is the same construction for money.
VOCABULARY_SCREEN: Final = "capabilities"


def may_name_capabilities(entitlement: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether a capability string may be put in front of this reader at all (M27.3.1).

    Asked of the Capabilities screen's own read rather than of a capability invented for
    whichever surface is asking. See
    `A_LIST_OF_SOMEBODY_ELSES_CAPABILITIES_IS_A_LIST_OF_CAPABILITIES`: the People screen's
    second column is a subset of the vocabulary, so it is the vocabulary's grant that governs
    it, and a surface with its own would be a way of reading one screen's contents from
    another screen without the first screen's grant.
    """
    return permitted(screen(VOCABULARY_SCREEN).read, entitlement, now)


def catalogue(
    vocabulary: Iterable[Capability],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> tuple[str, ...]:
    """Everything that can be granted at all, or nothing at all (M27.3.4).

    **Whole or empty, and never narrowed to what the reader holds.** See
    `A_CATALOGUE_FILTERED_TO_THE_READER_IS_THEIR_OWN_ENTITLEMENT_RELABELLED`. A reader holding
    the grant gets every capability handed in, including the ones they hold none of, because
    that is what the screen is for; a reader without it gets an empty tuple and no lock, since
    `navigation` has already left the screen out of their menu and a lock rendered on a screen
    they cannot open would be a lock nobody sees.

    `vocabulary` is handed in rather than assembled here, on `screens.unregistered_tools`'
    argument about a registry: what can be granted on one install is what its tools and its
    packs require, and a module that worked it out would be a second answer to a question the
    tool registry already answers per install.

    Sorted, because the order of a vocabulary carries no information and two readings of an
    unchanged install should be the same list.
    """
    if not may_name_capabilities(entitlement, now):
        return ()
    return tuple(sorted(one.value for one in vocabulary))


@dataclass(frozen=True)
class PersonRow:
    """One grant subject and what they hold, as this reader may see it (M27.3.1).

    `subject` is `GrantSubject.key`, so `principal:u_1` and `team:web.design` are both rows.
    A team is a subject that holds grants, and attributing a team's grants to each member
    would need `brain.identity.packs.resolve_entitlement` to walk the memberships, which is
    that module's answer and would be a second expansion of what a grant reaches if it were
    written here.

    `capabilities` is empty both when the reader may not name them and when the subject holds
    none, and there is no third field saying which. See
    `A_LIST_OF_SOMEBODY_ELSES_CAPABILITIES_IS_A_LIST_OF_CAPABILITIES`: a flag reading
    "withheld" would say this subject holds something, which is the disclosure the withholding
    was for.
    """

    subject: str
    capabilities: tuple[str, ...] = ()


def people(
    holdings: Sequence[Placed[SubjectGrant]],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> tuple[PersonRow, ...]:
    """Who holds what, at this reader's reach (M27.3.1).

    Two decisions and they are separate. Whether a subject appears at all is the People
    screen's own capability against the row the grant sits in, which is `_in_reach`. Whether
    their capabilities are named is the Capabilities screen's grant, which is
    `may_name_capabilities`, and a reader can have the first without the second.

    An expired grant is not a holding. `scope_for` refuses an expired principal and
    `SubjectGrant.is_active` refuses a lapsed grant, and both are asked: the first is about the
    reader and the second about the row, and a listing that asked only the first would show a
    grant that confers nothing as though it did.

    Ordered by subject, then by capability, so two readings of an unchanged grant table are
    the same list. No count of the subjects left out, for the reason `navigation` returns one
    value, and a capability granted twice appears once: repeating it would say how many grants
    stand behind it, which is a count of rows the reader was never shown one at a time.
    """
    # A mapping used as an ordered set, as `owners` uses one, and deliberately not a set: a
    # set iterates in hash order, string hashing is seeded per process, and the same grant
    # table would then render two different rows on two servers reading it at once.
    held: dict[str, dict[str, None]] = {}
    for one in holdings:
        if not one.record.is_active(now):
            continue
        if not _in_reach(entitlement, screen("people").read.requires, one.where, now):
            continue
        held.setdefault(one.record.subject.key, {})[one.record.capability.value] = None
    named = may_name_capabilities(entitlement, now)
    return tuple(
        PersonRow(subject=subject, capabilities=tuple(sorted(values)) if named else ())
        for subject, values in sorted(held.items())
    )


# ------------------------------------------------------------------------ roles (M27.3.3)
def role_catalogue() -> tuple[RoleSpec, ...]:
    """The six roles and what each one exists to do (M27.3.3).

    Takes no entitlement, and that absence is the statement rather than an oversight: what a
    role is for is product documentation, the same thing `brain.console.role_surfaces.
    designed_for` returns about a screen, and a function that cannot see a reader cannot make
    a decision about one. `ROLE_SPECS` is the constant the validator reads, so the screen and
    the rule cannot disagree about what a role requires.

    In `Role`'s own declaration order rather than sorted, because that order is the order the
    architecture introduces them in and a reader meets Super Admin before Approver.
    """
    return tuple(ROLE_SPECS[one] for one in Role)


def role_holders(
    grants: Sequence[Placed[RoleGrant]],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> tuple[Placed[RoleGrant], ...]:
    """Who holds a role, at this reader's reach (M27.3.3).

    **Returns role grants and never an entitlement.** See `A_ROLE_LISTING_IS_NOT_A_REACH`.
    Somebody reading this screen learns who was appointed to what, which is a fact about the
    platform's governance; what they may see is decided by their own grant of the Roles
    screen's capability against the row each holder sits in.

    A lapsed grant is absent rather than shown as lapsed. `RoleGrant.is_active` is the single
    statement of whether a grant still confers the role, and a deputy whose thirty days ran out
    holds nothing; listing them greyed out is the shape `role_surfaces` rejected for expired
    suspensions, and for the same reason, that it invites an act that will be refused.

    Order follows `grants`, for the reason `screens.offerable` gives: the caller's order is
    usually meaningful and re-sorting discards it.
    """
    return tuple(
        one
        for one in grants
        if one.record.is_active(now)
        and _in_reach(entitlement, screen("roles").read.requires, one.where, now)
    )


# --------------------------------------------------------------- access review (M27.3.6)
class Decision(enum.StrEnum):
    """What a recertification round can conclude about one grant. Two, and no third.

    There is deliberately no `DEFER` and no `ESCALATE`. A round exists to end, and a member
    meaning "not now" is the one every row acquires in the last week of it: the grant stays,
    nobody decided, and the register shows the round as complete. Removing a grant somebody
    could not decide about is the safe direction and keeping it is a decision, so both
    available answers are answers.
    """

    #: The grant stands, decided by a person who could have written it.
    KEEP = "keep"
    #: The grant goes. `apply_round` deletes the row; there is no deny row anywhere.
    REMOVE = "remove"


def may_certify(
    holding: Placed[SubjectGrant],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> bool:
    """Whether this admin may decide this grant, on both counts (M27.3.6).

    Both, and they are different questions asked with different capabilities. The Access
    review screen's own capability decides whether the round is theirs at all, in a scope that
    admits the row; the grant's own capability decides whether they could have written it.
    See `A_REVIEW_THAT_SHOWS_A_GRANT_OUTSIDE_A_SCOPE_WIDENS_BY_SHOWING` and
    `AN_ADMIN_MAY_NOT_CERTIFY_WHAT_THEY_COULD_NOT_HAVE_GRANTED`.

    The second check is against the grant's capability rather than against a wildcard covering
    it, because `EntitlementSet.scope_for` already expands a trailing `.*` through
    `Capability.covers`: an admin holding `read:client.*` may certify a grant of
    `read:client.name`, and one holding only the narrow capability may not certify the wide one.
    """
    if not _in_reach(entitlement, screen("access_review").read.requires, holding.where, now):
        return False
    return _in_reach(entitlement, holding.record.capability, holding.where, now)


def recertifiable(
    holdings: Sequence[Placed[SubjectGrant]],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> tuple[Placed[SubjectGrant], ...]:
    """The round this admin is shown: what they may decide, and no count of the rest (M27.3.6).

    Filtered before it is rendered rather than rendered whole with the out-of-scope rows
    disabled, which is the version that gets built because it looks more informative. A
    disabled row is the grant disclosed with a reason attached.

    Order follows `holdings`. One value comes back and there is no second one carrying what
    was dropped, which is `navigation`'s rule and `pending_for`'s.
    """
    return tuple(one for one in holdings if may_certify(one, entitlement, now))


@dataclass(frozen=True)
class Certification:
    """One decision about one grant, by somebody who is not its subject (M27.3.6).

    **The self-certification refusal is here rather than in `certify`.** A rule enforced only
    by the function that usually builds the object is a rule a hand-built object goes around,
    and `brain.console.reads.StewardNotice` puts its equivalent refusal in the same place for
    the same reason. See
    `A_CERTIFICATION_OF_YOUR_OWN_GRANT_IS_A_SELF_GRANT_WITH_A_ROUND_ATTACHED`.

    Carries no reason field. A reason on a KEEP is the sentence everybody writes "still
    needed" in, and its presence would make the round look reviewed; what makes a round worth
    anything is that the person deciding could have written the grant, which is checked rather
    than described.
    """

    holding: Placed[SubjectGrant]
    decision: Decision
    #: The principal who decided. Never the grant's own subject.
    by: str
    at: datetime

    def __post_init__(self) -> None:
        if not self.by.strip():
            msg = "a certification by nobody leaves no one accountable for the grant standing"
            raise GovernError(msg)
        if self.at.tzinfo is None:
            msg = "a naive certification time compares wrongly against an aware round boundary"
            raise GovernError(msg)
        subject = self.holding.record.subject
        if isinstance(subject, PrincipalSubject) and subject.principal_id == self.by:
            msg = (
                f"{self.by!r} is certifying their own grant of "
                f"{self.holding.record.capability.value}. "
                f"{A_CERTIFICATION_OF_YOUR_OWN_GRANT_IS_A_SELF_GRANT_WITH_A_ROUND_ATTACHED}"
            )
            raise GovernError(msg)


def certify(
    holding: Placed[SubjectGrant],
    entitlement: EntitlementSet,
    decision: Decision,
    *,
    by: str,
    at: datetime,
    now: datetime | None = None,
) -> Certification:
    """Record one decision, refusing one this admin could not have made (M27.3.6).

    `may_certify` is asked here as well as by `recertifiable`, and that is not belt and
    braces: the listing decides what a screen offers and this decides what a submitted form
    may do, and a form is submitted by whatever was posted rather than by what was offered.
    """
    if not may_certify(holding, entitlement, now):
        msg = (
            f"{by!r} may not certify a grant of {holding.record.capability.value} over "
            f"{dict(holding.where)!r}. "
            f"{AN_ADMIN_MAY_NOT_CERTIFY_WHAT_THEY_COULD_NOT_HAVE_GRANTED}"
        )
        raise GovernError(msg)
    return Certification(holding=holding, decision=decision, by=by, at=at)


def apply_round(
    certifications: Sequence[Certification],
    grants: Sequence[SubjectGrant],
) -> tuple[SubjectGrant, ...]:
    """The grants that remain after a round (M27.3.6). Deletion, never a negative row.

    `brain.identity.packs.revoke_capability` does the removing, once per REMOVE, and it
    matches the capability exactly rather than by `covers`: revoking `read:client.name` must
    not delete a `read:client.*` grant that happens to imply it, which is that module's rule
    and would be a different decision made by a different person.

    Returns the remaining rows rather than writing anything, on the split
    `brain.ops.limits` keeps from `brain.ops.limit_store`: the policy has no connection, so
    the case that is always wrong stays testable.
    """
    remaining = tuple(grants)
    for one in certifications:
        if one.decision is Decision.REMOVE:
            remaining = revoke_capability(
                remaining,
                one.holding.record.subject,
                one.holding.record.capability,
            )
    return remaining


# -------------------------------------------------------------------- sessions (M27.3.8)
#: The capability that offers the control to end somebody else's session.
#:
#: The Access review screen's own requirement, written out here rather than derived from the
#: registry so that a test can compare the two: derived, the comparison would be a constant
#: against itself and repointing either would move both. `brain.console.reach_view.
#: CEILING_DISCLOSURE` is pinned the same way and records the same argument.
#:
#: See `REVOKING_A_GRANT_DOES_NOT_CLOSE_A_SESSION` for why this is the right capability and
#: not one of this module's own.
SESSION_CONTROL: Final = Capability(value="approve:grant")


def open_sessions(
    sessions: Sequence[Placed[Session]],
    entitlement: EntitlementSet,
    now: datetime,
) -> tuple[Placed[Session], ...]:
    """The sign-ins this reader may see, at this instant (M27.3.8).

    Live and in reach, and both are needed. `Session.is_live` is the single statement of
    whether a sign-in still stands, asked rather than compared against `expires_at` a second
    time here, and a session that has lapsed is absent rather than listed as expired: it
    admits nothing, so a control beside it would be a control over nothing.

    Order follows `sessions`, which is usually most recent first and is information.
    """
    return tuple(
        one
        for one in sessions
        if one.record.is_live(now)
        and _in_reach(entitlement, screen("sessions").read.requires, one.where, now)
    )


def may_end(
    one: Placed[Session],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> bool:
    """Whether this reader may end this session (M27.3.8).

    A different capability from the one that lists it. Reading who is signed in is the
    Sessions screen's own grant; ending a sign-in is taking away what the sign-in is still
    conferring, which is the grant decision, which is `SESSION_CONTROL`. A reader can see the
    row and not have the control, and that is the ordinary case rather than an edge.
    """
    return _in_reach(entitlement, SESSION_CONTROL, one.where, now)


def end_one(
    registry: SessionRegistry,
    session_id: str,
    *,
    sessions: Sequence[Placed[Session]],
    entitlement: EntitlementSet,
    now: datetime,
) -> Session | None:
    """End one session from the Sessions screen, or `None` (M27.3.8).

    `None` for all three failures and the sameness is the point rather than a convenience: a
    session outside this reader's reach, one they may see and not end, and one that is not
    there are one answer. See `A_CONTROL_THAT_REFUSES_DIFFERENTLY_SAYS_THE_SESSION_IS_THERE`.

    The ending itself is `SessionRegistry.end_session`, which deletes the session and raises
    the principal's logout floor in one call. Reimplementing it here would end the session and
    not the floor, and the floor is the only thing that refuses the token already minted, so
    the second implementation would look like it worked in every test that held the registry.
    """
    for one in open_sessions(sessions, entitlement, now):
        if one.record.session_id == session_id and may_end(one, entitlement, now):
            return registry.end_session(session_id, now)
    return None


# ------------------------------------------------------------- access friction (M27.3.11)
#: Field names that would put the thing back on a friction row.
#:
#: Restated here rather than imported from `brain.ops.jobs`, whose list is about counts a
#: reader was not shown: the words somebody reaches for differ by surface, and the field that
#: breaks this one is called `assessment` or `note` rather than `hidden`. Both lists are
#: checked, because the two failures are different.
NAMES_THAT_WOULD_NAME_THE_THING: Final[frozenset[str]] = frozenset(
    {
        "assessment",
        "capability",
        "denials",
        "distinct_targets",
        "note",
        "object_id",
        "target",
        "targets",
        "where",
    }
)


@dataclass(frozen=True)
class FrictionRow:
    """One colleague, one shape of boundary, and the sentence for it (M27.3.11).

    Three fields and no fourth. There is no capability, no object, no denial count, no target
    count and no assessment, which is
    `A_FRICTION_ROW_CARRIES_A_SHAPE_AND_NOT_THE_COUNT_THAT_PRODUCED_IT` expressed as a shape
    rather than as a rule somebody remembers, and `govern_gaps` reports one if a later edit
    adds it.

    `text` is `brain.ops.denial_alerts.ALERT_TEXT`'s sentence and never
    `DenialAssessment.note`, which quotes both counts. The two read almost identically at a
    glance, which is exactly why the row is built from the first.
    """

    subject_id: str
    shape: DenialShape
    text: str


def friction(
    patterns: Sequence[DenialPattern],
    reader: EntitlementSet,
    now: datetime,
) -> tuple[FrictionRow, ...]:
    """Where people are repeatedly hitting a boundary, by shape and never by name (M27.3.11).

    Three filters and each is a disclosure decision somebody could remove without a screen
    looking wrong.

    A shape with no sentence produces no row, and that one check is the threshold decision as
    well: `ALERT_TEXT` has no entry for `DenialShape.ORDINARY` and its own docstring says why,
    which is that a run below the noticing threshold has nothing to say. The reader is never
    shown their own denials, because somebody who can watch whether they appear can measure
    the boundary of what exists by walking it. And `reach` decides whether they may be told at
    all, which is the entitlement model rather than a rule of this module's: it narrows the
    requirement by the recipient rather than the other way about, so a wildcard grant is not
    dropped.

    **Rejected: asking `DenialAssessment.is_worth_alerting` as well.** `digest` asks both and
    it reads like defence in depth, and it is not: `is_worth_alerting` is `shape is not
    ORDINARY` and `ALERT_TEXT` holds exactly the shapes that are not ORDINARY, which
    `tests/unit/test_govern.py` pins, so no input can separate the two and neither of them can
    fail on its own. Two checks nothing can tell apart are one check written twice, and a
    mutation showed that: breaking either alone changed no behaviour any test could observe,
    which means a reader cannot tell which one is holding. The threshold belongs to
    `brain.ops.limits` and the sentence table belongs to `brain.ops.denial_alerts`; this asks
    the table, once.

    **One row per subject and shape.** See
    `A_ROW_PER_RUN_IS_A_COUNT_OF_RUNS_WITH_THE_NUMBER_LEFT_OFF`. The first run of a shape is
    kept and later ones collapse into it, which loses nothing because the row never carried a
    number.

    See `A_READ_OF_THE_FRICTION_SCREEN_MUST_NOT_SPEND_THE_ALERT_BUDGET` for why this is not
    `digest` with a zero window.

    Ordered by subject and then by shape rather than following the patterns, which is the
    opposite choice from every other listing here and rests on the same reason: those keep an
    order the caller meant something by, and these rows have already been collapsed, so the
    order they arrived in means nothing and two readings of one log would differ by it.
    """
    seen: dict[tuple[str, DenialShape], FrictionRow] = {}
    for pattern in patterns:
        text = ALERT_TEXT.get(pattern.shape)
        if text is None:
            continue
        if reader.principal_id == pattern.subject_id:
            continue
        if reach(pattern, reader, now=now) is None:
            continue
        seen.setdefault(
            (pattern.subject_id, pattern.shape),
            FrictionRow(subject_id=pattern.subject_id, shape=pattern.shape, text=text),
        )
    return tuple(sorted(seen.values(), key=lambda one: (one.subject_id, one.shape)))


# ------------------------------------------------------------------------- the diagnostic
#: The types a reader of these surfaces is handed. Listed rather than discovered, following
#: `brain.console.workspace.WORKSPACE_SURFACE`: a type added here and not to this tuple is a
#: type the checks below never see.
GOVERN_ROWS: Final[tuple[type, ...]] = (PersonRow, FrictionRow, Certification, Placed)


def govern_gaps(
    *,
    surfaces: Sequence[GovernSurface] = GOVERN_SURFACES,
    registry: Sequence[Screen] = SCREENS,
    rows: Sequence[type] = GOVERN_ROWS,
    friction_row: type = FrictionRow,
    namespace: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """Everything about this group that would show somebody more than they hold.

    Takes its inputs rather than reading the module's own constants, and a mutation is the
    reason: a diagnostic that can only run against the healthy tree has nothing to report on
    today's data, so switching off any of its refusals changes nothing observable and every
    one of them survives. Calling it with no arguments is the deployment check and calling it
    with a constructed set is the test. `brain.console.workspace.workspace_gaps` and
    `brain.ops.starter.starter_gaps` make the same argument about their own parameters.

    Five checks. The first two are about the register agreeing with the screen registry and
    with the modules it claims; the last three hold the row types to their own shape.
    """
    gaps: list[str] = []

    wanted = [one.key for one in registry if one.group is Group.GOVERN]
    claimed: dict[str, int] = {}
    for one in surfaces:
        claimed[one.key] = claimed.get(one.key, 0) + 1
    for key, count in claimed.items():
        if count > 1:
            gaps.append(
                f"{key} is registered as a governance surface {count} times, so which module "
                "a reader is told owns it depends on which entry was read first"
            )
        if key not in wanted:
            gaps.append(
                f"{key} is registered as a governance surface and is not a govern screen, so "
                "the two lists have come apart and one of them is describing nothing"
            )
    for key in wanted:
        if key not in claimed:
            gaps.append(
                f"the {key} screen has no governance surface, so nothing says which module it "
                "reads and the next person to need one writes a second implementation"
            )

    for one in surfaces:
        try:
            importlib.import_module(one.owner)
        except ImportError:
            gaps.append(
                f"{one.key} names {one.owner}, which does not import, so the claim that this "
                f"surface is already built is not a claim anybody checked. "
                f"{A_GOVERNANCE_SCREEN_IS_A_VIEW_OF_A_MODULE_THAT_ALREADY_EXISTS}"
            )

    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(rows)
    )
    gaps.extend(
        f"{friction_row.__name__}.{name} puts the thing back on a friction row. "
        f"{A_FRICTION_ROW_CARRIES_A_SHAPE_AND_NOT_THE_COUNT_THAT_PRODUCED_IT}"
        for name in getattr(friction_row, "__dataclass_fields__", {})
        if name in NAMES_THAT_WOULD_NAME_THE_THING
    )

    # Reused rather than reimplemented, exactly as `role_surfaces.surface_gaps` reuses
    # `assert_no_role_in_resolution`. This module is not in the identity package, so the
    # invariant suite's sweep over that package does not reach it, and a roles surface is
    # precisely where a convenience mapping from a role to a capability would be written.
    gaps.extend(role_capability_leaks(globals() if namespace is None else namespace))

    return tuple(gaps)
