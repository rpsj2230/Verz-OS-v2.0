"""The Profile's words about an agent's ceiling, tools, leash and spend, held to what decides each.

Every sentence here is checked against a literal written in this file, so a change of wording in
the module is a failing comparison rather than a constant agreeing with itself, and every decision
the words stand for is checked against the module that owns it: which tools a run keeps against
`brain.gate.catalogue.project`, which rungs a target could be held to against
`brain.gate.leash.Leash.rung_for` over generated leashes and rows, which capability names a reader
is told against `brain.console.reach_view.ceiling_block`, and whether anything records a run's cost
against the source itself.

Task ids: none
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.console.agent_profile import (
    CANNOT,
    EVERY_ROW_ITS_CALLER_MAY_SEE,
    MAY,
    NO_TOOLS,
    RUN_SPEND_IS_RECORDED,
    LeashEntryWords,
    ProfileError,
    ToolRow,
    above,
    capability_sentence,
    ceiling_words,
    clause_words,
    effect_sentence,
    leash_rows,
    leash_up_to,
    profile_gaps,
    rung_key,
    rungs_for,
    scope_sentence,
    spend_writers,
    tool_rows,
    tools_sentence,
)
from brain.console.reach_view import ceiling_block
from brain.core.entitlement import VERBS, Capability, EntitlementSet, Grant
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.scope import Clause, Op, Scope
from brain.gate.catalogue import AgentCeiling, project
from brain.gate.injection import AutonomyTier
from brain.gate.leash import Leash, LeashEntry
from brain.knowledge.visibility import Visibility

SRC = Path(__file__).resolve().parents[2] / "src"

SHADOW, ASSISTED, AUTONOMOUS = AutonomyTier.SHADOW, AutonomyTier.ASSISTED, AutonomyTier.AUTONOMOUS
WEB = Scope(clauses=(Clause(field="department", op=Op.EQ, value="web"),))
SALES = Scope(clauses=(Clause(field="department", op=Op.EQ, value="sales"),))


def tool(name: str, effect: SideEffect, source: str = "ledger") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"does {name}",
        entity="invoice",
        required_capability="read:invoice.reference",
        side_effect=effect,
        source=source,
    )


#: One registered tool per side effect, named without any word a sentence could be read by.
TOOLS = (
    tool("ledger.read_invoice", SideEffect.NONE),
    tool("ledger.draft_invoice", SideEffect.DRAFT),
    tool("ledger.update_invoice", SideEffect.WRITE),
    tool("ledger.post_invoice", SideEffect.SEND),
    tool("ledger.pay_invoice", SideEffect.MONEY),
)


def authority(
    max_side_effect: SideEffect, *extra: str, scope: Scope | None = None
) -> AgentAuthority:
    return AgentAuthority(
        scope=scope or Scope(),
        capabilities=(Capability(value="read:client.hours_remaining"),),
        allowed_tools=frozenset({one.name for one in TOOLS} | set(extra)),
        max_side_effect=max_side_effect,
    )


def record(of: AgentAuthority) -> AgentRecord:
    return AgentRecord(
        agent_id="quote_helper",
        display_name="Quote helper",
        persona="Answer briefly.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=of,
        created_by="u_builder",
    )


def reader(*capabilities: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_reader",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope()) for one in capabilities
        ),
    )


# ------------------------------------------------------------------------------ the rows
def test_an_unrestricted_scope_says_the_agent_narrows_no_rows_of_its_own() -> None:
    """An empty scope and a scope of `ANY` clauses alone both admit every row, and both say so.

    What breaks if this is deleted: an unrestricted ceiling is described as a narrow one, or a
    scope of `ANY` clauses reads as a condition a row has to meet."""
    wording = "Any row the person it works for may see: this agent narrows no rows of its own."
    assert scope_sentence(Scope()) == wording
    assert scope_sentence(Scope(clauses=(Clause(field="department", op=Op.ANY),))) == wording
    assert wording == EVERY_ROW_ITS_CALLER_MAY_SEE


def test_a_scope_says_each_of_its_conditions_and_leaves_out_the_ones_every_row_meets() -> None:
    """Equality, membership and a prefix are each said in the clause's own terms, joined with
    and, and an `ANY` clause beside them adds nothing. The unrestricted test above is the sibling.

    What breaks if this is deleted: a ceiling narrowed to one department is described without the
    department, or a membership clause loses a value, and the Profile says the agent reads rows it
    cannot."""
    scope = Scope(
        clauses=(
            Clause(field="department", op=Op.EQ, value="web"),
            Clause(field="region", op=Op.IN, value=("north", "south", "east")),
            Clause(field="client_code", op=Op.PREFIX, value="AC"),
            Clause(field="owner_id", op=Op.ANY),
        )
    )
    assert scope_sentence(scope) == (
        "Only rows where client code starts with AC, department is web and region is north, south "
        "or east."
    )


def test_a_clause_that_can_match_no_row_says_so_rather_than_reading_like_a_condition() -> None:
    """`EQ` with no value and an empty `IN` match nothing in `Clause.matches`, and their words say
    that no row meets them; the matching clause beside each is the positive case.

    What breaks if this is deleted: a ceiling that reaches nothing reads as a ceiling reaching the
    rows where a field is blank, which is the opposite of what the gate does."""
    empty_in = Clause(field="region", op=Op.IN, value=())
    no_value = Clause(field="department", op=Op.EQ, value=None)
    assert not empty_in.matches({"region": ""})
    assert not no_value.matches({"department": "None"})
    assert clause_words(empty_in) == "region is in an empty list, which no row is"
    assert clause_words(no_value) == "department equals nothing, which no row does"
    assert clause_words(Clause(field="region", op=Op.IN, value=("north",))) == "region is north"


# ----------------------------------------------------------------------------- the reads
def test_a_capability_is_said_by_its_verb_its_noun_and_its_field() -> None:
    """A column read, an entity read, a wildcard and every other verb, each said literally.

    What breaks if this is deleted: a wildcard reads as a field called star, or a verb added to
    the grammar has no words and the whole Profile raises for an agent holding it."""
    assert capability_sentence(Capability(value="read:client.hours_remaining")) == (
        "Reads the hours remaining field of client."
    )
    assert capability_sentence(Capability(value="read:client")) == "Reads client."
    assert capability_sentence(Capability(value="read:client.*")) == "Reads every field of client."
    assert capability_sentence(Capability(value="write:ticket.status")) == (
        "Changes the status field of ticket."
    )
    for verb in VERBS:
        assert capability_sentence(Capability(value=f"{verb}:thing"))


def test_the_reads_are_the_ceilings_whole_for_a_reader_of_the_vocabulary_and_locked_otherwise() -> (
    None
):
    """A reader holding the Capabilities screen's grant is told every capability the ceiling holds,
    implied row reads included, and a reader without it is told none and that they are locked. The
    rows, tools and side effect are the same for both, because those are the Settings tab's.

    What breaks if this is deleted: a capability name reaches a reader who was never told what can
    be granted, or the ceiling is narrowed to what the reader holds and reads as the agent's."""
    agent = authority(SideEffect.DRAFT, scope=WEB)
    rows = tool_rows(agent, TOOLS)
    one = record(agent)

    told = ceiling_words(agent, ceiling_block(one, reader("read:capability")), rows)
    locked = ceiling_words(agent, ceiling_block(one, reader("read:client")), rows)

    assert told.reads == ("Reads client.", "Reads the hours remaining field of client.")
    assert told.reads_locked is False
    assert locked.reads == ()
    assert locked.reads_locked is True
    assert (told.rows, told.tools, told.largest_effect) == (
        locked.rows,
        locked.tools,
        locked.largest_effect,
    )
    assert told.rows == "Only rows where department is web."


