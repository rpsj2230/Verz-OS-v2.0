"""Common automations an agent can take on, and the one confirmed step that installs one.

`brain.console.agent_automations` closed eight of the nine leaves in its group and declined this
one, M39.6.1.3, on two grounds. A gallery is a rendered thing, and there was no automations tab
to render it in. And the content looked like company detail: "a set of common automations is a
set of outcomes somebody at a particular company wants, and a list of them written here would be
exactly the company detail CLAUDE.md says never goes into the source." The first ground has gone,
because the agent workspace now draws an Automations tab and this is what it draws. The second is
answered here, and the answer is a line rather than a refusal.

**An outcome that would be correct on a server belonging to a company nobody here has met is
product content, and anything else is configuration.** That is CLAUDE.md's own test, applied to
each template rather than to the idea of a catalogue. "I write you a summary of this agent's week"
names no company, no system, no person and no domain, and it is right on every install for the
same reason `brain.agents.catalogue`'s twenty-three role manifests are: it is a thing this product
can be asked to do, described in the product's vocabulary. "I send the Friday numbers to the
finance channel" names a company's habit and a company's channel, and it belongs to that company,
stored as that installation's own template and never written here. See
`A_GENERIC_OUTCOME_IS_PRODUCT_CONTENT_AND_A_COMPANYS_OWN_IS_CONFIGURATION`. The four in `BUILT_IN`
are each about something every install has: the questions an agent is asked, the sources it
draws on, the approvals it raises and the work it did.

**These are not agent templates and do not pretend to be.** An agent template is a role, served
by `GET /agent-templates` behind the Skills and templates screen and installed by
`brain.agents.template` with a signature. An automation template is something one agent does
without being asked, installed onto that agent, and it has no signature because nothing here is
published by anybody: it is the product's, exactly as the unsigned role manifests are.

**A template has nowhere to hold a grant, so no template can widen anybody.** `AutomationTemplate`
has no field whose type could carry a capability, a grant, a scope or an entitlement set, which
`brain.ops.jobs.reach_carrying_fields` asks of the class rather than of a reviewer. What an
installed automation may reach is `brain.console.agent_automations.automation_reach`, which is
`brain.ops.automation.flow_reach` over the principal it runs as and the agent's own ceiling, so
the platform's one intersection is the only thing that decides it and a template cannot enter the
computation at all. See `A_TEMPLATE_HAS_NOWHERE_TO_HOLD_A_GRANT`.

**An installed automation runs as whoever installed it, and nobody else.** The obvious form has a
picker for the principal, and that picker is a way to widen yourself: an installer who names a
colleague with more reach sets unattended work running at that colleague's reach, which is
exactly what `brain.ops.automation_owner` refuses by letting a registration be written only in the
session's own name. So the installer is the principal, named, revocable by removing their grants,
and stopped by offboarding them. It is never the agent, for
`AN_AUTOMATION_RUNNING_AS_ITSELF_IS_A_GRANT_NOBODY_CAN_REVOKE`. See
`AN_INSTALLED_AUTOMATION_RUNS_AS_WHOEVER_INSTALLED_IT`.

**And so an install lands paused, because the two rules leave no other shape.** M39.6.2.2 makes a
schedule change a gated learning event whose approver may not be the principal the automation
runs as, which `agent_automations.may_change_schedule` enforces. Going from no automation to one
that runs every morning is the largest schedule change there is, and the installer is the
principal, so the installer cannot approve it. An install that set a next run would be the way
round that rule, reached by pressing a button in a gallery. The installed automation therefore has
no next run, which is what paused means in `agent_automations`, and starting it is a schedule
change somebody else approves. The template's cadence is shown so the person knows what it will do
once started. See `AN_INSTALL_CANNOT_BE_THE_WAY_ROUND_A_GATED_SCHEDULE`.

**Confirmed means the write is refused unless it carries what was shown.** `InstallPreview` is
everything the person is asked to agree to: the outcome, who it runs as, the cadence, that it
starts paused, and the reach it would hold, summarised by that reach's own digest.
`InstallPreview.confirmation` is a digest over all of it, and `install` refuses a request whose
confirmation is not the one the server computes now. So a request that skipped the preview is
refused, and so is one whose preview went stale: a grant the installer lost, a ceiling somebody
narrowed or a template that moved each change the digest. See
`A_CONFIRMATION_IS_EVIDENCE_OF_WHAT_WAS_SHOWN`.

Rejected: a keyed confirmation, signed with a server secret so that only a preview could have
produced it. It proves a round trip and nothing else. A client holding the installer's token can
fetch the preview and echo it, so the key would add a secret to manage and no refusal a person
could not already get round, and the property worth having is that what was agreed to is what is
written.

**The automation and its registry entry are one value.** `Installation` carries both and refuses
any shape in which they disagree, through `agent_automations.registry_gaps`, which is
`SchedulerChange`'s construction for the case `SchedulerChange` cannot express: its `before` is a
required automation, and an install has none. Loosening that field to admit `None` would make a
change from nothing to nothing constructible, so the install is its own value built from the same
check. `brain.ops.agent_automation_store` then writes both halves as one row in one statement.

**Installing twice is answered with the first.** One automation per agent, template and person,
held by a unique constraint rather than a read before the write, because two presses of one
button race each other and a read cannot see a write that has not committed. A second install is
told which automation it already has. The constraint names the person, so the conflict only ever
concerns the caller's own automation, which they may always see, and nothing about anybody else's
is disclosed by being refused. See `INSTALLING_TWICE_IS_ANSWERED_WITH_THE_FIRST`.

**Who may do which part.** Opening the gallery is the Automations tab's own read, through
`brain.console.reads.permitted`, so a person sees the gallery exactly when the tab is in their
strip. Installing is `AUTOMATION_AUTHORITY`, an `admin:` capability that
`brain.gate.admission` withholds from a password-only session, asked in a scope over the same
three fields `agent_automations` scopes scheduled work by: the agent, the task and the principal.
A grant can therefore be written for one department's agents, and a grant naming a field the row
does not carry admits nothing.

**What this does not do, and each is said on the screen.** Installing starts nothing: the
automation stays paused until somebody it does not run as starts it from the Automations tab
(`brain.console.automation_schedule`), and the worker's `automation_run` control then runs it
(`brain.ops.automation_run`). Only the outcomes `brain.ops.automation_run.TASKS` can perform can be
started, and the tab says what the others still need. There is no store for an installation's own
automation templates, because there is no surface that publishes one, and a table nothing writes is
a control that reaches nothing. The constant keeps its name from before anything ran one, because a
rename would reach two routes' response shapes for no change in what they say; see
`NOTHING_RUNS_AN_INSTALLED_AUTOMATION_YET`.

Task ids: M39.6.1.3
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
import secrets
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.agents.model import AgentRecord
from brain.console.agent_automations import (
    MINIMUM_GUARDS,
    Automation,
    RegistryEntry,
    automation_reach,
    outcome_name_refusals,
    register,
    registry_gaps,
)
from brain.console.reads import permitted
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.principal import Principal
from brain.gate.admission import admit
from brain.ops.automation_owner import AUTOMATION_ASSURANCE, AUTOMATION_CHANNEL, AUTOMATION_ID

# ------------------------------------------------------------------ written-down reasons
#: Where the line between the product's templates and a company's own is drawn.
A_GENERIC_OUTCOME_IS_PRODUCT_CONTENT_AND_A_COMPANYS_OWN_IS_CONFIGURATION: Final = (
    "An automation template that would be correct on a server belonging to a company nobody "
    "here has met is product content, as the agent role manifests are: it names no company, "
    "person, domain or system, only something this product can be asked to do. A template "
    "naming a company's own habit, channel or system is that company's configuration and is "
    "stored by its installation, never written into the source."
)

#: Why no template can widen anybody.
A_TEMPLATE_HAS_NOWHERE_TO_HOLD_A_GRANT: Final = (
    "A template carries an outcome, a task, a cadence and a sentence about what breaks, and no "
    "field whose type could hold a capability, a grant, a scope or an entitlement set. What an "
    "installed automation reaches is flow_reach over the principal it runs as and the agent's "
    "ceiling, so the one intersection decides it and a template never enters the computation."
)

#: Why the installer is the principal.
AN_INSTALLED_AUTOMATION_RUNS_AS_WHOEVER_INSTALLED_IT: Final = (
    "A picker for the principal is a way to widen yourself: naming a colleague with more reach "
    "sets unattended work running at theirs. So an automation installed from the gallery runs "
    "as the person who installed it, named, revocable by removing their grants and stopped by "
    "offboarding them, and never as the agent, whose ceiling is nobody's grant to revoke."
)

#: Why an install has no next run.
AN_INSTALL_CANNOT_BE_THE_WAY_ROUND_A_GATED_SCHEDULE: Final = (
    "A schedule change is a gated learning event whose approver may not be the principal the "
    "automation runs as. Going from no automation to one that runs every morning is the largest "
    "schedule change there is, and the installer is that principal. An install that set a next "
    "run would be a gated change approved by the one person the rule excludes, so it starts "
    "paused, and starting it is a schedule change somebody else approves."
)

#: Why the confirmation is a digest over what was shown.
A_CONFIRMATION_IS_EVIDENCE_OF_WHAT_WAS_SHOWN: Final = (
    "The confirmation is a digest over the outcome, the principal, the cadence, the paused start "
    "and the reach the automation would hold. A write carrying a different one is refused, so a "
    "request that skipped the preview is refused and so is one whose preview went stale because "
    "a grant, a ceiling or the template moved. It is evidence of what was agreed to, not a "
    "secret: anybody holding the installer's token could fetch the preview and echo it."
)

#: Why a second install is answered rather than written.
INSTALLING_TWICE_IS_ANSWERED_WITH_THE_FIRST: Final = (
    "One automation per agent, template and person. A second install writes nothing and is told "
    "which automation it already has. The rule is a unique constraint rather than a read before "
    "the write, because two presses of one button race and a read cannot see an uncommitted "
    "write, and it names the person, so the conflict only ever concerns the caller's own."
)

#: What the screen says about running. Named before anything ran an installed automation; the
#: sentence is what is true now.
NOTHING_RUNS_AN_INSTALLED_AUTOMATION_YET: Final = (
    "Installing writes the automation under this agent, lists it in the scheduled job registry "
    "and records it in the audit ledger. Nothing runs until somebody other than the person it "
    "runs as starts it on this tab, and only the outcomes this install can perform can be started."
)

#: What the confirmation says about the paused start, in words for the person installing.
IT_STARTS_PAUSED: Final = (
    "It starts paused. Starting it changes how much this agent does with nobody watching, and "
    "somebody other than you has to approve that, because it runs as you."
)

#: What the confirmation says about the reach, beside the reach itself.
ITS_REACH_IS_YOURS_NARROWED_BY_THIS_AGENT: Final = (
    "It runs as you, reading only, and reaches what you may reach that this agent's ceiling also "
    "allows, and never more. Remove your grants or leave and it reaches nothing."
)


class GalleryError(Exception):
    """A template or an installation was described in a shape that could not be installed."""


class NotConfirmedError(GalleryError):
    """The install carried no confirmation of what would be installed, or a stale one."""


# ------------------------------------------------------------------ the capability
#: Installs an automation onto an agent. Asked in a scope over `install_row`'s three fields.
AUTOMATION_AUTHORITY: Final = Capability(value="admin:automation")

#: The tab the gallery is drawn in, whose read decides who may open it.
GALLERY_TAB: Final = Tab.AUTOMATIONS

#: What a compose change records the installed automation as, and why it was attached. Both
#: in `brain.audit.ledger.FIELD_NAME`'s grammar, so `redact_details` keeps them.
AUTOMATION_PART: Final = "automation"
INSTALL_REASON: Final = "template_install"


# ------------------------------------------------------------------ the templates
#: A template's id. A slug, which is also the shape the ledger keeps as a field name.
TEMPLATE_ID: Final = r"^[a-z][a-z0-9_]{2,63}$"

#: A template's task. Namespaced, so a task somebody registers for one cannot collide with the
#: control task or with anything the queue's driver registers of its own.
TEMPLATE_TASK: Final = r"^automation\.[a-z][a-z0-9_]{2,63}$"

_TEMPLATE_ID_RE: Final = re.compile(TEMPLATE_ID)
_TEMPLATE_TASK_RE: Final = re.compile(TEMPLATE_TASK)
_AUTOMATION_ID_RE: Final = re.compile(AUTOMATION_ID)

#: The longest summary a card carries. One sentence.
MAXIMUM_SUMMARY: Final = 240

#: Hours in a day and days in a week, for the cadence's bounds.
HOURS: Final = 24
WEEKDAYS: Final[tuple[str, ...]] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


class Every(enum.StrEnum):
    """How often a template's automation runs once somebody starts it."""

    DAY = "day"
    WEEKDAY = "weekday"
    WEEK = "week"


