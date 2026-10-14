"""Which genuinely new features an install has switched on, and what reads each switch.

CLAUDE.md says a genuinely new feature "goes into this repository behind a flag and ships to
everyone switched off", and until this module there was no flag to put one behind. What existed
were switches for one kind of thing each: a routing rung's `enabled` column, the plugin
lifecycle's four states with nothing loading a plugin, a connector registry nothing constructs,
and `Settings.release_check`, which is read from the environment and so could not be turned from a
browser. None of them was a place a new feature could be declared and turned on by an
administrator without a shell. The release check is now a feature here as well (`RELEASE_CHECK`),
beside the environment's value rather than instead of it (M27.15.51).

**A feature is declared in this file, with the functions that read it, and nowhere else.**
`FEATURES` is closed and compiled, for the reason `brain.ops.controls.CONTROLS` is: what the
product can switch on is a fact about the product, identical on every install, and a table of
features would be a list any operator could extend with a switch nothing reads. The install's
half is one boolean row per feature in `ops.setting`, under `feature.<name>`, which is exactly
the kind of row `brain.tables.config` was built for. See `brain.ops.setting_store`.

**Every feature ships switched off, and there is no field that could say otherwise.** Absence
of a row is off, a row whose value is not the JSON `true` is off, and a row naming a feature
nobody declared is ignored. `Feature` has no default to set, so a feature cannot arrive on by a
reviewer missing one word. See `EVERY_FEATURE_SHIPS_SWITCHED_OFF`.

**A switch nothing reads is the defect this repository keeps finding, so the readers are
checked in both directions.** `Feature.read_by` names each function that asks `is_on` about the
feature, and `feature_gaps` parses those functions and every other function under `src/brain`:
a declared reader that does not ask, and a function that asks and is not declared, are both
findings. A feature whose switch reaches nothing is the control `docs/admin-console.md` calls
worse than no control. See `A_SWITCH_NOTHING_READS_IS_A_CONTROL_THAT_REACHES_NOTHING`.

**A switch gates the door and never traps what it opened.** Turning `schedule_control` off
stops anybody pausing a control or asking for a run; it does not resume a control somebody
paused while it was on, and resuming is not behind the switch, because a switch turned off
that left a control paused with no way back would be a stop nobody can release. The same holds
for giving an agent's instructions back to its template. See
`A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED`.

**Module enablement is not here, and the reason is where modules live.** The optional
components an install runs are chosen by its profile (`brain.ops.wiring.PROFILES`) as containers
in a compose file, so switching one on from a browser would be a process starting a container
on its own host, which nothing in this product may do. The Install screen already shows which
components the profile runs. Plugins have a lifecycle (`brain.plugins.lifecycle`) and no loader,
so an enabled plugin changes nothing and a switch for one would reach nothing. Both are said on
the Features screen rather than drawn as switches.

Rejected: a feature per new route, discovered by a decorator. It reads as less ceremony and it
puts the declaration beside the code, where a reviewer reading the list of what an install can
switch on cannot find it; `brain.ops.effects` rejected a decorator for the same reason.

Rejected: reading the switches once at startup, as `brain.ops.install_settings` does. A value
the wizard writes once can be held per process; a switch an administrator flips expects the next
request to see it, and every reader here already holds a session in the request that asks.

Not claimed, and the reason is the paragraph on module enablement above: the leaf names features
and modules, and this switches features.

Task ids: M27.15.51
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
import textwrap
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from brain.ops.setting_store import SettingState, put, read_namespace, values_under
from brain.tables.config import SettingType

# ------------------------------------------------------------------ written-down reasons
#: Why a feature has no default.
EVERY_FEATURE_SHIPS_SWITCHED_OFF: Final = (
    "A genuinely new feature reaches every install in the same release, including installs "
    "whose owners have never heard of it. Off is the only default that asks nobody to have "
    "read the release notes, so there is no default at all: no row is off, a row that is not "
    "true is off, and switching one on is a person's recorded act."
)

#: Why the readers are checked against the source.
A_SWITCH_NOTHING_READS_IS_A_CONTROL_THAT_REACHES_NOTHING: Final = (
    "A feature switch is pressed in a browser and read by a route. If the route stops asking, "
    "the switch goes on rendering and changing a row, and the feature is either always on or "
    "never on whatever the screen says. So the functions that ask are named on the feature, and "
    "the source is parsed to hold the names to the calls in both directions."
)

#: Why switching a feature off does not undo what it did.
A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED: Final = (
    "A switch decides whether the door is open. A control paused while the switch was on is "
    "still paused after it is turned off, and if resuming were behind the same switch the "
    "control would be stopped with no way back from the console. So the act that opens a "
    "state is behind the switch and the act that undoes it never is."
)

# ------------------------------------------------------------------------ the figures
#: The `ops.setting` namespace every switch sits under: `feature.<name>`.
FEATURE_NAMESPACE: Final = "feature"

#: A feature's name, and the last segment of its key. The key grammar's own segment shape.
FEATURE_NAME_PATTERN: Final = r"^[a-z][a-z0-9_]*$"

#: `module:function`, both dotted identifiers, as `brain.ops.controls` spells a symbol.
_READER_RE: Final = re.compile(r"^[a-z_][a-z0-9_.]*:[a-z_][a-z0-9_]*$")

#: The package `feature_gaps` reads. A parameter everywhere below.
SRC: Final[Path] = Path(__file__).resolve().parents[1]

#: The name every reader calls. A literal the source check looks for.
READER_CALL: Final = "is_on"


class FeatureError(Exception):
    """Raised for a feature this product does not declare, or one declared wrongly."""


@dataclass(frozen=True)
class Feature:
    """One switch an administrator can turn, and every function that reads it.

    `what` and `while_off` are product text a person reads beside the switch: what turning it
    on lets somebody do, and what stays true while it is off.
    """

    name: str
    title: str
    what: str
    while_off: str
    #: Every function that asks `is_on` about this feature, as `module:function`: the ones it gates
    #: and the ones that only say on a screen whether it is on, because both stop being true
    #: together if the switch stops reaching them.
    read_by: tuple[str, ...]

    def __post_init__(self) -> None:
        if not re.fullmatch(FEATURE_NAME_PATTERN, self.name):
            msg = f"{self.name!r} is not a feature name: lowercase, digits and underscores"
            raise FeatureError(msg)
        named = ((self.title, "title"), (self.what, "what"), (self.while_off, "while_off"))
        for sentence, field in named:
            if not sentence.strip():
                msg = f"feature {self.name!r} has no {field}, so its switch explains nothing"
                raise FeatureError(msg)
        if not self.read_by:
            msg = (
                f"feature {self.name!r} names no reader. "
                f"{A_SWITCH_NOTHING_READS_IS_A_CONTROL_THAT_REACHES_NOTHING}"
            )
            raise FeatureError(msg)
        for reader in self.read_by:
            if not _READER_RE.match(reader):
                msg = f"feature {self.name!r} names {reader!r}, which is not module:function"
                raise FeatureError(msg)

    @property
    def key(self) -> str:
        """The `ops.setting` key this feature's switch is kept under."""
        return f"{FEATURE_NAMESPACE}.{self.name}"


