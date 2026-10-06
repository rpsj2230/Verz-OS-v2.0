"""A correction carrying the right answer, held, grouped and decided as a new version (M16.6.5,
M16.6.6, M16.7.6): the rules, without a database.

The database's half, the one write function, the policies and the apply, is
`brain.ops.acceptance_checks_corrections`, which drives the routes against PostgreSQL as their
readers; `tests/unit/test_acceptance_corrections.py` runs it on a real database and breaks it.

Task ids: M16.6.5, M16.6.6, M16.7.6
"""

from __future__ import annotations

import ast
import inspect
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from brain.core.entitlement import Capability
from brain.core.scope import Scope
from brain.knowledge import candidates
from brain.knowledge.candidates import (
    A_CORRECTION_IS_DECIDED_BY_WHOEVER_MAY_ADD_A_NEW_VERSION,
    CORRECTION_HEADING,
    NOBODY_WHOSE_CORRECTION_IT_HOLDS_MAY_APPROVE_IT,
    Candidate,
    CandidateError,
    CandidateState,
    Passage,
    audience,
    candidate_id_for,
    corrected_blocks,
    group_key,
    may_decide,
    version_id_for,
    words_key,
)
from brain.knowledge.item import ITEM_ID_PATTERN
from brain.knowledge.lifecycle import Authority, authority_for, successor_place
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD
from brain.knowledge.text_path import joined
from brain.knowledge.visibility import KnowledgeVisibility, Visibility
from brain.memory.turn import key_of
from tests.unit.test_knowledge_lifecycle import REGISTRY, reach, stored

#: Pinned far from any wall clock: nothing here is about the present.
AT = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
WORDS = "The handover takes five working days, not three."


def pending(*, proposers: frozenset[str] = frozenset({"u_corrector"})) -> Candidate:
    return Candidate(
        candidate_id=candidate_id_for("upload.v1", WORDS, at=AT),
        item_id="upload.v1",
        words=WORDS,
        raised_by="u_corrector",
        raised_at=AT,
        proposers=proposers,
    )


def authority(principal: str, *capabilities: Capability, department: str = "web") -> Authority:
    return authority_for(
        reach(principal, *((one, Scope.department(department)) for one in capabilities)),
        departments=REGISTRY,
        now=AT,
    )


# ------------------------------------------------------------------------------ the same fix


def test_the_same_fix_in_other_case_and_punctuation_is_one_group_and_a_different_one_is_not() -> (
    None
):
    """**M16.7.6.** Two corrections of one document to the same words, typed differently, share a
    group; other words or another document do not.

    Delete this and every correction is a candidate of its own, so a reviewer reads the same fix
    ten times and the ten instances never stand together as evidence."""
    same = group_key("upload.v1", "the handover takes FIVE working days, not three")
    assert same == group_key("upload.v1", WORDS)
    assert group_key("upload.v1", "six working days") != same
    assert group_key("upload.v2", WORDS) != same
    assert re.fullmatch(r"[0-9a-f]{64}", same)


def test_the_words_key_is_the_memory_statement_key_restated() -> None:
    """The key is restated rather than imported, to keep `brain.tables` off the answer lane, and is
    held equal to `brain.memory.turn.key_of` on real sentences.

    Delete this and the two keys can drift, so a fix grouped one way here is counted another way
    by the learning that reads memories."""
    for one in (WORDS, "I'd rather the figure first!", "", "Mixed CASE, punctuation; and 'quotes'"):
        assert words_key(one) == key_of(one)


def test_a_candidate_s_id_and_its_version_s_id_are_references_and_never_its_words() -> None:
    """Both ids are digests in the item id grammar, and neither carries a word the person typed.

    Delete this and a candidate's id, which reaches tasks and the ledger, can carry the words."""
    made = candidate_id_for("upload.v1", WORDS, at=AT)
    version = version_id_for(made, "upload.v1")
    for one in (made, version):
        assert re.fullmatch(ITEM_ID_PATTERN, one)
        assert "handover" not in one
    assert version == version_id_for(made, "upload.v1")


# ------------------------------------------------------------------------------ the decider


def test_the_steward_and_an_administrator_where_it_sits_may_decide_and_nobody_else() -> None:
    """**The positive case and its edges.** The document's steward who reads it, and somebody
    holding the upload grant over its department, may decide; a reader who does neither, and an
    administrator of another department, may not.

    Delete this and `may_decide` can admit everybody or nobody with the rest green."""
    item = stored()
    steward = authority("u_steward", KNOWLEDGE_READ)
    administrator = authority("u_admin", KNOWLEDGE_UPLOAD)
    reader = authority("u_reader", KNOWLEDGE_READ)
    elsewhere = authority("u_admin_b", KNOWLEDGE_UPLOAD, department="finance")

    assert may_decide(pending(), item, steward)
    assert may_decide(pending(), item, administrator)
    assert not may_decide(pending(), item, reader)
    assert not may_decide(pending(), item, elsewhere)


