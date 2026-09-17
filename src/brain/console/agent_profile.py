"""How an agent is set up, in words a person can check against what the gate will do.

The agent page's Profile tab puts the agent's configuration in front of an administrator: the
ceiling, the tools it may call, the rung each of its actions is held to, and whether the figure
at the top of the page measures anything. Every one of those already has an owner that decides
it. `brain.agents.model.AgentAuthority` is the ceiling, `brain.gate.catalogue.project` decides
which tools a run keeps, `brain.gate.leash.Leash` decides a rung, and `brain.ops.spend_store`
is the only place a run's cost is written. This module says each of them in sentences and adds
no decision of its own, and every test of it is asked of the owner as well as of the words.

**A sentence about a ceiling is a second reading of it, so each one is built from the value and
never typed beside it.** The rows sentence is the scope's own clauses, the reads are the
capabilities `brain.console.reach_view.ceiling_block` disclosed, and the side effect sentence
names what the ceiling admits and every effect above it as something the agent cannot do, read
off `brain.gate.catalogue.SIDE_EFFECT_ORDER`. A table of sentences written per agent would be
right on the day it was written and describe a ceiling somebody has since narrowed. See
`A_CEILING_IS_SAID_FROM_ITS_OWN_VALUE_AND_NEVER_FROM_A_DESCRIPTION_OF_IT`.

**The capability names are disclosed whole or not at all, by the grant that already decides
it.** `ceiling_words` takes a `CeilingBlock` rather than a reader, so the only way to put a
capability sentence on the page is through `ceiling_block`, which checks
`reach_view.CEILING_DISCLOSURE` and never narrows the ceiling to what the reader holds. The
scope, the tools and the side effect are the Settings tab's own content, which the roster
already sends the scope under; that decision belongs to the route and is not taken here.

**A rung is a set, not a value, the moment one leash entry carries a scope.** `Leash.rung_for`
takes the row an action is aimed at and the strictest matching entry wins, so the same tool can
be held to Shadow on one record and run on its own on another. A page shows no row, so
`rungs_for` returns every rung a call on the target could be held to, and a test holds that
for any leash and any row the rung `rung_for` gives is in that set. Rejected: the rung for an
empty row. It is exact for every entry in the product today, which are all unscoped, and it
would describe a target whose only entry is scoped as Shadow everywhere while it runs on its
own in the department the entry names. See
`A_RUNG_A_PAGE_CANNOT_SEE_THE_ROW_FOR_IS_EVERY_RUNG_IT_COULD_BE`.

**The leash shown is the configured one, and a run can only be held lower.** A template's
leash is bound to this install's tools by `brain.agents.install.bound_leash`, which is what a
finished install stores the rungs from. What the page is not told is
`brain.agents.install.pinned_leash`, which holds every rung at Shadow while a declared
connector is not serving, because no connector registry is read by the process answering the
page, and the risk score `brain.gate.injection.autonomy_ceiling` applies per request. Both only
lower a rung, so the page states the most the agent could do, which is the direction a
description of supervision may err in. See
`THE_LEASH_SHOWN_IS_THE_CONFIGURED_ONE_AND_A_RUN_MAY_ONLY_BE_HELD_LOWER`.

**Nothing writes a run's cost, and the page is told so rather than shown nought.**
`brain.ops.spend_store.record` has no caller, so every headline is 0.00 over no rows.
`RUN_SPEND_IS_RECORDED` is served beside the figure, and `spend_writers` reads the source for a
caller of that function, so the day something starts writing cost the constant is a failing
test rather than a page still saying nothing is recorded. See
`A_FIGURE_NOTHING_WRITES_IS_SERVED_WITH_THE_STATEMENT_THAT_NOTHING_WRITES_IT`.

Scope: domain logic. Nothing here opens a connection, reads a clock or renders markup.

It is written for the Profile of M27.11.15, and claims no leaf: that leaf closes when the page
exists.

Task ids: none
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from brain.agents.model import AgentAuthority
from brain.console.reach_view import CeilingBlock
from brain.core.entitlement import Capability
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.scope import Clause, Op, Scope
from brain.gate.catalogue import SIDE_EFFECT_ORDER
from brain.gate.injection import AutonomyTier
from brain.gate.leash import MISSING_ENTRY_RUNG, Leash
from brain.ops.jobs import hidden_count_fields
from brain.ops.starter import VERB_WORDS

# ------------------------------------------------------------------ written-down reasons

#: Why every sentence is built from the ceiling rather than stored beside it.
A_CEILING_IS_SAID_FROM_ITS_OWN_VALUE_AND_NEVER_FROM_A_DESCRIPTION_OF_IT: Final = (
    "A ceiling is narrowed by a draft and a publish, and a description written beside it is "
    "correct on the day it was written. So the rows sentence is the scope's own clauses, the "
    "reads are the capabilities the ceiling holds, the tools are its allowed tools, and the "
    "side effect sentence names what the ceiling admits and every effect above it as one the "
    "agent cannot have. Nothing on the page can describe a ceiling the agent no longer has."
)

#: Why a rung on a page is the set of rungs a call could be held to.
A_RUNG_A_PAGE_CANNOT_SEE_THE_ROW_FOR_IS_EVERY_RUNG_IT_COULD_BE: Final = (
    "Leash.rung_for is asked about one row, and the strictest entry matching that row wins. A "
    "page describing an agent has no row, so it describes a target by every rung a call on it "
    "could be held to: the rungs of the entries naming it, capped by the entries that apply "
    "everywhere, with Shadow among them wherever no entry has to match. Any row's rung is in "
    "that set, which a test holds against rung_for itself."
)

#: Why the page's rungs are an upper bound.
THE_LEASH_SHOWN_IS_THE_CONFIGURED_ONE_AND_A_RUN_MAY_ONLY_BE_HELD_LOWER: Final = (
    "The rungs shown are the template's leash bound to this install's tools. A run is held "
    "lower still while a declared connector is not serving and whenever the risk score of a "
    "request tightens it, and neither is known to the page. Both only lower a rung, so the "
    "page states the most the agent could do and never less."
)

#: Why a figure nothing writes travels with a statement saying so.
A_FIGURE_NOTHING_WRITES_IS_SERVED_WITH_THE_STATEMENT_THAT_NOTHING_WRITES_IT: Final = (
    "Nothing in this product calls brain.ops.spend_store.record, so every agent's spend is "
    "0.00 over no rows and every run count is nought. Nought is a measurement, and a page "
    "drawing it says the agent cost nothing. The figure is sent with RUN_SPEND_IS_RECORDED so "
    "the page can say it is not recorded yet, and spend_writers reads the source so the "
    "statement fails a test the day something starts writing cost."
)

# ------------------------------------------------------------------------ the vocabulary

#: Whether anything records what a run of an agent cost. Nothing does: see
#: `A_FIGURE_NOTHING_WRITES_IS_SERVED_WITH_THE_STATEMENT_THAT_NOTHING_WRITES_IT`.
RUN_SPEND_IS_RECORDED: Final = False

#: The module and the function whose callers are the writers of a run's cost.
SPEND_STORE_MODULE: Final = "brain.ops.spend_store"
SPEND_WRITER: Final = "record"

#: What an unrestricted scope says. It narrows nothing, which is not a grant of everything:
#: a run is still the caller's reach intersected with the ceiling.
EVERY_ROW_ITS_CALLER_MAY_SEE: Final = (
    "Any row the person it works for may see: this agent narrows no rows of its own."
)

#: What a ceiling holding no tools says.
NO_TOOLS: Final = "It may call no tools, so it can only answer from what it is told."

#: What each largest side effect admits, as the start of a sentence.
MAY: Final[Mapping[SideEffect, str]] = MappingProxyType(
    {
        SideEffect.NONE: "It may only read",
        SideEffect.DRAFT: "At most it prepares a draft for a person",
        SideEffect.WRITE: "At most it changes a record in another system",
        SideEffect.SEND: "At most it sends a message out of the building",
        SideEffect.MONEY: "At most it moves money",
    }
)

#: What each effect is, as something an agent cannot do. `NONE` is absent: reading is below
#: every ceiling, so it is never something a ceiling rules out.
CANNOT: Final[Mapping[SideEffect, str]] = MappingProxyType(
    {
        SideEffect.DRAFT: "prepare a draft",
        SideEffect.WRITE: "change a record",
        SideEffect.SEND: "send anything",
        SideEffect.MONEY: "move money",
    }
)

#: What a rung means, in words a person reads beside an action.
RUNG_WORDS: Final[Mapping[AutonomyTier, str]] = MappingProxyType(
    {
        AutonomyTier.SHADOW: "Shadow",
        AutonomyTier.ASSISTED: "Assisted",
        AutonomyTier.AUTONOMOUS: "Autonomous",
    }
)


def rung_key(rung: AutonomyTier) -> str:
    """A rung as it travels: its member's name in lower case.

    `AutonomyTier` is an `IntEnum`, so its value is a number that means nothing to a page, and
    its name is the word the leash's own docstrings use. Derived rather than tabled, so a fourth
    rung travels the day it exists.
    """
    return rung.name.lower()


def _joined(items: Sequence[str], last: str) -> str:
    """`a`, `a and b`, `a, b and c`. No Oxford comma, which is the house's own spelling."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} {last} {items[-1]}"


