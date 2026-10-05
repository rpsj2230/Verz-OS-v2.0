"""`ops.custom_connector` as the application role: submit, change, decide, and the approved set.

`brain.ops.custom_connector` says what a definition is and compiles one; this keeps them and reads
them back. Three writes and two reads, and one function the rest of the product calls: `refresh`,
which reads the approved rows and lays them under the shipped connectors
(`brain.ops.connector_catalogue.install`), at the start of every request and every worker cycle.

**Nobody approves their own, refused here before the database refuses it too.** `decide` refuses a
reviewer who submitted the revision under review (`OwnDefinitionError`), and the row's check
constraint and the update policy refuse the same write, so a route that forgot to ask could not make
it. See `NOBODY_APPROVES_THEIR_OWN_DEFINITION`.

**A decision names the revision it was made on.** A reviewer approves what they read, so `decide`
takes the revision the review screen showed and refuses one that has moved since
(`DefinitionMovedError`). Without it, an edit landing between reading and approving would be
approved unread, which is the change-after-approval this leaf takes care to send back for review.

**A change always goes back to waiting.** `change` writes the new definition, bumps the revision,
sets the state to unreviewed and clears the reviewer in one statement, so there is no moment in
which a changed definition is approved. See `A_CHANGED_DEFINITION_WAITS_FOR_A_SECOND_PERSON_AGAIN`.

**A stored definition that no longer compiles is left out of the catalogue, not half-offered.** It
was judged at submit; one that fails now (a document this release reads more strictly, say) is
logged by name and skipped, so the screen shows it as not connectable rather than a form that builds
nothing.

Task ids: M11.7.8
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.declaration import ConnectorDeclaration, CredentialShape, KeyScheme
from brain.connectors.manifest import FieldShape
from brain.core.field_policy import Classification
from brain.ops import connector_catalogue
from brain.ops.custom_connector import (
    Ceiling,
    CustomDefinition,
    EntityDefinition,
    MappedField,
    ReviewState,
    declaration_of,
)
from brain.tables.audit import attributed_to
from brain.tables.custom_connector import CustomConnectorRow

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons
#: Why a submitter cannot approve their own definition.
NOBODY_APPROVES_THEIR_OWN_DEFINITION: Final = (
    "A connector added from the console reads a company's data with a key the company gave it, "
    "and the review is the only thing standing in for the release a shipped connector goes "
    "through. So a second person holding the authority to connect it approves it, never the "
    "person who submitted the revision under review, and the database refuses the same write."
)

#: Why a change sends a definition back for review.
A_CHANGED_DEFINITION_WAITS_FOR_A_SECOND_PERSON_AGAIN: Final = (
    "An approval is of what the reviewer read. A definition changed after it was approved is not "
    "what anybody approved, so the change sets it back to waiting in the statement that writes "
    "it: it is not offered, has no tool and is not read until a second person approves it again."
)


class DefinitionTakenError(Exception):
    """A definition by that name exists already; changing it is a change, not a submission."""


class NoSuchDefinitionError(Exception):
    """No definition by that name."""


class OwnDefinitionError(Exception):
    """The reviewer submitted the revision under review. See the named constant."""


class DefinitionMovedError(Exception):
    """The revision reviewed is not the definition's revision now, or it was decided already."""


@dataclass(frozen=True)
class StoredDefinition:
    """One definition as kept: what it says, where its review stands, and who did what."""

    definition: CustomDefinition
    state: ReviewState
    submitted_by: str
    submitted_at: datetime
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


# ------------------------------------------------------------------------ the row's shape
def entities_json(definition: CustomDefinition) -> list[dict[str, Any]]:
    """Each entity as the row's JSON holds it."""
    return [
        {
            "entity": one.entity,
            "list_operation": one.list_operation,
            "one_operation": one.one_operation,
            "id_path": one.id_path,
            "named_by": one.named_by,
            "description": one.description,
            "fields": [
                {
                    "target": field.target,
                    "source_path": field.source_path,
                    "classification": field.classification.value,
                    "kept": None if field.kept is None else field.kept.value,
                }
                for field in one.fields
            ],
        }
        for one in definition.entities
    ]


