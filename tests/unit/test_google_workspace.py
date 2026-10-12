"""Google Workspace: chosen services, a person's own consent, and a person's own passages.

Over `brain.connectors.google_workspace` and `brain.ops.google_workspace_live.WorkspacePassages`,
driven by the recordings in `tests/fixtures/cassettes/google_workspace.py` through a stand-in Google
that answers each address with its recorded body and notes every call and every header. No socket is
opened. The whole path against PostgreSQL, the consent included, is the install check in
`tests/unit/test_acceptance_google_workspace.py`. Every refusal here has a sibling that reads.

Task ids: M11.7.6
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

import pytest

from brain.connectors import google_workspace as gws
from brain.connectors.contract import ConnectorContractError
from brain.connectors.declaration import SettingRefusedError, shipped
from brain.connectors.manifest import PermissionSync
from brain.connectors.oauth import (
    YOUR_CONSENT_WITHDRAWN,
    asked_scopes,
    consent_address,
    new_consent,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import IdentityMode
from brain.core.scope import Scope
from brain.knowledge.connector_rows import ANSWERED_BY_PASSAGES
from brain.ops.connectable import key_reference, person_refresh_reference
from brain.ops.connector_store import Connection
from brain.ops.connector_sync_run import SourceAnswer
from brain.ops.google_workspace_live import READ_WORKSPACE, WITHDRAWN_TITLE, WorkspacePassages
from tests.fixtures.cassettes import FILES, for_source
from tests.fixtures.cassettes import google_workspace as recorded
from tests.unit.test_oauth_renewal import Keys, Resolver

#: A clock far from any wall clock, for CLAUDE.md's reason about dates in fixtures.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
SECRET: Final = "GOOGLE-CLIENT-SECRET-SENTINEL"
ADA: Final = "u_ada"
BEA: Final = "u_bea"
OPERATIONS: Final = "operations"
QUESTION: Final = "What did we agree about the retainer?"


def settings(services: str = "mail, calendar") -> dict[str, str]:
    example = gws.CONSOLE.example
    assert example is not None  # the connector declares one
    return {**example.settings, gws.SERVICES_SETTING: services}


def reader(pid: str, department: str = OPERATIONS) -> EntitlementSet:
    return EntitlementSet(
        principal_id=pid,
        grants=(Grant(capability=READ_WORKSPACE, scope=Scope.department(department)),),
    )


def recording(cid: str) -> Any:
    return next(one for one in for_source(gws.CONNECTOR_NAME) if one.cid == cid).body


@dataclass
class Google:
    """Google as the recordings answer it: one refresh token per person, each renewing that
    person's access, and the API answering only an access token it issued."""

    refresh: dict[str, str] = field(default_factory=dict)
    revoked: set[str] = field(default_factory=set)
    issued: dict[str, str] = field(default_factory=dict)
    asked: list[tuple[str, str]] = field(default_factory=list)

    def post(
        self, url: str, *, address: str, headers: Mapping[str, str], body: bytes, max_bytes: int
    ) -> SourceAnswer:
        del address, headers, max_bytes
        form = {key: values[0] for key, values in parse_qs(body.decode()).items()}
        person = self.refresh.get(form.get("refresh_token", ""), "")
        if url != gws.EXCHANGE_URL or form.get("client_secret") != SECRET:
            person = ""
        if not person or person in self.revoked:
            return SourceAnswer(status=400, body=json.dumps(recording("GWS-token-400")).encode())
        access = f"access-{person}"
        self.issued[access] = person
        answer = {**recording("GWS-token-200"), "access_token": access}
        return SourceAnswer(status=200, body=json.dumps(answer).encode())

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        del address, max_bytes
        sent = headers.get("Authorization", "").removeprefix("Bearer ")
        path = urlsplit(url).path
        self.asked.append((path, self.issued.get(sent, "")))
        if sent not in self.issued:
            return SourceAnswer(status=401, body=json.dumps(recording("GWS-401")).encode())
        if path.endswith("/export"):
            return SourceAnswer(status=200, body=recording("GWS-200-export").encode())
        cid = (
            "GWS-200-message"
            if "/messages/" in path
            else "GWS-200-messages"
            if path.endswith("/messages")
            else "GWS-200-events"
            if "/calendar/" in path
            else "GWS-200-files"
        )
        return SourceAnswer(status=200, body=json.dumps(recording(cid)).encode())


def passages_for(
    entitlement: EntitlementSet, google: Google, keys: Keys, services: str = "mail, calendar"
) -> Any:
    connection = Connection(
        connector=gws.CONNECTOR_NAME,
        settings=settings(services),
        digest="0" * 64,
        connected_by="u_admin",
        connected_at=NOW,
    )

    async def connected() -> Connection:
        return connection

    search = WorkspacePassages(
        connected, keys=keys, caller=google, poster=google, resolver=Resolver(), clock=lambda: NOW
    )
    return asyncio.run(search.passages(QUESTION, entitlement=entitlement, now=NOW))


