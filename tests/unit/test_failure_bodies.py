"""Every failing response carries a sentence and a reference, whichever part of the application
produced it.

On 2026-09-17 the owner of a staging install saw "That did not work. Something went wrong." on
screen after screen, which is the console's fallback for a failure with no `message`. Three ways
out of the application skipped `brain.api.ErrorBody` (an exception nothing handled, a refused
request, an address or method nothing serves) and nine routes answered refusals with documents of
their own. Each is driven here through the real application, with a positive sibling proving the
ordinary answer is untouched.

Task ids: M27.9.6
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, field_validator

from brain.api import (
    API_PREFIX,
    KEPT_ERROR_KEYS,
    NOT_ACCEPTED,
    NOT_DONE_AS_THINGS_STAND,
    NOT_FOUND,
    NOT_THIS_VALUE,
    STATUS_SENTENCES,
    UNEXPECTED_FAILURE,
    NoEchoRoute,
    RequestProblemView,
    problem_field,
    problem_words,
)
from brain.app import Settings, create_app

#: A value a refused request carries, which no answer may repeat.
SENTINEL = "SENTINEL-4471-VALUE"


class Posted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=5)
    count: int = Field(ge=1)


class Checked(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def _shaped(cls, value: str) -> str:
        if not value.startswith("ok"):
            msg = f"a code starts with ok, and {value} does not"
            raise ValueError(msg)
        return value


def _routes() -> APIRouter:
    router = APIRouter(prefix=f"{API_PREFIX}/test-failures")

    @router.get("/raises")
    async def raises() -> dict[str, str]:
        msg = f"the database said duplicate key {SENTINEL}"
        raise RuntimeError(msg)

    @router.get("/answers")
    async def answers(hours: Annotated[int, Query(ge=1, le=24)] = 1) -> dict[str, int]:
        return {"hours": hours}

    @router.post("/posts")
    async def posts(body: Posted) -> dict[str, str]:
        return {"name": body.name}

    @router.post("/checks")
    async def checks(body: Checked) -> dict[str, str]:
        return {"code": body.code}

    @router.get("/document/{kind}")
    async def document(kind: str) -> JSONResponse:
        found: dict[str, tuple[int, Any]] = {
            "sentence": (409, {"sentence": "The last administrator keeps their link.", "o": 1}),
            "problems": (422, {"problems": [{"field": "a", "code": "b", "message": "c"}]}),
            "bare": (409, {"outcome": "not_bound"}),
            "worded": (409, {"message": "Already worded.", "trace_id": "kept-as-sent"}),
            "list": (400, [1, 2, 3]),
            "fine": (200, {"outcome": "bound"}),
        }
        status, content = found[kind]
        return JSONResponse(status_code=status, content=content)

    @router.get("/streams")
    async def streams() -> StreamingResponse:
        async def frames() -> AsyncIterator[bytes]:
            yield b"data: one\n\n"
            yield b"data: two\n\n"

        return StreamingResponse(frames(), media_type="text/event-stream")

    return router


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(_routes())
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def reference_of(answer: Any) -> str:
    """The body's trace id, which must be the header's, which the middleware minted."""
    body = answer.json()
    assert body["trace_id"], "a failure with no reference is one nobody can report"
    assert body["trace_id"] == answer.headers["x-trace-id"]
    return str(body["trace_id"])


# ------------------------------------------------------------- an exception nothing handled
def test_an_exception_nothing_handled_answers_a_sentence_and_the_reference_and_never_its_text(
    client: TestClient,
) -> None:
    """A 500 in `ErrorBody` with the id the log line carries, and nothing of the exception.

    Delete this and the plain-text `Internal Server Error` comes back, with no reference, which is
    what four staging screens showed; or the exception's message reaches the body, and a database
    refusal names the key it collided on."""
    answer = client.get(f"{API_PREFIX}/test-failures/raises")

    assert answer.status_code == 500
    assert answer.headers["content-type"].startswith("application/json")
    assert answer.json()["message"] == UNEXPECTED_FAILURE
    reference_of(answer)
    assert SENTINEL not in answer.text
    assert "RuntimeError" not in answer.text


def test_an_answer_that_did_not_fail_is_untouched(client: TestClient) -> None:
    """The sibling: an ordinary 200 and a stream pass through as they were written.

    Delete this and the shaping can start holding or rewriting every answer, which would buffer the
    answer lane's event stream until it ends."""
    answer = client.get(f"{API_PREFIX}/test-failures/answers", params={"hours": 3})
    stream = client.get(f"{API_PREFIX}/test-failures/streams")
    fine = client.get(f"{API_PREFIX}/test-failures/document/fine")

    assert (answer.status_code, answer.json()) == (200, {"hours": 3})
    assert stream.status_code == 200
    assert stream.text == "data: one\n\ndata: two\n\n"
    assert (fine.status_code, fine.json()) == (200, {"outcome": "bound"})


