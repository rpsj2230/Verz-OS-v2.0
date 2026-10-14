"""Starting a new automation on an agent: from a named outcome or from words, never a canvas.

`brain.console.automation_gallery` installs one of the product's own templates exactly as it is. A
person who wants the same outcome at another hour, on another trigger, or only when something is
true, or who wants something no template says, had no way in. This is the way in, and it is shaped
by the rule the gallery already carries: **what a person configures is which outcome they want and
when it should happen, and the wiring is not theirs to assemble.** There is no step list here and
nowhere to put one.

**Three things are chosen and one is written.** The trigger is one of the three
`brain.orchestration.unattended.TriggerKind` members, so "what can run without a person" still has
a readable answer; the condition is at most one comparison from a short named list; the tools are
named from what the agent may already use; and the instruction is prose for the agent. A template,
when one is the start, supplies the name, the cadence, the sentence about what breaks and the task,
and the person changes what they want changed. See `A_NEW_AUTOMATION_IS_FOUR_CHOICES_AND_NO_WIRING`.

**A condition is one comparison and never an expression.** The owner decided this on 2026-10-12
(needs-rupash 177, option A) and the shape is what makes it safe rather than only simple. The field
is one a connected source reports, offered from that connector's own projected fields, and the
comparisons a field may take depend on its shape: a status or an identifier is equal to something, a
label is equal to something or contains it, and a timestamp is more than, less than or within some
days of now. A condition has nowhere to hold a function, a second clause or a field the connector
does not report, and `ConditionOp` is the closed list the migration's check admits and no other.
Free expressions were rejected for the reason the question gave: an expression is code, and code
in a condition is a way to reach data the person's grants do not allow. See
`A_CONDITION_IS_ONE_COMPARISON_FROM_A_NAMED_LIST`.

**A condition is decided from facts the run is handed and never from a stored answer.** `holds`
takes the field's reported value and the instant and says holds, does not hold or cannot tell, and
cannot tell is what a missing or unreadable value gives, not a quiet yes. Where the facts come from
at a run is the run's own: a connector reads them live at the owner's reach, which is what the
rule about connectors never bulk-syncing asks, so nothing here keeps a copy of what a source said.

**The instruction is the agent's, within its ceiling and the person's reach.** What it may use is
named, and every name must be one the agent's own ceiling already allows, so an instruction that
names a tool the agent may not use is refused in words before anything is written. Naming a tool
grants nothing, because the run is still `E(owner) ∩ agent_ceiling`, resolved at the run; and
anything the agent would write waits for a person as every agent write does, which is
`brain.gate.runtime.RUNTIME_WRITES_ALWAYS_WAIT_FOR_A_PERSON` and is imported here only to be said on
the card. See `AN_INSTRUCTION_IS_THE_AGENTS_AND_NEVER_A_GRANT`.

**A person who writes it runs it, and starts paused.** Both rules are the gallery's, for its
reasons: the installer is the principal (`AN_INSTALLED_AUTOMATION_RUNS_AS_WHOEVER_INSTALLED_IT`) and
going from nothing to an automation at a cadence is a schedule change somebody else approves
(`AN_INSTALL_CANNOT_BE_THE_WAY_ROUND_A_GATED_SCHEDULE`). `Authoring` builds the same `Automation`
and the same registry entry, and `brain.console.automation_gallery.Installation` refuses the same
shapes. Rejected: a second construction path that skipped the paused start because the person
wrote the words themselves. Writing the instruction is not the approval that rule asks for.

**A rehearsal is the preview and it writes and sends nothing.** The leaf asks that a new automation
be rehearsed before it is switched on, showing what it would have done at its owner's reach for the
last few triggers. The rehearsal here is part of the confirmation a person reads before the
automation exists at all, so it is before every switch by construction and there is no state in
which an authored automation is on and unrehearsed. It replays the last few slots the cadence would
have fired, and for each says what the agent would have been told, which tools it could have used,
what the condition said, and that nothing was written or sent. It makes no model call and reads no
record: a rehearsal that read live data would be a run, and a run is what the person has not agreed
to yet. A condition it cannot decide without a live read says so. See
`A_REHEARSAL_WRITES_AND_SENDS_NOTHING`. A trigger that is not a schedule has no earlier triggers to
replay on this install, and the rehearsal says that instead of inventing them.

**What a trigger of each kind does is said on the card.** A schedule runs when the worker's cadence
says. A connector event runs when the connected source's index reports a changed record, once the
install has switched `automation_events` on, and says so until then. **A webhook is refused when it
is written**, in `WEBHOOKS_ARE_NOT_OFFERED`' words, and the form lists it as not offered: the owner
decided on 2026-10-13 (needs-rupash 223, option B) that nothing starts work from outside the
install. A webhook stored before that decision still reads back and says it cannot be started. A
control that looks live and reaches nothing is the defect this repository keeps finding. See
`A_TRIGGER_NOTHING_FIRES_IS_SAID_TO_BE_ONE`.

**The confirmation covers the terms, not the rehearsal.** The digest is over everything the person
agrees to: the name, the instruction, the trigger, the condition, the tools, who it runs as, the
reach and that it starts paused. The rehearsal is what would have happened and changes with the
clock, so a digest over it would go stale every hour and refuse a person who had done nothing
wrong.

Task ids: M39.9.2.1, M39.9.2.2, M39.9.2.3, M39.9.2.4, M17.4.1, M17.4.2
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol

from brain.agents.model import AgentRecord
from brain.connectors.manifest import FieldShape
from brain.console.agent_automations import (
    MINIMUM_GUARDS,
    Automation,
    RegistryEntry,
    automation_reach,
    outcome_name_refusals,
    register,
)
from brain.console.automation_gallery import (
    AUTOMATION_AUTHORITY,
    TEMPLATE_TASK,
    AutomationTemplate,
    Cadence,
    Every,
    GalleryError,
    Installation,
    NotConfirmedError,
    may_open_gallery,
    template_by_id,
)
from brain.core.entitlement import EntitlementSet
from brain.core.principal import Principal
from brain.gate.admission import admit
from brain.gate.runtime import RUNTIME_WRITES_ALWAYS_WAIT_FOR_A_PERSON
from brain.ops.automation_event import STARTABLE_KINDS, WEBHOOKS_ARE_NOT_OFFERED
from brain.ops.automation_owner import AUTOMATION_ASSURANCE, AUTOMATION_CHANNEL
from brain.ops.automation_run import INSTRUCTION_TASK, slots_before
from brain.orchestration.unattended import TriggerKind

# ------------------------------------------------------------------ written-down reasons
#: Why a new automation has no canvas.
A_NEW_AUTOMATION_IS_FOUR_CHOICES_AND_NO_WIRING: Final = (
    "A person starting an automation chooses when it runs, whether something must be true, what "
    "the agent may use and what it is told to do. There is no step list, no graph and no "
    "expression to assemble, so what runs unattended can still be read off one closed list of "
    "triggers and one named list of conditions."
)

#: Why a condition is one comparison from a list.
A_CONDITION_IS_ONE_COMPARISON_FROM_A_NAMED_LIST: Final = (
    "A condition compares one field a connected source reports with one value, by equals, is over, "
    "is under, contains or is within some days of now, chosen from lists. It holds no expression, "
    "so it cannot be a way to reach data the person's grants do not allow, and it is shown on the "
    "card in words."
)

#: Why naming a tool is not granting one.
AN_INSTRUCTION_IS_THE_AGENTS_AND_NEVER_A_GRANT: Final = (
    "The tools an automation names must already be allowed by the agent's own ceiling, and naming "
    "one grants nothing: each run is the owner's reach at that moment narrowed by the agent, and "
    "anything it would write waits for a person."
)

#: Why a rehearsal is part of the confirmation and reads nothing.
A_REHEARSAL_WRITES_AND_SENDS_NOTHING: Final = (
    "A rehearsal shows what the automation would have been told at the last few times it would "
    "have fired, at its owner's reach. It makes no model call, reads no record, writes nothing "
    "and sends nothing, because a rehearsal that did any of those would be a run."
)

#: Why a trigger nothing fires is said to be one.
A_TRIGGER_NOTHING_FIRES_IS_SAID_TO_BE_ONE: Final = (
    "A trigger that nothing on this install fires is said to be one and its automation cannot be "
    "started, so no control looks live and reaches nothing. A change fires only while the install "
    "has switched it on, and a webhook is never fired."
)

# ------------------------------------------------------------------ the figures
#: The placeholder template id an authored automation carries. `0219` and
#: `brain.tables.agent_automation.AUTHORED_TEMPLATE` hold the same word, held equal by a test.
AUTHORED_TEMPLATE: Final = "authored"

#: The task an automation written in words runs. Namespaced as every template task is, and declared
#: in `brain.ops.automation_run.TASKS` as the instruction run, which says what it still needs.
AUTHORED_TASK: Final = INSTRUCTION_TASK

#: How long an instruction may be and how short. Below the minimum it is a label, and above the
#: maximum it is a document: a prompt of that size is configuration of the agent, not an errand.
MINIMUM_INSTRUCTION: Final = 12
MAXIMUM_INSTRUCTION: Final = 2000

#: How many tools one automation may name. Bounded so the card stays readable and the list a run
#: intersects stays short.
MAXIMUM_TOOLS: Final = 12

#: How many earlier triggers a rehearsal replays.
REHEARSED_TRIGGERS: Final = 3

#: The longest span of days a timestamp comparison may name: ten years.
MAXIMUM_DAYS: Final = 3650

#: A comparison's value, when it is text.
MAXIMUM_VALUE: Final = 200

#: A connector or an endpoint name: the product's object grammar, which a condition field also uses.
_NAME_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

#: One field a source reports, as `connector.entity.field`.
FIELD_KEY: Final = r"^[a-z][a-z0-9_]{0,62}\.[a-z][a-z0-9_]{0,62}\.[a-z][a-z0-9_]{0,62}$"
_FIELD_KEY_RE: Final = re.compile(FIELD_KEY)

#: What a rehearsal says the run would have been unable to do. Said once, and the same every time.
NOTHING_WAS_WRITTEN_OR_SENT: Final = (
    "Nothing was read, written or sent, and anything it wanted to change would have waited for a "
    "person to decide."
)

#: What the card says about writes, which is the runtime's own rule in its own words.
WRITES_WAIT_FOR_A_PERSON: Final = RUNTIME_WRITES_ALWAYS_WAIT_FOR_A_PERSON

#: What the card says about a trigger nothing fires.
NOTHING_FIRES_THIS_YET: Final = (
    "Nothing on this install starts work from outside it, so this kind of trigger is shown and "
    "cannot be started."
)

#: What the card says about a change trigger while the install has not switched changes on.
EVENTS_ARE_OFF: Final = (
    "Starting an automation when a source changes is switched off on this install, so it is saved "
    "and cannot be started until an administrator switches it on."
)

#: What the card says about starting.
IT_STARTS_PAUSED: Final = (
    "It starts paused. Starting it changes how much this agent does with nobody watching, and "
    "somebody other than you has to approve that, because it runs as you."
)


class AuthoringRefusedError(GalleryError):
    """What a person wrote cannot become an automation. Carries every finding, in words."""

    def __init__(self, findings: Sequence[str]) -> None:
        self.findings: tuple[str, ...] = tuple(findings)
        super().__init__("; ".join(self.findings))


# ------------------------------------------------------------------ the condition
class ConditionOp(enum.StrEnum):
    """The five comparisons a condition may make, and no other (needs-rupash 177, option A)."""

    EQUALS = "equals"
    #: A timestamp more than this many days ago, which is how "more than seven days overdue" reads.
    IS_OVER = "is_over"
    #: A timestamp less than this many days ago.
    IS_UNDER = "is_under"
    CONTAINS = "contains"
    #: A timestamp within this many days of now, either side.
    WITHIN_DAYS = "within_days"


#: Which comparisons each shape of field may take. A status, an identifier or a join key is equal
#: to something and nothing else; a label is also searched; a timestamp is measured in days. A
#: shape not here takes none, and `ops_for` says so rather than offering a comparison that means
#: nothing for it.
OPS_FOR_SHAPE: Final[Mapping[FieldShape, tuple[ConditionOp, ...]]] = {
    FieldShape.STATUS: (ConditionOp.EQUALS,),
    FieldShape.IDENTIFIER: (ConditionOp.EQUALS,),
    FieldShape.JOIN_KEY: (ConditionOp.EQUALS,),
    FieldShape.LABEL: (ConditionOp.EQUALS, ConditionOp.CONTAINS),
    FieldShape.TIMESTAMP: (
        ConditionOp.IS_OVER,
        ConditionOp.IS_UNDER,
        ConditionOp.WITHIN_DAYS,
    ),
}

#: The comparisons measured in whole days.
DAY_OPS: Final[frozenset[ConditionOp]] = frozenset(
    {ConditionOp.IS_OVER, ConditionOp.IS_UNDER, ConditionOp.WITHIN_DAYS}
)


def ops_for(shape: FieldShape) -> tuple[ConditionOp, ...]:
    """The comparisons a field of this shape may take, in the order a form lists them."""
    return OPS_FOR_SHAPE.get(shape, ())


def field_label(key: str) -> str:
    """A field key as a person reads it: `invoice due date (xero)` for `xero.invoice.due_date`.

    Computed from the key alone so a card can say a stored condition in words without asking the
    connector registry, which a card is not always able to reach.
    """
    connector, entity, name = key.split(".")
    return f"{entity} {name}".replace("_", " ") + f" ({connector.replace('_', ' ')})"


@dataclass(frozen=True)
class ConditionField:
    """One field a connected source reports, as the form offers it.

    The connector and the entity are in the key so that two sources reporting a field of the same
    name are two choices, and a condition names exactly one of them.
    """

    connector: str
    entity: str
    name: str
    shape: FieldShape

    def __post_init__(self) -> None:
        for label, value in (
            ("connector", self.connector),
            ("entity", self.entity),
            ("name", self.name),
        ):
            if not _NAME_RE.fullmatch(value):
                msg = f"a condition field's {label} {value!r} is not a name"
                raise GalleryError(msg)

    @property
    def key(self) -> str:
        return f"{self.connector}.{self.entity}.{self.name}"

    @property
    def label(self) -> str:
        """The field as a person reads it: the entity and the field, and which source."""
        return field_label(self.key)

    @property
    def ops(self) -> tuple[ConditionOp, ...]:
        return ops_for(self.shape)


class Verdict(enum.StrEnum):
    """What a condition said about one fact."""

    HOLDS = "holds"
    DOES_NOT_HOLD = "does_not_hold"
    #: The fact was missing or could not be read as the field's shape. Never read as a yes.
    CANNOT_TELL = "cannot_tell"


def _as_instant(fact: object) -> datetime | None:
    """A fact as an aware instant, or None when it is not one."""
    if isinstance(fact, datetime):
        return fact if fact.tzinfo is not None else None
    if isinstance(fact, str):
        try:
            parsed = datetime.fromisoformat(fact)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None
    return None


@dataclass(frozen=True)
class Condition:
    """One comparison of a reported field against one value. See
    `A_CONDITION_IS_ONE_COMPARISON_FROM_A_NAMED_LIST`.

    `value` is text for every operation, and a whole number of days for the three that measure
    days, which `__post_init__` checks so that a row read back cannot carry a comparison its own
    words could not say.
    """

    field: str
    op: ConditionOp
    value: str

    def __post_init__(self) -> None:
        if not _FIELD_KEY_RE.fullmatch(self.field):
            msg = f"{self.field!r} is not a field a source reports"
            raise GalleryError(msg)
        text = self.value.strip()
        if not text or len(text) > MAXIMUM_VALUE:
            msg = (
                f"a condition on {self.field!r} needs a value of one to {MAXIMUM_VALUE} characters"
            )
            raise GalleryError(msg)
        if self.op in DAY_OPS and not (text.isdigit() and 1 <= int(text) <= MAXIMUM_DAYS):
            msg = f"{self.op.value} measures whole days, from one to {MAXIMUM_DAYS}"
            raise GalleryError(msg)

    def days(self) -> int:
        """The number of days a day-measured comparison names."""
        return int(self.value.strip())

    def holds(self, fact: object | None, *, now: datetime) -> Verdict:
        """Whether the reported fact satisfies this comparison at `now`.

        A missing fact, and a timestamp that is not a timestamp, cannot be told, so a run that
        cannot read the field does not go ahead on a guess. Text is compared without case, because
        a status a source capitalises differently is the same status.
        """
        if fact is None:
            return Verdict.CANNOT_TELL
        if self.op in DAY_OPS:
            seen = _as_instant(fact)
            if seen is None:
                return Verdict.CANNOT_TELL
            span = timedelta(days=self.days())
            age = now - seen
            match self.op:
                case ConditionOp.IS_OVER:
                    held = age > span
                case ConditionOp.IS_UNDER:
                    held = timedelta(0) <= age < span
                case _:
                    held = abs(age) <= span
            return Verdict.HOLDS if held else Verdict.DOES_NOT_HOLD
        if not isinstance(fact, str):
            return Verdict.CANNOT_TELL
        seen_text, wanted = fact.strip().casefold(), self.value.strip().casefold()
        held = wanted in seen_text if self.op is ConditionOp.CONTAINS else seen_text == wanted
        return Verdict.HOLDS if held else Verdict.DOES_NOT_HOLD

    def words(self, label: str | None = None) -> str:
        """The condition as the card says it, the field read as `label` or as its key."""
        label = field_label(self.field) if label is None else label
        value = self.value.strip()
        match self.op:
            case ConditionOp.EQUALS:
                return f"only when the {label} is {value}"
            case ConditionOp.CONTAINS:
                return f"only when the {label} contains {value}"
            case ConditionOp.IS_OVER:
                return f"only when the {label} is more than {value} days ago"
            case ConditionOp.IS_UNDER:
                return f"only when the {label} is less than {value} days ago"
            case ConditionOp.WITHIN_DAYS:
                return f"only when the {label} is within {value} days of now"


def condition_gaps(condition: Condition, offered: Mapping[str, ConditionField]) -> tuple[str, ...]:
    """Everything wrong with a condition against the fields this agent's sources report."""
    found = offered.get(condition.field)
    if found is None:
        return (
            "That condition names a field none of this install's connected sources reports, so "
            "nothing could ever tell whether it holds. Choose one from the list.",
        )
    if condition.op not in found.ops:
        allowed = ", ".join(op.value.replace("_", " ") for op in found.ops) or "nothing"
        return (f"{found.label} cannot be compared that way. It may be compared by: {allowed}.",)
    return ()