def test_two_readers_of_the_vocabulary_are_told_one_ceiling_whatever_else_they_hold() -> None:
    """The reader's other grants never narrow the words, which is
    `A_CEILING_FILTERED_TO_THE_READER_IS_THE_COLLAPSE_WEARING_A_CEILING_LABEL` asked of the words.

    What breaks if this is deleted: the Profile shows each administrator the part of the ceiling
    they hold, and two of them disagree about what the same agent may do."""
    agent = authority(SideEffect.NONE)
    rows = tool_rows(agent, TOOLS)
    one = record(agent)
    narrow = ceiling_words(agent, ceiling_block(one, reader("read:capability")), rows)
    wide = ceiling_words(
        agent,
        ceiling_block(one, reader("read:capability", "read:client.hours_remaining", "read:client")),
        rows,
    )
    assert narrow == wide


def test_tool_rows_that_are_not_this_ceilings_tools_are_refused() -> None:
    """A tool list belonging to another ceiling is refused; the ceiling's own is the sibling.

    What breaks if this is deleted: a sentence naming the tools another agent may call is put
    under this agent's heading."""
    agent = authority(SideEffect.NONE)
    other = authority(SideEffect.NONE, "ledger.extra_invoice")
    block = ceiling_block(record(agent), reader())
    with pytest.raises(ProfileError):
        ceiling_words(agent, block, tool_rows(other, TOOLS))
    assert ceiling_words(agent, block, tool_rows(agent, TOOLS)).tools


