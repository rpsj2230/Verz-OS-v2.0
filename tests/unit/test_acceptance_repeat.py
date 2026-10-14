"""One complete run is the gate, and a run short of clean is repeated for only what did not pass.

Owner-approved on 2026-10-14. Two properties are held here without a database: **a run is marked
complete only when the store holds a result for every registered check** (so the single run the
proof sweep reads is never a partial one), and **a repeat runs only the checks that failed or
came back not run, in a new run of the same commit that carries the passes and says where from**.
The decision functions are pure; the orchestration runs against a fake store that keeps what the
real one would, with the store's functions replaced by name in both modules that call them.

Task ids: M38.5.4
"""

from __future__ import annotations

import asyncio
import io
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.ops import acceptance_resume, acceptance_run
from brain.ops.acceptance import (
    CARRIED_FORWARD_FROM,
    FAILED,
    NOT_RUN,
    PASSED,
    Check,
    Occasion,
    Result,
)
from brain.ops.acceptance_resume import (
    STALE_AFTER,
    CompleteRun,
    Unfinished,
    carried_forward,
    finish_if_whole,
    unsettled,
)
from brain.settings import settings_from

LEAF = "M38.5.4"
COMMIT = "bbbbbbb"
AT = datetime(2999, 1, 1, tzinfo=UTC)
SOURCE = uuid.UUID("00000000-0000-4000-8000-000000000001")

#: The decision functions never touch the engine they are handed, so none is made.
NO_ENGINE: Any = None


def result(name: str, outcome: str, reason: str = "") -> Result:
    return Result(name, (LEAF,), outcome, AT, reason)


# ------------------------------------------------------------------------------ the decision
def test_the_checks_a_repeat_runs_are_those_that_did_not_pass_in_suite_order() -> None:
    """A check that failed, one that did not run and one with no result at all are each run again,
    in the order the suite declares them and once each; a check that passed is not.

    Delete this and a repeat runs everything again (the thirty-five minutes it exists to save), or
    skips a check that never recorded and leaves the new run short of a registered check."""
    recorded = [
        result("check_a", PASSED),
        result("check_b", FAILED, "broke"),
        result("check_c", NOT_RUN, "no"),
    ]

    assert unsettled(["check_a", "check_b", "check_c", "check_d", "check_b"], recorded) == (
        "check_b",
        "check_c",
        "check_d",
    )
    assert unsettled(["check_a"], recorded) == ()
    assert unsettled(["check_a", "check_b"], []) == ("check_a", "check_b")


def test_a_repeat_carries_only_passes_of_checks_the_suite_still_has() -> None:
    """Passes are copied with the run they came from; failures and not-run results are not; a check
    the suite no longer declares is not. Each carried reason begins with the shared prefix and
    names the run, and fits the column.

    Delete this and a repeat carries a failure forward as if it had passed, or leaves no mark that
    a result was not run again."""
    recorded = [
        result("check_a", PASSED),
        result("check_b", FAILED, "broke"),
        result("check_c", NOT_RUN, "no"),
        result("check_gone", PASSED),
    ]

    carried = carried_forward(["check_a", "check_b", "check_c"], recorded, SOURCE)

    assert [one.name for one in carried] == ["check_a"]
    (one,) = carried
    assert one.outcome == PASSED
    assert one.reason.startswith(CARRIED_FORWARD_FROM)
    assert str(SOURCE) in one.reason
    assert (one.leaves, one.checked_at) == ((LEAF,), AT)


# -------------------------------------------------------- complete only when every check is in
def test_a_run_is_marked_complete_when_the_store_holds_every_registered_check() -> None:
    """The positive half: with a result for each name the run is closed, once. Delete this and a
    guard that refuses everything passes the test below."""
    closed: list[uuid.UUID] = []

    async def read(_: Any, run_id: uuid.UUID) -> list[Result]:
        return [result("check_a", PASSED), result("check_b", FAILED, "broke")]

    async def close(_: Any, run_id: uuid.UUID) -> bool:
        closed.append(run_id)
        return True

    marked, lacking = asyncio.run(
        finish_if_whole(NO_ENGINE, SOURCE, ["check_a", "check_b"], read=read, close=close)
    )

    assert (marked, lacking, closed) == (True, (), [SOURCE])


