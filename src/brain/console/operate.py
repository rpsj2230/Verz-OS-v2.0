"""The twelve screens that say what is happening and what it cost, and one rule joining them.

The rule is **honest counting**, and it is the whole of the landing screen. A front page
reading "1,284 documents" to somebody who may open forty of them has published the size of
what they cannot see, in a figure nobody reviews because it is not a row. That is the
DENIED-and-ABSENT rule of `CLAUDE.md` arriving as a headline, and it is the likeliest single
way this console leaks: every screen below carries a figure, so the rule is the spine of the
group rather than one screen's problem.

**A front-page figure may not be a shortcut past a screen's grant.**
`brain.console.workspace.Basis` is the existing answer and there is not a second one here.
`brain.console.agent_output.basis_over` is that rule with the screen as a parameter, and
`tile` calls it, so a reader sees everybody's figure exactly when they could open the screen
that shows them and count the rows there. `brain.console.agent_automations.schedule_basis`
already asks it of the queue screen; a test pins the two together rather than trusting that
they agree.

**A figure with no narrower version is withheld and never narrowed.** Runs, questions and
spend belong to somebody, so a reader without the screen's grant is honestly shown their own.
The corpus, the connector list and the halts belong to nobody, and "your share of the
documents" is not a smaller true figure, it is a different and meaningless one. `Attribution`
is the two cases and `tile` returns `None` for the second, which is `brain.console.workspace.
projection` returning `None` on the narrower basis for the same reason: withheld beats
narrowed when narrowing would produce a confident number that is wrong.

**Which case a screen is in is checked against the row rather than declared.** A per-person
figure is counted over rows carrying `principal_id`, which is what this system calls the
person a thing is attributed to: `JobRecord`, `Actual` and `Turn` all have one. Authorship is
not attribution, so `KnowledgeItem.owner_id` does not make the corpus per-person. `Panel.row`
names the type and `operate_gaps` imports it and compares, so the register cannot claim an
attribution the row cannot support. Mutating one entry of the register fails a test that never
reads the register.

**No figure is ever handed in.** `tile` takes rows and counts what is left after filtering,
so there is no point inside it at which a total exists to be returned by accident. That is
`brain.ops.jobs.dead_letter_summary`'s construction and `operate_gaps` refuses a parameter a
precomputed figure could arrive through.

**Two figures for one screen is a subtraction.** A landing screen showing a reader their own
runs beside everybody's runs hands them the difference, which is a count of other people's
work. `overview` refuses a second tile for one screen rather than rendering both.

What each screen adds beyond that:

**Live runs.** `brain.ops.jobs` decides who may see a dead letter and nothing decided who may
watch a running job. `may_watch` is that, built the same way, and `RunRow` carries no
arguments: `Job.args` holds identifiers of records, so a row showing them names records the
reader may hold nothing over, on a screen whose whole content is supposed to be the question
rather than the answer.

**Connector health.** `brain.connectors.federation.NAMING_A_SOURCE_IS_A_DISCLOSURE` is already
the rule, and this is it applied to a list rather than to a sentence. The connectors a reader
may be shown are the ones `brain.console.screens.offerable` admits, so a source that is down
and a source that was never installed produce the same absence.

**Knowledge coverage.** The sharpest of the twelve, because coverage is a count per area and
an area is a department. `brain.knowledge.search.reach_for` returns `None` for a caller with
no read of the plane at all, and `None` is nothing rather than everything; the areas offered
are the ones that reach admits; and a row's figure is over the items `Reach.admits` passes.
`brain.knowledge.quality.A_COUNT_OF_WHAT_WAS_SHOWN_IS_NOT_A_COUNT_OF_WHAT_WAS_HIDDEN` is the
constraint and there is no field on a coverage row for a corpus total.

**Incidents.** `brain.ops.wiring.Component` carries no dependency edge, so "what it blocks"
cannot be read off a graph that does not exist. What can be read is what a source declares:
a degraded connector blocks the tools on its own manifest. Naming those tools names capability
surface, so the blocked list is filtered to the connectors the reader already reaches, and an
incident on a source out of reach is absent rather than redacted.

**The stop button.** A halt scoped to everything is shown to everybody it stops, whatever
their scope, and that is not an exception to the rule. `brain.ops.halt.
A_HALT_DISCLOSES_NOTHING_ABOUT_WHAT_ANYBODY_MAY_SEE` says a halt is neither DENIED nor ABSENT,
and hiding a global halt leaves a reader in front of a screen saying nothing is stopped while
nothing runs. Narrower halts name a department, an agent, a connector or a person, and those
are filtered.

**Questions and gaps.** `brain.gate.abstain.AbstentionReason` has five members and exactly one
of them is a fact about the company rather than about a person: `NOTHING_CONNECTED`, whose own
comment says it is identical for everybody. The other four are outcomes of a reach or a
model's judgement, and `NOTHING_RETRIEVED` deliberately covers the case where a record existed
and was withheld. Counting those on a screen publishes refusals as gaps, so `gaps` counts the
connected reason alone and `GAP_REASONS` is the whole of it.

**Budgets.** `brain.ops.spend.Refusal` carries two fields and no figure on purpose, and the
console's job here is not to add one back. `ceiling_effect` renders the ladder and the refusal
sentence and has nowhere to put an amount.

**Quality.** `brain.ops.canaries.CanaryFinding.subject` is a field name, so a findings list is
a listing of the schema. `A_FINDING_REPEATS_THE_LEAK_IF_IT_CARRIES_THE_VALUE` refuses the
value; this refuses the name to a reader who could not have been told the field exists.

Rejected: a reporting query of this group's own. That is
`brain.console.reads.A_REPORT_QUERY_IS_A_SECOND_DATA_PATH_WITH_NO_REDACTOR` and it is the
thing a screen showing twelve figures at once is most tempted by. Every function here is
handed rows somebody else fetched.

Rejected: generalising `brain.console.workspace.basis_for` in place, for the reason
`agent_output` gives about a file two other agents are editing tonight.

Rejected: a tile for the landing screen itself. Its only possible figure is how many of the
other eleven it could show, which is the count of what it hid; `Panel` refuses the landing key
in its constructor rather than leaving that to a reviewer.

**Nothing here computes a reach.** `brain.console.reads.audience` and
`brain.console.workspace_capabilities.run_reach` are the console's two routes into
`EntitlementSet.intersect`, and `brain.console.workspace.intersections_in` is run over this
module's own source by its tests, so the absence is checked rather than intended.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock; `now` is a
parameter, as in every sibling in this package.

**No console screen exists behind any of the twelve**, exactly as `brain.console.screens` and
`brain.console.govern` say of their own registers. Two leaves are declined and neither id is
repeated below. Usage and tokens by person, department, model and agent is declined because
`brain.ops.spend.Actual` carries a cost and no tokens, `brain.ops.telemetry` carries tokens and
no department, and nothing joins them, so a tokens-by-department column has no source and would
be a figure that looks measured; `usage_gaps` reports it. The model matrix is declined because
what is missing there is a renderer rather than a decision, and `MATRIX_SURFACES` says which
module holds each half.

Task ids: M27.2.1, M27.2.2, M27.2.4, M27.2.5, M27.2.6, M27.2.7, M27.2.8
Task ids: M27.4.1, M27.4.3, M27.4.4
"""

from __future__ import annotations

import enum
import importlib
import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final

from brain.chat.turns import Turn, TurnKind
from brain.connectors.contract import ConnectorHealth
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.registry import RegisteredConnector
from brain.console.agent_output import basis_over
from brain.console.screens import SCREENS, Group, Screen, offerable, screen
from brain.console.workspace import Basis
from brain.core.entitlement import EntitlementSet
from brain.core.scope import Scope
from brain.gate.abstain import Abstention, AbstentionReason
from brain.gate.provenance import DEFAULT_HORIZON, Freshness, StalenessHorizon, assess_freshness
from brain.knowledge.item import KnowledgeItem
from brain.knowledge.search import Reach, reach_for
from brain.ops.budgets import Allowance, BudgetLevel, BudgetRow
from brain.ops.canaries import CanaryFinding
from brain.ops.halt import Halt, HaltScope, HaltState
from brain.ops.jobs import JobRecord, JobState, hidden_count_fields
from brain.ops.spend import LADDER, Refusal, Rung

