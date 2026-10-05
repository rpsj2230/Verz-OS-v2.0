"""Which stewarded things a grant somebody made to themselves reaches, and so who is told of it.

The architecture's permission model lets a super administrator grant themselves a capability,
because refusing it only moves the grant to the database, and asks that doing so "notifies the
object's steward". M7.7.2 makes that concrete for the three things that have a steward: a knowledge
document (`know.item.owner_id`, handed over on the document's page), a connected source (the steward
`brain.ops.stewardship_store` reads, named on the source's page) and an agent (its owner,
transferred on the agent's page). The database records every grant a person makes to themselves
(`gate.self_grant`, `0167`); this module decides which of those a steward is told of.

**A grant reaches a thing when its capability touches one of the capabilities that reach the thing,
and its scope admits the thing's row.** The capability test is `touches`, which is
`Capability.covers` in both directions a stewardship question needs: a grant of `read:knowledge.*`
reaches a document read through `read:knowledge`, and so does a grant of the one field
`read:knowledge.document`, because either is somebody reading the document's words. The scope test
is `brain.core.scope.Scope.matches`, the rule every read in the product is decided by, against the
row the product itself judges that thing by: a passage's department, visibility, owner and document
for a document, `brain.prompt_routes.agent_scope_row` for an agent. A second rule here would be a
second place for it to be wrong. See `A_GRANT_REACHES_WHAT_THE_PRODUCT_WOULD_LET_IT_READ`.

**A source is reached by reaching any part of it.** A source's records carry departments, owners
and fields a source-level row cannot pin, so a clause on a field the row does not carry is a grant
reaching some of the source's records rather than none of them, and its steward is told. Leaving it
out would let a department-scoped grant of `read:ticket.*` pass unseen by the one person who answers
for the tickets. See `A_SOURCE_IS_REACHED_BY_REACHING_ANY_OF_ITS_RECORDS`.

**A steward is never told of their own grant.** They made it, so there is nobody to tell, and the
super administrators' notice (`brain.console.global_surfaces.self_grant_notices`) is still
computed from the ledger for the grants that concern the platform. See
`A_STEWARD_IS_NOT_TOLD_OF_THEIR_OWN_GRANT`.

**A notice names the grant, the person and the things this steward stewards, and nothing else.**
Which other things the same grant reached, and who stewards them, are other stewards' business, so
a notice lists only what the reader answers for. See `A_NOTICE_NAMES_ONLY_WHAT_ITS_READER_STEWARDS`.

Scope: domain logic. Nothing here opens a connection or reads a clock.

Task ids: M7.7.2
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final

from brain.core.entitlement import Capability
from brain.core.scope import Op, Scope

# ------------------------------------------------------------------ written-down reasons
#: Why a grant's reach is decided by the product's own rules and not by a rule of this module's.
A_GRANT_REACHES_WHAT_THE_PRODUCT_WOULD_LET_IT_READ: Final = (
    "A steward is told of a grant that reaches what they steward, and whether it does is the "
    "question every read in the product already answers: the capability covers the one that "
    "reaches the thing, and the scope matches the row the product judges the thing by. A second "
    "rule here would tell a steward of grants that reach nothing, or keep quiet about one that "
    "reads everything they answer for."
)

#: Why a clause on a field a source's row does not carry counts as reaching the source.
A_SOURCE_IS_REACHED_BY_REACHING_ANY_OF_ITS_RECORDS: Final = (
    "A source's records carry departments, owners and fields that a row for the whole source "
    "cannot pin, so a grant scoped by one of them reaches some of the source's records. Its "
    "steward is told: a grant of read:ticket.* over one department is somebody reading tickets, "
    "and the person who answers for the tickets is the one who should know."
)

#: Why a steward's own grant is not a notice to them.
A_STEWARD_IS_NOT_TOLD_OF_THEIR_OWN_GRANT: Final = (
    "A notice exists so that somebody other than the person who granted themselves something "
    "finds out. A steward granting themselves access to what they steward is told nothing by "
    "being told, and the super administrators' notice is still computed from the ledger."
)

#: Why a notice lists only the reader's own things.
A_NOTICE_NAMES_ONLY_WHAT_ITS_READER_STEWARDS: Final = (
    "One grant can reach things several people steward. Each is told of the things they answer "
    "for, and not of the others, which are other stewards' business and may be things the "
    "reader cannot see."
)

#: How far back a steward's list of self-grants reaches. A quarter, which is the access review's
#: own interval, so every grant made since the last review is on the list when the next one runs.
NOTICE_WINDOW: Final = timedelta(days=90)

#: The capability that lets a person use an agent, which a grant to oneself can widen.
INVOKE_AGENT: Final = Capability(value="invoke:agent")


class StewardedKind(enum.StrEnum):
    """The three things that name a steward."""

    DOCUMENT = "document"
    SOURCE = "source"
    AGENT = "agent"


@dataclass(frozen=True)
class Stewarded:
    """One thing with a steward, as a grant's reach is judged against it.

    `row` is the fields the product decides a read of this thing by; `reached_by` is the
    capabilities that read or govern it. `partial` is true for a thing whose records carry fields
    the row cannot pin, which is a source: see `A_SOURCE_IS_REACHED_BY_REACHING_ANY_OF_ITS_RECORDS`.
    """

    kind: StewardedKind
    object_id: str
    label: str
    steward_id: str
    row: Mapping[str, str]
    reached_by: tuple[Capability, ...]
    partial: bool = False

    def __post_init__(self) -> None:
        if not self.object_id or not self.steward_id:
            msg = "a stewarded thing names itself and its steward"
            raise ValueError(msg)
        if not self.reached_by:
            msg = f"{self.kind.value} {self.object_id!r} names no capability that reaches it"
            raise ValueError(msg)


@dataclass(frozen=True)
class SelfGrant:
    """One grant a person made to themselves, as `gate.self_grant` holds it."""

    grant_id: str
    principal_id: str
    capabilities: tuple[Capability, ...]
    scope: Scope
    at: datetime
    #: The pack's name when it was a pack assignment, and nothing for a direct grant.
    pack: str | None = None


@dataclass(frozen=True)
class StewardNotice:
    """What one steward is told of one self-grant: the grant and the things of theirs it reaches."""

    grant: SelfGrant
    reached: tuple[Stewarded, ...] = field(default_factory=tuple)


def _stem(capability: Capability) -> str:
    """A capability without a trailing `.*`, which is what it reaches the prefix of."""
    value = capability.value
    return value[:-2] if value.endswith(".*") else value


def touches(granted: Capability, base: Capability) -> bool:
    """Whether holding `granted` reads or governs what `base` does, in part or whole.

    Covers in either direction, and a field of the base: `read:knowledge.*`, `read:knowledge`
    and `read:knowledge.document` all touch `read:knowledge`, and `read:knowledgebase` does not.
    """
    if granted.covers(base) or base.covers(granted):
        return True
    stem, root = _stem(granted), _stem(base)
    return stem == root or stem.startswith(root + ".") or root.startswith(stem + ".")


def admits(scope: Scope, thing: Stewarded) -> bool:
    """Whether the scope admits the thing's row, by `Scope.matches`, or some of it for a source."""
    if not thing.partial:
        return scope.matches(dict(thing.row))
    pinned = tuple(one for one in scope.clauses if one.op is Op.ANY or one.field in thing.row)
    return Scope(clauses=pinned).matches(dict(thing.row))


