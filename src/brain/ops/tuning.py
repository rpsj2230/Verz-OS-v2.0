"""Budgets and rate limits as rows a person changes from the console, within the product's bounds.

Until this module every capacity budget (`brain.ops.admission.seed_budgets`) and every request
window (`brain.ops.limits.DEFAULT_PRINCIPAL_PER_MINUTE` and its two siblings) was a constant, and
the one route that asked admission anything, the queued upload, handed it `seed_budgets()` itself.
`seed_budgets` says of its own rows "not a runtime source of truth", and nothing else was one: an
administrator who needed a tighter window on a misbehaving channel, or a lower document budget on
a small machine, needed a release. Architecture section 25 says in as many words that "all of these
are configuration rows, not constants", and M22.4.1 asks for them to be changed from the console
within bounds the product fixes, each change audited and in force without a release.

**The rows are `ops.setting` rows in the `tuning` namespace, and there is no migration.**
`brain.ops.setting_store` argues for that table at length: a typed value, a key grammar that cannot
parse as a capability, one live row per key, and since `0059` a trigger that appends a `setting`
entry to the audit ledger for every write that moves a row, naming the key and the writer and never
the value. That trigger is the "each change audited" half of the leaf, and it is the database's, so
no caller can write a row and forget the entry. Rejected: a `capacity_budget` table of its own,
which would need a migration, a second row-level security policy and an audit trigger of its own to
hold the same four facts.

**What a person may set is a closed list of knobs, each with the product's own bounds.** A value
outside a knob's bounds is refused before it is written, with the bounds in the sentence, and a
saved value that a later release's bounds no longer admit is read as the product's default rather
than trusted, because a bound tightened in a release is a bound the product now depends on. See
`A_SAVED_VALUE_OUTSIDE_THE_BOUNDS_IS_NOT_USED`. The bounds are written beside each knob with the
reason for them, because the first question about a bound is why it is not wider.

**A saved value is held by every process within a minute, and never read on the request path.**
`brain.ops.install_settings.refresh` and `refresh_changed` load this namespace in the same
transaction as the installation values: the application loads it when it starts and again every
minute (`keep_holding`), and the worker before every tick. The request path reads what is held,
which costs a dictionary lookup rather than a query per request. See
`A_TUNED_VALUE_REACHES_EVERY_PROCESS_WITHIN_A_MINUTE`.

**The held values are this module's and the readers ask for them by knob.** `brain.ops.limits`
asks `per_minute` for a window's allowance when a caller gave none, so `request_limits`,
`limit_for` and `declared_windows` all follow a saved value at once and cannot disagree, which is
the property `limit_for` was written around. The capacity readers ask `configured_budgets`, which
is `seed_budgets` with each saved limit laid over its row and the row's source saying so.

Task ids: M22.1.2, M22.4.1
"""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from brain.memory.formation import HALF_LIFE_DAYS, RECALL_FLOOR
from brain.memory.tiers import PROMOTION_AGREEMENT
from brain.memory.turn import EXTRACTED_CONFIDENCE
from brain.ops.admission import Budget, Resource, seed_budgets
from brain.ops.limits import (
    DEFAULT_AGENT_PER_MINUTE,
    DEFAULT_CHANNEL_PER_MINUTE,
    DEFAULT_PRINCIPAL_PER_MINUTE,
    LimitScope,
)
from brain.ops.setting_store import put, read_namespace, values_under
from brain.tables.config import SettingType

# ------------------------------------------------------------------ written-down reasons
#: Why a saved value a release no longer admits is read as the default.
A_SAVED_VALUE_OUTSIDE_THE_BOUNDS_IS_NOT_USED: Final = (
    "A value is refused outside its bounds when it is saved, and a saved value is checked again "
    "when it is read. A release that tightens a bound does so because the product now depends on "
    "it, so a row saved under the old bound is read as the product's default until somebody saves "
    "a value inside the new one, rather than holding the install outside what the product admits."
)

#: When a change is in force, in words, for the console and the tests.
A_TUNED_VALUE_REACHES_EVERY_PROCESS_WITHIN_A_MINUTE: Final = (
    "A saved value is held at once by the process that saved it, by every other application "
    "process at its next minute's reload of saved settings, and by the worker before its next "
    "tick. No release and no restart is needed, and no request reads the table."
)

#: The sentence a refusal of an unknown knob gives. Names nothing the install holds.
NOT_A_KNOB: Final = "That is not a limit this screen changes."