# ----------------------------------------------------------------- written-down reasons
#: Why the landing screen's figures follow the screens they came from.
A_FRONT_PAGE_FIGURE_IS_A_SHORTCUT_PAST_THE_SCREEN_IT_CAME_FROM: Final = (
    "A landing screen reading 1,284 documents to somebody who may open forty of them has "
    "published the size of what they cannot see, and it has done it in a figure nobody "
    "reviews because it is not a row. So a figure is shown at everybody's scale exactly "
    "when the reader could open the screen behind it and count the rows there, which is "
    "brain.console.workspace.Basis asked with the screen as a parameter. No capability is "
    "invented for a front page: a new one is a second answer to a question the screen "
    "registry already answers, and the administrator reviewing one would never see the other."
)

#: Why some figures are withheld rather than narrowed.
A_FIGURE_WITH_NO_NARROWER_VERSION_IS_WITHHELD_AND_NEVER_NARROWED: Final = (
    "Runs, questions and spend belong to somebody, so a reader without the screen's grant "
    "can honestly be shown their own. The corpus, the connector list and the halts belong "
    "to nobody. Your share of the documents is not a smaller true figure, it is a different "
    "and meaningless one, and it would be read as the corpus. Withheld beats narrowed "
    "wherever narrowing produces a confident number that is wrong, which is why "
    "brain.console.workspace.projection returns None on the narrower basis rather than "
    "projecting one person's afternoon against a ceiling everybody shares."
)

#: Why a per-person figure is recognised from the row rather than declared by the register.
ATTRIBUTION_IS_A_FACT_ABOUT_THE_ROW_AND_NOT_A_LABEL_ON_THE_SCREEN: Final = (
    "principal_id is what this system calls the person a thing is attributed to: an "
    "entitlement set has one, a job record has one, an accounting row has one and a turn "
    "has one. Authorship is not attribution, so a knowledge item's owner_id does not make "
    "the corpus somebody's. A register that declared the attribution by hand would be a "
    "label a later edit could set to per-person on a screen whose rows carry nobody, and "
    "the figure would then narrow to zero for every reader and look like an empty system."
)

#: Why no function here takes a figure it did not compute.
A_TOTAL_THAT_ARRIVES_AS_AN_ARGUMENT_WAS_COUNTED_SOMEWHERE_ELSE: Final = (
    "Filtering happens first and the arithmetic happens on what is left, so there is no "
    "point inside these functions at which a count of everything exists to be returned by "
    "accident. A parameter carrying a precomputed total defeats that in one line at a call "
    "site nobody reviews, because the call site looks like it is passing data. There is no "
    "such parameter and the diagnostic reads the signature rather than trusting this."
)

#: Why one screen may lend the landing page only one figure.
A_SECOND_FIGURE_FOR_ONE_SCREEN_IS_A_SUBTRACTION: Final = (
    "A landing screen showing a reader their own runs beside everybody's runs has handed "
    "them the difference, which is a count of other people's work arrived at without "
    "anybody publishing it. Two tiles for one screen is that shape whatever the labels say, "
    "so the assembly refuses the pair rather than rendering both and hoping."
)

#: Why nobody may watch a job that is not theirs without a grant.
A_RUNNING_JOB_NAMES_THE_PERSON_IT_IS_RUNNING_FOR: Final = (
    "A live runs screen is a list of what colleagues are asking for, minute by minute. "
    "brain.ops.jobs.may_see already decides this for a dead letter, two ways in and no "
    "third: it is your own work, or a grant covers it in a scope that matches the row. "
    "This is the same decision about a job that has not failed yet, and a second rule for "
    "it would be a second place for who may read what to be wrong."
)

#: Why a run row carries no arguments.
AN_ARGUMENT_IS_A_REFERENCE_TO_A_RECORD_THE_READER_MAY_HOLD_NOTHING_OVER: Final = (
    "brain.ops.queue.Job.args holds identifiers rather than content, deliberately, and that "
    "is exactly what makes them unsafe on a screen: an identifier names a record, and a row "
    "reading task=export_invoice client=447 tells the reader that client 447 exists and is "
    "being worked on. The screen's own purpose says configuration and not content, the "
    "question and not the answer, and an argument is halfway to the answer."
)

#: Why a connector list is filtered the way a dropdown is.
NAMING_A_SOURCE_IS_A_DISCLOSURE_ON_A_LIST_TOO: Final = (
    "brain.connectors.federation says naming a source is a disclosure and passes a "
    "disclosable set into every sentence that might name one. A health table is that "
    "sentence thirty times over, and it is the shape where nobody thinks to pass the set. "
    "The connectors a reader may be shown are the ones screens.offerable admits, so a "
    "source that is down and a source that was never installed produce the same absence."
)

#: Why an area with nothing visible is still a row and an area out of reach is not.
AN_AREA_OUT_OF_REACH_IS_ABSENT_AND_AN_EMPTY_AREA_IS_A_GAP: Final = (
    "Coverage is a count per area and an area is a department, so the list of areas is a "
    "listing of the org chart and is filtered to the reach like any other. Inside that "
    "reach, zero is the honest answer and is the point of the screen: an area the reader "
    "may see and which holds nothing they may see is a gap, and gaps are the roadmap. What "
    "must never appear beside it is the number that was there instead, which is why a "
    "coverage row has no field for a corpus total."
)

#: Why a knowledge reader holding no grant is shown nothing rather than everything.
NO_READ_OF_THE_PLANE_IS_NOTHING_AND_NEVER_EVERYTHING: Final = (
    "brain.knowledge.search.reach_for returns None for a caller who holds no read of the "
    "knowledge plane, and None is not the unrestricted reach: that module has no "
    "constructor meaning everything, precisely so a missing grant cannot compile to a "
    "query with no WHERE clause. A coverage screen is where that would be undone, because "
    "an empty reach reads like a caller who simply has no departments yet."
)

#: Why a degradation's blast radius is filtered rather than listed whole.
WHAT_AN_INCIDENT_BLOCKS_IS_NAMED_IN_CAPABILITIES_SOMEBODY_MAY_NOT_HOLD: Final = (
    "brain.ops.wiring.Component carries no dependency edge, so what a degradation blocks "
    "cannot be read off a graph. What can be read is what the source itself declares, and "
    "a connector's manifest declares its tools. Listing those tools tells the reader which "
    "operations exist against a source they may hold nothing over, so an incident on a "
    "connector outside the reader's reach is absent rather than shown with the detail "
    "removed, and a redacted row would announce it just as well."
)

#: Why a halt on everything reaches every reader.
A_GLOBAL_HALT_IS_SHOWN_TO_EVERYBODY_IT_STOPS: Final = (
    "brain.ops.halt.A_HALT_DISCLOSES_NOTHING_ABOUT_WHAT_ANYBODY_MAY_SEE says a halt is "
    "neither denied nor absent: it says the system is paused, which reveals nothing about "
    "what this person could otherwise have read. Filtering a halt on everything out of "
    "somebody's stop screen leaves them reading that nothing is stopped while nothing runs, "
    "and sends them to raise an incident that already exists. Narrower halts name a "
    "department, an agent, a connector or a person, and each of those is a row like any "
    "other and is filtered like one."
)

#: Why the gaps report counts one abstention reason and not the other four.
ONLY_ONE_ABSTENTION_IS_A_FACT_ABOUT_THE_COMPANY: Final = (
    "brain.gate.abstain.AbstentionReason has five members and only NOTHING_CONNECTED is a "
    "fact about this company's setup, identical for everybody, which is what its own "
    "comment says. NOTHING_RETRIEVED deliberately covers the case where a record existed "
    "and was withheld, and NOT_ENTITLED is byte identical to it on the way out. A gaps "
    "screen counting those publishes refusals as holes in the knowledge base: wrong as a "
    "roadmap, and a count of hidden things as a disclosure."
)

