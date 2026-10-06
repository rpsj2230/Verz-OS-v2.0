"""The install acceptance check for a connector added from the console, reviewed, with no release.

M11.7.8 is one path, so it is one check, walked through the parts the routes and the worker call and
in their order, inside the check's transaction. An API made up for the run has its specification,
field mapping and key scheme submitted through `brain.custom_connector_routes. submission` by a
person who may connect it. While it waits it is not on the Connectors screen and the registry the
application builds has no tool for it. Its submitter's own approval is refused, and a second
person's is accepted through `deciding`. The approved set is then read as the catalogue reads it at
every request (`brain.ops.custom_connector_store.approved_in`), and from there it is a source like
any other: judged with a key by `connection_problems`, connected through the store the Connect route
calls, read by the worker's own `attempt` from a recorded answer, and asked about through the answer
lane with everything the answer route builds. A reader granted its price is told the price, read
live; a reader without that grant is told what a record that does not exist is told; and the price
is in no table afterwards. Last, the definition is changed, and from that statement it is waiting
again and in no list.

**No socket is opened and no real key is held.** The API's answers are the check's own `_Api`, and
the key the worker leases is minted for the check (`brain.ops.acceptance_checks_connectors._Keys`).
See that module's `A_RECORDED_ANSWER_IS_NEVER_A_CALL`.

**What the check lays over the catalogue is its own context's.** The approved set it reads is from
inside its transaction, which is rolled back, so it is laid over the catalogue with
`brain.ops.connector_catalogue.overlaid` and never installed for the process: a request served
beside the check never sees an API that, once the check ends, nobody approved.

Task ids: M11.7.8
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Clause, Op, Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_connectors import _Keys, _Resolver, _search
from brain.ops.acceptance_checks_sources import _connect_and_read, _connection, _prose
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet
    from brain.custom_connector_routes import DefinitionAsked
    from brain.gate.answer import Answered
    from brain.ops.connector_sync_run import SourceAnswer

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 398

A, B = RESERVED_DEPARTMENTS

#: The made-up API's address. Never reached: the recorded caller answers it.
HOST: Final = "acceptance-check.example.com"

#: The entity the made-up API lists, and its three fields: a code it is named by, a state kept in
#: the index, and a price read live and never kept.
CODE, STATE, PRICE = "code", "state", "price"


# ------------------------------------------------------------------------ the made-up API
def made_up_document(host: str = HOST) -> dict[str, Any]:
    """An OpenAPI document for an API nobody ships: a list of widgets and one widget by id.

    The widget's schema is a component the operations refer to, so the check also proves an internal
    `$ref` resolves.
    """
    widget = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "code": {"type": "string"},
            "state": {"type": "string"},
            "price": {"type": "string"},
        },
    }
    return {
        "openapi": "3.0.3",
        "info": {"title": "Widgets", "version": "1"},
        "servers": [{"url": f"https://{host}"}],
        "components": {"schemas": {"Widget": widget}},
        "paths": {
            "/widgets": {
                "get": {
                    "operationId": "listWidgets",
                    "parameters": [{"name": "page", "in": "query"}],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "data": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/Widget"},
                                            }
                                        },
                                    }
                                }
                            }
                        }
                    },
                }
            },
            "/widgets/{widgetId}": {
                "get": {
                    "operationId": "getWidget",
                    "parameters": [{"name": "widgetId", "in": "path", "required": True}],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Widget"}
                                }
                            }
                        }
                    },
                }
            },
        },
    }


def made_up_definition(name: str, entity: str, department: str) -> DefinitionAsked:
    """The submit form's body for the made-up API, as a person would fill it in."""
    from brain.connectors.declaration import KeyScheme
    from brain.connectors.manifest import FieldShape
    from brain.core.field_policy import Classification
    from brain.custom_connector_routes import DefinitionAsked, EntityAsked, FieldAsked

    return DefinitionAsked(
        name=name,
        label="Acceptance check widgets",
        document=json.dumps(made_up_document()),
        entities=[
            EntityAsked(
                entity=entity,
                list_operation="listWidgets",
                one_operation="getWidget",
                id_path="id",
                named_by=CODE,
                description="Widgets by their code: their state, and their price read live",
                fields=[
                    FieldAsked(
                        target=CODE,
                        source_path="code",
                        classification=Classification.INTERNAL,
                        kept=FieldShape.LABEL,
                    ),
                    FieldAsked(
                        target=STATE,
                        source_path="state",
                        classification=Classification.INTERNAL,
                        kept=FieldShape.STATUS,
                    ),
                    FieldAsked(
                        target=PRICE,
                        source_path="price",
                        classification=Classification.RESTRICTED,
                    ),
                ],
            )
        ],
        key_scheme=KeyScheme.BEARER,
        ceiling_per_minute=60,
        ceiling_per_day=10_000,
        ceiling_cited=f"https://{HOST}/docs/limits",
        department=department,
        page_parameter="page",
        page_size=50,
    )


