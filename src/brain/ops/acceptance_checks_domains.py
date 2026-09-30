"""The install acceptance check for domains and hosting: a domain's facts from its registry, on Ask.

M11.7.4 asks that each client domain's registrar, expiry and hosting status are reported from the
source, so an expiry question is answered from the registry rather than from a spreadsheet. The
check connects a domains connection made up for the run inside its own transaction, through the
store the Connectors screen's routes call, reads its index with the worker's own
`brain.ops.connector_sync_run.attempt`, and asks about it through the answer lane with everything
the answer route hands it built by the route's own functions, as
`brain.ops.acceptance_checks_sources` does for Xero and Freshdesk.

**No socket is opened.** Every registry and every site is answered by `_Registries`, which returns
a record in RDAP's documented shape for a listed domain whose registry publishes one, and a
site's 200, and records every address it was asked for. So the check can say what was never
asked, which is the half of this leaf that matters most.

**What it proves, in the owner's guards' words.** A listed domain's expiry and registrar are read
from its registry when asked, and its site is asked beside it; the registrar is kept in no table.
A domain whose registry publishes no RDAP is answered as that, for that domain, and its registry is
never asked. A domain nobody listed is never looked up, whoever asks about it. A reader not granted
the registrar is told what a domain nobody listed tells them.

**The check steps aside where the install has a domains connection already**, for
`brain.ops.acceptance_checks_sources.A_SOURCE_IS_CONNECTED_HERE_ALREADY`'s reason.

Task ids: M11.7.4
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_connectors import _Keys, _Resolver, _search
from brain.ops.acceptance_checks_sources import _connect_and_read, _connection, _prose
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet
    from brain.gate.answer import Answered
    from brain.ops.connector_sync_run import SourceAnswer

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 350

A, _ = RESERVED_DEPARTMENTS

#: What the check says where the install has a domains connection already.
DOMAINS_ARE_CONNECTED_HERE_ALREADY: Final = (
    "this install has its domains connected already, so the check does not connect them again "
    "and does not ask about them"
)

#: The expiry the recorded registry states, far from any wall clock.
EXPIRY: Final = "2999-03-01T00:00:00Z"


@dataclass
class _Registries:
    """Every registry and every site, answered from the check's own record. No socket."""

    registrar: str
    asked: list[str] = field(default_factory=list)

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, headers, max_bytes
        self.asked.append(url)
        if "/domain/" in url:
            name = url.rsplit("/", 1)[-1]
            record = {
                "objectClassName": "domain",
                "ldhName": name.upper(),
                "status": ["client transfer prohibited"],
                "events": [{"eventAction": "expiration", "eventDate": EXPIRY}],
                "entities": [
                    {
                        "objectClassName": "entity",
                        "roles": ["registrar"],
                        "vcardArray": ["vcard", [["fn", {}, "text", self.registrar]]],
                    }
                ],
            }
            return SourceAnswer(status=200, headers={}, body=json.dumps(record).encode())
        return SourceAnswer(status=200, headers={}, body=b"<html></html>")

    def looked_up(self, domain: str) -> bool:
        return any(one.endswith(f"/domain/{domain}") for one in self.asked)