# ------------------------------------------------------------------ a refused request
def test_a_refused_body_is_answered_with_its_problems_in_words_and_never_the_value(
    client: TestClient,
) -> None:
    """Each field named as a form names it, each problem in words built from its limit, and no
    part of what was sent in the answer.

    Delete this and FastAPI's `{"detail": [...]}` comes back, which quotes the refused value and
    carries no message, so the console could neither say what was wrong nor mark the field."""
    answer = client.post(
        f"{API_PREFIX}/test-failures/posts",
        json={"name": SENTINEL, "count": 0, "colour": SENTINEL},
    )

    assert answer.status_code == 422
    assert answer.json()["message"] == NOT_ACCEPTED
    reference_of(answer)
    assert SENTINEL not in answer.text
    problems = {one["field"]: one for one in answer.json()["problems"]}
    assert problems["name"]["message"] == "This should be at most 5 characters."
    assert problems["name"]["code"] == "string_too_long"
    assert problems["count"]["message"] == "This should be at least 1."
    assert problems["colour"]["code"] == "extra_forbidden"
    assert all(set(one) == set(KEPT_ERROR_KEYS) for one in answer.json()["problems"])


def test_a_body_that_is_accepted_is_answered_by_the_route(client: TestClient) -> None:
    """The sibling. Delete this and a refusal of everything passes the test above."""
    answer = client.post(f"{API_PREFIX}/test-failures/posts", json={"name": "abc", "count": 2})

    assert (answer.status_code, answer.json()) == (200, {"name": "abc"})


def test_a_query_parameter_is_named_as_its_field_and_unparsable_json_as_the_whole_request(
    client: TestClient,
) -> None:
    """`hours` rather than `query.hours`, and `""` for JSON that does not parse, which FastAPI
    locates at a character offset. Delete this and a form is handed a field name no input has."""
    query = client.get(f"{API_PREFIX}/test-failures/answers", params={"hours": 99})
    broken = client.post(
        f"{API_PREFIX}/test-failures/posts",
        content=b'{"name": ',
        headers={"content-type": "application/json"},
    )

    assert query.status_code == broken.status_code == 422
    assert [(one["field"], one["message"]) for one in query.json()["problems"]] == [
        ("hours", "This should be at most 24.")
    ]
    assert [one["field"] for one in broken.json()["problems"]] == [""]


def test_a_validators_own_sentence_is_kept_only_when_it_does_not_quote_the_input(
    client: TestClient,
) -> None:
    """A validator wrote "a code starts with ok, and <value> does not", which quotes, so the
    answer falls back to the neutral sentence; one that quotes nothing is shown as written.

    Delete this and every custom validator in the application becomes a way to echo a secret."""
    quoting = client.post(f"{API_PREFIX}/test-failures/checks", json={"code": SENTINEL})

    assert quoting.status_code == 422
    assert SENTINEL not in quoting.text
    assert quoting.json()["problems"][0]["message"] == NOT_THIS_VALUE
    assert (
        problem_words(
            {"type": "value_error", "msg": "Value error, pick a shorter one", "input": "x" * 9}
        )
        == "pick a shorter one"
    )
    assert problem_words({"type": "too_long", "ctx": {"max_length": 2, "actual_length": 7}}) == (
        "This should have at most 2 entries."
    )
    assert problem_words({"type": "something_new", "input": SENTINEL}) == NOT_THIS_VALUE
    assert problem_field(("body", "rungs", 0, "attempts"), "int_parsing") == "rungs.0.attempts"
    assert tuple(RequestProblemView.model_fields) == KEPT_ERROR_KEYS


