"""The install acceptance check that a live connector answer says where it came from.

M11.8.8 asks for live connector answers proved on an install. It has three parts:
- every shipped connector is connected from the console with its key in the vault and scoped to
  the slice it was given;
- a question about one of a client's open tickets is answered from the live source, citing the
  record, the field and the time read;
- a connector not bound to the agent is refused even where the asker could reach it.

**Two halves, and only one of them is a check.** The live half asks a real question about a real
ticket on the company's own helpdesk. A check may not do that. It stands up reserved people in
reserved departments and grants nobody anything elsewhere
(`brain.ops.acceptance_checks_connector_framework.A_CHECK_GRANTS_NOBODY_OUTSIDE_ITS_DEPARTMENTS`),
so it cannot be told the company's tickets, and that rule is kept whole. Pointing the real
connection at a reserved department inside a rolled-back transaction was rejected for the same
reason: it is the same grant by another route, and every later check that copied it would weaken
the rule. The live half is the owner's own walk-through, recorded on Install, Requirement checks
against the Connectors area, which names this leaf
(`brain.requirement_check_routes.A_LIVE_HALF_IS_PROVED_BY_A_PERSON`).

**This check is the automated half, and it is a regression over a helpdesk made up for the run.**
- **The key.** Every connector the console offers builds a manifest that binds its key by reference
  to its own vault slot, scoped by at least one selector. The made-up helpdesk is connected through
  the connect route's own store, with its key kept by the product's keeper in a vault the check
  holds.
- **The read.** The live read leases that key from the same vault, so the key that reaches the
  helpdesk is the one the console kept.
- **The citation.** A person asks about the open ticket on `/answer`. Their answer must cite that
  ticket's id, the field read live, Freshdesk, and the instant it was read.
- **Binding.** An agent bound to Freshdesk answers, and one that is not is told what a missing
  ticket tells it.

No socket is opened and no real key is held
(`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`).

Task ids: M11.8.8
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import SET_UP_REACH, Harness

if TYPE_CHECKING:
    from brain.ops.secrets import SecretRef

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 425

A, _ = RESERVED_DEPARTMENTS

#: The helpdesk address the check connects. Never reached: the check's own helpdesk answers it.
HELPDESK: Final = "acceptance-live.freshdesk.com"

# What the check says, one sentence for each way the property can fail.
FRESHDESK_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has Freshdesk connected already, so the check does not connect a helpdesk of "
    "its own beside it; the live half is the owner's recorded check on Requirement checks"
)
A_SOURCE_IS_NOT_KEYED_BY_REFERENCE: Final = (
    "a connector the console offers does not bind its key by reference to its own vault slot, "
    "scoped to a slice"
)
THE_KEY_WAS_NOT_THE_ONE_KEPT: Final = (
    "the helpdesk was not read with the key the Connectors route kept in the vault"
)
THE_ANSWER_DID_NOT_CITE_WHAT_WAS_READ: Final = (
    "a question about an open ticket was not answered citing the ticket, the field read live, "
    "Freshdesk and the time it was read"
)
AN_UNBOUND_AGENT_WAS_ANSWERED: Final = "an agent not bound to Freshdesk was answered from it"


@dataclass
class _VaultLease:
    """`KeyLease` over what the vault slot holds."""

    given: str | None = field(repr=False)

    def key(self) -> str:
        from brain.ops.connector_sync import NO_KEY
        from brain.ops.connector_sync_run import ConnectorKeyAbsentError

        if self.given is None:
            raise ConnectorKeyAbsentError(NO_KEY)
        return self.given

    def user(self) -> str:
        from brain.ops.connector_sync import NO_KEY
        from brain.ops.connector_sync_run import ConnectorKeyAbsentError

        raise ConnectorKeyAbsentError(NO_KEY)

    def close(self, now: datetime) -> Any:
        from brain.ops.connector_lease import LeaseOutcome

        del now
        return LeaseOutcome.NONE


@dataclass
class _VaultKeys:
    """`ConnectorKeys` reading each slot from the vault the console's keeper wrote, nothing else."""

    vault: Any

    def lease(self, ref: SecretRef, *, now: datetime) -> _VaultLease:
        from brain.ops.credentials import KEY_FIELD

        del now
        held = self.vault.slots.get(ref.path) or {}
        return _VaultLease(held.get(KEY_FIELD))


