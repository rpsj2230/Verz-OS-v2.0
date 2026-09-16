"""Which genuinely new features an install has switched on, and what reads each switch.

CLAUDE.md says a genuinely new feature "goes into this repository behind a flag and ships to
everyone switched off", and until this module there was no flag to put one behind. What existed
were switches for one kind of thing each: a routing rung's `enabled` column, the plugin
lifecycle's four states with nothing loading a plugin, a connector registry nothing constructs,
and `Settings.release_check`, which is read from the environment and so cannot be turned from a
browser. None of them is a place a new feature can be declared and turned on by an administrator
without a shell.

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

Task ids: none
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
    read_by=("brain.jobs_routes:jobs", "brain.jobs_routes:pause_job", "brain.jobs_routes:run_job"),
)

#: Every feature this product can switch on, in the order the screen lists them.
FEATURES: Final[tuple[Feature, ...]] = (PROMPT_EDITING, SCHEDULE_CONTROL)


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
