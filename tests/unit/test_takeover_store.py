"""A takeover is fed to the autonomy breaker, and the third inside a week lowers the rung (M8.3.5).

The first half runs anywhere: the feed from instants to `AutonomyBreaker`, the leash lowering the
configured rung by it, and the rules that keep a takeover away from the model circuit breaker. The
second builds `gate.suspension` through the migrations that ship it, adds `0172`, takes approvals
over through the Approvals route's own `decide_once` as the application role, and reads the
standing back through `brain.gate.takeover_store.StoredTakeovers`.

The clock is 2999, for the reason CLAUDE.md records about fixtures that go off: what is tested is
the window, not the present.

Task ids: M8.3.5
"""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import psycopg
import pytest
from sqlalchemy import text

from brain.approval_routes import (
    DecidableVerdict,
    DecisionAsked,
    RejectionReason,
    TakeoverReason,
    decide_once,
)
from brain.audit.ledger import AuditChain
from brain.audit.record import ApprovalVerdict, AuditRecorder
from brain.core.scope import Scope
from brain.gate import takeover_store
from brain.gate.abstain import (
    TAKEOVER_DEMOTION_THRESHOLD,
    TAKEOVER_IS_NOT_A_PROVIDER_FAULT,
    TAKEOVER_WINDOW,
    AutonomyBreaker,
)
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.gate.leash import (
    A_TAKEN_OVER_AGENT_STANDS_ONE_RUNG_LOWER,
    Leash,
    LeashEntry,
    Route,
    SuspendedAction,
    decide,
    effective_tier,
    render_artefact,
    route_for,
)
from brain.gate.suspension_store import StoredSuspensions
from brain.gate.takeover_store import (
    FUNCTION,
    MOST_TAKEOVERS_READ,
    StoredTakeovers,
    TakeoverStandings,
    standing_from,
)
from brain.models.routing import FALLBACK_TRIGGER_VALUES
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_suspension_store import (
    APPROVER,
    ASKER_REACH,
    CEILING,
    CLEAN,
    POLICY,
    an_action,
    app_engine,
    put,
    raised,
    suspensions,
    upgraded,
    with_store,
)

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
AGENT = "agent_test"
TARGET = "ticket.update_status"
ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "0172_takeover_instants.py"
SRC = ROOT / "src" / "brain"


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m0172", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def held_at(rung: AutonomyTier) -> Leash:
    """The test agent held to `rung` on the target, everywhere."""
    return Leash(
        entries=(LeashEntry(agent_id=AGENT, target=TARGET, scope=Scope.unrestricted(), rung=rung),)
    )


def taken_over(*days_ago: int) -> AutonomyBreaker:
    return standing_from(AGENT, TARGET, (NOW - timedelta(days=one) for one in days_ago))


# ------------------------------------------------------------------------ the feed
def test_the_third_takeover_in_the_window_lowers_the_rung_and_the_second_does_not() -> None:
    """**The positive half of M8.3.5, through the leash.** An agent held to Assisted on a target
    stays there after two takeovers inside the week and stands at Shadow after the third, so its
    next action there is simulated rather than suspended; the configured rung is untouched without
    a standing. Delete this and the breaker can be fed and read while nothing the leash decides
    changes, which is the state the breaker was in until 2026-09-30."""
    leash = held_at(AutonomyTier.ASSISTED)
    action = an_action()

    def tier(standing: AutonomyBreaker | None) -> AutonomyTier:
        return effective_tier(leash, action, CLEAN, standing=standing, now=NOW)

    assert tier(None) is AutonomyTier.ASSISTED
    assert tier(taken_over(0, 1)) is AutonomyTier.ASSISTED
    assert tier(taken_over(0, 1, 2)) is AutonomyTier.SHADOW

    def routed(standing: AutonomyBreaker) -> Route:
        return route_for(
            decide(
                action,
                caller=ASKER_REACH,
                agent_ceiling=CEILING,
                policy=POLICY,
                leash=leash,
                assessment=CLEAN,
                now=NOW,
                standing=standing,
            )
        )

    assert routed(taken_over(0, 1)) is Route.SUSPEND
    assert routed(taken_over(0, 1, 2)) is Route.SIMULATE


def test_takeovers_that_have_left_the_window_stop_lowering_the_rung() -> None:
    """The window is measured from the decision's own instant: three takeovers a week and a minute
    before it no longer count. Delete this and an agent fixed last month stays demoted for ever."""
    standing = taken_over(0, 1, 2)

    later = NOW + TAKEOVER_WINDOW
    tier = effective_tier(
        held_at(AutonomyTier.ASSISTED), an_action(), CLEAN, standing=standing, now=later
    )

    assert tier is AutonomyTier.ASSISTED