#: Why a setting can make learning slower or quicker to offer and never less supervised.
NO_SETTING_MOVES_A_CHANGE_TO_A_LOWER_TIER: Final = (
    "Which oversight a learned change needs is decided by what it would reach, in "
    "`brain.memory.tiers.blast_radius`, which takes the change and nothing else. The learning "
    "settings are a decay and a count: the decay decides how long an inference is recalled, the "
    "count decides when a tier-two rule is offered to a person, and neither is read by the tier "
    "map, so no figure saved on any install lets a change take effect with less agreement than "
    "its reach needs."
)

#: Why an install check's reading of its own rows reaches no other request.
A_READING_IS_LENT_TO_ONE_TASK_AND_NEVER_HELD: Final = (
    "`reading` sets a context variable, which asyncio copies into each task when the task is "
    "made, so the rows it lends are read by what the lending task calls and by nothing any other "
    "request is doing. It is reset on the way out whatever happened. Holding the rows instead "
    "would put a figure saved in a transaction that is about to be rolled back in front of every "
    "request the process serves until the next reload."
)

#: The knob that sets how quickly an inferred memory fades, by name.
INFERRED_HALF_LIFE: Final = "inferred_memory_half_life_days"

#: The knob that sets how many independent agreements make a learned rule eligible for review.
PROMOTION_AGREEMENT_KNOB: Final = "promotion_agreement"

#: The namespace every row here sits under.
TUNING_NAMESPACE: Final = "tuning"


class KnobKind(enum.StrEnum):
    """Whether a knob is a request window, a capacity budget or a learning figure."""

    RATE = "rate"
    BUDGET = "budget"
    #: How learning behaves. Names no window and no resource; the Learning screen lists these.
    LEARNING = "learning"


@dataclass(frozen=True)
class Knob:
    """One value a person may set, with the product's default and bounds and why they are those.

    `resource` and `connector` say which capacity budget a BUDGET knob sets; `scope` says which
    request window a RATE knob sets. Exactly one of the two is set, which `__post_init__` holds.
    """

    name: str
    kind: KnobKind
    label: str
    unit: str
    default: int
    lowest: int
    highest: int
    bounds_because: str
    resource: Resource | None = None
    connector: str = ""
    scope: LimitScope | None = None

    def __post_init__(self) -> None:
        if not self.lowest <= self.default <= self.highest:
            msg = f"knob {self.name} has a default outside its own bounds"
            raise ValueError(msg)
        if self.lowest < 1:
            # A zero allowance switches a door off while the row reads as configured, which is
            # `brain.ops.admission.Budget`'s own reason for refusing a limit below one.
            msg = f"knob {self.name} admits a value below one"
            raise ValueError(msg)
        if (self.kind is KnobKind.BUDGET) != (self.resource is not None):
            msg = f"knob {self.name} is a budget exactly when it names a resource"
            raise ValueError(msg)
        if (self.kind is KnobKind.RATE) != (self.scope is not None):
            msg = f"knob {self.name} is a rate exactly when it names a window"
            raise ValueError(msg)

    def admits(self, value: int) -> bool:
        return self.lowest <= value <= self.highest

    @property
    def key(self) -> str:
        return f"{TUNING_NAMESPACE}.{self.name}"


def _seeded(resource: Resource, connector: str = "") -> int:
    """The seed row's limit, so a knob's default can never drift from the budget it sets."""
    for one in seed_budgets():
        if one.resource is resource and one.key == connector:
            return one.limit
    msg = f"no seed budget for {resource}/{connector or '*'}"
    raise LookupError(msg)


def _source_calls(connector: str, label: str, highest: int, because: str) -> Knob:
    return Knob(
        name=f"source_calls_{connector or 'other'}",
        kind=KnobKind.BUDGET,
        label=label,
        unit="calls at once",
        default=_seeded(Resource.SOURCE_CALLS, connector),
        lowest=1,
        highest=highest,
        bounds_because=because,
        resource=Resource.SOURCE_CALLS,
        connector=connector,
    )


