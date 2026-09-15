"""The response type the tests annotate is the one the test client returns.

No task ids: this guards the test suite's own types, not a leaf.
"""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from tests.fixtures.http_client import Response


def test_the_response_type_the_tests_annotate_is_the_one_the_test_client_returns() -> None:
    """Starlette picks its transport library by what is installed, so the class a request
    returns can change with a dependency nobody added on purpose. Asserted on a real request
    rather than on an import, because the import would agree with itself.

    Delete this and the next transport switch is found by mypy in CI, after the push, in ten
    files at once, which is how the last one was found."""

    async def hello(_: Request) -> PlainTextResponse:
        return PlainTextResponse("hello")

    with TestClient(Starlette(routes=[Route("/", hello)])) as client:
        response = client.get("/")

    assert isinstance(response, Response)
    assert response.text == "hello"