def test_a_run_short_of_a_registered_check_is_never_marked_complete() -> None:
    """**The safeguard that survives the move to one run.** A registered check with no recorded
    result leaves the run `running`, however the loop that wrote the others ended, and names what
    is missing. The close is not even attempted. Delete this and a run cut short counts as the one
    complete run the proof sweep reads, closing tasks on a partial result."""
    closed: list[uuid.UUID] = []

    async def read(_: Any, run_id: uuid.UUID) -> list[Result]:
        return [result("check_a", PASSED), result("check_c", PASSED)]

    async def close(_: Any, run_id: uuid.UUID) -> bool:
        closed.append(run_id)
        return True

    marked, lacking = asyncio.run(
        finish_if_whole(
            NO_ENGINE, SOURCE, ["check_a", "check_b", "check_c", "check_d"], read=read, close=close
        )
    )

    assert (marked, lacking, closed) == (False, ("check_b", "check_d"), [])


def test_a_run_another_worker_abandoned_is_reported_as_not_marked_with_nothing_lacking() -> None:
    """Whole, but the store refuses to close it because somebody abandoned it meanwhile: not
    marked, and nothing lacking, so the caller can say which of the two happened. Delete this and
    an abandoned run is reported as one that was short of a check."""

    async def read(_: Any, run_id: uuid.UUID) -> list[Result]:
        return [result("check_a", PASSED)]

    async def close(_: Any, run_id: uuid.UUID) -> bool:
        return False

    taken = asyncio.run(finish_if_whole(NO_ENGINE, SOURCE, ["check_a"], read=read, close=close))

    assert taken == (False, ())


# ------------------------------------------------------------------ the orchestration, no database
class Engine:
    async def dispose(self) -> None:
        return None


class Store:
    """What the real store keeps, in memory: runs, their rows and what was closed."""

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, list[Result]] = {}
        self.opened: list[tuple[uuid.UUID, str, Occasion]] = []
        self.closed: list[uuid.UUID] = []
        self.complete: CompleteRun | None = None
        self.running: tuple[Unfinished, ...] = ()
        self.drop: set[str] = set()

    def source(self, results: list[Result]) -> None:
        self.rows[SOURCE] = list(results)
        self.complete = CompleteRun(SOURCE, COMMIT, Occasion.DEPLOY, AT)

    async def unfinished(self, engine: Any) -> tuple[Unfinished, ...]:
        return self.running

    async def newest_complete_run(self, engine: Any, commit: str) -> CompleteRun | None:
        return self.complete if self.complete and self.complete.commit == commit else None

    async def recorded(self, engine: Any, run_id: uuid.UUID) -> tuple[Result, ...]:
        return tuple(self.rows.get(run_id, ()))

    async def open_run(
        self, engine: Any, *, run_id: uuid.UUID, commit: str, occasion: Occasion, **_: Any
    ) -> None:
        self.rows[run_id] = []
        self.opened.append((run_id, commit, occasion))

    async def record_check(self, engine: Any, one: Result, *, run_id: uuid.UUID, **_: Any) -> None:
        if one.name not in self.drop:
            self.rows[run_id].append(one)

    async def beat(self, engine: Any, run_id: uuid.UUID) -> None:
        return None

    async def finish(self, engine: Any, run_id: uuid.UUID) -> bool:
        self.closed.append(run_id)
        return True


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Iterator[Store]:
    """The fake store in place of the real one, in `acceptance_run` and in `acceptance_resume`
    (where `finish_if_whole` looks `recorded` and `finish` up when it is called)."""
    held = Store()
    for module in (acceptance_run, acceptance_resume):
        for name in ("recorded", "finish"):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, getattr(held, name))
    for name in ("unfinished", "newest_complete_run", "open_run", "record_check", "beat"):
        monkeypatch.setattr(acceptance_run, name, getattr(held, name))

    async def not_in_use(*_: Any, **__: Any) -> bool:
        return False

    monkeypatch.setattr(acceptance_run, "in_use", not_in_use)
    yield held


def suite(*names: str) -> list[Check]:
    async def body(_: Any) -> None:
        return None

    return [Check(name, (LEAF,), "A check made for this test.", body) for name in names]


def repeat(
    names: list[str], outcomes: dict[str, tuple[str, str]], ran: list[str]
) -> tuple[Occasion | None, tuple[Result, ...], str]:
    """`repeat_unsettled` over `names`, each check coming to `outcomes[name]` and noted in `ran`."""
    stream = io.StringIO()

    async def one(_: Any, check: Check, **kwargs: Any) -> tuple[str, str]:
        ran.append(check.name)
        return outcomes[check.name]

    patch = pytest.MonkeyPatch()
    patch.setattr(acceptance_run, "run_one", one)
    try:
        occasion, results = asyncio.run(
            acceptance_run.repeat_unsettled(
                "postgresql://unused",
                settings=settings_from({}),
                commit=COMMIT,
                checks=suite(*names),
                stream=stream,
                make_engine=lambda url: Engine(),  # type: ignore[arg-type,return-value]
            )
        )
    finally:
        patch.undo()
    return occasion, results, stream.getvalue()


