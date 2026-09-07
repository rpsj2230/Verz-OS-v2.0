"""How hard the model works, how long the answer may be, and why those are two things.

They are constantly confused because they trade against the same bill, and the confusion has
a symptom in each direction. Fold length into effort and a cheap lane truncates a hard
question halfway through a sentence, which reads to the person asking as the system being
broken rather than as the system being thrifty. Fold effort into length and an expensive lane
writes an essay about a date, which nobody complains about and everybody pays for. So there
are two types here and neither is derivable from the other: `Effort` is a setting on the
call, and `OutputLength` is an instruction in the prompt plus a cap that must never be what
ends the answer.

**Effort is pinned per lane, and pinned means there is no per-request override.** A provider
caches on the request's shape, and the reasoning setting is part of that shape, so a value
that varies request by request means a cache partition per value and a hit rate near zero.
The pin is therefore a lookup on the lane and nothing else, which is what
`THE_PIN_READS_THE_LANE_AND_NOTHING_ELSE` says and what `settings_for` enforces by having no
`effort` parameter at all. There is nothing to remember. A caller who wants more effort asks
for the task lane, which is a decision `brain.gate.classify` makes and records, rather than a
knob on one request that quietly costs everybody else their cache.

**Output length does have a per-request override, and that is the difference in one line.**
Its instruction lives after the cache breakpoint, in `PromptLayout.variable`, so varying it
costs the request that varied it and nobody else. That is the practical reason the two axes
are separate as well as the honest one: one of them can move per request without externality
and the other cannot.

**The lane is the only per-request value a pin may read.** A lane is a bucket that many
callers share, not a caller, and it is decided before anything expensive by a classifier that
makes no model call. Anything else from the request, and the question above all, turns a
lookup into a computation: a pin that reads the words would produce a different setting for
two phrasings of the same question, which is a cache partition per phrasing.

**Nothing here is a permission decision and nothing here may become one.** Effort and length
are about cost and shape. A model working harder does not see more, and an answer allowed to
be longer does not carry more: what a caller may see is settled by `brain.core.redaction`
before any of this is reached. There is deliberately no field on `ModelSettings` that could
be read as reach.

Rejected: deriving the effort from the tool count, the context estimate or the question's
length, which is what `brain.models.routing.classify_tier` already does for the *tier*. Those
are per-request numbers, so the derived effort would be per-request, which is the thing this
leaf exists to prevent. The tier and the effort are different levers and it is fine for one
to be computed and the other pinned: a tier change moves the request to another pool, which
has its own cache anyway, while an effort change re-partitions the pool the request stays in.

Rejected also: putting the effort in the prompt as words ("think carefully"). It is a call
parameter, so it belongs in `DriverRequest.extra` where a trace can replay it, and text
telling a model to try harder is a request rather than a setting.

Task ids: M6.4.3, M6.4.4
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import assert_never

from brain.core.lane import Lane

# ------------------------------------------------------------------ written-down reasons
#: Why the pin is a lookup on the lane and reads nothing else about the request.
THE_PIN_READS_THE_LANE_AND_NOTHING_ELSE = (
    "The pin exists to keep the provider cache shared, so anything that makes it vary "
    "within a lane defeats it. A lane is a bucket many callers share and is decided by a "
    "classifier that makes no model call, so reading it is a lookup. Reading the question, "
    "the principal, the entitlements or the channel would make the effort a per-request "
    "value, which is a cache partition per value and a hit rate near zero. The failure is "
    "invisible: every answer is still correct and the only symptom is the bill."
)

#: Why effort has no per-request override and output length does.
EFFORT_IS_PINNED_AND_LENGTH_IS_NOT = (
    "Effort is part of the request shape a provider caches on, so one caller raising it "
    "costs every other caller on that lane their cache. Output length is an instruction "
    "that sits after the cache breakpoint, so one caller shortening it costs that request "
    "and nothing else. That asymmetry is why settings_for takes a length and does not take "
    "an effort: the parameter that exists is the one whose cost falls on whoever sets it."
)

#: Why the cap is not the thing that ends an answer.
THE_INSTRUCTION_ENDS_THE_ANSWER_NOT_THE_CAP = (
    "A token cap that bites cuts a sentence in half, and a half sentence about a client's "
    "invoice reads as a broken system rather than as a brief answer. So the instruction "
    "asks for a length and the cap sits well above what it asked for, as a stop on a "
    "runaway rather than as the shaping mechanism. OutputLength refuses a cap too close to "
    "its own instruction, so the relation holds for any length added later."
)

#: Why an effort setting is not a permission.
EFFORT_IS_NOT_REACH = (
    "A model working harder does not see more. Reach is settled by the projected catalogue "
    "and by the redaction walker before anything here is consulted, and there is no field "
    "on ModelSettings that a future reader could take for an entitlement. The one thing "
    "this module must never become is a second place where what a caller may see is decided."
)


# ------------------------------------------------------------------------------- effort
class Effort(enum.StrEnum):
    """How much work the provider is asked to do on one call.

    Four members rather than three, because the fast lane's honest answer is not "a small
    amount" but "none": no model reads the question at all, and a value meaning that is what
    lets `effort_for` stay total. `brain.models.driver.ProviderClient.policy_for` refuses the
    fast lane for the same reason, and the two refusals agree.
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


