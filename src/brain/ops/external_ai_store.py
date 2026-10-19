"""Where an install keeps the outside AI services it has declared: rows of `ops.setting`.

`brain.tools.external_ai` decides what a declaration is and what registering one means. This is the
half that holds them, and it holds them where the install's other switches and knobs already live,
under the namespace `external_ai`, one JSON row per service: `external_ai.<service>`.

**`ops.setting` and not a table of their own**, for the reason `brain.ops.setting_store` gives
about a switch: it already holds a value with its type pinned, who changed it last and when, a key
grammar no permission can parse as, and an audit entry appended in the same transaction by `0059`'s
trigger on every write that moves a row. A table of their own would need a migration, a policy and
a registration to hold four small fields. The row never holds a key: a declaration has no field one
could arrive in, and `brain.tables.config` refuses secrets in this table in its own words.

**A row that no longer constructs is absent, not a fault.** `declared_in` reads what the table
holds and skips, and logs by the kind of failure alone, any row whose value is not a declaration
that validates, or whose key does not name the service inside it. One row somebody wrote by hand
must not stop every other service registering, or the application starting.

**A service is retired, never deleted**, as every switch here is: the value stays on the row and the
ledger names who removed it.

**Nothing here is a route.** Declaring a service is a write this module offers and no screen calls
yet; the leaf does not ask for a screen, and a screen over a switch that is off and a call that does
not exist is a screen that cannot be tried. The install check declares one the way a screen would.

Task ids: M12.3.7
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import structlog
from pydantic import ValidationError
from sqlalchemy import Update, func, update
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.features import is_on
from brain.ops.features_declared.external_ai_services import EXTERNAL_AI_SERVICES
from brain.ops.setting_store import SettingState, put_statement, read_namespace, values_under
from brain.tables.audit import attributed_to
from brain.tables.config import SettingRow, SettingType
from brain.tools.external_ai import ExternalAiService

log = structlog.get_logger(__name__)

#: The `ops.setting` namespace every declaration sits under: `external_ai.<service>`.
NAMESPACE: Final = "external_ai"

#: What a row says about itself, which is product text and never a value an administrator typed.
DESCRIPTION: Final = "An outside AI service this install has declared."


def key_of(service: str) -> str:
    """The row a service is kept in."""
    return f"{NAMESPACE}.{service}"


def service_statement(service: ExternalAiService, *, by: str) -> Insert:
    """The one write that declares (or redeclares) a service, as a statement a caller may join.

    Built from the validated declaration and never from text, so what is stored is what the
    declaration allows and nothing a caller added beside it.
    """
    return put_statement(
        key_of(service.service),
        value_type=SettingType.JSON,
        value=stored_value(service),
        description=DESCRIPTION,
        updated_by=by,
    )


async def record_service(
    session: AsyncSession, service: ExternalAiService, *, actor: str, ent_hash: str, trace_id: str
) -> None:
    """Declare a service in the caller's transaction, attributed. The caller commits.

    The attribution is set here, before the write and in its transaction, because the ledger entry
    `0059`'s trigger appends reads who, at what reach and for which request from the transaction
    and writes thirty-two zeros when nothing set them (`brain.ops.write_attribution`). A writer
    that left it to its caller would be a placeholder waiting for whoever called it first.
    """
    for statement in attributed_to(actor_id=actor, ent_hash=ent_hash, trace_id=trace_id):
        await session.execute(statement)
    await session.execute(service_statement(service, by=actor))


async def retire_service(
    session: AsyncSession, service: str, *, actor: str, ent_hash: str, trace_id: str
) -> None:
    """Retire a declaration in the caller's transaction, attributed. The caller commits."""
    for statement in attributed_to(actor_id=actor, ent_hash=ent_hash, trace_id=trace_id):
        await session.execute(statement)
    await session.execute(retire_statement(service, by=actor))


def retire_statement(service: str, *, by: str) -> Update:
    """Retire one declaration: the row keeps its value, and `by` is named in the ledger entry.

    `setting_store.retire_statement` retires a whole namespace, which is the wrong reach for taking
    away one service, so this is the same statement narrowed to one key.
    """
    if not by.strip():
        msg = "a declaration retired by nobody says it went and not who removed it"
        raise ValueError(msg)
    return (
        update(SettingRow)
        .where(SettingRow.deleted_at.is_(None))
        .where(SettingRow.key == key_of(service))
        .values(deleted_at=func.statement_timestamp(), updated_by=by, updated_at=func.now())
    )


def declared_in(states: Mapping[str, SettingState]) -> tuple[ExternalAiService, ...]:
    """The services these rows declare, in name order, skipping every row that is not one.

    A row is a declaration when it is a JSON row whose value validates as one (an object with
    exactly the four fields, which the model refuses anything else for) and names the service its
    key does. A key naming another service than its value is skipped, because the
    row a service is retired through is the one its key says.
    """
    found: list[ExternalAiService] = []
    for name, state in sorted(values_under(states, NAMESPACE).items()):
        if state.value_type != SettingType.JSON.value:
            log.warning("external_ai.row_skipped", reason="not_json")
            continue
        try:
            declared = ExternalAiService.model_validate(state.value)
        except ValidationError:
            log.warning("external_ai.row_skipped", reason="does_not_validate")
            continue
        if declared.service != name:
            log.warning("external_ai.row_skipped", reason="key_names_another_service")
            continue
        found.append(declared)
    return tuple(found)


async def declared(session: AsyncSession) -> tuple[ExternalAiService, ...]:
    """Every service this install has declared and not retired."""
    return declared_in(await read_namespace(session, NAMESPACE))


async def services_are_on(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Whether this install has switched outside services on. Off until somebody does."""
    async with sessions() as session:
        return await is_on(session, EXTERNAL_AI_SERVICES)


async def declared_if_on(
    sessions: async_sessionmaker[AsyncSession] | None,
) -> tuple[ExternalAiService, ...]:
    """What the application registers at start: every declared service when the switch is on.

    Nothing when the switch is off, there is no database or the rows cannot be read, which is the
    same answer: the declarations stay on their rows for the start that finds the switch on.
    """
    if sessions is None:
        return ()
    try:
        if not await services_are_on(sessions):
            return ()
        async with sessions() as session:
            return await declared(session)
    except Exception as failure:
        # A read that fails serves none, as `brain.ops.custom_connector_store.refresh` does for
        # the connectors a second person approved: an install whose settings cannot be read yet
        # starts without outside services, and does not fail to start over a feature that is off
        # by default.
        log.warning("external_ai.declarations_not_read", error=type(failure).__name__)
        return ()


def stored_value(service: ExternalAiService) -> dict[str, Any]:
    """The JSON a declaration is stored as. Exposed so a test can say what a row may hold."""
    return service.model_dump(mode="json")
