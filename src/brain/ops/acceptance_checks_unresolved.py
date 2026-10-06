"""A name two clients share, asked on an install: the asker reading both is told it could not tell
which, a reviewer is handed the review, and an asker reading one is answered as if the other did
not exist (M14.6.5).

The check uploads a price list through the Classification screen's steps (`acceptance_checks_tables`
holds them), with two rows of one name placed in two departments, and asks it on Ask's own lane,
`brain.gate.answer.answer_lane`, with the registry reader the answer route hands it
(`brain.api_routes.ambiguity_of`). Everything is inside the check's transaction.

**The registry is told the two rows are companies, for the check only.** On an install the records
the registry links are connector records, read live, which a check cannot hold still; a table's rows
are read by the same lane and the same row plane at the same reach, so the check declares the
table as a company source, writes each row where a sync would leave it, and registers and matches
them with the worker's own `StoredRegistry` and `StoredMatching`. Two companies with one name and
nothing else in common are put to a person, so a review item is open between them, which is the
state a reviewer's link is about.

**Three readers, and the third is the one the leaf is held to.** An asker reading both rows is told
the one sentence and neither figure. A reviewer reading both, holding the reviewer's capability
over everything on a session with a second factor, is told where to check it. An asker reading
only the first row's department is asked twice, before the second row exists and after, and the
two replies must be the same bytes: a withheld record must not make a name ambiguous.

Task ids: M14.6.5
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from sqlalchemy import insert, text

from brain.core.scope import Clause, Op, Scope
from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_checks import _in
from brain.ops.acceptance_checks_tables import (
    ASKED_COLUMNS,
    ASKED_HEADINGS,
    SELL_PRICE,
    A,
    B,
    _Administrator,
    _Application,
    _apply,
    _console,
    _PriceList,
    _upload,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.connectors.resolves import ResolvesAs
    from brain.core.entitlement import EntitlementSet
    from brain.core.principal import Principal
    from brain.gate.answer import Answered

#: Where this module's check sits on the acceptance page, after the review screen's.
CHECK_ORDER: Final = 440

WITHHELD_RECORD_TOLD: Final = (
    "an asker reading one of two records with one name was not answered exactly as when the "
    "second record did not exist"
)
NOT_NAMED_AMBIGUOUS: Final = (
    "an asker reading two clients with one name was not told it could not tell which, or was "
    "told a figure"
)
LINK_TO_A_NON_REVIEWER: Final = "the review reference was shown to somebody who is not a reviewer"
REVIEWER_NOT_LINKED: Final = "a reviewer was not handed the review reference for the two clients"


def _declared(entity: str) -> Mapping[tuple[str, str], ResolvesAs]:
    """Every shipped declaration, and the check's table as a company source keeping a name."""
    from brain.connectors.resolves import ResolvesAs
    from brain.knowledge.classified_rows import TABLES_SOURCE
    from brain.resolution.canonical import EntityType
    from brain.resolution.sources import resolved_entities

    return MappingProxyType(
        {
            **resolved_entities(),
            (TABLES_SOURCE, entity): ResolvesAs(
                entity=entity, entity_type=EntityType.COMPANY, fields={"name": "name"}
            ),
        }
    )


async def _positions(h: Harness, entity: str, name: str) -> list[str]:
    """The ids the row plane gives the rows of the table's live version named `name`. The name is
    compared here rather than in the statement, so no scope-shaped JSON test is written outside
    `brain.core.scope_sql`."""
    rows = await h.execute(
        text(
            "SELECT r.position, r.fields FROM know.classified_row r JOIN know.classified_table t"
            " ON t.entity = r.entity AND t.version = r.version"
            " WHERE r.entity = :entity ORDER BY r.position"
        ).bindparams(entity=entity)
    )
    # A JSONB value arrives decoded: psycopg, the application's driver, loads it.
    return [str(position) for position, fields in rows.all() if dict(fields).get("name") == name]


async def _ask(h: Harness, person: Principal, reach: EntitlementSet, name: str) -> Answered:
    """The sell price of `name`, on Ask's lane with the registry reader the answer route uses."""
    from brain.api_routes import ambiguity_of
    from brain.gate.answer import answer_lane
    from brain.gate.context import Channel
    from brain.gate.finish import Origin
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of
    from brain.ops.classification_store import classified_lane_of
    from brain.ops.trace_sink import CountingTraceSink

    state = _Application(h.sessions)
    lane = await classified_lane_of(state)
    now = h.now
    return await answer_lane(
        QUESTION_SHAPES[0].format(label=label_of(SELL_PRICE), slot=name),
        origin=Origin(trace_id=f"{h.trace_id}-ask", principal=person, channel=Channel.CONSOLE),
        recorders=(),
        rules=lane.rules,
        readers=lane.readers,
        entitlement=reach,
        policies=lane.policies,
        reachable_sources=(),
        sink=CountingTraceSink(),
        now=now,
        clock=lambda: now,
        ambiguity=ambiguity_of(state),
    )


async def _reader(
    h: Harness,
    role: str,
    grants: Sequence[tuple[str, Scope]],
    *,
    second_factor: bool = False,
) -> tuple[Principal, EntitlementSet]:
    from brain.identity.principal_store import StoredPrincipals

    made = h.principal(_A, role)
    await h.person(made, department=_A, grants=tuple(grants))
    person = await StoredPrincipals(h.sessions).live_principal(made)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    return person, await _console(h, made, second_factor=second_factor)