#: Least to most work. `Effort` is a `StrEnum` and carries no order of its own, so a
#: comparison needs one stated somewhere; the same device, for the same reason, as
#: `brain.gate.catalogue.SIDE_EFFECT_ORDER`. Written as a ladder rather than as integer
#: values on the enum so that a member inserted in the middle is a visible edit here rather
#: than a renumbering that silently reorders every comparison.
EFFORT_LADDER: tuple[Effort, ...] = (Effort.NONE, Effort.LOW, Effort.MEDIUM, Effort.HIGH)


def effort_rank(effort: Effort) -> int:
    """Where an effort sits on the ladder, so two of them can be compared."""
    return EFFORT_LADDER.index(effort)


#: The provider vocabulary word this setting travels under, and the only one in this module.
#: It feeds `brain.models.driver.DriverRequest.extra`, which is passed through untouched, so
#: a provider that spells it differently is one line in the adapter rather than a change to
#: the policy here. Held as a constant so that line has something to point at.
EFFORT_PARAMETER = "reasoning_effort"


# ------------------------------------------------------------------------- output length
#: How much room the cap leaves above what the instruction asked for. Three, because a token
#: is a fraction of a word, so a cap of three tokens per requested word is comfortably above
#: the length being asked for in every case. The number matters far less than the direction:
#: see `THE_INSTRUCTION_ENDS_THE_ANSWER_NOT_THE_CAP`.
TRUNCATION_HEADROOM = 3


@dataclass(frozen=True)
class OutputLength:
    """How long an answer may be: what to ask for, and where to stop regardless.

    `target_words` is data rather than a number buried in the instruction's English, so the
    cap beside it can be checked against it. The validator below is what makes that pair
    inseparable: a cap lowered without the instruction moving, or an instruction rewritten to
    ask for more without the cap following, is refused at import rather than discovered as a
    sentence that stops halfway.
    """

    name: str
    #: What the instruction asks for, in words.
    target_words: int
    #: Where the provider is told to stop, in tokens. A runaway stop, not a shaping tool.
    max_output_tokens: int
    #: The sentence the model actually reads. Goes after the cache breakpoint.
    instruction: str

    def __post_init__(self) -> None:
        if not self.name:
            msg = "an output length needs a name; the console renders it and a trace cites it"
            raise ValueError(msg)
        if self.target_words < 1:
            msg = f"output length {self.name!r} asks for {self.target_words} words"
            raise ValueError(msg)
        if str(self.target_words) not in self.instruction:
            # The instruction is what the model obeys and `target_words` is what everything
            # else reasons about. Two numbers that are meant to be one is how they drift.
            msg = (
                f"output length {self.name!r} asks for {self.target_words} words but its "
                "instruction does not say so, so the two can drift apart silently"
            )
            raise ValueError(msg)
        if self.max_output_tokens < self.target_words * TRUNCATION_HEADROOM:
            msg = (
                f"output length {self.name!r} caps at {self.max_output_tokens} tokens while "
                f"asking for {self.target_words} words, so the cap is what would end the "
                f"answer. {THE_INSTRUCTION_ENDS_THE_ANSWER_NOT_THE_CAP}"
            )
            raise ValueError(msg)


BRIEF = OutputLength(
    name="brief",
    target_words=60,
    max_output_tokens=400,
    instruction="Answer in about 60 words. Give the figure and the record it came from, then stop.",
)

NORMAL = OutputLength(
    name="normal",
    target_words=200,
    max_output_tokens=1_200,
    instruction=(
        "Answer in about 200 words. Use a short list where a list is clearer than a paragraph."
    ),
)

FULL = OutputLength(
    name="full",
    target_words=900,
    max_output_tokens=8_000,
    instruction=(
        "Answer in about 900 words. Set out what you checked, and what you could not see, "
        "as well as the answer itself."
    ),
)

#: Every length the system ships, shortest first. A tuple rather than a set so the console
#: renders them in a sensible order without sorting on a field that might change.
OUTPUT_LENGTHS: tuple[OutputLength, ...] = (BRIEF, NORMAL, FULL)

#: Derived, never maintained by hand, so a renamed length cannot leave a stale key behind.
OUTPUT_LENGTHS_BY_NAME: Mapping[str, OutputLength] = MappingProxyType(
    {length.name: length for length in OUTPUT_LENGTHS}
)


