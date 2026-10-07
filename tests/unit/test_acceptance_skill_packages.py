"""The install checks for skill packages, each passing on PostgreSQL at head and each failing with
the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: every check
passes and leaves nothing, the run rows and the skill, rehearsal, export and script rows included.
Then each is shown failing: an approval that does not wait for a rehearsal or that reads a rehearsal
in which one example failed, an export of a version nobody approved, a package whose changed text
is read as the version it claims to be, and a script whose bytes changed after approval handed to a
sandbox. The script check is also run as an install with the sandbox switched on runs it, where the
add route itself takes the package.

Not asked here, and said where a reader would look: what a version with no examples does
(needs-rupash 161, the owner's), and the landing of an exported package on a second install, which
`tests/unit/test_skill_export.py` builds a scratch database for.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M12.3.4, M12.3.1, M12.4.11
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, SENTENCE_CHARS, registered
from brain.ops.acceptance_checks_skill_packages import (
    CHANGED_SCRIPT,
    CHECK_ORDER,
    SCRIPT,
    SCRIPT_PATH,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_skill_packages"
REHEARSED = "a_version_with_examples_is_approved_only_once_rehearsed"
EXPORTED = "an_approved_skill_is_exported_and_a_changed_package_is_refused"
SCRIPTED = "a_script_changed_after_approval_is_refused_before_it_runs"

#: What these checks write beyond the suite's own list of tables.
ALSO_WRITTEN = ("agent.skill_script", "agent.skill_export", "agent.skill_rehearsal")


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_leaf_it_proves() -> None:
    """Three checks, each naming exactly the leaf it proves and no other. Delete this and a check
    can drift onto a leaf its sentence does not prove, or two checks can claim one leaf, and the
    leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (REHEARSED, ("M12.3.4",)),
        (EXPORTED, ("M12.3.1",)),
        (SCRIPTED, ("M12.4.11",)),
    ]


def test_the_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [REHEARSED, EXPORTED, SCRIPTED]


def test_the_module_stands_after_the_checks_that_build_what_it_asks_about() -> None:
    """The key is a number the Install page sorts by, and it must follow the skill library's own
    checks, whose helpers these use. Delete this and the page can list a package check above the
    library checks it depends on."""
    from brain.ops import acceptance_checks_skills

    assert CHECK_ORDER > acceptance_checks_skills.CHECK_ORDER


def test_every_sentence_fits_the_page_and_every_reason_fits_the_column() -> None:
    """The sentences the page shows and the reasons it stores, each within its own bound. Delete
    this and a sentence is cut short on the Install page or a reason is refused by the column."""
    import ast
    import inspect

    from brain.ops import acceptance_checks_skill_packages as module

    for one in registered((MODULE,)):
        assert 0 < len(one.sentence) <= SENTENCE_CHARS, one.name
    tree = ast.parse(inspect.getsource(module))
    reasons = [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CheckFailedError"
        and isinstance(node.args[0], ast.Constant)
    ]
    assert len(reasons) >= 30
    assert all(len(str(reason)) <= REASON_CHARS for reason in reasons)


def test_the_script_the_check_changes_differs_from_the_one_it_approves() -> None:
    """Held against the hash, so the refusal is asked of a different byte. Delete this and the
    'changed' script can be edited back to the approved one, and the check then passes a runner
    that refuses nothing."""
    assert hashlib.sha256(SCRIPT).hexdigest() != hashlib.sha256(CHANGED_SCRIPT).hexdigest()
    assert SCRIPT_PATH.startswith("scripts/") and SCRIPT_PATH.endswith(".py")


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_skill_packages") as url:
        yield url


def run_packages(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_every_package_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All three pass on an install with no sandbox and
    nothing a check wrote is left: no skill, review, rehearsal, export, script or ledger entry.
    Delete this and a check that can never pass on a real schema, or one leaving a skill in the
    library, reaches the owner's server."""
    before = _counts(install)
    outcomes = run_packages(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 3
    assert _counts(install) == before


@pytest.mark.needs_db
def test_the_script_check_passes_where_the_sandbox_is_switched_on_too(install: str) -> None:
    """Where `INSTALL_SERVICES` names the sandbox the add route takes the package itself, and the
    check goes through that door instead of the store. Delete this and the sandbox branch of the
    check is code no run ever executed, which would first fail on the owner's server."""
    from brain.install import hold_saved

    before = hold_saved({"INSTALL_SERVICES": "sandbox"})
    try:
        outcomes = run_packages(install, SCRIPTED)
    finally:
        hold_saved(before)
    assert outcomes == {SCRIPTED: (PASSED, "")}, outcomes


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_packages(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_an_approval_that_does_not_wait_for_a_rehearsal_fails_the_rehearsal_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The review route's rehearsal gate answering yes to anything. Delete this and M12.3.4 closes
    on a review that approves a version nobody rehearsed."""
    from brain import skill_routes

    monkeypatch.setattr(skill_routes, "rehearsal_clears", lambda *args: True)
    assert "before a rehearsal" in _failed(install, REHEARSED)


@pytest.mark.needs_db
def test_an_approval_that_reads_a_failed_rehearsal_as_a_pass_fails_the_rehearsal_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate asking only that some rehearsal exists. Delete this and M12.3.4 closes on a review
    that approves a version whose rehearsal failed an example."""
    from brain import skill_routes

    monkeypatch.setattr(
        skill_routes,
        "rehearsal_clears",
        lambda digest, examples, rehearsals: bool(examples) and any(True for _ in rehearsals),
    )
    assert "in which one failed" in _failed(install, REHEARSED)


@pytest.mark.needs_db
def test_a_rehearsal_that_ignores_what_the_agent_reaches_fails_the_rehearsal_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rehearsal passing every example whatever the agent can reach. Delete this and M12.3.4
    closes on a rehearsal that cannot fail, which clears every approval."""
    from brain import skill_routes
    from brain.tools.skill_examples import ExampleOutcome

    monkeypatch.setattr(
        skill_routes,
        "rehearse_reach",
        lambda examples, reachable: tuple(ExampleOutcome(one.task, True) for one in examples),
    )
    assert "cannot reach the tool" in _failed(install, REHEARSED)


@pytest.mark.needs_db
def test_an_export_of_a_version_nobody_approved_fails_the_export_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every stored version reading as approved and unchanged. Delete this and M12.3.1 closes on
    an export that hands out a draft nobody reviewed."""
    from brain.tools.skills import ImportedSkill

    monkeypatch.setattr(ImportedSkill, "is_executable", lambda self: True)
    assert "nobody approved was exported" in _failed(install, EXPORTED)


@pytest.mark.needs_db
def test_a_package_changed_after_export_and_read_as_the_version_it_claims_fails_the_export_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The import not comparing a package with the manifest it carries. Delete this and M12.3.1
    closes on an import that adds a changed package as the version it claims to be."""
    from brain.console import skill_library

    monkeypatch.setattr(skill_library, "_checked_against", lambda skill, said: skill)
    assert "text was changed after export was accepted" in _failed(install, EXPORTED)


@pytest.mark.needs_db
def test_a_runner_that_does_not_recheck_the_bytes_fails_the_script_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runner trusting the stored hash instead of recomputing it from the bytes. Delete this
    and M12.4.11 closes on a runner that hands a changed script to the sandbox."""
    from brain.ops import sandbox_client

    def trusting(spec: Any, files: Any) -> None:
        return None

    monkeypatch.setattr(sandbox_client, "verify_script_bytes", trusting)
    assert "was run" in _failed(install, SCRIPTED)
