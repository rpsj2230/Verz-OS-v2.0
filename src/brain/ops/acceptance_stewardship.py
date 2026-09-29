"""The install acceptance check for stewardship: a source's steward named, and told of a self-grant.

M7.7.2 has two halves and one sentence. A connected source names its steward, set on the source's
page by whoever governs it and only ever to somebody who can reach it; and when anybody grants
themselves access, the steward of each document, source or agent the grant reaches is the person
told. The per-document hand-over has its own proof already, in the document's whole life
(`brain.ops.acceptance_knowledge`); this check is the source's steward and the notice.

**It is the routes' own functions, in the routes' order, and restates no rule.** Naming a steward is
`brain.connector_routes`: `may_connect_source` for the person naming, `may_steward` for the person
named, then `StoredStewardship.name`, whose ledger entry `0167`'s trigger appends. The self-grant is
`brain.govern_routes.grant`'s sequence: the scope row, `proposal_from`, `write_grant`, the
transaction attributed to the person, and `add_grant`; nothing tells the database it is a
self-grant, which is the point, because `0167` recognises one from the attribution alone. The
notice is `brain.stewardship_routes.things_stewarded` and `brain.identity.stewardship.notices_for`,
which is exactly what `GET /stewardship/self-grants` answers with. See
`A_CHECK_IS_THE_ROUTES_SEQUENCE_AND_NOT_A_SECOND_COPY_OF_ITS_RULES`.

**Only the check's own grants are asserted on.** The notice list is built from every self-grant on
the install in the window, as the route builds it, and a real administrator may have granted
themselves something that reaches the same source this morning. A check asserting the whole list
would fail on an install doing exactly what it should; so each assertion is about the grants the
check's own person made, and the rest of the list is read and left alone. See
`ONLY_THE_CHECK_S_OWN_GRANTS_ARE_ASSERTED_ON`.

**The source is the install's own if it is connected, and connected in the check if not.** Naming a
steward needs a live connection. A live one is used as it is, because everything the check writes
about it is rolled back with the check; an absent one is connected through the store the
Connectors screen's routes call, as `brain.ops.acceptance_checks_connectors` connects it.

Task ids: M38.5.1
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _ledger
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from collections.abc import Sequence

    from brain.identity.stewardship import StewardedKind
    from brain.ops.connector_store import Connection
    from brain.ops.stewardship_store import StoredStewardship

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the check calls the routes' functions rather than restating what they decide.
A_CHECK_IS_THE_ROUTES_SEQUENCE_AND_NOT_A_SECOND_COPY_OF_ITS_RULES: Final = (
    "Naming a steward, writing a grant and listing a steward's notices are each the route's own "
    "functions in the route's order, so a check that passes is the install doing what the "
    "screens do, and a rule changed in a route is changed here without an edit."
)

#: Why the notice assertions are filtered to the check's own grants.
ONLY_THE_CHECK_S_OWN_GRANTS_ARE_ASSERTED_ON: Final = (
    "A steward's list holds every self-grant on the install in the window that reaches what they "
    "steward, and a real administrator may have made one. The check asserts on the grants its own "
    "person made and reads the rest without judging them."
)

#: The capability the check's person grants themselves over the source's invoices. A field under
#: `read:invoice.*`, which the source declares, so it reaches the source and no document.
INVOICE_FIELD: Final = "read:invoice.total"

#: The capability the check's person grants themselves over the knowledge in acceptance_a. A field
#: under `read:knowledge`, so it reaches a document there and not the source.
KNOWLEDGE_FIELD: Final = "read:knowledge.title"

#: Why the check's person grants themselves each of the two, as the grant's reason reads.
SELF_GRANT_REASON: Final = "An install acceptance check grants itself this to see who is told"


@check(
    leaves=("M7.7.2",),
    sentence=(
        "A source's administrator names a reader of its invoices its steward, and the ledger "
        "records it; a person who cannot reach it, or is not here, cannot be named. Somebody "
        "then grants themselves an invoice field and a knowledge field: the source's steward is "
        "told of the first, a document's steward of the second, and the administrator of neither."
    ),
)
async def a_steward_is_named_and_told_of_access_somebody_gave_themselves(h: Harness) -> None:
    from brain.connector_routes import may_steward
    from brain.connectors.manifest import manifest_digest
    from brain.connectors.registry import INSTALL_AUTHORITY
    from brain.console.organisation import founded
    from brain.console.scoped_authority import REACH_AUTHORITY
    from brain.core.scope import Clause, Op, Scope
    from brain.identity.stewardship import NOTICE_WINDOW, StewardedKind
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.ops.acceptance_checks_connectors import SOURCE, _nothing_kept, _settings
    from brain.ops.acceptance_checks_lifecycle import _added
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_admin import may_connect_source
    from brain.ops.connector_store import StoredConnections, live
    from brain.ops.stewardship_store import StoredStewardship

    await h.found_departments()
    admin, reader = h.principal(A, "admin"), h.principal(A, "invoices")
    steward, granter = h.principal(A, "steward"), h.principal(B, "granter")
    only_the_source = Scope(clauses=(Clause(field="connector", op=Op.EQ, value=SOURCE),))
    await h.person(admin, department=A, grants=((INSTALL_AUTHORITY.value, only_the_source),))
    await h.person(reader, department=A, grants=_in(A, "read:invoice.*"))
    await h.person(steward, department=A, grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value))
    await h.person(
        granter,
        department=B,
        grants=_in(A, REACH_AUTHORITY.value, "read:invoice.*", "read:knowledge.*"),
    )

    connections = StoredConnections(h.sessions)
    if (await h.execute(live(SOURCE))).scalar_one_or_none() is None:
        settings = _settings()
        await connections.connect(
            connector=SOURCE,
            settings=settings,
            digest=manifest_digest(manifest_for(SOURCE, settings)),
            actor=h.actor,
            trace_id=h.trace_id,
            ent_hash=SET_UP_REACH,
            keep_key=_nothing_kept,
        )
    connected = await connections.connected()
    source = next((one for one in connected if one.connector == SOURCE), None)
    if source is None:
        raise CheckFailedError("the source the check connected was not read back as connected")

    # 1. Named: by the person who governs the source, only to somebody who can reach it.
    store = StoredStewardship(h.sessions)
    governing = await h.reach(admin)
    if not may_connect_source(governing, SOURCE, h.now):
        raise CheckFailedError("the source's administrator was refused the steward form")
    if may_connect_source(await h.reach(reader), SOURCE, h.now):
        raise CheckFailedError("a reader of the source's invoices was offered the steward form")
    for cannot in (steward, h.principal(A, "nobody")):
        if await may_steward(h.sessions, cannot, source, h.now):
            raise CheckFailedError("a person who cannot reach the source could be its steward")
    if not await may_steward(h.sessions, reader, source, h.now):
        raise CheckFailedError("a reader of what the source declares could not be its steward")
    await store.name(SOURCE, reader, by=admin, ent_hash=governing.ent_hash(), trace_id=h.trace_id)
    if await store.steward_of(SOURCE, connected_by=source.connected_by) != reader:
        raise CheckFailedError("the source did not name the steward it was just given")
    entries = await _ledger(h, f"connector:{SOURCE}")
    if not entries or entries[-1] != (admin, {"change": "steward", "steward": reader}):
        raise CheckFailedError("naming the source's steward is not in the ledger under who named")

    # 2. A document in acceptance_a, whose steward is the person who added it.
    document = await _added(h, steward, h.word())

    # 3. Granted to themselves, through the grant route's own sequence.
    scope_slug = founded(A, "Acceptance check A")[1].slug
    for capability in (INVOICE_FIELD, KNOWLEDGE_FIELD):
        if not await _granted_to_themselves(h, granter, capability, scope_slug):
            raise CheckFailedError("a grant the grant route admits could not be written")

    # 4. Told: each steward of the check's own grant that reaches what they steward, nobody else.
    grants = await store.self_grants(h.now - NOTICE_WINDOW)
    told = {
        person: await _told(h, store, connected, person, granter)
        for person in (reader, steward, admin)
    }
    if told[reader] != [((INVOICE_FIELD,), ((StewardedKind.SOURCE, SOURCE),))]:
        raise CheckFailedError("the source's steward was not told of the invoice grant alone")
    if told[steward] != [((KNOWLEDGE_FIELD,), ((StewardedKind.DOCUMENT, document),))]:
        raise CheckFailedError("the document's steward was not told of the knowledge grant alone")
    if told[admin]:
        raise CheckFailedError("somebody who stewards nothing the grants reach was told of them")
    if not any(one.principal_id == granter for one in grants):
        raise CheckFailedError("a grant somebody made to themselves was not recorded")


async def _granted_to_themselves(h: Harness, person: str, capability: str, slug: str) -> bool:
    """`brain.govern_routes.grant`'s sequence, with the person granting to themselves.

    False where the route answers its one refusal, which the check reports as a failure: the
    person holds the authority and the capability over the scope, so the route admits it.
    """
    from sqlalchemy.exc import IntegrityError

    from brain.console.scoped_authority import AuthorityError, write_grant
    from brain.core.department import ScopeRecord
    from brain.govern_routes import GrantProposal, add_grant, one_live_scope, proposal_from
    from brain.ops.acceptance_run import RESERVED_REACH_LASTS
    from brain.tables.audit import attributed_to

    reach = await h.reach(person)
    body = GrantProposal(
        principal_id=person,
        capability=capability,
        scope_slug=slug,
        reason=SELF_GRANT_REASON,
        not_after=h.now + RESERVED_REACH_LASTS / 2,
    )
    async with h.sessions() as session:
        row = (await session.execute(one_live_scope(slug))).scalar_one_or_none()
        if row is None:
            return False
        try:
            record = ScopeRecord.from_predicate(
                row.slug, row.predicate, is_department=row.is_department, label=row.label
            )
            written = write_grant(proposal_from(body, record, person, h.now), reach, h.now)
        except (ValueError, AuthorityError):
            return False
        for statement in attributed_to(
            actor_id=person, ent_hash=reach.ent_hash(), trace_id=h.trace_id
        ):
            await session.execute(statement)
        try:
            stored = (await session.execute(add_grant(written, person))).scalar_one_or_none()
        except IntegrityError:
            return False
        await session.commit()
        return stored is not None


async def _told(
    h: Harness,
    store: StoredStewardship,
    connected: Sequence[Connection],
    person: str,
    granter: str,
) -> list[tuple[tuple[str, ...], tuple[tuple[StewardedKind, str], ...]]]:
    """What `GET /stewardship/self-grants` tells `person` of `granter`'s grants: the capabilities
    of each notice and the kind and id of each thing of theirs it reaches."""
    from brain.identity.stewardship import NOTICE_WINDOW, notices_for
    from brain.ops.acceptance_checks_lifecycle import _as
    from brain.stewardship_routes import things_stewarded

    authority = (await _as(h, person)).authority
    things = await things_stewarded(store, connected, person, authority)
    grants = await store.self_grants(h.now - NOTICE_WINDOW)
    return [
        (
            tuple(one.value for one in notice.grant.capabilities),
            tuple((thing.kind, thing.object_id) for thing in notice.reached),
        )
        for notice in notices_for(person, grants, things)
        if notice.grant.principal_id == granter
    ]
