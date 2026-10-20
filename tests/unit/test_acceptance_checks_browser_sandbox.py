"""The sandbox install check: what it names, that it says not run when there is no host to ask, and
that it fails for each way a host could describe a sandbox as weaker than the product says.

The launcher is answered for by a stand-in that speaks the rehearsal's wire and nothing else, so
every outcome the check can reach is reached here: a host that answers cleanly, one that finds gaps,
one with the wrong runtime, one that left something behind, one that is not there and one that says
nothing. What is not shown here is a real Docker daemon describing a real gVisor container; that is
the check itself, run on an install that has one, and `ops/browser/REHEARSAL.md`.

Skipped halves: the database test skips when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M19.1.1, M19.1.5, M19.1.6, M19.3.5, M19.6.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest

from brain.browsing import driver, sandbox
from brain.browsing.wire import Kind, decode, encode
from brain.ops import acceptance_checks_browser_sandbox as module
from brain.ops.acceptance import (
    NOT_RUN,
    PASSED,
    CheckFailedError,
    CheckNotRunError,
    registered,
)
from tests.unit.test_acceptance import at_head, checks_in
from tests.unit.test_acceptance_cards import INSTALL, run_checks

MODULE = "brain.ops.acceptance_checks_browser_sandbox"
NAME = "a_browser_sandbox_is_made_for_one_run_and_removed_with_it"


# ------------------------------------------------------------------ a host that answers
@dataclass
class Launcher:
    """A launcher that answers a `rehearse` line the way the real one would, or does not."""

    gaps: tuple[str, ...] = ()
    runtime: str = "runsc"
    left_behind: int = 0
    silent: bool = False
    wrong_run: bool = False
    sent: bytes = b""

    async def put_line(self, line: bytes) -> None:
        self.sent = line

    async def next_line(self) -> bytes:
        if self.silent:
            return b""
        asked = decode(self.sent)
        return encode(
            Kind.REHEARSED,
            run_id="somebody-else" if self.wrong_run else asked.fields["run_id"],
            runtime=self.runtime,
            gaps=list(self.gaps),
            left_behind=self.left_behind,
        )

    async def hang_up(self) -> None:
        return None


class Rolled:
    """A harness stand-in: the check reads its run and opens a session to ask the switch."""

    run = "r1"

    @asynccontextmanager
    async def sessions(self) -> Any:
        yield None


@pytest.fixture
def switched(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    async def on(session: object) -> bool:
        return True

    monkeypatch.setattr(driver, "browser_runs_are_on", on)
    yield


def reached(monkeypatch: pytest.MonkeyPatch, launcher: Launcher) -> Launcher:
    async def dial() -> Launcher:
        return launcher

    monkeypatch.setattr(module, "_launcher_dial", dial)
    return launcher


async def run_it() -> None:
    await module.a_browser_sandbox_is_made_for_one_run_and_removed_with_it(Rolled())  # type: ignore[arg-type]


# ------------------------------------------------------------------ what it names
def test_the_check_names_the_five_sandbox_leaves_and_sits_in_this_packages_range() -> None:
    """Delete this and the check can lose a leaf with the page showing the same row, or sit outside
    the keys this package was given, where it would collide with another package's."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (NAME, ("M19.1.1", "M19.1.5", "M19.1.6", "M19.3.5", "M19.6.4"))
    ]
    assert checks_in(MODULE) == [NAME]
    assert 2300 <= module.CHECK_ORDER <= 2399


# ------------------------------------------------------------------ no host to ask
def test_a_switch_that_is_off_is_not_run_and_the_launcher_is_never_dialled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check starts containers on the host, so it asks first. Delete this and an install that
    never agreed to browser runs has a network and a proxy made on its host by a check."""

    async def off(session: object) -> bool:
        return False

    async def never() -> Launcher:
        msg = "the launcher was dialled with the switch off"
        raise AssertionError(msg)

    monkeypatch.setattr(driver, "browser_runs_are_on", off)
    monkeypatch.setattr(module, "_launcher_dial", never)

    with pytest.raises(CheckNotRunError) as stopped:
        asyncio.run(run_it())

    assert stopped.value.reason == module.SWITCH_OFF


def test_a_launcher_that_is_not_there_is_not_run_and_not_passed(
    switched: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first half passes on any machine, so without this an install with no gVisor and no
    launcher passes. Delete this and it does, and closes five leaves it has not shown."""

    async def absent() -> Launcher:
        raise OSError

    monkeypatch.setattr(module, "_launcher_dial", absent)

    with pytest.raises(CheckNotRunError) as stopped:
        asyncio.run(run_it())

    assert stopped.value.reason == module.LAUNCHER_ABSENT


