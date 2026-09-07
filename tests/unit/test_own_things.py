"""A person's own five surfaces, and the predicate that is the same one a store would get.

The file is written around one claim: **"their own" is a permission claim, not a filter**, so
the narrowing here is a `Scope` and not a comparison. The first two tests are that claim, and
they drive the predicate through both evaluators, the SQL one and the Python one, because a
personal surface whose in-memory filter and whose query disagree is one that shows a person
somebody else's row on exactly one of the two paths.

The other tests are the five leaves. An agent is somebody's own when they steward it and never
when they merely built it (M33.3.1.1). A knowledge item stays theirs after it is promoted
(M33.3.1.2). An export is built from the narrowed turns rather than from the input, which is
the whole of that function (M33.3.1.3). A memory is theirs by authorship, the delete control
writes a mark and refuses somebody else's (M33.3.1.4). And a person's ceilings are paired with
what they actually spent inside each period's window, with a ceiling nobody supplied a window
for left out rather than reported at zero (M33.3.1.5).

Real `AgentRecord`s, real `KnowledgeItem`s, a real `Learning` through `brain.memory.tiers.
propose`, real `Actual`s and real `BudgetRow`s throughout. The export test runs
`brain.ops.export.conversation_export` rather than inspecting the arguments handed to it,
because the claim is about what comes back.

Task ids: M33.3.1.1, M33.3.1.2, M33.3.1.3, M33.3.1.4, M33.3.1.5
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.chat.turns import Turn, TurnKind
from brain.console.own_things import (
    NAMES_THAT_WOULD_MEAN_EVERYBODY,
    OWN_LEVEL,
    PERSONAL_SURFACE,
    OwnThingsError,
    delete_own_memory,
    export_own_history,
    is_own,
    own_agents,
    own_allowances,
    own_gaps,
    own_history,
    own_knowledge,
    own_memory,
    own_scope,
)
from brain.core.entitlement import Capability
from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.core.scope_sql import ColumnLayout, compile_where
from brain.gate.context import TrafficClass
from brain.knowledge.item import KnowledgeItem
from brain.knowledge.visibility import (
    OWNER_FIELD,
    KnowledgeVisibility,
    Visibility,
    VisibilityError,
)
from brain.memory.correction import Correction, Demotion
from brain.memory.digest import Learning
from brain.memory.formation import Formation
from brain.memory.tiers import Change, propose
from brain.ops.budgets import BudgetLevel, BudgetPeriod, BudgetRow
from brain.ops.spend import Actual

#: A fixed moment, so a window test cannot pass because the machine's clock sat on the
#: convenient side of a boundary. Everything below is relative to it.
NOW = datetime(2027, 5, 4, 10, 0, tzinfo=UTC)

#: Two people, so a personal surface has somebody to leave out.
ME = "u_me"
THEM = "u_them"

MAINTENANCE = "maintenance"

#: The whole month and the day inside it, for the allowance join.
MONTH = (NOW - timedelta(days=30), NOW)
DAY = (NOW - timedelta(hours=24), NOW)


def an_agent(
    *,
    owner_id: str,
    agent_id: str = "a_one",
    created_by: str = THEM,
    level: Visibility = Visibility.DEPARTMENT,
    archived: bool = False,
) -> AgentRecord:
    """One agent, whose steward and whose author can be told apart."""
    return AgentRecord(
        agent_id=agent_id,
        display_name="Reporter",
        persona="answers questions about clients",
        audience=AgentAudience(
            level=level,
            owner_id=owner_id,
            department=MAINTENANCE if level is Visibility.DEPARTMENT else "",
        ),
        authority=AgentAuthority(scope=Scope.department(MAINTENANCE)),
        created_by=created_by,
        archived_at=NOW - timedelta(days=1) if archived else None,
    )


def an_item(*, owner_id: str, level: Visibility, item_id: str = "k_one") -> KnowledgeItem:
    """One knowledge item, owned by somebody and visible at some level."""
    visibility = (
        KnowledgeVisibility.personal(owner_id)
        if level is Visibility.PERSONAL
        else KnowledgeVisibility.company(owner_id=owner_id)
    )
    return KnowledgeItem(
        item_id=item_id,
        content="the hosting renewal runbook",
        title="Renewals",
        visibility=visibility,
        owner_id=owner_id,
    )


def a_turn(*, principal_id: str, minutes: int) -> Turn:
    return Turn(
        kind=TurnKind.QUESTION,
        at=NOW - timedelta(minutes=minutes),
        principal_id=principal_id,
        text="what is left on the retainer",
    )


def a_learning(*, principal_id: str, memory_id: str = "m_one") -> Learning:
    """One learning, formed from somebody's own conversation."""
    return Learning(
        memory_id=memory_id,
        proposal=propose(Change.PREFERENCE, subject=memory_id),
        formation=Formation(
            principal_id=principal_id,
            capabilities=(Capability(value="read:client.name"),),
            scope=Scope.department(MAINTENANCE),
            ent_hash="a" * 32,
            formed_at=NOW - timedelta(days=1),
        ),
    )