#: Editing an agent's instructions from the console.
PROMPT_EDITING: Final = Feature(
    name="prompt_editing",
    title="Edit agent instructions from the console",
    what=(
        "An administrator holding the authority may replace an agent's instructions on the "
        "Prompts screen. The edit is recorded on the agent's install as a local change to its "
        "template, and the agent is given the new text from the next request."
    ),
    while_off=(
        "Instructions are shown and cannot be edited. An edit made while this was on stays in "
        "force and can still be given back to the template."
    ),
    read_by=(
        "brain.prompt_routes:prompts",
        "brain.prompt_routes:edit_instructions",
        "brain.prompt_routes:give_back_instructions",
    ),
)

#: Pausing a scheduled control and asking for one to run now.
SCHEDULE_CONTROL: Final = Feature(
    name="schedule_control",
    title="Pause and run scheduled jobs from the console",
    what=(
        "An administrator holding the authority may pause a scheduled job, so the worker stops "
        "starting it, or ask for one run now, which the worker starts on its next tick through "
        "the same lock and the same run record as a scheduled run."
    ),
    while_off=(
        "Jobs run on their schedule and nothing can be paused or run from the console. A job "
        "paused while this was on stays paused and can still be resumed."
    ),
    read_by=(
        "brain.jobs_routes:jobs",
        "brain.jobs_routes:job_detail",
        "brain.jobs_routes:pause_job",
        "brain.jobs_routes:run_job",
        # Sync now on Staff sources writes the same run request as Run now (M1.10.2).
        "brain.staff_source_routes:ask_staff_sync_now",
    ),
)