#: Every value a person may set, in the order the console lists them.
KNOBS: Final[tuple[Knob, ...]] = (
    Knob(
        name="person_per_minute",
        kind=KnobKind.RATE,
        label="Questions one person may ask a minute",
        unit="a minute",
        default=DEFAULT_PRINCIPAL_PER_MINUTE,
        lowest=5,
        highest=120,
        bounds_because=(
            "Below five, a person asking follow-up questions in a busy minute is refused. Above "
            "a hundred and twenty, the window no longer catches a loop before the channel's does."
        ),
        scope=LimitScope.PRINCIPAL,
    ),
    Knob(
        name="channel_per_minute",
        kind=KnobKind.RATE,
        label="Questions one channel may carry a minute",
        unit="a minute",
        default=DEFAULT_CHANNEL_PER_MINUTE,
        lowest=30,
        highest=1200,
        bounds_because=(
            "Below thirty, one busy group chat refuses everybody in it. Above twelve hundred, a "
            "misbehaving integration is no longer contained by its channel."
        ),
        scope=LimitScope.CHANNEL,
    ),
    Knob(
        name="agent_per_minute",
        kind=KnobKind.RATE,
        label="Runs one agent may make a minute",
        unit="a minute",
        default=DEFAULT_AGENT_PER_MINUTE,
        lowest=10,
        highest=600,
        bounds_because=(
            "Below ten, an agent a department shares refuses its own people. Above six hundred, "
            "a looping agent runs for a minute before anything stops it."
        ),
        scope=LimitScope.AGENT,
    ),
    Knob(
        name="model_calls",
        kind=KnobKind.BUDGET,
        label="Model calls at once, across the install",
        unit="calls at once",
        default=_seeded(Resource.MODEL_CALLS),
        lowest=2,
        highest=200,
        bounds_because=(
            "Below two, one long answer holds every question behind it. Above two hundred, the "
            "providers' own concurrency refuses first and the budget protects nothing."
        ),
        resource=Resource.MODEL_CALLS,
    ),
    _source_calls(
        "lark_base",
        "Calls to Lark Base at once",
        8,
        "Lark Base allows 100 requests a minute and no plan raises it: at the five-second "
        "connector timeout eight calls in flight reach that ceiling, so more produce only "
        "refusals.",
    ),
    _source_calls(
        "xero",
        "Calls to Xero at once",
        5,
        "Xero allows 60 calls a minute per organisation, shared with its other integrations: at "
        "the five-second timeout five calls in flight reach it, so more produce only refusals.",
    ),
    _source_calls(
        "freshdesk",
        "Calls to Freshdesk at once",
        58,
        "Freshdesk allows between 100 and 700 requests a minute by plan: fifty-eight calls in "
        "flight reach the highest plan's ceiling at the five-second timeout.",
    ),
    _source_calls(
        "",
        "Calls at once to any other connected system",
        8,
        "A system nobody has measured has a ceiling nobody knows, so its budget stays low.",
    ),
    Knob(
        name="browser_sessions",
        kind=KnobKind.BUDGET,
        label="Browser sessions at once",
        unit="sessions at once",
        default=_seeded(Resource.BROWSER_SESSIONS),
        lowest=1,
        highest=8,
        bounds_because=(
            "Each session holds hundreds of megabytes; eight is more than the largest profile's "
            "browser container is sized for."
        ),
        resource=Resource.BROWSER_SESSIONS,
    ),
    Knob(
        name="long_running_tasks",
        kind=KnobKind.BUDGET,
        label="Long-running tasks at once",
        unit="tasks at once",
        default=_seeded(Resource.LONG_RUNNING_TASKS),
        lowest=1,
        highest=40,
        bounds_because="Forty is four times the machine section 25 sizes for ten.",
        resource=Resource.LONG_RUNNING_TASKS,
    ),
    Knob(
        name="document_jobs",
        kind=KnobKind.BUDGET,
        label="Documents read at once",
        unit="documents at once",
        default=_seeded(Resource.DOCUMENT_JOBS),
        lowest=1,
        highest=16,
        bounds_because=(
            "Reading a document is work for the processor that answers questions too; sixteen at "
            "once would take every core of the largest profile."
        ),
        resource=Resource.DOCUMENT_JOBS,
    ),
    Knob(
        name="embedding_jobs",
        kind=KnobKind.BUDGET,
        label="Embedding jobs at once",
        unit="jobs at once",
        default=_seeded(Resource.EMBEDDING_JOBS),
        lowest=1,
        highest=16,
        bounds_because="Sized with documents read at once, for the same reason.",
        resource=Resource.EMBEDDING_JOBS,
    ),
    Knob(
        name="tokens_per_minute",
        kind=KnobKind.BUDGET,
        label="Model tokens a minute, across the install",
        unit="tokens a minute",
        default=_seeded(Resource.TOKENS_PER_MINUTE),
        lowest=20_000,
        highest=2_000_000,
        bounds_because=(
            "Below twenty thousand, two long answers fill the minute. Above two million, the "
            "providers' own rate limits refuse first."
        ),
        resource=Resource.TOKENS_PER_MINUTE,
    ),
    Knob(
        name=INFERRED_HALF_LIFE,
        kind=KnobKind.LEARNING,
        label="Days an inferred memory takes to lose half its weight",
        unit="days",
        default=round(HALF_LIFE_DAYS),
        lowest=10,
        highest=365,
        bounds_because=(
            "Below ten days, a memory inferred at the start of a week is no longer recalled by "
            "the time that week's digest offers to undo it. Above a year, an inference about how "
            "somebody works outlasts the way they work. A memory somebody states does not fade, "
            "whatever this says."
        ),
    ),
    Knob(
        name=PROMOTION_AGREEMENT_KNOB,
        kind=KnobKind.LEARNING,
        label="Separate conversations that must agree before a learned rule is offered for review",
        unit="conversations",
        default=PROMOTION_AGREEMENT,
        lowest=2,
        highest=10,
        bounds_because=(
            "Below two, one conversation is enough, and one person's way of phrasing a question "
            "becomes a rule offered for review. Above ten, a rule would need more evidence than "
            "an agent needs to be trusted with less supervision, which changes more. A person "
            "still approves every rule, whatever this says."
        ),
    ),
)

