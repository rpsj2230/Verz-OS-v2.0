"""Every question about who can reach something is asked of a role or a capability over a scope, and
the one that names a record opens only for a reader who can already see it.

`docs/admin-console-architecture.md` 4.4 says the reverse question, "who can reach X and why", is
asked of a capability and a scope and never of a single record, because the answer to "who can see
this invoice" confirms the invoice exists to whoever asked. On 2026-09-18 the owner decided one
record access view (`brain.record_access_routes`), on one condition: it opens only for somebody who
can already see the record. M27.15.62's text still says no route may answer who can see a named
record, and `docs/needs-rupash.md` item 188 asks the owner whether to narrow it to what is built.
**Nothing here decides that.** This file holds the half that is true under either answer, and says
so in each place it matters: every who-can-reach question the API offers is *declared* with what it
is asked of, a route that starts to answer one without being declared fails, and the one question
that names a record is held to the owner's own condition by the order of its source.

**The set is found, not remembered.** `reach_questions_in` reads the application's own OpenAPI
document, as `tests/unit/test_money_figures.py` reads it for currencies, and matches the words a
route uses when it answers such a question: its path, its summary and the first paragraph of its
description. A list of the routes somebody remembered would be the place the next one is forgotten.
The matches that are not reach questions are written down with the reason each is not one, so a new
match is a decision a person made rather than a line a test skipped.

Task ids: M27.15.62
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Final

import pytest

from brain.record_access_routes import RecordAudience

#: The words a route uses when it answers who can see, hold, read or reach something.
REACH_WORDS: Final = re.compile(
    r"who (?:can|may) (?:see|reach|read|open|use|hold|view)|who (?:holds|has|reads|sees)"
    r"|\bholders?\b|\bwho can\b|\baudience of\b",
    re.IGNORECASE,
)

#: A list's own controls: the only parameters a reach question may take besides its subject.
LIST_CONTROLS: Final = frozenset({"limit", "cursor", "q", "filter", "sort"})

#: What a declared reach question is asked of.
ROLE_OVER_A_SCOPE: Final = "a role, over the scope each grant carries"
PEOPLE_AT_THE_READER_S_REACH: Final = "people, narrowed to where the reader may see them"
THE_CALLER_S_OWN_RECORD: Final = "the caller's own record, answered to the caller"
A_RECORD_FOR_ITS_OWN_READER: Final = "one record, answered only to a reader who can already see it"

#: Every route that answers who can reach something, with what it is asked of. Keyed `METHOD path`.
REACH_QUESTIONS: Final[Mapping[str, str]] = {
    "GET /api/v1/govern/roles/holders": ROLE_OVER_A_SCOPE,
    "GET /api/v1/govern/roles/group-rules": ROLE_OVER_A_SCOPE,
    "GET /api/v1/govern/roles/misconfigurations": ROLE_OVER_A_SCOPE,
    "GET /api/v1/govern/people": PEOPLE_AT_THE_READER_S_REACH,
    "GET /api/v1/me/reads": THE_CALLER_S_OWN_RECORD,
    "GET /api/v1/records/{entity}/access": A_RECORD_FOR_ITS_OWN_READER,
}

#: Routes the words match that do not answer a reach question, each with why.
NOT_A_REACH_QUESTION: Final[Mapping[str, str]] = {
    "POST /api/v1/govern/directory/{principal_id}/work-email": (
        "Binds a work email to a person who has none; 'who has' describes the person it is for."
    ),
    "GET /api/v1/help/runbooks/{key}": (
        "One screen's runbook, to a reader who may open that screen. The key names a screen, "
        "not a record."
    ),
    "GET /api/v1/knowledge/items/{item_id}": (
        "Reads the one document, for a reader who may see it, and answers nobody about who "
        "else may."
    ),
    "POST /api/v1/knowledge/items/{item_id}/steward": (
        "Hands a document to a steward who can reach it. It writes a steward and lists nobody."
    ),
    "GET /api/v1/operate/models": (
        "The models screen's figures; 'who may see' describes its gate."
    ),
    "GET /api/v1/operations/interrupted": (
        "The interrupted side effects; 'who may see' describes its gate."
    ),
    "GET /api/v1/govern/sign-ins": (
        "The people who can sign in and since when; no grant or reach is listed."
    ),
    "GET /api/v1/sign-in/status": (
        "Whether this token's account is linked, and who can link it; no reach is listed."
    ),
}

RECORD_VIEW: Final = "GET /api/v1/records/{entity}/access"
SOURCE: Final = Path(__file__).resolve().parents[2] / "src" / "brain" / "record_access_routes.py"


def _operations(spec: Mapping[str, Any]) -> Iterator[tuple[str, Mapping[str, Any]]]:
    for path, operations in spec.get("paths", {}).items():
        for method, operation in operations.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                yield f"{method.upper()} {path}", operation


def _words_of(key: str, operation: Mapping[str, Any]) -> str:
    """The path, the summary and the first paragraph of the description."""
    first = re.split(r"\n\s*\n", str(operation.get("description") or ""))[0]
    return " ".join([key.split(" ", 1)[1], str(operation.get("summary") or ""), first])


def reach_questions_in(spec: Mapping[str, Any]) -> frozenset[str]:
    """Every operation whose words say it answers who can see, hold, read or reach something."""
    return frozenset(
        key for key, operation in _operations(spec) if REACH_WORDS.search(_words_of(key, operation))
    )


def parameters_of(spec: Mapping[str, Any], key: str) -> frozenset[str]:
    """The parameter names one operation takes, in the path and in the query."""
    for found, operation in _operations(spec):
        if found == key:
            return frozenset(str(one["name"]) for one in operation.get("parameters", []))
    raise KeyError(key)


def takes_a_subject(spec: Mapping[str, Any], key: str) -> frozenset[str]:
    """The parameters that are not a list's own controls: what the question is asked of."""
    return parameters_of(spec, key) - LIST_CONTROLS


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    from brain.app import create_app

    return create_app().openapi()


