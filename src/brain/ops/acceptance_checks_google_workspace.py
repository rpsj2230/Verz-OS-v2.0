"""The install acceptance check for Google Workspace: a person's own account, read for them alone.

M11.7.6 is Google Workspace as a connector whose services are chosen at connect and whose mail
and calendar are read with the asking person's own authorisation. This check connects a made-up
Workspace through the product's own path and asks each part of that of it.

**Each step is the product's own code.** The connection is made by `StoredConnections.connect` with
the client secret kept by `Credentials.keep`; each person's consent is started and answered by
`brain.connector_routes.start_consent` and `finish_consent`, the bodies of the routes My workspace
calls, judged by `may_consent_for_themselves`; and a question is read by
`brain.ops.google_workspace_live.WorkspacePassages`, the passage reader the answer lane is handed,
with the asker's reach as the console admits it. What the check stands in for is Google and the
vault: Google is `_Google`, a recorded consent page, token endpoint and API that open no socket and
hold one account per person, and the vault is `brain.ops.acceptance_checks_oauth._RoleVault`, which
answers each token with what its policy file grants. Recorded answers only, never a real call.

**What it proves.** A person consents for their own account and Google is asked for the chosen
services' scopes alone; their question reads their own mail and calendar with their own token; a
second person holding the same grant, who has not consented, is read nothing and Google is asked
nothing for them; the service the connection did not choose is never called; and no message,
token or secret is in any table afterwards.

Task ids: M11.7.6
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs, urlsplit

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_connectors import _Resolver, _search
from brain.ops.acceptance_run import SET_UP_REACH

if TYPE_CHECKING:
    from brain.ops.acceptance_run import Harness
    from brain.ops.connector_sync_run import SourceAnswer

#: Where this module's check stands on the Install page, after Slack's.
CHECK_ORDER: Final = 365

A = RESERVED_DEPARTMENTS[0]

#: What the check says where the install has Google Workspace connected already.
WORKSPACE_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has Google Workspace connected already, so the check does not stand a second "
    "connection up beside the real one"
)

#: The console's consent page, under a name reserved for examples.
CONSOLE_RETURN: Final = "https://console.example/connector-consent"


@dataclass
class _Google:
    """Google's consent page, token endpoint and API as recorded answers, one account per person.

    A code is issued for the account that signed in, exchanged only with the verifier its S256
    challenge was asked with and the client's own secret; a refresh token renews its own
    account's access; and the API answers an access token with its own account's mail and events
    and nothing else. Every API call is noted with whose access it carried.
    """

    client_secret: str = field(repr=False)
    mail: dict[str, str]
    events: dict[str, str]
    codes: dict[str, tuple[str, str]] = field(default_factory=dict, repr=False)
    refresh: dict[str, str] = field(default_factory=dict, repr=False)
    access: dict[str, str] = field(default_factory=dict, repr=False)
    asked_scopes: list[str] = field(default_factory=list)
    called: list[tuple[str, str]] = field(default_factory=list)

    def consent(self, address: str, account: str) -> tuple[str, str]:
        """`account` signing in on Google's page: the state and the code it sends back."""
        from brain.connectors import google_workspace as gws

        asked = {key: values[0] for key, values in parse_qs(urlsplit(address).query).items()}
        if not address.startswith(f"{gws.AUTHORIZE_URL}?") or asked.get("access_type") != (
            "offline"
        ):
            raise CheckFailedError("the person was not sent to Google's page asking for offline")
        self.asked_scopes.extend(asked.get("scope", "").split())
        code = secrets.token_urlsafe(24)
        self.codes[code] = (account, asked["code_challenge"])
        return asked["state"], code

    def _issued(self, account: str) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        refresh, access = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.refresh[refresh], self.access[access] = account, account
        body = {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": 3599,
            "refresh_token": refresh,
        }
        return SourceAnswer(status=200, headers={}, body=json.dumps(body).encode())

    def post(
        self, url: str, *, address: str, headers: Mapping[str, str], body: bytes, max_bytes: int
    ) -> SourceAnswer:
        from brain.connectors import google_workspace as gws
        from brain.ops.connector_sync_run import SourceAnswer

        del address, headers, max_bytes
        form = {key: values[0] for key, values in parse_qs(body.decode("ascii")).items()}
        refused = SourceAnswer(status=400, headers={}, body=b'{"error": "invalid_grant"}')
        if url != gws.EXCHANGE_URL or form.get("client_secret") != self.client_secret:
            return refused
        if form.get("grant_type") == "authorization_code":
            account, challenge = self.codes.pop(form.get("code", ""), ("", ""))
            digest = hashlib.sha256(form.get("code_verifier", "").encode("ascii")).digest()
            if not account or challenge != base64.urlsafe_b64encode(digest).rstrip(b"=").decode():
                return refused
            return self._issued(account)
        account = self.refresh.get(form.get("refresh_token", ""), "")
        if not account:
            return refused
        # Google sends no new refresh token on a renewal.
        access = secrets.token_urlsafe(32)
        self.access[access] = account
        issued = {"access_token": access, "token_type": "Bearer", "expires_in": 3599}
        return SourceAnswer(status=200, headers={}, body=json.dumps(issued).encode())

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, max_bytes
        account = self.access.get(headers.get("Authorization", "").removeprefix("Bearer "), "")
        path = urlsplit(url).path
        self.called.append((path, account))
        if not account:
            return SourceAnswer(status=401, headers={}, body=b'{"error": {"code": 401}}')
        if path.endswith("/messages"):
            body: Any = {"messages": [{"id": f"m{account[-8:].replace('.', '')}"}]}
        elif "/messages/" in path:
            body = {
                "id": path.rsplit("/", 1)[-1],
                "snippet": self.mail[account],
                "payload": {"headers": [{"name": "Subject", "value": "Retainer"}]},
            }
        elif "/calendar/" in path:
            body = {
                "items": [
                    {
                        "id": "evt0123abcdefghij",
                        "summary": "Retainer review",
                        "description": self.events[account],
                        "start": {"dateTime": "2020-09-14T10:00:00Z"},
                    }
                ]
            }
        else:
            body = {"files": []}
        return SourceAnswer(status=200, headers={}, body=json.dumps(body).encode())