def _words(name: str) -> str:
    return name.replace("_", " ").replace(".", " ")


# ----------------------------------------------------------------------------- the rows
def clause_words(clause: Clause) -> str:
    """One clause as a condition a row meets, in the clause's own terms.

    Exhaustive over `Op`. A clause that can match no row says so rather than reading like a
    condition: `EQ` with no value and an empty `IN` both match nothing in `Clause.matches`.
    """
    field = _words(clause.field)
    match clause.op:
        case Op.ANY:
            return f"{field} is anything"
        case Op.EQ:
            if clause.value is None:
                return f"{field} equals nothing, which no row does"
            return f"{field} is {clause.value}"
        case Op.IN:
            values = tuple(clause.value) if isinstance(clause.value, tuple) else ()
            if not values:
                return f"{field} is in an empty list, which no row is"
            return f"{field} is {_joined(list(values), 'or')}"
        case Op.PREFIX:
            return f"{field} starts with {clause.value}"


def scope_sentence(scope: Scope) -> str:
    """Which rows a ceiling admits, as one sentence built from its clauses.

    An unrestricted scope, including one of `ANY` clauses alone, is `EVERY_ROW_ITS_CALLER_MAY_SEE`,
    which is `Scope.is_unrestricted`'s own reading rather than a count of clauses here.
    """
    if scope.is_unrestricted():
        return EVERY_ROW_ITS_CALLER_MAY_SEE
    conditions = [clause_words(one) for one in scope.clauses if one.op is not Op.ANY]
    return f"Only rows where {_joined(conditions, 'and')}."