#: The knobs by name.
KNOB_BY_NAME: Final[Mapping[str, Knob]] = MappingProxyType({one.name: one for one in KNOBS})

_HELD: dict[str, int] = {}

#: Rows one task lent itself with `reading`. None outside one, which is every request.
_READING: ContextVar[Mapping[str, int] | None] = ContextVar("tuning_reading", default=None)


# ------------------------------------------------------------------------ holding
def hold(values: Mapping[str, int]) -> Mapping[str, int]:
    """Hold these as this process's tuned values, and return the ones they replaced.

    The whole mapping at once, for `brain.install.hold_saved`'s reason: a partial update would
    make "nothing is saved" and "nothing has been loaded" the same thing. Names that are not knobs
    are dropped here, so there is one place a row nothing declares stops being configuration.
    """
    before = dict(_HELD)
    _HELD.clear()
    _HELD.update({name: int(value) for name, value in values.items() if name in KNOB_BY_NAME})
    return MappingProxyType(before)


def held() -> Mapping[str, int]:
    """What this process holds now, by knob name."""
    return MappingProxyType(dict(_HELD))


@contextmanager
def reading(saved: Mapping[str, int]) -> Iterator[None]:
    """Read these rows instead of what the process holds, in this task and what it calls only.

    For an install check that saved a figure in a transaction it will roll back and must ask the
    product's own readers what they decide under it. See
    `A_READING_IS_LENT_TO_ONE_TASK_AND_NEVER_HELD`.
    """
    token = _READING.set(MappingProxyType(dict(saved)))
    try:
        yield
    finally:
        _READING.reset(token)


def _in_force(saved: Mapping[str, int] | None) -> Mapping[str, int]:
    """The rows to read: the caller's, else the ones this task was lent, else the held ones."""
    if saved is not None:
        return saved
    lent = _READING.get()
    return _HELD if lent is None else lent


def value(name: str, saved: Mapping[str, int] | None = None) -> int:
    """The value in force for one knob: saved and within bounds, or the product's default.

    `saved` is what to read instead of this process's held values, for a caller that has read the
    rows itself and must not change what the process holds, which is what an acceptance check is.
    See `A_SAVED_VALUE_OUTSIDE_THE_BOUNDS_IS_NOT_USED`.
    """
    knob = KNOB_BY_NAME[name]
    found = _in_force(saved).get(name)
    if found is None or not knob.admits(found):
        return knob.default
    return found


def is_saved(name: str, saved: Mapping[str, int] | None = None) -> bool:
    """Whether a saved value is what is in force for this knob, rather than the default."""
    knob = KNOB_BY_NAME[name]
    found = _in_force(saved).get(name)
    return found is not None and knob.admits(found)


def inferred_half_life_days(saved: Mapping[str, int] | None = None) -> float:
    """How many days an inferred memory takes to lose half its weight, as in force now."""
    return float(value(INFERRED_HALF_LIFE, saved))


def promotion_agreement(saved: Mapping[str, int] | None = None) -> int:
    """How many separate conversations must agree before a tier-two rule is offered for review."""
    return value(PROMOTION_AGREEMENT_KNOB, saved)