# --------------------------------------------------------------------------- the settings
@dataclass(frozen=True)
class ModelSettings:
    """The two axes together, for one call.

    Two fields and no third. There is no reach here, no tool list and no principal: see
    `EFFORT_IS_NOT_REACH`. What a caller may see was settled before this object existed.
    """

    effort: Effort
    length: OutputLength

    def __post_init__(self) -> None:
        if self.effort is Effort.NONE:
            # **The only implementation of "no model means no call settings."** A lane whose
            # effort is NONE takes no model, and every guarantee downstream of that (an empty
            # tool catalogue, reads restricted to projected tables) was built on it. Held on
            # the type rather than at the entry point because a check on the constructor
            # covers direct construction too, and `settings_for` is not the only way here.
            # It names the effort rather than a lane, because a lane is not what it was
            # given; `settings_for` adds that.
            msg = (
                "Effort.NONE means no model reads the question, so there is nothing to "
                "configure; settings carrying it describe a call that must not happen"
            )
            raise ValueError(msg)

    @property
    def max_output_tokens(self) -> int:
        """The cap, in the shape `DriverRequest.max_output_tokens` takes."""
        return self.length.max_output_tokens

    @property
    def instruction(self) -> str:
        """The sentence that goes after the cache breakpoint, in `PromptLayout.variable`.

        A property rather than a field, so there is one instruction and it is the one on the
        length. A copy on the settings would be a second place for it to be edited, and the
        copy that goes stale is the one being sent.
        """
        return self.length.instruction

    def as_extra(self) -> Mapping[str, str]:
        """The call parameters, in the shape `DriverRequest.extra` takes.

        Strings, because that field is `Mapping[str, str]` deliberately: a knob that cannot
        be serialised is a request that cannot be replayed from a trace. The output cap is
        not in here, because it has its own field on the request rather than being a
        provider-specific extra.
        """
        return MappingProxyType({EFFORT_PARAMETER: self.effort.value})


# ------------------------------------------------------------------------------- the pins
def effort_for(lane: Lane) -> Effort:
    """The pinned effort for a lane. A lookup, and a function of the lane alone.

    Written as a `match` with `assert_never` rather than as a dictionary lookup, because a
    dictionary with a `.get` default would accept a lane nobody has thought about and hand
    back whatever the default happened to be. This way a member added to `Lane` is a type
    error until somebody decides what it costs, which is the same device
    `brain.gate.context.traffic_class_for` uses for the traffic class.

    MEDIUM for the answer lane and HIGH for the task lane, and the gap is the whole ladder:
    a person is waiting on the answer lane and roughly 95% of traffic is on it, so its
    setting is what the bill mostly is; nobody is watching the task lane, and a wrong answer
    there is acted on by an agent rather than read by somebody who can tell.
    """
    match lane:
        case Lane.FAST:
            return Effort.NONE
        case Lane.ANSWER:
            return Effort.MEDIUM
        case Lane.TASK:
            return Effort.HIGH
        case _:
            assert_never(lane)


def default_length_for(lane: Lane) -> OutputLength:
    """The lane's default answer length. A default, and unlike the effort it is overridable.

    Total for the same reason `effort_for` is. `Lane.FAST` gets BRIEF although no model
    speaks on that lane: the fast lane's answer is a projected row rendered by us, and the
    honest default for "a figure and where it came from" is the shortest length there is. It
    is never handed to a provider, because `ModelSettings` refuses `Effort.NONE`.
    """
    match lane:
        case Lane.FAST:
            return BRIEF
        case Lane.ANSWER:
            return NORMAL
        case Lane.TASK:
            return FULL
        case _:
            assert_never(lane)


#: Derived from the functions above rather than written beside them, so the table the console
#: renders and the pin the gate applies cannot disagree. The same reason
#: `brain.agents.catalogue.catalogue_by_id` derives its index.
EFFORT_BY_LANE: Mapping[Lane, Effort] = MappingProxyType({lane: effort_for(lane) for lane in Lane})

DEFAULT_LENGTH_BY_LANE: Mapping[Lane, OutputLength] = MappingProxyType(
    {lane: default_length_for(lane) for lane in Lane}
)


def settings_for(lane: Lane, *, length: OutputLength | None = None) -> ModelSettings:
    """The settings for one call: the lane's pinned effort, and a length that may be asked for.

    **Look at what this signature does not have.** There is no `effort` parameter and there
    must never be one; see `EFFORT_IS_PINNED_AND_LENGTH_IS_NOT`. A caller wanting more effort
    asks for the task lane, which `brain.gate.classify` decides and records in the trace, so
    the decision is visible and belongs to a bucket rather than to one request.

    Raises for the fast lane rather than returning something plausible, matching
    `ProviderClient.policy_for`. Two modules that both know the fast lane takes no model must
    refuse it the same way, or the one that does not is the path the bug takes.

    That refusal is re-raised rather than checked again here, and the distinction matters. A
    second `if effort is Effort.NONE` would be a second copy of the rule, and the copy that
    goes wrong is the one in production. What this adds is the lane, which is what the caller
    passed and what they can act on: `ModelSettings` was handed an effort and cannot name a
    lane it never saw. The same shape as `gate.invoke` re-raising an `EmptyCatalogueError`
    as a refusal.
    """
    try:
        return ModelSettings(
            effort=effort_for(lane),
            length=length or default_length_for(lane),
        )
    except ValueError as exc:
        # The original travels in the message as well as in the chain, so a ValueError
        # raised here for some future reason is still readable rather than relabelled.
        msg = (
            f"the {lane} lane takes no model, so there are no call settings for it; a "
            f"request assembling them has already left the lane's guarantees behind ({exc})"
        )
        raise ValueError(msg) from exc