#: Why the ceiling panel has nowhere to put an amount.
A_REFUSAL_CARRIES_NO_FIGURE_ON_A_SCREEN_EITHER: Final = (
    "brain.ops.spend.Refusal carries a level and a period and nothing else, so the sentence "
    "somebody reads when a budget runs out names the budget and who can raise it and never "
    "how much was spent or by whom. A console panel explaining what happens at the ceiling "
    "is where that would be helpfully undone, so the type built here has the same two "
    "fields and the ladder, and no field an amount could be put in."
)

#: Why a canary finding is filtered by the field it names.
A_CANARY_FINDING_NAMES_THE_FIELD_THE_LEAK_WAS_IN: Final = (
    "brain.ops.canaries refuses to put the leaked value in a finding and keeps the field "
    "name, which is right for an alert read by whoever planted the canary. On a quality "
    "screen the field name is the disclosure: a list of subjects is a list of the columns "
    "this system holds, offered to whoever may open a report. The findings a reader is "
    "shown are the ones whose subject their own reach already admits."
)


class OperateError(Exception):
    """Raised when a figure or a row would say more than the reader holds."""


#: What a connector health table is handed when nothing has checked anything.
#:
#: A shared frozen mapping rather than a default built at each call, for the reason
#: `brain.console.workspace_capabilities._NO_PROJECTIONS` is a `MappingProxyType`: a default
#: constructed per call is a default that can differ, and a mutable one is a default that can
#: be written to by whoever received it.
_NOTHING_CHECKED: Final[Mapping[str, ConnectorHealth]] = MappingProxyType({})


# ------------------------------------------------------------------------- the register
class Attribution(enum.StrEnum):
    """Whether a screen's figure has a version that is one person's. Two, and no third.

    There is deliberately nothing meaning "the department's". A figure aggregated over a
    group the reader cannot enumerate still moves when one of them works, which is the
    argument `brain.console.workspace.Basis` makes against a middle basis, and a middle
    attribution would be the same disclosure one level up.
    """

    #: Counted over rows carrying the person they belong to. Narrows honestly.
    PER_PERSON = "per_person"
    #: Counted over rows belonging to nobody. Withheld rather than narrowed.
    WHOLE_INSTALL = "whole_install"


#: The screen the other eleven lend a figure to.
#:
#: Named rather than assumed to be the first entry of the screen registry, because the
#: registry's order is the menu's order and a later insertion would silently repoint this.
LANDING: Final = "overview"

#: The field name that says a row belongs to somebody. See
#: `ATTRIBUTION_IS_A_FACT_ABOUT_THE_ROW_AND_NOT_A_LABEL_ON_THE_SCREEN`.
ATTRIBUTION_FIELD: Final = "principal_id"


def _field_names(record_type: type) -> frozenset[str]:
    """The fields of a dataclass or of a pydantic model, whichever this is.

    Both, because the row types these screens count are written in both styles and the
    register would otherwise be checkable for eight of them and taken on trust for the rest,
    which is the half nobody notices is unchecked. `brain.knowledge.item.KnowledgeItem` is
    the pydantic one.
    """
    declared: Mapping[str, Any] = getattr(record_type, "__dataclass_fields__", {})
    if declared:
        return frozenset(declared)
    model: Mapping[str, Any] = getattr(record_type, "model_fields", {})
    return frozenset(model)


@dataclass(frozen=True)
class Panel:
    """One screen, the row its figure counts, and the two sentences about what it may show.

    `row` is a dotted path rather than prose because the attribution below is checked against
    it: `operate_gaps` imports the type and asks whether it carries a principal. `shows` and
    `never` follow `brain.console.govern.GovernSurface`, and `never` is the sentence a ticket
    is written without.
    """

    #: The `brain.console.screens` key. Checked against that registry rather than restated.
    key: str
    #: Dotted path to the type a figure over this screen is counted over.
    row: str
    #: What that number counts, in words, for the person reading the landing screen.
    counts: str
    attribution: Attribution
    #: What the screen puts in front of a reader.
    shows: str
    #: What it must never put in front of one, however useful that would be.
    never: str

    def __post_init__(self) -> None:
        if self.key == LANDING:
            msg = (
                f"{LANDING} is registered as lending itself a figure, and the only figure it "
                f"could lend is how many of the others it managed to show. "
                f"{A_SECOND_FIGURE_FOR_ONE_SCREEN_IS_A_SUBTRACTION}"
            )
            raise OperateError(msg)
        if not self.counts.strip():
            msg = (
                f"{self.key} says nothing about what its figure counts, so the landing "
                "screen renders a number with no unit and the reader supplies one"
            )
            raise OperateError(msg)
        if "." not in self.row:
            msg = (
                f"{self.key} names {self.row!r} as its row, which is not a dotted path, so "
                "nothing can import it and the attribution below rests on nobody's word"
            )
            raise OperateError(msg)
        if not self.shows.strip() or not self.never.strip():
            msg = (
                f"{self.key} does not say both what it shows and what it must never show; "
                "the second sentence is the one a screen gets built without"
            )
            raise OperateError(msg)

    def row_type(self) -> type:
        """The type this screen's figure counts, imported.

        Imported rather than held as an object, so this module does not import eleven
        packages for the sake of a register. `operate_gaps` is where the failure surfaces.
        """
        module_path, _, name = self.row.rpartition(".")
        found = getattr(importlib.import_module(module_path), name)
        if not isinstance(found, type):
            msg = f"{self.key} names {self.row!r}, which is not a type"
            raise OperateError(msg)
        return found


#: Every operate and report screen except the landing one, in the order the menu shows them.
#:
#: A tuple rather than a mapping for the reason `brain.console.screens.SCREENS` gives: the
#: order is information, and it is the order somebody reads the front page in.
PANELS: Final[tuple[Panel, ...]] = (
    Panel(
        key="runs",
        row="brain.ops.jobs.JobRecord",
        counts="runs executing right now",
        attribution=Attribution.PER_PERSON,
        shows="what is executing, for whom, in which lane and since when",
        never=(
            "a job's arguments, which are identifiers of records the reader may hold nothing "
            "over, and no count of the runs belonging to people they cannot see"
        ),
    ),
    Panel(
        key="queue",
        row="brain.ops.jobs.JobRecord",
        counts="jobs waiting to start",
        attribution=Attribution.PER_PERSON,
        shows="what is waiting, what is scheduled and what is being retried",
        never=(
            "a queue depth over everybody's work to a reader who could not open this screen, "
            "because a depth is a count of other people's asking"
        ),
    ),
    Panel(
        key="connectors",
        row="brain.connectors.registry.RegisteredConnector",
        counts="sources this install reads",
        attribution=Attribution.WHOLE_INSTALL,
        shows="every source in reach, whether it is answering, and when it last was checked",
        never=(
            "the name of a source outside the reader's reach, in any state; naming a source "
            "is a disclosure and a health table is that disclosure thirty times over"
        ),
    ),
    Panel(
        key="models",
        row="brain.models.routing.RoutingRung",
        counts="model deployments in the routing chain",
        attribution=Attribution.WHOLE_INSTALL,
        shows="which model answers which tier, and which deployment is out of rotation",
        never=(
            "a degraded provider reported as an absence of an answer; an outage is a fact "
            "about this install and never a fact about whether a record exists"
        ),
    ),
    Panel(
        key="knowledge_coverage",
        row="brain.knowledge.item.KnowledgeItem",
        counts="documents behind the answers",
        attribution=Attribution.WHOLE_INSTALL,
        shows="per area, how much is behind it, how much is ageing and how much is stale",
        never=(
            "an area the reader's own reach does not admit, and never the size of the "
            "corpus beside the size of what they can see"
        ),
    ),
    Panel(
        key="incidents",
        row="brain.ops.wiring.Component",
        counts="things degraded now",
        attribution=Attribution.WHOLE_INSTALL,
        shows="what is degraded, since when, and which tools stop working because of it",
        never=(
            "a tool declared on a source the reader does not reach, because the blocked "
            "list would then be a catalogue of operations against sources they cannot see"
        ),
    ),
    Panel(
        key="halt",
        row="brain.ops.halt.Halt",
        counts="halts in force",
        attribution=Attribution.WHOLE_INSTALL,
        shows="everything stopped, who stopped it and why, plus every halt that stops them",
        never=(
            "a halt naming a department, an agent, a connector or a person out of the "
            "reader's reach; the halt on everything is the one exception and it stops them too"
        ),
    ),
    Panel(
        key="usage",
        row="brain.ops.spend.Actual",
        counts="charged runs in the period",
        attribution=Attribution.PER_PERSON,
        shows="what was consumed, grouped by a dimension the reader may group by",
        never=(
            "a group whose members the reader cannot enumerate, because a breakdown by "
            "person is a listing of people wearing an arithmetic label"
        ),
    ),
    Panel(
        key="budget",
        row="brain.ops.budgets.BudgetRow",
        counts="ceilings in force",
        attribution=Attribution.WHOLE_INSTALL,
        shows="which ceilings apply, and exactly what the system does on the way to each",
        never=(
            "an amount beside the refusal sentence; the refusal names the budget and who "
            "may raise it and has nowhere to carry a figure"
        ),
    ),
    Panel(
        key="questions",
        row="brain.chat.turns.Turn",
        counts="questions asked in the period",
        attribution=Attribution.PER_PERSON,
        shows="what was asked, and which areas nothing is connected to",
        never=(
            "a refusal counted as a gap; four of the five abstention reasons are facts "
            "about one person's reach and counting them publishes what they were refused"
        ),
    ),
    Panel(
        key="quality",
        row="brain.ops.canaries.CanaryFinding",
        counts="canary findings outstanding",
        attribution=Attribution.WHOLE_INSTALL,
        shows="what the permission canaries found, by the field each finding is about",
        never=(
            "a finding whose subject is a field the reader's reach does not admit, because "
            "the subject is a column name and a list of them is the schema"
        ),
    ),
)