@dataclass
class _Api:
    """`SourceCaller` answering the made-up API's list and its one widget. No socket."""

    widget: dict[str, str]
    asked: list[str] = field(default_factory=list)

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, headers, max_bytes
        self.asked.append(url)
        path = url.split("?", 1)[0]
        if path.endswith(f"/widgets/{self.widget['id']}"):
            return SourceAnswer(status=200, headers={}, body=json.dumps(self.widget).encode())
        if path.endswith("/widgets"):
            body = {"data": [self.widget]}
            return SourceAnswer(status=200, headers={}, body=json.dumps(body).encode())
        return SourceAnswer(status=404, headers={}, body=b"{}")


async def _approved(h: Harness) -> dict[str, Any]:
    """The approved definitions as the catalogue reads them, inside the check's transaction."""
    from brain.ops.custom_connector_store import approved_in

    async with h.sessions() as session:
        return dict(await approved_in(session))


def _tool_names(h: Harness) -> set[str]:
    """The row tools the registry the application builds would have now."""
    from brain.knowledge.row_store import SessionRowSource
    from brain.tools.startup import build_registry

    registry = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    return {one.name for one in registry.definitions() if one.source}


# ------------------------------------------------------ 1. added, reviewed, connected, asked
@check(
    leaves=("M11.7.8",),
    sentence=(
        "A made-up API is defined from the console by its specification, mapping and key scheme; "
        "unreviewed it is offered nowhere; its submitter cannot approve it and a second person "
        "does; it is connected, read by the worker and answered on Ask to a granted reader and "
        "withheld as absent from another, keeping nothing read live; changed, it waits again."
    ),
)
async def an_api_added_from_the_console_is_read_after_a_second_review(
    h: Harness,
) -> None:
    from brain.api_routes import (
        connected_questions_of,
        covered_at,
        field_policies,
        row_readers,
        source_field_policies,
    )
    from brain.connectors.minimal_index import fresh_canary
    from brain.connectors.registry import INSTALL_AUTHORITY
    from brain.custom_connector_routes import ReviewAsked, changing, deciding, submission
    from brain.gate.answer import answer_lane
    from brain.gate.context import Channel
    from brain.gate.finish import Origin
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.connectable import CONNECTABLE
    from brain.ops.connector_admin import SOURCE_FIELD, connection_problems
    from brain.ops.connector_catalogue import overlaid
    from brain.ops.custom_connector import ReviewState
    from brain.ops.custom_connector_store import StoredCustomConnectors, StoredDefinition
    from brain.ops.live_read_run import ConnectedSources
    from brain.ops.live_records import SourceRecords
    from brain.ops.trace_sink import CountingTraceSink
    from brain.tools.startup import build_registry

    await h.found_departments()
    suffix = secrets.token_hex(5)
    name, entity = f"acceptance_api_{suffix}", f"acceptance_widget_{suffix}"
    tool = f"{name}.read_{entity}"
    authority = Scope(clauses=(Clause(field=SOURCE_FIELD, op=Op.EQ, value=name),))
    definer, reviewer = h.principal(A, "definer"), h.principal(A, "reviewer")
    for person in (definer, reviewer):
        await h.person(person, department=A, grants=((INSTALL_AUTHORITY.value, authority),))
    store = StoredCustomConnectors(h.sessions)

    # 1. Submitted through the routes' own submission, by a person who may connect it.
    defining = await _console(h, definer, second_factor=True)
    body = made_up_definition(name, entity, A)
    kept = await submission(store, body, reach=defining, now=h.now, resolver=_Resolver())
    if not isinstance(kept, StoredDefinition) or kept.state is not ReviewState.UNREVIEWED:
        raise CheckFailedError("a made-up API's definition was not kept waiting for review")

    # 2. Unreviewed, it is offered nowhere and has no tool.
    with overlaid(await _approved(h)):
        if name in CONNECTABLE or tool in _tool_names(h):
            raise CheckFailedError("an unreviewed definition was offered or given a tool")

    # 3. The submitter's own approval is refused.
    own = await deciding(
        store, name, ReviewAsked(approve=True, revision=1), reach=defining, now=h.now
    )
    if not isinstance(own, tuple) or [one.code for one in own] != ["own_definition"]:
        raise CheckFailedError("a definition's submitter approved their own")

    # 4. A second person approves it.
    reviewing = await _console(h, reviewer, second_factor=True)
    approved = await deciding(
        store, name, ReviewAsked(approve=True, revision=1), reach=reviewing, now=h.now
    )
    if not isinstance(approved, StoredDefinition) or approved.reviewed_by != reviewer:
        raise CheckFailedError("a second person's approval was not recorded as theirs")

    with overlaid(await _approved(h)):
        if name not in CONNECTABLE or tool not in _tool_names(h):
            raise CheckFailedError("an approved definition was not offered with its tool")

        # 5. Connected with a key, judged as the Connect route judges it.
        settings = {"department": A}
        if connection_problems(name, settings, secrets.token_urlsafe(24)):
            raise CheckFailedError("an approved definition could not be connected with a key")
        canary = fresh_canary("ACCEPTANCE")
        code = h.word()
        api = _Api({"id": secrets.token_hex(8), CODE: code, STATE: "active", PRICE: canary})

        # 6. Read by the worker from a recorded answer.
        connection = _connection(h, name, settings)
        await _connect_and_read(h, connection, api, at=h.now)

        # 7 and 8. Asked through the answer route's own parts.
        state = SimpleNamespace(db_sessions=h.sessions)
        rules = await connected_questions_of(state)
        if name not in {one.source for one in rules}:
            raise CheckFailedError("an approved, connected definition asked nothing on Ask")
        registry = build_registry(
            source=h.settings.tool_source, records=SessionRowSource(h.sessions)
        )
        readers = row_readers(registry)

        async def connected() -> Any:
            return ConnectedSources(
                {name: connection},
                keys=_Keys(),
                caller=api,
                resolver=_Resolver(),
                clock=lambda: h.now,
            )

        live = SourceRecords(connected=connected, clock=lambda: h.now)

        async def ask(principal_id: str, question: str) -> Answered:
            person = await StoredPrincipals(h.sessions).live_principal(principal_id)
            if person is None:
                raise CheckFailedError("a reserved person was not live in the directory")
            reach: EntitlementSet = await _console(h, principal_id, second_factor=False)
            return await answer_lane(
                question,
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
                live=live,
                source_policies=source_field_policies(registry),
            )

        def asking(field_name: str, slot: str) -> str:
            return QUESTION_SHAPES[0].format(label=label_of(field_name), slot=slot)

        reads = (f"read:{entity}", f"read:{entity}.{CODE}", f"read:{entity}.{STATE}")
        granted, other = h.principal(A, "pricing"), h.principal(A, "counter")
        in_a = Scope.department(A)
        await h.person(
            granted,
            department=A,
            grants=tuple((one, in_a) for one in (*reads, f"read:{entity}.{PRICE}")),
        )
        await h.person(other, department=A, grants=tuple((one, in_a) for one in reads))
        told = await ask(granted, asking(PRICE, code))
        if told.composed is None or canary not in _prose(told):
            raise CheckFailedError("a granted reader was not told a field read live from the API")
        withheld = await ask(other, asking(PRICE, code))
        nobody = await ask(other, asking(PRICE, h.word()))
        if canary in _prose(withheld) or _prose(withheld) != _prose(nobody):
            raise CheckFailedError("a field was told apart from a record that is not there")

        # 9. Nothing read live is kept beyond the minimal index.
        if await _search(h, canary):
            raise CheckFailedError("a value read live from the API was found in a table")

    # Changed after approval, it waits for a second person again and is in no list.
    changed = await changing(store, name, body, reach=defining, now=h.now, resolver=_Resolver())
    if not isinstance(changed, StoredDefinition) or changed.state is not ReviewState.UNREVIEWED:
        raise CheckFailedError("a definition changed after approval did not wait for review")
    with overlaid(await _approved(h)):
        if name in CONNECTABLE or tool in _tool_names(h):
            raise CheckFailedError("a definition changed after approval was still offered")
