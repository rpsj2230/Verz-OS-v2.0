"""Installing a template, and building an agent by hand, which is the same six steps.

`brain.agents.template` says what a template is and what an install is made of. It ends by
saying that `install` exists and nothing calls it, and that the wizard is this leaf. This
module is that caller, and it adds one idea: an install is a draft somebody fills in, a
report of what is still missing, and a completion that produces an agent already sitting at
the floor.

**Installing is not a way to widen anything.** Every value an installer supplies goes into
the overlay, and the overlay is refused at five paths by `check_overlay` and by the check
constraint behind it. There is no argument anywhere in this module that raises a rung, a
side effect or a ceiling, and the one place a rung moves at all is `pinned_leash`, which is
written as an intersection so it can only lower. `INSTALLING_IS_NOT_A_WAY_TO_WIDEN` states
it, and the property is asserted by installing a template whose leash says AUTONOMOUS and
reading SHADOW back.

**The seal is not restated here and this module could not restate it if it wanted to.**
`plan` hands its own field list to `check_overlay` rather than comparing against
`SEALED_PATHS`, so a step that named a sealed path would be refused by the domain's own
validator with the domain's own sentence. There are two enforcement points for the seal and
this is a caller of one of them, not a third. See `THE_SEAL_IS_NOT_RESTATED_HERE`, and see
`brain.tables.template` for why the constraint rather than the validator is the fence.

**A hand-built agent and an installed template finish through one function.** M13.2.7 built
the blank template precisely so there would be no second constructor, and the way to keep
that promise is to have nowhere else to go: `complete` is the only function in this module
that returns an `Installation`, `begin_hand_built` is one line that delegates to `begin`, and
`tests/unit/test_agent_install.py` asserts the first of those by reading the module's own
annotations rather than by believing this paragraph.

**A new agent starts at the floor, and an unbound connector holds it there.** The blank
template's sealed values are `NONE` and an empty leash, so a hand-built agent is SHADOW on
every target before anybody configures anything. For an installed template the floor is the
template's own leash, narrowed: `pinned_leash` returns SHADOW everywhere while any connector
the manifest declares is not serving, because a rung above SHADOW is a promise that the
agent's tools work, and a tool behind an unbound connector does not. See
`AN_UNBOUND_CONNECTOR_PINS_THE_RUN_TO_SHADOW`.

**An incomplete install is disabled rather than badged and selectable.** M13.3.6 asks for an
amber badge listing what is missing, and a badge alone would leave an agent answering from a
blank where a price list should be, which is exactly the failure `Placeholder` was written to
prevent. So `complete` runs the materialised record through `brain.agents.lifecycle.disable`
when anything is missing, and `runnable_agent_ids` therefore leaves it out until somebody
finishes it. The badge is what a person reads; the disabled timestamp is what selection
reads. See `AN_INCOMPLETE_INSTALL_IS_DISABLED_RATHER_THAN_SELECTABLE`.

**A template names its tools by what they do, and the install binds them to this install's
tools.** A manifest cannot know which system a company reads, so the catalogue declares
`invoice.read`; a registered tool carries its source in its name, `demo.read_invoice`, because
`brain.knowledge.rows.RowTool` argues a source is part of a tool's identity. `project` and
`Leash.rung_for` both compare names exactly, so until 2026-09-14 every catalogue template
reached `invoke` holding names no registry could contain and was refused for every caller,
while this module badged it READY. `complete` now takes the tool registry, `bind_tool` binds
each declared tool by entity and verb, and the bound names are what `Installation.record` and
`Installation.leash` carry, which is the shape `agent.agent.allowed_tools` already stores. A
declared tool nothing binds is `MissingKind.TOOL`: the badge is INCOMPLETE and the agent starts
disabled, exactly as for an unbound connector. See
`A_TEMPLATE_NAMES_WHAT_IT_USES_AND_THE_INSTALL_NAMES_WHICH_TOOL` and
`A_TOOL_NOTHING_HERE_BINDS_IS_MISSING`.

**An agent is finished from a manifest in one function, and an upgrade finishes through it
too.** `settle` materialises, binds the declared tools, reads the connectors, badges the
result and disables it when anything is missing, and it is the only caller of `materialise` in
`brain.agents`. `complete` calls it for an install and `brain.agents.upgrade.accept` calls it for
an upgrade. Until 2026-09-14 `accept` called `materialise` itself, so an accepted upgrade came
back holding the record the template declared, with `invoice.read` in its allowed tools and on
its leash: the defect this module had just fixed for installs, waiting for the first caller to
persist an upgrade. Fixing that call site would have left the next finishing path free to make
the same mistake, so the step moved rather than being repeated, and a test reads the package's
source for any other caller. See `AN_AGENT_IS_FINISHED_FROM_A_MANIFEST_IN_ONE_PLACE`.

**A template nobody may install and a template that does not exist give one answer.**
`TemplateCatalogue.open_for` has one raise site, so the two causes cannot drift into two
sentences, and `installable_ids` returns a frozenset, which has nowhere to put a count of
what it withheld. This is `A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER` applied one
layer up, and it matters more here than it looks: a catalogue of templates is a list of what
a company does, so a reader who could tell "there is no debt-chasing template" from "you may
not install it" could map the departments from the picker.

**The audience of a template is not the audience of the agent it installs.** `Offer.audience`
answers who may install; `complete` takes the agent's audience as its own argument and never
reads the offer's. Defaulting one to the other reads as a convenience and would publish an
agent to everybody who could see the template it came from, which is
`AUDIENCE_IS_NOT_AUTHORITY` failing in the audience direction. A template itself still
carries no audience anywhere: the offer is a local record of what this installation chose to
put in front of whom, and it lives beside the manifest rather than inside it.

**What a golden-set run can honestly check here, and what it cannot.** M13.3.4 and M13.3.5
ask for the golden set to be run twice, as the installing principal and as a low-privilege
fixture. Judging an answer needs a model and there is none wired into this process, so what
runs here is the half that does not: `rehearse` assembles the run through the real
`brain.gate.invoke.invoke` and reports whether it starts, what it reaches and at what rung.
That is the half the two leaves exist for, because it is the half that differs between the
two people: an agent that assembles for an administrator and reaches nothing for ordinary
staff is the commonest way an install passes its own test. Whether the answer is right is
judged by a person against `GoldenCase.expectation`, which is prose for the reason that model
gives. `rehearse_golden_set` refuses to be handed the same principal twice, because a golden
set run twice as one person is one run wearing two labels.

Six designs were rejected.

*Binding when a run starts rather than when the install completes.* The registry is in hand at
run time and the binding would follow a change of source for free. But the badge is computed
here, and it is read by a person deciding whether the install is finished: bound only at run
time, it would go on saying READY about an agent the run then refuses, which is the defect
this binding exists to remove. Binding is recomputed every time `complete` assembles an
`Installation`, which is the same recomputation the connector pin gets.

*A tool registry argument that defaults to none.* There is no honest default. Without a
registry nothing binds, so a default would either report every declared tool missing, which
reads as a broken template, or report nothing missing, which is the defect. A required
argument makes every caller say which tools it installs against.

*Binding `search` to a row tool's `read` because a row tool also filters.* The catalogue's
authors wrote the two verbs as two leash targets, and the product's vocabulary keeps them apart:
the Freshdesk connector declares `freshdesk.search_tickets`. Binding both to one tool would put
two supervision decisions on one name and badge a template complete for a tool it did not ask
for, so a verb binds only the same verb.

*A wizard with two paths, one for a template and one for "create from scratch".* It is the
obvious shape and it is the one M13.2.7 exists to prevent. Two paths means two places the
overlay is assembled, two places `check_overlay` is or is not called, and the hand-built path
is the one nobody reviews because it looks like the simple case.

*Storing the pin to Shadow on the instance.* An install that recorded "this one is pinned"
would be a decision taken once, at the moment a connector happened to be down, and it would
outlive the outage in both directions: it would go on holding an agent at SHADOW after the
connector came back, and it would say nothing when a connector was disabled a month later.
The pin is recomputed from the registry every time an `Installation` is assembled, so it
follows the connector rather than remembering it.

*A `placeholder_answers` column on `agent.template_instance`.* Nothing in `src` writes that
table at all today, so the column would be storage for a writer that does not exist, and the
migration would be the tenth mechanism here that nothing calls. The answers are carried on
the draft and on the `Installation`, and when somebody builds the writer that is where they
go.

**What consults this, and what does not.** No HTTP route calls any of it. There is no route
behind the gate in this repository, `brain.agents.model` and `brain.agents.template` both
refused to invent one, and a request pipeline invented here would be a second pipeline for
the real one to be reconciled with. What is wired is real and was not before: this is the
only caller of `brain.agents.template.install` and `blank_template`; `settle` is the only caller
of `materialise` in `brain.agents`, while `brain.agent_routes` materialises to show an install's
composition and `brain.member_activity.build_personal_agent` materialises a personal agent,
neither of them through `settle`; this is the only caller of `brain.agents.lifecycle.disable` in
`src`; and `rehearse` drives
`brain.gate.invoke.invoke` with the tool ceiling `brain.agents.model.tool_ceiling` produces,
a reach narrowed by `entitlement_ceiling` through `EntitlementSet.intersect`, and a leash
this module computed. Those were three arguments with no producer anywhere.

**One thing this deliberately leaves uncalled, said plainly rather than implied.**
`brain.agents.template.hand_built` is the single-shot form of what `begin_hand_built` and
`complete` do across six steps, and it still has no caller in `src`. Reaching for it at
`complete` would mean re-signing the blank template at completion time and branching on which
template the draft came from, which is the two-path shape the module exists to refuse. The
two are not duplicates worth collapsing either: one is a wizard and the other is a one-line
constructor for a caller who already has the whole overlay.

Task ids: M13.3.1, M13.3.2, M13.3.3, M13.3.4, M13.3.5, M13.3.6, M13.3.7
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final

from pydantic import JsonValue

from brain.agents.lifecycle import disable
from brain.agents.model import (
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    AgentViewer,
    entitlement_ceiling,
    tool_ceiling,
    visible_to,
)
from brain.agents.template import (
    SETTABLE_PATHS,
    EffectiveAgent,
    Placeholder,
    SignedManifest,
    TemplateError,
    TemplateInstance,
    TemplateManifest,
    blank_template,
    check_overlay,
    install,
    materialise,
)
from brain.connectors.registry import ConnectorRegistry, ConnectorState
from brain.core.entitlement import EntitlementSet
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.gate.invoke import InvocationRefusedError, invoke
from brain.gate.leash import Leash, LeashEntry
from brain.knowledge.visibility import Visibility
from brain.tools.registry import TOOL_NAME_RE, ToolRegistry

# ------------------------------------------------------------------ written-down reasons

#: The rule the whole flow serves, stated where a reader meets it.
INSTALLING_IS_NOT_A_WAY_TO_WIDEN: Final = (
    "An install supplies values and never permissions. Everything an installer types lands "
    "in the overlay, the overlay cannot reach the five sealed paths, and no argument in "
    "this module raises a rung, a side effect or a ceiling. The single place a rung moves "
    "is the pin, which is written as an intersection and can only lower one. An install "
    "that could relax the supervision its template committed to would make the template's "
    "guardrails a suggestion, and the person relaxing them would be whoever was setting the "
    "agent up rather than whoever published it."
)

#: Why the wizard delegates the seal rather than checking it.
THE_SEAL_IS_NOT_RESTATED_HERE: Final = (
    "There are two enforcement points for the seal: the check constraint on "
    "agent.template_instance, which is the fence, and check_overlay, which is the message. "
    "This module is a caller of the second and never a third copy. A wizard that compared "
    "its own field list against SEALED_PATHS would be a third list to keep in step, and the "
    "copy that falls behind is the one a person is looking at while they fill the form in."
)

#: Why there is one completion function and not one per starting point.
ONE_FLOW_FOR_A_TEMPLATE_AND_A_HAND_BUILT_AGENT: Final = (
    "A hand-built agent is an install of the blank template, so there is one draft type, "
    "one set of steps and one function that finishes an install. Two paths would mean two "
    "places the overlay is assembled and two places the seal is or is not consulted, and "
    "the hand-built path is the one that gets the lighter review because it looks like the "
    "simple case. The property is asserted by reading this module's annotations for "
    "anything else that returns an Installation."
)

#: Why an unbound connector holds the whole agent at the bottom rung (M13.3.7).
AN_UNBOUND_CONNECTOR_PINS_THE_RUN_TO_SHADOW: Final = (
    "A rung above SHADOW is a statement that this agent may act without a person watching, "
    "and it was written by a template author who assumed the connectors the template "
    "declares are there. With one of them unbound, the agent acts on whatever it can still "
    "reach, from a partial picture, unsupervised, and the missing half is invisible in the "
    "result. So every rung is pinned to SHADOW while any declared connector is not serving. "
    "The pin is recomputed from the registry rather than stored, so it lifts when the "
    "connector comes back and returns when one is disabled later."
)

#: Why an install with something missing is switched off rather than merely marked.
AN_INCOMPLETE_INSTALL_IS_DISABLED_RATHER_THAN_SELECTABLE: Final = (
    "An amber badge is read by whoever opens the console. An agent is selected by whoever "
    "asks a question, who never sees the badge at all. An install missing a required price "
    "list answers confidently from a blank, which is the failure a placeholder exists to "
    "prevent, so the missing item has to stop the agent being chosen rather than only "
    "colour a row. disable is reversible and archive is not, which is why this uses the "
    "first: finishing the install and enabling it is the ordinary next step."
)

#: Why a template names its tools by what they do and the install names them by system.
A_TEMPLATE_NAMES_WHAT_IT_USES_AND_THE_INSTALL_NAMES_WHICH_TOOL: Final = (
    "A template travels between installations and cannot know which system a company reads, "
    "so it names a tool by what it does to what: invoice.read. A registered tool carries the "
    "system in its name as well, demo.read_invoice, because two systems' record ids collide by "
    "coincidence of integers and a source is part of a tool's identity. The gate compares names "
    "exactly, in the projection and on the leash, so a declared name reaching either matches "
    "nothing and every run is refused. The install is where the two meet: each declared tool "
    "is bound by entity and verb to the tools this install registered, and the bound names are "
    "what the record and the leash carry."
)

#: Why a declared tool nothing here binds holds the install open.
A_TOOL_NOTHING_HERE_BINDS_IS_MISSING: Final = (
    "The badge is read as a promise that the agent will run. Until 2026-09-14 it said READY for "
    "every catalogue template while brain.gate.invoke.invoke refused every one of them, because "
    "no declared tool matched a registered name. A declared tool no registered tool binds is "
    "therefore missing, as an unbound connector is: the badge is INCOMPLETE and the agent starts "
    "disabled. Nothing is invented to fill the gap, so a drafting tool the product does not "
    "have stays missing on every install until somebody builds one."
)

#: Why materialising, binding and badging are one function that every finishing path calls.
AN_AGENT_IS_FINISHED_FROM_A_MANIFEST_IN_ONE_PLACE: Final = (
    "materialise alone returns the record a template declared, whose allowed tools are names "
    "like invoice.read that no registry holds and whose leash is written against the same "
    "names. A caller that stored it would store an agent the gate can never project a tool for, "
    "and nothing would report it. So an install and an upgrade both finish through settle, "
    "which materialises, binds every declared tool to this install's registry, reads the "
    "connectors, and disables the record when anything is missing. A second finishing path "
    "is a second place for the binding to be forgotten, and the upgrade path had forgotten it."
)

#: Why the catalogue answers absence and refusal identically.
A_HIDDEN_TEMPLATE_AND_A_MISSING_TEMPLATE_ARE_ONE_ANSWER: Final = (
    "A catalogue of templates is a list of what a company does. A reader who could tell "
    "'there is no debt-chasing template here' from 'you may not install that one' could map "
    "the departments, the systems and the problems from a picker. So there is one raise "
    "site, one sentence, and a listing that returns a frozenset of ids with nowhere to put "
    "a count of what it left out."
)

#: Why installing something visible to a group does not publish the agent to that group.
THE_OFFER_AUDIENCE_IS_NOT_THE_AGENT_AUDIENCE: Final = (
    "Who may install a template and who may see the agent it becomes are two decisions with "
    "two answers. Defaulting the second to the first reads as a convenience and publishes "
    "an agent to everybody who could have installed it, which is how a finance assistant "
    "appears in the picker of all 126 staff without anybody choosing that. complete takes "
    "the agent's audience as its own argument and never reads the offer's."
)

#: Why the golden set is run twice and refused when it would be run twice as one person.
A_GOLDEN_SET_RUN_AS_ONE_PRINCIPAL_PROVES_NOTHING_ABOUT_ANOTHER: Final = (
    "The person installing an agent is usually the person with the widest reach in the "
    "room, so a golden set that passes for them proves the agent works for administrators. "
    "The run that finds the real problem is the second one, as somebody with almost "
    "nothing, because that is where an unreachable tool, a missing grant and a ceiling that "
    "narrows to nothing show up. Handing the same principal twice would produce two "
    "identical rehearsals and a report that looks like it checked both."
)

# ----------------------------------------------------------------- the six steps (M13.3.1)


class Step(enum.StrEnum):
    """The six screens an install is filled in through.

    Six because the work breakdown says six, and the grouping is by the question a person is
    answering rather than by the shape of the manifest: what is this called, what does it
    say, what may it reach, what does it plug into, what does it need to be told, and how
    will we know it works.
    """

    #: What this agent is called in a picker.
    IDENTITY = "identity"
    #: The instruction and the procedures that make it this agent, and the pool it runs on.
    PERSONA = "persona"
    #: The ceiling: rows, capabilities and tools. Never wider than the caller's own reach,
    #: because `E_run` is an intersection and this is only ever the right-hand side.
    AUTHORITY = "authority"
    #: What it plugs into, and whether those are actually serving (M13.3.2).
    CONNECTORS = "connectors"
    #: What the template could not know: the SOP, the price list, the escalation contact
    #: (M13.3.3).
    PLACEHOLDERS = "placeholders"
    #: The questions it must still answer correctly afterwards (M13.3.4, M13.3.5).
    GOLDEN_SET = "golden_set"


#: The order the six are presented in, written out rather than relying on the enum's
#: declaration order, for the reason `brain.gate.leash.CHECK_ORDER` gives: declaration order
#: is not part of an enum's contract and a reordering during a merge would silently move a
#: screen. The order is meaning as well: the ceiling is chosen before the connectors are
#: bound, because a connector nothing may reach is a binding nobody needed.
STEP_ORDER: Final[tuple[Step, ...]] = (
    Step.IDENTITY,
    Step.PERSONA,
    Step.AUTHORITY,
    Step.CONNECTORS,
    Step.PLACEHOLDERS,
    Step.GOLDEN_SET,
)

#: Which settable paths each step collects. Every settable path appears exactly once, and
#: `plan` refuses a table where one does not: a path in no step is a field the wizard never
#: shows and nobody can set, and a path in two is a field whose value depends on which screen
#: was saved last.
#:
#: `skills` sits with the persona because both are what the agent is told to do: the persona
#: is the instruction in words and a skill is a reviewed procedure pinned by digest.
STEP_FIELDS: Final[Mapping[Step, tuple[str, ...]]] = MappingProxyType(
    {
        Step.IDENTITY: ("identity.display_name", "identity.summary"),
        Step.PERSONA: ("persona", "skills", "tier"),
        Step.AUTHORITY: (
            "authority.scope",
            "authority.capabilities",
            "authority.allowed_tools",
            "authority.required_tools",
        ),
        Step.CONNECTORS: ("connectors",),
        Step.PLACEHOLDERS: ("placeholders",),
        Step.GOLDEN_SET: ("golden_set",),
    }
)

#: The paths a manifest cannot be blank in, and the constant is kept honest by a test that
#: asserts each one against the constructors rather than against this tuple:
#: `identity.display_name` is refused blank by `ManifestIdentity`, and `persona` is refused
#: blank by `AgentRecord`, which is why the blank template can carry an empty one and an
#: installed agent cannot. Anything else may legitimately be empty, including the summary.
REQUIRED_FIELDS: Final[tuple[str, ...]] = ("identity.display_name", "persona")

#: What a rung is held down to while a connector is missing. Named rather than written as a
#: literal at the point of use, so the fail-closed value is one thing a test can pin.
PIN_WHEN_UNBOUND: Final = AutonomyTier.SHADOW


class NoSuchTemplateError(TemplateError):
    """A template that is not offered here, or is not offered to this person.

    One type and one message for both, deliberately. Its own class rather than a message on
    `TemplateError` so a console can catch it and render absence, which is the one thing it
    is allowed to say.
    """


@dataclass(frozen=True)
class StepField:
    """One field on one screen, carrying the manifest's own schema for it (M13.3.1).

    The schema is a fragment of `TemplateManifest.model_json_schema()` rather than anything
    written here, which is what "generated from the manifest JSON Schema" has to mean if it
    is to be worth saying: a bound tightened on the model tightens the form, and a field that
    changes type changes the control, with no edit in this file. A hand-written description
    of each field would be a second description, and the second one is the one that goes
    stale without failing anything.
    """

    path: str
    schema: Mapping[str, Any]


@dataclass(frozen=True)
class WizardStep:
    """One of the six screens, its position, and the fields it collects."""

    step: Step
    #: One-based, because it is shown to a person as "step 3 of 6".
    position: int
    fields: tuple[StepField, ...]


@dataclass(frozen=True)
class WizardPlan:
    """The whole form, generated once from the manifest schema (M13.3.1)."""

    steps: tuple[WizardStep, ...]
    #: `$defs` from the manifest schema, so a renderer can resolve the references the
    #: fragments still carry. Carried rather than resolved recursively because a nested
    #: schema flattened into every field that mentions it is the same definition repeated
    #: nine times, and the day one copy differs nobody can tell which is authoritative.
    definitions: Mapping[str, Any]

    def field_for(self, path: str) -> StepField:
        """One field by path, or a refusal naming what the wizard actually collects."""
        for step in self.steps:
            for entry in step.fields:
                if entry.path == path:
                    return entry
        msg = f"the install wizard does not collect {path!r}"
        raise TemplateError(msg)

    def step_for(self, path: str) -> Step:
        """Which screen a path is answered on. Raises for a path no screen shows."""
        for step in self.steps:
            if any(entry.path == path for entry in step.fields):
                return step.step
        msg = f"the install wizard does not collect {path!r}"
        raise TemplateError(msg)

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(entry.path for step in self.steps for entry in step.fields)


def _resolve(fragment: Mapping[str, Any], defs: Mapping[str, Any]) -> dict[str, Any]:
    """One `$ref` followed, with the local keys kept.

    The local keys matter and are easy to drop: pydantic renders `tier` as a reference plus a
    `default`, so a resolver that returned the definition alone would produce a form with no
    default on the one field that has a sensible one.
    """
    ref = fragment.get("$ref")
    if not isinstance(ref, str):
        return dict(fragment)
    resolved: dict[str, Any] = dict(defs[ref.rsplit("/", 1)[-1]])
    resolved.update({k: v for k, v in fragment.items() if k != "$ref"})
    return resolved


def _fragment(path: str, schema: Mapping[str, Any], defs: Mapping[str, Any]) -> dict[str, Any]:
    """The schema for one dotted path, walked the way `TemplateManifest.document` walks it.

    One `partition` and at most one descent, because a manifest path is one or two parts and
    `document()` flattens it the same way. Walking with the same rule as the flattener is
    what keeps a field the form shows and a path the overlay carries the same field.
    """
    head, _, tail = path.partition(".")
    fragment = _resolve(schema["properties"][head], defs)
    if tail:
        fragment = _resolve(fragment["properties"][tail], defs)
    return fragment


def plan(step_fields: Mapping[Step, tuple[str, ...]] = STEP_FIELDS) -> WizardPlan:
    """Build the six-step form from the manifest's own JSON Schema (M13.3.1).

    Two refusals, and the first is delegated rather than written here.

    **A step naming a sealed or unknown path is refused by `check_overlay`.** The whole field
    list is handed to the domain's own validator, so a wizard that offered to set
    `guardrails.leash` fails with the seal's own sentence and this module gains no opinion
    about which paths are sealed. See `THE_SEAL_IS_NOT_RESTATED_HERE`.

    **Every settable path is collected exactly once.** A path in no step cannot be set by
    anybody, which turns a field the manifest declares into one nobody can fill; a path on
    two steps has a value that depends on which screen was saved last. Both are silent, so
    both are refused here rather than left to a test of the constant.

    `step_fields` is a parameter with the module's own table as its default so the partition
    rule can be tested against a table that breaks it. Without it, the only way to prove the
    refusal works would be to edit the constant, which is a mutation rather than a test.
    """
    # Values are irrelevant; `check_overlay` reads keys. Built as a dict comprehension rather
    # than `dict.fromkeys` so the annotation is the union the validator takes.
    probe: dict[str, JsonValue] = {p: None for step in STEP_ORDER for p in step_fields[step]}
    check_overlay(probe)

    seen: list[str] = [p for step in STEP_ORDER for p in step_fields[step]]
    duplicated = sorted({p for p in seen if seen.count(p) > 1})
    if duplicated:
        msg = (
            f"{duplicated} appear on more than one step; a path collected twice has a value "
            "decided by whichever screen was saved last"
        )
        raise TemplateError(msg)
    uncollected = sorted(set(SETTABLE_PATHS) - set(seen))
    if uncollected:
        msg = (
            f"{uncollected} are settable and no step collects them; a manifest field the "
            "wizard never shows is a field nobody can set"
        )
        raise TemplateError(msg)

    schema: dict[str, Any] = TemplateManifest.model_json_schema()
    defs: dict[str, Any] = schema.get("$defs", {})
    return WizardPlan(
        steps=tuple(
            WizardStep(
                step=step,
                position=position,
                fields=tuple(
                    StepField(path=path, schema=_fragment(path, schema, defs))
                    for path in step_fields[step]
                ),
            )
            for position, step in enumerate(STEP_ORDER, start=1)
        ),
        definitions=defs,
    )


# ------------------------------------------------------ what may be installed, and by whom
@dataclass(frozen=True)
class Offer:
    """One template this installation puts in front of somebody.

    The audience lives here rather than in the manifest, and that is the same rule
    `brain.agents.template` keeps one layer down: a template travels between installations
    and cannot know a company's idea of who may use it. An offer is the local record of that
    decision, made beside the manifest and never inside it.
    """

    signed: SignedManifest
    #: Who may install it. Not who may see the agent afterwards; see
    #: `THE_OFFER_AUDIENCE_IS_NOT_THE_AGENT_AUDIENCE`.
    audience: AgentAudience

    @property
    def template_id(self) -> str:
        return self.signed.manifest.identity.template_id

    @property
    def version(self) -> int:
        return self.signed.manifest.identity.version


@dataclass
class TemplateCatalogue:
    """Every template on offer here, and who each one is offered to.

    An instance rather than a module-level singleton, for the reason
    `brain.connectors.registry.ConnectorRegistry` gives about its own: a singleton is process
    state in a layer that holds none, and "which templates exist" would depend on import
    order.

    Holds declarations in memory. Nothing in `src` writes `agent.template_version` either, so
    the table that survives a restart is somebody else's leaf and this is the domain half.
    """

    _offers: dict[str, Offer] = field(default_factory=dict)

    def offer(self, signed: SignedManifest, *, audience: AgentAudience) -> Offer:
        """Put a template in front of an audience, replacing any earlier version of it.

        Replacing is what publishing a new version means, and it moves nothing: every
        existing instance is pinned to the version it was installed from, by three fields,
        and `materialise` refuses to follow a newer one. Which version the catalogue points
        at is a decision about what a new install gets, and the upgrade path for the existing
        ones is M13.4.
        """
        entry = Offer(signed=signed, audience=audience)
        self._offers[entry.template_id] = entry
        return entry

    def installable_ids(self, viewer: AgentViewer) -> frozenset[str]:
        """The template ids this person may install.

        A frozenset of ids and nothing else, per
        `A_HIDDEN_TEMPLATE_AND_A_MISSING_TEMPLATE_ARE_ONE_ANSWER`: there is no second return
        value carrying what was dropped, no total, and nowhere for one to be added later
        without somebody changing the signature.
        """
        return frozenset(
            template_id
            for template_id, entry in self._offers.items()
            if visible_to(entry.audience, viewer)
        )

    def open_for(self, template_id: str, viewer: AgentViewer) -> Offer:
        """The offer, if this person may install it.

        One raise site covering both causes, which is the whole of the property: two
        branches would be two sentences, and two sentences are a side channel that two people
        can read by comparing screens. `visible_to` is the audience answer from
        `brain.agents.model` rather than a second one written here.
        """
        entry = self._offers.get(template_id)
        if entry is None or not visible_to(entry.audience, viewer):
            msg = f"no template named {template_id!r} is available to install"
            raise NoSuchTemplateError(msg)
        return entry


def blank_offer(*, key: str, at: datetime, installer: str) -> Offer:
    """The blank template, offered to one person: themselves (M13.2.7 seen from M13.3).

    Personal rather than company-wide, because an offer's audience is who may install it and
    the person building an agent by hand is the only person this particular offer concerns.
    It is not put in the catalogue: a shared entry would be one row two people would race to
    install under one instance id, and there is nothing to share anyway since the manifest is
    a constant.
    """
    return Offer(
        signed=blank_template(key=key, at=at),
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id=installer),
    )


# ---------------------------------------------------------------------- the draft
@dataclass(frozen=True)
class InstallDraft:
    """A part-filled install: what was chosen, what was typed, and by whom.

    Frozen, and every edit returns a new draft, so a console can hold the answer before an
    edit beside the answer after it. That is the same arrangement `TemplateInstance` has and
    it is what M13.4's diff will need from this side too.

    `answers` is the overlay under construction and is keyed by manifest path.
    `placeholder_answers` is keyed by placeholder key and is not a manifest path at all: the
    manifest declares the questions and the install answers them, and there is nowhere in a
    manifest for an answer to live.
    """

    offer: Offer
    instance_id: str
    installer: str
    answers: Mapping[str, JsonValue] = field(default_factory=dict)
    placeholder_answers: Mapping[str, str] = field(default_factory=dict)


def begin(offer: Offer, *, instance_id: str, installer: str) -> InstallDraft:
    """Start an install of an offer somebody already proved they may install.

    Takes an `Offer` rather than a catalogue and a template id, so that the visibility check
    has exactly one home. An offer can only be got from `open_for`, which checks, or from
    `blank_offer`, which is the caller's own; there is no third constructor and therefore no
    path that starts an install without the check having run.
    """
    return InstallDraft(offer=offer, instance_id=instance_id, installer=installer)


def begin_hand_built(*, key: str, at: datetime, instance_id: str, installer: str) -> InstallDraft:
    """Start an agent built from nothing, which is an install of the blank template.

    One line, and it delegates. That is the point rather than an economy: there is no second
    draft type, no second set of steps and no second completion, so
    `ONE_FLOW_FOR_A_TEMPLATE_AND_A_HAND_BUILT_AGENT` is a fact about the call graph rather
    than a claim in a comment.
    """
    return begin(
        blank_offer(key=key, at=at, installer=installer),
        instance_id=instance_id,
        installer=installer,
    )


def answer(draft: InstallDraft, path: str, value: JsonValue) -> InstallDraft:
    """Set one manifest path, returning a new draft.

    `check_overlay` is the only check, and it is the domain's. A sealed path is refused with
    the seal's own sentence, an unknown path with the settable list, and this module contains
    no opinion about either. A wizard that filtered the paths itself would be a filter that
    could be looser than the constraint, and the looser one is the one a form is built from.
    """
    check_overlay({path: value})
    return InstallDraft(
        offer=draft.offer,
        instance_id=draft.instance_id,
        installer=draft.installer,
        answers={**draft.answers, path: value},
        placeholder_answers=draft.placeholder_answers,
    )


def provide(draft: InstallDraft, key: str, value: str) -> InstallDraft:
    """Answer one of the template's placeholders (M13.3.3).

    Refuses a key the effective manifest does not declare. An answer to a question nothing
    asked is an answer that goes nowhere: it would sit on the instance looking configured,
    the required placeholder it was meant for would still read as missing, and the person who
    typed it would have no way to see which of the two happened.
    """
    declared = {p.key for p in _effective_placeholders(draft)}
    if key not in declared:
        msg = (
            f"{key!r} is not a placeholder this template declares; it asks for "
            f"{sorted(declared)} and an answer to anything else is stored where nothing "
            "reads it"
        )
        raise TemplateError(msg)
    return InstallDraft(
        offer=draft.offer,
        instance_id=draft.instance_id,
        installer=draft.installer,
        answers=draft.answers,
        placeholder_answers={**draft.placeholder_answers, key: value},
    )


def _effective(draft: InstallDraft) -> dict[str, JsonValue]:
    """The flat document with the draft's answers laid over it.

    A reading rather than a materialisation, and it exists because the report has to be shown
    before the manifest can be built at all: a draft with no persona cannot be materialised,
    and "you still need a persona" is exactly what the report is for. `materialise` remains
    the authority on what an install is, and
    `test_the_report_reads_the_values_materialise_produces` holds the two together on the
    paths this reads.
    """
    return {**draft.offer.signed.manifest.document(), **draft.answers}


def _effective_placeholders(draft: InstallDraft) -> tuple[Placeholder, ...]:
    """The placeholders as the overlay leaves them, parsed through the real model.

    Through `Placeholder` rather than by reading raw keys off the JSON, so a placeholder an
    overlay supplies goes through the same validator a published one did and cannot arrive
    with a key the grammar refuses.
    """
    raw = _effective(draft)["placeholders"]
    if not isinstance(raw, list):
        msg = "placeholders must be a list; an overlay of another shape is not a manifest"
        raise TemplateError(msg)
    return tuple(Placeholder.model_validate(item) for item in raw)


def _text(document: Mapping[str, JsonValue], path: str) -> str:
    """One string path off an effective document, or the empty string if it is not one."""
    value = document[path]
    return value if isinstance(value, str) else ""


def _unanswered(draft: InstallDraft) -> tuple[str, ...]:
    """The keys of the required placeholders this draft has not answered, in manifest order."""
    return tuple(
        placeholder.key
        for placeholder in _effective_placeholders(draft)
        if placeholder.required and not draft.placeholder_answers.get(placeholder.key, "").strip()
    )


# ------------------------------------------------- connectors and readiness (M13.3.2)
@dataclass(frozen=True)
class ConnectorReadiness:
    """One connector the template declares, and whether it is actually serving.

    `state` is `None` when nothing by that name is installed here, which is a different
    indicator from registered-but-off and from quarantined: the first is a connector somebody
    has to install, the second one somebody has to switch on, and the third one somebody has
    to read a manifest diff about. Collapsing them into a boolean would leave an installer
    with an amber badge and no idea which of three people to go to.
    """

    name: str
    state: ConnectorState | None
    #: Read from `RegisteredConnector.is_serving` rather than compared against a state here,
    #: so there is one answer to "may this be called right now" and the registry owns it.
    ready: bool


def connector_readiness(
    names: tuple[str, ...], registry: ConnectorRegistry
) -> tuple[ConnectorReadiness, ...]:
    """A readiness indicator per declared connector, in the order the manifest lists them.

    The manifest's own list is normalised to sorted and deduplicated by `TemplateManifest`,
    so this is stable without sorting again here.
    """
    indicators: list[ConnectorReadiness] = []
    for name in names:
        if not registry.has(name):
            indicators.append(ConnectorReadiness(name=name, state=None, ready=False))
            continue
        entry = registry.get(name)
        indicators.append(ConnectorReadiness(name=name, state=entry.state, ready=entry.is_serving))
    return tuple(indicators)


def pinned_leash(leash: Leash, readiness: tuple[ConnectorReadiness, ...]) -> Leash:
    """Hold every rung at SHADOW while any declared connector is not serving (M13.3.7).

    Written as `min` against `PIN_WHEN_UNBOUND` rather than as an assignment, for the reason
    `brain.gate.invoke` gives about `autonomy_ceiling`: an intersection cannot raise a rung
    by accident, and an assignment could once somebody edits the constant.

    The entries are rebuilt through `LeashEntry`'s constructor rather than copied with an
    update, because `model_copy` skips validation, and the one path that ever rewrites a rung
    must not be the one path that can store an invalid one.

    Entries are kept rather than dropped. An empty leash answers SHADOW everywhere too, by
    `MISSING_ENTRY_RUNG`, so the two agree on the rung and disagree on the record: keeping
    them lets a console show which targets the template configured and what they will be
    once the connector is back.
    """
    if all(indicator.ready for indicator in readiness):
        return leash
    return Leash(
        entries=tuple(
            LeashEntry(
                agent_id=entry.agent_id,
                target=entry.target,
                scope=entry.scope,
                rung=min(entry.rung, PIN_WHEN_UNBOUND),
            )
            for entry in leash.entries
        )
    )


# ------------------------------------------------------ tools, bound to this install
@dataclass(frozen=True)
class ToolBinding:
    """One tool a manifest declares, and the registered tools that answer to it here.

    `bound` is empty when nothing registered here answers to the declaration, which is what
    `completeness` reports. It holds more than one name when two systems read here both carry
    the entity: a template asking to read invoices is asking for both, and neither widens the
    run, because each still requires the capability the ceiling has to admit.
    """

    #: As the manifest declares it: `invoice.read`, or a registered name for a hand-built agent.
    target: str
    #: The registered names it binds, in registry order.
    bound: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return bool(self.bound)


def _verb_of(name: str) -> str:
    """The verb of a registered tool's name, read off the grammar's own named group.

    `brain.core.envelope` asks that a name be split through its pattern rather than on a dot
    written here. Registration refuses a name outside the grammar, so a name read from a
    registry always matches; the empty string exists because `match` is typed as optional,
    and it is a verb no declaration can bind, since the grammar's verb is never empty.
    """
    parsed = TOOL_NAME_RE.match(name)
    return parsed["verb"] if parsed is not None else ""


def bind_tool(target: str, tools: ToolRegistry) -> ToolBinding:
    """The registered tools one declared tool stands for on this install.

    **A registered name binds itself.** That is a hand-built agent, whose tools are typed into
    the overlay by somebody who can see the registry, and it is disjoint from the other case:
    a registered name always has an underscore after its dot and a declaration never does.

    **Otherwise `entity.verb` binds every registered tool of that entity and that verb.** The
    entity is `ToolDefinition.entity` rather than the noun in the name, because the entity is
    what a field policy, a capability and a leash target are written about. A declaration with
    no dot has an empty verb and binds nothing, without a branch saying so.

    See `A_TEMPLATE_NAMES_WHAT_IT_USES_AND_THE_INSTALL_NAMES_WHICH_TOOL`.
    """
    if tools.has(target):
        return ToolBinding(target=target, bound=(target,))
    entity, _, verb = target.partition(".")
    return ToolBinding(
        target=target,
        bound=tuple(
            definition.name
            for definition in tools.definitions()
            if definition.entity == entity and _verb_of(definition.name) == verb
        ),
    )


def bind_tools(targets: tuple[str, ...], tools: ToolRegistry) -> tuple[ToolBinding, ...]:
    """A binding per declared tool, in the order the manifest lists them."""
    return tuple(bind_tool(target, tools) for target in targets)


def bound_record(record: AgentRecord, bindings: tuple[ToolBinding, ...]) -> AgentRecord:
    """The record with every declared tool replaced by the registered tools it binds.

    A declaration nothing binds is dropped rather than kept. The stored column is the gate's
    vocabulary, and a name no registry can hold is a name `project` can never match; what is
    missing is recorded where a person reads it, on `Completeness.missing`.

    Rebuilt through `AgentRecord`'s constructor rather than `model_copy`, which skips
    validation, so the rule that required tools sit inside allowed ones runs on the bound
    names too.
    """
    by_target = {binding.target: binding.bound for binding in bindings}
    authority = record.authority

    def bound(declared: frozenset[str]) -> frozenset[str]:
        return frozenset(name for target in declared for name in by_target.get(target, ()))

    fields = {name: getattr(record, name) for name in type(record).model_fields}
    return AgentRecord.model_validate(
        {
            **fields,
            "authority": AgentAuthority(
                scope=authority.scope,
                capabilities=authority.capabilities,
                allowed_tools=bound(authority.allowed_tools),
                required_tools=bound(authority.required_tools),
                max_side_effect=authority.max_side_effect,
            ),
        }
    )


def bound_leash(leash: Leash, bindings: tuple[ToolBinding, ...]) -> Leash:
    """The leash with each bound target's entry repeated for every registered name it binds.

    Scope and rung are carried unchanged, so binding can move a rung neither way; the one
    place a rung moves is `pinned_leash`. An entry whose target binds nothing is kept as it was
    written, for the reason `pinned_leash` keeps entries: a console can show what the template
    configured, and `Leash.rung_for` answers SHADOW for a name that matches no entry anyway.
    """
    by_target = {binding.target: binding.bound for binding in bindings if binding.ready}
    return Leash(
        entries=tuple(
            LeashEntry(agent_id=entry.agent_id, target=name, scope=entry.scope, rung=entry.rung)
            for entry in leash.entries
            for name in by_target.get(entry.target, (entry.target,))
        )
    )


# ------------------------------------------------------ what is still missing (M13.3.6)
class MissingKind(enum.StrEnum):
    """The four ways an install can be unfinished. Closed; there is no fifth."""

    #: A manifest path that may not be blank and is.
    FIELD = "field"
    #: A required placeholder with no answer.
    PLACEHOLDER = "placeholder"
    #: A declared connector that is not serving.
    CONNECTOR = "connector"
    #: A declared tool no tool registered on this install binds. See
    #: `A_TOOL_NOTHING_HERE_BINDS_IS_MISSING`.
    TOOL = "tool"


@dataclass(frozen=True)
class Missing:
    """One thing an install still needs, named so a person can go and do it."""

    kind: MissingKind
    name: str


class InstallBadge(enum.StrEnum):
    """Whether an install is finished. Two states, and there is no third.

    The console paints `INCOMPLETE` amber, and the colour is deliberately not in here: a
    domain enum holding a colour is a second vocabulary the day somebody adds a dark theme,
    and the thing worth naming is the state rather than how it is drawn.
    """

    READY = "ready"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class Completeness:
    """The badge, and everything it is a badge for (M13.3.6).

    The list is the point. A badge on its own tells somebody to go and look, and the looking
    is the part that does not happen. Listing what is missing is safe here in a way a count
    of hidden items never is: every item named is something the installer's own manifest
    declares and they are already holding.
    """

    badge: InstallBadge
    missing: tuple[Missing, ...]

    @property
    def is_ready(self) -> bool:
        return self.badge is InstallBadge.READY


def completeness(
    draft: InstallDraft,
    readiness: tuple[ConnectorReadiness, ...],
    bindings: tuple[ToolBinding, ...],
) -> Completeness:
    """What this draft still needs, in the order somebody would work through it (M13.3.6).

    Fields first, because a blank persona means there is no agent to badge at all and
    `materialise` will refuse rather than warn. Then the placeholders, which are the
    installer's own typing. Then the connectors, which are usually somebody else's job. Then
    the tools, last, because binding one is a change to what the whole install reads rather
    than to this agent. See `A_TOOL_NOTHING_HERE_BINDS_IS_MISSING`.
    """
    return _report(_effective(draft), _unanswered(draft), readiness, bindings)


def _report(
    document: Mapping[str, JsonValue],
    unanswered: tuple[str, ...],
    readiness: tuple[ConnectorReadiness, ...],
    bindings: tuple[ToolBinding, ...],
) -> Completeness:
    """The badge over one effective document, shared by `completeness` and `settle`.

    One body for both, so a draft's report and a finished agent's report cannot come to
    disagree about what counts as missing. See `completeness` for the order.
    """
    missing: list[Missing] = []
    missing.extend(
        Missing(kind=MissingKind.FIELD, name=path)
        for path in REQUIRED_FIELDS
        if not _text(document, path).strip()
    )
    missing.extend(Missing(kind=MissingKind.PLACEHOLDER, name=key) for key in unanswered)
    missing.extend(
        Missing(kind=MissingKind.CONNECTOR, name=indicator.name)
        for indicator in readiness
        if not indicator.ready
    )
    missing.extend(
        Missing(kind=MissingKind.TOOL, name=binding.target)
        for binding in bindings
        if not binding.ready
    )
    badge = InstallBadge.READY if not missing else InstallBadge.INCOMPLETE
    return Completeness(badge=badge, missing=tuple(missing))


# --------------------------------------------------------------- finishing an agent
@dataclass(frozen=True)
class Settled:
    """An effective agent settled against this install's connectors and tools.

    What `settle` returns, and the only way this package turns a signed manifest and an
    instance into something fit to store. `record` and `leash` carry bound names; `effective`
    keeps the declared ones, so a console can show what the template asked for beside what it
    became. See `AN_AGENT_IS_FINISHED_FROM_A_MANIFEST_IN_ONE_PLACE`.
    """

    effective: EffectiveAgent
    record: AgentRecord
    leash: Leash
    readiness: tuple[ConnectorReadiness, ...]
    completeness: Completeness
    tools: tuple[ToolBinding, ...]


def settle(
    signed: SignedManifest,
    instance: TemplateInstance,
    *,
    audience: AgentAudience,
    unanswered: tuple[str, ...],
    registry: ConnectorRegistry,
    tools: ToolRegistry,
    at: datetime,
) -> Settled:
    """Materialise an agent and settle it against this install's registries (M13.3.6, M13.3.7).

    The order is the argument.

    **Materialised first**, so the pin, the overlay and the record's own validators have all run
    before anything is bound: a manifest that cannot become an agent is refused rather than
    badged.

    **Every declared tool is bound to `tools` and every declared connector read from `registry`
    before the badge is decided**, per
    `A_TEMPLATE_NAMES_WHAT_IT_USES_AND_THE_INSTALL_NAMES_WHICH_TOOL` and
    `A_TOOL_NOTHING_HERE_BINDS_IS_MISSING`. Neither registry has a default, for the reason
    the module docstring gives about the tool registry: with no registry nothing binds, and a
    default would report every tool missing or none.

    **`unanswered` is the one fact only the caller holds.** Placeholder answers live on a draft
    and nowhere a manifest or an instance can carry them, so the caller names the required keys
    still unanswered. It has no default, so a caller that cannot know them has to say so.

    **The record is disabled when anything is missing**, per
    `AN_INCOMPLETE_INSTALL_IS_DISABLED_RATHER_THAN_SELECTABLE`, through
    `brain.agents.lifecycle.disable`. The leash is bound, then pinned, per
    `AN_UNBOUND_CONNECTOR_PINS_THE_RUN_TO_SHADOW`.
    """
    effective = materialise(signed, instance, audience=audience)
    readiness = connector_readiness(effective.manifest.connectors, registry)
    bindings = bind_tools(effective.manifest.authority.allowed_tools, tools)
    report = _report(effective.document, unanswered, readiness, bindings)
    bound = bound_record(effective.record, bindings)
    return Settled(
        effective=effective,
        record=bound if report.is_ready else disable(bound, now=at),
        leash=pinned_leash(bound_leash(effective.leash, bindings), readiness),
        readiness=readiness,
        completeness=report,
        tools=bindings,
    )


@dataclass(frozen=True)
class Installation:
    """One finished install: the row, the effective agent, and the state it starts in.

    `record` rather than `effective.record` is the one to store and the one to select on.
    They differ in two ways: `EffectiveAgent.record` is what the manifest and the overlay say,
    and this is that record with its declared tools bound to this install's registered ones and
    the install's own state applied, which today means disabled when anything is missing. Both
    decisions are taken in `settle` and nowhere else, so there is one place the two can be
    compared rather than two places they can drift.

    `leash` is likewise bound and then pinned, rather than `effective.leash`, which is what the
    template declared. Both are recomputed here from the registries handed in, so they follow
    the connector and the tool rather than remembering either.
    """

    instance: TemplateInstance
    effective: EffectiveAgent
    record: AgentRecord
    leash: Leash
    readiness: tuple[ConnectorReadiness, ...]
    completeness: Completeness
    placeholder_answers: Mapping[str, str]
    #: What each declared tool bound to. See
    #: `A_TEMPLATE_NAMES_WHAT_IT_USES_AND_THE_INSTALL_NAMES_WHICH_TOOL`.
    tools: tuple[ToolBinding, ...]

    @property
    def is_pinned_to_shadow(self) -> bool:
        """Whether a connector is holding this agent at the bottom rung right now."""
        return not all(indicator.ready for indicator in self.readiness)


def complete(
    draft: InstallDraft,
    *,
    key: str,
    audience: AgentAudience,
    registry: ConnectorRegistry,
    tools: ToolRegistry,
    at: datetime,
) -> Installation:
    """Finish an install and produce the agent it becomes (M13.3.6, M13.3.7).

    The only function here that returns an `Installation`, which is what makes M13.2.7's one
    code path a property of this module rather than a hope. A hand-built agent arrives here
    through `begin_hand_built` carrying the blank template, and nothing in the body branches
    on which it was.

    The order is the argument.

    **The signature is verified before anything is read**, because `install` calls `verify`
    and this calls `install`. A manifest nobody published must not become an agent, and the
    check belongs where the manifest stops being data.

    **The overlay is checked twice and neither check is here.** `answer` calls
    `check_overlay` as each value arrives, and `install` calls it again over the whole
    overlay, because a draft can also be built by a caller who assembled `answers` directly.

    **The audience is this function's argument and never the offer's**, per
    `THE_OFFER_AUDIENCE_IS_NOT_THE_AGENT_AUDIENCE`.

    **The record is disabled when anything is missing**, per
    `AN_INCOMPLETE_INSTALL_IS_DISABLED_RATHER_THAN_SELECTABLE`, through
    `brain.agents.lifecycle.disable` rather than by writing the column here, so the one rule
    about archived records refusing a state change applies to an install too.

    **Every declared tool is bound to `tools` before the badge is decided**, per
    `A_TEMPLATE_NAMES_WHAT_IT_USES_AND_THE_INSTALL_NAMES_WHICH_TOOL`, and a declared tool that
    binds nothing is missing, per `A_TOOL_NOTHING_HERE_BINDS_IS_MISSING`. The allowed tools are
    what is bound, and required tools are always inside them, which `AgentCeiling` refuses
    otherwise when the record is built.

    A blank persona is refused rather than badged. There is no `AgentRecord` to attach a
    badge to, and `AgentRecord`'s own validator is the refusal, which keeps that rule in one
    place rather than restated as a wizard step.
    """
    instance = install(
        draft.offer.signed,
        key=key,
        instance_id=draft.instance_id,
        created_by=draft.installer,
        at=at,
        overlay=draft.answers,
    )
    settled = settle(
        draft.offer.signed,
        instance,
        audience=audience,
        unanswered=_unanswered(draft),
        registry=registry,
        tools=tools,
        at=at,
    )
    return Installation(
        instance=instance,
        effective=settled.effective,
        record=settled.record,
        leash=settled.leash,
        readiness=settled.readiness,
        completeness=settled.completeness,
        placeholder_answers=dict(draft.placeholder_answers),
        tools=settled.tools,
    )


# ------------------------------------------------- the golden set (M13.3.4, M13.3.5)
@dataclass(frozen=True)
class Rehearsal:
    """What one person would actually get from this agent, before anybody asks in anger.

    Names and a rung, and nothing that could be a value. `reachable` is the tool names the
    projection kept, which is already the intersection of what this person holds and what
    the agent's ceiling admits, so there is nothing here the caller could not compute for
    themselves by asking.

    `started` is the whole verdict on reach, and there is no reason field beside it because
    `invoke` refuses for exactly one reason: this person reaches no tool through this agent.
    """

    principal_id: str
    started: bool
    reachable: tuple[str, ...]
    #: The strictest rung this run would be held to, or `None` when the run does not start.
    rung: AutonomyTier | None
    #: The golden set's questions, carried so whoever judges the answers has them beside the
    #: reach. The judging needs a model and there is none in this process; see the module
    #: docstring.
    questions: tuple[str, ...]


@dataclass(frozen=True)
class GoldenRehearsal:
    """The same golden set, rehearsed as two people (M13.3.4, M13.3.5)."""

    installer: Rehearsal
    fixture: Rehearsal

    @property
    def both_started(self) -> bool:
        """Whether the agent assembles a run for both. False is the finding, not an error."""
        return self.installer.started and self.fixture.started


def rehearse(
    installed: Installation,
    *,
    registry: ToolRegistry,
    entitlement: EntitlementSet,
    assessment: RiskAssessment,
    now: datetime,
    row: dict[str, str] | None = None,
) -> Rehearsal:
    """Assemble the run this person would get, through the real gate (M13.3.4).

    `brain.gate.invoke.invoke` rather than anything written here, and it is handed the
    ceiling `brain.agents.model.tool_ceiling` produces and the leash this install computed,
    which are the two arguments that had no producer in `src` before. A rehearsal built from
    a stand-in would prove that this module's idea of a run is self-consistent.

    **The lens is applied before the run is assembled, and by calling `intersect`.** `invoke`
    takes an entitlement and narrows tools by the ceiling it is given; it does not narrow the
    entitlement, so a rehearsal that handed it the caller's own reach would report a run
    wider than any real one, and it would report it about the very case this exists to check.
    `E(caller) ∩ agent_ceiling` is computed here by `EntitlementSet.intersect`, which is the
    one implementation of it, with `entitlement_ceiling` producing the right-hand side.

    A refusal is a result and not an exception here. "This agent reaches nothing for this
    person" is exactly what the rehearsal is asking, and raising would make the finding
    something the caller has to remember to catch.
    """
    questions = tuple(case.question for case in installed.effective.manifest.golden_set)
    run = entitlement.intersect(entitlement_ceiling(installed.record), now)
    try:
        invocation = invoke(
            principal_id=entitlement.principal_id,
            agent_id=installed.record.agent_id,
            registry=registry,
            entitlement=run,
            ceiling=tool_ceiling(installed.record),
            leash=installed.leash,
            assessment=assessment,
            now=now,
            row=row or {},
        )
    except InvocationRefusedError:
        return Rehearsal(
            principal_id=entitlement.principal_id,
            started=False,
            reachable=(),
            rung=None,
            questions=questions,
        )
    return Rehearsal(
        principal_id=entitlement.principal_id,
        started=True,
        reachable=invocation.reachable,
        rung=invocation.ceiling_rung,
        questions=questions,
    )


def rehearse_golden_set(
    installed: Installation,
    *,
    registry: ToolRegistry,
    installer: EntitlementSet,
    fixture: EntitlementSet,
    assessment: RiskAssessment,
    now: datetime,
    row: dict[str, str] | None = None,
) -> GoldenRehearsal:
    """Rehearse as the installing principal and as a low-privilege fixture (M13.3.4, M13.3.5).

    Refuses the same principal twice. Two identical rehearsals under two labels is a report
    that looks like it checked both, and the second run is the one that finds anything: see
    `A_GOLDEN_SET_RUN_AS_ONE_PRINCIPAL_PROVES_NOTHING_ABOUT_ANOTHER`.
    """
    if installer.principal_id == fixture.principal_id:
        msg = (
            f"the golden set cannot be rehearsed twice as {installer.principal_id!r}; the "
            "second run exists to be somebody with less, and two runs as one person is one "
            "run wearing two labels"
        )
        raise TemplateError(msg)
    return GoldenRehearsal(
        installer=rehearse(
            installed,
            registry=registry,
            entitlement=installer,
            assessment=assessment,
            now=now,
            row=row,
        ),
        fixture=rehearse(
            installed,
            registry=registry,
            entitlement=fixture,
            assessment=assessment,
            now=now,
            row=row,
        ),
    )