def test_a_repeat_runs_only_what_did_not_pass_and_carries_the_rest(store: Store) -> None:
    """Four checks, two passed (a, d), one failed (b), one did not run (c). The repeat runs b and c
    and nothing else, in a new run of the same commit asked for by a person, copies a and d with
    the run they came from, and records all four before marking the new run complete.

    Delete this and a repeat runs the whole suite again, records only the new results (so the run
    is never whole), or marks itself complete without the passes."""
    store.source(
        [
            result("check_a", PASSED),
            result("check_b", FAILED, "broke"),
            result("check_c", NOT_RUN, "no vendor"),
            result("check_d", PASSED),
        ]
    )
    ran: list[str] = []

    occasion, results, said = repeat(
        ["check_a", "check_b", "check_c", "check_d"],
        {"check_b": (PASSED, ""), "check_c": (FAILED, "still broken")},
        ran,
    )

    assert ran == ["check_b", "check_c"]
    assert occasion is Occasion.REQUEST
    ((new_run, commit, asked),) = store.opened
    assert (commit, asked) == (COMMIT, Occasion.REQUEST)
    assert new_run != SOURCE
    kept = {one.name: one for one in store.rows[new_run]}
    assert sorted(kept) == ["check_a", "check_b", "check_c", "check_d"]
    assert (kept["check_a"].outcome, kept["check_d"].outcome) == (PASSED, PASSED)
    assert (
        kept["check_a"].reason.startswith(CARRIED_FORWARD_FROM)
        and str(SOURCE) in kept["check_a"].reason
    )
    assert (kept["check_b"].outcome, kept["check_b"].reason) == (PASSED, "")
    assert (kept["check_c"].outcome, kept["check_c"].reason) == (FAILED, "still broken")
    assert store.closed == [new_run]
    assert [one.name for one in results] == ["check_a", "check_d", "check_b", "check_c"]
    assert "repeating 2 check(s) and carrying 2" in said


def test_a_repeat_leaves_the_run_it_repeats_as_it_was(store: Store) -> None:
    """The earlier run keeps its failure and is not closed again: the table is append-only and the
    first failure is what somebody reading a regression needs. Delete this and a repeat edits the
    rows of a finished run, which was a fact when it finished."""
    store.source([result("check_a", FAILED, "broke")])
    before = list(store.rows[SOURCE])

    repeat(["check_a"], {"check_a": (PASSED, "")}, [])

    assert store.rows[SOURCE] == before
    assert SOURCE not in store.closed


def test_a_repeat_whose_new_run_lacks_a_registered_check_is_left_unfinished(store: Store) -> None:
    """If a result was not recorded the new run is not marked complete, whatever the loop did, and
    the log says how many checks are missing. Delete this and a repeat becomes the one complete
    run with a hole in it."""
    store.source([result("check_a", PASSED), result("check_b", FAILED, "broke")])
    store.drop = {"check_b"}

    _, _, said = repeat(["check_a", "check_b"], {"check_b": (PASSED, "")}, [])

    assert store.closed == []
    assert "left unfinished: 1 registered check(s) have no recorded result" in said


def test_a_repeat_with_nothing_to_repeat_starts_no_run(store: Store) -> None:
    """When every registered check passed there is nothing to do, and no run is opened: an empty
    run recorded as asked for would be noise on the install page. Delete this and a clean run
    gets a pointless twin."""
    store.source([result("check_a", PASSED), result("check_b", PASSED)])
    ran: list[str] = []

    occasion, results, said = repeat(["check_a", "check_b"], {}, ran)

    assert (occasion, results, ran, store.opened) == (None, (), [], [])
    assert "every check passed in the run to repeat" in said


def test_a_repeat_with_no_complete_run_of_this_commit_is_refused(store: Store) -> None:
    """Passes are only ever carried within one release, so a commit with no complete run of its
    own has nothing to repeat, and the newest run of another commit is not offered. Delete this and
    a repeat borrows another release's passes, which is the mixture the sweep refuses."""
    store.complete = CompleteRun(SOURCE, "ccccccc", Occasion.DEPLOY, AT)
    store.rows[SOURCE] = [result("check_a", FAILED, "broke")]

    with pytest.raises(acceptance_run.RepeatRefusedError, match="no complete run of bbbbbbb"):
        repeat(["check_a"], {"check_a": (PASSED, "")}, [])

    assert store.opened == []


