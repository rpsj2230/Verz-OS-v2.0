"""The connectors screen over HTTP: who may open it, and what it says when it cannot look.

Driven through the real application, with the token machinery, the identity directory and the key
source imported from `tests/unit/test_api_routes.py` rather than rebuilt, for that file's reason:
a second copy of a JWS builder is a second place a token can be minted subtly differently, and it
fails looking like a permission bug.

**Every refusal has a sibling that reads**, and on this screen the sibling matters more than
usual: a route that refused everybody would pass every disclosure test in this file while
answering nothing to anybody, and the screen it produces looks exactly like an install that reads
no outside system.

**The unread case is tested both ways.** Nothing in this repository attaches an
`installed_connectors` reader, so the sentence is what every install gets today; the fixture that
attaches one is what proves the route is not simply hard-coded to answer a sentence, and the one
that does not is what proves it does not answer an empty list instead.

**No credential reaches a response or a log line, and that is asserted over the whole body and
over everything the run logged rather than over a named field.** A test naming the field would go
green the moment somebody added a different one.

Task ids: M42.6.5
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Final, cast

import pytest
import structlog
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.connector_routes import (
    CONNECTORS_READ,
    ConnectorsView,
    installed_connectors_of,
)
from brain.connectors.contract import ConnectorHealth, HealthState
from brain.connectors.registry import INSTALL_AUTHORITY, ConnectorState
from brain.console.connector_trust import (
    CONNECTING_IS_NOT_DONE_FROM_A_BROWSER_TODAY,
    NOTHING_HERE_COUNTS_TODAYS_CALLS,
    NOTHING_HERE_HOLDS_A_CONNECTOR_REGISTRY,
)
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)
from tests.unit.test_connector_trust import a_manifest, a_registered

CONNECTORS_PATH: Final = f"{API_PREFIX}/connectors"

#: The vault path the fixture manifest is bound to. Read off the manifest rather than typed, so
#: the assertion that it never leaves the process cannot pass by comparing against a string the
#: manifest stopped using.
BOUND_PATH: Final[str] = a_manifest().credential.ref.path

WHOLE: Final = Scope.unrestricted()
ONE_SOURCE: Final = Scope(clauses=(Clause(field="connector", op=Op.EQ, value="laravel"),))

#: The plane grant this screen needs beside its own capability. `brain.console.reads.permitted`
#: asks for both, and the route calls that function rather than checking the capability alone.
THE_CONSOLE_PLANE: Final[Grant] = Grant(capability=plane_capability(Plane.CONTENT), scope=WHOLE)

#: An `amr` a Keycloak session carries when a second factor was used.
SECOND_FACTOR: Final[Mapping[str, object]] = {"amr": ["otp"]}

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
LONG_AGO: Final = datetime(2019, 1, 1, tzinfo=UTC)


def _grant(capability: Capability, scope: Scope) -> Grant:
    return Grant(capability=capability, scope=scope)


#: What each of `test_api_routes`' people holds. One of them holds the install authority and no
#: read, which is the pair that proves `may_connect` is answered about the reader's own grant and
#: decides nothing about what the list contains.
CONNECTOR_GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_none": (THE_CONSOLE_PLANE,),
    "u_narrow": (THE_CONSOLE_PLANE, _grant(CONNECTORS_READ, ONE_SOURCE)),
    "u_prefix": (THE_CONSOLE_PLANE, _grant(INSTALL_AUTHORITY, WHOLE)),
    "u_wide": (THE_CONSOLE_PLANE, _grant(CONNECTORS_READ, WHOLE)),
    "u_admin": (
        THE_CONSOLE_PLANE,
        _grant(CONNECTORS_READ, WHOLE),
        _grant(INSTALL_AUTHORITY, WHOLE),
    ),
    "u_elsewhere": (_grant(CONNECTORS_READ, WHOLE),),
}


class ConnectorStore:
    """A `brain.gate.resolve.EntitlementStore` over `CONNECTOR_GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=CONNECTOR_GRANTS[principal_id])


def _wiring() -> Any:
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    return GateWiring(
        authority=TokenAuthority(
            issuer="https://id.verz.example/realms/brain",
            audience="brain-api",
            keys=Keys(),
            verify=verifier,
            directory=Directory(),
        ),
        versions=Versions(),
        store=ConnectorStore(),
        cache=NoCache(),
    )


def _app() -> FastAPI:
    """The real application, built the way a deployment builds it.

    `create_app` produces the router registration as well as the routes: a test mounting the
    router itself would prove the route works and not that it is served, which is the failure
    this repository keeps finding.
    """
    return create_app(Settings(env="development"))


@pytest.fixture
def client() -> Iterator[TestClient]:
    """An install with no connector registry, which is every install today."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        yield c


@pytest.fixture
def wired() -> Iterator[TestClient]:
    """An install whose process holds a registry, so the list half can be exercised at all."""
    app = _app()
    registry = (
        a_registered("laravel"),
        a_registered("freshdesk", ConnectorState.QUARANTINED),
    )
    probes = {
        "laravel": ConnectorHealth(connector="laravel", state=HealthState.OK, checked_at=LONG_AGO)
    }
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.installed_connectors = lambda: (registry, probes)
        yield c


def get(c: TestClient, pid: str) -> Response:
    token = token_for(pid, claims=SECOND_FACTOR)
    response: Response = c.get(CONNECTORS_PATH, headers={"authorization": f"Bearer {token}"})
    return response


# --- what a caller holding the capability is answered -------------------------------------------


def test_a_reader_is_told_which_sources_are_installed_and_what_each_may_read(
    wired: TestClient,
) -> None:
    """The positive case, and the sibling of every refusal below.

    Asserted by naming a source and reading its fields rather than by counting the list, because
    a count would go red the day the fixture grows a third connector for a reason nobody cares
    about, and because the whole point of the screen is what is said about one row.

    Delete this and the refusals are satisfied by a route that refuses everybody, which renders
    as an install that reads no outside system at all."""
    body = get(wired, "u_wide").json()

    by_name = {one["name"]: one for one in body["connectors"]}
    assert set(by_name) == {"laravel", "freshdesk"}
    assert by_name["laravel"]["wiring"] == "database"
    assert by_name["laravel"]["health"] == "ok"
    assert by_name["laravel"]["serving"] is True
    # A quarantined source is shown rather than hidden. It is the state somebody opens this
    # screen to find, and a screen that dropped it would be reassuring about the one connector
    # whose far side stopped matching what was installed.
    assert by_name["freshdesk"]["lifecycle"] == "quarantined"
    assert by_name["freshdesk"]["health"] == ""
    assert by_name["freshdesk"]["checked_at"] is None


def test_a_grant_narrowed_to_one_source_is_told_about_that_source_and_no_other(
    wired: TestClient,
) -> None:
    """Deleting this lets a narrowed grant answer the whole list, which is the disclosure this
    screen exists to prevent: which outside systems a company reads is a fact about the company,
    and naming one to somebody holding nothing over it is the disclosure whether or not any of
    its rows are shown."""
    body = get(wired, "u_narrow").json()

    assert [one["name"] for one in body["connectors"]] == ["laravel"]
    assert "freshdesk" not in get(wired, "u_narrow").text


def test_a_body_carries_no_count_of_the_sources_that_were_left_out(wired: TestClient) -> None:
    """Deleting this lets a `total` appear beside a filtered list, and a reader holding one
    grant then learns how many other systems this company reads by subtraction, with every
    value on the screen correct."""
    body = get(wired, "u_narrow").json()

    assert "total" not in body
    assert "truncated" not in body
    assert not any(key in body for key in ("hidden", "withheld", "of"))


# --- the refusal, which is the same refusal for everybody ---------------------------------------


def test_a_caller_without_the_capability_is_answered_as_one_with_nothing_to_see(
    wired: TestClient, client: TestClient
) -> None:
    """The rule this screen turns on: DENIED and ABSENT are one answer.

    Three callers are compared and all three get the same status and the same body: somebody
    holding no connector grant on an install with two connectors, the same person on an install
    with none, and somebody holding the console plane and nothing else. If the refusal differed
    from the absence by a single character, whether this company reads anything at all would be
    readable by anybody who can reach the port.

    Delete this and a refusal acquires a message of its own, which is the change that reads as
    helpfulness."""
    refused_with_sources = get(wired, "u_none")
    refused_without = get(client, "u_none")

    assert refused_with_sources.status_code == refused_without.status_code
    assert refused_with_sources.json()["message"] == refused_without.json()["message"]
    # The trace id is the one field that differs, and it differs between two calls by the same
    # caller as well, so it carries nothing about which install answered.
    assert set(refused_with_sources.json()) == {"message", "trace_id"}
    # Nothing in the refusal names the screen, the capability or a source.
    text = refused_with_sources.json()["message"]
    for word in ("connector", "laravel", "freshdesk", CONNECTORS_READ.value):
        assert word not in text


def test_the_console_plane_is_asked_for_as_well_as_the_capability(wired: TestClient) -> None:
    """Deleting this lets the route check the capability alone, which would answer somebody who
    may know a source exists with the configuration of it. `u_elsewhere` holds the read over
    every source and no console plane, and is refused; `u_wide` holds both and is answered. The
    pair is what makes this a test of two conditions rather than of one."""
    assert get(wired, "u_elsewhere").status_code != 200
    assert get(wired, "u_wide").status_code == 200


# --- what the screen says when it cannot look ---------------------------------------------------


def test_an_install_with_no_registry_answers_a_sentence_and_never_an_empty_list(
    client: TestClient,
) -> None:
    """Deleting this lets the route send `connectors: []` on an install where nothing looked,
    and an empty list of connectors reads as a system that reads no outside data, which is the
    reassuring answer to the question this screen exists to answer honestly."""
    body = get(client, "u_wide").json()

    assert body["connectors"] is None
    assert body["unread"] == NOTHING_HERE_HOLDS_A_CONNECTOR_REGISTRY
    # And the reader really is absent rather than present and empty, which is the state this
    # branch is about: a process that held one returning nothing is the other test above.
    assert installed_connectors_of(cast(Request, SimpleNamespace(app=_app()))) is None


def test_something_attached_that_is_not_callable_is_not_treated_as_a_reader() -> None:
    """Deleting this lets the `callable` check go, and the route then calls whatever is on
    `app.state.installed_connectors`. A string there produces a TypeError inside the request,
    which reaches the caller as a 500 and reads as a bug in the gate rather than as a process
    somebody wired wrong. The sentence is the right answer to a reader that is not a reader.

    Its own test rather than a branch of the one above, because the two absences are different:
    nothing attached is the state of every install today, and something attached that cannot be
    called is a deployment mistake."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.installed_connectors = "not a reader"
        body = get(c, "u_wide").json()

    assert body["connectors"] is None
    assert body["unread"] == NOTHING_HERE_HOLDS_A_CONNECTOR_REGISTRY


def test_a_list_and_a_sentence_cannot_both_be_sent(wired: TestClient) -> None:
    """Deleting this lets a body carry both, and a reader cannot then tell an install that reads
    nothing from one nothing looked at. Asserted on the model rather than on a response, because
    what is under test is the refusal and no route builds the bad value."""
    with pytest.raises(ValidationError):
        ConnectorsView(
            connectors=[],
            unread="something",
            connecting="x",
            copy_policy=[],
            budget_unread="y",
            may_connect=False,
        )
    with pytest.raises(ValidationError):
        ConnectorsView(connecting="x", copy_policy=[], budget_unread="y", may_connect=False)
    assert get(wired, "u_wide").json()["unread"] == ""


def test_the_screen_says_what_connecting_involves_on_every_answer_including_the_unread_one(
    client: TestClient, wired: TestClient
) -> None:
    """Deleting this lets the sentence be dropped from the branch nobody looks at, which is the
    one every install currently takes. The sentence is what stands in for a control this build
    cannot offer, and a screen with neither is a screen that looks finished."""
    for c in (client, wired):
        body = get(c, "u_wide").json()
        assert body["connecting"] == CONNECTING_IS_NOT_DONE_FROM_A_BROWSER_TODAY
        assert body["budget_unread"] == NOTHING_HERE_COUNTS_TODAYS_CALLS
        assert len(body["copy_policy"]) > 2


def test_the_authority_to_install_is_a_fact_about_the_reader_and_narrows_nothing(
    wired: TestClient,
) -> None:
    """Deleting this lets `may_connect` become a filter, and a reader holding the install
    authority would then see sources their read grant does not reach. It is the reader's own
    grant and it decides only which of two sentences they are shown."""
    holder = get(wired, "u_admin").json()
    without = get(wired, "u_wide").json()

    assert holder["may_connect"] is True
    assert without["may_connect"] is False
    # The same rows either way. The authority to install decides nothing about the list.
    assert [one["name"] for one in holder["connectors"]] == [
        one["name"] for one in without["connectors"]
    ]


def test_the_install_authority_alone_opens_no_screen(wired: TestClient) -> None:
    """The sibling: `u_prefix` holds `admin:connector` and no read, and is refused exactly as
    somebody holding nothing is. Deleting this lets the install authority be read as covering
    the screen, which is a capability that grants a listing nobody wrote a grant for."""
    assert get(wired, "u_prefix").status_code == get(wired, "u_none").status_code
    assert get(wired, "u_prefix").json()["message"] == get(wired, "u_none").json()["message"]


# --- nothing that could be a credential leaves the process --------------------------------------


def test_no_response_and_no_log_line_carries_a_vault_path(wired: TestClient) -> None:
    """The rule the whole screen is built under, asserted over the whole body and over
    everything the request logged rather than over a named field: a test naming the field goes
    green the moment somebody adds a different one.

    Delete this and a vault path arrives on a console row, in a screenshot, in a support chat.
    The reference is useless without the vault by `CredentialBinding`'s own argument, and it is
    still the fact `brain.ops.openbao` builds every error message to avoid naming."""
    with structlog.testing.capture_logs() as logged:
        answered = get(wired, "u_wide")
        refused = get(wired, "u_none")

    assert BOUND_PATH not in answered.text
    assert BOUND_PATH not in refused.text
    # The tail as well as the whole, because a row carrying the last segment beside a mount name
    # is the same disclosure assembled by the reader. The mount itself is not asserted on: it is
    # the word `database`, which is also a transport and is on a row legitimately.
    assert BOUND_PATH.rsplit("/", 1)[-1] not in answered.text
    written = " ".join(str(one) for one in logged)
    assert BOUND_PATH not in written
    # And nothing shaped like a secret value. The one field on this response that mentions a
    # credential at all is a sentence, so it names a vault role and no more.
    assert "password" not in answered.text
    assert "api_key" not in answered.text
