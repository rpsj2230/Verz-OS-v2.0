"""The wizard's answers, kept in `ops.setting`, so a fresh install needs no hand-edited file.

Until this module the setup wizard **checked** its settings. `brain.setup_routes` required
every value the person typed to already equal what `brain.install.value_of` read from the
process environment, and named back the ones that differed as a 409. That was honest about
what the application could do and it made the wizard a form for confirming a file somebody had
already edited: the answers were collected, compared, and kept nowhere. 82afbfb's own
`A_SETTING_THIS_PROCESS_CANNOT_WRITE_IS_CONFIRMED_BEFORE_THE_DOOR_CLOSES` says so plainly.

**The database is the writable configuration surface this install already has, and it was
already built for exactly this.** `ops.setting` is M31.3.1.4: configuration as data in
Postgres rather than code, key, type, value, description and who changed it last, with
row-level security, a check constraint per rule, and a partial unique index making one live
row per key. It shipped in `0004` in September and **nothing under `src` has ever read or
written it**, which is the shape CLAUDE.md warns about: a control that is correct,
documented, and absent from every direction except the one that matters. So there is no
migration here. There is a first reader and a first writer.

**The resolution order is saved, then the environment, then the declared default, and it is
decided in one place**, which is `brain.install.value_of`. See
`A_SAVED_ANSWER_OUTRANKS_THE_TEMPLATE_THE_INSTALLER_COPIED` for why it is that way round and
not the other. Every reader of an installation value already goes through that function, so
the order moves everywhere at once and there is nowhere else for a second order to live.

**What stays in the environment file, and it is a short list.** A process needs its database
address, its profile, its image and its setup code before it has a database to read them
from, and those are fields of `brain.settings.Settings` rather than installation settings, so
they are outside `value_of` entirely and outside this module. Of the values `value_of` does
resolve, one stays in the file in practice: `INSTALL_OIDC_ISSUER` is required, has no safe
default, and no wizard screen asks for it, because an issuer guessed from the web address is
a sign-in page pointing at somebody else's identity provider. The installer sets it where the
realm is created. Nothing here refuses to save it; there is simply nothing that collects it.

**The provider key is never saved here, and since 2026-09-16 it is kept anyway, in the vault.**
A model provider's API key is a standing credential, `brain.ops.provider_keys` argues at length
that its home is the vault and the process environment and never a table the application role
can select from, and `brain.tables.config` refuses secrets in this table in its own words. Until
that date the vault client read a static slot and wrote none, so a hosted install's key could
not be kept by this process at all and the wizard refused it unless the environment already
carried it. `brain.ops.credentials` is the write now, `brain.setup_routes.keep_provider_key`
calls it, and what is left of the 409 is an install that names no vault. See
`THE_ONE_ANSWER_THIS_TABLE_WILL_NEVER_KEEP`.

**A saved value reaches the process that saved it and every process started after it, and not
a sibling worker that is still running.** `A_SAVED_SETTING_IS_NOT_A_MESSAGE_TO_ANOTHER_WORKER`
carries the argument, which is `brain.ops.provider_keys`' "rotation is a restart" reached from
the other end. It is stated rather than solved, and since 2026-09-17 it is said
at the moment that matters: the finishing screen is served by the process that appointed, and the
appointment answers whether other processes serve beside it, so the screen lands on the console
where it serves alone and asks for a restart where it does not. See
`brain.setup_routes.A_RESTART_IS_ASKED_FOR_ONLY_WHERE_ANOTHER_PROCESS_SERVES`.

Rejected: writing the environment file from the application. The container has no mount onto
it, and a process that rewrites its own configuration is a second writer beside the variables
repository M42.1.1 makes the record of an install, undone by the next deploy. That argument
has not changed and is why the values go to a table instead.

Rejected: a second reader beside `value_of`. `brain.install.ONE_READER_OR_TWO_DEFAULTS` is
exactly about this, and it is why the saved values are resolved inside that function rather
than by a caller that knows to ask the database first.

Rejected: reading the table on every resolution. `value_of` is synchronous and on the read
path of every rendered page, and the database session is not. A per-request query for a value
that changes once per install is the cost this repository refuses everywhere else.

Rejected: environment first, database second. It reads as the safer order and it is the one
that would make this whole change invisible. See the named constant.

Task ids: M42.5.10, M42.5.14, M31.3.1.4
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.install import BY_NAME, INSTALL_PREFIX, InstallError, hold_saved
from brain.tables.config import SettingRow, SettingType

log = structlog.get_logger(__name__)

# ------------------------------------------------------------ written-down reasons

#: Why a row beats the environment rather than the other way round.
A_SAVED_ANSWER_OUTRANKS_THE_TEMPLATE_THE_INSTALLER_COPIED: Final = (
    "A row in ops.setting exists only because somebody answered the wizard or turned the knob "
    "afterwards. A line in the environment file is whatever the template left behind, and the "
    "template spells the product's neutral defaults out as literals: .env.example carries "
    "INSTALL_COMPANY_NAME=Your Company, generated from the declaration by install.env_example. "
    "So on the environment-first order every install that copied the template would save the "
    "company's real name and go on rendering Your Company, with nothing anywhere saying why. "
    "Database first also keeps the operator's escape hatch exactly where the table already put "
    "it: retiring the row returns the system to the environment and then to the default, which "
    "is brain.tables.config's own rule that an absent row means the compiled default."
)

#: What a saved setting reaches, and what it does not.
A_SAVED_SETTING_IS_NOT_A_MESSAGE_TO_ANOTHER_WORKER: Final = (
    "The saved values are held per process and loaded in two places: the lifespan, once, for "
    "every process as it starts, and the appointment route, from what it has just written, for "
    "the process that wrote it. brain.serve starts brain.runtime.detect_profile's number of "
    "uvicorn workers, so an install serving more than one carries the environment's answer in "
    "the siblings until they are restarted. Polling for a value that changes once per install "
    "is what brain.ops.provider_keys refuses for a key that rotates twice a year, and the same "
    "argument is made here for the same cost, with the gap written down rather than implied."
)

#: Why the provider key goes to the vault and never to this table, vault or no vault.
THE_ONE_ANSWER_THIS_TABLE_WILL_NEVER_KEEP: Final = (
    "A provider API key is a standing credential with no lease and no expiry, its home is the "
    "vault, and ops.setting refuses secrets in its own docstring because a credential the "
    "application role can select is a credential in the ordinary query path. So the wizard's "
    "key is written to the vault by brain.ops.credentials, and an install that names no vault "
    "keeps it nowhere: the refusal names the slot's path, the variable and the reason, and "
    "never a value, and nothing falls back to a row here."
)

# --------------------------------------------------------------------- the figures

#: The namespace every saved installation value sits under in `ops.setting`.
#:
#: Dotted because `SETTING_KEY_PATTERN` requires at least two segments, and `install` because
#: it is the word the declaration already uses. It is not one of `RESERVED_KEY_PREFIXES`, and
#: a test holds that rather than the reading: a namespace the permission model owns would be
#: refused by the column, on a client's server, at the end of their wizard.
SETTING_NAMESPACE: Final = "install"

#: The one type these rows carry. Every declared installation value is a string to `value_of`,
#: including `INSTALL_EMBEDDING_DIMENSIONS`, whose reader parses it. Storing a width as a json
#: number here would make this the place the parse is decided, which is a second answer to a
#: question `brain.knowledge.search` already answers.
SAVED_TYPE: Final = SettingType.STRING


def key_for(name: str) -> str:
    """The `ops.setting` key one declared installation setting is saved under.

    Refuses a name the declaration does not carry, so a setting saved before it is declared is
    refused here rather than becoming a row nothing reads. See `name_for` for the way back.
    """
    if name not in BY_NAME:
        msg = (
            f"{name!r} is not a declared installation setting, so there is nothing to save it "
            "as. Add it to brain.install.INSTALLATION with a meaning and a default first"
        )
        raise InstallError(msg)
    return f"{SETTING_NAMESPACE}.{name.removeprefix(INSTALL_PREFIX).lower()}"


def name_for(key: str) -> str:
    """The declared installation setting one key names, or empty for anything else.

    Empty rather than raising, because this reads rows a person may have written by hand: a key
    in another namespace, or one naming a setting nobody declared, is a row this does not
    resolve rather than a startup that refuses.
    """
    head, _, rest = key.partition(".")
    if head != SETTING_NAMESPACE or not rest:
        return ""
    name = f"{INSTALL_PREFIX}{rest.upper()}"
    return name if name in BY_NAME else ""


def rows_for(values: Mapping[str, str], *, updated_by: str) -> tuple[dict[str, Any], ...]:
    """One `ops.setting` row per value, in key order, ready for an insert.

    Pure, and handed to whoever holds the transaction, so the write can land beside the
    appointment rather than in a transaction of its own. See `save`.

    `description` is the setting's own declared meaning rather than a sentence written here.
    The column is required for the reason a grant's reason is, an undescribed setting is one
    nobody can safely change, and the declaration is already what the install runbook prints,
    so a second sentence here would be the one that goes stale.
    """
    return tuple(
        {
            "key": key_for(name),
            "value_type": SAVED_TYPE.value,
            "value": values[name],
            "description": BY_NAME[name].meaning,
            "updated_by": updated_by,
        }
        for name in sorted(values)
    )


def values_from(rows: Iterable[Sequence[Any]]) -> dict[str, str]:
    """The installation values a set of `(key, value_type, value)` rows carries.

    A row whose key names no declared setting, or whose value is not a string, is dropped
    rather than resolved. Both are things a person with a psql prompt can write, and neither
    should be able to make `value_of` return something that is not a string.
    """
    found: dict[str, str] = {}
    for key, value_type, value in rows:
        name = name_for(str(key))
        if not name or str(value_type) != SAVED_TYPE.value or not isinstance(value, str):
            continue
        found[name] = value
    return found


# ------------------------------------------------------------------------ the writes


async def save(session: AsyncSession, values: Mapping[str, str], *, updated_by: str) -> int:
    """Write these installation values as live rows, in the caller's transaction.

    Handed a session rather than a session factory, because the whole point is that these rows
    and the first administrator commit together: an appointment that lands without them closes
    the wizard over answers kept nowhere, and rows that land without an appointment configure
    an install nobody can sign in to. See
    `brain.identity.first_administrator.APPOINTING_IS_THE_LAST_WRITE`.

    Existing live rows for the same keys are updated rather than duplicated, against the
    partial unique index, so this says the same thing when it is run twice. Returns how many
    rows it wrote, which is what a caller logs; it never returns or logs a value.
    """
    prepared = rows_for(values, updated_by=updated_by)
    if not prepared:
        return 0
    statement = insert(SettingRow).values(list(prepared))
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[SettingRow.key],
            index_where=SettingRow.deleted_at.is_(None),
            set_={
                "value_type": statement.excluded.value_type,
                "value": statement.excluded.value,
                "description": statement.excluded.description,
                "updated_by": statement.excluded.updated_by,
            },
        )
    )
    return len(prepared)


async def load(session: AsyncSession) -> dict[str, str]:
    """Every installation value this database holds, resolved from the live rows.

    The policy on the table hides retired rows from `brain_app`, and the `deleted_at` test is
    written here as well rather than left to it: this also runs in a migration's own connection
    and in a test connected as the owner, where no policy applies.
    """
    rows = (
        await session.execute(
            select(SettingRow.key, SettingRow.value_type, SettingRow.value)
            .where(SettingRow.deleted_at.is_(None))
            .where(SettingRow.key.startswith(f"{SETTING_NAMESPACE}."))
        )
    ).all()
    return values_from(rows)


async def refresh(sessions: async_sessionmaker[AsyncSession]) -> Mapping[str, str]:
    """Load the saved values and hold them for this process, returning what is now held.

    The one place a session factory is opened here, so `save` and `load` stay testable against
    a transaction somebody else owns. Called by the lifespan once the database is reachable and
    before anything reads a setting; see `A_SAVED_SETTING_IS_NOT_A_MESSAGE_TO_ANOTHER_WORKER`
    for what that does and does not reach.
    """
    async with sessions() as session, session.begin():
        found = await load(session)
    hold_saved(found)
    log.info("installation settings loaded", settings=sorted(found))
    return found