def test_a_standing_for_another_agent_or_target_or_without_an_instant_is_refused() -> None:
    """Each refused in the rule's own words, and the matching standing accepted. Delete this and a
    standing read for one agent can demote another, or be measured from no instant at all."""
    leash, action = held_at(AutonomyTier.ASSISTED), an_action()
    others = (
        standing_from("agent_other", TARGET, ()),
        standing_from(AGENT, "invoice", ()),
    )

    for other in others:
        with pytest.raises(ValueError, match=r"demote|given for an action"):
            effective_tier(leash, action, CLEAN, standing=other, now=NOW)
    with pytest.raises(ValueError) as refused:
        effective_tier(leash, action, CLEAN, standing=taken_over(0))
    assert A_TAKEN_OVER_AGENT_STANDS_ONE_RUNG_LOWER in str(refused.value)
    assert effective_tier(leash, action, CLEAN, standing=taken_over(0), now=NOW) is (
        AutonomyTier.ASSISTED
    )


def test_the_risk_ceiling_and_the_sensitive_cap_still_lower_a_rung_the_breaker_left_alone() -> None:
    """The standing is applied before the other two ceilings and never instead of them. Delete
    this and an action whose standing is clean could skip the risk ceiling it would otherwise
    meet."""
    risky = RiskAssessment(score=100, matched=("override",))

    tier = effective_tier(
        held_at(AutonomyTier.AUTONOMOUS), an_action(), risky, standing=taken_over(0), now=NOW
    )

    assert tier < AutonomyTier.AUTONOMOUS


def test_each_instant_is_fed_as_a_signal_and_a_naive_one_is_refused() -> None:
    """`standing_from` feeds through `AutonomyBreaker.record`, so the signal's own refusals apply.
    Delete this and a naive timestamp from a driver lands in the wrong window, which the signal
    exists to refuse."""
    standing = standing_from(AGENT, TARGET, [NOW, NOW - timedelta(days=2), NOW - timedelta(days=1)])

    assert standing.takeovers == tuple(sorted(standing.takeovers))
    assert standing.recent(NOW) == 3
    with pytest.raises(ValueError, match="timezone-aware"):
        standing_from(AGENT, TARGET, [datetime(2999, 6, 1, 9, 0)])


# ------------------------------------------------ never the provider breaker
def test_a_takeover_feeds_the_autonomy_breaker_and_never_the_model_circuit_breaker() -> None:
    """**`TAKEOVER_IS_NOT_A_PROVIDER_FAULT`, held on the feed.** Nothing that reads or records a
    takeover imports the model routing that owns the provider breaker, and a takeover is no
    fallback trigger there. Delete this and the feed can be wired to the provider breaker, which
    would take a healthy model out of rotation for everybody because one agent's leash was set
    too long on one target."""
    feeding = (
        SRC / "gate" / "takeover_store.py",
        SRC / "gate" / "leash.py",
        SRC / "approval_routes.py",
        SRC / "console" / "approvals.py",
    )
    for path in feeding:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert not any(one.startswith("brain.models") for one in imported), path.name
    assert not {one for one in FALLBACK_TRIGGER_VALUES if "take" in one}
    assert "CircuitBreaker" in TAKEOVER_IS_NOT_A_PROVIDER_FAULT


# --------------------------------------------------------------- the figures
def test_the_read_is_bounded_above_the_threshold_that_lowers_a_rung() -> None:
    """The bound is a resource limit and must never be the reason a rung stays up. Delete this and
    a bound of two keeps every agent at its configured rung however often it is taken over."""
    assert MOST_TAKEOVERS_READ >= TAKEOVER_DEMOTION_THRESHOLD
    with pytest.raises(ValueError, match="keep a rung up"):
        StoredTakeovers(lambda: None, most=TAKEOVER_DEMOTION_THRESHOLD - 1)  # type: ignore[arg-type]


def test_the_read_names_the_function_the_migration_creates_with_the_ledger_s_verdict() -> None:
    """The store's statement, the migration's function and the verdict the function filters on are
    one name each. Delete this and a renamed function or verdict leaves the store reading nothing,
    which is every agent at its configured rung and no error anywhere."""
    built = migration()

    assert f"CREATE FUNCTION {FUNCTION}(" in built.CREATE_FUNCTION
    assert f"FROM {FUNCTION}(" in str(takeover_store._READ)
    assert f"FROM {FUNCTION}(" in INSTANTS
    assert built.TAKEN_OVER == ApprovalVerdict.TAKEN_OVER.value == DecidableVerdict.TAKEN_OVER.value
    assert built.FUNCTION.startswith(f"{FUNCTION}(")


