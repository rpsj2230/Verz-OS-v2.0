"""What a model is shown for one turn, assembled in one place, and named in the trace (M16.6.1).

Until this module the parts of a turn's context arrived at the prompt as separate arguments, each
fetched by whoever happened to need it: `brain.gate.model_lane.draft` read the asker's memories
just before the call, took the thread's earlier questions off a `FollowUp`, offered skill cards
from the agent, and handed all of it to `prompt_for` positionally. The agent runtime
(`brain.gate.runtime.AgentRuntime`, M13.7.1) would have been a second assembler written beside
it, and the first part one of them forgot would be the first part a person noticed missing. So
the parts are one value, `ContextParts`, built by one coroutine, `assemble`, and both answer
paths take that value rather than reading the parts themselves. See
`ONE_PLACE_ASSEMBLES_WHAT_A_MODEL_IS_SHOWN`.

**Every part is read at the asker's reach at the moment of the turn, and none of them is kept.**
The memories are recalled through the reader the route bound to the run's reach, the earlier
questions are the person's own words in their own thread, the skill cards are offered at the
caller's reach, and the knowledge is the redacted payload. `assemble` takes each through a
parameter rather than reaching for a store, so nothing here could read past the reach the
caller already narrowed, and nothing it builds outlives the turn.

**The trace names which parts were included and which were left out, and never what any of them
said.** `ContextNote` carries part names and, for a part left out, why, in a closed vocabulary.
Its two attributes are on `brain.ops.tracing.SAFE_ATTRIBUTES` because their values are only ever
this module's words, and a part left out because nothing came back at this reach is one reason
whether the asker had nothing or may see nothing, so an operator reading a trace learns no more
about the asker's memories than the asker's prompt did. See
`A_PART_LEFT_OUT_IS_NAMED_WITH_ITS_REASON_AND_NEVER_ITS_CONTENTS`.

**Two parts have no source yet, and are named as left out rather than dropped from the type.**
The project a question is about (M16.6.2) waits on which system holds client projects, owner item
137, and an agent has no memory of its own anywhere in the product. A type without those fields
would make the trace say nothing about them, which reads as "nothing to say" rather than "not
built". See `A_PART_WITH_NO_SOURCE_IS_SAID_TO_HAVE_NONE`.

Rejected: a context object the model lane fills in place as it goes. The order the parts are read
in would then be the order of the lane's lines, and the runtime would have to repeat it.

Rejected: putting the project and the agent's memory in once something holds them, and leaving
them out of the type until then. See above.

Task ids: M16.6.1
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from brain.core.redaction import ChannelPayload
from brain.tools.skills import SkillCard

# ------------------------------------------------------------------ written-down reasons
#: Why there is one assembler for both answer paths.
ONE_PLACE_ASSEMBLES_WHAT_A_MODEL_IS_SHOWN: Final = (
    "The context a model is shown for a turn is one value built by assemble, and the model "
    "lane and the agent runtime both take that value. A second assembler would be a second list "
    "of parts, and the part one of them forgot would reach a model on one path and not the "
    "other; a test reading the source refuses any other caller of the prompt's part builders."
)

#: Why the trace names parts and reasons and nothing else.
A_PART_LEFT_OUT_IS_NAMED_WITH_ITS_REASON_AND_NEVER_ITS_CONTENTS: Final = (
    "The trace says which parts a model was shown and which it was not, by name, and why a part "
    "was left out, from a closed vocabulary. It never carries what a part said. A part left out "
    "because nothing came back at this reach is one reason whether the asker had nothing or may "
    "see nothing, so the trace tells an operator no more than the prompt told the model."
)

#: Why a part nothing holds is in the type and left out, rather than absent from it.
A_PART_WITH_NO_SOURCE_IS_SAID_TO_HAVE_NONE: Final = (
    "The project a question is about waits on owner item 137, which system holds client "
    "projects, and an agent has no memory of its own in the product. Both are fields of "
    "ContextParts that are always empty and named in the trace as having no source, so a "
    "trace says the part is not built rather than saying nothing about it."
)


# ------------------------------------------------------------------------ the vocabulary
class Part(enum.StrEnum):
    """The parts M16.6.1 names, in the order a reader of the prompt meets them."""

    #: The person's own earlier questions in this thread, never an earlier answer (M9.2.3).
    CONVERSATION = "conversation"
    #: What the person said for this conversation only, held for the thread (M16.1.1).
    SESSION = "session"
    #: The task the agent was given, as the skill cards it may use.
    TASK = "task"
    #: The client project the question is about (M16.6.2). See
    #: `A_PART_WITH_NO_SOURCE_IS_SAID_TO_HAVE_NONE`.
    PROJECT = "project"
    #: What the asker said about themselves and may still recall (M16.6.3).
    ASKER_MEMORY = "asker_memory"
    #: What the agent remembers of its own. See `A_PART_WITH_NO_SOURCE_IS_SAID_TO_HAVE_NONE`.
    AGENT_MEMORY = "agent_memory"
    #: Company knowledge: the redacted passages, or what the run's tools read.
    KNOWLEDGE = "knowledge"


class LeftOut(enum.StrEnum):
    """Why a part was not shown. Closed, because the trace keeps these words unmasked.

    Short, because the whole attribute must fit `brain.ops.tracing.SAFE_VALUE_MAX_CHARS` with
    every part left out, and a test measures that case.
    """

    #: Read at this reach and nothing came back, whichever of the two reasons that was.
    NOTHING = "none"
    #: Nothing in the product holds this part yet.
    NO_SOURCE = "no_source"
    #: Read during the run by the tools the agent was handed, not assembled up front.
    BY_TOOLS = "tools"


#: The parts nothing holds yet. Read by `ContextParts.note`, and by a test that fails the day one
#: of them gets a source and this line is not changed.
WITHOUT_A_SOURCE: Final[frozenset[Part]] = frozenset({Part.PROJECT, Part.AGENT_MEMORY})

#: The two trace attributes, both on `brain.ops.tracing.SAFE_ATTRIBUTES`.
INCLUDED_ATTRIBUTE: Final = "context_included"
LEFT_OUT_ATTRIBUTE: Final = "context_left_out"


# ------------------------------------------------------------------------------ the ports
class Recollection(Protocol):
    """Somewhere a turn's remembered statements are read, bound to the run's reach already.

    `brain.gate.model_lane.AskerHints` for the asker's memories and the session store for the
    thread's; both are read once, here, when a model is about to be asked.
    """

    async def hints(self) -> tuple[str, ...]: ...


# ----------------------------------------------------------------------------- the value
@dataclass(frozen=True)
class ContextNote:
    """What the trace keeps about a turn's context: part names, and why each absent one is."""

    included: tuple[Part, ...]
    left_out: tuple[tuple[Part, LeftOut], ...]

    def attributes(self) -> Mapping[str, str]:
        """The two trace attributes, as words `brain.ops.tracing.mask` keeps.

        Empty values are left out rather than stored as an empty string, which the token grammar
        would refuse and mask would then turn into a shape.
        """
        found: dict[str, str] = {}
        if self.included:
            found[INCLUDED_ATTRIBUTE] = "/".join(one.value for one in self.included)
        if self.left_out:
            found[LEFT_OUT_ATTRIBUTE] = "/".join(
                f"{one.value}:{why.value}" for one, why in self.left_out
            )
        return found