def test_a_repeat_is_refused_while_a_worker_is_running_this_commit(store: Store) -> None:
    """A worker whose heartbeat is fresh owns the run in progress, and a repeat beside it would be
    two runs of one release at once. Delete this and the two race to record the same checks."""
    store.source([result("check_a", FAILED, "broke")])
    store.running = (Unfinished(uuid.uuid4(), COMMIT, Occasion.DEPLOY, AT, timedelta(seconds=1)),)
    assert timedelta(seconds=1) < STALE_AFTER

    with pytest.raises(acceptance_run.RepeatRefusedError, match="still running this commit"):
        repeat(["check_a"], {"check_a": (PASSED, "")}, [])

    assert store.opened == []


def test_a_silent_run_of_this_commit_does_not_stop_a_repeat(store: Store) -> None:
    """The positive sibling: a run whose worker has stopped beating is not in progress, so the
    refusal above is not a refusal of everything. Delete this and any unfinished row at all blocks
    a repeat."""
    store.source([result("check_a", FAILED, "broke")])
    store.running = (Unfinished(uuid.uuid4(), COMMIT, Occasion.DEPLOY, AT, STALE_AFTER * 2),)

    occasion, _, _ = repeat(["check_a"], {"check_a": (PASSED, "")}, [])

    assert occasion is Occasion.REQUEST


# ------------------------------------------------------------------------------- the command
class FakeSettings:
    database_url = "postgresql://unused"

    def resolved_commit(self) -> str:
        return COMMIT


@pytest.fixture
def command(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """`main` with its settings and both runners replaced, recording which one it called."""
    called: list[str] = []

    async def saved(_: str) -> None:
        return None

    monkeypatch.setattr(acceptance_run, "Settings", FakeSettings)
    monkeypatch.setattr(acceptance_run, "hold_what_was_saved", saved)

    async def full(*_: Any, **kwargs: Any) -> tuple[Occasion, tuple[Result, ...]]:
        called.append(f"full force={kwargs['force']}")
        return Occasion.REQUEST, (result("check_a", PASSED),)

    async def again(*_: Any, **__: Any) -> tuple[Occasion | None, tuple[Result, ...]]:
        called.append("repeat")
        return Occasion.REQUEST, (result("check_a", PASSED),)

    monkeypatch.setattr(acceptance_run, "run_acceptance", full)
    monkeypatch.setattr(acceptance_run, "repeat_unsettled", again)
    return called


def test_the_flag_runs_the_repeat_and_no_flag_runs_the_whole_suite(
    command: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """`--repeat-unsettled` is the way to repeat only what did not pass, and without it the command
    is what it always was: every check, forced. Delete this and the flag is accepted and ignored,
    or becomes the default and a person asking for a full run gets a partial one."""
    assert acceptance_run.main(["--repeat-unsettled"]) == 0
    assert acceptance_run.main([]) == 0

    assert command == ["repeat", "full force=True"]
    assert "acceptance bbbbbbb: 1 passed" in capsys.readouterr().out


def test_a_refused_repeat_exits_non_zero_and_a_clean_one_exits_zero(
    command: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A repeat that could not start says why on stderr and exits 1, and a repeat with nothing to do
    exits 0 and prints nothing as a result. Delete this and a script that repeats until clean loops
    on a refusal, or stops on a run that was already clean."""

    async def refused(*_: Any, **__: Any) -> tuple[Occasion | None, tuple[Result, ...]]:
        msg = "there is no complete run of bbbbbbb to repeat"
        raise acceptance_run.RepeatRefusedError(msg)

    async def nothing(*_: Any, **__: Any) -> tuple[Occasion | None, tuple[Result, ...]]:
        return None, ()

    monkeypatch.setattr(acceptance_run, "repeat_unsettled", refused)
    assert acceptance_run.main(["--repeat-unsettled"]) == 1
    assert "there is no complete run of bbbbbbb to repeat" in capsys.readouterr().err

    monkeypatch.setattr(acceptance_run, "repeat_unsettled", nothing)
    assert acceptance_run.main(["--repeat-unsettled"]) == 0
    assert capsys.readouterr().out == ""


def test_a_repeat_that_still_has_a_failed_check_exits_non_zero(
    command: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The repeat's exit code is the run's, as the full run's is: a failed check is 1. Delete this
    and a repeat that is still red reports success."""

    async def red(*_: Any, **__: Any) -> tuple[Occasion | None, tuple[Result, ...]]:
        return Occasion.REQUEST, (result("check_a", FAILED, "broke"),)

    monkeypatch.setattr(acceptance_run, "repeat_unsettled", red)

    assert acceptance_run.main(["--repeat-unsettled"]) == 1
