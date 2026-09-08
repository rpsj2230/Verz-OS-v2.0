"""The rehearsal and the publish gate held to the rules a builder makes necessary.

A builder inverts the usual risk. Everywhere else somebody asks a question and the gate
decides what they may be told; here somebody builds the asker, and two things follow that
nothing else in the system has to worry about.

A rehearsal is a run, so it has a reach, and the reach it uses is a fact whether or not
anybody chose it. Run as the author it previews a different run from the one being shipped;
run as the persona and handed back in full it is a way of reading any colleague's data by
picking them. Both readings pass a test that only checks the rehearsal happened.

And a publish is where a ceiling can grow past its author's reach. Nothing they publish widens
their own runs, because their own runs are intersected down to what they hold, so the one seat
the author occupies is the seat the widening is invisible from.

The seven leaves claimed here are the ones with a rule in them rather than a control. A
rehearsal runs at the persona's reach and shows the author no rows (M20.3.3); a system-written
check can block and an author-written one never can (M20.4.1, M20.4.2); a widened ceiling
demotes to shadow and asks for a second approver who is not the author (M20.4.3); an
instruction edit keeps its rung because the gate reads the ceilings rather than the paths
(M20.4.4); a router collision is refused once, naming the route and never the agent (M20.4.5);
and the publish record carries the paths that moved and never what they moved to (M20.4.6).

Real `EntitlementSet`s, real `Scope`s, a real `AgentBinding` and the real screen registry
throughout. A fixture standing in for any of them would be this module agreeing with itself.

Task ids: M20.3.3, M20.4.1, M20.4.2, M20.4.3, M20.4.4, M20.4.5, M20.4.6
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from brain.agents.template import MANIFEST_PATHS
from brain.builder.compose import BuilderError
from brain.builder.publish import (
    A_BUILDER_IS_WHERE_A_CEILING_CAN_OUTGROW_ITS_AUTHORS_REACH,
    APPROVERS_FOR_A_WIDENING,
    APPROVERS_FOR_AN_ORDINARY_PUBLISH,
    INSTRUCTION_PATHS,
    NAMES_THAT_WOULD_CARRY_ANOTHER_PERSONS_ROWS,
    NAMES_THAT_WOULD_PROMOTE_AN_AUTHORS_TEST,
    PERSONA_DETAIL_SCREEN,
    PUBLISH_SURFACE,
    REACH_PATHS,
    REHEARSAL_RUNG,
    Check,
    CheckOrigin,
    Detail,
    PublishDecision,
    PublishRecord,
    Rehearsal,
    RehearsalOutcome,
    approval_refusals,
    approvers_needed,
    binding_collisions,
    blocking_failures,
    decide,
    detail_for,
    instruction_only,
    promotion_shaped_fields,
    publish_gaps,
    reach_refusals,
    record_publish,
    route_key,
    row_shaped_fields,
    rung_after,
    shown,
    widened_capabilities,
)
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import Channel
from brain.gate.injection import AutonomyTier
from brain.gate.select import AgentBinding

AGENT = "support_triage"
AUTHOR = "p_author"
PERSONA = "p_persona"
NOW = datetime(2026, 1, 16, 12, 0, tzinfo=UTC)


def holding(
    principal: str, *capabilities: str, planes: tuple[Plane, ...] = (Plane.CONTENT,)
) -> EntitlementSet:
    """A caller holding these capabilities company-wide, plus the console planes named.

    Both halves matter: `permitted` is a conjunction of the tool's own capability and the
    console plane, and `detail_for` needs one without the other.
    """
    grants = [
        Grant(capability=Capability(value=one), scope=Scope(clauses=())) for one in capabilities
    ]
    grants += [Grant(capability=plane_capability(one), scope=Scope(clauses=())) for one in planes]
    return EntitlementSet(principal_id=principal, grants=tuple(grants))


def ceiling(*pairs: tuple[str, Scope], principal: str = AGENT) -> EntitlementSet:
    """An agent ceiling, written as capability and scope pairs."""
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(
            Grant(capability=Capability(value=value), scope=scope) for value, scope in pairs
        ),
    )


def department(name: str) -> Scope:
    return Scope(clauses=(Clause(field="department", op=Op.EQ, value=name),))


def a_binding(agent: str, *, conversation: str | None = None) -> AgentBinding:
    return AgentBinding(channel=Channel.LARK, agent_id=agent, conversation_id=conversation)


def a_decision(after: EntitlementSet | None = None) -> PublishDecision:
    """The gate's own decision for a publish, so approval can be tested on a real one.

    The decision is built by `decide` rather than by constructing a `PublishDecision`
    directly, because a test that assembled the value the function under test consumes would
    be testing `approval_refusals` against a number this file chose.
    """
    unchanged = ceiling(("read:ticket.subject", Scope(clauses=())))
    return decide(
        agent_id=AGENT,
        current_rung=AutonomyTier.AUTONOMOUS,
        before_ceiling=unchanged,
        after_ceiling=unchanged if after is None else after,
        now=NOW,
    )


# --- a rehearsal runs at the persona's reach (M20.3.3) ----------------------------------------


def test_a_rehearsal_run_at_the_personas_reach_is_accepted() -> None:
    """**M20.3.3.** The positive case. A rehearsal as a persona has to work, or the refusal
    below is satisfied by a function that refuses every pairing and the leaf is closed by
    something that rehearses nothing. Deleting this lets that happen.
    """
    rehearsal = Rehearsal(agent_id=AGENT, persona_id=PERSONA, author_id=AUTHOR)
    assert reach_refusals(rehearsal, holding(PERSONA, "read:ticket.subject")) == ()


def test_a_rehearsal_handed_the_authors_own_reach_is_refused() -> None:
    """**M20.3.3.** This is the leaf. An `EntitlementSet` for the author and one for the
    persona are the same type, so nothing but the principal on it distinguishes the run being
    previewed from the run being shipped: a rehearsal at the author's reach passes, and then
    somebody else runs the published agent at theirs. Deleting this leaves the two
    indistinguishable and the preview free to lie.
    """
    rehearsal = Rehearsal(agent_id=AGENT, persona_id=PERSONA, author_id=AUTHOR)
    found = reach_refusals(rehearsal, holding(AUTHOR, "read:ticket.subject"))
    assert len(found) == 1
    assert PERSONA in found[0]
    assert AUTHOR in found[0]


def test_a_rehearsal_runs_at_the_rung_that_carries_nothing_out() -> None:
    """**M20.3.3.** A rehearsal that could carry out the action it is rehearsing is not a
    preview, and the shadow rung is the one thing this layer can fasten without a runner.
    Deleting this lets a rehearsal be constructed at an autonomous rung, where the difference
    between a rehearsal and a run is a comment.
    """
    assert REHEARSAL_RUNG is AutonomyTier.SHADOW
    assert Rehearsal(agent_id=AGENT, persona_id=PERSONA, author_id=AUTHOR).rung is REHEARSAL_RUNG
    with pytest.raises(BuilderError, match="not a preview"):
        Rehearsal(
            agent_id=AGENT,
            persona_id=PERSONA,
            author_id=AUTHOR,
            rung=AutonomyTier.AUTONOMOUS,
        )


def test_a_rehearsal_names_an_agent_a_persona_and_somebody_watching() -> None:
    """**M20.3.3.** A rehearsal as nobody has no reach to check, and one nobody is watching is
    a run. Deleting this lets either be built, and `reach_refusals` then compares a principal
    against an empty string and passes.
    """
    with pytest.raises(BuilderError, match="as nobody"):
        Rehearsal(agent_id=AGENT, persona_id=" ", author_id=AUTHOR)
    with pytest.raises(BuilderError, match="not a rehearsal"):
        Rehearsal(agent_id=AGENT, persona_id=PERSONA, author_id="")


def test_the_tools_a_persona_reached_follow_the_grant_that_shows_their_grants() -> None:
    """**M20.3.3.** Naming which tools a persona reached is a statement about that persona's
    grants, and the screen that shows a person's grants has a grant in front of it. Deleting
    this lets the builder answer a question the console answers behind a capability, from a
    surface nobody reviews as a reporting screen.
    """
    may_read_grants = holding(AUTHOR, "read:grant", planes=(Plane.CONFIGURATION,))
    may_not = holding(AUTHOR, "read:ticket.subject", planes=(Plane.CONFIGURATION,))
    assert detail_for(may_read_grants) is Detail.PER_TOOL
    assert detail_for(may_not) is Detail.OUTCOME
    assert PERSONA_DETAIL_SCREEN == "people"


def test_an_author_who_may_not_read_grants_is_shown_the_outcome_and_no_tool_list() -> None:
    """**M20.3.3.** The narrowing itself, as against the decision about it. The tool list is
    emptied rather than counted, because a count of tools the reader may not be told about is
    the same disclosure with a digit in front of it. Deleting this lets `detail_for` be
    computed and then ignored.
    """
    outcome = RehearsalOutcome(
        agent_id=AGENT,
        persona_id=PERSONA,
        answered=True,
        tools_reached=("helpdesk.read_ticket", "crm.read_client"),
    )
    assert shown(outcome, Detail.PER_TOOL) == outcome
    narrowed = shown(outcome, Detail.OUTCOME)
    assert narrowed.tools_reached == ()
    assert narrowed.answered is True


def test_no_type_in_the_rehearsal_can_carry_the_rows_the_persona_read() -> None:
    """**M20.3.3.** The hazard a builder introduces arrives through the preview before it
    arrives through the publish: a rehearsal that handed its answer back would read any
    colleague's data with no approval anywhere. Deleting this lets a `records` field be added
    to the outcome, with every behavioural test still green.
    """
    assert row_shaped_fields(PUBLISH_SURFACE) == ()
    assert "records" in NAMES_THAT_WOULD_CARRY_ANOTHER_PERSONS_ROWS

    @dataclass(frozen=True)
    class WouldReturnRows:
        records: tuple[str, ...] = ()

    assert any("WouldReturnRows.records" in one for one in publish_gaps(surface=[WouldReturnRows]))


# --- system checks block, author checks never do (M20.4.1, M20.4.2) ---------------------------


def test_a_failing_system_check_stops_the_publish() -> None:
    """**M20.4.1.** A permission canary that could not block would be a report, and a report
    about a permission leak is a thing somebody reads next week. Deleting this lets every
    check become advisory and the gate become a dashboard.
    """
    checks = [Check(name="canary.contract_value", origin=CheckOrigin.SYSTEM, passed=False)]
    assert blocking_failures(checks) == ("canary.contract_value",)


def test_a_failing_author_written_test_does_not_stop_the_publish() -> None:
    """**M20.4.2.** A gate held shut by a test the person being gated owns is a gate with a
    handle on the inside: the way past a failing publish is to edit the test. Deleting this
    lets an author's own test be treated as a canary, which reads as strictness and is the
    opposite.
    """
    checks = [
        Check(name="author.answers_in_the_house_voice", origin=CheckOrigin.AUTHOR, passed=False),
        Check(name="canary.contract_value", origin=CheckOrigin.SYSTEM, passed=True),
    ]
    assert blocking_failures(checks) == ()


def test_a_passing_system_check_stops_nothing() -> None:
    """**M20.4.1.** The positive case. A gate satisfied by refusing every publish would pass
    the two tests above, and nothing would ever ship. Deleting this lets `blocks` become
    "written by the system", which is every canary whether it passed or not.
    """
    assert blocking_failures([Check(name="c", origin=CheckOrigin.SYSTEM, passed=True)]) == ()
    assert Check(name="c", origin=CheckOrigin.SYSTEM, passed=False).blocks is True
    assert Check(name="c", origin=CheckOrigin.AUTHOR, passed=False).blocks is False


def test_a_check_with_no_name_is_refused() -> None:
    """**Written because a mutation of this guard survived the whole file.** Every check built
    anywhere here was named, so the refusal could be deleted and the suite would have stayed
    green.

    The name is the entire content of a blocked publish. `blocking_failures` returns names and
    nothing else, deliberately: the author is told which check stopped them and never what it
    found, because what a permission canary found is somebody's data. So an unnamed failing
    check is a publish refused with an empty string as the reason, and the only ways past it
    are to guess or to ask somebody with more reach to look.

    Blank as well as empty, because a check registered through anything that trims nothing
    arrives with a space rather than with nothing at all.

    Delete this and a builder can be stopped by a check nobody can argue with or fix."""
    for missing in ("", "   "):
        with pytest.raises(BuilderError, match="a check with no name"):
            Check(name=missing, origin=CheckOrigin.SYSTEM, passed=False)

    assert Check(name="canary.contract_value", origin=CheckOrigin.SYSTEM, passed=False).name


def test_nothing_on_a_check_could_promote_an_authors_test_to_blocking() -> None:
    """**M20.4.2.** "Advisory forever" is a claim about every future edit, and a claim of that
    shape only survives as a check on the type: `blocks` is a property computed from the
    origin, so there is nothing to set. Deleting this lets a `blocking` field be added, after
    which the origin decides nothing.
    """
    assert promotion_shaped_fields(Check) == ()
    assert "blocking" in NAMES_THAT_WOULD_PROMOTE_AN_AUTHORS_TEST

    @dataclass(frozen=True)
    class WouldPromote:
        blocking: bool = False

    assert any("WouldPromote.blocking" in one for one in publish_gaps(check_type=WouldPromote))


# --- a widened ceiling demotes and asks for a second approver (M20.4.3) -----------------------


def test_a_capability_the_old_ceiling_did_not_cover_is_a_widening() -> None:
    """**M20.4.3.** This is the leaf, and the hazard is that it is invisible from the author's
    own seat: their runs are intersected down to what they hold, so a ceiling wider than their
    reach never shows up in anything they can see. Deleting this lets one ship silently.
    """
    before = ceiling(("read:ticket.subject", Scope(clauses=())))
    after = ceiling(
        ("read:ticket.subject", Scope(clauses=())),
        ("read:invoice.total", Scope(clauses=())),
    )
    assert widened_capabilities(before, after, now=NOW) == ("read:invoice.total",)
    assert A_BUILDER_IS_WHERE_A_CEILING_CAN_OUTGROW_ITS_AUTHORS_REACH


def test_a_scope_that_lost_a_clause_is_a_widening() -> None:
    """**M20.4.3.** The second way a ceiling grows, and the one a capability-name comparison
    misses entirely: the same capability, company-wide instead of in one department. A scope
    is a conjunction, so it is no wider exactly when it keeps every clause it had. Deleting
    this lets an unrestricted rewrite of a departmental ceiling publish as an ordinary edit.
    """
    before = ceiling(("read:ticket.subject", department("web")))
    after = ceiling(("read:ticket.subject", Scope(clauses=())))
    assert widened_capabilities(before, after, now=NOW) == ("read:ticket.subject",)


def test_a_narrowed_ceiling_is_not_a_widening() -> None:
    """**M20.4.3.** The positive case, and it has to be tested or the comparison is satisfied
    by a function that calls everything a widening, which demotes every publish to shadow and
    makes the gate useless enough to be switched off. Deleting this lets that ship.
    """
    before = ceiling(("read:ticket.subject", Scope(clauses=())))
    after = ceiling(("read:ticket.subject", department("web")))
    assert widened_capabilities(before, after, now=NOW) == ()
    assert widened_capabilities(before, before, now=NOW) == ()


def test_a_widening_demotes_to_shadow_and_asks_for_one_more_approver_than_usual() -> None:
    """**M20.4.3.** Shadow is the rung at which an action is simulated and shown to somebody,
    which is the honest answer for reach nobody could review from the seat it was authored in.
    Deleting this lets a widening publish at whatever rung the agent already had.
    """
    assert rung_after(AutonomyTier.AUTONOMOUS, ["read:invoice.total"]) is AutonomyTier.SHADOW
    assert rung_after(AutonomyTier.AUTONOMOUS, []) is AutonomyTier.AUTONOMOUS
    assert approvers_needed(["read:invoice.total"]) == APPROVERS_FOR_A_WIDENING
    assert approvers_needed([]) == APPROVERS_FOR_AN_ORDINARY_PUBLISH
    # Against each other rather than against themselves: "a second approver" means exactly one
    # more than the ordinary case, which is a relation a mutation of either figure breaks.
    assert APPROVERS_FOR_A_WIDENING == APPROVERS_FOR_AN_ORDINARY_PUBLISH + 1


def test_the_author_may_not_be_an_approver_of_their_own_publish() -> None:
    """**M20.4.3.** An approval given by the person who wants it tells nobody anything and
    passes every test that checks an approval was recorded. It is the rule the steward notice
    keeps about a notice addressed to the actor. Deleting this lets a widening be approved by
    the person who cannot see it.
    """
    decision = a_decision(
        ceiling(
            ("read:ticket.subject", Scope(clauses=())),
            ("read:invoice.total", Scope(clauses=())),
        )
    )
    # An ordinary publish with the author and one other person: the head count is satisfied,
    # so the only thing left to refuse is the self-approval. Asserting it here rather than on
    # the widening is the difference between testing this rule and testing the count beside it.
    ordinary = approval_refusals(a_decision(), author_id=AUTHOR, approvers=[AUTHOR, "p_two"])
    assert len(ordinary) == 1
    assert AUTHOR in ordinary[0]

    assert approval_refusals(decision, author_id=AUTHOR, approvers=[AUTHOR, "p_two"])
    assert approval_refusals(decision, author_id=AUTHOR, approvers=["p_two"])
    assert approval_refusals(decision, author_id=AUTHOR, approvers=["p_two", "p_two"])
    assert approval_refusals(decision, author_id=AUTHOR, approvers=["p_two", "p_three"]) == ()


def test_an_ordinary_publish_needs_one_approver_who_is_not_the_author() -> None:
    """**M20.4.3.** The positive case for approval. A refusal function that refused every
    approval would pass the test above, and nothing would ever publish. Deleting this lets the
    count be raised for every publish rather than only for a widening.
    """
    decision = a_decision()
    assert approval_refusals(decision, author_id=AUTHOR, approvers=["p_two"]) == ()
    assert approval_refusals(decision, author_id=AUTHOR, approvers=[]) != ()


# --- instruction edits keep their rung (M20.4.4) ----------------------------------------------


def test_an_instruction_edit_publishes_without_demotion() -> None:
    """**M20.4.4.** An edit to the persona leaves the ceiling identical, so there is nothing to
    demote for, and the gate reaches that answer by reading the ceilings rather than a path
    list somebody maintains by hand. Deleting this lets a demotion be triggered by any diff,
    which trains everybody to approve them.
    """
    same = ceiling(("read:ticket.subject", department("web")))
    decision = decide(
        agent_id=AGENT,
        current_rung=AutonomyTier.AUTONOMOUS,
        before_ceiling=same,
        after_ceiling=same,
        now=NOW,
    )
    assert decision.rung is AutonomyTier.AUTONOMOUS
    assert decision.approvers == APPROVERS_FOR_AN_ORDINARY_PUBLISH
    assert decision.widenings == ()
    assert decision.may_publish is True


def test_every_manifest_path_is_classified_as_reach_or_as_instruction() -> None:
    """**M20.4.4.** A path in neither classification is one nobody has decided about, and the
    default it falls into decides whether editing it asks for a second pair of eyes. Deleting
    this lets a new authority path be added and read as an instruction.
    """
    declared = set(MANIFEST_PATHS)
    assert REACH_PATHS.issubset(declared)
    assert REACH_PATHS.union(INSTRUCTION_PATHS) == declared
    assert REACH_PATHS.isdisjoint(INSTRUCTION_PATHS)
    assert instruction_only(["persona", "identity.summary"]) is True
    assert instruction_only(["persona", "authority.capabilities"]) is False
    assert instruction_only(["authority.scope_predicate"]) is False


def test_a_reach_path_the_manifest_does_not_have_is_reported() -> None:
    """**M20.4.4.** A renamed manifest path leaves its old name classified as reach and its new
    name classified as an instruction by derivation, so an edit to it would publish without
    demotion. Deleting this leaves the rename silent in the permissive direction.
    """
    found = publish_gaps(reach_paths=["authority.capability_list"])
    assert any("authority.capability_list" in one for one in found)


def test_the_gate_takes_no_parameter_that_could_wave_a_publish_through() -> None:
    """**M20.4.4.** The demotion follows the ceilings, and a `paths` parameter would let a
    caller decide its own supervision; a `force` would let one skip a canary. A gate with an
    override is a gate whose real policy is whoever holds the override. Deleting this lets one
    be added quietly.
    """
    assert publish_gaps() == ()

    def would_be_overridable(*, force: bool = False) -> None: ...

    import brain.builder.publish as module

    original = module.decide
    module.decide = would_be_overridable  # type: ignore[assignment]
    try:
        assert any("decide takes force" in one for one in publish_gaps())
    finally:
        module.decide = original


# --- the router collision (M20.4.5) -----------------------------------------------------------


def test_a_route_already_bound_to_another_agent_is_refused() -> None:
    """**M20.4.5.** Two agents on one route is a router that answers whichever it iterated
    first, which is a routing decision nobody made. Deleting this lets a publish take a route
    from an agent that was already answering on it.
    """
    found = binding_collisions(a_binding(AGENT), [a_binding("finance_desk")])
    assert len(found) == 1
    assert route_key(a_binding(AGENT)) in found[0]


def test_a_collision_refusal_names_the_route_and_never_the_agent_on_it() -> None:
    """**M20.4.5.** The refusal goes to somebody who may not be entitled to know the other
    agent exists, and one publish attempt per route would enumerate the router. Deleting this
    lets the message become the useful one, which is the disclosure.
    """
    found = binding_collisions(a_binding(AGENT), [a_binding("finance_desk")])
    assert "finance_desk" not in found[0]


def test_two_agents_on_one_route_produce_one_refusal_and_not_two() -> None:
    """**M20.4.5.** A refusal per collision is a count of things the reader may not see, which
    is the disclosure by subtraction wearing a list. Deleting this lets the author count the
    agents on a route by reading how many refusals came back.
    """
    found = binding_collisions(
        a_binding(AGENT), [a_binding("finance_desk"), a_binding("delivery_desk")]
    )
    assert len(found) == 1


def test_a_free_route_and_an_agents_own_route_are_not_collisions() -> None:
    """**M20.4.5.** The positive case, twice. A check that refused every binding would pass the
    three above and nothing could ever be published; and republishing an agent onto the route
    it already holds must not be refused as a clash with itself. Deleting this lets either
    happen.
    """
    assert binding_collisions(a_binding(AGENT), []) == ()
    assert binding_collisions(a_binding(AGENT), [a_binding(AGENT)]) == ()
    assert (
        binding_collisions(a_binding(AGENT, conversation="c1"), [a_binding("finance_desk")]) == ()
    )


def test_a_collision_refuses_the_publish_rather_than_demoting_it() -> None:
    """**M20.4.5.** A refusal and a demotion are different outcomes rather than degrees of one:
    a collision means this publish does not happen, and a widening means it happens under
    supervision. Deleting this lets the two be collapsed, which makes a widening refusable and
    a collision survivable, both the wrong way round.
    """
    decision = decide(
        agent_id=AGENT,
        current_rung=AutonomyTier.AUTONOMOUS,
        before_ceiling=ceiling(("read:ticket.subject", Scope(clauses=()))),
        after_ceiling=ceiling(("read:ticket.subject", Scope(clauses=()))),
        candidate_binding=a_binding(AGENT),
        published_bindings=[a_binding("finance_desk")],
        now=NOW,
    )
    assert decision.may_publish is False
    assert decision.rung is AutonomyTier.AUTONOMOUS


# --- the publish record (M20.4.6) --------------------------------------------------------------


def test_the_publish_record_says_who_when_and_which_paths_moved() -> None:
    """**M20.4.6.** The record is the only thing that says a publish happened at all, and a
    later reader needs the actor, the instant and what changed to reconstruct it. Deleting this
    lets the paths come back empty with every other test green.
    """
    record = record_publish(
        agent_id=AGENT,
        actor_id=AUTHOR,
        at=NOW,
        before={"persona": "old", "tier": "fast"},
        after={"persona": "new", "tier": "fast"},
        decision=a_decision(),
        approvers=["p_two"],
    )
    assert record.actor_id == AUTHOR
    assert record.at == NOW
    assert record.paths == ("persona",)
    assert record.approvers == ("p_two",)
    assert record.rung is AutonomyTier.AUTONOMOUS


def test_the_publish_record_carries_no_field_a_value_could_arrive_in() -> None:
    """**M20.4.6.** The obvious record holds the before and after of what changed, and for a
    publish that is the before and after of the authority section: a map of what an agent may
    reach, in the longest-retained record in the system. Deleting this lets a `diff` field be
    added, which is exactly the field somebody adds to make the record useful.
    """

    @dataclass(frozen=True)
    class WouldCarryValues:
        diff: str = ""

    assert any("WouldCarryValues.diff" in one for one in publish_gaps(record_type=WouldCarryValues))
    assert publish_gaps(record_type=PublishRecord) == ()


def test_a_publish_recorded_at_a_naive_instant_is_refused() -> None:
    """**M20.4.6.** The record is what a later reader orders the history by, and a naive
    instant is wrong by the host's offset from UTC in a direction that does not announce
    itself. Deleting this lets two publishes an hour apart be recorded in the wrong order.
    """
    with pytest.raises(BuilderError, match="naive instant"):
        PublishRecord(
            agent_id=AGENT,
            actor_id=AUTHOR,
            at=datetime(2026, 1, 16, 12, 0),
            paths=(),
            rung=AutonomyTier.SHADOW,
            approvers=(),
        )
    with pytest.raises(BuilderError, match="no actor"):
        PublishRecord(
            agent_id=AGENT,
            actor_id="",
            at=NOW,
            paths=(),
            rung=AutonomyTier.SHADOW,
            approvers=(),
        )


# --- the module holds no copy of the invariant --------------------------------------------------


def test_the_publish_gate_computes_no_reach_of_its_own() -> None:
    """**M20.4.3.** The gate compares two declared ceilings, which is a different question from
    what one person gets through one agent, and answering the second here would be a copy of
    the platform's central rule in the layer that decides what ships. Deleting this lets one be
    added, and the copy that is subtly wrong is the one in production.
    """
    assert publish_gaps() == ()
    planted = "def f(caller, ceiling):\n    return caller.intersect(ceiling)\n"
    assert any("intersects two entitlement sets" in one for one in publish_gaps(source=planted))