# ------------------------------------------------------------------ the trigger
@dataclass(frozen=True)
class TriggerChoice:
    """When a new automation runs: one of the three kinds, and the one fact that kind needs.

    A schedule carries its cadence and nothing else, and a connector event or a webhook carries
    the source it listens to and nothing else, which is `brain.orchestration.unattended.Trigger`'s
    rule held here as well so a person cannot save a trigger whose spare field reads on a screen as
    applying and is never consulted.
    """

    kind: TriggerKind
    cadence: Cadence | None = None
    source: str = ""

    def __post_init__(self) -> None:
        is_schedule = self.kind is TriggerKind.SCHEDULE
        if is_schedule and self.cadence is None:
            msg = "a schedule needs a cadence, or nothing decides when it runs"
            raise GalleryError(msg)
        if not is_schedule and self.cadence is not None:
            msg = (
                f"a {self.kind.value.replace('_', ' ')} has no cadence, and one would never be read"
            )
            raise GalleryError(msg)
        if is_schedule and self.source.strip():
            msg = "a schedule names no source"
            raise GalleryError(msg)
        if not is_schedule and not _NAME_RE.fullmatch(self.source):
            what = "connector" if self.kind is TriggerKind.CONNECTOR_EVENT else "endpoint"
            msg = f"a {self.kind.value.replace('_', ' ')} needs a {what} name"
            raise GalleryError(msg)

    @property
    def fires(self) -> bool:
        """Whether this kind of trigger can start anything: a schedule, or a change. Not a webhook.

        Whether the install has switched changes on is configuration, so it is asked by the route,
        which reads the switch, and not here.
        """
        return self.kind in STARTABLE_KINDS

    def words(self) -> str:
        """The trigger as the card says it."""
        match self.kind:
            case TriggerKind.SCHEDULE:
                assert self.cadence is not None  # `__post_init__` refuses a schedule without one
                return f"Runs {self.cadence.words()}"
            case TriggerKind.CONNECTOR_EVENT:
                return f"Runs when something changes in {self.source.replace('_', ' ')}"
            case TriggerKind.WEBHOOK:
                return f"Runs when {self.source.replace('_', ' ')} is called from outside"