# ---------------------------------------------------------------------------- the reads
def capability_sentence(capability: Capability) -> str:
    """What one capability lets a run do, read off `verb:noun[.field]` and nothing more.

    The verbs are `brain.ops.starter.VERB_WORDS`, the words the Capabilities screen already
    uses, so a ceiling and the vocabulary screen say one capability the same way. A trailing
    wildcard is every field, which is `Capability.covers`' own reading of it.
    """
    noun, _, field = capability.value.partition(":")[2].partition(".")
    verb = VERB_WORDS[capability.verb]
    if field == "*":
        return f"{verb} every field of {_words(noun)}."
    if field:
        return f"{verb} the {_words(field)} field of {_words(noun)}."
    return f"{verb} {_words(noun)}."


# ---------------------------------------------------------------------- the side effect
def above(effect: SideEffect) -> tuple[SideEffect, ...]:
    """Every effect larger than this one, in `SIDE_EFFECT_ORDER`, which is the gate's order."""
    return SIDE_EFFECT_ORDER[SIDE_EFFECT_ORDER.index(effect) + 1 :]


def at_most(effect: SideEffect, ceiling: SideEffect) -> bool:
    """Whether a tool with this effect is inside a ceiling with that largest effect.

    The comparison `brain.gate.catalogue.project` makes when it drops a tool, over the same
    order. Written out because that module's rank is private, and held to `project` itself by
    a test that runs it over the same tools.
    """
    return SIDE_EFFECT_ORDER.index(effect) <= SIDE_EFFECT_ORDER.index(ceiling)


