"""A Lark Wiki page has a read of its own, and everybody who reads the library is given it.

Lark Wiki's pages were told to anybody holding the knowledge library's read, `read:knowledge`,
which is the same capability as the company's own documents. So an agent's connector list
(`0186`, `brain.agents.binding`) could not withhold the wiki: an agent holding the library read
reached wiki pages whether or not it named Lark Wiki. From this release a page needs
`read:wiki_page` as well, Lark Wiki declares that it provides `wiki_page`, and the binding narrows
it like every other source's entity. See `brain.agents.binding.A_WIKI_PAGE_HAS_A_READ_OF_ITS_OWN`.

**Nobody's reach shrinks.** Everything that confers the library read today is given the wiki's:

- each live `gate.capability_grant` of exactly `read:knowledge` gains a `read:wiki_page` grant with
  the same principal or team, scope, expiry, reason and grantor. Only the exact capability: a
  field read such as `read:knowledge.title` does not cover `read:knowledge`
  (`Capability.covers`), so it never admitted a wiki page and gains nothing;
- each live `gate.capability_pack` naming `read:knowledge` gains `read:wiki_page`, so everybody
  assigned it holds both. The Starter pack is one, and `brain.identity.lifecycle.STARTER_PACK`
  declares the read too, so a pack furnished after this has it from the start;
- an agent whose capabilities name `read:knowledge` and whose connectors name `lark_wiki` gains
  `read:wiki_page`, because that agent was bound to the wiki and read it before. An agent naming
  no Lark Wiki gains nothing: it reaches no wiki page from this release, which is the binding.

A copy that already exists is not written again.

**The downgrade takes the copies back, by the rule that made them.** A live `read:wiki_page` grant
with a live `read:knowledge` twin (same principal or team, same scope) is revoked, which here as
everywhere is setting `deleted_at`; the wiki read leaves every pack that also confers the library
read, and every agent that holds the library read and names Lark Wiki. A wiki read with no library
twin is left alone: 0187 did not write it, and on the release before this one it reaches nothing.
A twin an administrator made by hand after the upgrade is indistinguishable from a copy and goes
with them, which costs nothing on that release for the same reason.

Task ids: M13.7.8, M13.8.1

Revision ID: 0187
Revises: 0186
"""

from __future__ import annotations

from alembic import op

revision = "0187"
down_revision = "0186"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

LIBRARY_READ = "read:knowledge"
WIKI_READ = "read:wiki_page"
WIKI_CONNECTOR = "lark_wiki"

COPY_GRANTS = f"""
INSERT INTO gate.capability_grant
    (principal_id, team_path, capability, scope, granted_by, reason, not_after)
SELECT g.principal_id, g.team_path, '{WIKI_READ}', g.scope, g.granted_by, g.reason, g.not_after
  FROM gate.capability_grant AS g
 WHERE g.deleted_at IS NULL
   AND g.capability = '{LIBRARY_READ}'
   AND NOT EXISTS (
        SELECT 1 FROM gate.capability_grant AS e
         WHERE e.deleted_at IS NULL
           AND e.principal_id IS NOT DISTINCT FROM g.principal_id
           AND e.team_path IS NOT DISTINCT FROM g.team_path
           AND e.capability = '{WIKI_READ}'
           AND e.scope = g.scope
       )
"""

COPY_INTO_PACKS = f"""
UPDATE gate.capability_pack
   SET capabilities = capabilities || ARRAY['{WIKI_READ}']::varchar(200)[], updated_at = now()
 WHERE deleted_at IS NULL
   AND '{LIBRARY_READ}' = ANY (capabilities)
   AND NOT ('{WIKI_READ}' = ANY (capabilities))
"""

COPY_INTO_AGENTS = f"""
UPDATE agent.agent
   SET capabilities = capabilities || ARRAY['{WIKI_READ}']::varchar(200)[]
 WHERE '{LIBRARY_READ}' = ANY (capabilities)
   AND '{WIKI_CONNECTOR}' = ANY (connectors)
   AND NOT ('{WIKI_READ}' = ANY (capabilities))
"""


def upgrade() -> None:
    op.execute(COPY_GRANTS)
    op.execute(COPY_INTO_PACKS)
    op.execute(COPY_INTO_AGENTS)


#: The inverse of `COPY_GRANTS`: the wiki reads that have the library read they were copied from.
REVOKE_COPIED_GRANTS = f"""
UPDATE gate.capability_grant AS w
   SET deleted_at = now()
 WHERE w.deleted_at IS NULL
   AND w.capability = '{WIKI_READ}'
   AND EXISTS (
        SELECT 1 FROM gate.capability_grant AS g
         WHERE g.deleted_at IS NULL
           AND g.principal_id IS NOT DISTINCT FROM w.principal_id
           AND g.team_path IS NOT DISTINCT FROM w.team_path
           AND g.capability = '{LIBRARY_READ}'
           AND g.scope = w.scope
       )
"""

#: The inverse of `COPY_INTO_PACKS`.
REMOVE_FROM_PACKS = f"""
UPDATE gate.capability_pack
   SET capabilities = array_remove(capabilities, '{WIKI_READ}'::varchar(200)), updated_at = now()
 WHERE deleted_at IS NULL
   AND '{LIBRARY_READ}' = ANY (capabilities)
   AND '{WIKI_READ}' = ANY (capabilities)
"""

#: The inverse of `COPY_INTO_AGENTS`.
REMOVE_FROM_AGENTS = f"""
UPDATE agent.agent
   SET capabilities = array_remove(capabilities, '{WIKI_READ}'::varchar(200))
 WHERE '{LIBRARY_READ}' = ANY (capabilities)
   AND '{WIKI_CONNECTOR}' = ANY (connectors)
   AND '{WIKI_READ}' = ANY (capabilities)
"""


def downgrade() -> None:
    op.execute(REVOKE_COPIED_GRANTS)
    op.execute(REMOVE_FROM_PACKS)
    op.execute(REMOVE_FROM_AGENTS)