# ------------------------------------------------------------------ what a person wrote
@dataclass(frozen=True)
class Authored:
    """One automation as a person wrote it, before it has an id or an owner.

    `template_id` is the template it started from, or None when it started from words. `task` is
    the template's when there is one and `AUTHORED_TASK` otherwise, so the scheduler's registry
    names a task whichever way it began.
    """

    name: str
    instruction: str
    guards: str
    trigger: TriggerChoice
    tools: tuple[str, ...]
    condition: Condition | None = None
    template_id: str | None = None
    task: str = AUTHORED_TASK

    def __post_init__(self) -> None:
        findings = list(outcome_name_refusals(self.name))
        text = self.instruction.strip()
        if not MINIMUM_INSTRUCTION <= len(text) <= MAXIMUM_INSTRUCTION:
            findings.append(
                f"The instruction needs between {MINIMUM_INSTRUCTION} and {MAXIMUM_INSTRUCTION} "
                "characters: enough to say what to do, and short enough to be an errand."
            )
        if len(self.guards.strip()) < MINIMUM_GUARDS:
            findings.append("Say what goes wrong if this does not run, in a full sentence.")
        if not re.fullmatch(TEMPLATE_TASK, self.task):
            findings.append("The task is not one an automation can run.")
        if len(self.tools) > MAXIMUM_TOOLS or len(set(self.tools)) != len(self.tools):
            findings.append(f"Name at most {MAXIMUM_TOOLS} tools, each once.")
        if findings:
            raise AuthoringRefusedError(findings)

    @property
    def instruction_text(self) -> str:
        return self.instruction.strip()


