"""The response type the application's test client returns, named once.

Starlette's test client imports `httpx2` in preference to `httpx` whenever `httpx2` is installed,
and `httpx2` arrived on 2026-09-15 as a requirement of `langsmith`, which the graph library's
core requires. The day it arrived, thirteen annotations reading `response: Response` with
`Response` imported from `httpx` became the wrong type in ten files at once, and only mypy said
so: every request still worked, because the two classes have the same shape.

So the type is named here and every test annotates against this name. A second transport switch
changes one line, and `tests/unit/test_http_client_fixture.py` asserts that this name is the
class the client actually returns, so the switch is found by a failing test rather than by a
type checker in CI. `httpx2` is declared as a development dependency for the same reason: a
test's transport should be a decision in `pyproject.toml`, not an accident of a transitive
requirement.
"""

from __future__ import annotations

from httpx2 import Response

__all__ = ["Response"]