#: Looking for newer releases from Version and updates. Either this switch or the environment's
#: `BRAIN_RELEASE_CHECK` turns the look on, so an install that set the variable keeps its answer,
#: and one that never edits its environment file can agree from the console instead.
RELEASE_CHECK: Final = Feature(
    name="release_check",
    title="Look for newer releases",
    what=(
        "Version and updates asks the product's published list of releases whether a newer one "
        "exists, when the page is opened, and says whether this install is behind. The request "
        "goes outside your network."
    ),
    while_off=(
        "Nothing is asked outside your network, and the page says it cannot tell whether this "
        "install is behind. The environment file can still switch the look on for every page."
    ),
    read_by=("brain.install_routes:updates",),
)

#: Merging two entities with nobody looking. Off until the owner decides needs-rupash 155: a
#: merge joins two permission surfaces, and an unattended one does that on a score. A merge a
#: named reviewer decided is never behind this switch.
UNATTENDED_ENTITY_MERGE: Final = Feature(
    name="unattended_entity_merge",
    title="Merge matching records without a reviewer",
    what=(
        "When two records in your connected sources match on a hard identifier, and neither "
        "carries financial records, the product merges them into one entity on its own. Every "
        "such merge is recorded with its evidence and can be undone."
    ),
    while_off=(
        "No two records are merged unless a named reviewer decides it. A merge made while this "
        "was on stays in force and can still be undone."
    ),
    read_by=("brain.resolution.merge_store:merge_entities",),
)

#: Stopping questions when a budget is used up. Off until the owner decides needs-rupash 169: the
#: stop is the hard one he chose, and `brain.ops.budget_stop` records the argument against it. While
#: off, a used-up budget is still recorded as one the install would have stopped, and those records
#: are what the decision is made on.
BUDGET_ENFORCEMENT: Final = Feature(
    name="budget_enforcement",
    title="Stop questions when a budget is used up",
    what=(
        "When a budget runs out, whoever can raise it is told, and questions it covers are not "
        "answered until its period ends: the next day for a daily budget, the first of the "
        "month for a monthly one. Raising the budget lifts the stop at once."
    ),
    while_off=(
        "No question is refused for a budget. A budget that runs out is recorded on the Spend "
        "screen as one the install would have stopped, with when its period ends."
    ),
    read_by=("brain.ops.budget_stop_store:budget_refusal_for",),
)

#: Reviewing a supervised agent's pin on a schedule. Off until the owner decides needs-rupash 174:
#: the review itself is the person-pressed one's, and what is new is that the worker asks it daily
#: and writes the answer as the system. While off the run still decides each due pin and reports
#: how many it would have extended or marked eligible, and writes nothing.
SUPERVISION_REVIEW: Final = Feature(
    name="supervision_review",
    title="Review supervised agents at thirty days on a schedule",
    what=(
        "Each day the product reviews every supervised agent whose thirty days have passed and "
        "records the answer under the name of the system. An agent whose measured confidence is "
        "short, or who has not been reviewed enough, is held for another thirty days; one at or "
        "over the bar is marked as eligible for a person to raise. Nothing is ever released "
        "because a date passed, and raising a rung is still two people's decision."
    ),
    while_off=(
        "No pin is reviewed unless a person presses Review. Each day the product still works out "
        "what it would have decided and records only how many pins that is, writing nothing "
        "about any agent."
    ),
    read_by=("brain.ops.supervision_review:review_switch_is_on",),
)

#: Furnishing a new install's library with the eight starter skills. Off until the owner decides
#: needs-rupash 185: whether they arrive waiting for a person's review, which is the recommended
#: answer and the only one this builds, or approved by the product, which nothing here does.
STARTER_SKILLS_SWITCH: Final = Feature(
    name="starter_skills",
    title="Furnish the library with the starter skills",
    what=(
        "At the next start the library gains eight ready-made skills: an SEO audit, keyword "
        "research, a website health check, ticket analysis, complaint analysis, a monthly SEO "
        "report, proposal generation and website troubleshooting. Each arrives waiting for "
        "review with its example tasks, and no agent can read one until a person has rehearsed "
        "it and approved it."
    ),
    while_off=(
        "The library holds only what an administrator added. Starter skills furnished while this "
        "was on stay in the library, and one an administrator edited, retired or rejected is "
        "never put back."
    ),
    read_by=("brain.ops.starter_skill_store:furnish_skills_when_on",),
)

