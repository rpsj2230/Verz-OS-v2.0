"""The skill packages' install acceptance checks: registered, passing on a real schema, and each
failing with its own sentence when the property it proves is broken.

The pure half holds the checks to the suite and to the leaves they prove. The database half builds
PostgreSQL to head and runs the three checks as the worker would: each passes, and afterwards every
table any of them wrote to holds what it held before, which is
`brain.ops.acceptance.NOTHING_A_CHECK_WRITES_IS_EVER_COMMITTED` measured for the three tables `0164`
adds. Then each property is broken in the product, one at a time, and the check proving it fails
with the sentence written for that break: the byte comparison `plan_run` makes, the rehearsal gate
`decided` applies, and the manifest comparison `read_package` makes. A check that passed whatever
the product did would pass all three runs; these are the runs that say it would not.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M12.4.11, M12.3.4, M12.3.1
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from brain.console import skill_library
from brain.ops import acceptance_checks_skill_packages as packages
from brain.ops.acceptance import CHECK_MODULES, FAILED, PASSED, Check, registered
from brain.tools import run_skill
from tests.unit.test_acceptance import at_head, counts
from tests.unit.test_acceptance_skills import run_checks

MODULE = "brain.ops.acceptance_checks_skill_packages"

#: Each check and the one leaf it proves.
LEAVES = {
    "a_script_changed_after_approval_is_refused_before_it_runs": ("M12.4.11",),
    "a_version_with_examples_is_approved_only_once_rehearsed": ("M12.3.4",),
    "an_approved_skill_is_exported_and_a_changed_package_is_refused": ("M12.3.1",),
}

#: Every table the checks write to, which must hold afterwards what it held before.
WRITTEN_BY_PACKAGE_CHECKS = (
    "agent.skill",
    "agent.skill_review",
    "agent.skill_script",
    "agent.skill_example",
    "agent.skill_rehearsal",
    "obs.audit_entry",
)


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


def package_counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in WRITTEN_BY_PACKAGE_CHECKS
    }


# ------------------------------------------------------------------------ without a server
def test_the_package_checks_are_in_the_suite_in_order_and_prove_their_leaves() -> None:
    """The module is one the registry imports, and each check names the leaf it proves, in the
    order the page lists them. Delete this and the checks can fall out of the run with the Install
    page listing three fewer rows, or close a leaf they do not exercise."""
    assert MODULE in CHECK_MODULES
    assert [(one.name, one.leaves) for one in mine()] == list(LEAVES.items())


def test_the_script_and_examples_the_checks_write_are_ones_the_product_accepts() -> None:
    """The fixture held to the rules outside the check: the package the script check uploads
    reads with the script's sha256, and the examples it writes are within the bounds a skill may
    carry. Delete this and a check can fail on its own fixture and read as a product fault."""
    from brain.tools.skills import MAX_EXAMPLES, script_sha256

    package = packages._read("check.zip", packages._package_zip("acceptance_x_scripted"))
    assert package is not None
    recorded = package.skill.recorded(packages.SCRIPT_PATH)
    assert recorded is not None and recorded.sha256 == script_sha256(packages.SCRIPT)
    assert 0 < len(packages.EXAMPLES) <= MAX_EXAMPLES


# --------------------------------------------------------------------------- a real run
@pytest.mark.needs_db
def test_on_a_real_database_every_package_check_passes_and_leaves_nothing_behind() -> None:
    """**The three checks as the worker runs them, against PostgreSQL at head.** Each passes with
    no reason, and every table any of them wrote to holds afterwards exactly what it held before.
    Delete this and a check that cannot pass on the real schema, or one that commits a skill's
    script to a client's library, reaches the owner's server first."""
    with at_head("brain_acceptance_packages") as url:
        before = (counts(url), package_counts(url))
        outcomes = run_checks(url, mine())
        after = (counts(url), package_counts(url))

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


def _without_the_byte_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_skill, "verified_script", lambda skill, path, content: content)


def _without_the_rehearsal_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(skill_library, "awaits_rehearsal", lambda one, newest: False)


def _without_the_example_requirement(monkeypatch: pytest.MonkeyPatch) -> None:
    held = skill_library.approval_needs

    def lenient(one: Any, newest: Any) -> str | None:
        return None if not one.imported.skill.examples else held(one, newest)

    monkeypatch.setattr(skill_library, "approval_needs", lenient)


def _without_the_manifest_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    def trusting(raw: bytes, skill: Any, refuse: Any) -> str:
        return str(skill.digest())

    monkeypatch.setattr(skill_library, "_manifest_digest", trusting)


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("check", "breaks", "sentence"),
    [
        (
            "a_script_changed_after_approval_is_refused_before_it_runs",
            _without_the_byte_comparison,
            "a script whose bytes changed after approval was planned to run",
        ),
        (
            "a_version_with_examples_is_approved_only_once_rehearsed",
            _without_the_rehearsal_gate,
            "a version with example tasks was approved before it was rehearsed",
        ),
        (
            "a_version_with_examples_is_approved_only_once_rehearsed",
            _without_the_example_requirement,
            "a version with no example tasks was approved",
        ),
        (
            "an_approved_skill_is_exported_and_a_changed_package_is_refused",
            _without_the_manifest_comparison,
            "a package changed after it was exported was accepted",
        ),
    ],
)
def test_each_check_fails_with_its_own_sentence_when_its_property_is_broken(
    monkeypatch: pytest.MonkeyPatch,
    check: str,
    breaks: Callable[[pytest.MonkeyPatch], None],
    sentence: str,
) -> None:
    """The byte comparison `plan_run` makes, the example requirement and the rehearsal gate
    `decided` applies, and the manifest comparison `read_package` makes, each removed from the
    product in turn: the check proving it
    fails, with the sentence written for exactly that break. Delete this and a check can pass for
    a product that no longer has the property, which is a check that proves nothing."""
    [one] = [candidate for candidate in mine() if candidate.name == check]
    with at_head(f"brain_acceptance_packages_{check[:12]}_{breaks.__name__[-12:]}") as url:
        breaks(monkeypatch)
        outcomes = run_checks(url, (one,))

    assert outcomes[check] == (FAILED, sentence)