@dataclass(frozen=True)
class ContextParts:
    """Everything a model is shown for one turn besides the shared prefix. See the module.

    `knowledge` is None when the run reads company knowledge through its tools rather than up
    front, which is the agent runtime's case; the model lane always has a payload.
    """

    question: str
    conversation: tuple[str, ...] = ()
    session: tuple[str, ...] = ()
    task: tuple[SkillCard, ...] = ()
    project: tuple[str, ...] = ()
    asker_memory: tuple[str, ...] = ()
    agent_memory: tuple[str, ...] = ()
    knowledge: ChannelPayload | None = None

    def _held(self) -> Mapping[Part, bool]:
        return {
            Part.CONVERSATION: bool(self.conversation),
            Part.SESSION: bool(self.session),
            Part.TASK: bool(self.task),
            Part.PROJECT: bool(self.project),
            Part.ASKER_MEMORY: bool(self.asker_memory),
            Part.AGENT_MEMORY: bool(self.agent_memory),
            Part.KNOWLEDGE: self.knowledge is not None and bool(self.knowledge.records),
        }

    def note(self) -> ContextNote:
        """Which parts this turn showed, and why each of the others was not shown."""
        held = self._held()
        included = tuple(one for one in Part if held[one])
        left_out = tuple((one, self._why(one)) for one in Part if not held[one])
        return ContextNote(included=included, left_out=left_out)

    def _why(self, part: Part) -> LeftOut:
        if part in WITHOUT_A_SOURCE:
            return LeftOut.NO_SOURCE
        if part is Part.KNOWLEDGE and self.knowledge is None:
            return LeftOut.BY_TOOLS
        return LeftOut.NOTHING


async def assemble(
    question: str,
    *,
    conversation: Sequence[str] = (),
    session: Recollection | None = None,
    task: Sequence[SkillCard] = (),
    asker: Recollection | None = None,
    knowledge: ChannelPayload | None = None,
) -> ContextParts:
    """The one assembly of a turn's context. See `ONE_PLACE_ASSEMBLES_WHAT_A_MODEL_IS_SHOWN`.

    Every argument is already at the asker's reach: the readers were bound to the run's reach by
    the route, the earlier questions are the person's own, the cards were offered at the caller's
    reach and the knowledge is the redacted payload. The project and the agent's memory have no
    parameter, because nothing holds them: see `A_PART_WITH_NO_SOURCE_IS_SAID_TO_HAVE_NONE`.
    """
    return ContextParts(
        question=question,
        conversation=tuple(conversation),
        session=() if session is None else await session.hints(),
        task=tuple(task),
        asker_memory=() if asker is None else await asker.hints(),
        knowledge=knowledge,
    )
