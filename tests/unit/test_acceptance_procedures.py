"""The written-procedure import's install acceptance check: in the suite, passing, and breakable.

The pure half holds the check to the suite and to its leaf, and reads the two files it builds
through the product's reader with no database, so a failure of the files themselves is told apart
from a failure of the store. The database half builds PostgreSQL to head and runs the check as the
worker does: it passes with no reason, and every table it wrote to holds afterwards what it held
before. Then two breaks, each run through the same harness: the reviewer's findings read as
nothing, and a typed step number no longer read as one. Each fails the check with its own sentence,
which is what makes a pass of it evidence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M12.2.10, M38.5.1
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from brain.console import skill_library
from brain.console.skill_library import added, procedure_package, read_procedure_file
from brain.ops import acceptance_checks_procedures as procedures
from brain.ops.acceptance import CHECK_MODULES, FAILED, PASSED, Check, registered
from brain.tools import sop_files
from brain.tools.sop_files import MAX_PROCEDURE_BYTES
from brain.tools.sop_import import Concern
from tests.fixtures.scratch_postgres import sql
from tests.unit.test_acceptance import at_head, counts
from tests.unit.test_acceptance_skills import run_checks, skill_counts

NAME = "a_written_procedure_lands_as_a_draft_skill_with_its_findings"

#: Far outside any plausible wall clock: nothing here is about the present.
AT = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


def mine() -> tuple[Check, ...]:
    return tuple(one for one in registered() if one.name == NAME)


# ------------------------------------------------------------------------ without a server
def test_the_procedure_check_is_in_the_suite_and_proves_the_procedure_import_leaf() -> None:
    """The module is one the registry imports and its one check names M12.2.10. Delete this and
    the check can fall out of the run with the Install page listing one fewer row, or prove a
    leaf it does not exercise."""
    assert "brain.ops.acceptance_checks_procedures" in CHECK_MODULES
    assert [(one.name, one.leaves) for one in mine()] == [(NAME, ("M12.2.10",))]


@pytest.mark.parametrize(
    ("file_name", "build", "steps", "injection"),
    [
        (
            "Acceptance run Word procedure.docx",
            procedures.a_word_procedure,
            procedures.WORD_STEPS,
            procedures.WORD_INJECTION,
        ),
        (
            "Acceptance run Confluence procedure.html",
            procedures.a_confluence_page,
            procedures.PAGE_STEPS,
            procedures.PAGE_INJECTION,
        ),
    ],
    ids=["word", "confluence"],
)
def test_each_file_the_check_builds_reads_as_its_steps_in_order_with_the_injected_line_found(
    file_name: str, build: Callable[[str], bytes], steps: tuple[str, ...], injection: str
) -> None:
    """The files as the product reads them, with no store: the steps numbered in the document's
    order, the line addressed to a model a finding on the draft, and no tool on the skill. Delete
    this and a database run that fails leaves open whether the file or the store was wrong."""
    title = file_name.rsplit(".", 1)[0]
    procedure = read_procedure_file(file_name, build(title))
    one = added(procedure_package(procedure, ()), by="acceptance.x.a.procedures", at=AT)

    assert procedures.steps_in(one.imported.skill.body) == [
        f"{place}. {step}" for place, step in enumerate(steps, start=1)
    ]
    addressed = [
        found
        for found in skill_library.procedure_findings(one)
        if found.concern is Concern.ADDRESSED_TO_THE_SYSTEM
    ]
    assert len(addressed) == 1 and injection in addressed[0].excerpt
    assert one.imported.skill.tools == ()


def test_the_file_past_the_bound_is_a_word_document_refused_for_its_size() -> None:
    """The padded file is still a Word document, and the refusal names the bound. Delete this and
    the check's size refusal could be a refusal for something else, passing while the bound does
    nothing."""
    word = procedures.a_word_procedure("Acceptance run Word procedure")
    padded = procedures.past_the_bound(word, MAX_PROCEDURE_BYTES)

    assert len(padded) > MAX_PROCEDURE_BYTES
    assert procedures._refused("big.docx", word) is None
    refused = procedures._refused("big.docx", padded)
    assert refused is not None and str(MAX_PROCEDURE_BYTES) in refused
    assert re.search(r"over the \d+ a procedure may be", refused)


# ---------------------------------------------------------------------------- a real run
@pytest.mark.needs_db
def test_on_a_real_database_the_procedure_check_passes_and_leaves_nothing_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes with no reason,
    and every table it wrote to, the skill library's and the ledger's among them, holds afterwards
    exactly what it held before. Delete this and a check that cannot pass on the real schema, or
    one that commits a procedure to a client's library, reaches the owner's server first."""
    with at_head("brain_acceptance_procedures") as url:
        before = (counts(url), skill_counts(url))
        outcomes = run_checks(url, mine())
        after = (counts(url), skill_counts(url))
        # The one statement is this test's own text, never input.
        kept = sql(url, "SELECT count(*) FROM agent.skill WHERE name LIKE 'acceptance-%'")

    assert outcomes == {NAME: (PASSED, "")}
    assert after == before
    assert int(kept[0][0]) == 0


def _nothing(_one: object) -> tuple[()]:
    return ()


@pytest.mark.needs_db
def test_the_check_fails_with_its_own_sentence_when_the_reviewer_is_shown_nothing_or_a_step_is_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two breaks, each run as the worker runs the check. Findings read as nothing fail it on the
    reviewer's sentence; a typed `3)` no longer read as a step fails it on the order's sentence.
    Delete this and the check can pass over a Skills screen that shows the reviewer nothing, or an
    importer that numbers a messy document's steps wrongly."""
    with at_head("brain_acceptance_procedures_broken") as url:
        with monkeypatch.context() as broken:
            broken.setattr(skill_library, "procedure_findings", _nothing)
            unseen = run_checks(url, mine())
        with monkeypatch.context() as broken:
            broken.setattr(sop_files, "TYPED_STEP_RE", re.compile(r"(?!)"))
            unnumbered = run_checks(url, mine())

    assert unseen == {
        NAME: (FAILED, "a line addressed to an AI was not a finding for the reviewer")
    }
    assert unnumbered == {
        NAME: (FAILED, "a procedure's steps were not kept in the document's order")
    }