def an_actual(*, principal_id: str, cost_minor: int, hours_ago: int) -> Actual:
    return Actual(
        principal_id=principal_id,
        principal_kind=PrincipalKind.HUMAN,
        traffic=TrafficClass.HUMAN_INTERACTIVE,
        department=MAINTENANCE,
        agent_id="a_one",
        model="a-model",
        lane=Lane.ANSWER,
        cost_minor=cost_minor,
        at=NOW - timedelta(hours=hours_ago),
    )


def a_budget(
    *,
    subject: str,
    period: BudgetPeriod,
    ceiling_minor: int = 10_000,
    level: BudgetLevel = OWN_LEVEL,
) -> BudgetRow:
    return BudgetRow(
        level=level,
        subject=subject,
        period=period,
        ceiling_minor=ceiling_minor,
        version=1,
        author="u_owner",
        effective_from=NOW - timedelta(days=90),
        reason="written for a test",
    )


# ------------------------------------------------------ the predicate, and both evaluators
def test_the_narrowing_is_the_same_predicate_a_query_would_be_given() -> None:
    """**The claim the module is built on, driven through both evaluators.**

    A personal surface can filter rows it already read or hand a store a predicate, and the
    two look identical from the screen while differing entirely in what was disclosed. So
    `own_scope` returns a `Scope`, and this asserts that the same scope compiles to SQL
    through `brain.core.scope_sql.compile_where` and decides in Python through
    `Scope.matches`, with the owner travelling as a bound parameter rather than as text in
    the statement.

    Delete this and `own_scope` can quietly become a comparison written here, the SQL path
    stops existing, and every personal screen reads the whole table before narrowing it."""
    scope = own_scope(ME)
    compiled = compile_where(scope, ColumnLayout(promoted=frozenset({OWNER_FIELD})))

    assert scope.matches({OWNER_FIELD: ME})
    assert not scope.matches({OWNER_FIELD: THEM})
    assert ME in compiled.params.values()
    assert ME not in compiled.where


def test_a_personal_scope_with_no_owner_is_refused_rather_than_built() -> None:
    """A personal scope without an owner is `Scope()`, which is the unrestricted scope, so
    the narrowest level in the system becomes the widest through a blank form field.
    `brain.knowledge.visibility.scope_for` refuses it and `own_scope` routes through that
    function rather than constructing a one-clause scope of its own.

    **Asserted through `is_own` as well as through `own_scope`, and a mutation is why.**
    Replacing the body of `is_own` with `principal_id == owner_id` survives every other test
    in this file, because the two agree on every pair of non-empty strings. They differ on
    the pair that matters: an empty principal and an unowned record are two empty strings, a
    comparison calls them equal, and a half-configured session then owns every half-migrated
    row in the store. Routing through `scope_for` turns that into a refusal.

    Delete this and a second construction here can arrive without the refusal, and an empty
    principal id turns a personal screen into the company's."""
    with pytest.raises(VisibilityError, match="needs an owner"):
        own_scope("")
    with pytest.raises(VisibilityError, match="needs an owner"):
        is_own("", "")


def test_a_record_with_no_owner_belongs_to_nobody_rather_than_everybody() -> None:
    """`Clause.matches` admits no row missing the field and no row whose value differs, which
    is `brain.core.scope`'s rule that absent is not permitted, and this asserts it reaches
    through `is_own` rather than being something a caller has to know.

    Delete this and an unowned record, which is what a half-migrated row looks like, appears
    on everybody's personal screen at once."""
    assert is_own(ME, ME)
    assert not is_own(ME, THEM)
    assert not is_own(ME, "")


# ------------------------------------------------------------------- own agents (M33.3.1.1)
def test_an_agent_is_somebodys_own_when_they_steward_it_and_not_when_they_built_it() -> None:
    """`brain.agents.model` keeps `created_by` and `audience.owner_id` apart because the first
    is history and never moves and the second is who answers for the thing now. A personal
    list built on authorship never shrinks and contains things the person cannot change.

    Both directions are asserted, because a filter written on the wrong field passes any test
    whose fixture sets the two to the same value.

    Delete this and ownership transfer stops changing anybody's personal screen, which is the
    thing transferring is for."""
    stewarded = an_agent(owner_id=ME, created_by=THEM, agent_id="a_mine")
    authored = an_agent(owner_id=THEM, created_by=ME, agent_id="a_handed_over")

    assert own_agents([stewarded, authored], principal_id=ME) == (stewarded,)