def tool_gaps(tools: Sequence[str], agent: AgentRecord) -> tuple[str, ...]:
    """Every tool named that this agent's ceiling does not allow. See
    `AN_INSTRUCTION_IS_THE_AGENTS_AND_NEVER_A_GRANT`.

    A tool is named, not described, and the refusal names the tool the person themselves wrote, so
    it discloses nothing they did not already have.
    """
    allowed = agent.authority.allowed_tools
    return tuple(
        f"This agent may not use {tool}, so an automation of it cannot name that."
        for tool in sorted(set(tools))
        if tool not in allowed
    )


def compose(
    *,
    agent: AgentRecord,
    name: str,
    instruction: str,
    guards: str,
    trigger: TriggerChoice,
    tools: Sequence[str],
    condition: Condition | None,
    fields: Mapping[str, ConditionField],
    template: AutomationTemplate | None = None,
) -> Authored:
    """What a person wrote, checked against this agent and this install, or every reason it is not.

    The findings are gathered rather than raised one at a time, because a person editing a form
    wants all of what is wrong at once, and the three checks that depend on the agent and the
    install (the tools, the condition's field and the template's task) run beside the ones the
    value checks itself.
    """
    findings: list[str] = []
    if trigger.kind is TriggerKind.WEBHOOK:
        findings.append(WEBHOOKS_ARE_NOT_OFFERED)
    bound = agent.authority.connectors
    if trigger.kind is TriggerKind.CONNECTOR_EVENT and trigger.source not in bound:
        findings.append(
            "This agent is not bound to that source, so a change in it could never be read by a "
            "run of this automation."
        )
    findings.extend(tool_gaps(tools, agent))
    if condition is not None:
        findings.extend(condition_gaps(condition, fields))
    try:
        built = Authored(
            name=name,
            instruction=instruction,
            guards=guards,
            trigger=trigger,
            tools=tuple(tools),
            condition=condition,
            template_id=None if template is None else template.template_id,
            task=AUTHORED_TASK if template is None else template.task,
        )
    except AuthoringRefusedError as exc:
        findings.extend(exc.findings)
        raise AuthoringRefusedError(findings) from exc
    if findings:
        raise AuthoringRefusedError(findings)
    return built