def test_every_route_that_answers_who_can_reach_something_is_declared(spec: dict[str, Any]) -> None:
    """The API's own document is searched, and what it finds is exactly what is written down.

    Delete this and a new route answering "who can see this invoice" arrives with the suite green,
    because nothing compared the routes to what was declared.
    """
    found = reach_questions_in(spec)
    declared = set(REACH_QUESTIONS) | set(NOT_A_REACH_QUESTION)
    assert found - declared == frozenset(), (
        f"answers who can reach, and is not declared: {sorted(found - declared)}"
    )
    assert declared - found == frozenset(), (
        f"declared, and no longer found: {sorted(declared - found)}"
    )
    assert not set(REACH_QUESTIONS) & set(NOT_A_REACH_QUESTION)


def test_only_the_record_access_view_is_asked_of_anything_but_a_role_or_the_readers_own_reach(
    spec: dict[str, Any],
) -> None:
    """A reach question takes a list's controls and nothing that names a thing, but the record view.

    Delete this and a route `GET /documents/{document_id}/readers` is declared as a role question
    and takes a document's identifier, which is the route this whole rule exists to refuse.
    """
    for key in REACH_QUESTIONS:
        if key == RECORD_VIEW:
            assert takes_a_subject(spec, key) == {"entity"}
        else:
            assert takes_a_subject(spec, key) == frozenset(), (
                f"{key} is asked of {sorted(takes_a_subject(spec, key))}"
            )
    subjects = {key: REACH_QUESTIONS[key] for key in REACH_QUESTIONS if "{" in key}
    assert subjects == {RECORD_VIEW: A_RECORD_FOR_ITS_OWN_READER}


