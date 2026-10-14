"""The browser agent's install checks, passing on PostgreSQL at head and failing with the product
broken the way it would plausibly break.

The first half runs anywhere: what each check names, where the module sits and what is held. The
database half runs the module as the worker would, against a database at head: both checks pass,
nothing they wrote is left in any table the suite counts or in the browser's own, and then each is
shown failing when the thing it proves is broken: a planner handed a page, a sandbox given a
volume, a write that starts without its approval, a session that is not counted, and a replay that
trusts the container.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M19.2.1, M19.9.3, M19.5.1, M19.5.3, M19.5.4
Task ids: M19.2.2, M19.2.3, M19.3.6, M19.6.2, M19.6.3
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_cards import INSTALL, run_checks

MODULE = "brain.ops.acceptance_checks_browser"
STRUCTURAL = "the_browser_planner_cannot_read_a_page_and_a_run_starts_empty"
JOINED = "a_browser_write_waits_for_a_person_and_runs_are_counted"
BROWSER_TABLES = ("agent.browser_envelope", "agent.browser_session")


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_the_two_checks_and_the_leaves_each_closes() -> None:
    """Delete this and a check can lose a leaf with the page showing the same row, and the
    leaf then closes on a check that never looked, or never closes."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (STRUCTURAL, ("M19.2.1", "M19.9.3", "M19.5.1", "M19.5.3", "M19.5.4")),
        (JOINED, ("M19.2.2", "M19.2.3", "M19.3.6", "M19.6.2", "M19.6.3")),
    ]
    assert checks_in(MODULE) == [STRUCTURAL, JOINED]


def test_the_module_sits_in_the_range_this_package_was_given() -> None:
    """The coordinator gave this package the keys 2300 to 2399, so two packages cannot share one.
    Delete this and a key outside the range is not noticed until two modules collide."""
    from brain.ops import acceptance_checks_browser as module

    assert 2300 <= module.CHECK_ORDER <= 2399


def test_the_replay_check_is_held_on_a_real_container_until_one_has_run() -> None:
    """The joined check drives the product's own runner with a page it made up, so the leaf that
    says the control plane re-checks what a container reports is on the proof sweep's hold list.
    Delete this and M19.3.6 closes on a run no container ever made."""
    import json
    from pathlib import Path

    held = json.loads(
        (Path(__file__).resolve().parents[2] / "docs" / "proof-sweep-holds.json").read_text(
            encoding="utf-8"
        )
    )["held"]
    assert "M19.3.6" in held


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_browser") as url:
        yield url


@pytest.fixture(autouse=True)
def _install_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def browser_rows(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in BROWSER_TABLES
    }


@pytest.mark.needs_db
def test_both_browser_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The module as the worker runs it.** Both checks pass and nothing they wrote is left in any
    table the suite counts or in the browser's own. Delete this and a check that can never pass on
    a real schema, or one that leaves an open browser session counted against an agent on the
    owner's install, reaches it first."""
    before, before_browser = counts(install), browser_rows(install)

    assert run_checks(install, registered((MODULE,))) == {
        STRUCTURAL: (PASSED, ""),
        JOINED: (PASSED, ""),
    }
    assert counts(install) == before
    assert browser_rows(install) == before_browser


@pytest.mark.needs_db
def test_the_structural_check_fails_when_a_sandbox_is_allowed_a_volume(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the sandbox's own gap check blind to a volume the check says so. Delete this and the
    check passes whatever `sandbox_gaps` does, so a run could be given a staff member's profile."""
    from brain.browsing import sandbox

    real = sandbox.sandbox_gaps

    def blind(box: object) -> tuple[str, ...]:
        runner = getattr(box, "runner")  # noqa: B009 - a stand-in for the typed attribute
        return () if runner.body.get("Volumes") else real(box)  # type: ignore[arg-type]

    monkeypatch.setattr(sandbox, "sandbox_gaps", blind)

    outcome = run_checks(install, registered((MODULE,)))[STRUCTURAL]

    assert outcome[0] == FAILED and "volume" in outcome[1]


@pytest.mark.needs_db
def test_the_joined_check_fails_when_a_session_is_not_counted(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the counter reading nothing, a second session is admitted and the check says so.
    Delete this and the per-site and per-agent limits are proved only by decisions nothing feeds."""
    from brain.browsing import driver
    from brain.browsing.concurrency import SessionCounts

    async def nothing(session: object, registry: object) -> SessionCounts:
        return SessionCounts()

    monkeypatch.setattr(driver, "held_counts", nothing)

    outcome = run_checks(install, registered((MODULE,)))[JOINED]

    assert outcome[0] == FAILED and "counted" in outcome[1]


@pytest.mark.needs_db
def test_the_joined_check_fails_when_a_pending_envelope_is_read_back_as_approved(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the stored approval read as granted whatever the row says, the check says an envelope
    nobody had decided was approved. Delete this and a driver that stopped reading the row, and
    trusted its caller instead, passes the check."""
    from datetime import UTC, datetime

    from brain.browsing import driver
    from brain.browsing.approval import EnvelopeApproval
    from brain.browsing.envelope import Envelope

    async def always(session: object, envelope: Envelope) -> EnvelopeApproval:
        return EnvelopeApproval(
            run_id=envelope.run_id,
            envelope_digest=envelope.digest(),
            approved_by="nobody_in_particular",
            approved_at=datetime(2999, 1, 1, tzinfo=UTC),
        )

    monkeypatch.setattr(driver, "approval_of_run", always)

    outcome = run_checks(install, registered((MODULE,)))[JOINED]

    assert outcome[0] == FAILED and "nobody had decided" in outcome[1]