@dataclass(frozen=True)
class Cadence:
    """When an automation would run: every day, every weekday, or one day a week, at an hour.

    In UTC and said so in its words, because an install serves people in more than one place and
    an hour with no zone is read in whichever the reader is in. A day of the week is required for
    a weekly cadence and refused for any other, so "every day on Friday" cannot be written.
    """

    every: Every
    hour_utc: int
    #: Monday is nought, as `datetime.weekday` counts. Only for `Every.WEEK`.
    weekday: int | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.hour_utc < HOURS:
            msg = f"{self.hour_utc} is not an hour of the day"
            raise GalleryError(msg)
        if (self.every is Every.WEEK) != (self.weekday is not None):
            msg = "a weekly cadence names its day, and no other cadence names one"
            raise GalleryError(msg)
        if self.weekday is not None and not 0 <= self.weekday < len(WEEKDAYS):
            msg = f"{self.weekday} is not a day of the week"
            raise GalleryError(msg)

    def words(self) -> str:
        """The cadence as a person reads it, with its zone."""
        at = f"at {self.hour_utc:02d}:00 UTC"
        if self.weekday is not None:
            return f"every {WEEKDAYS[self.weekday]} {at}"
        return f"every {self.every.value} {at}"


@dataclass(frozen=True)
class AutomationTemplate:
    """One outcome an agent can take on. See `A_TEMPLATE_HAS_NOWHERE_TO_HOLD_A_GRANT`.

    The name is refused by `agent_automations.outcome_name_refusals` exactly as an automation's
    is, so a template cannot install an automation the automation's own constructor would then
    refuse. `guards` is the registry entry's prose, required at the same length.
    """

    template_id: str
    version: int
    #: The outcome, in the first person. It becomes the installed automation's name.
    name: str
    #: One sentence saying what a person gets from it.
    summary: str
    #: The queue task it runs, once something registers one.
    task: str
    cadence: Cadence
    #: What breaks if it does not run. Becomes the registry entry's `guards`.
    guards: str

    def __post_init__(self) -> None:
        if not _TEMPLATE_ID_RE.fullmatch(self.template_id):
            msg = f"{self.template_id!r} is not a template id"
            raise GalleryError(msg)
        if self.version < 1:
            msg = f"{self.template_id!r} has version {self.version}; versions start at one"
            raise GalleryError(msg)
        refusals = outcome_name_refusals(self.name)
        if refusals:
            msg = f"{self.template_id!r} is named badly: {'; '.join(refusals)}"
            raise GalleryError(msg)
        if not self.summary.strip() or len(self.summary) > MAXIMUM_SUMMARY:
            msg = f"{self.template_id!r} needs a summary of one sentence"
            raise GalleryError(msg)
        if not _TEMPLATE_TASK_RE.fullmatch(self.task):
            msg = f"{self.template_id!r} names {self.task!r}, which is not an automation task"
            raise GalleryError(msg)
        if len(self.guards.strip()) < MINIMUM_GUARDS:
            msg = f"{self.template_id!r} does not say what breaks if it does not run"
            raise GalleryError(msg)