def test_the_function_is_a_pinned_definer_revoked_from_public_and_granted_to_the_application() -> (
    None
):
    """What the coordinator's brief and `0040` require of a read past a policy, read off the
    migration's own statements. Delete this and the search path can be left to the caller, which
    lets a caller's schema shadow a table the definer reads, or PUBLIC keeps EXECUTE."""
    built = migration()
    body = " ".join(built.CREATE_FUNCTION.split())

    assert "SECURITY DEFINER" in body
    assert "SET search_path = pg_catalog, gate" in body
    assert "STABLE" in body
    assert (
        f"REVOKE EXECUTE ON FUNCTION {built.FUNCTION} FROM PUBLIC",
        f"GRANT EXECUTE ON FUNCTION {built.FUNCTION} TO brain_app",
    ) == built.GRANTS
    assert "RETURNS TABLE (taken_over_at timestamptz)" in body


def test_the_store_is_the_standings_protocol() -> None:
    """Delete this and a caller typed against the protocol can be handed something that is not."""
    assert isinstance(StoredTakeovers(lambda: None), TakeoverStandings)  # type: ignore[arg-type]


# ---------------------------------------------------------- against the database
TAKE_OVER = DecisionAsked(
    verdict=DecidableVerdict.TAKEN_OVER, reason_code=TakeoverReason.NEEDS_CHANGES
)
REJECT = DecisionAsked(verdict=DecidableVerdict.REJECTED, reason_code=RejectionReason.WRONG_TARGET)
APPROVE = DecisionAsked(verdict=DecidableVerdict.APPROVED)

#: The three takeovers inside the week before `NOW`, oldest first.
INSIDE = (NOW - timedelta(days=3), NOW - timedelta(days=2), NOW - timedelta(days=1))


def raised_by(
    ident: str, at: datetime, *, agent: str = AGENT, target: str = TARGET
) -> SuspendedAction:
    """A suspension of the status tool raised an hour before `at`, so it can be decided at `at`."""
    action = an_action().model_copy(update={"agent_id": agent, "target": target})
    return raised(ident).model_copy(
        update={
            "action": action,
            "artefact": render_artefact(action),
            "action_digest": action.digest(),
            "raised_at": at - timedelta(hours=1),
            "expires_at": at + timedelta(hours=3),
        }
    )


async def decided(store: StoredSuspensions, ident: str, asked: DecisionAsked, at: datetime) -> None:
    """One decision through the Approvals route's `decide_once`, by the approver at `at`."""
    recorder = AuditRecorder(
        AuditChain(),
        actor_id=APPROVER.principal_id,
        ent_hash=APPROVER.ent_hash(),
        trace_id="trace_test",
        clock=lambda: at,
    )
    async with store.holding(APPROVER, at) as rows:
        done = await decide_once(rows, ident, APPROVER, recorder, asked=asked, now=at)
    assert done is not None, ident


#: Every row the function must leave out, and why, beside the three it must return.
AROUND: tuple[tuple[str, DecisionAsked, datetime, dict[str, str]], ...] = (
    ("rejected", REJECT, NOW - timedelta(days=1), {}),
    ("approved", APPROVE, NOW - timedelta(days=1), {}),
    ("other_target", TAKE_OVER, NOW - timedelta(days=1), {"target": "ticket.close"}),
    ("other_agent", TAKE_OVER, NOW - timedelta(days=1), {"agent": "agent_other"}),
    ("last_month", TAKE_OVER, NOW - timedelta(days=30), {}),
)


@contextmanager
def taken_over_rows(database: str) -> Iterator[str]:
    """`gate.suspension` with `0083`'s decision and `0172`'s function, three takeovers of the
    agent's target inside the week before `NOW`, one pending row, and every row the function must
    leave out."""
    with suspensions(database) as url:
        upgraded(database, MIGRATION)

        async def work(store: StoredSuspensions) -> None:
            for n, at in enumerate(INSIDE):
                await put(store, raised_by(f"t_{n}", at))
                await decided(store, f"t_{n}", TAKE_OVER, at)
            for ident, asked, at, other in AROUND:
                await put(store, raised_by(ident, at, **other))
                await decided(store, ident, asked, at)
            await put(store, raised_by("pending", NOW))

        with_store(url, work)
        yield url


#: Every column the function returns, for the pair and the window given. `FUNCTION`, written out.
INSTANTS = "SELECT * FROM gate.takeover_instants(%s, %s, %s, %s, %s)"