def test_a_department_visible_agent_somebody_stewards_is_still_their_own() -> None:
    """The gap this closes. `brain.identity.lifecycle.agents_following` filters on the
    personal visibility level as well as the owner, correctly, because it answers which
    agents follow somebody changing department. A personal surface asking the same question
    would drop every agent its owner had made visible to their team.

    Delete this and a visibility filter creeps back in, and the person who publishes an agent
    to their department loses it from their own screen as a consequence."""
    departmental = an_agent(owner_id=ME, level=Visibility.DEPARTMENT, agent_id="a_dept")
    personal = an_agent(owner_id=ME, level=Visibility.PERSONAL, agent_id="a_personal")

    assert own_agents([departmental, personal], principal_id=ME) == (departmental, personal)


def test_an_archived_agent_is_absent_and_a_disabled_one_is_present() -> None:
    """Archiving is terminal in `brain.agents.lifecycle`'s own words and disabling is
    reversible, so a personal listing that showed an archived record would offer controls
    over something that cannot come back, and one that hid a disabled record would hide the
    thing its owner is about to re-enable.

    Delete this and the two lifecycle states collapse into one, and whichever way they
    collapse is wrong for half of them."""
    archived = an_agent(owner_id=ME, agent_id="a_gone", archived=True)
    live = an_agent(owner_id=ME, agent_id="a_here")

    assert own_agents([archived, live], principal_id=ME) == (live,)


# ---------------------------------------------------------------- own knowledge (M33.3.1.2)
def test_a_knowledge_item_stays_its_owners_after_it_is_promoted() -> None:
    """An item somebody uploaded and later had promoted to the company is still theirs to
    steward. Narrowing this list by visibility level would make a personal library shrink as
    a reward for publishing, and the person who published would go looking for it on a screen
    it is no longer on.

    Delete this and `own_scope` gets reused as a visibility filter, which is the other
    question that same function answers and is not this one."""
    published = an_item(owner_id=ME, level=Visibility.COMPANY, item_id="k_published")
    draft = an_item(owner_id=ME, level=Visibility.PERSONAL, item_id="k_draft")
    somebody_elses = an_item(owner_id=THEM, level=Visibility.PERSONAL, item_id="k_theirs")

    assert own_knowledge([published, draft, somebody_elses], principal_id=ME) == (
        published,
        draft,
    )


# ------------------------------------------------------------------ own history (M33.3.1.3)
def test_a_history_keeps_the_order_it_arrived_in() -> None:
    """A conversation read out of order is not a conversation, and `Turn.at` is not
    guaranteed distinct within one exchange, so sorting here would reorder an exchange by a
    tie-break nobody chose. The input is deliberately not in time order.

    Delete this and a sort appears, and two turns recorded in the same second swap."""
    second = a_turn(principal_id=ME, minutes=1)
    first = a_turn(principal_id=ME, minutes=9)
    theirs = a_turn(principal_id=THEM, minutes=5)

    assert own_history([second, theirs, first], principal_id=ME) == (second, first)


def test_an_export_is_built_from_the_narrowed_turns_and_never_from_the_input() -> None:
    """**The whole of that function.** `brain.ops.export.conversation_export` takes what it is
    given and its own docstring says the narrowing happened before it: "turns is what this
    caller may see, decided before it gets here". This is where that decision is made, once,
    so a caller who narrowed the screen and forgot the download cannot produce an export of
    somebody else's turns filed under this person's name.

    Asserted on what comes back rather than on the arguments handed over, and the subject is
    asserted alongside, because an export whose contents and whose subject came from two
    parameters is exactly the mixture this prevents.

    Delete this and the export can be wired to the input sequence, which is a one-word change
    and produces a file that looks right to whoever asked for it."""
    mine = a_turn(principal_id=ME, minutes=2)
    theirs = a_turn(principal_id=THEM, minutes=1)

    exported = export_own_history(
        [theirs, mine],
        principal_id=ME,
        conversation_id="c_one",
        at=NOW,
    )

    assert exported.subject_id == ME
    assert tuple(one.principal_id for one in exported.turns) == (ME,)
    assert len(exported.turns) == 1