#: The product's own templates. Generic by CLAUDE.md's test: each would be correct on a server
#: belonging to a company nobody here has met. See the module docstring.
BUILT_IN: Final[tuple[AutomationTemplate, ...]] = (
    AutomationTemplate(
        template_id="weekly_work_summary",
        version=1,
        name="I write you a summary of my week's work",
        summary=(
            "What this agent was asked and what it answered over the past week, at the reach "
            "of the person it runs as."
        ),
        task="automation.work_summary",
        cadence=Cadence(every=Every.WEEK, hour_utc=15, weekday=4),
        guards=(
            "Without it the person answerable for this agent learns what it did only by asking, "
            "so a week of wrong answers is found by a complaint rather than by a read."
        ),
    ),
    AutomationTemplate(
        template_id="unanswered_questions",
        version=1,
        name="I list the questions I could not answer this week",
        summary=(
            "Every question this agent answered with nothing, so the gaps in what it draws on "
            "reach somebody who can fill them."
        ),
        task="automation.unanswered_questions",
        cadence=Cadence(every=Every.WEEK, hour_utc=8, weekday=0),
        guards=(
            "Without it a gap in what this agent can draw on is found one disappointed person at "
            "a time and never written down where the owner of that knowledge reads."
        ),
    ),
    AutomationTemplate(
        template_id="source_freshness",
        version=1,
        name="I check each morning that my sources were refreshed",
        summary=(
            "Whether each source this agent draws on has been read recently, so a stale figure "
            "is caught before somebody quotes it."
        ),
        task="automation.source_freshness",
        cadence=Cadence(every=Every.DAY, hour_utc=7),
        guards=(
            "Without it an answer drawn from a source that stopped refreshing reads as current, "
            "and nobody is told the figure is weeks old."
        ),
    ),
    AutomationTemplate(
        template_id="approvals_waiting",
        version=1,
        name="I remind you of approvals still waiting on you",
        summary=(
            "Actions this agent has held for a person to decide that are still undecided, so "
            "the work behind them does not quietly lapse."
        ),
        task="automation.approvals_waiting",
        cadence=Cadence(every=Every.WEEKDAY, hour_utc=9),
        guards=(
            "Without it an action this agent suspended for a decision waits until it lapses, and "
            "the work it was doing simply does not happen."
        ),
    ),
)