#: Sharing the start of an agent run's request with everybody. Off because it changes the bytes sent
#: to the model on every run; the owner decided what it may hold (needs-rupash 175, option A) and
#: asked that it ship off until proved on his install with two real questions.
SHARED_TOOL_START: Final = Feature(
    name="shared_tool_start",
    title="Share the start of a model request between people",
    what=(
        "A run's request to the model begins with the same words for everybody, naming only the "
        "tools every person in the company already holds, and what is particular to the person "
        "follows it. A provider charges much less for a start it has seen before, so the second "
        "question on a day costs less to answer. No tool a person may not use is ever named."
    ),
    while_off=(
        "Each run sends the model its tools in one block, as before, and no start is shared on "
        "purpose. Nothing a person is shown changes."
    ),
    read_by=("brain.ops.shared_start:universal_when_on",),
)

#: The website widget's answers written by the model. Off until its owner has seen it on his
#: install: every visitor question then costs a model call, paid by the install, asked by strangers
#: with no budget of their own (needs-rupash 139, option B). The cap is `widget_daily_spend`.
WIDGET_MODEL_ANSWERS: Final = Feature(
    name="widget_model_answers",
    title="Let the website widget write its answers with the model",
    what=(
        "A visitor's question is answered by a short reply the model writes from the passages you "
        "have marked public and from nothing else, with those passages shown beside it. What the "
        "replies cost a day is capped by the figure on the Rate limits screen, and once it is used "
        "up the widget answers with the passages themselves until midnight UTC."
    ),
    while_off=(
        "The widget answers with the published passages, word for word, and no model is called "
        "for a visitor."
    ),
    read_by=("brain.widget_answers:model_answers_on",),
)

#: A person making their own agent. Off until the owner has watched it on his install: it widens who
#: may start the builder from the holders of the install authority to anybody signed in, though only
#: for an agent that nobody but its maker can find (needs-rupash 173 and 189, requirement ANY-060).
PERSONAL_AGENTS: Final = Feature(
    name="personal_agents",
    title="Let each person make their own agent",
    what=(
        "Any signed-in person may make an agent that only they can find and use, from the "
        "builder, without asking anybody. It can reach nothing its maker cannot reach. "
        "Administrators who may make agents already make both kinds, and a team agent is "
        "still made only by them."
    ),
    while_off=(
        "Only people who hold the authority to make agents may start the builder, as before. "
        "A personal agent somebody already has stays theirs and keeps working."
    ),
    read_by=("brain.agents.kinds:personal_agents_on",),
)

#: Counting which documents an agent's answers cite, for the Knowledge section's figures. Off
#: because it is a new record kept on every answer: `brain.ops.agent_item_use` keeps an agent, a
#: document, a day and a count, and no question, person or passage. While off, the section shows no
#: figure rather than noughts.
AGENT_ITEM_COUNTS: Final = Feature(
    name="agent_item_counts",
    title="Count which documents an agent's answers cite",
    what=(
        "Each answer an agent gives adds one to a count for every document it cited, by day, and "
        "the agent's Knowledge section shows beside each document how many answers drew on it in "
        "the last thirty days and which it has not touched. The count records the agent, the "
        "document and the day, and nothing about who asked or what was asked."
    ),
    while_off=(
        "Nothing is counted and the Knowledge section shows no figure beside a document. Counts "
        "already kept stay, and are shown again if the switch is turned back on."
    ),
    read_by=("brain.ops.agent_item_use:counting_is_on",),
)

#: Refusing a skill an agent cannot use. Off until the owner decides needs-rupash 178 and 179: a
#: skill that names tools or knowledge an agent lacks is today assigned and shown with what the
#: agent cannot reach, and refusing it is a change in what an administrator can do in one step.
SKILL_NEEDS: Final = Feature(
    name="skill_needs",
    title="Refuse a skill an agent cannot use",
    what=(
        "Giving a skill to an agent is refused when a tool the skill names is outside the agent's "
        "own tools or when a department whose knowledge it needs is outside the agent's scope. "
        "The refusal names what is missing, and nothing is widened: the agent changes only "
        "through its own publish."
    ),
    while_off=(
        "A skill is given to any agent and the screen shows which of its tools the agent can "
        "reach. A skill given while this was on stays given."
    ),
    read_by=("brain.skill_routes:assign_skill",),
)