# ------------------------------------------------------------------ the rehearsal
@dataclass(frozen=True)
class RehearsedTrigger:
    """One earlier trigger, and what the automation would have done at it."""

    #: When the trigger would have fired, or None for a kind with no history here.
    at: datetime | None
    #: What the condition said, or None when there is none.
    verdict: Verdict | None
    #: What would have happened, in a sentence.
    says: str


def rehearse(
    authored: Authored,
    *,
    reach_words: Sequence[str],
    now: datetime,
    facts: Mapping[str, object] | None = None,
    fields: Mapping[str, ConditionField] | None = None,
) -> tuple[RehearsedTrigger, ...]:
    """What this automation would have done at its last few triggers, writing and sending nothing.

    See `A_REHEARSAL_WRITES_AND_SENDS_NOTHING`. `reach_words` is the capability list the preview
    already shows the person, so the rehearsal names nothing the confirmation does not. `facts`
    is what a caller already holds about the condition's field, keyed by field key; a rehearsal
    never fetches any, so without one the condition cannot be told, and says that.
    """
    told = f"It would have been told: {authored.instruction_text}"
    tools = (
        f"It could have used {', '.join(authored.tools)}."
        if authored.tools
        else "It could have used no tools, only what it already knows."
    )
    reach = (
        f"It would have read at your reach through this agent: {', '.join(reach_words)}."
        if reach_words
        else "Your access and this agent's ceiling have no read in common, so it would have "
        "reached nothing."
    )
    cadence = authored.trigger.cadence
    if cadence is None:
        return (
            RehearsedTrigger(
                at=None,
                verdict=None,
                says=(
                    f"{authored.trigger.words()}, and this install has no earlier triggers of "
                    "that kind to replay. Nothing was read, written or sent."
                ),
            ),
        )
    lines: list[RehearsedTrigger] = []
    for slot in slots_before(cadence, now, REHEARSED_TRIGGERS):
        verdict: Verdict | None = None
        condition_said = ""
        if authored.condition is not None:
            label = (
                fields[authored.condition.field].label
                if fields is not None and authored.condition.field in fields
                else authored.condition.field
            )
            fact = None if facts is None else facts.get(authored.condition.field)
            verdict = authored.condition.holds(fact, now=slot)
            condition_said = {
                Verdict.HOLDS: f"The condition held ({authored.condition.words(label)}). ",
                Verdict.DOES_NOT_HOLD: (
                    f"The condition did not hold ({authored.condition.words(label)}), so it "
                    "would not have run. "
                ),
                Verdict.CANNOT_TELL: (
                    f"Whether the condition held ({authored.condition.words(label)}) cannot be "
                    "told without reading a live record, which a rehearsal does not do. "
                ),
            }[verdict]
        acted = verdict is not Verdict.DOES_NOT_HOLD
        body = f"{told}. {tools} {reach} " if acted else ""
        lines.append(
            RehearsedTrigger(
                at=slot,
                verdict=verdict,
                says=f"{condition_said}{body}{NOTHING_WAS_WRITTEN_OR_SENT}".strip(),
            )
        )
    return tuple(lines)