def effect_sentence(largest: SideEffect) -> str:
    """The most any run may do, and every larger effect as something it cannot do.

    The larger effects are `above`, so the sentence cannot fail to rule out an effect the
    ceiling excludes, and a sixth member of `SideEffect` is a `KeyError` in a test rather than
    a sentence silently missing it.
    """
    excluded = [CANNOT[one] for one in above(largest)]
    if not excluded:
        return f"{MAY[largest]}."
    return f"{MAY[largest]}. It cannot {_joined(excluded, 'or')}."


# ---------------------------------------------------------------------------- the tools
@dataclass(frozen=True)
class ToolRow:
    """One tool the ceiling names, with what the registry on this process says about it.

    `source`, `side_effect` and `description` are None together when the registry holds no tool
    by that name, and `within_ceiling` is then False: `project` can never keep a tool it was
    not handed, so a name the ceiling allows and nothing registers is one no run can call.
    """

    name: str
    source: str | None
    side_effect: SideEffect | None
    description: str | None
    within_ceiling: bool

    @property
    def acts(self) -> bool:
        """Whether a run could call this tool and change something outside the Brain."""
        return (
            self.within_ceiling
            and self.side_effect is not None
            and self.side_effect is not SideEffect.NONE
        )

    @property
    def reads(self) -> bool:
        """Whether a run could call this tool and change nothing."""
        return self.within_ceiling and self.side_effect is SideEffect.NONE


def tool_rows(
    authority: AgentAuthority, registered: Iterable[ToolDefinition]
) -> tuple[ToolRow, ...]:
    """Every tool the ceiling allows, by name, as the registry here describes each one.

    Every allowed name has a row, registered or not, because the ceiling is shown whole; which
    of them a run could call is `within_ceiling`, decided by the registry and the largest side
    effect exactly as `project` decides it. Sorted by name, which is `project`'s own order.
    """
    by_name = {one.name: one for one in registered}
    rows: list[ToolRow] = []
    for name in sorted(authority.allowed_tools):
        found = by_name.get(name)
        if found is None:
            rows.append(ToolRow(name, None, None, None, within_ceiling=False))
            continue
        rows.append(
            ToolRow(
                name=name,
                source=found.source or None,
                side_effect=found.side_effect,
                description=found.description,
                within_ceiling=at_most(found.side_effect, authority.max_side_effect),
            )
        )
    return tuple(rows)


def tools_sentence(rows: Sequence[ToolRow]) -> str:
    """The tools a run could call, named, and nothing about the ones it could not."""
    usable = [one.name for one in rows if one.within_ceiling]
    if not usable:
        return NO_TOOLS
    return f"It may call {_joined(usable, 'and')}, and no other tool."


# -------------------------------------------------------------------------- the ceiling
@dataclass(frozen=True)
class CeilingWords:
    """The ceiling as sentences: rows, reads, tools and the largest side effect.

    `reads` is empty and `reads_locked` is True for a reader the capability names are not
    disclosed to, whatever the ceiling holds, so a locked ceiling with no capabilities and a
    locked ceiling with forty are one answer. There is no field counting what was locked.
    """

    rows: str
    reads: tuple[str, ...]
    reads_locked: bool
    tools: str
    largest_effect: str


