"""Which Lark Wiki spaces this install may answer from, at what reach, and who declared each.

A wiki space shared with the company's Lark app is not yet a space the Brain may answer from:
somebody has to say who on this install may be told its pages, the whole company or one
department, and be answerable for that. `brain.connectors.lark_wiki.SpaceDeclaration` refuses a
default for either, so each space is declared by a person, on the step of Connect Lark that
follows sharing the space, and kept here.

**One row of `ops.setting` a space, under `lark_wiki.space.`, and the writer is the steward.** The
value holds the space's id, its reach and, for a department reach, the department; the person
who wrote the row is its steward, and 0059's trigger records the write in the ledger with who,
when and at what reach. A table of its own would hold the same four facts behind a migration.
See `A_SPACE_IS_READ_ONLY_WHERE_SOMEBODY_DECLARED_ITS_REACH`.

**The shape is the Lark Wiki reader's, and this is its one copy.** The key and value here are the
ones the answering half reads (`declared_spaces` below, and the Wiki's live reader that walks the
declared spaces), so a declaration written on the Connect Lark screen is a declaration that
reader finds. `declare_space` refuses, before writing, any row `declaration_of` would not read
back, so a space cannot be saved in a shape that is then silently skipped.

**A space is named by its id or by its link.** The app's test lists the spaces Lark shows it; a
space the list does not show can be pasted from its settings page, whose link carries
`/wiki/space/` and the space's number (`space_id_of`).

Rejected: declaring a space at the reach of the person who shared it in Lark. Lark's sharing says
who may open a space in Lark, which is a different population from who may be told it here, and
guessing one from the other is the widening this declaration exists to prevent.

Task ids: M11.6.4, M11.9.4, M27.11.9
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Final

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.contract import ConnectorContractError
from brain.connectors.lark_wiki import SpaceDeclaration
from brain.core.department import SLUG_RE
from brain.knowledge.visibility import KnowledgeVisibility, VisibilityError
from brain.ops.setting_store import SettingState, put, read_namespace, values_under
from brain.tables.config import SettingType

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons

#: Why a space is read only where a person declared its reach.
A_SPACE_IS_READ_ONLY_WHERE_SOMEBODY_DECLARED_ITS_REACH: Final = (
    "A wiki space shared with the app is read only once a person on this install has said who "
    "may be told its pages, the whole company or one department, and that person is its "
    "steward. A space nobody declared is not read, and a row that does not declare a readable "
    "reach is refused when it is written rather than skipped when it is read."
)

# --------------------------------------------------------------------- the figures

#: Where each declared space is kept: `lark_wiki.space.<name>`, one row a space.
SPACES_NAMESPACE: Final = "lark_wiki.space"

#: The two reaches a space may be declared at.
COMPANY: Final = "company"
DEPARTMENT: Final = "department"
REACHES: Final = (COMPANY, DEPARTMENT)

#: The sentence every declared space's row carries, which the settings screen shows beside it.
SPACE_DESCRIPTION: Final = (
    "A Lark Wiki space the Brain may answer from, the reach its pages are told at, and, as the "
    "person who declared it, its steward."
)

#: A space's id as Lark writes it: digits, and nothing else.
SPACE_ID: Final = re.compile(r"^[0-9]{6,32}$")
_SPACE_IN_LINK: Final = re.compile(r"/wiki/space/([0-9]{6,32})")


class SpaceDeclarationError(ValueError):
    """A space cannot be declared as asked. The message says what to change."""


def space_id_of(given: str) -> str:
    """The space's id out of its settings link or a bare id, or empty when neither is there."""
    text = given.strip()
    if SPACE_ID.fullmatch(text):
        return text
    found = _SPACE_IN_LINK.search(text)
    return found.group(1) if found else ""


def space_key(space_id: str) -> str:
    """The setting key a space is declared under. Its id is kept in the value, whole."""
    return f"{SPACES_NAMESPACE}.s{re.sub(r'[^a-z0-9_]', '_', space_id.lower())}"


def space_value(space_id: str, reach: str, department: str = "") -> dict[str, str]:
    """The value a declared space is kept as: its id, its reach and, for one, its department."""
    return {"space_id": space_id, "reach": reach, "department": department}


def declaration_of(state: SettingState) -> SpaceDeclaration | None:
    """One kept row as a declaration, or None for a row that does not declare one."""
    value = state.value if isinstance(state.value, Mapping) else {}
    space_id = str(value.get("space_id", "")).strip()
    reach = str(value.get("reach", "")).strip()
    department = str(value.get("department", "")).strip()
    try:
        if reach == COMPANY:
            visibility = KnowledgeVisibility.company(owner_id=state.updated_by)
        elif reach == DEPARTMENT and SLUG_RE.fullmatch(department):
            visibility = KnowledgeVisibility.of_department(department, owner_id=state.updated_by)
        else:
            return None
        return SpaceDeclaration(space_id=space_id, visibility=visibility, owner_id=state.updated_by)
    except (VisibilityError, ConnectorContractError, ValueError):
        return None


def readable(space_id: str, reach: str, department: str, *, by: str) -> bool:
    """Whether a space declared this way would be read back, which is what a save must ensure.

    A department reach names a department by the short name every department is known by
    (`brain.core.department.SLUG_RE`): a name in any other shape matches no department, so the
    space would be told to nobody, and it is refused here rather than kept.
    """
    if reach == DEPARTMENT and not SLUG_RE.fullmatch(department):
        return False
    probe = SettingState(
        key=space_key(space_id),
        value_type=SettingType.JSON.value,
        value=space_value(space_id, reach, "" if reach == COMPANY else department),
        updated_by=by,
        updated_at=datetime.min,
    )
    return declaration_of(probe) is not None


async def declare_space(
    session: AsyncSession, space_id: str, *, reach: str, department: str = "", updated_by: str
) -> None:
    """Declare one space in the caller's transaction, refusing what `declaration_of` would not read.

    The caller sets the ledger's attribution first, so the entry 0059's trigger appends names the
    person, who is the space's steward.
    """
    value = space_value(space_id, reach, "" if reach == COMPANY else department)
    if not readable(space_id, reach, department, by=updated_by):
        msg = (
            f"space {space_id!r} at reach {reach!r} declares nothing this install can read: a "
            "space needs its id and a reach of company, or department with a department"
        )
        raise SpaceDeclarationError(msg)
    await put(
        session,
        space_key(space_id),
        value_type=SettingType.JSON,
        value=value,
        description=SPACE_DESCRIPTION,
        updated_by=updated_by,
    )


async def declared_spaces(
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[SpaceDeclaration, ...]:
    """Every space declared on this install, each read back through `declaration_of`."""
    async with sessions() as session:
        states = await read_namespace(session, SPACES_NAMESPACE)
    found: list[SpaceDeclaration] = []
    for name, state in sorted(values_under(states, SPACES_NAMESPACE).items()):
        declared = declaration_of(state)
        if declared is None:
            log.warning("lark_wiki.space_not_declared", key=name)
            continue
        found.append(declared)
    return tuple(found)