@check(
    leaves=("M11.7.6",),
    sentence=(
        "A Google Workspace is connected for mail and calendar through the product's own path: a "
        "person consents for their own account and is asked for those two scopes alone, their "
        "question reads their own mail and calendar with their own token, a colleague who has "
        "not consented is told nothing of theirs, Drive is never called, and nothing is kept in "
        "a table."
    ),
)
async def a_persons_own_workspace_is_read_with_their_token_for_them_alone(h: Harness) -> None:
    from brain.connector_routes import (
        ConsentExchange,
        finish_consent,
        may_consent_for_themselves,
        start_consent,
    )
    from brain.connectors import google_workspace as gws
    from brain.connectors.declaration import shipped
    from brain.connectors.manifest import manifest_digest
    from brain.ops.acceptance_checks_oauth import _RoleVault
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_consent import StoredConsentHealth, StoredConsents
    from brain.ops.connector_store import Connection, StoredConnections, live
    from brain.ops.connector_sync_run import WorkerConnectorKeys
    from brain.ops.credential_write_store import StoredCredentialWrites
    from brain.ops.credentials import Credentials, connector_key_slot
    from brain.ops.google_workspace_live import WorkspacePassages

    source = gws.CONNECTOR_NAME
    declared = shipped()[source]
    if (await h.execute(live(source))).scalar_one_or_none() is not None:
        raise CheckNotRunError(WORKSPACE_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()

    ada, bea = h.principal(A, "ada"), h.principal(A, "bea")
    canary = {one: f"{h.word()} retainer" for one in ("ada-mail", "ada-event", "bea-mail")}
    google = _Google(
        client_secret=secrets.token_urlsafe(32),
        mail={ada: canary["ada-mail"], bea: canary["bea-mail"]},
        events={ada: canary["ada-event"], bea: canary["bea-mail"]},
    )
    vault = _RoleVault()
    credentials = Credentials(vault, writes=StoredCredentialWrites(h.sessions))
    example = gws.CONSOLE.example
    assert example is not None  # the connector declares one
    settings = {**example.fresh((A,)), gws.SERVICES_SETTING: "mail, calendar"}
    connection = Connection(
        connector=source,
        settings=settings,
        digest=manifest_digest(manifest_for(source, settings)),
        connected_by=h.actor,
        connected_at=h.now,
    )

    async def keep_secret() -> datetime | None:
        kept = await credentials.keep(
            connector_key_slot(source), google.client_secret, actor=h.actor, trace_id=h.trace_id
        )
        return kept.set_at

    await StoredConnections(h.sessions).connect(
        connector=source,
        settings=settings,
        digest=connection.digest,
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        keep_key=keep_secret,
    )
    reader = ((gws.READER, Scope.department(A)),)
    for person in (ada, bea):
        await h.person(person, department=A, grants=reader)
    reaches = {one: await _console(h, one, second_factor=False) for one in (ada, bea)}

    # Ada connects her own account from My workspace, as the route does.
    if not may_consent_for_themselves(reaches[ada], declared, connection, h.now):
        raise CheckFailedError("a person holding the reader grant may not connect their account")
    consents = StoredConsents(h.sessions)
    address = await start_consent(
        declared,
        connection,
        consents=consents,
        principal_id=ada,
        return_address=CONSOLE_RETURN,
        now=h.now,
    )
    state, code = google.consent(address, ada)
    if sorted(google.asked_scopes) != sorted((gws.GMAIL_SCOPE, gws.CALENDAR_SCOPE)):
        raise CheckFailedError("the consent asked Google for a scope of a service not chosen")

    async def connected(name: str) -> Connection | None:
        return connection if name == source else None

    done = await finish_consent(
        state=state,
        code=code,
        vendor_refused=False,
        principal_id=ada,
        may_connect=lambda name: False,
        may_consent_personally=lambda one, live_one: may_consent_for_themselves(
            reaches[ada], one, live_one, h.now
        ),
        declarations={source: declared},
        connected=connected,
        consents=consents,
        exchange=ConsentExchange(
            keys=WorkerConnectorKeys(vault),
            poster=google,
            resolver=_Resolver(),
            health=StoredConsentHealth(h.sessions),
        ),
        credentials=credentials,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        now=h.now,
    )
    if not done.kept or not done.personal:
        raise CheckFailedError("a person's own consent to Google Workspace was not kept")

    async def the_connection() -> Connection | None:
        return connection

    search = WorkspacePassages(
        the_connection,
        keys=WorkerConnectorKeys(vault),
        caller=google,
        poster=google,
        resolver=_Resolver(),
        clock=lambda: h.now,
    )
    question = "What did we agree about the retainer?"

    # Ada's question reads her own mail and calendar with her own access, for her alone.
    told = await search.passages(question, entitlement=reaches[ada], now=h.now)
    texts = " ".join(one.document for one in told.records)
    if canary["ada-mail"] not in texts or canary["ada-event"] not in texts:
        raise CheckFailedError("a person's own mail and calendar were not read for their question")
    if any(one.owner_id != ada or one.visibility != "personal" for one in told.records):
        raise CheckFailedError("a Workspace passage was not personal to the person it was read for")
    if {who for _, who in google.called} != {ada}:
        raise CheckFailedError("a person's question was read with somebody else's access")

    # Bea holds the same grant and has not consented: Google is asked nothing for her.
    since = len(google.called)
    theirs = await search.passages(question, entitlement=reaches[bea], now=h.now)
    if theirs.records or len(google.called) != since:
        raise CheckFailedError("a person who has not connected their account was read something")
    if canary["ada-mail"] in " ".join(one.document for one in theirs.records):
        raise CheckFailedError("one person was told what another person's account holds")

    # Documents were not chosen, and Drive was never called for anybody.
    if [path for path, _ in google.called if "/drive/" in path]:
        raise CheckFailedError("a service the connection did not choose was called")

    # Nothing read, and no token or secret, is in any table.
    secrets_held = (google.client_secret, *google.refresh, *google.access, state)
    for needle in (*canary.values(), *secrets_held):
        if await _search(h, needle):
            raise CheckFailedError("a message, a token or a secret was found in a table")