def consented(*people: str) -> tuple[Google, Keys]:
    google = Google()
    keys = Keys(slots={key_reference(gws.CONNECTOR_NAME).path: SECRET})
    for person in people:
        token = f"REFRESH-{person}"
        google.refresh[token] = person
        keys.slots[person_refresh_reference(gws.CONNECTOR_NAME, person).path] = token
    return google, keys


# ------------------------------------------------------------------ the declaration
def test_the_connector_ships_answered_by_passages_with_a_personal_consent() -> None:
    """Workspace is a shipped connector whose consent each person gives for themselves, naming
    the reader capability the passages are told under, and whose records Ask reads as passages.
    Delete this and it can ship consented to once for everybody, or classified into rows."""
    declared = shipped()[gws.CONNECTOR_NAME]
    assert declared.oauth is gws.CONSENT and declared.reading is None
    assert declared.oauth.reader == READ_WORKSPACE.value == gws.READER
    assert gws.CONNECTOR_NAME in ANSWERED_BY_PASSAGES
    assert declared.ceiling is gws.CEILING and gws.CEILING.name == gws.CONNECTOR_NAME


def test_every_scope_a_consent_can_ask_for_is_googles_read_only_one() -> None:
    """The three scopes are Gmail's, Calendar's and Drive's read-only scopes, one per service,
    and Google is asked for offline access so it issues a refresh token at all. Delete this and a
    scope that sends mail can be added beside them in a debugging session."""
    assert set(gws.SCOPE_OF.values()) == set(gws.CONSENT.scopes)
    assert all(one.endswith(".readonly") for one in gws.CONSENT.scopes)
    assert ("access_type", "offline") in gws.CONSENT.authorize_params


def test_a_service_not_chosen_is_never_asked_for_at_consent() -> None:
    """A connection reading mail alone sends a person to Google asking for `gmail.readonly` and
    nothing else; one reading all three asks for all three. A service nobody chose is refused as a
    choice. Delete this and a person consents to their documents for a connection that reads only
    their mail."""
    start = new_consent()

    def asked(services: str) -> list[str]:
        address = consent_address(
            gws.CONSENT,
            client_id="c",
            redirect_uri="https://console.example/connector-consent",
            start=start,
            scopes=asked_scopes(gws.CONSENT, settings(services)),
        )
        return parse_qs(urlsplit(address).query)["scope"][0].split()

    assert asked("mail") == [gws.GMAIL_SCOPE]
    assert asked("documents, mail, calendar") == list(gws.CONSENT.scopes)
    for refused in ("", "contacts"):
        with pytest.raises(ConnectorContractError):
            asked_scopes(gws.CONSENT, settings(refused))


def test_a_connection_needs_a_client_id_a_service_and_a_department() -> None:
    """The example connects; an unknown service, no service, a client id that is not Google's
    and a department that is not a short name are each refused naming their setting. Delete this
    and a connection is made that no consent could ever be asked for."""
    made = gws.WorkspaceConnection.from_settings(settings("calendar, mail"))
    assert made.services == (gws.Service.MAIL, gws.Service.CALENDAR)
    for setting, value in (
        (gws.SERVICES_SETTING, "mail, contacts"),
        (gws.SERVICES_SETTING, ""),
        (gws.CLIENT_ID_SETTING, "not-a-client"),
        (gws.DEPARTMENT_SETTING, "Not A Slug"),
    ):
        with pytest.raises(SettingRefusedError) as refused:
            gws.WorkspaceConnection.from_settings({**settings(), setting: value})
        assert refused.value.setting == setting


def test_the_manifest_declares_a_delegated_tool_per_chosen_service_and_projects_nothing() -> None:
    """One tool per chosen service, each read as the asking person, no projected entity, and the
    source's own permissions enforced on every call. Delete this and a minimal index of somebody's
    mail can be added with nothing saying the owner's rule was broken."""
    built = gws.built_from_the_console(settings("mail"), key_reference(gws.CONNECTOR_NAME))
    assert [one.name for one in built.tools] == ["google_workspace.find_mail"]
    assert all(one.identity_mode is IdentityMode.DELEGATED for one in built.tools)
    assert built.projections == () and built.permission_sync is PermissionSync.DELEGATED
    every = gws.built_from_the_console(settings("mail, calendar, documents"), key_reference("x"))
    assert len(every.tools) == 3