def test_a_launcher_that_says_nothing_is_not_run(
    switched: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a launcher that closes the connection is read as having found no gaps."""
    reached(monkeypatch, Launcher(silent=True))

    with pytest.raises(CheckNotRunError) as stopped:
        asyncio.run(run_it())

    assert stopped.value.reason == module.LAUNCHER_SILENT


# ------------------------------------------------------------------ a host that answers
def test_a_host_whose_daemon_describes_the_sandbox_as_asked_passes_the_check(
    switched: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive case, and the rehearsal line it sent is the one the launcher accepts. Delete
    this and a check that fails on every host passes the tests below."""
    launcher = reached(monkeypatch, Launcher())

    asyncio.run(run_it())

    sent = decode(launcher.sent)
    assert sent.kind is Kind.REHEARSE
    assert sent.fields["origins"] == [module.REHEARSAL_ORIGIN]
    assert str(sent.fields["run_id"]).startswith("rehearsal-")


@pytest.mark.parametrize(
    ("launcher", "words"),
    [
        (Launcher(gaps=("the runner is not running under runsc",)), "weaker"),
        (Launcher(runtime="runc"), "gVisor runtime"),
        (Launcher(runtime=""), "gVisor runtime"),
        (Launcher(left_behind=1), "wholly removed"),
        (Launcher(wrong_run=True), "something else"),
    ],
)
def test_each_way_the_host_can_fall_short_fails_the_check(
    switched: None, monkeypatch: pytest.MonkeyPatch, launcher: Launcher, words: str
) -> None:
    """Delete this and a host that reports gaps, runs the runner under runc, leaves a proxy behind
    or answers about another run passes."""
    reached(monkeypatch, launcher)

    with pytest.raises(CheckFailedError) as failed:
        asyncio.run(run_it())

    assert words in failed.value.reason


# ------------------------------------------------------------------ the half that needs no host
def test_a_sandbox_gap_check_that_is_blind_fails_the_check_before_any_host_is_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the switch off, so only the first half can have spoken. Delete this and the first half
    is a statement the check makes and never tests."""
    monkeypatch.setattr(sandbox, "sandbox_gaps", lambda box: ())

    with pytest.raises(CheckFailedError) as failed:
        asyncio.run(run_it())

    assert "volume, a bind or a writable root" in failed.value.reason


def test_a_comparison_that_finds_nothing_fails_the_check(
    switched: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a comparison of the daemon's answer that is blind is never noticed, and every
    host passes it."""
    from brain.browsing import inspection

    monkeypatch.setattr(inspection, "observed_gaps", lambda *a, **k: ())
    reached(monkeypatch, Launcher())

    with pytest.raises(CheckFailedError) as failed:
        asyncio.run(run_it())

    assert "another runtime" in failed.value.reason


# ------------------------------------------------------------------ on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_browser_sandbox") as url:
        yield url


@pytest.fixture(autouse=True)
def _install_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
def test_on_an_install_with_the_switch_off_the_check_is_not_run_and_says_why(install: str) -> None:
    """**The module as the worker runs it, against a database at head.** Browser runs ship off, so
    the check ends as not run with its sentence, which is what an install with no gVisor must show.
    Delete this and the check is only ever run against a harness this file made up."""
    outcomes = run_checks(install, registered((MODULE,)))

    assert outcomes == {NAME: (NOT_RUN, module.SWITCH_OFF)}
    assert PASSED not in {outcome for outcome, _ in outcomes.values()}


# --------------------------------------------------------- each statement of the first half
def test_two_runs_given_one_sandbox_name_fail_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a sandbox builder that names every run's network alike, so runs share one,
    passes the first half."""
    real = sandbox.sandbox_for
    monkeypatch.setattr(
        sandbox,
        "sandbox_for",
        lambda run_id, **kw: real("same-run", **kw),
    )

    with pytest.raises(CheckFailedError) as failed:
        asyncio.run(run_it())

    assert "one network or one container name" in failed.value.reason


def test_a_runner_given_another_runtime_in_its_body_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a builder that stops asking for gVisor passes the first half, where only the
    gap check would have to notice."""
    real = sandbox.sandbox_for

    def under_runc(run_id: str, **kw: Any) -> Any:
        box = real(run_id, **kw)
        box.runner.body["HostConfig"]["Runtime"] = "runc"
        return box

    monkeypatch.setattr(sandbox, "sandbox_for", under_runc)
    monkeypatch.setattr(sandbox, "sandbox_gaps", lambda box: ())

    with pytest.raises(CheckFailedError) as failed:
        asyncio.run(run_it())

    assert "gVisor runtime" in failed.value.reason


def test_a_gap_check_blind_to_a_network_with_a_gateway_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a network's own gateway is the one weakness the first half does not plant."""
    real = sandbox.sandbox_gaps

    def blind_to_routes(box: Any) -> tuple[str, ...]:
        return () if box.network.get("Internal") is False else real(box)

    monkeypatch.setattr(sandbox, "sandbox_gaps", blind_to_routes)

    with pytest.raises(CheckFailedError) as failed:
        asyncio.run(run_it())

    assert "gateway" in failed.value.reason


def test_a_comparison_blind_to_a_second_network_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a comparison that forgets to count networks passes the first half."""
    from brain.browsing import inspection

    real = inspection.observed_gaps

    def blind_to_networks(run_id: str, **facts: Any) -> tuple[str, ...]:
        if len(facts["runner"].networks) > 1:
            return ()
        return real(run_id, **facts)

    monkeypatch.setattr(inspection, "observed_gaps", blind_to_networks)

    with pytest.raises(CheckFailedError) as failed:
        asyncio.run(run_it())

    assert "second network" in failed.value.reason


def test_a_comparison_that_reports_a_gap_in_a_faithful_daemon_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a comparison that is wrong in the other direction, finding a gap everywhere,
    would send every install with a real daemon to a failure the product caused."""
    from brain.browsing import inspection

    monkeypatch.setattr(inspection, "observed_gaps", lambda *a, **k: ("a gap",))

    with pytest.raises(CheckFailedError) as failed:
        asyncio.run(run_it())

    assert "did as it was asked" in failed.value.reason
