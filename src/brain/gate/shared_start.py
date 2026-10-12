"""The start of a model request that every person shares, and the tools it may name.

A provider bills the start of a request at a fraction of its price when it has seen the same bytes
before, so the product keeps the start identical for everybody and puts what differs from person
to person after it (M3.7.2). The owner decided on 2026-10-12, as option A of needs-rupash 175,
what the shared start may hold of the tools: **only the tools every person in the company already
holds.**

**Why not every tool.** The architecture's union puts every tool in the shared start and lets only
the entitled subset follow it. The product's own rule is the opposite about one thing: a tool a
person may not use is absent from what the model sees, never shown and refused, because a model
that has been told of a tool it cannot use will say so, and that sentence tells the person what
exists (`brain.gate.catalogue`). So the shared start names a tool only when naming it can tell
nobody anything: it is a tool the joiner's pack gives everybody, and it is named to a person only
if that person is shown it anyway.

**Two halves, and both are derived from what the person reaches.** `shared_and_following` splits
the tools a person is offered into those in `universal` and the rest, so the shared half is
`universal ∩ offered` and can never hold a tool outside the person's reach: somebody whose grant
for a universal tool was taken away is offered neither half of it, and their shared start is a
different, shorter text that shares with the people who lack the same. The following half is the
person's own. Rejected: the architecture's union, for the reason above. Rejected: deciding
`universal` by reading every principal's grants at each request, which is a query over the company
for a bytes saving.

**`universal` is what the joiner pack confers**, read from
`brain.identity.lifecycle.STARTER_PACK`, the one place the product says what everybody holds on
joining. A capability the pack holds covers a tool that requires it, by `Capability.covers`, so
`read:knowledge` makes the two knowledge tools universal and a connector's read, which no pack
gives, never is. An install that removes the pack's capability from everybody changes nothing
about safety: the shared start is `universal ∩ offered`.

The reader behind the switch is `brain.ops.shared_start`; this module is pure and holds no
session.

Task ids: M3.7.2
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

from brain.core.entitlement import Capability
from brain.core.envelope import ToolDefinition
from brain.identity.lifecycle import STARTER_PACK
from brain.tools.registry import ToolRegistry

#: Why the shared start names only what everybody holds.
THE_SHARED_START_NAMES_NO_TOOL_A_PERSON_CANNOT_USE: Final = (
    "A model told of a tool its asker cannot use will say there is one, and that sentence tells "
    "the asker what exists. So the shared start holds only the tools every person already holds, "
    "intersected with what this person is offered, and a tool outside their reach is in neither "
    "half of what they are sent."
)

#: What every person holds on joining: the one pack the product furnishes.
EVERYBODY_HOLDS: Final[tuple[Capability, ...]] = STARTER_PACK.capabilities


def universal_tools(
    registry: ToolRegistry, held: Iterable[Capability] = EVERYBODY_HOLDS
) -> frozenset[str]:
    """The registered tools whose capability a pack everybody receives covers.

    A tool is universal when some held capability covers the one it requires. An empty `held`
    gives no universal tool, which is today's behaviour: nothing is shared.
    """
    pack = tuple(held)
    return frozenset(
        name
        for name in registry.names()
        if any(one.covers(registry.get(name).capability) for one in pack)
    )


def shared_and_following(
    offered: Sequence[ToolDefinition], universal: frozenset[str]
) -> tuple[tuple[ToolDefinition, ...], tuple[ToolDefinition, ...]]:
    """Split what a person is offered: the tools the shared start may name, then the person's own.

    Each half keeps `offered`'s order, which the caller sorts. The first is `universal ∩ offered`
    by construction: nothing here adds a tool, so neither half can name one the person was not
    offered. See `THE_SHARED_START_NAMES_NO_TOOL_A_PERSON_CANNOT_USE`.
    """
    shared = tuple(one for one in offered if one.name in universal)
    following = tuple(one for one in offered if one.name not in universal)
    return shared, following