def test_the_function_returns_instants_alone_over_the_pair_asked_for() -> None:
    """**What crosses the policy is an instant and nothing else.** One column, the three takeovers
    of this agent on this target inside the window, newest first; not a rejection, an approval, a
    pending row, another target, another agent or a takeover older than the window; and the end of
    the window is the caller's, so an instant before the newest leaves it out. Delete this and the
    function can return the action, the artefact or the approver, which the policy exists to keep
    from anybody the row is not theirs, or count what is not a takeover."""
    with taken_over_rows("brain_takeover_instants") as url, psycopg.connect(url) as conn:
        cursor = conn.execute(
            INSTANTS,
            (AGENT, TARGET, NOW - TAKEOVER_WINDOW, NOW, MOST_TAKEOVERS_READ),
        )
        columns = [one.name for one in cursor.description or ()]
        rows = [one[0] for one in cursor.fetchall()]
        earlier = [
            one[0]
            for one in conn.execute(
                INSTANTS,
                (AGENT, TARGET, NOW - TAKEOVER_WINDOW, INSIDE[-1] - timedelta(seconds=1), 50),
            ).fetchall()
        ]

    assert columns == ["taken_over_at"]
    assert rows == sorted(INSIDE, reverse=True)
    assert earlier == sorted(INSIDE[:-1], reverse=True)


def test_a_reader_with_no_row_of_their_own_still_gets_the_count_that_lowers_the_rung() -> None:
    """**The reason the function exists.** Read as the application role for somebody who raised
    and decided none of the rows, the table itself shows nothing and the store still reads all
    three takeovers, so the rung falls to Shadow at `NOW`; at an instant when only two had happened
    it does not. Delete this and the breaker can be read under the reader's policy, where the same
    agent stands differently depending on who is using it."""
    with taken_over_rows("brain_takeover_reader") as url:

        async def work(engine_url: str) -> tuple[int, AutonomyBreaker, AutonomyBreaker]:
            engine = app_engine(engine_url)
            try:
                sessions = make_session_factory(engine)
                async with sessions() as session:
                    await session.execute(
                        text("SELECT set_config('app.principal_id', 'u_stranger', true)")
                    )
                    seen = (
                        await session.execute(text("SELECT count(*) FROM gate.suspension"))
                    ).scalar_one()
                store = StoredTakeovers(sessions)
                now = await store.standing(AGENT, TARGET, NOW)
                before = await store.standing(AGENT, TARGET, INSIDE[-1] - timedelta(seconds=1))
                return int(seen), now, before
            finally:
                await engine.dispose()

        seen, now, before = run(lambda: work(url))

    leash, action = held_at(AutonomyTier.ASSISTED), an_action()
    assert seen == 0
    assert now.recent(NOW) == 3
    assert effective_tier(leash, action, CLEAN, standing=now, now=NOW) is AutonomyTier.SHADOW
    assert before.recent(INSIDE[-1]) == 2
    held = effective_tier(
        leash, action, CLEAN, standing=before, now=INSIDE[-1] - timedelta(seconds=1)
    )
    assert held is AutonomyTier.ASSISTED


def test_the_function_runs_as_its_owner_on_a_pinned_path_for_the_application_alone() -> None:
    """Read off the catalogue rather than the migration's text, so what is checked is what the
    database made of it. Delete this and a REVOKE the compatibility gate once refused can go
    missing again, leaving every role with USAGE on the schema able to call a read past a policy."""
    with taken_over_rows("brain_takeover_acl") as url:
        [(definer, config, acl)] = sql(
            url,
            "SELECT prosecdef, proconfig, proacl::text[] FROM pg_proc"
            " WHERE proname = 'takeover_instants'",
        )
        public = sql(
            url,
            "SELECT has_function_privilege('brain_fastlane', %s, 'EXECUTE'),"
            " has_function_privilege('brain_app', %s, 'EXECUTE')",
            migration().FUNCTION,
            migration().FUNCTION,
        )

    assert definer is True
    assert config == ["search_path=pg_catalog, gate"]
    assert not any(one.startswith("=") for one in acl), acl
    assert any(one.startswith("brain_app=X/") for one in acl), acl
    assert public == [(False, True)]


#: How many of the function and the index there are.
COUNTS = (
    "SELECT count(*) FROM pg_proc WHERE proname = 'takeover_instants' UNION ALL"
    " SELECT count(*) FROM pg_indexes WHERE indexname = 'ix_suspension_taken_over'"
)


def test_the_migration_reverses_and_applies_again() -> None:
    """Down removes the function and the index, and up puts both back. Delete this and a rollback
    can leave a definer function behind that no migration knows it owns."""
    with taken_over_rows("brain_takeover_round_trip") as url:
        migrate("brain_takeover_round_trip", "downgrade", str(migration().down_revision))
        gone = sql(
            url,
            COUNTS,
        )
        migrate("brain_takeover_round_trip", "upgrade", "0172")
        back = sql(
            url,
            COUNTS,
        )

    assert gone == [(0,), (0,)]
    assert back == [(1,), (1,)]