def template_by_id(
    template_id: str, catalogue: Sequence[AutomationTemplate] = BUILT_IN
) -> AutomationTemplate | None:
    """One template by its id, or None."""
    for one in catalogue:
        if one.template_id == template_id:
            return one
    return None


# ------------------------------------------------------------------ the gallery
def may_open_gallery(reach: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether this reader may open the gallery: the Automations tab's own read, on both counts."""
    return permitted(tab(GALLERY_TAB).read, reach, now)


@dataclass(frozen=True)
class GalleryCard:
    """One template, and the automation this reader already installed from it on this agent.

    `installed_as` is the reader's own and nobody else's, which is why it can be shown at all: an
    automation from this template running as somebody else is not a fact about this reader, and
    marking the card with it would be a way of asking who else has installed what.
    """

    template: AutomationTemplate
    installed_as: str | None


def gallery(
    installed: Mapping[str, str],
    *,
    catalogue: Sequence[AutomationTemplate] = BUILT_IN,
) -> tuple[GalleryCard, ...]:
    """Every template, ordered by name and then by id, each marked with the reader's own install.

    `installed` maps a template id to the automation this reader installed from it on the agent
    being asked about, and it is read by the store for that reader and that agent only. Nothing
    here filters the catalogue, because a template is not anybody's to be withheld from, so
    there is no count of anything a reader was not shown.
    """
    ordered = sorted(catalogue, key=lambda one: (one.name, one.template_id))
    return tuple(
        GalleryCard(template=one, installed_as=installed.get(one.template_id)) for one in ordered
    )


# ------------------------------------------------------------------ who may install
def install_row(agent_id: str, template: AutomationTemplate, principal_id: str) -> dict[str, str]:
    """The fields an installing grant's scope is matched against.

    The same three `agent_automations._scope_row` gives scheduled work, so a grant written for
    one agent's automations reads the same on the listing and here, and a test holds the two
    equal for the automation an install produces.
    """
    return {"agent_id": agent_id, "task": template.task, "principal_id": principal_id}


def may_install(
    agent_id: str,
    template: AutomationTemplate,
    reach: EntitlementSet,
    now: datetime | None = None,
) -> bool:
    """Whether this reach may install this template onto this agent, running as itself."""
    scope = reach.scope_for(AUTOMATION_AUTHORITY, now)
    if scope is None:
        return False
    return scope.matches(install_row(agent_id, template, reach.principal_id))


# ------------------------------------------------------------------ the preview
@dataclass(frozen=True)
class InstallPreview:
    """Everything a person agrees to before an install. See
    `A_CONFIRMATION_IS_EVIDENCE_OF_WHAT_WAS_SHOWN`."""

    agent_id: str
    template: AutomationTemplate
    #: The installer. See `AN_INSTALLED_AUTOMATION_RUNS_AS_WHOEVER_INSTALLED_IT`.
    runs_as: Principal
    #: `automation_reach` over the installer's reach as an automation is admitted.
    reach: EntitlementSet
    #: Always None. See `AN_INSTALL_CANNOT_BE_THE_WAY_ROUND_A_GATED_SCHEDULE`.
    next_run_at: datetime | None = None

    @property
    def capabilities(self) -> tuple[str, ...]:
        """What the automation would reach, by capability, sorted and without repeats."""
        return tuple(sorted({grant.capability.value for grant in self.reach.grants}))

    @property
    def confirmation(self) -> str:
        """The digest a write must carry. Over every fact the person is shown."""
        shown = {
            "agent_id": self.agent_id,
            "template_id": self.template.template_id,
            "version": self.template.version,
            "name": self.template.name,
            "summary": self.template.summary,
            "task": self.template.task,
            "cadence": self.template.cadence.words(),
            "guards": self.template.guards,
            "runs_as": self.runs_as.id,
            "next_run_at": None if self.next_run_at is None else self.next_run_at.isoformat(),
            "reach": self.reach.ent_hash(),
        }
        encoded = json.dumps(shown, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def preview(
    template: AutomationTemplate,
    agent: AgentRecord,
    *,
    installer: Principal,
    installer_reach: EntitlementSet,
) -> InstallPreview:
    """What installing this template onto this agent would write, as this installer.

    The reach is the installer's as an automation is admitted, `AUTOMATION_CHANNEL` at
    `AUTOMATION_ASSURANCE`, which is what `brain.ops.automation_owner.owner_reach` holds a call
    to, narrowed by the agent's ceiling through `automation_reach`. There is no arithmetic here:
    `brain.console.workspace.intersections_in` is run over this module's source by its test.

    A reach resolved for somebody other than the installer is a wiring fault and raises, because
    answering it would show one person a reach computed from another's grants.
    """
    if installer_reach.principal_id != installer.id:
        msg = (
            f"a preview for {installer.id!r} was handed the reach of "
            f"{installer_reach.principal_id!r}"
        )
        raise GalleryError(msg)
    admitted = admit(installer_reach, AUTOMATION_CHANNEL, AUTOMATION_ASSURANCE)
    return InstallPreview(
        agent_id=agent.agent_id,
        template=template,
        runs_as=installer,
        reach=automation_reach(admitted, agent),
    )


# ------------------------------------------------------------------ the install
def new_automation_id() -> str:
    """A fresh automation id, in the grammar a credential can carry and the ledger keeps."""
    return f"auto_{uuid.uuid4().hex}"


@dataclass(frozen=True)
class Installation:
    """An installed automation and its registry entry, as one value.

    See the module docstring on why this is not a `SchedulerChange`. Four refusals, each a shape
    in which the two halves or the install's own rules have come apart.
    """

    automation: Automation
    entry: RegistryEntry
    template_id: str
    template_version: int
    installed_by: str

    def __post_init__(self) -> None:
        gaps = registry_gaps([self.automation], [self.entry])
        if gaps:
            msg = f"the registry entry does not describe the automation: {'; '.join(gaps)}"
            raise GalleryError(msg)
        if (self.entry.agent_id, self.entry.task) != (
            self.automation.agent_id,
            self.automation.task,
        ):
            msg = (
                f"the registry entry for {self.automation.automation_id!r} names another agent "
                "or another task, so a reviewer reading the registry is reading about something "
                "else"
            )
            raise GalleryError(msg)
        if self.automation.runs_as.id != self.installed_by:
            msg = (
                f"{self.automation.automation_id!r} runs as {self.automation.runs_as.id!r} and "
                f"was installed by {self.installed_by!r}. "
                f"{AN_INSTALLED_AUTOMATION_RUNS_AS_WHOEVER_INSTALLED_IT}"
            )
            raise GalleryError(msg)
        if self.automation.next_run_at is not None:
            msg = (
                f"{self.automation.automation_id!r} is installed with a next run. "
                f"{AN_INSTALL_CANNOT_BE_THE_WAY_ROUND_A_GATED_SCHEDULE}"
            )
            raise GalleryError(msg)


def install(shown: InstallPreview, *, confirmation: str, automation_id: str) -> Installation:
    """The installation a confirmed request writes, or `NotConfirmedError`.

    `shown` is the preview recomputed by the server at the moment of the write, never one the
    client sent, so the comparison is between what the person agreed to and what is true now.
    Compared in constant time, which buys nothing against a digest that is not a secret and costs
    nothing either, and it keeps a reader from wondering whether it should.
    """
    if not secrets.compare_digest(confirmation, shown.confirmation):
        msg = (
            f"the install of {shown.template.template_id!r} onto {shown.agent_id!r} did not "
            "confirm what would be installed now. "
            f"{A_CONFIRMATION_IS_EVIDENCE_OF_WHAT_WAS_SHOWN}"
        )
        raise NotConfirmedError(msg)
    if not _AUTOMATION_ID_RE.fullmatch(automation_id):
        msg = f"{automation_id!r} is not an id an automation can carry"
        raise GalleryError(msg)
    automation = Automation(
        automation_id=automation_id,
        agent_id=shown.agent_id,
        name=shown.template.name,
        runs_as=shown.runs_as,
        task=shown.template.task,
        next_run_at=shown.next_run_at,
    )
    return Installation(
        automation=automation,
        entry=register(automation, guards=shown.template.guards),
        template_id=shown.template.template_id,
        template_version=shown.template.version,
        installed_by=shown.runs_as.id,
    )
