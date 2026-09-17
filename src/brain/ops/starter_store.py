"""Furnishing an install: the starter set written into PostgreSQL once, as the application.

`brain.ops.starter` declares what a new install holds and said, until this module, that nothing
applied it. Measured on origin/main 07f6aff: no statement under `src` inserted into
`gate.scope`, `gate.capability_registry` or `gate.capability_pack`, so on a fresh install the
grant route found no scope to resolve a slug against and refused every grant, a first
administrator's included, and the Capabilities screen listed nothing. This is the half that owns
a session, for the layout's rule that nothing deciding policy owns a client.

**Called from three places, and the first is the one that matters.** `brain.app.lifespan` furnishes
at every start, beside the ladder's reconciliation, so an install set up before this module
existed is furnished on its next deploy with nobody at a shell; see
`EVERY_START_FURNISHES_BECAUSE_NOTHING_FURNISHED_IS_AN_ANSWER`. A start that cannot furnish logs the
exception's class and serves anyway. The installer's `furnish the install` step runs
`python -m brain.ops.starter_store` after readiness, so on a healthy install it finds the start's
record and is skipped, and on one whose start could not furnish it fails out loud with its own
sentence rather than a log line. The same command is what a person runs by hand, and `furnish` is
what a Settings action will call.

**What it writes, and all of it is the product's.** One registry row for every capability
`starter.vocabulary` declares, with the sentence its declaring module wrote; the starter pack;
and the one company-wide scope, `starter.COMPANY_SCOPE`. Nothing it writes names a person, a
department, a team or a record, and nothing it writes is read from configuration, so no value
here could be one company's: every row is a constant of the product, which
`test_furnishing_never_writes_a_person_or_a_demo_row` holds against every table in the database
rather than against the three it means to touch.

**Two regimes, because the rows are two kinds of thing.** The vocabulary is the product's in the
way `starter.THE_SIX_ROLES_ARE_THE_PRODUCT_AND_NOT_A_CLIENTS_CHOICE` says the roles are: the gate
checks a declared capability whether or not a row lists it, nothing under `src` retires a registry
row, and a release that declares a new capability should be able to register it on an install
furnished by an older one. So every furnishing registers each declared capability that has no live
row, and registers nothing when every one has. The scope and the pack are furniture: once written
they are the company's to keep, rename or retire, and furnishing again must not put back what an
administrator took away, which is
`default_ladder.A_LADDER_SOMEBODY_HELD_IS_NEVER_REFILLED_BY_THE_PRODUCT` reached from the permission
side. See `WHAT_FURNISHING_WROTE_IS_THE_COMPANYS_AND_IS_NEVER_PUT_BACK` and
`THE_VOCABULARY_IS_REGISTERED_WHEREVER_A_ROW_IS_MISSING`.

**How "once" is remembered: a setting row, and the ledger entry its trigger writes.** The table
policies on `gate.scope` and `gate.capability_pack` hide a retired row from the application, so a
store asking "is the company scope there" cannot tell a scope nobody wrote from one somebody
retired. The first furnishing therefore also writes `ops.setting` `starter.furnished`, and `0059`'s
`setting_is_audited` appends a `setting` entry for it, naming the actor and the trace, in the same
transaction. Every later furnishing reads the ledger for that entry, which no policy hides and
nothing deletes, and skips the furniture when it is there. The entry is also this change's audit
record: it says who furnished the install and when, which the three furnished tables cannot say
for themselves.

Rejected: a table of its own for the fact, which is a migration, a policy and a trigger for one
row. Rejected: a new `AuditAction` member, which is a closed vocabulary widened for one event and
a migration to widen the ledger's check constraint. Rejected: reading retired rows as the owner,
which a Settings action served by the application cannot do and should not be able to.

**Idempotent by the live-row indexes, in one transaction, and with no advisory lock.** Every
insert is `ON CONFLICT DO NOTHING` against its table's partial unique index on live rows. Two
furnishings started together can both find no ledger entry; the second's first insert then waits
on the first's uncommitted row in that index, and once the first commits it writes nothing, its
setting insert included, so it reports that it wrote nothing. Every insert writes its rows in one
order, capability order for the registry, so the two cannot wait on each other. That is exactly
the serialisation `default_ladder_store`'s advisory lock buys, and the ladder needs its lock
because its rung insert has no conflict clause and would raise instead. **A lock was written here
first and taken out, because it was measured to change nothing:**
`test_two_furnishings_at_once_furnish_once` passed with it and passes without it, so it was a
guard no test could reach, which is this repository's recurring defect in its plainest form.

**Who the ledger says did it is first run.** The actor is `brain.firstrun.GRANTED_BY` from a
start, the installer and the command alike, because furnishing is what first run would have written
had it existed then, which is the argument `default_ladder_store` makes about a start writing the
ladder late. The trace says which: a start's is the `startup.reconcile.` prefix every start's
reconciliation carries, and the command's is `install.furnish.`, each followed by sixteen hex
characters.

**Audited per row, and not.** `ops.setting` is recorded by `0059`'s trigger, one `switched_on`
entry, and since `0086` the company-wide scope is recorded by that migration's trigger on
`gate.scope`, one `organisation` entry under `scope:company` naming first run.
`gate.capability_registry` and `gate.capability_pack` have no ledger trigger in any migration. An
insert into `gate.capability_pack` runs `0003`'s `bump_grants_version_for_pack`, which bumps
`gate.policy_epoch` and the version of every principal the pack is assigned to, which on a
furnishing is nobody, and records nothing. The furnishing's own entry is what the ledger has for
those two.

**What W0.5 names that this does not write, and why each is absent rather than forgotten.**

- *Routing tiers and rungs.* `brain.ops.default_ladder_store` writes the rungs, from the wizard for
  the provider it records and at every start for an install with an administrator (07f6aff).
  Furnishing runs before the wizard, when no provider has been chosen, which is
  `default_ladder.NO_LADDER_IS_WRITTEN_BEFORE_SETUP_HAS_CHOSEN_WHERE_TEXT_MAY_GO`, and a second
  writer of rungs is what that change refused. `ops.routing_tier` has no reader under `src`, so a
  row there would be furniture nothing sits on.
- *Signed built-in templates.* See
  `NO_TEMPLATE_IS_SIGNED_BEFORE_THE_INSTALL_HOLDS_A_KEY_OF_ITS_OWN`.
- *Departments and their starter scopes.* A department's slug and name are a company's own, and
  `core.department.starter_scopes` is applied when somebody creates one.
- *`starter.DEFAULTS`.* Measured: nothing under `src` reads `session_idle_minutes`,
  `session_absolute_hours`, `approval_required_above` or `knowledge_visibility` from anywhere, and
  none of the four is a key `ops.setting`'s grammar admits. Four rows no process reads would be
  four settings that change nothing when an administrator changes them.
- *Agents.* `starter.agents` names templates, and an agent is an install of a signed one.

Task ids: M41.2.7
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningInsert

from brain.audit.ledger import AuditAction
from brain.core.department import ScopeRecord
from brain.firstrun import GRANTED_BY
from brain.identity.packs import CapabilityPack
from brain.ops.starter import PACKS, SCOPES, Declared, vocabulary
from brain.tables.audit import AuditEntryRow, attributed_to
from brain.tables.config import SettingRow, SettingType
from brain.tables.gate import CapabilityPackRow, CapabilityRegistryRow, ScopeRow

# ------------------------------------------------------------------- written-down reasons

#: Why a second furnishing never writes the scope or the pack again.
WHAT_FURNISHING_WROTE_IS_THE_COMPANYS_AND_IS_NEVER_PUT_BACK: Final = (
    "The company-wide scope and the starter pack are written once. After that they are the "
    "company's, and a scope or pack an administrator retired is a decision. The table policies "
    "hide a retired row from the application, so furnishing remembers that it has run through "
    "the ledger entry its own setting row leaves, and writes neither again once that entry "
    "exists, whatever the tables now show."
)

#: Why the vocabulary is registered on every furnishing and the furniture is not.
THE_VOCABULARY_IS_REGISTERED_WHEREVER_A_ROW_IS_MISSING: Final = (
    "A capability the product declares is checked by the gate whether or not a registry row "
    "lists it, and nothing under src retires a registry row. So every furnishing registers each "
    "declared capability with no live row, which is how a release declaring a new one registers "
    "it on an install an older release furnished, and registers nothing when every one is there."
)

#: Why a start furnishes, when a start does not write the ladder before setup.
EVERY_START_FURNISHES_BECAUSE_NOTHING_FURNISHED_IS_AN_ANSWER: Final = (
    "The ladder waits for the wizard because a provider is somebody's choice and a ladder written "
    "for the template's default would sit in front of the one they then choose. Nothing furnished "
    "is anybody's choice: the scope restricts nothing, the pack and the registry are the "
    "product's, and none of them depends on a setting. So every start furnishes, which is how an "
    "install set up before furnishing existed gets it on its next deploy with no command and no "
    "shell. It costs a start one transaction that writes nothing after the first, and it puts "
    "back nothing somebody retired, because what stops that is the ledger entry and not the "
    "caller."
)

#: Why no built-in template is signed here.
NO_TEMPLATE_IS_SIGNED_BEFORE_THE_INSTALL_HOLDS_A_KEY_OF_ITS_OWN: Final = (
    "agents.template.publish signs with an HMAC key, and install verifies with the same key, so "
    "the key has to be minted on the install, kept where the application can read it back, and "
    "never replaced while a signed row exists. No vault path the application policy grants is "
    "for that: providers/ holds provider keys a person supplies, webhooks/ holds subscribers' "
    "secrets, connector_keys/ holds vendors' keys. Choosing the path, the policy grant, a "
    "write-once rule and what a lite install without a vault says is a design decision on the "
    "vault and its policy, which the vault that runs at install since 0c4b5f8 did not make. So "
    "furnishing signs nothing, the catalogue stays the unsigned manifests in code, and install "
    "stays unoffered, which is what agent_routes already says."
)

# ------------------------------------------------------------------------------ the figures

#: The setting whose ledger entry records that an install has been furnished.
FURNISHED_KEY: Final = "starter.furnished"

#: The sentence on that setting's row, which is what the Settings screen will show beside it.
FURNISHED_DESCRIPTION: Final = (
    "Whether this install has been furnished with the product's starter set: one company-wide "
    "scope, the starter pack and the capability registry. Written once, by first run. The audit "
    "ledger's entry for it is what stops a retired scope or pack being furnished again, so "
    "changing or retiring this row changes nothing."
)

#: What the trace of a furnishing starts with. Sixteen hex characters follow.
FURNISHING_TRACE_PREFIX: Final = "install.furnish."


@dataclass(frozen=True)
class Furnished:
    """What one furnishing wrote, by the product's own names. Never a count of anything hidden:
    every name here is a constant of the product that the caller could have read in the code.
    """

    #: The capabilities registered by this call, in capability order.
    registered: tuple[str, ...] = ()
    #: The scopes written by this call.
    scopes: tuple[str, ...] = ()
    #: The packs written by this call.
    packs: tuple[str, ...] = ()
    #: True when this call was the install's first furnishing and wrote the record of it.
    first: bool = False

    @property
    def wrote_nothing(self) -> bool:
        """Whether this call changed no row at all."""
        return not (self.registered or self.scopes or self.packs or self.first)


# ------------------------------------------------------------------------------ statements


def register(declared: Sequence[Declared]) -> ReturningInsert[tuple[str]]:
    """Every declared capability with no live registry row, returning the ones written."""
    statement = insert(CapabilityRegistryRow).values(
        [{"capability": one.capability.value, "description": one.description} for one in declared]
    )
    return statement.on_conflict_do_nothing(
        index_elements=[CapabilityRegistryRow.capability],
        index_where=CapabilityRegistryRow.deleted_at.is_(None),
    ).returning(CapabilityRegistryRow.capability)


def furnish_scopes(records: Sequence[ScopeRecord]) -> ReturningInsert[tuple[str]]:
    """The furnished scopes that have no live row of their slug, returning the slugs written.

    The predicate is `ScopeRecord.predicate`, the document form `from_predicate` reads back,
    never `Scope.model_dump`, which is the shape `gate.scope`'s check constraint refuses.
    """
    statement = insert(ScopeRow).values(
        [
            {
                "slug": one.slug,
                "predicate": one.predicate(),
                "is_department": one.is_department,
                "label": one.label,
            }
            for one in records
        ]
    )
    return statement.on_conflict_do_nothing(
        index_elements=[ScopeRow.slug], index_where=ScopeRow.deleted_at.is_(None)
    ).returning(ScopeRow.slug)


def furnish_packs(packs: Sequence[CapabilityPack]) -> ReturningInsert[tuple[str]]:
    """The furnished packs that have no live row of their name, returning the names written.

    `name` is the pack's slug and `description` its label, which is the reading
    `brain.govern_routes.placed_assignment` already makes of a pack row.
    """
    statement = insert(CapabilityPackRow).values(
        [
            {
                "name": one.slug,
                "description": one.label,
                "capabilities": [capability.value for capability in one.capabilities],
            }
            for one in packs
        ]
    )
    return statement.on_conflict_do_nothing(
        index_elements=[CapabilityPackRow.name], index_where=CapabilityPackRow.deleted_at.is_(None)
    ).returning(CapabilityPackRow.name)


def record_furnishing(actor: str) -> ReturningInsert[tuple[str]]:
    """The setting row whose trigger writes the ledger entry every later furnishing reads."""
    return (
        insert(SettingRow)
        .values(
            key=FURNISHED_KEY,
            value_type=SettingType.BOOLEAN.value,
            value=True,
            description=FURNISHED_DESCRIPTION,
            updated_by=actor,
        )
        .on_conflict_do_nothing(
            index_elements=[SettingRow.key], index_where=SettingRow.deleted_at.is_(None)
        )
        .returning(SettingRow.key)
    )


def any_furnishing() -> Select[tuple[int]]:
    """One ledger entry for the furnishing setting, or none: whether this install was furnished."""
    return (
        select(AuditEntryRow.seq)
        .where(
            AuditEntryRow.action == AuditAction.SETTING.value,
            AuditEntryRow.subject == f"setting:{FURNISHED_KEY}",
        )
        .limit(1)
    )


# ------------------------------------------------------------------------------- the write


async def furnish(
    sessions: async_sessionmaker[AsyncSession], *, actor: str, trace_id: str, ent_hash: str = ""
) -> Furnished:
    """Furnish this install, or register only what the vocabulary is missing, or write nothing.

    One transaction as the application role, attributed to `actor` under `trace_id`, with no
    advisory lock; see the module docstring for why none is needed. Raises for a database that
    refuses, and the caller decides what that costs. `ent_hash` is the writer's reach as a
    digest, empty where there is no reach to digest.
    """
    async with sessions() as session, session.begin():
        for statement in attributed_to(actor_id=actor, ent_hash=ent_hash, trace_id=trace_id):
            await session.execute(statement)
        registered = await _written(session, register(vocabulary()))
        if (await session.execute(any_furnishing())).first() is not None:
            return Furnished(registered=registered)
        scopes = await _written(session, furnish_scopes(SCOPES))
        packs = await _written(session, furnish_packs(PACKS))
        first = bool(await _written(session, record_furnishing(actor)))
    return Furnished(registered=registered, scopes=scopes, packs=packs, first=first)


async def _written(
    session: AsyncSession, statement: ReturningInsert[tuple[str]]
) -> tuple[str, ...]:
    """What an insert returning one name column wrote, sorted."""
    return tuple(sorted(str(one) for one in (await session.execute(statement)).scalars().all()))


def told(done: Furnished) -> str:
    """One line for the person who ran the command, naming what was written."""
    if done.wrote_nothing:
        return "nothing to furnish: this install was furnished already and nothing is missing"
    parts = [f"registered {len(done.registered)} capabilities"]
    if done.scopes:
        parts.append(f"wrote the scope {', '.join(done.scopes)}")
    if done.packs:
        parts.append(f"wrote the pack {', '.join(done.packs)}")
    if done.first:
        parts.append(f"recorded the furnishing as {FURNISHED_KEY}")
    return "furnished: " + "; ".join(parts)


# ----------------------------------------------------------------------------- the command


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m brain.ops.starter_store`: furnish the install this process is configured for.

    What the installer's `furnish the install` step runs inside the application container, and
    what an operator runs by hand when a start logged that it could not furnish. Takes no
    arguments.
    The failure line names the exception's class and never its message, which can carry the
    connection string.
    """
    from brain.session import make_app_engine, make_application_sessions
    from brain.settings import Settings

    if argv:
        print("brain.ops.starter_store takes no arguments", file=sys.stderr)
        return 2
    url = Settings().database_url
    if not url:
        print("DATABASE_URL is not set, so there is no install to furnish", file=sys.stderr)
        return 2
    trace_id = f"{FURNISHING_TRACE_PREFIX}{uuid.uuid4().hex[:16]}"

    async def go() -> Furnished:
        engine = make_app_engine(url)
        try:
            return await furnish(
                make_application_sessions(engine), actor=GRANTED_BY, trace_id=trace_id
            )
        finally:
            await engine.dispose()

    # psycopg's async driver needs a selector loop on Windows; see `brain.ops.worker`.
    loop_factory: Any = asyncio.SelectorEventLoop if os.name == "nt" else None
    try:
        done = asyncio.run(go(), loop_factory=loop_factory)
    except Exception as exc:
        print(f"furnishing failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"{told(done)} (trace {trace_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