@check(
    leaves=("M11.7.4",),
    sentence=(
        "A domains connection made up for the check is read from recorded registries and asked "
        "about on Ask: a listed domain's expiry and registrar come from its registry and its site "
        "is asked beside it, a domain whose registry publishes no RDAP is said so and its registry "
        "never asked, a domain nobody listed is never looked up, and the registrar is in no table."
    ),
)
async def a_domain_s_expiry_comes_from_its_registry_and_no_other_is_asked(
    h: Harness,
) -> None:
    from brain.api_routes import (
        connected_questions_of,
        covered_at,
        field_policies,
        row_readers,
        source_field_policies,
    )
    from brain.connectors import domains
    from brain.connectors.contract import FetchRequest
    from brain.connectors.live_read import RECORD_ID_FILTER
    from brain.connectors.minimal_index import fresh_canary
    from brain.connectors.rdap_servers import server_for
    from brain.connectors.throttle import CallOutcome
    from brain.core.envelope import IdentityMode
    from brain.gate.answer import answer_lane
    from brain.gate.context import Channel
    from brain.gate.finish import Origin
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.connector_store import live
    from brain.ops.live_read_run import ConnectedSources
    from brain.ops.live_records import SourceRecords
    from brain.ops.trace_sink import CountingTraceSink
    from brain.tools.startup import build_registry

    if (await h.execute(live(domains.CONNECTOR_NAME))).scalar_one_or_none() is not None:
        raise CheckNotRunError(DOMAINS_ARE_CONNECTED_HERE_ALREADY)
    await h.found_departments()

    routed = f"acceptance-{secrets.token_hex(4)}.com"
    unpublished = f"acceptance-{secrets.token_hex(4)}.my"
    unlisted = f"acceptance-{secrets.token_hex(4)}.com"
    if server_for(routed) is None or server_for(unpublished) is not None:
        raise CheckFailedError("the registry list no longer says which domains publish RDAP")
    registries = _Registries(registrar=fresh_canary("ACCEPTANCE"))
    connection = _connection(
        h, domains.CONNECTOR_NAME, {"domains": f"{routed}, {unpublished}", "department": A}
    )
    await _connect_and_read(h, connection, registries, at=h.now)
    if registries.looked_up(unpublished) or registries.looked_up(unlisted):
        raise CheckFailedError(
            "the worker looked up a domain no registry publishes or nobody listed"
        )

    rules = await connected_questions_of(SimpleNamespace(db_sessions=h.sessions))
    registry = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    readers = row_readers(registry)

    async def connected() -> Any:
        return ConnectedSources(
            {domains.CONNECTOR_NAME: connection},
            keys=_Keys(),
            caller=registries,
            resolver=_Resolver(),
            clock=lambda: h.now,
        )

    live_records = SourceRecords(connected=connected, clock=lambda: h.now)

    async def ask(principal_id: str, field_name: str, domain: str) -> Answered:
        person = await StoredPrincipals(h.sessions).live_principal(principal_id)
        if person is None:
            raise CheckFailedError("a reserved person was not live in the directory")
        reach: EntitlementSet = await _console(h, principal_id, second_factor=False)
        return await answer_lane(
            QUESTION_SHAPES[0].format(label=label_of(field_name), slot=domain),
            origin=Origin(trace_id=h.trace_id, principal=person, channel=Channel.CONSOLE),
            recorders=(),
            rules=rules,
            readers=readers,
            entitlement=reach,
            policies=field_policies(registry),
            reachable_sources=covered_at(registry, reach, h.now),
            sink=CountingTraceSink(),
            now=h.now,
            clock=lambda: h.now,
            live=live_records,
            source_policies=source_field_policies(registry),
        )

    facts = ("name", "expiry", "registration", "registrar", "hosting")
    reads = ("read:domain", *(f"read:domain.{one}" for one in facts))
    operations, clerk = h.principal(A, "operations"), h.principal(A, "clerk")
    await h.person(
        operations, department=A, grants=tuple((one, Scope.department(A)) for one in reads)
    )
    await h.person(
        clerk,
        department=A,
        grants=tuple((one, Scope.department(A)) for one in reads if one != "read:domain.registrar"),
    )

    # A listed domain: its expiry and registrar from its registry, its site asked beside it.
    expiry = await ask(operations, "expiry", routed)
    if expiry.composed is None or EXPIRY[:10] not in _prose(expiry):
        raise CheckFailedError("a listed domain's expiry was not answered from its registry")
    registrar = await ask(operations, "registrar", routed)
    if registrar.composed is None or registries.registrar not in _prose(registrar):
        raise CheckFailedError("a listed domain's registrar was not read from its registry")
    hosting = await ask(operations, "hosting", routed)
    if hosting.composed is None or "answers (HTTP 200)" not in _prose(hosting):
        raise CheckFailedError("a listed domain's site was not asked whether it answers")

    # A domain whose registry publishes no RDAP: said so, and its registry never asked.
    said = await ask(operations, "expiry", unpublished)
    if said.composed is None or domains.NOT_PUBLISHED not in _prose(said):
        raise CheckFailedError("a domain no registry publishes was not said to be unpublished")

    # A domain nobody listed: never looked up, whoever asks about it, on Ask or through the
    # connector's own live read as a tool would call it.
    nobody = await ask(operations, "expiry", unlisted)
    if nobody.composed is not None:
        raise CheckFailedError("a domain nobody listed was answered")
    fetch = (await connected()).source_for(
        domains.CONNECTOR_NAME, mode=IdentityMode.SERVICE, asker=operations
    )
    if fetch is None:
        raise CheckFailedError("a listed domain's registry cannot be read live")
    tried = await fetch(
        FetchRequest(entity=domains.DOMAIN, filters=((RECORD_ID_FILTER, unlisted),))
    )
    if tried.outcome is not CallOutcome.REJECTED or any(
        unlisted in one for one in registries.asked
    ):
        raise CheckFailedError("a domain nobody listed was looked up")
    if registries.looked_up(unpublished):
        raise CheckFailedError("a domain no registry publishes was looked up")

    # A reader not granted the registrar is told what a domain nobody listed tells them.
    withheld = await ask(clerk, "registrar", routed)
    absent = await ask(clerk, "registrar", unlisted)
    if registries.registrar in _prose(withheld) or _prose(withheld) != _prose(absent):
        raise CheckFailedError("a registrar was told to a reader not granted it")

    if await _search(h, registries.registrar):
        raise CheckFailedError("a registrar read live was found in a table")