#: Drafting a skill from a description. Off because it sends a person's words to a model: an install
#: chooses whether a description of a procedure may leave for the model it has set up. What it
#: drafts is never more than an import, waiting undecided for a second person (M12.4.14).
SKILL_DRAFTING: Final = Feature(
    name="skill_drafting",
    title="Draft a skill from a description",
    what=(
        "An administrator who may add skills describes what a skill should do, and the model "
        "this install has set up drafts its instructions, the departments whose knowledge it "
        "needs, the tools it uses and some example tasks. The draft is added to the library "
        "waiting for review, exactly as a skill imported from a file is, and no agent can read "
        "it until a second person has approved it."
    ),
    while_off=(
        "Skills are added by pasting or uploading a file, or from a repository or an address. A "
        "draft made while this was on stays in the library, waiting for review."
    ),
    read_by=("brain.skill_draft_routes:draft_skill",),
)

#: Writing a new automation on an agent's own page. Off because it is a new way to start unattended
#: work, and the owner decided what a trigger and a condition may be (needs-rupash 177, option A)
#: and asked that it ship off until proved on his install with two real people.
AUTOMATION_AUTHORING: Final = Feature(
    name="automation_authoring",
    title="Write a new automation on an agent's page",
    what=(
        "The agent's Automations section offers New automation: start from a named outcome or from "
        "words, choose when it runs and whether something must be true first, name what the agent "
        "may use, read what it would have done at its last few triggers, and save it. It is saved "
        "paused, runs as the person who wrote it, and somebody else has to start it."
    ),
    while_off=(
        "Automations are installed from the gallery as they are and nothing new can be written. "
        "One written while this was on stays, is shown on the page, and can still be stopped."
    ),
    read_by=("brain.automation_authoring_routes:authoring_is_on",),
)

#: A second person for actions that cannot be taken back. Off until the owner answers needs-rupash
#: 192, which decides whether it covers every sensitive effect (option A, recommended) or money only
#: (option B): `brain.gate.suspension_store.needs_second_person` is the one place that changes.
TWO_PERSON_APPROVAL: Final = Feature(
    name="two_person_approval",
    title="Two different people approve an action that cannot be taken back",
    what=(
        "An approval of an action with a sensitive effect, such as a client message, a payment or "
        "a deletion, needs two different people. The first approves and the action waits; the "
        "second approves and it runs. Neither may be the person who asked for it."
    ),
    while_off=(
        "One person approves such an action, and that person may be the one who asked for it "
        "where the agent's rung allows it. An approval already waiting for a second person "
        "still needs one."
    ),
    read_by=("brain.gate.suspension_store:put_suspension",),
)

#: Recording plugins on the install and moving them between states. Off because it is a new way to
#: put something from outside on an install, and what it records is not run: no runner exists for
#: the points that take code, so an enabled plugin changes a row and nothing else (M29.2.3).
PLUGIN_REGISTRY: Final = Feature(
    name="plugin_registry",
    title="Record plugins on this install",
    what=(
        "An administrator of plugins may add a plugin by its manifest, switch it on, move it to a "
        "later version of itself and return it to one that has run here. The manifest is refused "
        "if it asks for reach, names a point no plugin may take, or is outside this release's "
        "range. Nothing is loaded or run: this keeps the record a runner will read."
    ),
    while_off=(
        "No plugin can be added, switched on, upgraded or rolled back, and the list says so. A "
        "plugin recorded while this was on stays recorded, and can still be switched off and "
        "removed."
    ),
    read_by=(
        "brain.plugin_routes:plugins",
        "brain.plugin_routes:_switched_on",
    ),
)

#: Letting an agent run a browser. Off because it starts a container that opens pages on the
#: install's behalf: the sandbox, the launcher and the runner image have been specified and tested
#: as decisions and have not run on a host, and `brain.browsing.driver` is the first thing that
#: sends a run to one. A run that needs a person's approval still waits for it with this on.
BROWSER_RUNS: Final = Feature(
    name="browser_runs",
    title="Let agents run a browser",
    what=(
        "An agent whose ceiling holds the browser tools may have a page opened for it in a "
        "sandbox of its own, on the websites its target declares and nowhere else. A write "
        "waits for a person to approve the whole run first, and every run is recorded."
    ),
    while_off=(
        "No browser is started. A website check still reads a page over a plain request, as "
        "before. A run that started while this was on is stopped by the halt, not by this."
    ),
    read_by=("brain.browsing.driver:browser_runs_are_on",),
)