# ------------------------------------------------------------------ the preview
@dataclass(frozen=True)
class AuthoringPreview:
    """Everything a person agrees to before a new automation exists. See the module docstring on
    why the digest leaves the rehearsal out."""

    agent_id: str
    authored: Authored
    runs_as: Principal
    #: `automation_reach` over the author's reach as an automation is admitted.
    reach: EntitlementSet
    #: Always None: it starts paused. See `IT_STARTS_PAUSED`.
    next_run_at: datetime | None = None

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(sorted({grant.capability.value for grant in self.reach.grants}))

    @property
    def confirmation(self) -> str:
        """The digest a write must carry: over every term the person is shown."""
        one = self.authored
        shown = {
            "agent_id": self.agent_id,
            "template_id": one.template_id,
            "name": one.name,
            "instruction": one.instruction_text,
            "guards": one.guards.strip(),
            "task": one.task,
            "trigger": one.trigger.kind.value,
            "cadence": None if one.trigger.cadence is None else one.trigger.cadence.words(),
            "source": one.trigger.source,
            "condition": None
            if one.condition is None
            else [one.condition.field, one.condition.op.value, one.condition.value.strip()],
            "tools": sorted(one.tools),
            "runs_as": self.runs_as.id,
            "next_run_at": None if self.next_run_at is None else self.next_run_at.isoformat(),
            "reach": self.reach.ent_hash(),
        }
        encoded = json.dumps(shown, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def preview(
    authored: Authored,
    agent: AgentRecord,
    *,
    author: Principal,
    author_reach: EntitlementSet,
) -> AuthoringPreview:
    """What writing this automation onto this agent would store, as this author.

    The reach is the author's as an automation is admitted, narrowed by the agent's ceiling through
    `automation_reach`, which is `brain.ops.automation.flow_reach`. There is no arithmetic here:
    `brain.console.workspace.intersections_in` is run over this module's source by its test. A
    reach resolved for somebody other than the author is a wiring fault and raises.
    """
    if author_reach.principal_id != author.id:
        msg = f"a preview for {author.id!r} was handed the reach of {author_reach.principal_id!r}"
        raise GalleryError(msg)
    admitted = admit(author_reach, AUTOMATION_CHANNEL, AUTOMATION_ASSURANCE)
    return AuthoringPreview(
        agent_id=agent.agent_id,
        authored=authored,
        runs_as=author,
        reach=automation_reach(admitted, agent),
    )


# ------------------------------------------------------------------ the write
@dataclass(frozen=True)
class Authoring:
    """A written automation and its registry entry, as one value, plus what the person wrote.

    The same two halves `brain.console.automation_gallery.Installation` holds, because the store
    writes the same row and the registry must describe the same automation. `installation` is that
    value, built with the placeholder template, so every refusal it makes (the registry entry
    describing the automation, the owner being the author, no next run) is made here too.
    """

    installation: Installation
    authored: Authored


def authoring_of(shown: AuthoringPreview, *, confirmation: str, automation_id: str) -> Authoring:
    """The automation a confirmed request writes, or `NotConfirmedError`.

    `shown` is the preview recomputed by the server at the moment of the write, never one the
    client sent, so the comparison is between what the person agreed to and what is true now.
    """
    if not secrets.compare_digest(confirmation, shown.confirmation):
        msg = (
            f"the new automation on {shown.agent_id!r} did not confirm what would be written now. "
            "A grant, the agent's ceiling or what was written changed since it was shown."
        )
        raise NotConfirmedError(msg)
    one = shown.authored
    automation = Automation(
        automation_id=automation_id,
        agent_id=shown.agent_id,
        name=one.name,
        runs_as=shown.runs_as,
        task=one.task,
        next_run_at=None,
    )
    entry: RegistryEntry = register(automation, guards=one.guards.strip())
    return Authoring(
        installation=Installation(
            automation=automation,
            entry=entry,
            template_id=AUTHORED_TEMPLATE,
            template_version=1,
            installed_by=shown.runs_as.id,
        ),
        authored=one,
    )


# ------------------------------------------------------------------ who may
def may_author(
    agent_id: str, task: str, reach: EntitlementSet, now: datetime | None = None
) -> bool:
    """Whether this reader may write an automation onto this agent, running as themselves.

    The Automations tab's own read, on both counts, and `AUTOMATION_AUTHORITY` in a scope over the
    agent, the task and the person, which is the same question the gallery asks of a template and
    is asked of the task the automation would have.
    """
    if not may_open_gallery(reach, now):
        return False
    scope = reach.scope_for(AUTOMATION_AUTHORITY, now)
    if scope is None:
        return False
    return scope.matches({"agent_id": agent_id, "task": task, "principal_id": reach.principal_id})


# ------------------------------------------------------------------ from a template
def template_for(template_id: str | None) -> AutomationTemplate | None:
    """The product's template a person started from, or None when they started from words."""
    return None if template_id is None else template_by_id(template_id)


def default_cadence(template: AutomationTemplate | None) -> Cadence:
    """The cadence a form starts with: the template's, or a weekday morning for words."""
    return Cadence(every=Every.WEEKDAY, hour_utc=9) if template is None else template.cadence


# ------------------------------------------------------------------ reading one back
class AuthoredColumns(Protocol):
    """The columns of `agent.automation` an authored row is read from. The ORM row satisfies it."""

    template_id: str
    name: str
    guards: str
    task: str
    trigger_kind: str | None
    trigger_source: str | None
    cadence_every: str | None
    cadence_hour: int | None
    cadence_weekday: int | None
    condition_field: str | None
    condition_op: str | None
    condition_value: str | None
    instruction: str | None
    tools: list[str] | None
    from_template_id: str | None


def authored_from_row(row: AuthoredColumns) -> Authored | None:
    """What a stored row says a person wrote, or None for a row installed from a template.

    Reads the columns through the same constructors a person's words go through, so a row whose
    columns could not have come from the form (a hand edit, a migration gone wrong) is refused
    here with `GalleryError` or `AuthoringRefusedError` rather than drawn as if it were sound. The
    database's own checks make that unreachable for a row written through the application, and
    this is the second place it is held, because the first is a different language.
    """
    if row.template_id != AUTHORED_TEMPLATE:
        return None
    cadence = (
        None
        if row.cadence_every is None
        else Cadence(
            every=Every(row.cadence_every),
            hour_utc=0 if row.cadence_hour is None else row.cadence_hour,
            weekday=row.cadence_weekday,
        )
    )
    condition = (
        None
        if row.condition_field is None or row.condition_op is None or row.condition_value is None
        else Condition(
            field=row.condition_field,
            op=ConditionOp(row.condition_op),
            value=row.condition_value,
        )
    )
    return Authored(
        name=row.name,
        instruction=row.instruction or "",
        guards=row.guards,
        trigger=TriggerChoice(
            kind=TriggerKind(row.trigger_kind or ""),
            cadence=cadence,
            source=row.trigger_source or "",
        ),
        tools=tuple(row.tools or ()),
        condition=condition,
        template_id=row.from_template_id,
        task=row.task,
    )