# ----------------------------------------------------------------------- the side effect
def test_the_side_effect_sentence_rules_out_every_larger_effect_and_nothing_at_or_below() -> None:
    """Each largest effect admits its own words and names every effect above it in the gate's
    order as something the agent cannot do, and none at or below it.

    What breaks if this is deleted: a draft agent's Profile stops saying it cannot send, or says a
    sending agent cannot send, and a reader decides about trust on a sentence that is wrong."""
    assert above(SideEffect.DRAFT) == (SideEffect.WRITE, SideEffect.SEND, SideEffect.MONEY)
    assert above(SideEffect.MONEY) == ()
    assert effect_sentence(SideEffect.DRAFT) == (
        "At most it prepares a draft for a person. It cannot change a record, send anything or "
        "move money."
    )
    assert effect_sentence(SideEffect.NONE) == (
        "It may only read. It cannot prepare a draft, change a record, send anything or move money."
    )
    assert effect_sentence(SideEffect.MONEY) == "At most it moves money."
    order = list(SideEffect)
    for largest in SideEffect:
        said = effect_sentence(largest)
        assert said.startswith(MAY[largest])
        for other in CANNOT:
            assert (CANNOT[other] in said) is (order.index(other) > order.index(largest))


def test_a_tool_is_within_the_ceiling_exactly_when_the_gate_would_keep_it() -> None:
    """Asked of `project` itself, for every largest side effect: a caller holding what every tool
    needs keeps exactly the rows marked within the ceiling, and a name nothing registers is not
    one of them.

    What breaks if this is deleted: the Profile's comparison of side effects drifts from the one
    the gate makes, and a tool the gate drops is listed as one a run could call."""
    caller = reader("read:invoice.reference")
    for largest in SideEffect:
        agent = authority(largest, "ledger.ghost_invoice")
        kept = project(
            TOOLS,
            caller,
            AgentCeiling(
                agent_id="quote_helper",
                allowed_tools=agent.allowed_tools,
                max_side_effect=largest,
            ),
        )
        rows = tool_rows(agent, TOOLS)
        assert {one.name for one in rows if one.within_ceiling} == set(kept.names), largest
        ghost = next(one for one in rows if one.name == "ledger.ghost_invoice")
        assert ghost == ToolRow("ledger.ghost_invoice", None, None, None, within_ceiling=False)


def test_the_tools_sentence_names_what_a_run_could_call_or_that_it_calls_nothing() -> None:
    """What breaks if this is deleted: a tool above the ceiling is named as callable, or an agent
    with no usable tool reads as an agent with a blank sentence."""
    agent = authority(SideEffect.DRAFT, "ledger.ghost_invoice")
    assert tools_sentence(tool_rows(agent, TOOLS)) == (
        "It may call ledger.draft_invoice and ledger.read_invoice, and no other tool."
    )
    assert tools_sentence(tool_rows(AgentAuthority(), TOOLS)) == NO_TOOLS


# ---------------------------------------------------------------------------- the leash
TARGETS = ("ledger.draft_invoice", "ledger.post_invoice")
ROWS: tuple[dict[str, str], ...] = (
    {},
    {"department": "web"},
    {"department": "sales"},
    {"department": "hr"},
)
SCOPES = (Scope(), WEB, SALES, Scope(clauses=(Clause(field="department", op=Op.ANY),)))

entries = st.lists(
    st.builds(
        LeashEntry,
        agent_id=st.sampled_from(("quote_helper", "someone_else")),
        target=st.sampled_from(TARGETS),
        scope=st.sampled_from(SCOPES),
        rung=st.sampled_from(tuple(AutonomyTier)),
    ),
    max_size=6,
)


@settings(max_examples=300, deadline=None)
@given(found=entries)
def test_every_rung_the_leash_gives_any_row_is_among_the_rungs_a_page_is_told(
    found: list[LeashEntry],
) -> None:
    """For any leash and any row, `Leash.rung_for` answers one of `rungs_for`.

    What breaks if this is deleted: the Profile tells a reader an action waits for approval
    everywhere while a scoped entry lets it run on its own in one department, which is the one
    misstatement a page about supervision must not make."""
    leash = Leash(entries=tuple(found))
    for target in TARGETS:
        told = rungs_for(leash, "quote_helper", target)
        assert list(told) == sorted(set(told))
        for row in ROWS:
            assert leash.rung_for("quote_helper", target, row) in told