# ------------------------------------------------------------------- own memory (M33.3.1.4)
def test_a_memory_is_somebodys_own_by_who_was_asking_when_it_formed() -> None:
    """`brain.memory.formation` records the principal for the audit question and its comment
    says the field never permits a recall. This surface reads it as authorship, which is what
    a person means by their own memory, and the test asserts the narrowing without asserting
    anything about recall, which is `may_recall`'s answer and takes an entitlement this
    function does not have.

    Delete this and the owner field starts deciding recall, and a memory comes back because
    the same person returned rather than because they still reach what it was formed from."""
    mine = a_learning(principal_id=ME, memory_id="m_mine")
    theirs = a_learning(principal_id=THEM, memory_id="m_theirs")

    assert own_memory([mine, theirs], principal_id=ME) == (mine,)


def test_the_delete_control_writes_a_mark_rather_than_removing_anything() -> None:
    """**The control the leaf asks for exists and this is what it does.** `brain.memory.review.
    delete` is `digest.undo` renamed, and no removal is reachable: `brain.tables.memory`
    grants SELECT and INSERT on both memory tables, `brain.ops.erasure.StoreEraser` is a
    protocol nothing implements, and the schema has one DELETE grant and it is elsewhere.

    Asserted on the shape of what comes back, which is a correction naming the memory, so a
    console cannot describe this as a purge without the assertion failing first.

    Delete this and the next reader promises a removal the database cannot perform, and the
    person finds out from a later answer that still knows the thing."""
    mine = a_learning(principal_id=ME)

    marked = delete_own_memory(mine, principal_id=ME, at=NOW)

    assert marked.memory_id == "m_one"
    assert isinstance(marked.correction, Demotion)
    assert marked.correction.confidence == 0.0
    assert set(Correction) == {Correction.SUPERSEDED, Correction.DEMOTED}


def test_a_person_cannot_delete_a_memory_formed_from_somebody_elses_conversation() -> None:
    """`brain.memory.review.delete` takes a `Learning` and no principal, correctly, because
    the review queue's delete is an administrator's and is decided by the entitlement filter
    on the queue. A personal control is decided by ownership, and one that took the memory id
    from a form would otherwise undo anybody's.

    Refused rather than returning nothing, because a delete that quietly did nothing reads on
    the screen as a delete that worked.

    Delete this and the personal tab becomes a way to undo the whole company's learning by
    typing an id."""
    theirs = a_learning(principal_id=THEM, memory_id="m_theirs")

    with pytest.raises(OwnThingsError, match="may not delete"):
        delete_own_memory(theirs, principal_id=ME, at=NOW)


# -------------------------------------------------------------------- own usage (M33.3.1.5)
def test_a_persons_ceilings_are_paired_with_what_they_actually_spent() -> None:
    """**The join neither module could make.** `brain.ops.budgets` builds the ceilings and
    counts nothing; `brain.ops.spend` counts and takes the ceilings as an argument. This is
    the question between them.

    The spend is asserted per period rather than in total, because the interesting failure is
    one window's figure being used for both rows: the daily row here must not carry the
    month's spend, and a single sum would look right on whichever row happened to be checked.

    Delete this and a person's own usage screen is the one surface in the console that cannot
    be built without writing the join twice."""
    rows = [
        a_budget(subject=ME, period=BudgetPeriod.DAY, ceiling_minor=1_000),
        a_budget(subject=ME, period=BudgetPeriod.MONTH, ceiling_minor=10_000),
    ]
    actuals = [
        an_actual(principal_id=ME, cost_minor=200, hours_ago=2),
        an_actual(principal_id=ME, cost_minor=500, hours_ago=400),
        an_actual(principal_id=THEM, cost_minor=900, hours_ago=2),
    ]

    found = own_allowances(
        rows,
        actuals,
        principal_id=ME,
        windows={BudgetPeriod.DAY: DAY, BudgetPeriod.MONTH: MONTH},
    )

    assert tuple(one.row.period for one in found) == (BudgetPeriod.DAY, BudgetPeriod.MONTH)
    assert tuple(one.spent_minor for one in found) == (200, 700)
    assert tuple(one.headroom_minor for one in found) == (800, 9_300)