def reaches(grant: SelfGrant, thing: Stewarded) -> bool:
    """Whether this grant reaches this thing.

    See `A_GRANT_REACHES_WHAT_THE_PRODUCT_WOULD_LET_IT_READ`.
    """
    touched = any(touches(one, base) for one in grant.capabilities for base in thing.reached_by)
    return touched and admits(grant.scope, thing)


def notices_for(
    steward_id: str, grants: Iterable[SelfGrant], things: Sequence[Stewarded]
) -> tuple[StewardNotice, ...]:
    """What this steward is told: each grant somebody else made that reaches a thing of theirs.

    Newest first, and each grant once, listing only this steward's things. See
    `A_STEWARD_IS_NOT_TOLD_OF_THEIR_OWN_GRANT` and `A_NOTICE_NAMES_ONLY_WHAT_ITS_READER_STEWARDS`.
    """
    mine = tuple(one for one in things if one.steward_id == steward_id)
    found: list[StewardNotice] = []
    for grant in sorted(grants, key=lambda one: (one.at, one.grant_id), reverse=True):
        if grant.principal_id == steward_id:
            continue
        reached = tuple(one for one in mine if reaches(grant, one))
        if reached:
            found.append(StewardNotice(grant=grant, reached=reached))
    return tuple(found)