def test_a_route_built_on_no_echo_route_answers_the_same_shape_on_an_application_of_its_own() -> (
    None
):
    """The routers that take a secret do not depend on `brain.app` having installed the handler.

    Delete this and a secret-taking router mounted on another application, or in a test, repeats
    the key it refused."""
    router = APIRouter(route_class=NoEchoRoute)

    @router.post("/secret")
    async def secret(body: Posted) -> dict[str, str]:
        return {"name": body.name}

    bare = FastAPI()
    bare.include_router(router)
    with TestClient(bare) as c:
        refused = c.post("/secret", json={"name": SENTINEL, "count": 1})
        accepted = c.post("/secret", json={"name": "abc", "count": 1})

    assert refused.status_code == 422
    assert SENTINEL not in refused.text
    assert refused.json()["message"] == NOT_ACCEPTED
    assert [one["field"] for one in refused.json()["problems"]] == ["name"]
    assert accepted.status_code == 200


# ------------------------------------------------------- an address or a method nothing serves
def test_a_wrong_method_and_an_address_nothing_serves_are_answered_in_words(
    client: TestClient,
) -> None:
    """A 405 keeps its `Allow` header, and an API address nothing serves says what a refused
    record says, so the two are one answer.

    Delete this and both come back as `{"detail": ...}`, which the console shows as something
    having gone wrong."""
    method = client.post(f"{API_PREFIX}/test-failures/answers")
    nowhere = client.get(f"{API_PREFIX}/test-failures/nothing-is-here")

    assert method.status_code == 405
    assert method.json()["message"] == STATUS_SENTENCES[405]
    assert "GET" in method.headers["allow"]
    reference_of(method)
    assert nowhere.status_code == 404
    assert nowhere.json()["message"] == NOT_FOUND
    assert set(nowhere.json()) == {"message", "trace_id"}
    reference_of(nowhere)


# ------------------------------------------------------- a document a route wrote for itself
def test_a_document_a_route_wrote_gains_a_sentence_and_the_reference_and_keeps_its_fields(
    client: TestClient,
) -> None:
    """Its own `sentence` becomes the message; a problems document gets the refused-request
    sentence; one naming neither gets its status's; a document already worded keeps its words and
    its reference; a body that is not an object is replaced, because what it holds is not known.

    Delete this and the nine routes that answer refusals with documents of their own go back to
    reaching the console with nothing to show and no reference to quote."""
    sentence = client.get(f"{API_PREFIX}/test-failures/document/sentence")
    problems = client.get(f"{API_PREFIX}/test-failures/document/problems")
    bare = client.get(f"{API_PREFIX}/test-failures/document/bare")
    worded = client.get(f"{API_PREFIX}/test-failures/document/worded")
    listed = client.get(f"{API_PREFIX}/test-failures/document/list")

    assert sentence.json()["message"] == "The last administrator keeps their link."
    assert sentence.json()["o"] == 1
    reference_of(sentence)
    assert problems.json()["message"] == NOT_ACCEPTED
    assert problems.json()["problems"] == [{"field": "a", "code": "b", "message": "c"}]
    assert bare.json() == {
        "outcome": "not_bound",
        "message": NOT_DONE_AS_THINGS_STAND,
        "trace_id": reference_of(bare),
    }
    assert worded.json() == {"message": "Already worded.", "trace_id": "kept-as-sent"}
    assert listed.status_code == 400
    assert listed.json()["message"] == STATUS_SENTENCES[400]
    assert set(listed.json()) == {"message", "trace_id"}
    assert int(sentence.headers["content-length"]) == len(sentence.content)