@settings(max_examples=200, deadline=None)
@given(rungs=st.lists(st.sampled_from(tuple(AutonomyTier)), min_size=1, max_size=4))
def test_a_leash_of_entries_that_apply_everywhere_is_told_as_one_rung(
    rungs: list[AutonomyTier],
) -> None:
    """With no scoped entry the set is exactly the rung every row gets, so the precision the page
    has for today's leashes is not lost to the soundness above.

    What breaks if this is deleted: `rungs_for` can return every rung for every target, which is
    sound and tells a reader nothing."""
    leash = Leash(
        entries=tuple(
            LeashEntry(agent_id="quote_helper", target=TARGETS[0], scope=Scope(), rung=one)
            for one in rungs
        )
    )
    assert rungs_for(leash, "quote_helper", TARGETS[0]) == (min(rungs),)


def test_a_scoped_entry_runs_in_its_rows_and_is_shadow_elsewhere_unless_an_entry_caps_it() -> None:
    """A lone scoped entry leaves Shadow possible outside its rows; an entry that applies
    everywhere caps what a scoped one can raise and lets it lower; a target nothing names is Shadow
    alone; and another agent's entry changes nothing.

    What breaks if this is deleted: the page's rung for a scoped leash is right by accident, and
    the property above is the only thing noticing, one generated leash at a time."""
    lone = Leash(
        entries=(
            LeashEntry(agent_id="quote_helper", target=TARGETS[0], scope=WEB, rung=AUTONOMOUS),
        )
    )
    assert rungs_for(lone, "quote_helper", TARGETS[0]) == (SHADOW, AUTONOMOUS)
    capped = lone.with_entry(
        LeashEntry(agent_id="quote_helper", target=TARGETS[0], scope=Scope(), rung=ASSISTED)
    )
    assert rungs_for(capped, "quote_helper", TARGETS[0]) == (ASSISTED,)
    lowered = capped.with_entry(
        LeashEntry(agent_id="quote_helper", target=TARGETS[0], scope=SALES, rung=SHADOW)
    )
    assert rungs_for(lowered, "quote_helper", TARGETS[0]) == (SHADOW, ASSISTED)
    assert rungs_for(lone, "quote_helper", TARGETS[1]) == (SHADOW,)
    assert rungs_for(lone, "someone_else", TARGETS[0]) == (SHADOW,)


def test_the_leash_rows_are_every_configured_target_and_every_action_nothing_names() -> None:
    """An entry for a read tool is a row that acts on nothing, an entry for an action is a row
    that acts, and an action with no entry is a row on the Shadow default with no entries.

    What breaks if this is deleted: the actions nobody configured, which are the ones Shadow exists
    for, vanish from the page, or an entry for a tool the agent cannot use reads as an action."""
    leash = Leash(
        entries=(
            LeashEntry(
                agent_id="quote_helper",
                target="ledger.read_invoice",
                scope=Scope(),
                rung=AUTONOMOUS,
            ),
            LeashEntry(
                agent_id="quote_helper", target="ledger.draft_invoice", scope=WEB, rung=ASSISTED
            ),
            LeashEntry(
                agent_id="someone_else",
                target="ledger.post_invoice",
                scope=Scope(),
                rung=AUTONOMOUS,
            ),
        )
    )
    rows = leash_rows(leash, "quote_helper", ("ledger.draft_invoice", "ledger.post_invoice"))

    assert [(one.target, one.rungs, one.configured, one.acts) for one in rows] == [
        ("ledger.draft_invoice", (SHADOW, ASSISTED), True, True),
        ("ledger.post_invoice", (SHADOW,), False, True),
        ("ledger.read_invoice", (AUTONOMOUS,), True, False),
    ]
    assert rows[0].entries == (
        LeashEntryWords(rung=ASSISTED, where="Only rows where department is web."),
    )
    assert rows[2].entries == (LeashEntryWords(rung=AUTONOMOUS, where=None),)


