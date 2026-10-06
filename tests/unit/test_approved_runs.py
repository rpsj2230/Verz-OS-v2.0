"""An approved action runs once, with nobody present, and an unapproved, lapsed or run one never.

The first half runs anywhere: what a run reports, the three ways `_run_one` declines before it
reaches an executor, `ToolExecutor` through the real `brain.gate.leash.resume` (once, again, and a
reach that moved), `ConnectorWrites` mapping every `send_approved` outcome, and one failing action
not stopping the rest. The second builds PostgreSQL to head and asks `gate.approved_to_run` (`0201`)
which rows it returns, as whom it may be called, and whether it reverses.

The clock is 2999, for the reason CLAUDE.md records about fixtures that go off: what is tested is
the window, not the present.

Task ids: M13.7.6
"""

from __future__ import annotations

import importlib.util
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import psycopg
import pytest
from psycopg.types.json import Jsonb

from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.gate.leash import Action, ApprovalState, Leash, LeashEntry, SuspendedAction
from brain.gate.suspension_store import row_values
from brain.ops import approved_runs
from brain.ops.approved_runs import (
    ApprovedRun,
    ConnectorWrites,
    Listed,
    Ran,
    RunContext,
    Standing,
    ToolExecutor,
    _run_one,
    run_approved,
)
from brain.ops.connector_write_run import WriteOutcome
from brain.ops.controls import CONTROLS
from tests.fixtures.operation_ledger import MemoryLedger
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_suspension_store import (
    ASKER,
    ASKER_REACH,
    CEILING,
    CLEAN,
    POLICY,
    STATUS_TOOL,
    raised,
    reach,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "0201_approved_runs.py"
NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
LEASH = Leash(
    entries=(
        LeashEntry(
            agent_id="agent_test",
            target="ticket.update_status",
            scope=Scope.unrestricted(),
            rung=AutonomyTier.ASSISTED,
        ),
    )
)


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m0201", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def approved(ident: str = "s_one") -> SuspendedAction:
    return raised(ident).model_copy(
        update={"state": ApprovalState.APPROVED, "decided_by": "u_narrow", "decided_at": NOW}
    )


def context(caller: EntitlementSet = ASKER_REACH, ledger: Any = None) -> RunContext:
    return RunContext(
        reach=caller,
        agent_ceiling=CEILING,
        policy=POLICY,
        leash=LEASH,
        assessment=CLEAN,
        trace_id="trace_test",
        now=NOW,
        ledger=MemoryLedger() if ledger is None else ledger,
    )


# ------------------------------------------------------------------------ what a run says
def test_a_look_with_nothing_waiting_says_so_and_a_look_with_some_counts_them_by_outcome() -> None:
    """Delete this and the worker's run record can say nothing happened when two ran, or name
    nothing a reader can act on."""
    assert ApprovedRun(listed=0).summary() == "no approved action was waiting to run"
    said = ApprovedRun(listed=3, outcomes={Ran.DONE: 2, Ran.REFUSED: 1}).summary()
    assert said == "3 approved action(s) looked at: 2 done, 1 refused"


def test_with_no_tool_to_run_the_door_is_not_asked() -> None:
    """**An action nothing can run is never listed**, and with no executor at all there is no
    query to make. Delete this and an install with no executor asks the database for every approved
    action of no tool, which `ANY` over an empty array answers with nothing only by luck."""

    class Refuses:
        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("the door was asked with no tool")

    found = run(lambda: approved_runs.approved_to_run(Refuses(), now=NOW, tools=()))  # type: ignore[arg-type]
    assert found == []


# ------------------------------------------------------------------------ one action
class Store:
    """`StoredSuspensions.reading_as`, holding one suspension readable by one principal."""

    def __init__(self, held: SuspendedAction | None) -> None:
        self.held = held
        self.read_as: list[str] = []

    def reading_as(self, who: EntitlementSet, now: datetime) -> Any:
        del now
        self.read_as.append(who.principal_id)
        held = self.held

        class Reader:
            async def suspension(self, ident: str) -> SuspendedAction | None:
                return held if held is not None and held.id == ident else None

        return Reader()


class Reaches:
    def __init__(self, caller: EntitlementSet = ASKER_REACH) -> None:
        self.caller = caller
        self.asked: list[tuple[str, datetime]] = []

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        self.asked.append((principal_id, now))
        return self.caller


class Standings:
    def __init__(self, standing: Standing | None) -> None:
        self.found = standing

    async def standing(self, agent_id: str, now: datetime) -> Standing | None:
        del agent_id, now
        return self.found


class Recording:
    """An executor that records the context it was handed and answers DONE."""

    def __init__(self, tools: frozenset[str] = frozenset({STATUS_TOOL.name})) -> None:
        self.named = tools
        self.handed: list[RunContext] = []

    def tools(self) -> frozenset[str]:
        return self.named

    async def run(self, suspension: SuspendedAction, context: RunContext) -> Ran:
        del suspension
        self.handed.append(context)
        return Ran.DONE


STANDING = Standing(ceiling=CEILING, leash=LEASH)
LISTED = Listed(suspension_id="s_one", principal_id=ASKER)


def one(
    store: Store, executor: Recording | None, standing: Standing | None, reaches: Reaches
) -> Ran:
    by_tool = {} if executor is None else dict.fromkeys(executor.tools(), executor)
    return run(
        lambda: _run_one(
            store, LISTED, by_tool, Standings(standing), reaches, MemoryLedger(), NOW, "trace_x"
        )
    )


def test_an_approved_action_is_read_and_run_at_its_requesters_reach_as_it_is_now() -> None:
    """**The positive case.** The requester's reach is resolved at the run's instant, the
    suspension is read as them, and the executor is handed that reach, the agent's stored ceiling
    and leash, and the instant. Delete this and every refusal below is satisfied by a run that
    never runs anything."""
    store, reaches, executor = Store(approved()), Reaches(), Recording()
    assert one(store, executor, STANDING, reaches) is Ran.DONE
    assert reaches.asked == [(ASKER, NOW)]
    assert store.read_as == [ASKER]
    [handed] = executor.handed
    assert (handed.reach, handed.agent_ceiling, handed.leash, handed.now) == (
        ASKER_REACH,
        CEILING,
        LEASH,
        NOW,
    )


@pytest.mark.parametrize("missing", ["suspension", "executor", "standing"])
def test_an_action_whose_row_executor_or_agent_is_gone_is_not_run(missing: str) -> None:
    """Three declines before any executor: the row is not readable at the requester's reach now,
    no executor runs the tool it names, or its agent has no standing (gone or disabled). Each is
    GONE and nothing runs. Delete this and an action can run for an agent that was switched off
    after the approval, with a ceiling of nothing in particular."""
    executor = Recording(
        frozenset({"something.else"}) if missing == "executor" else frozenset({STATUS_TOOL.name})
    )
    store = Store(None if missing == "suspension" else approved())
    standing = None if missing == "standing" else STANDING
    assert one(store, executor, standing, Reaches()) is Ran.GONE
    assert executor.handed == []


# ------------------------------------------------------------------------ the tool executor
def test_the_tool_executor_runs_an_approved_action_once_and_says_so_the_second_time() -> None:
    """**Once, through `resume`.** The handler is called with the action and the run's reach, the
    first run is DONE and a second against the same ledger is ALREADY_RAN with the handler not
    called again. Delete this and the executor can call the handler directly, where every check
    `resume` makes and the ledger's once are skipped."""
    calls: list[tuple[str, str]] = []

    def handler(action: Action, caller: EntitlementSet) -> TypedResult[Any]:
        calls.append((action.target, caller.principal_id))
        return TypedResult(records=(), source="test")

    executor, ledger = ToolExecutor({STATUS_TOOL.name: handler}), MemoryLedger()
    assert executor.tools() == frozenset({STATUS_TOOL.name})
    held = approved()
    first = run(lambda: executor.run(held, context(ledger=ledger)))
    second = run(lambda: executor.run(held, context(ledger=ledger)))
    assert (first, second) == (Ran.DONE, Ran.ALREADY_RAN)
    assert calls == [("ticket.update_status", ASKER)]


@pytest.mark.parametrize("moved", ["pending", "lapsed", "reach"])
def test_the_tool_executor_refuses_what_no_longer_runs_as_approved(moved: str) -> None:
    """A suspension still pending, one past its window, and one whose requester's reach has
    changed since it was raised are each REFUSED by `resume`, and the handler is never called.
    Delete this and the executor can report DONE for a run `resume` declined."""
    calls: list[str] = []

    def handler(action: Action, caller: EntitlementSet) -> TypedResult[Any]:
        calls.append(action.target)
        return TypedResult(records=(), source="test")

    held = {
        "pending": raised("s_one"),
        "lapsed": approved().model_copy(update={"expires_at": NOW - timedelta(seconds=1)}),
        "reach": approved(),
    }[moved]
    caller = reach(ASKER, "write:ticket.status") if moved == "reach" else ASKER_REACH
    assert run(lambda: ToolExecutor({STATUS_TOOL.name: handler}).run(held, context(caller))) is (
        Ran.REFUSED
    )
    assert calls == []


# ------------------------------------------------------------------------ connector writes
class Declared:
    def __init__(self, *tools: str) -> None:
        self.writes = (SimpleNamespace(tools=tools),)


DECLARED = {"cloudflare": Declared("cloudflare.change_record"), "freshdesk": Declared("x.reply")}


def writes(connected: tuple[Any, ...]) -> ConnectorWrites:
    async def connections() -> tuple[Any, ...]:
        return connected

    return ConnectorWrites(
        connections=connections,
        keys=None,
        caller=None,
        resolver=None,
        clock=lambda: NOW,
        declarations=DECLARED,
    )


def test_connector_writes_name_every_declared_write_tool_and_no_other() -> None:
    """Delete this and the worker can ask for approved actions of a tool no grant sends, or miss
    one a grant does."""
    assert writes(()).tools() == frozenset({"cloudflare.change_record", "x.reply"})


def test_a_write_whose_connector_is_not_connected_is_gone_and_nothing_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and an approval for a connector somebody has since disconnected is sent through
    another connector's connection, or raises and is counted as a failed send."""
    import brain.ops.connector_write_run as write_run

    def refuses(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("sent with no connection")

    monkeypatch.setattr(write_run, "send_approved", refuses)
    held = approved().model_copy(
        update={"action": approved().action.model_copy(update={"tool": STATUS_TOOL})}
    )
    other = SimpleNamespace(connector="freshdesk")
    assert run(lambda: writes((other,)).run(held, context())) is Ran.GONE


@pytest.mark.parametrize(
    ("outcome", "ran"),
    [
        (WriteOutcome.DONE, Ran.DONE),
        (WriteOutcome.FAILED, Ran.FAILED),
        (WriteOutcome.NOT_ALLOWED, Ran.NOT_ALLOWED),
        (WriteOutcome.NOT_SENT, Ran.REFUSED),
        (WriteOutcome.ALREADY_SENT, Ran.ALREADY_RAN),
    ],
)
def test_every_outcome_of_a_send_is_reported_as_its_own_kind(
    monkeypatch: pytest.MonkeyPatch, outcome: WriteOutcome, ran: Ran
) -> None:
    """The write is sent through `send_approved` with the connection of the connector whose grant
    names the tool and the run's reach, and each of its outcomes maps to one of the run's. Delete
    this and a refused send can be counted as done, or the reach handed over can be anybody's."""
    import brain.ops.connector_write_run as write_run

    sent: list[tuple[Any, EntitlementSet]] = []

    def send(suspension: SuspendedAction, **kwargs: Any) -> Any:
        sent.append((kwargs["connection"], kwargs["reach"]))
        return SimpleNamespace(outcome=outcome)

    monkeypatch.setattr(write_run, "send_approved", send)
    tool = STATUS_TOOL.model_copy(update={"name": "cloudflare.change_record"})
    held = approved().model_copy(
        update={"action": approved().action.model_copy(update={"tool": tool})}
    )
    mine, other = SimpleNamespace(connector="cloudflare"), SimpleNamespace(connector="freshdesk")
    assert run(lambda: writes((other, mine)).run(held, context())) is ran
    assert sent == [(mine, ASKER_REACH)]


# ------------------------------------------------------------------------ the whole look
def test_one_action_that_raises_is_counted_failed_and_the_rest_still_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and one action whose connection raises stops every approval behind it from
    running, every five minutes, until its window lapses."""

    async def door(session: Any, *, now: datetime, tools: Any, limit: int = 50) -> list[Listed]:
        del session, now, limit
        assert list(tools) == [STATUS_TOOL.name]
        return [Listed("s_bad", ASKER), Listed("s_good", ASKER)]

    async def one_of(store: Any, listed: Listed, *args: Any) -> Ran:
        if listed.suspension_id == "s_bad":
            raise RuntimeError("the connection went away")
        return Ran.DONE

    class Session:
        @asynccontextmanager
        async def begin(self) -> AsyncIterator[None]:
            yield

    @asynccontextmanager
    async def sessions() -> AsyncIterator[Session]:
        yield Session()

    monkeypatch.setattr(approved_runs, "approved_to_run", door)
    monkeypatch.setattr(approved_runs, "_run_one", one_of)
    found = run(
        lambda: run_approved(
            sessions,  # type: ignore[arg-type]
            now=NOW,
            executors=(Recording(),),
            standings=Standings(STANDING),
            reaches=Reaches(),
            ledger=MemoryLedger(),
        )
    )
    assert found == ApprovedRun(listed=2, outcomes={Ran.FAILED: 1, Ran.DONE: 1})


# ------------------------------------------------------------------------ registrations
def test_the_worker_runs_the_look_every_five_minutes_as_a_control() -> None:
    """Delete this and the control can be dropped from the registry, which is the state M13.7.6 was
    in: an approval recorded and nothing that ever sends it."""
    [control] = [one for one in CONTROLS if one.name == "approved_actions"]
    assert control.symbols == (
        "brain.ops.approved_runs:run_approved_now",
        "brain.ops.approved_runs:run_approved",
    )
    assert timedelta(minutes=5) == approved_runs.RUNS_EVERY


def test_in_report_only_mode_the_control_runs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a worker told to report only sends approved writes to the systems they
    change, which is the one thing report-only mode promises it will not do."""
    from brain.ops import schedule_runner

    def refuses(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("ran in report-only mode")

    monkeypatch.setattr(approved_runs, "run_approved_now", refuses)
    said = schedule_runner.approved_actions(NOW, True, "postgresql://unused/brain")
    assert said.startswith("report only: no approved action was run.")
    assert schedule_runner.AN_APPROVED_ACTION_IN_REPORT_ONLY_MODE_RUNS_NOTHING in said


def test_the_migration_reads_the_approved_state_as_the_leash_names_it() -> None:
    """Delete this and the state `resume` reads can be renamed with the function still listing the
    old word, so nothing is ever listed again."""
    assert ApprovalState.APPROVED.value == migration().APPROVED


# ------------------------------------------------------------------------ the function
@contextmanager
def at_head_with_rows(database: str) -> Iterator[str]:
    """PostgreSQL at head, with one suspension of every kind the function must tell apart."""
    from tests.unit.test_acceptance import at_head

    with at_head(database) as url:
        held = raised("x_template")
        base = row_values(held)
        rows = {
            "a_first": ("approved", NOW + timedelta(hours=1), STATUS_TOOL.name, NOW - timedelta(2)),
            "a_second": ("approved", NOW + timedelta(hours=1), STATUS_TOOL.name, NOW),
            "a_ran": ("approved", NOW + timedelta(hours=1), STATUS_TOOL.name, NOW),
            "a_lapsed": ("approved", NOW, STATUS_TOOL.name, NOW),
            "a_other_tool": ("approved", NOW + timedelta(hours=1), "other.tool", NOW),
            "p_pending": ("pending", NOW + timedelta(hours=1), STATUS_TOOL.name, None),
            "r_rejected": ("rejected", NOW + timedelta(hours=1), STATUS_TOOL.name, NOW),
        }
        with psycopg.connect(url, autocommit=True) as conn:
            for ident, (state, expires, tool, decided) in rows.items():
                action = dict(base["action"])
                action["tool"] = dict(action["tool"]) | {"name": tool}
                verdict = None if state == "pending" else state
                conn.execute(
                    "INSERT INTO gate.suspension (id, trace_id, principal_id, agent_id,"
                    " required_capability, action, ent_hash, artefact, action_digest, raised_at,"
                    " expires_at, state, decided_by, decided_at, verdict, reason_code)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        ident,
                        base["trace_id"],
                        base["principal_id"],
                        base["agent_id"],
                        base["required_capability"],
                        Jsonb(action),
                        base["ent_hash"],
                        base["artefact"],
                        base["action_digest"],
                        NOW - timedelta(hours=3),
                        expires,
                        state,
                        None if decided is None else "u_narrow",
                        decided,
                        verdict,
                        "no_longer_needed" if state == "rejected" else None,
                    ),
                )
            conn.execute(
                "INSERT INTO ops.operation (key, connector, tool, principal_id, intent_ref, state)"
                " VALUES (%s, 'agent', %s, %s, 'a_ran', 'pending')",
                ("0" * 64, STATUS_TOOL.name, ASKER),
            )
        yield url


TO_RUN = "SELECT * FROM gate.approved_to_run(%s, %s, %s)"


@pytest.mark.needs_db
def test_the_function_lists_the_approved_unrun_unlapsed_actions_of_the_tools_asked_alone() -> None:
    """**What crosses the policy is an id and a principal, and only for what may run.** Two
    columns; the two approved actions of the tool asked for inside their window with no operation
    recorded, oldest decision first; not a pending, a rejected, a lapsed (its window ends at the
    instant asked), one already keyed in the ledger, or one of another tool; and the limit is the
    caller's. Delete this and the worker can run a rejected action, run one twice, or be handed the
    action and the artefact, which the policy exists to keep from anybody the row is not theirs."""
    with at_head_with_rows("brain_approved_to_run") as url, psycopg.connect(url) as conn:
        cursor = conn.execute(TO_RUN, (NOW, [STATUS_TOOL.name], 50))
        columns = [one.name for one in cursor.description or ()]
        rows = cursor.fetchall()
        limited = conn.execute(TO_RUN, (NOW, [STATUS_TOOL.name], 1)).fetchall()
        both = conn.execute(TO_RUN, (NOW, [STATUS_TOOL.name, "other.tool"], 50)).fetchall()
        earlier = conn.execute(TO_RUN, (NOW - timedelta(seconds=1), [STATUS_TOOL.name], 50))
        before_lapse = {one[0] for one in earlier.fetchall()}

    assert columns == ["suspension_id", "principal_id"]
    assert rows == [("a_first", ASKER), ("a_second", ASKER)]
    assert limited == [("a_first", ASKER)]
    assert {one[0] for one in both} == {"a_first", "a_second", "a_other_tool"}
    assert before_lapse == {"a_first", "a_second", "a_lapsed"}


@pytest.mark.needs_db
def test_the_function_is_a_pinned_definer_only_the_application_may_call() -> None:
    """Delete this and the function can run as its caller, where `0042`'s policy hides every row,
    or be callable by any login, which is a list of who has approved actions waiting."""
    with at_head_with_rows("brain_approved_to_run_grants") as url:
        [(definer, config)] = sql(
            url,
            "SELECT prosecdef, proconfig FROM pg_proc WHERE proname = 'approved_to_run'",
        )
        [(app, fast)] = sql(
            url,
            "SELECT has_function_privilege('brain_app', %s, 'EXECUTE'),"
            " has_function_privilege('brain_fastlane', %s, 'EXECUTE')",
            migration().FUNCTION,
            migration().FUNCTION,
        )
    assert definer is True
    assert config == ["search_path=pg_catalog, pg_temp"]
    assert (app, fast) == (True, False)


@pytest.mark.needs_db
def test_the_migration_reverses_and_applies_again() -> None:
    """Down removes the function and the control's name, and up puts both back. Delete this and a
    rollback can leave a definer function behind that no migration knows it owns."""
    from tests.unit.test_acceptance import at_head

    count = "SELECT count(*) FROM pg_proc WHERE proname = 'approved_to_run'"
    with at_head("brain_approved_to_run_round") as url:
        database = url.rsplit("/", 1)[-1]
        migrate(database, "downgrade", str(migration().down_revision))
        gone = sql(url, count)
        migrate(database, "upgrade", "heads")
        back = sql(url, count)
    assert (gone, back) == ([(0,)], [(1,)])


# ------------------------------------------------------------------------ the agent, read now
@pytest.mark.parametrize("selectable", [True, False])
def test_an_agent_that_is_not_enabled_has_no_standing_and_an_enabled_one_has_its_own(
    monkeypatch: pytest.MonkeyPatch, selectable: bool
) -> None:
    """**A disabled agent runs nothing it was approved for.** The agent's record is read now, under
    the runner's actor; one that is not selectable has no standing, and one that is stands at its
    own stored ceiling and the leash its install binds. Delete this and an agent switched off after
    an approval still has the approval carried out in its name."""
    import brain.agent_routes as routes
    import brain.agents.model as model

    record = SimpleNamespace(is_selectable=selectable)
    said: list[Any] = []

    class Result:
        def __init__(self, value: Any) -> None:
            self.value = value

        def scalar_one_or_none(self) -> Any:
            return self.value

        def one_or_none(self) -> Any:
            return self.value

    class Session:
        async def execute(self, statement: Any, params: Any = None) -> Result:
            said.append(statement if params is None else params)
            return Result({"agent": "row", "install": ("instance", "version")}.get(statement))

        @asynccontextmanager
        async def begin(self) -> AsyncIterator[None]:
            yield

    @asynccontextmanager
    async def sessions() -> AsyncIterator[Session]:
        yield Session()

    monkeypatch.setattr(routes, "one_agent", lambda agent_id: "agent")
    monkeypatch.setattr(routes, "install_for", lambda agent_id: "install")
    monkeypatch.setattr(routes, "record_of", lambda row: record if row == "row" else None)
    monkeypatch.setattr(routes, "install_of", lambda instance, version, found: (instance, found))
    monkeypatch.setattr(routes, "leash_of", lambda install, registry: LEASH)
    monkeypatch.setattr(model, "entitlement_ceiling", lambda found: CEILING)
    found = run(lambda: approved_runs.StoredStandings(sessions).standing("agent_test", NOW))  # type: ignore[arg-type]
    from brain.ops.automation_run import RUNNER_ACTOR

    assert said[0]["value"] == RUNNER_ACTOR
    assert found == (Standing(ceiling=CEILING, leash=LEASH) if selectable else None)