@check(
    leaves=("M11.8.8",),
    sentence=(
        "Every connector the console offers is keyed by reference to its own vault slot and "
        "scoped; a helpdesk made up for the check is connected with its key kept in the vault and "
        "read with that key; a person's question about its open ticket cites the ticket, the field "
        "read live, Freshdesk and when; and an agent not bound to it is refused. The live half is "
        "the owner's recorded check."
    ),
)
async def a_live_connector_answer_cites_what_it_read_and_when(h: Harness) -> None:
    from brain.connectors import freshdesk
    from brain.connectors.minimal_index import fresh_canary
    from brain.ops.acceptance_checks_connectable import (
        _answering,
        _asked,
        _from_the_console,
        _on_ask,
        _prose,
        _served,
        _two_agents,
    )
    from brain.ops.acceptance_checks_connector_framework import _form, _Vault
    from brain.ops.acceptance_checks_sources import OPEN
    from brain.ops.connectable import CONNECTABLE, key_reference, manifest_for
    from brain.ops.connector_store import live
    from brain.ops.connector_sync_run import authorization
    from brain.ops.credential_write_store import StoredCredentialWrites
    from brain.ops.credentials import Credentials, connector_key_slot

    # Every connector the console offers: its key by reference, in its own slot, and scoped.
    for name in CONNECTABLE:
        declared = manifest_for(name, _form(name))
        if declared.credential.ref != key_reference(name) or not declared.scope.selectors:
            raise CheckFailedError(A_SOURCE_IS_NOT_KEYED_BY_REFERENCE)

    if (await h.execute(live(freshdesk.FRESHDESK))).scalar_one_or_none() is not None:
        raise CheckNotRunError(FRESHDESK_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()

    # A made-up helpdesk with one open ticket, connected from its form and read by the worker.
    subject, body = h.word(), fresh_canary("ACCEPTANCE")
    ticket = {
        "id": 900_000 + uuid.uuid4().int % 99_999,
        "subject": subject,
        "status": OPEN,
        "priority": 1,
        "company_id": 1,
        "requester_id": 1,
        "group_id": 1,
        "created_at": "2019-03-01T10:00:00Z",
        "updated_at": "2019-03-02T10:00:00Z",
        "due_by": "2019-03-08T10:00:00Z",
    }
    helpdesk = _Signed(ticket, body=body)
    vault = _Vault()
    key = secrets.token_hex(24)
    await Credentials(vault, writes=StoredCredentialWrites(h.sessions)).keep(
        connector_key_slot(freshdesk.FRESHDESK),
        key,
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
    )
    source = await _from_the_console(
        h,
        freshdesk.FRESHDESK,
        {freshdesk.DOMAIN_SETTING: HELPDESK, freshdesk.DEPARTMENT_SETTING: A},
        helpdesk,
        keys=_VaultKeys(vault),
    )

    # A permitted person asks, and the answer cites the ticket, the field, the source and when.
    scope = Scope.department(A)
    reads = (
        f"read:{freshdesk.TICKET}",
        f"read:{freshdesk.TICKET}.subject",
        f"read:{freshdesk.TICKET}.{freshdesk.LIVE_BODY_FIELD}",
    )
    app = await _answering(h, source)
    reader = h.principal(A, "livereader")
    await h.person(reader, department=A, grants=tuple((one, scope) for one in reads))
    asked = _asked(freshdesk.LIVE_BODY_FIELD, subject)
    told = await _on_ask(h, app, reader, asked)
    scheme = freshdesk.FreshdeskReading().key_scheme()
    if not helpdesk.read_with or set(helpdesk.read_with) != {authorization(scheme, key)}:
        raise CheckFailedError(THE_KEY_WAS_NOT_THE_ONE_KEPT)
    cited = () if told.composed is None else told.composed.citations
    if body not in _prose(told) or not any(
        one.entity == freshdesk.TICKET
        and one.record_id == str(ticket["id"])
        and one.field == freshdesk.LIVE_BODY_FIELD
        and one.source == freshdesk.FRESHDESK
        and one.fetched_at
        for one in cited
    ):
        raise CheckFailedError(THE_ANSWER_DID_NOT_CITE_WHAT_WAS_READ)

    # An agent bound to Freshdesk answers; one that is not is told what a missing ticket tells it.
    bound, unbound = await _two_agents(
        h, freshdesk.FRESHDESK, reads, scope, served=await _served(h), tools=app.state.tools
    )
    through = await _on_ask(h, app, reader, asked, agent=bound)
    refused = await _on_ask(h, app, reader, asked, agent=unbound)
    nothing = await _on_ask(
        h, app, reader, _asked(freshdesk.LIVE_BODY_FIELD, h.word()), agent=unbound
    )
    if body not in _prose(through) or body in _prose(refused) or _prose(refused) != _prose(nothing):
        raise CheckFailedError(AN_UNBOUND_AGENT_WAS_ANSWERED)


@dataclass
class _Signed:
    """The sources check's helpdesk, also keeping the `Authorization` each call carried."""

    ticket: dict[str, Any]
    body: str = ""
    read_with: list[str] = field(default_factory=list)

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> Any:
        from brain.ops.acceptance_checks_sources import _Helpdesk

        self.read_with.append(str(headers.get("Authorization", "")))
        return _Helpdesk(self.ticket, body=self.body).get(
            url, address=address, headers=headers, max_bytes=max_bytes
        )