#: How many panels there are, so a test can pin it and a person can quote it.
#:
#: Pinned rather than computed for the reason `brain.console.screens.SCREEN_COUNT` is: the
#: interesting failure is a panel disappearing in a refactor, and `len(x) == len(x)` would not
#: notice. Eleven rather than twelve because the landing screen lends itself nothing.
PANEL_COUNT: Final = 11

#: The two screen groups this module covers, so the completeness check names them once.
COVERED_GROUPS: Final[tuple[Group, ...]] = (Group.OPERATE, Group.REPORT)


def panel(key: str) -> Panel:
    """One panel by its screen key, or a failure naming it."""
    for one in PANELS:
        if one.key == key:
            return one
    msg = f"no panel named {key!r}"
    raise KeyError(msg)


# --------------------------------------------------------------- honest counting (M27.2.1)
@dataclass(frozen=True)
class Tile:
    """One figure on the landing screen, and whose it is (M27.2.1).

    `basis` is carried rather than left implicit, which is `brain.console.workspace.Headline`'s
    argument: a figure whose meaning is unstated is read as the total, so a reader shown their
    own runs with no label reads them as the system's.

    There is no field for a total, a share, a percentage or an amount withheld, and
    `hidden_count_fields` is the check that keeps it that way rather than a reviewer.
    """

    #: The screen this figure came from. The panel says what it counts.
    key: str
    basis: Basis
    #: How many rows this reader was counted over. A count of what was shown.
    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            msg = f"{self.key} reports {self.value} rows, which is not a count of anything"
            raise OperateError(msg)


@dataclass(frozen=True)
class Overview:
    """The landing screen, for one reader (M27.2.1).

    One field. A second carrying what was withheld would be a count of screens this person
    may not open, which is `brain.console.screens.
    A_MENU_THAT_COUNTS_WHAT_IT_HID_IS_A_DIRECTORY_OF_WHAT_YOU_CANNOT_SEE` in a figure instead
    of a menu, and the menu already refuses it.
    """

    tiles: tuple[Tile, ...] = ()


def _principal_of(row: object) -> str:
    """The person a row is attributed to, read off the row and never supplied by a caller.

    Structural rather than a callable parameter, and that is the point rather than economy:
    a caller passing `lambda one: reader.principal_id` would make every row theirs, and the
    call site would look like it was passing data. Refused loudly rather than defaulting,
    because a missing attribute here means the register named a per-person screen over rows
    that belong to nobody, and the quiet outcome is a figure of zero for everybody.
    """
    found = getattr(row, ATTRIBUTION_FIELD, None)
    if not isinstance(found, str) or not found:
        msg = (
            f"a row of {type(row).__name__} carries no {ATTRIBUTION_FIELD}, so a per-person "
            f"figure over it belongs to nobody. "
            f"{ATTRIBUTION_IS_A_FACT_ABOUT_THE_ROW_AND_NOT_A_LABEL_ON_THE_SCREEN}"
        )
        raise OperateError(msg)
    return found


def tile(
    one: Panel,
    rows: Sequence[object],
    reader: EntitlementSet,
    now: datetime | None = None,
) -> Tile | None:
    """One landing-screen figure, or `None` when there is no honest one (M27.2.1).

    `rows` are the rows this reader may already see, filtered by whichever screen owns them.
    What is decided here is the second question: whether the figure may be over all of them
    or only over the reader's own, and whether a narrower one exists at all.

    The basis comes from `brain.console.agent_output.basis_over` against this panel's own
    screen, so the grant behind the figure is the grant behind the screen. See
    `A_FRONT_PAGE_FIGURE_IS_A_SHORTCUT_PAST_THE_SCREEN_IT_CAME_FROM`.

    `None` for a whole-install figure on the narrower basis, withheld rather than narrowed:
    see `A_FIGURE_WITH_NO_NARROWER_VERSION_IS_WITHHELD_AND_NEVER_NARROWED`. There is no
    parameter through which a precomputed figure could arrive; `operate_gaps` reads this
    signature rather than trusting the sentence.
    """
    basis = basis_over(one.key, reader, now)
    if basis is Basis.EVERYONE:
        return Tile(key=one.key, basis=basis, value=len(rows))
    if one.attribution is Attribution.WHOLE_INSTALL:
        return None
    mine = [row for row in rows if _principal_of(row) == reader.principal_id]
    return Tile(key=one.key, basis=basis, value=len(mine))


def overview(tiles: Iterable[Tile | None]) -> Overview:
    """The landing screen: the figures that could be shown honestly, in menu order (M27.2.1).

    Nothing is added for a figure that was withheld. A placeholder, a greyed panel or a
    heading with no number under it all say the same thing as a count would, which is that
    there is a screen here the reader may not open, and the menu already declines to say it.

    Refuses two tiles for one screen. See `A_SECOND_FIGURE_FOR_ONE_SCREEN_IS_A_SUBTRACTION`:
    the pair is a subtraction whatever the two labels say, and the difference between them is
    a count of work belonging to people the reader cannot see.

    Ordered by the register rather than by whatever the caller assembled, so two readings of
    an unchanged system put the same figure in the same place.
    """
    kept = [one for one in tiles if one is not None]
    seen: set[str] = set()
    for one in kept:
        if one.key in seen:
            msg = (
                f"{one.key} lends the landing screen two figures. "
                f"{A_SECOND_FIGURE_FOR_ONE_SCREEN_IS_A_SUBTRACTION}"
            )
            raise OperateError(msg)
        seen.add(one.key)
    order = {entry.key: index for index, entry in enumerate(PANELS)}
    unknown = sorted(one.key for one in kept if one.key not in order)
    if unknown:
        msg = f"the landing screen was handed figures from unregistered screens: {unknown}"
        raise OperateError(msg)
    return Overview(tiles=tuple(sorted(kept, key=lambda one: order[one.key])))


# ------------------------------------------------------------------- live runs (M27.2.2)
#: The states a job is in while it is executing, as against waiting or finished.
#:
#: Anchored against `brain.ops.jobs` rather than written from memory: every member must be a
#: state the job model treats as having spent an attempt, and none may be terminal. A state
#: added to one list and not the other is a live runs screen that shows finished work, or one
#: that misses a job the moment it is cancelled and leaves it running with nothing watching.
EXECUTING: Final[frozenset[JobState]] = frozenset({JobState.RUNNING, JobState.CANCELLING})