def inferred_lifetime_days(half_life_days: float) -> int:
    """About how many days an inference is recalled for, from the day it forms, at a half-life.

    An inference forms at `brain.memory.turn.EXTRACTED_CONFIDENCE` and stops being recalled when
    it decays below `brain.memory.formation.RECALL_FLOOR`, so this is the number of half-lives
    between the two, in days, rounded down: the last whole day it is still recalled.
    """
    return math.floor(half_life_days * math.log2(EXTRACTED_CONFIDENCE / RECALL_FLOOR))


def lifetime_sentence(saved: Mapping[str, int] | None = None) -> str:
    """What the half-life in force means for a person, in words, for the Learning screen."""
    days = inferred_lifetime_days(inferred_half_life_days(saved))
    return (
        f"At the figure in force, an inferred memory stops being recalled about {days} days "
        "after it forms. A memory somebody states does not fade."
    )


_RATE_KNOB: Final[Mapping[LimitScope, str]] = MappingProxyType(
    {one.scope: one.name for one in KNOBS if one.scope is not None}
)


def per_minute(scope: LimitScope, saved: Mapping[str, int] | None = None) -> int:
    """One request window's allowance a minute, as `brain.ops.limits` asks for it."""
    return value(_RATE_KNOB[scope], saved)


def budget_knob(resource: Resource, connector: str = "") -> Knob | None:
    """The knob that sets one budget row, or None for a row no knob sets."""
    for one in KNOBS:
        if one.resource is resource and one.connector == connector:
            return one
    return None


def configured_budgets(saved: Mapping[str, int] | None = None) -> tuple[Budget, ...]:
    """`seed_budgets`, with every saved limit laid over its row and the row saying so."""
    rows: list[Budget] = []
    for seed in seed_budgets():
        knob = budget_knob(seed.resource, seed.key)
        if knob is None or not is_saved(knob.name, saved):
            rows.append(seed)
            continue
        rows.append(
            dataclasses.replace(
                seed,
                limit=value(knob.name, saved),
                source="saved",
                reason=f"Set on the Rate limits screen. The product's figure: {seed.reason}",
            )
        )
    return tuple(rows)


# ------------------------------------------------------------------------ the rows
def problem(name: str, raw: object) -> str:
    """Why this value cannot be saved for this knob, or empty when it can."""
    knob = KNOB_BY_NAME.get(name)
    if knob is None:
        return NOT_A_KNOB
    if isinstance(raw, bool) or not isinstance(raw, int):
        return f"{knob.label} is a whole number."
    if not knob.admits(raw):
        return (
            f"{knob.label} is between {knob.lowest:,} and {knob.highest:,}. {knob.bounds_because}"
        )
    return ""


class TuningRefusedError(ValueError):
    """A value was refused before it was written. The message is `problem`'s sentence."""


async def save(session: AsyncSession, name: str, amount: int, *, updated_by: str) -> None:
    """Write one knob's value in the caller's transaction. The caller commits and attributes it.

    The audit entry is the table trigger's, appended in the same transaction, so the caller's only
    duty is `brain.tables.audit.attributed_to`, which names who wrote it.
    """
    said = problem(name, amount)
    if said:
        raise TuningRefusedError(said)
    knob = KNOB_BY_NAME[name]
    await put(
        session,
        knob.key,
        value_type=SettingType.INTEGER,
        value=amount,
        description=knob.label,
        updated_by=updated_by,
    )


async def load(session: AsyncSession) -> dict[str, int]:
    """Every saved knob value, by name. A row of another shape or no knob is left out."""
    rows = values_under(await read_namespace(session, TUNING_NAMESPACE), TUNING_NAMESPACE)
    return {
        name: int(state.value)
        for name, state in rows.items()
        if name in KNOB_BY_NAME
        and state.value_type == SettingType.INTEGER.value
        and isinstance(state.value, int)
        and not isinstance(state.value, bool)
    }


def knobs_of(kind: KnobKind) -> Sequence[Knob]:
    """The knobs of one kind, in the console's order."""
    return tuple(one for one in KNOBS if one.kind is kind)


#: The kinds the Rate limits screen lists and sets. The Learning screen's are the rest.
LIMIT_KINDS: Final[frozenset[KnobKind]] = frozenset({KnobKind.RATE, KnobKind.BUDGET})

#: The kinds the Learning screen lists and sets.
LEARNING_KINDS: Final[frozenset[KnobKind]] = frozenset({KnobKind.LEARNING})