def test_every_recording_is_concluded_as_it_was_recorded() -> None:
    """Each recording replayed through the connector's own reading concludes what it states: an
    absent search is absent, a refused token is refused, a page that is not JSON is unusable and a
    429 is a rate limit. Delete this and Workspace can read a refusal as an empty mailbox."""
    concluded = {
        one.cid: FILES[gws.CONNECTOR_NAME].replay(one).outcome for one in recorded.CASSETTES
    }
    assert concluded == {one.cid: one.expect for one in recorded.CASSETTES}


def test_the_ceiling_is_gmails_dearest_call_and_agrees_with_the_recording() -> None:
    """The ceiling is the recorded per-user Gmail allowance at a message read's cost, and the
    cassette's rate limit says the same number and that it can be raised. Delete this and the
    figure can drift from Google's page with both records agreeing with themselves."""
    assert gws.CEILING.per_minute == 6_000 // 20 == recorded.RATE_LIMIT.calls
    assert gws.CEILING.raisable is recorded.RATE_LIMIT.raisable is True


# ------------------------------------------------------------------ the read
def test_a_person_is_read_their_own_mail_and_calendar_with_their_own_access() -> None:
    """Ada, holding the capability and her own consent, is read her matching mail and events with
    the access her own refresh token renewed, as passages personal to her; documents were not
    chosen and are never called, and a message is read as metadata, never its body. Delete this
    and the read can use somebody else's access, call a service nobody chose, or tell a passage
    to more than its asker."""
    google, keys = consented(ADA)
    told = passages_for(reader(ADA), google, keys)
    texts = [one.document for one in told.records]
    assert any(recorded.MAIL_SNIPPET in one for one in texts)
    assert any(recorded.EVENT_TEXT in one for one in texts)
    assert all(one.owner_id == ADA and one.visibility == "personal" for one in told.records)
    assert {who for _, who in google.asked} == {ADA}
    assert not [path for path, _ in google.asked if "/drive/" in path]
    assert all("format" not in path for path, _ in google.asked)


def test_documents_are_read_only_when_chosen() -> None:
    """With documents chosen, the matching Google Doc's words are read for the asker, around the
    question's word. The sibling above never calls Drive. Delete this and documents chosen at
    connect are never read."""
    google, keys = consented(ADA)
    told = passages_for(reader(ADA), google, keys, services="documents")
    assert [one.document for one in told.records] and all(
        recorded.DOCUMENT_TEXT.split("\n", 1)[1] in one.document for one in told.records
    )
    assert {path for path, _ in google.asked} <= {
        "/drive/v3/files",
        f"/drive/v3/files/{recorded.DOCUMENT}/export",
    }


def test_another_person_is_told_nothing_from_someone_elses_account() -> None:
    """Ada has consented and Bea has not: Bea's question reads nothing, renews nothing of Ada's
    and calls Google for nothing, and what she is told is what an empty account tells her. Delete
    this and one person's question reads another person's mailbox."""
    google, keys = consented(ADA)
    told = passages_for(reader(BEA), google, keys)
    assert told.records == ()
    assert google.asked == [] and not google.issued
    leased = {one.given for one in keys.leases}
    assert "REFRESH-u_ada" not in leased


def test_a_person_without_the_capability_or_in_another_department_is_read_nothing() -> None:
    """Holding no grant, or the grant in a department the connection does not answer to, Ada is
    read nothing and Google is not asked, consent or not; the sibling above reads her. Delete this
    and the data steward's grant decides nothing."""
    google, keys = consented(ADA)
    for entitlement in (EntitlementSet(principal_id=ADA, grants=()), reader(ADA, "sales")):
        assert passages_for(entitlement, google, keys).records == ()
    assert google.asked == [] and keys.leases == []


def test_a_withdrawn_consent_is_said_to_that_person_and_another_still_reads() -> None:
    """Google refusing Ada's renewal is told to Ada as one passage in her own sentence, and Bea,
    with her own consent, is still read. Delete this and a revoked consent reads as an empty
    mailbox, or takes everybody's reads down."""
    google, keys = consented(ADA, BEA)
    google.revoked.add(ADA)
    told = passages_for(reader(ADA), google, keys)
    assert [(one.title, one.document, one.owner_id) for one in told.records] == [
        (WITHDRAWN_TITLE, YOUR_CONSENT_WITHDRAWN, ADA)
    ]
    assert passages_for(reader(BEA), google, keys).records


def test_the_reader_capability_is_one_the_capabilities_screen_names() -> None:
    """`read:google_workspace` is declared among the capabilities code checks, with words, so the
    data steward can find the grant the owner's steps name. Delete this and the grant cannot be
    given from the screen on any install."""
    from brain.ops.starter import checked_elsewhere

    assert READ_WORKSPACE in {one for one, _ in checked_elsewhere()}
    assert Capability(value=gws.READER) == READ_WORKSPACE
