"""The five kinds of memory an agent may be set up to read and write.

The owner decided on needs item 180 (2026-10-12, option B) that memory is told apart in five kinds,
as the task for it says: **the conversation, the task, the project, the person, and the agent's
own.** What was built told it apart by how long it lives (session, persistent, adaptive), which is
a fact about the store and not about what a person is remembered for. The five here are what a run
is shown, so each is one or more of the parts `brain.gate.turn_context` assembles: the thread's
earlier questions and what the person said for this conversation only are the conversation; the
skill cards are the task; the client project is the project; what the asker said about themselves is
the person; and what the agent remembers of its own is its own.

**An agent is configured with the kinds it may read and write, and a run cannot read a kind its
configuration leaves out.** The configuration is `AgentRecord.memory_kinds`, and the assembler
(`brain.gate.turn_context.assemble`) is the one place a run's context is read, so it is the one
place the setting is enforced: a kind left out is not read at all, which is a different thing from
being read and hidden, and the trace says it was left out by configuration. Like the channels, it
is reachability and not authority: it narrows what an agent is shown, never what a caller may
reach, and it can only narrow, because the entitlement it is intersected with is the caller's.

**A new agent has all five, and the setting only ever removes.** Rejected: a default of none, which
would silence the memory of every agent on every install the day this ships, and an agent whose
owner had never opened the page would stop remembering the person it answers. The reverse risk is
the one memory has always carried, and the person's own deletion right is unchanged by it.

Task ids: M39.7.1
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from typing import Annotated, Final

from pydantic import BeforeValidator


class MemoryKind(enum.StrEnum):
    """What a piece of remembered context is about."""

    CONVERSATION = "conversation"
    TASK = "task"
    PROJECT = "project"
    PERSON = "person"
    OWN = "own"


#: Every kind, sorted, as a record stores them. A new agent has all of them.
ALL_KINDS: Final[tuple[str, ...]] = tuple(sorted(one.value for one in MemoryKind))


def memory_kinds_of(value: object) -> tuple[str, ...]:
    """Kind names as an agent stores them: sorted, without repeats, each one a kind.

    The one check, used by `AgentRecord` and by every request body that names kinds, so the list a
    console form may send and the list a record may hold cannot drift apart. A name that is not a
    kind is refused rather than dropped: kept, it is a box that reads as ticked and switches
    nothing on; dropped, the steward's choice is edited without their being told.
    """
    if isinstance(value, str) or not isinstance(value, Iterable):
        msg = "memory kinds is a list of kind names"
        raise ValueError(msg)
    names = {str(one) for one in value}
    unknown = sorted(names - set(ALL_KINDS))
    if unknown:
        msg = f"{unknown} are not kinds of memory; an agent's memory is {list(ALL_KINDS)}"
        raise ValueError(msg)
    return tuple(sorted(names))


#: A request field naming the kinds a person ticked, checked by `memory_kinds_of`.
MemoryKinds = Annotated[tuple[str, ...], BeforeValidator(memory_kinds_of)]