def test_the_one_view_that_names_a_record_says_nobody_was_left_out_and_no_count(
    spec: dict[str, Any],
) -> None:
    """The answer lists people and says whether the candidate load came back full. Nothing else.

    Delete this and a `hidden`, `total` or `others` field is added to say how many people the reader
    may not be told about, which is the count of hidden things the whole product refuses.
    """
    assert set(RecordAudience.model_fields) == {"people", "truncated"}
    schema = spec["components"]["schemas"]["RecordAudience"]
    assert set(schema["properties"]) == {"people", "truncated"}


def _record_access_calls() -> list[tuple[str, int]]:
    """Each call inside `record_access`, with its line, in source order."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "record_access"
    )
    calls: list[tuple[str, int]] = []
    for node in ast.walk(handler):
        if isinstance(node, ast.Call):
            name = (
                node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            )
            calls.append((name, node.lineno))
    return sorted(calls, key=lambda one: one[1])


def _line_of(name: str) -> int:
    return min(line for call, line in _record_access_calls() if call == name)


def test_the_record_view_looks_at_the_record_as_the_reader_before_it_lists_anybody() -> None:
    """The People read, then the record at the caller's own reach, then the candidates.

    This is the owner's 2026-09-18 condition as the shape of the source: a reader who cannot see
    the record is refused before any candidate is read. Delete this and the order is reversed in a
    refactor, so the candidates are read first and a refusal arrives after the database has
    answered, which is a timing difference between a record that exists and one that does not.
    """
    assert _line_of("permitted") < _line_of("_rows_seen") < _line_of("live_people")


def test_every_refusal_in_the_record_view_is_the_one_sentence_an_unknown_entity_gets() -> None:
    """DENIED and ABSENT are one answer: each `raise` is `_not_answerable` or a failure.

    Delete this and a refusal is written as `Denied("you may not see this record")`, which says that
    the record exists to anybody who is told it.
    """
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "record_access"
    )
    raised: list[str] = []
    for node in ast.walk(handler):
        if (
            isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
        ):
            raised.append(node.exc.func.id)
    assert raised, "the view refuses nobody, so the reading is wrong"
    assert set(raised) <= {"_not_answerable", "Failed"}
    assert raised.count("_not_answerable") >= 3


def _synthetic(**operations: dict[str, Any]) -> dict[str, Any]:
    return {"paths": {path: {"get": operation} for path, operation in operations.items()}}


def test_the_reading_finds_a_route_that_answers_who_can_see_and_leaves_a_plain_one() -> None:
    """The positive case beside the refusal, driven from a document written here.

    Delete this and `reach_questions_in` is replaced by a function that finds nothing, and the first
    test above passes over an empty set.
    """
    spec = _synthetic(
        **{
            "/invoices/{invoice_id}/readers": {
                "summary": "Who can see this invoice",
                "responses": {},
            },
            "/agents": {
                "summary": "The agents",
                "description": "One page of the agents.",
                "responses": {},
            },
            "/capabilities/{name}/holders": {"summary": "Holders of a capability", "responses": {}},
        }
    )
    assert reach_questions_in(spec) == {
        "GET /invoices/{invoice_id}/readers",
        "GET /capabilities/{name}/holders",
    }


def test_a_reach_question_that_takes_a_record_identifier_is_seen_as_asked_of_it() -> None:
    """`takes_a_subject` reports the identifier, and a list's own controls are not one.

    Delete this and the second test above is satisfied by a helper that reports no subject for any
    route, which is the route that names a record passing as a role question.
    """
    spec = _synthetic(
        **{
            "/invoices/{invoice_id}/readers": {
                "summary": "Who can see this invoice",
                "parameters": [
                    {"name": "invoice_id", "in": "path"},
                    {"name": "limit", "in": "query"},
                ],
                "responses": {},
            }
        }
    )
    assert takes_a_subject(spec, "GET /invoices/{invoice_id}/readers") == {"invoice_id"}