def _row(name: str, department: str, price: str) -> dict[str, str]:
    return {
        "name": name,
        "department": department,
        SELL_PRICE: price,
        "cost": f"c{secrets.token_hex(4)}",
        "margin": f"m{secrets.token_hex(4)}",
    }


_A: Final = A
_B: Final = B


def _in_both(*capabilities: str) -> tuple[tuple[str, Scope], ...]:
    """Each capability over both departments, as one grant: a person holds one live grant of a
    capability, so two departments are one scope rather than two grants."""
    scope = Scope(clauses=(Clause(field="department", op=Op.IN, value=(_A, _B)),))
    return tuple((one, scope) for one in capabilities)


@check(
    leaves=("M14.6.5",),
    sentence=(
        "Two rows of one name, in two departments, registered as two companies with a review item "
        "open between them: an asker reading both is told it could not tell which client and "
        "neither price, a reviewer is handed the review, and an asker reading one department is "
        "answered exactly as before the second row existed."
    ),
)
async def a_shared_name_is_named_and_a_withheld_record_changes_nothing(
    h: Harness,
) -> None:
    from brain.classification_routes import CLASSIFICATION_READ, CLASSIFICATION_WRITE
    from brain.gate.streaming import Event, encode, frames
    from brain.knowledge.classified_rows import TABLES_SOURCE
    from brain.knowledge.columns import ColumnAccess, table_capability
    from brain.resolution.canonical import SourceRef
    from brain.resolution.guardrails import (
        REVIEWER_CAPABILITY,
        UNRESOLVED_TEXT,
        UnresolvedNotice,
    )
    from brain.resolution.matching_store import StoredMatching
    from brain.resolution.registry_store import StoredRegistry
    from brain.tables.projection import ProjectedRecordRow

    await h.found_departments()
    entity = f"acceptance_{h.run}_clients"
    name, filler = h.word(), h.word()
    first, second = (_row(name, _A, h.word()), _row(name, _B, h.word()))
    other = _row(filler, _A, h.word())

    made = h.principal(_A, "classifier")
    caps = (CLASSIFICATION_READ.value, CLASSIFICATION_WRITE.value)
    await h.person(made, department=_A, grants=_in_both(*caps))
    admin = _Administrator(made, await _console(h, made, second_factor=True))

    async def uploaded(*rows: dict[str, str]) -> None:
        prices = _PriceList(
            entity=entity,
            headings=ASKED_HEADINGS,
            columns=ASKED_COLUMNS,
            rows=tuple(rows),
        )
        await _upload(h, admin, prices, filename=f"{entity}.csv", content=prices.csv())
        opened = await _apply(h, admin, entity, "department", ColumnAccess.OPEN)
        if not opened.applied:
            raise CheckFailedError("an uploaded table's department column could not be opened")

    table = table_capability(entity).value
    one_person, one = await _reader(h, "one", _in(_A, table))
    both_person, both = await _reader(h, "both", _in_both(table))
    reviewer_person, reviewer = await _reader(
        h,
        "reviewer",
        (*_in_both(table), (REVIEWER_CAPABILITY.value, Scope.unrestricted())),
        second_factor=True,
    )

    # Before the second row exists: what the one-department asker is told.
    await uploaded(first, other)
    absent = await _ask(h, one_person, one, name)

    # The second row, registered with the first as two companies and matched by the worker's own
    # cascade, which puts two equal names with nothing else in common to a person.
    await uploaded(first, other, second)
    refs = []
    for position, row in zip(await _positions(h, entity, name), (first, second), strict=True):
        await h.execute(
            *h.attributed(),
            insert(ProjectedRecordRow).values(
                source=TABLES_SOURCE,
                entity=entity,
                source_id=position,
                last_seen_at=h.now,
                fields={"name": row["name"]},
            ),
        )
        refs.append(SourceRef(source=TABLES_SOURCE, entity=entity, source_id=position))
    pepper, declared = secrets.token_hex(32), _declared(entity)
    await StoredRegistry(h.sessions, declared=declared).register(
        refs, pepper=pepper, now=h.now, by=h.actor
    )
    await StoredMatching(h.sessions, declared=declared).match(refs, pepper=pepper, now=h.now)
    item = (
        await h.execute(
            text(
                "SELECT item_id FROM er.review_item WHERE state = 'open'"
                " AND left_source = :source AND left_entity = :entity"
                " AND right_entity = :entity"
            ).bindparams(source=TABLES_SOURCE, entity=entity)
        )
    ).scalar_one_or_none()
    if item is None:
        raise CheckFailedError(
            "two companies with one name and nothing else were not put to a person"
        )

    withheld = await _ask(h, one_person, one, name)
    if withheld.frames != absent.frames or first[SELL_PRICE] not in frames(withheld.frames):
        raise CheckFailedError(WITHHELD_RECORD_TOLD)

    told = await _ask(h, both_person, both, name)
    body = frames(told.frames)
    if str(item) in body:
        raise CheckFailedError(LINK_TO_A_NON_REVIEWER)
    if (
        encode(Event.TEXT, UNRESOLVED_TEXT) not in told.frames
        or first[SELL_PRICE] in body
        or second[SELL_PRICE] in body
    ):
        raise CheckFailedError(NOT_NAMED_AMBIGUOUS)

    linked = await _ask(h, reviewer_person, reviewer, name)
    if encode(Event.TEXT, UnresolvedNotice(review_ref=str(item)).render()) not in linked.frames:
        raise CheckFailedError(REVIEWER_NOT_LINKED)