def test_the_highest_rung_is_over_the_actions_and_absent_for_an_agent_that_only_reads() -> None:
    """An autonomous entry on a read tool raises nothing, a scoped assisted action counts at its
    highest, and an agent with no action has no rung at all.

    What breaks if this is deleted: the header says an agent runs on its own because of a read it
    was trusted with, or an agent that only reads is shown on the Shadow rung as though it acted."""
    leash = Leash(
        entries=(
            LeashEntry(
                agent_id="quote_helper",
                target="ledger.read_invoice",
                scope=Scope(),
                rung=AUTONOMOUS,
            ),
            LeashEntry(
                agent_id="quote_helper", target="ledger.draft_invoice", scope=WEB, rung=ASSISTED
            ),
        )
    )
    assert leash_up_to(leash_rows(leash, "quote_helper", ("ledger.draft_invoice",))) is ASSISTED
    assert leash_up_to(leash_rows(leash, "quote_helper", ("ledger.post_invoice",))) is SHADOW
    assert leash_up_to(leash_rows(leash, "quote_helper", ())) is None


def test_a_rung_travels_as_the_word_the_leash_names_it_by() -> None:
    """What breaks if this is deleted: the page receives a number, or a rung renamed in the leash
    travels under its old word."""
    assert [rung_key(one) for one in AutonomyTier] == ["shadow", "assisted", "autonomous"]


# ------------------------------------------------------------------------------ the spend
def sources_under(root: Path) -> dict[str, str]:
    return {
        ".".join(path.relative_to(root).with_suffix("").parts): path.read_text(encoding="utf-8")
        for path in root.rglob("*.py")
    }


def test_the_page_is_told_nothing_records_a_runs_cost_while_nothing_in_the_source_writes_one() -> (
    None
):
    """Read off the source rather than trusted: no module under `src/brain` reaches
    `brain.ops.spend_store.record`, the flag says nothing is recorded, and the diagnostic agrees.

    What breaks if this is deleted: the day a writer lands, the page goes on saying a figure is
    not recorded, or the flag is flipped and every agent's nought is drawn as a measurement."""
    every = sources_under(SRC)
    assert "brain.ops.spend_store" in every
    assert spend_writers(every) == ()
    assert RUN_SPEND_IS_RECORDED is False
    assert profile_gaps(sources=every) == ()


WRITERS = {
    "calls.by_module": (
        "from brain.ops import spend_store\n"
        "async def f(s, a):\n"
        "    await spend_store.record(s, a)\n"
    ),
    "calls.by_name": (
        "from brain.ops.spend_store import record as keep\n"
        "async def f(s, a):\n"
        "    await keep(s, a)\n"
    ),
    "calls.by_path": (
        "import brain.ops.spend_store\n"
        "async def f(s, a):\n"
        "    await brain.ops.spend_store.record(s, a)\n"
    ),
    "hands.it.on": "from brain.ops import spend_store as store\nWRITE = store.record\n",
}
READERS = {
    "reads.daily": (
        "from brain.ops import spend_store\n"
        "async def f(s):\n"
        "    return await spend_store.read_spend_daily(s)\n"
    ),
    "own.record": "def record(x):\n    return x\nrecord(1)\n",
    "other.record": "from brain.audit import ledger\nledger.record(1)\n",
    "brain.ops.spend_store": (
        "async def record(s, a):\n    pass\nasync def g(s, a):\n    await record(s, a)\n"
    ),
}


def test_every_way_a_module_reaches_the_writer_is_found_and_nothing_else_is() -> None:
    """The module's attribute called, the function imported under another name, the dotted path,
    and the writer handed on uncalled are each a writer; a different function of the store, a
    function of the same name elsewhere and the store's own module are not.

    What breaks if this is deleted: a writer reached one way the parser does not know keeps the
    page saying nothing is recorded, or every module with a `record` of its own flips it."""
    assert spend_writers({**WRITERS, **READERS}) == tuple(sorted(WRITERS))


def test_the_flag_and_the_source_disagreeing_is_a_gap_in_either_direction() -> None:
    """A writer with the flag false and the flag true with no writer are both reported; the two
    agreeing is not.

    What breaks if this is deleted: the diagnostic reports nothing whatever the source says, and
    the test of the real tree above passes for a check that cannot fail."""
    one = {"calls.by_module": WRITERS["calls.by_module"]}
    assert profile_gaps(sources=one, recorded=False)
    assert profile_gaps(sources={}, recorded=True)
    assert profile_gaps(sources=one, recorded=True) == ()
    assert profile_gaps(sources={}, recorded=False) == ()


def test_no_type_on_the_profile_carries_a_count_of_what_it_withheld() -> None:
    """What breaks if this is deleted: a field counting what the lock withheld is added to the
    ceiling words and nothing reports it."""

    @dataclass(frozen=True)
    class Counted:
        reads: tuple[str, ...]
        hidden: int

    assert profile_gaps(sources={}, surface=(Counted,))
    assert profile_gaps(sources={}) == ()