def test_a_ceiling_with_no_window_is_left_out_rather_than_reported_at_zero() -> None:
    """Pairing a ceiling with no measured spend produces an allowance whose headroom is the
    whole ceiling, which is indistinguishable from somebody who has spent nothing, on the one
    screen a person reads before starting something expensive.

    `BudgetPeriod.RUN` is the ordinary case: a per-run ceiling is a gate on one call rather
    than a figure anybody spends against over a period, and it is asserted here so the
    dropping is exercised by a row that really exists rather than only by a contrived one.

    Delete this and the reassuring direction becomes the default, which is the direction
    nobody reports as a bug."""
    rows = [
        a_budget(subject=ME, period=BudgetPeriod.RUN, ceiling_minor=50),
        a_budget(subject=ME, period=BudgetPeriod.DAY, ceiling_minor=1_000),
    ]

    found = own_allowances(
        rows,
        [an_actual(principal_id=ME, cost_minor=200, hours_ago=2)],
        principal_id=ME,
        windows={BudgetPeriod.DAY: DAY},
    )

    assert tuple(one.row.period for one in found) == (BudgetPeriod.DAY,)


def test_a_department_ceiling_is_not_one_persons_allowance() -> None:
    """A row at the department level with this person's own id in its subject would be the
    department's ceiling wearing a personal label, and a person reading their own headroom
    off it would be reading how much their whole team has left.

    Both refusals are asserted: the wrong level, and the right level belonging to somebody
    else.

    Delete this and the level comparison can be widened to include DEPARTMENT, which reads as
    showing somebody more context and publishes their colleagues' spend."""
    rows = [
        a_budget(subject=ME, period=BudgetPeriod.DAY, level=BudgetLevel.DEPARTMENT),
        a_budget(subject=THEM, period=BudgetPeriod.DAY),
        a_budget(subject=ME, period=BudgetPeriod.DAY),
    ]

    found = own_allowances(rows, [], principal_id=ME, windows={BudgetPeriod.DAY: DAY})

    assert tuple((one.row.level, one.row.subject) for one in found) == ((OWN_LEVEL, ME),)


def test_the_level_a_personal_allowance_is_read_at_is_the_budget_modules_own() -> None:
    """The constant checked against something outside itself rather than against a literal
    written here. `brain.ops.budgets.user_allowances` is the function that builds a person's
    ceilings, and every row it returns is at the level this module selects on, so the two
    cannot drift apart without this failing.

    Delete this and `OWN_LEVEL` can be repointed at DEPARTMENT with every other test in this
    file still green, because they all build their rows through the same constant."""
    from brain.ops.budgets import user_allowances

    department = a_budget(
        subject=MAINTENANCE,
        period=BudgetPeriod.MONTH,
        ceiling_minor=100_000,
        level=BudgetLevel.DEPARTMENT,
    )
    built = user_allowances(
        department,
        principal_id=ME,
        headcount=4,
        author="u_owner",
        effective_from=NOW - timedelta(days=90),
    )

    assert {one.level for one in built} == {OWN_LEVEL}
    assert {one.subject for one in built} == {ME}


# -------------------------------------------------------------------------- the diagnostic
def test_no_personal_function_can_be_asked_to_answer_for_everybody() -> None:
    """Every function narrows by the principal, keyword-only and with no default, and the
    deployment check is asserted rather than only the constructed one.

    A positional principal with a default is how a call site ends up omitting it: a default of
    the empty string builds a personal scope with no owner, which `scope_for` refuses loudly,
    and a default of `None` needs a branch somebody writes as "then show everything".

    Delete this and the first administrative screen that needs most of this code reuses it
    with one extra argument, and from then on the difference between a personal surface and a
    directory is a parameter nobody reviews."""
    assert own_gaps() == ()
    assert len(PERSONAL_SURFACE) == 7

    for one in PERSONAL_SURFACE:
        found = inspect.signature(one).parameters["principal_id"]
        assert found.kind is inspect.Parameter.KEYWORD_ONLY, one.__name__
        assert found.default is inspect.Parameter.empty, one.__name__


def test_a_function_that_could_answer_for_everybody_is_reported() -> None:
    """The diagnostic exercised with broken functions rather than only against the healthy
    tree, which is `govern_gaps`' argument about its own parameters: a check that can only
    run against a correct module has nothing to report, so switching it off changes nothing
    observable.

    All four shapes are covered: no principal at all, a positional one, a defaulted one, and
    a parameter beside it meaning everybody.

    Delete this and the signature check survives every mutation of itself."""

    def missing(rows: Any) -> None: ...

    def positional(rows: Any, principal_id: str) -> None: ...

    def defaulted(rows: Any, *, principal_id: str = "") -> None: ...

    def widened(rows: Any, *, principal_id: str, everyone: bool = False) -> None: ...

    assert any("does not narrow by" in one for one in own_gaps([missing]))
    assert any("positionally" in one for one in own_gaps([positional]))
    assert any("defaults" in one for one in own_gaps([defaulted]))
    assert any("becomes a" in one for one in own_gaps([widened]))
    assert "everyone" in NAMES_THAT_WOULD_MEAN_EVERYBODY