#: The states a job is in while it is waiting for a worker, which is the queue's own figure.
WAITING: Final[frozenset[JobState]] = frozenset({JobState.QUEUED})

#: The two screens a job row appears behind, each with its own grant.
#:
#: One `JobRecord` is a row on the live runs screen while it executes and a row on the queue
#: screen while it waits, and those are two screens an administrator grants separately. So the
#: grant that governs a row is the grant of the screen the row is on, and `may_watch` takes
#: the screen rather than reading one. A single capability for both would mean somebody
#: granted the queue could watch live traffic, which is not what they were given.
RUNS_SCREEN: Final = "runs"
QUEUE_SCREEN: Final = "queue"


def _run_row(record: JobRecord) -> dict[str, str]:
    """The fields a run grant's scope may be written against.

    Three, all of them closed vocabularies or references and none a business attribute,
    exactly as `brain.ops.jobs._scope_row` chooses for a dead letter. A grant scoped on a
    field the row does not carry admits nothing, which fails closed; a wider row would let a
    grant be written against something this surface cannot evaluate.
    """
    return {
        "task": record.job.task,
        "traffic_class": record.job.traffic_class.value,
        "state": record.state.value,
        ATTRIBUTION_FIELD: record.principal_id,
    }


def may_watch(
    record: JobRecord,
    reader: EntitlementSet,
    now: datetime | None = None,
    *,
    screen_key: str = RUNS_SCREEN,
) -> bool:
    """Whether this reader may see this job at all. Two ways in, and no third (M27.2.2).

    It is their own work, or a grant covers it in a scope matching the row. That is
    `brain.ops.jobs.may_see`'s decision about a dead letter asked about a job that has not
    failed yet, and the capability is the screen's own, read off the registry rather than
    spelled again here. See `A_RUNNING_JOB_NAMES_THE_PERSON_IT_IS_RUNNING_FOR`.

    `screen_key` is a parameter because one job row appears behind two screens: live runs
    while it executes and the queue while it waits. Those are granted separately, so reading
    one capability here would let a queue grant reach live traffic. The default is the runs
    screen because that is the narrower of the two to be wrong about.
    """
    if record.principal_id == reader.principal_id:
        return True
    where: Scope | None = reader.scope_for(screen(screen_key).read.requires, now)
    if where is None:
        return False
    return where.matches(_run_row(record))


def visible_runs(
    records: Sequence[JobRecord],
    reader: EntitlementSet,
    now: datetime | None = None,
    *,
    screen_key: str = RUNS_SCREEN,
) -> tuple[JobRecord, ...]:
    """The jobs this reader may see on one screen, in the order they were given (M27.2.2).

    One pass, one predicate, and nothing recorded about what was skipped. The strong form is
    what the test asserts: this list is identical to the one produced from records where the
    invisible jobs were never enqueued, which is the only version of indistinguishable worth
    having. `brain.ops.jobs.visible_dead_letters` makes the same claim about its own list.
    """
    return tuple(
        record for record in records if may_watch(record, reader, now, screen_key=screen_key)
    )


@dataclass(frozen=True)
class RunRow:
    """One live run, as a reader may see it (M27.2.2).

    **No arguments field, and that absence is the mechanism.** See
    `AN_ARGUMENT_IS_A_REFERENCE_TO_A_RECORD_THE_READER_MAY_HOLD_NOTHING_OVER`. The task name
    is a closed vocabulary of things this system can do; the arguments are identifiers of
    records, and the screen's own purpose says the question rather than the answer.

    No field here is a count of anything withheld, which `operate_gaps` asks of the type.
    """

    job_id: str
    task: str
    principal_id: str
    state: JobState
    attempts: int
    #: When this job was due to start, which is what a reader reads as "since".
    since: datetime


def run_rows(
    records: Sequence[JobRecord],
    reader: EntitlementSet,
    now: datetime | None = None,
    *,
    states: frozenset[JobState] = EXECUTING,
) -> tuple[RunRow, ...]:
    """What the live runs screen shows: the executing jobs this reader may watch (M27.2.2).

    Filtering by reach happens first and the state filter second, so there is no arrangement
    of arguments that produces a list of everybody's running work. `states` is a parameter
    rather than a constant read inside, because the queue screen asks the same question about
    `WAITING` and a second function for it would be the same filter written twice.
    """
    return tuple(
        RunRow(
            job_id=record.job_id,
            task=record.job.task,
            principal_id=record.principal_id,
            state=record.state,
            attempts=record.attempts,
            since=record.scheduled_at,
        )
        for record in visible_runs(records, reader, now, screen_key=RUNS_SCREEN)
        if record.state in states
    )


# ---------------------------------------------------------- queue and automations (M27.2.6)
@dataclass(frozen=True)
class QueueSummary:
    """What the queue screen shows above the list (M27.2.6).

    Every figure is computed from the rows the reader may see and from nothing else, so the
    summary of a queue holding other people's work is identical to the summary of a queue that
    never held any. That is `brain.ops.jobs.DeadLetterSummary`'s construction and it is the one
    worth copying.

    `by_task` carries only the tasks present among the visible rows. Every task the system can
    run, keyed at zero, would be a catalogue of what this install does offered to whoever may
    open the screen, which is the opposite of what the dead-letter summary wants from its own
    exhaustive keying: that one is over a closed vocabulary of failure reasons nobody is
    refused, and this one is over a list that grows with the tools installed.
    """

    #: Waiting jobs by task name, over the rows this reader may see.
    by_task: Mapping[str, int]
    #: How many of those are being retried rather than started for the first time.
    retrying: int
    #: The oldest visible waiting job, or `None`. What makes a stuck queue visible.
    oldest_at: datetime | None


def queue_basis(entitlement: EntitlementSet, now: datetime | None = None) -> Basis:
    """Whose queue figures this reader may be shown (M27.2.6).

    `brain.console.agent_output.basis_over` against the queue screen, which is the same
    question `brain.console.agent_automations.schedule_basis` asks of the same screen for an
    agent's scheduled work. Both call the one function and a test pins them equal, so the two
    surfaces cannot come to different answers about one grant.
    """
    return basis_over(QUEUE_SCREEN, entitlement, now)


def queue_summary(
    records: Sequence[JobRecord], reader: EntitlementSet, now: datetime | None = None
) -> QueueSummary:
    """The queue's figures, over the waiting jobs this reader may see (M27.2.6).

    Filtering happens first and the arithmetic happens on what is left. A retry is recognised
    from the attempt counter rather than from a state, because `brain.ops.jobs` records that
    scheduling is a timestamp and not a state: a job waiting for its second attempt is
    `QUEUED` exactly like one waiting for its first, and the counter is the only thing that
    tells them apart.
    """
    waiting = [
        record
        for record in visible_runs(records, reader, now, screen_key=QUEUE_SCREEN)
        if record.state in WAITING
    ]
    counts: dict[str, int] = {}
    for record in waiting:
        counts[record.job.task] = counts.get(record.job.task, 0) + 1
    return QueueSummary(
        by_task=dict(sorted(counts.items())),
        retrying=sum(1 for record in waiting if record.attempts > 0),
        oldest_at=min((record.scheduled_at for record in waiting), default=None),
    )


# ------------------------------------------------------------- connector health (M27.2.4)
def reachable_connectors(
    registry: Sequence[RegisteredConnector], reachable: Iterable[str]
) -> tuple[RegisteredConnector, ...]:
    """The sources this reader may be told exist, in registry order (M27.2.4).

    `brain.console.screens.offerable` is the filter, called rather than reimplemented: the
    connector dropdown on every screen in this group is narrowed by that function, and a
    health table narrowed by a second one would disagree with its own filter. See
    `NAMING_A_SOURCE_IS_A_DISCLOSURE_ON_A_LIST_TOO`.

    Returns the connectors and no count of what was dropped, for the reason `offerable`
    returns one value.
    """
    admitted = set(offerable([one.name for one in registry], reachable))
    return tuple(one for one in registry if one.name in admitted)