class ProfileError(Exception):
    """A profile was assembled from values that describe two different agents."""


def ceiling_words(
    authority: AgentAuthority, block: CeilingBlock, tools: Sequence[ToolRow]
) -> CeilingWords:
    """One agent's ceiling in words, with the capability names as its block discloses them.

    The block is `brain.console.reach_view.ceiling_block`'s answer for this reader, and it is the
    only source of a capability sentence here, so this function cannot disclose a name that
    function locked. Refuses tool rows that are not this ceiling's, because a sentence naming a
    tool another agent may call is a sentence about the wrong agent.
    """
    if {one.name for one in tools} != set(authority.allowed_tools):
        msg = "these tool rows are not the tools this ceiling allows"
        raise ProfileError(msg)
    reads = (
        ()
        if block.locked
        else tuple(capability_sentence(Capability(value=one)) for one in block.capabilities)
    )
    return CeilingWords(
        rows=scope_sentence(authority.scope),
        reads=reads,
        reads_locked=block.locked,
        tools=tools_sentence(tools),
        largest_effect=effect_sentence(authority.max_side_effect),
    )


# ---------------------------------------------------------------------------- the leash
def rungs_for(leash: Leash, agent_id: str, target: str) -> tuple[AutonomyTier, ...]:
    """Every rung a call on this target could be held to, lowest first.

    See `A_RUNG_A_PAGE_CANNOT_SEE_THE_ROW_FOR_IS_EVERY_RUNG_IT_COULD_BE`. The entries that apply
    everywhere are `Leash.matching` asked about a row with no fields, which only a scope of
    `ANY` clauses or none at all can match, and `rung_for` over that row is the most any row can
    reach, because those entries match every row and the strictest match wins. Without one, a
    row matching no entry is held at `MISSING_ENTRY_RUNG`, so that rung is always possible.
    """
    named = [one.rung for one in leash.entries if one.agent_id == agent_id and one.target == target]
    if not leash.matching(agent_id, target, {}):
        return tuple(sorted({MISSING_ENTRY_RUNG, *named}))
    cap = leash.rung_for(agent_id, target, {})
    return tuple(sorted({one for one in named if one <= cap}))


@dataclass(frozen=True)
class LeashEntryWords:
    """One configured entry: its rung, and where it applies when that is not everywhere."""

    rung: AutonomyTier
    #: `scope_sentence` of the entry's scope, or None for an entry that applies everywhere.
    where: str | None


@dataclass(frozen=True)
class LeashRow:
    """One target, the rungs a call on it could be held to, and the entries that decide it.

    `configured` is False for an action nothing names, whose only rung is the Shadow default and
    whose `entries` are empty. `acts` is whether a tool this agent could call and change
    something with is behind the target: an entry with no such tool is supervision for something
    the agent cannot do.
    """

    target: str
    rungs: tuple[AutonomyTier, ...]
    configured: bool
    acts: bool
    entries: tuple[LeashEntryWords, ...]

    @property
    def highest(self) -> AutonomyTier:
        return self.rungs[-1]

    @property
    def lowest(self) -> AutonomyTier:
        return self.rungs[0]


def leash_rows(leash: Leash, agent_id: str, actions: Iterable[str]) -> tuple[LeashRow, ...]:
    """A row for every target an entry names and every action nothing names, by target.

    An action with no entry is a row, because its rung is the Shadow default and a page listing
    only the configured targets would say nothing about the actions no one thought about, which
    are the ones `MISSING_ENTRY_RUNG` exists for.
    """
    acting = frozenset(actions)
    mine = [one for one in leash.entries if one.agent_id == agent_id]
    targets = sorted({one.target for one in mine} | acting)
    return tuple(
        LeashRow(
            target=target,
            rungs=rungs_for(leash, agent_id, target),
            configured=any(one.target == target for one in mine),
            acts=target in acting,
            entries=tuple(
                LeashEntryWords(
                    rung=one.rung,
                    where=None if one.scope.is_unrestricted() else scope_sentence(one.scope),
                )
                for one in mine
                if one.target == target
            ),
        )
        for target in targets
    )