def entities_of(raw: list[dict[str, Any]]) -> tuple[EntityDefinition, ...]:
    """The row's JSON as entities. Raises for JSON this module did not write."""
    return tuple(
        EntityDefinition(
            entity=str(one["entity"]),
            list_operation=str(one["list_operation"]),
            one_operation=None if one.get("one_operation") is None else str(one["one_operation"]),
            id_path=str(one["id_path"]),
            named_by=str(one["named_by"]),
            description=str(one["description"]),
            fields=tuple(
                MappedField(
                    target=str(field["target"]),
                    source_path=str(field["source_path"]),
                    classification=Classification(field["classification"]),
                    kept=None if field.get("kept") is None else FieldShape(field["kept"]),
                )
                for field in one["fields"]
            ),
        )
        for one in raw
    )


def definition_of(row: CustomConnectorRow) -> CustomDefinition:
    return CustomDefinition(
        name=row.name,
        label=row.label,
        document=row.document,
        entities=entities_of(row.entities),
        key_scheme=KeyScheme(row.key_scheme),
        credential_shape=CredentialShape(row.credential_shape),
        ceiling=Ceiling(
            per_minute=row.ceiling_per_minute,
            per_day=row.ceiling_per_day,
            cited=row.ceiling_cited,
        ),
        department=row.department,
        page_parameter=row.page_parameter,
        page_size=row.page_size,
        revision=row.revision,
    )


def stored_of(row: CustomConnectorRow) -> StoredDefinition:
    return StoredDefinition(
        definition=definition_of(row),
        state=ReviewState(row.state),
        submitted_by=row.submitted_by,
        submitted_at=row.submitted_at,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
    )


def _columns(definition: CustomDefinition) -> dict[str, Any]:
    """Every column a definition writes. A definition with no ceiling was refused before this."""
    ceiling = definition.ceiling
    if ceiling is None:
        msg = "a definition with no ceiling reached the store"
        raise ValueError(msg)
    return {
        "label": definition.label,
        "document": dict(definition.document),
        "entities": entities_json(definition),
        "key_scheme": definition.key_scheme.value,
        "credential_shape": definition.credential_shape.value,
        "ceiling_per_minute": ceiling.per_minute,
        "ceiling_per_day": ceiling.per_day,
        "ceiling_cited": ceiling.cited,
        "department": definition.department,
        "page_parameter": definition.page_parameter,
        "page_size": definition.page_size,
    }


# ------------------------------------------------------------------------ the approved set
#: Compiled declarations by name and revision, so a revision is compiled once per process.
_compiled: dict[tuple[str, int], ConnectorDeclaration] = {}


async def approved_in(session: AsyncSession) -> dict[str, ConnectorDeclaration]:
    """Every approved definition, compiled, by name. One that no longer compiles is left out."""
    rows = (
        (
            await session.execute(
                select(CustomConnectorRow).where(
                    CustomConnectorRow.state == ReviewState.APPROVED.value
                )
            )
        )
        .scalars()
        .all()
    )
    found: dict[str, ConnectorDeclaration] = {}
    for row in rows:
        key = (row.name, row.revision)
        declared = _compiled.get(key)
        if declared is None:
            try:
                declared = declaration_of(definition_of(row))
            except Exception:
                log.warning("an approved connector definition no longer compiles", name=row.name)
                continue
            _compiled[key] = declared
        found[row.name] = declared
    return found