@dataclass(frozen=True)
class ConnectorRow:
    """One source on the health screen, as a reader may see it (M27.2.4).

    Carries the state the registry holds and the state a health check reported, because they
    answer different questions: a connector can be enabled and unreachable, and a screen
    showing one of the two makes an operator chase the wrong thing.

    No field for a credential, a host or an endpoint. Those are the connector's own secrets
    and `brain.connectors.contract.assert_holds_no_credential` refuses them at the source; a
    console row is the obvious second place for one to appear.
    """

    name: str
    #: What the registry says: registered, enabled, disabled or quarantined.
    lifecycle: str
    #: What the last health check said, or empty when nothing has checked it.
    health: str
    checked_at: datetime | None


def connector_rows(
    registry: Sequence[RegisteredConnector],
    reachable: Iterable[str],
    *,
    checked: Mapping[str, ConnectorHealth] = _NOTHING_CHECKED,
) -> tuple[ConnectorRow, ...]:
    """The connector health table, for one reader (M27.2.4).

    Filtering by reach happens first, so there is no point in this function at which a row
    for an unreachable source exists to be accidentally kept. `checked` is handed in rather
    than gathered, because every connector produces its own `ConnectorHealth` through its own
    function with its own signature, and a console module calling five of them would be a
    sixth opinion about what healthy means.

    A source nothing has checked reports an empty health rather than a healthy one, and the
    two must not be collapsed: `brain.connectors.contract.HealthState` has an `UNCONFIGURED`
    member for a source that was never set up, and a source that is set up and has never been
    reached is a different thing an operator wants to see.
    """
    return tuple(
        ConnectorRow(
            name=one.name,
            lifecycle=one.state.value,
            health=checked[one.name].state.value if one.name in checked else "",
            checked_at=checked[one.name].checked_at if one.name in checked else None,
        )
        for one in reachable_connectors(registry, reachable)
    )


# ------------------------------------------------- knowledge coverage and staleness (M27.2.5)
#: The freshness bands a coverage row reports, in the order a reader reads them.
#:
#: `brain.gate.provenance.Freshness` is the one scale in this repository and the invariant
#: suite refuses a second, so these are its members rather than bands of this module's own.
COVERAGE_BANDS: Final[tuple[Freshness, ...]] = (
    Freshness.LIVE,
    Freshness.AGEING,
    Freshness.STALE,
    Freshness.UNSTATED,
)


@dataclass(frozen=True)
class CoverageRow:
    """What is behind one area, as this reader may see it (M27.2.5).

    **No field for the size of the corpus**, no share and no percentage. Each of those is
    this figure divided by a total the reader was not shown, and two of them recover it. See
    `AN_AREA_OUT_OF_REACH_IS_ABSENT_AND_AN_EMPTY_AREA_IS_A_GAP` and
    `brain.knowledge.quality.A_COUNT_OF_WHAT_WAS_SHOWN_IS_NOT_A_COUNT_OF_WHAT_WAS_HIDDEN`.

    A row with `items` at zero is the point of the screen rather than an empty state: an area
    the reader reaches and which holds nothing they may see is a gap, and the gaps are the
    roadmap. An area they do not reach has no row at all.
    """

    area: str
    #: How many items this reader may see in this area.
    items: int
    #: How many of those sit in each freshness band. Every band is a key, including zero,
    #: because a caller writing `by_freshness.get(STALE, 0)` reads as though stale were
    #: optional and it is the band the screen exists for.
    by_freshness: Mapping[Freshness, int]


def _item_row(item: KnowledgeItem) -> dict[str, object]:
    """One knowledge item in the shape `brain.knowledge.search.Reach.admits` evaluates.

    Built here rather than assumed, because that predicate is the audited one: it refuses a
    draft to anybody but its owner, refuses a state that is not retrievable, and evaluates the
    department branch through `Scope.matches`. Reimplementing any of that on a coverage screen
    would be a second answer to who may see a document.
    """
    return {
        "deleted_at": None,
        "state": item.state.value,
        "owner_id": item.visibility.owner_id or item.owner_id,
        "visibility": item.visibility.level.value,
        "department": item.visibility.department,
    }


def visible_items(items: Sequence[KnowledgeItem], reach: Reach) -> tuple[KnowledgeItem, ...]:
    """The items this reach admits, in the order they were given (M27.2.5).

    `Reach.admits` decides it, which is the Python half of the same predicate the search
    query compiles to SQL. Nothing here compares a department by hand.
    """
    return tuple(item for item in items if reach.admits(_item_row(item)))


def coverage(
    items: Sequence[KnowledgeItem],
    reader: EntitlementSet,
    *,
    areas: Sequence[str],
    now: datetime,
    horizon: StalenessHorizon = DEFAULT_HORIZON,
) -> tuple[CoverageRow, ...]:
    """What is behind each area this reader reaches, and how old it is (M27.2.5).

    Empty for a reader holding no read of the knowledge plane at all, because
    `brain.knowledge.search.reach_for` returns `None` for one and `None` is nothing rather
    than everything. See `NO_READ_OF_THE_PLANE_IS_NOTHING_AND_NEVER_EVERYTHING`: an unfiltered
    coverage screen is the exact shape that mistake takes, since an empty reach looks like a
    caller who simply has no departments yet.

    `areas` is the department registry and passing it here is what lets the reach be computed
    against it. What comes back names only the departments the reach admits, and there is no
    row, no placeholder and no count for the rest.

    Freshness is assessed from the item's own verification time through
    `brain.gate.provenance.assess_freshness`, which takes the timestamp as a string, and an
    item nobody has verified is `UNSTATED` rather than stale: never checked and checked long
    ago are different facts and a reader deciding what to fix needs both.
    """
    reach = reach_for(reader, departments=areas, now=now)
    if reach is None:
        return ()
    admitted = visible_items(items, reach)
    rows: list[CoverageRow] = []
    for area in reach.departments:
        here = [item for item in admitted if item.visibility.department == area]
        bands = dict.fromkeys(COVERAGE_BANDS, 0)
        for item in here:
            bands[freshness_of(item, now=now, horizon=horizon)] += 1
        rows.append(CoverageRow(area=area, items=len(here), by_freshness=bands))
    return tuple(rows)


def freshness_of(
    item: KnowledgeItem, *, now: datetime, horizon: StalenessHorizon = DEFAULT_HORIZON
) -> Freshness:
    """How current one item is, on the one freshness scale this repository has.

    An item with no verification time is `UNSTATED` and is not assessed as stale. That is
    `brain.gate.provenance.assess_freshness`'s own answer for a timestamp it cannot read, and
    repeating the distinction here keeps a coverage screen from reporting an unverified
    document as an old one, which would send somebody to re-verify a thing nobody ever did.
    """
    if item.verified_at is None:
        return Freshness.UNSTATED
    return assess_freshness(item.verified_at.isoformat(), horizon=horizon, now=now)


# --------------------------------------------------------------- incidents (M27.2.7)
@dataclass(frozen=True)
class Incident:
    """One thing that is degraded now, and what stops working because of it (M27.2.7).

    `blocks` is the tools the degraded source declares, filtered to what this reader reaches.
    See `WHAT_AN_INCIDENT_BLOCKS_IS_NAMED_IN_CAPABILITIES_SOMEBODY_MAY_NOT_HOLD`. There is no
    field for how many were filtered out, and an incident with nothing left to name is not
    built at all rather than built empty: an empty blocked list beside a source name would say
    the reader is missing something and not what.
    """

    #: The source or component that is degraded.
    subject: str
    #: What the health check said: degraded, down or unconfigured.
    state: str
    since: datetime
    #: The tool names that stop working, in manifest order.
    blocks: tuple[str, ...] = ()


def blocked_by(manifest: ConnectorManifest, reachable: Iterable[str]) -> tuple[str, ...]:
    """The tools a degraded source takes with it, or nothing when it is out of reach.

    All of the source's tools or none of them, decided by whether the reader reaches the
    source at all. A partial list would be a per-tool disclosure of what exists on a source,
    and the reader has no way to tell a tool that is missing from one that was removed.
    """
    if manifest.name not in set(reachable):
        return ()
    return manifest.tool_names()