def leash_up_to(rows: Sequence[LeashRow]) -> AutonomyTier | None:
    """The highest rung any action of this agent could be held to, or None with no action.

    Over the rows an action is behind and no others. A rung governs a side effect, so an agent
    that only reads has no rung to reach rather than a rung of Shadow, and an entry for a tool
    it cannot call raises nothing.
    """
    acting = [one.highest for one in rows if one.acts]
    return max(acting) if acting else None


# ------------------------------------------------------------------------ the spend flag
def _names_for(tree: ast.AST) -> tuple[set[str], set[str]]:
    """The names this module binds to the spend store, and to its writer, by import."""
    head, _, tail = SPEND_STORE_MODULE.rpartition(".")
    modules = {SPEND_STORE_MODULE}
    writers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == SPEND_STORE_MODULE:
            writers |= {one.asname or one.name for one in node.names if one.name == SPEND_WRITER}
        if isinstance(node, ast.ImportFrom) and node.module == head:
            modules |= {one.asname or one.name for one in node.names if one.name == tail}
        if isinstance(node, ast.Import):
            modules |= {
                one.asname for one in node.names if one.name == SPEND_STORE_MODULE and one.asname
            }
    return modules, writers


def spend_writers(sources: Mapping[str, str]) -> tuple[str, ...]:
    """The modules, of those handed in by name, that use `brain.ops.spend_store.record`.

    Parsed rather than searched, for `brain.console.workspace.intersections_in`'s reason: this
    module's own docstring names the function, and a text search would find it. A use is a
    reference and not only a call, because a writer handed on as a callback writes as surely as
    one called here. The store's own module is not a writer of itself.
    """
    found: list[str] = []
    for name, text in sorted(sources.items()):
        if name == SPEND_STORE_MODULE:
            continue
        tree = ast.parse(text)
        modules, writers = _names_for(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in writers:
                found.append(name)
                break
            if (
                isinstance(node, ast.Attribute)
                and node.attr == SPEND_WRITER
                and ast.unparse(node.value) in modules
            ):
                found.append(name)
                break
    return tuple(found)


#: The types a reader of the Profile is handed. Listed rather than discovered, following
#: `brain.ops.jobs.OPERATOR_SURFACE`.
PROFILE_SURFACE: Final[tuple[type, ...]] = (ToolRow, CeilingWords, LeashEntryWords, LeashRow)


def profile_gaps(
    *,
    sources: Mapping[str, str],
    recorded: bool = RUN_SPEND_IS_RECORDED,
    surface: Sequence[type] = PROFILE_SURFACE,
) -> tuple[str, ...]:
    """Everything that would make this profile say something untrue.

    Takes its inputs for the reason `brain.console.workspace.workspace_gaps` gives: a diagnostic
    that can only read the healthy tree has nothing to report, and every refusal in it survives
    a mutation.
    """
    gaps: list[str] = []
    writers = spend_writers(sources)
    if writers and not recorded:
        gaps.append(
            f"{', '.join(writers)} writes a run's cost and the page still says nothing records it. "
            f"{A_FIGURE_NOTHING_WRITES_IS_SERVED_WITH_THE_STATEMENT_THAT_NOTHING_WRITES_IT}"
        )
    if recorded and not writers:
        gaps.append(
            "the page says a run's cost is recorded and nothing writes one, so every figure of "
            "nought is served as a measurement"
        )
    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(surface)
    )
    return tuple(gaps)