#: Every feature this product can switch on, in the order the screen lists them.
FEATURES: Final[tuple[Feature, ...]] = (
    PROMPT_EDITING,
    SCHEDULE_CONTROL,
    RELEASE_CHECK,
    UNATTENDED_ENTITY_MERGE,
    BUDGET_ENFORCEMENT,
    TWO_PERSON_APPROVAL,
    SUPERVISION_REVIEW,
    SHARED_TOOL_START,
    WIDGET_MODEL_ANSWERS,
    PERSONAL_AGENTS,
    AGENT_ITEM_COUNTS,
    SKILL_NEEDS,
    SKILL_DRAFTING,
    AUTOMATION_AUTHORING,
    STARTER_SKILLS_SWITCH,
    PLUGIN_REGISTRY,
    BROWSER_RUNS,
)


def feature(name: str, features: Sequence[Feature] = FEATURES) -> Feature:
    """One declared feature by name, refusing an unknown one rather than answering None."""
    for one in features:
        if one.name == name:
            return one
    msg = f"no feature named {name!r}"
    raise FeatureError(msg)


def switched_on_in(
    states: Mapping[str, SettingState], features: Sequence[Feature] = FEATURES
) -> frozenset[str]:
    """The declared features whose row, keyed by feature name, holds the JSON `true`. See
    `EVERY_FEATURE_SHIPS_SWITCHED_OFF`.

    `is True` rather than truthiness, because the column is jsonb and a person at a prompt can
    write the string `"false"`, which is truthy.
    """
    declared = {one.name for one in features}
    return frozenset(
        name
        for name, state in states.items()
        if name in declared
        and state.value_type == SettingType.BOOLEAN.value
        and state.value is True
    )


async def switch_states(session: AsyncSession) -> dict[str, SettingState]:
    """Every live feature row, by feature name, declared or not. The screen drops the rest."""
    return values_under(await read_namespace(session, FEATURE_NAMESPACE), FEATURE_NAMESPACE)


async def is_on(session: AsyncSession, one: Feature) -> bool:
    """Whether this feature is switched on now. The one question every reader asks."""
    return one.name in switched_on_in(await switch_states(session), (one,))


async def switch(session: AsyncSession, one: Feature, *, on: bool, by: str) -> None:
    """Turn a feature on or off in the caller's transaction.

    Off is written as `false` rather than by retiring the row, so the row goes on saying who
    turned it off and when; retiring it would say the same thing as never having been touched.
    """
    await put(
        session,
        one.key,
        value_type=SettingType.BOOLEAN,
        value=on,
        description=one.title,
        updated_by=by,
    )


# ------------------------------------------------------------------ the reader check
def _functions(tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node


def _asks(function: ast.AST) -> tuple[str, ...]:
    """The names handed as the feature to every `is_on` call inside one function."""
    found: list[str] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        name = called.id if isinstance(called, ast.Name) else getattr(called, "attr", "")
        if name != READER_CALL:
            continue
        for argument in node.args[1:2]:
            found.append(argument.id if isinstance(argument, ast.Name) else ast.unparse(argument))
    return tuple(found)


def _constant_name(one: Feature) -> str:
    """The module-level name this file binds the feature to."""
    for name, value in globals().items():
        if value is one:
            return name
    return ""


def feature_gaps(features: Sequence[Feature] = FEATURES, src: Path = SRC) -> tuple[str, ...]:
    """Every declared reader that does not ask, and every asker nobody declared.

    See `A_SWITCH_NOTHING_READS_IS_A_CONTROL_THAT_REACHES_NOTHING`. The declared readers are
    imported and parsed, so a renamed function is a finding; the undeclared ones are found by
    parsing every module under `src`, and this module's own definition of `is_on` is not a call.
    """
    gaps: list[str] = []
    declared: dict[str, Feature] = {}
    for one in features:
        wanted = _constant_name(one)
        for reader in one.read_by:
            declared[reader] = one
            module_name, _, function_name = reader.partition(":")
            try:
                function = getattr(importlib.import_module(module_name), function_name)
                tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
            except (ImportError, AttributeError, OSError, TypeError):
                gaps.append(f"feature {one.name!r} names {reader}, which does not exist")
                continue
            if wanted not in _asks(tree):
                gaps.append(
                    f"feature {one.name!r} names {reader} as a reader, and it never asks "
                    f"{READER_CALL} about {wanted or one.name}"
                )
    for path in sorted(src.rglob("*.py")):
        module = ".".join(path.relative_to(src.parent).with_suffix("").parts)
        for function in _functions(ast.parse(path.read_text(encoding="utf-8"))):
            if not _asks(function):
                continue
            symbol = f"{module}:{function.name}"
            if symbol not in declared:
                gaps.append(f"{symbol} asks {READER_CALL} and no feature names it as a reader")
    return tuple(gaps)
