"""The runtime-rule checks, passing at head and failing with the product broken, and the scan.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test
does.

Task ids: M13.7.1, M20.4.2
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from brain.ops import acceptance_run, runtime_scan
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_harness"
ONE = "only_the_runtime_gives_a_model_tools"
TWO = "an_authors_failed_test_never_stops_a_publish"
SRC = Path(__file__).resolve().parents[2] / "src" / "brain"


def test_the_module_declares_two_checks_each_naming_the_leaf_it_proves() -> None:
    """One check per leaf. Delete this and a check can lose its leaf with the page showing the
    same row, or start closing a leaf it does not prove."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (ONE, ("M13.7.1",)),
        (TWO, ("M20.4.2",)),
    ]
    assert checks_in(MODULE) == [ONE, TWO]
    from brain.ops import acceptance_checks_harness as module

    assert 800 <= module.CHECK_ORDER <= 899


# ----------------------------------------------------------------------- the scan itself
def _trees(**sources: str) -> dict[str, ast.Module]:
    return {name.replace("__", "."): ast.parse(text) for name, text in sources.items()}


RUNTIME = "async def run(m):\n    return await m.complete([])\n"
BASE = {
    "brain__gate__runtime": RUNTIME,
    "brain__ops__connector_sync": "def done(s):\n    return s.complete()\n",
    "brain__ops__connector_sync_run": "def done(s):\n    return s.complete()\n",
}


def test_the_scan_reads_the_product_and_finds_one_runtime() -> None:
    """The positive case: the repository's own source has no second place. Delete this and a scan
    that reports nothing for every input passes the whole file."""
    assert runtime_scan.findings(runtime_scan.parsed(SRC)) == ()


def test_a_second_module_that_calls_a_model_with_a_catalogue_is_named() -> None:
    """A module that calls a model and holds a projected catalogue is reported by name, and one
    that calls a model and holds no catalogue is reported as unlisted. Delete this and a second
    loop passes whenever it takes a name nobody listed."""
    loop = "from brain.gate.catalogue import ProjectedCatalogue\n" + RUNTIME
    found = runtime_scan.findings(_trees(**BASE, brain__x__loop=loop))
    assert "brain.x.loop: a second place that calls a model" in found
    assert "brain.x.loop: calls a model while holding a tool catalogue" in found


def test_an_allowed_module_that_grows_a_catalogue_is_named() -> None:
    """A module on the no-tools list that starts importing a catalogue is a second loop in a
    familiar name. Delete this and the allow-list becomes a way past the rule."""
    grown = "from brain.gate.catalogue import ProjectedCatalogue\n" + RUNTIME
    found = runtime_scan.findings(_trees(**BASE, brain__gate__model_lane=grown))
    assert found == ("brain.gate.model_lane: calls a model while holding a tool catalogue",)


def test_an_exception_that_no_longer_calls_a_model_is_named() -> None:
    """A stale name on the not-a-model list is a door for the next module of that name. Delete
    this and the list keeps names that stopped meaning anything."""
    base = {k: v for k, v in BASE.items() if k != "brain__ops__connector_sync"}
    assert runtime_scan.findings(_trees(**base)) == (
        "brain.ops.connector_sync: an exception that no longer calls .complete(",
    )


def test_a_scan_that_cannot_find_the_runtime_says_so() -> None:
    """Reading nothing must not read as passing. Delete this and an empty directory proves the
    rule."""
    assert runtime_scan.findings({}) != ()


def test_the_minimum_is_below_what_the_product_holds() -> None:
    """The floor the install check reads the size of the source against is below the product's
    real size, so the check runs, and above anything a stray directory holds."""
    assert 50 < runtime_scan.AT_LEAST_THIS_MANY_MODULES < len(runtime_scan.parsed(SRC))


# ----------------------------------------------------------------------- the checks, run
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_harness") as url:
        yield url


def run_harness(url: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_the_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The checks as the worker runs them.** Both pass and nothing they wrote is left. Delete
    this and a check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    assert run_harness(install) == {ONE: (PASSED, ""), TWO: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_second_loop_in_the_source_fails_the_first_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second module calling a model beside the runtime. Delete this and the check closes
    M13.7.1 on a product that has two loops."""
    real = runtime_scan.parsed

    def with_a_loop(root: Path) -> dict[str, ast.Module]:
        found = real(root)
        found["brain.x.second"] = ast.parse(RUNTIME)
        return found

    monkeypatch.setattr(runtime_scan, "parsed", with_a_loop)
    outcome, reason = run_harness(install)[ONE]
    assert outcome == FAILED
    assert "second place that calls a model" in reason


@pytest.mark.needs_db
def test_a_scan_that_never_finds_anything_fails_the_first_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scan answering nothing for every input. Delete this and the check passes on a scan that
    cannot say no."""
    monkeypatch.setattr(runtime_scan, "findings", lambda trees: ())
    outcome, reason = run_harness(install)[ONE]
    assert outcome == FAILED
    assert "did not name a module" in reason


@pytest.mark.needs_db
def test_an_author_check_that_can_block_fails_the_second_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The publish gate counting an author's failed check as blocking. Delete this and the check
    closes M20.4.2 on a gate an author can stop."""
    from brain.builder import publish

    monkeypatch.setattr(publish.Check, "blocks", property(lambda self: not self.passed))
    outcome, reason = run_harness(install)[TWO]
    assert outcome == FAILED
    assert "an author wrote and that failed stopped a publish" in reason


@pytest.mark.needs_db
def test_a_system_check_that_cannot_block_fails_the_second_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate ignoring every failed check. Delete this and a gate that never refuses passes."""
    from brain.builder import publish

    monkeypatch.setattr(publish.Check, "blocks", property(lambda self: False))
    outcome, reason = run_harness(install)[TWO]
    assert outcome == FAILED
    assert "the system wrote and that failed did not stop" in reason