def incidents(
    degraded: Sequence[tuple[ConnectorManifest, str, datetime]],
    reachable: Iterable[str],
) -> tuple[Incident, ...]:
    """What is degraded now, filtered to the sources this reader reaches (M27.2.7).

    Takes the health verdicts rather than performing them, because every connector produces
    its own `ConnectorHealth` with its own signature and a console module that called five of
    them would be a sixth place that decides what healthy means.

    A source outside the reach produces no incident at all. Filtering the blocked list while
    keeping the row would name the source, which is the disclosure the filtering was for.
    """
    admitted = set(reachable)
    found: list[Incident] = []
    for manifest, state, since in degraded:
        if manifest.name not in admitted:
            continue
        found.append(
            Incident(
                subject=manifest.name,
                state=state,
                since=since,
                blocks=blocked_by(manifest, admitted),
            )
        )
    return tuple(found)


# -------------------------------------------------------------- the stop button (M27.2.8)
def _halt_row(one: Halt) -> dict[str, str]:
    """The fields a halt grant's scope may be written against.

    The scope and its target, which are the two things a halt names. `declared_by` is
    deliberately absent: a grant scoped to halts you declared yourself would hide from an
    administrator the halt somebody else put on their department, which is the one they most
    need to see.
    """
    return {"scope": one.scope.value, "target": one.target}


def stopped_for(
    state: HaltState, reader: EntitlementSet, now: datetime | None = None
) -> tuple[Halt, ...]:
    """Everything currently stopped, as this reader may see it (M27.2.8).

    **A halt on everything is in this list whatever the reader's scope**, because it stops
    them. See `A_GLOBAL_HALT_IS_SHOWN_TO_EVERYBODY_IT_STOPS`. Narrower halts name a
    department, an agent, a connector or a person, and each is filtered by the halt screen's
    own capability in a scope that matches the row.

    Widest first, following `HaltState.blocking`, so a reader reporting one reports the most
    general, which is the one an administrator will recognise.

    There is deliberately no branch here on whether the store could be read. A state nobody
    could read carries no halts, so this returns nothing for it without a guard, and a guard
    that returned early would throw away the halts of a state that was read partially. What
    that state is not is a system with nothing stopped:
    `brain.ops.halt.IF_WE_CANNOT_TELL_WHETHER_WE_ARE_HALTED_WE_ARE_HALTED` makes unknown mean
    halted for admission, so in that moment every request is being refused while this list is
    empty. `stop_is_unknown` is that second answer, kept separate because an empty tuple
    cannot carry it and a renderer reading only this one would print the wrong sentence.
    """
    where: Scope | None = reader.scope_for(screen("halt").read.requires, now)
    found = [
        one
        for one in state.halts
        if one.scope is HaltScope.EVERYTHING
        or (where is not None and where.matches(_halt_row(one)))
    ]
    return tuple(sorted(found, key=lambda one: (one.scope is not HaltScope.EVERYTHING, one.at)))


def stop_is_unknown(state: HaltState) -> bool:
    """Whether the screen must say it cannot tell, rather than that nothing is stopped.

    Separate from `stopped_for` returning an empty tuple, and that separation is the whole of
    it: an empty list and an unreadable store look identical to a renderer, and the second is
    the moment every request is being refused. The screen says so in its own words rather than
    by the absence of rows.
    """
    return not state.known


# ------------------------------------------------------------ questions and gaps (M27.4.1)
#: The abstention reasons a gaps report may count. One, and see
#: `ONLY_ONE_ABSTENTION_IS_A_FACT_ABOUT_THE_COMPANY`.
#:
#: Held as a set rather than as a comparison written into `gaps`, so a later edit adding a
#: second reason is a visible change to a named constant rather than a widened condition.
GAP_REASONS: Final[frozenset[AbstentionReason]] = frozenset({AbstentionReason.NOTHING_CONNECTED})


@dataclass(frozen=True)
class Gap:
    """One area nothing is connected to, and how often somebody asked about it (M27.4.1).

    Carries the scope statement the asker was already shown and never the question's text.
    A gaps screen listing what people typed is a transcript, and the transcript screen has
    its own grant; this one is about the shape of what is missing.
    """

    #: The reachable sources the abstention named, as `brain.gate.abstain.SearchScope` has
    #: them: derived from the asker's reach and never from what the search did.
    covered: tuple[str, ...]
    #: How many abstentions of this shape were counted. A count of rows in front of the
    #: reader rather than a count of anything withheld.
    occurrences: int


def gaps(abstentions: Sequence[Abstention]) -> tuple[Gap, ...]:
    """Where the system has nothing connected, most asked first (M27.4.1).

    Counts `NOTHING_CONNECTED` and nothing else. See
    `ONLY_ONE_ABSTENTION_IS_A_FACT_ABOUT_THE_COMPANY`: the other four reasons are outcomes of
    one person's reach or of a model's judgement, `NOTHING_RETRIEVED` deliberately covers the
    case where a record existed and was withheld, and counting those on a screen turns
    refusals into holes in the knowledge base. Wrong as a roadmap, and a count of hidden
    things as a disclosure.

    Grouped by the scope statement rather than by the detail, because `Abstention.detail` is
    written for an auditor and names things; the scope is what the asker was already told.
    """
    counts: dict[tuple[str, ...], int] = {}
    for one in abstentions:
        if one.reason not in GAP_REASONS:
            continue
        counts[one.scope.covered] = counts.get(one.scope.covered, 0) + 1
    return tuple(
        Gap(covered=covered, occurrences=seen)
        for covered, seen in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    )


def visible_questions(
    turns: Sequence[Turn], reader: EntitlementSet, now: datetime | None = None
) -> tuple[Turn, ...]:
    """The questions this reader may see, in the order they were asked (M27.4.1).

    Everybody's when they could open the questions screen and read them there, and otherwise
    their own. The same rule as every figure in this module, applied to rows: a transcript is
    the strongest form of the disclosure a count of it would only hint at.

    Answers are dropped whichever basis applies. The screen is questions and gaps, and an
    answer is the content plane rather than the existence plane the screen is registered on.
    """
    basis = basis_over(panel("questions").key, reader, now)
    return tuple(
        one
        for one in turns
        if one.kind is TurnKind.QUESTION
        and (basis is Basis.EVERYONE or one.principal_id == reader.principal_id)
    )


# ---------------------------------------------- budgets and what happens at the ceiling (M27.4.3)
@dataclass(frozen=True)
class CeilingEffect:
    """What the system does on the way to one ceiling, and what it says at it (M27.4.3).

    **No amount anywhere on this type.** See `A_REFUSAL_CARRIES_NO_FIGURE_ON_A_SCREEN_EITHER`:
    `brain.ops.spend.Refusal` carries a level and a period, so the sentence somebody reads
    names the budget and who may raise it and never how much was spent or by whom. A console
    panel explaining the ceiling is exactly where an amount gets helpfully added back.

    `ladder` is `brain.ops.spend.LADDER` in order, which is what happens before the refusal:
    a cheaper tier, then no fan-out, then queueing, then the refusal itself.
    """

    level: BudgetLevel
    #: The degradations tried before refusing, cheapest first.
    ladder: tuple[Rung, ...]
    #: The sentence the person who is refused reads.
    message: str
    #: Who can raise this budget, as the refusal names them: a role and never a person.
    raised_by: str


def ceiling_effect(allowance: Allowance) -> CeilingEffect:
    """What happens as one budget is used up, and what is said when it is (M27.4.3).

    Built from `brain.ops.spend.Refusal`, called rather than reworded, so the console and the
    channel say the same sentence. Two spellings of a refusal is two things to keep in step,
    and the console's copy is the one that would grow an amount.
    """
    refusal = Refusal(level=allowance.row.level, period=allowance.row.period)
    return CeilingEffect(
        level=allowance.row.level,
        ladder=LADDER,
        message=refusal.message,
        raised_by=refusal.raised_by,
    )