async def refresh(sessions: async_sessionmaker[AsyncSession] | None) -> bool:
    """Read the approved set and serve it from now on. True when it changed.

    An install with no database serves none. A read that fails serves none too, rather than the
    set read before it: a definition could have been changed since, and an unreadable catalogue
    offering what it last saw is a catalogue offering what nobody may have approved.
    """
    if sessions is None:
        return connector_catalogue.install({})
    try:
        async with sessions() as session:
            found = await approved_in(session)
    except Exception:
        log.warning("the approved connector definitions could not be read")
        return connector_catalogue.install({})
    return connector_catalogue.install(found)


# ------------------------------------------------------------------------------ the store
class StoredCustomConnectors:
    """`ops.custom_connector`, as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def listed(self) -> tuple[StoredDefinition, ...]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(CustomConnectorRow).order_by(CustomConnectorRow.name)
                    )
                )
                .scalars()
                .all()
            )
        return tuple(stored_of(row) for row in rows)

    async def one(self, name: str) -> StoredDefinition | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(CustomConnectorRow).where(CustomConnectorRow.name == name)
                )
            ).scalar_one_or_none()
        return None if row is None else stored_of(row)

    async def submit(
        self, definition: CustomDefinition, *, by: str, ent_hash: str, trace_id: str
    ) -> StoredDefinition:
        """Keep a new definition, waiting for review, attributed to `by`."""
        try:
            async with self._sessions() as session, session.begin():
                for statement in attributed_to(actor_id=by, ent_hash=ent_hash, trace_id=trace_id):
                    await session.execute(statement)
                row = CustomConnectorRow(
                    name=definition.name,
                    state=ReviewState.UNREVIEWED.value,
                    revision=1,
                    submitted_by=by,
                    **_columns(definition),
                )
                session.add(row)
                await session.flush()
                await session.refresh(row)
                return stored_of(row)
        except IntegrityError as exc:
            msg = f"a definition named {definition.name!r} exists"
            raise DefinitionTakenError(msg) from exc

    async def change(
        self, definition: CustomDefinition, *, by: str, ent_hash: str, trace_id: str
    ) -> StoredDefinition:
        """Write a changed definition, a new revision waiting for review, attributed to `by`.

        See `A_CHANGED_DEFINITION_WAITS_FOR_A_SECOND_PERSON_AGAIN`.
        """
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(actor_id=by, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            row = (
                await session.execute(
                    select(CustomConnectorRow)
                    .where(CustomConnectorRow.name == definition.name)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                raise NoSuchDefinitionError(definition.name)
            await session.execute(
                update(CustomConnectorRow)
                .where(CustomConnectorRow.id == row.id)
                .values(
                    state=ReviewState.UNREVIEWED.value,
                    revision=row.revision + 1,
                    submitted_by=by,
                    submitted_at=func.now(),
                    reviewed_by=None,
                    reviewed_at=None,
                    **_columns(definition),
                )
            )
            await session.refresh(row)
            return stored_of(row)

    async def decide(
        self,
        name: str,
        *,
        approve: bool,
        revision: int,
        by: str,
        at: datetime,
        ent_hash: str,
        trace_id: str,
    ) -> StoredDefinition:
        """Approve or reject the revision `revision` of a definition, as `by`, or refuse.

        See `NOBODY_APPROVES_THEIR_OWN_DEFINITION` and the module docstring on the revision.
        """
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(actor_id=by, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            row = (
                await session.execute(
                    select(CustomConnectorRow)
                    .where(CustomConnectorRow.name == name)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                raise NoSuchDefinitionError(name)
            if row.submitted_by == by:
                raise OwnDefinitionError(NOBODY_APPROVES_THEIR_OWN_DEFINITION)
            if row.revision != revision or row.state != ReviewState.UNREVIEWED.value:
                msg = f"revision {revision} of {name!r} is not the one waiting for review"
                raise DefinitionMovedError(msg)
            state = ReviewState.APPROVED if approve else ReviewState.REJECTED
            await session.execute(
                update(CustomConnectorRow)
                .where(CustomConnectorRow.id == row.id)
                .values(state=state.value, reviewed_by=by, reviewed_at=at)
            )
            await session.refresh(row)
            return stored_of(row)