def test_the_decider_is_the_new_version_s_decider_called_and_not_restated() -> None:
    """`may_decide` asks `Authority.may_act`, the function `POST .../versions` asks, read from its
    source rather than its docstring. Delete this and a second rule about who may replace a
    document can be written here and drift from the lifecycle's."""
    tree = ast.parse(inspect.getsource(candidates.may_decide))
    calls = {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert "by.may_act" in calls
    assert "may_act" in A_CORRECTION_IS_DECIDED_BY_WHOEVER_MAY_ADD_A_NEW_VERSION


def test_nobody_whose_correction_it_holds_may_decide_it_even_as_its_steward() -> None:
    """**The four-eyes rule.** The steward, who may decide any candidate about their document, may
    not decide one holding their own correction; and a candidate naming such a decider is refused.

    Delete this and a person can correct an answer and approve their own words into a document."""
    item = stored()
    steward = authority("u_steward", KNOWLEDGE_READ)
    theirs = pending(proposers=frozenset({"u_corrector", "u_steward"}))

    assert not may_decide(theirs, item, steward)
    with pytest.raises(CandidateError, match="their word is what it already has"):
        Candidate(
            candidate_id=theirs.candidate_id,
            item_id="upload.v1",
            words=WORDS,
            raised_by="u_corrector",
            raised_at=AT,
            proposers=theirs.proposers,
            state=CandidateState.APPROVED,
            decided_by="u_steward",
            decided_at=AT,
            applied_item_id="corrected.x",
        )
    assert "may not approve it" in NOBODY_WHOSE_CORRECTION_IT_HOLDS_MAY_APPROVE_IT


def test_a_decided_candidate_and_one_about_another_document_are_not_decided_again() -> None:
    """A candidate already decided, and one whose document is not the one handed, are refused.

    Delete this and one candidate can be applied twice, or applied to another document."""
    item = stored()
    steward = authority("u_steward", KNOWLEDGE_READ)
    rejected = Candidate(
        candidate_id=pending().candidate_id,
        item_id="upload.v1",
        words=WORDS,
        raised_by="u_corrector",
        raised_at=AT,
        proposers=frozenset({"u_corrector"}),
        state=CandidateState.REJECTED,
        decided_by="u_admin",
        decided_at=AT,
        reason="already right",
    )
    assert not may_decide(rejected, item, steward)
    assert not may_decide(pending(), stored("upload.v2"), steward)


def test_a_decision_is_shaped_by_its_outcome() -> None:
    """An approved candidate names its version and no reason, a rejected one its reason and no
    version, a pending one neither. Delete this and a row can claim an apply that never happened."""
    base: dict[str, Any] = {
        "candidate_id": pending().candidate_id,
        "item_id": "upload.v1",
        "words": WORDS,
        "raised_by": "u_corrector",
        "raised_at": AT,
        "proposers": frozenset({"u_corrector"}),
        "decided_by": "u_admin",
        "decided_at": AT,
    }
    with pytest.raises(CandidateError, match="names the version"):
        Candidate(**base, state=CandidateState.APPROVED)
    with pytest.raises(CandidateError, match="keeps its reason"):
        Candidate(**base, state=CandidateState.REJECTED)
    with pytest.raises(CandidateError, match="among its evidence"):
        Candidate(
            **{**base, "proposers": frozenset({"u_other"})},
            state=CandidateState.REJECTED,
            reason="x",
        )
    assert Candidate(**base, state=CandidateState.APPROVED, applied_item_id="corrected.x")


# ------------------------------------------------------------------------------ the version


def test_who_will_read_the_words_is_said_in_plain_terms_for_the_new_version_s_place() -> None:
    """**Condition five.** The review says who reads the words once approved, for the place the new
    version goes, which for a company-wide document is its department until it is published again.

    Delete this and a reviewer approves words into a company-wide document without being told that
    everyone will read them."""
    web = KnowledgeVisibility.of_department("web", owner_id="u_steward")
    assert audience(web) == "Everyone in web will see these words."
    assert audience(KnowledgeVisibility.personal("u_steward")) == (
        "Only the document's own steward will see these words."
    )
    company = stored(
        visibility=KnowledgeVisibility(
            level=Visibility.COMPANY, department="web", owner_id="u_steward"
        )
    )
    assert audience(successor_place(company)) == "Everyone in web will see these words."


def test_the_new_version_keeps_every_passage_as_it_was_and_adds_the_correction_after_them() -> None:
    """**The apply.** Every passage of the old version is a block of the new one, in order and word
    for word, each at the offset `joined` finds it at, and the correction is the last block under
    its heading.

    Delete this and an approved correction can drop or reorder the document it corrects, or write
    blocks a citation span would resolve against the wrong words."""
    kept = (
        Passage(body="Site handover. Step one.", section="Steps", page=1),
        Passage(body=""),
        Passage(body="Step two, three days.", section="Steps", page=2),
    )
    blocks = corrected_blocks(kept, f"  {WORDS}  ")

    content = joined(blocks)
    assert [one.text for one in blocks[:-1]] == [
        "Site handover. Step one.",
        "Step two, three days.",
    ]
    assert [one.page for one in blocks[:-1]] == [1, 2]
    assert blocks[-1].text == f"{CORRECTION_HEADING}\n\n{WORDS}"
    assert blocks[-1].section == CORRECTION_HEADING
    assert content.endswith(WORDS)


# ------------------------------------------------------------------------------ who reads them

#: The only modules that may import the candidates' store or table: the routes that propose and
#: decide, the install check, and the table registry. Everything that answers a question is
#: outside it, so held words cannot reach an answer before they are a version of a document.
MAY_READ_CANDIDATES = frozenset(
    {
        "brain.candidate_routes",
        "brain.thread_routes",
        "brain.knowledge.candidate_store",
        "brain.ops.acceptance_checks_corrections",
        "brain.tables",
    }
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_held_words_are_read_by_the_routes_that_decide_them_and_by_nothing_that_answers() -> None:
    """**The words change nothing until approved.** Only the routes that propose and decide, the
    install check and the table registry import the candidates' store or table; no module on the
    answer path, the memory or the model lane does.

    Delete this and a module that answers questions can import the store and read words nobody has
    approved, with every other test green."""
    source = Path(__file__).resolve().parents[2] / "src"
    held = {"brain.knowledge.candidate_store", "brain.tables.learning_candidate"}
    readers = set()
    for path in (source / "brain").rglob("*.py"):
        module = ".".join(path.relative_to(source).with_suffix("").parts).removesuffix(".__init__")
        if module in held:
            continue
        if _imports(path) & held:
            readers.add(module)
    assert readers <= MAY_READ_CANDIDATES, readers - MAY_READ_CANDIDATES
    # The positive sibling: the walk finds the importers it should, so an empty walk cannot pass.
    assert {"brain.candidate_routes", "brain.thread_routes", "brain.tables"} <= readers
    assert (
        "nowhere else"
        in candidates.A_CORRECTION_S_WORDS_CHANGE_NOTHING_UNTIL_SOMEBODY_APPROVES_THEM
    )


# ------------------------------------------------------------------------------ the route


def _decided(body: Any) -> tuple[int, list[str]]:
    import asyncio
    import json
    from types import SimpleNamespace

    from fastapi.responses import JSONResponse

    from brain.candidate_routes import decide_correction

    asked: Any = SimpleNamespace(now=AT)
    # No request: a refusal of the body is made before anything is read, so nothing reaches it.
    answer = asyncio.run(decide_correction(None, asked, "correction.x", body))  # type: ignore[arg-type]
    assert isinstance(answer, JSONResponse)
    problems = json.loads(bytes(answer.body))["problems"]
    return answer.status_code, [one["field"] for one in problems]


def test_an_approval_needs_a_review_date_ahead_and_a_rejection_needs_its_reason() -> None:
    """The route refuses an approval with no review date or one already past, and a rejection with
    no reason or only spaces, each naming its field, before it reads anything.

    Delete this and an approval writes a version due for review the moment it exists, or a
    rejection keeps no reason, with the install check green because it always sends both."""
    from datetime import timedelta

    from brain.candidate_routes import CorrectionDecisionAsked

    assert _decided(CorrectionDecisionAsked(approve=True)) == (422, ["review_by"])
    assert _decided(CorrectionDecisionAsked(approve=True, review_by=AT)) == (422, ["review_by"])
    assert _decided(CorrectionDecisionAsked(approve=True, review_by=AT - timedelta(days=1))) == (
        422,
        ["review_by"],
    )
    assert _decided(CorrectionDecisionAsked(approve=False)) == (422, ["reason"])
    assert _decided(CorrectionDecisionAsked(approve=False, reason="   ")) == (422, ["reason"])