def ceilings_in_reach(
    rows: Sequence[BudgetRow], reader: EntitlementSet, now: datetime | None = None
) -> tuple[BudgetRow, ...]:
    """The budget rows this reader may see, in the order they were given (M27.4.3).

    A budget row names its subject: a department, a person or an agent. So the list is
    filtered by the budget screen's own capability in a scope matching the row, and a ceiling
    on somebody the reader cannot see is absent rather than shown without its subject. A row
    stripped of its subject is still a row, and a reader counting them has the number of
    people with budgets.
    """
    where: Scope | None = reader.scope_for(screen("budget").read.requires, now)
    if where is None:
        return ()
    return tuple(
        one for one in rows if where.matches({"level": one.level.value, "subject": one.subject})
    )


# ------------------------------------------------------- quality and canaries (M27.4.4)
def findings_in_reach(
    findings: Sequence[CanaryFinding], reachable: Iterable[str]
) -> tuple[CanaryFinding, ...]:
    """The canary findings this reader may be shown, in the order they were found (M27.4.4).

    `CanaryFinding.subject` is a field or tool name, so a findings list is a listing of the
    columns this system holds. See `A_CANARY_FINDING_NAMES_THE_FIELD_THE_LEAK_WAS_IN`: the
    canaries module already refuses to carry the leaked value, and what is decided here is
    the name.

    `brain.console.screens.offerable` is the filter, the same one the dropdowns use, and it
    returns no count of what it dropped. `scan_stores` prefixes a subject with its store, so
    the reachable set is compared against the whole subject as recorded rather than against a
    piece of it: a prefix comparison would admit `client.contract_value` to somebody granted
    `client.contract` and the failure would look like a helpful match.
    """
    admitted = set(offerable([one.subject for one in findings], reachable))
    return tuple(one for one in findings if one.subject in admitted)


# ------------------------------------------------------------------------- the diagnostic
#: Every module the model matrix would read, and which half each one holds.
#:
#: Written down rather than built, because that leaf is declined: the routing chain, the
#: breaker and the provider health record all exist and what is missing is a renderer, which
#: is not this module's to write. A register entry naming both halves is what stops the next
#: person concluding the machinery is absent and writing a third one.
MATRIX_SURFACES: Final[Mapping[str, str]] = {
    "brain.models.routing": "the chain: which rung answers which tier, and what was skipped",
    "brain.models.health": "the evidence: the breaker, the probe ring, when traffic last landed",
}

#: The types a reader of these surfaces is handed. Listed rather than discovered, following
#: `brain.console.workspace.WORKSPACE_SURFACE`: a type added here and not to this tuple is a
#: type the checks below never see.
OPERATE_ROWS: Final[tuple[type, ...]] = (
    Tile,
    Overview,
    RunRow,
    QueueSummary,
    ConnectorRow,
    CoverageRow,
    Incident,
    Gap,
    CeilingEffect,
)

#: Parameter names a precomputed figure would arrive through. See
#: `A_TOTAL_THAT_ARRIVES_AS_AN_ARGUMENT_WAS_COUNTED_SOMEWHERE_ELSE`.
NAMES_A_FIGURE_WOULD_ARRIVE_THROUGH: Final[frozenset[str]] = frozenset(
    {"total", "count", "figure", "value", "of_total", "population", "corpus_size"}
)


def usage_gaps() -> tuple[str, ...]:
    """Why the usage screen cannot show tokens by department today.

    Separate from `operate_gaps` because this one is expected to stay non-empty until a row
    carries both, exactly as `brain.console.screens.unregistered_tools` is kept apart from
    `screen_gaps`: a diagnostic that is red for a month is one somebody switches off, so the
    honest thing is to keep it away from the ones that must always be green.

    Reported rather than worked around. The available workaround is to join a telemetry row
    to a principal's department at read time, which puts a second answer to "which department
    is this person in" on a reporting path, and the wrong copy of that decides who appears in
    a report.
    """
    return (
        "brain.ops.spend.Actual carries a department and a cost and no token counts, "
        "brain.ops.telemetry carries token counts and no department, and nothing joins them. "
        "A tokens-by-department column would have to be assembled at read time from a second "
        "answer to which department somebody is in, and a figure that looks measured and is "
        "assembled is worse on a report than a column that is not there.",
    )


def operate_gaps(
    *,
    panels: Sequence[Panel] = PANELS,
    registry: Sequence[Screen] = SCREENS,
    rows: Sequence[type] = OPERATE_ROWS,
    landing: str = LANDING,
    counter: Callable[..., Any] = tile,
) -> tuple[str, ...]:
    """Everything about this group that would put a figure in front of somebody it is not for.

    Takes its inputs rather than reading this module's own constants, and a mutation is the
    reason: a diagnostic that can only run against the healthy tree has nothing to report on
    today's data, so switching off any of its refusals changes nothing observable and every
    one of them survives. Calling it with no arguments is the deployment check and calling it
    with a constructed set is the test, which is `brain.console.govern.govern_gaps`'s own
    argument about its parameters.

    `counter` is `tile` and exists so the last check can be exercised. The interesting state
    is a counting function that does take a figure, and there is deliberately no such
    function in this module, so a check that could only read `tile` would be one whose
    refusal nothing could reach and whose removal nothing would notice.

    Five checks. The first three hold the register to the screen registry and to the row types
    it claims; the last two hold the surface and the counting function to their shapes.
    """
    findings: list[str] = []

    wanted = [one.key for one in registry if one.group in COVERED_GROUPS and one.key != landing]
    claimed: dict[str, int] = {}
    for one in panels:
        claimed[one.key] = claimed.get(one.key, 0) + 1
    for key, seen in claimed.items():
        if seen > 1:
            findings.append(
                f"{key} is registered as a panel {seen} times, so the landing screen would "
                f"be handed two figures for it. {A_SECOND_FIGURE_FOR_ONE_SCREEN_IS_A_SUBTRACTION}"
            )
        if key not in wanted:
            findings.append(
                f"{key} is registered as a panel and is not an operate or report screen "
                "other than the landing one, so the two lists have come apart"
            )
    for key in wanted:
        if key not in claimed:
            findings.append(
                f"the {key} screen lends the landing screen no figure, so either it has one "
                "nobody wrote a rule for or the front page is missing a panel"
            )

    for one in panels:
        try:
            record_type = one.row_type()
        except (ImportError, AttributeError, OperateError):
            findings.append(
                f"{one.key} names {one.row!r} as its row and that does not resolve, so the "
                "attribution below rests on nobody having checked it"
            )
            continue
        carries = ATTRIBUTION_FIELD in _field_names(record_type)
        if carries and one.attribution is not Attribution.PER_PERSON:
            findings.append(
                f"{one.key} counts {one.row} which carries {ATTRIBUTION_FIELD}, and is "
                f"declared {one.attribution.value}, so a reader without the screen's grant "
                f"is shown nothing where an honest narrower figure exists. "
                f"{ATTRIBUTION_IS_A_FACT_ABOUT_THE_ROW_AND_NOT_A_LABEL_ON_THE_SCREEN}"
            )
        if not carries and one.attribution is Attribution.PER_PERSON:
            findings.append(
                f"{one.key} counts {one.row} which carries no {ATTRIBUTION_FIELD}, and is "
                f"declared {one.attribution.value}, so the narrower figure belongs to nobody "
                f"and comes out zero for every reader. "
                f"{ATTRIBUTION_IS_A_FACT_ABOUT_THE_ROW_AND_NOT_A_LABEL_ON_THE_SCREEN}"
            )

    findings.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(rows)
    )

    taken = set(inspect.signature(counter).parameters)
    findings.extend(
        f"{counter.__name__} takes {forbidden}, so a figure counted somewhere else can be "
        f"put on the landing screen. "
        f"{A_TOTAL_THAT_ARRIVES_AS_AN_ARGUMENT_WAS_COUNTED_SOMEWHERE_ELSE}"
        for forbidden in sorted(NAMES_A_FIGURE_WOULD_ARRIVE_THROUGH & taken)
    )

    return tuple(findings)
