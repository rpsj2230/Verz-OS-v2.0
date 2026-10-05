"""An agent keeps the connectors it is bound to, and three shared entity names become one source's.

**`agent.agent.connectors`** holds the connectors an agent's template names, which
`brain.agents.model.entitlement_ceiling` compiles into its ceiling (M13.8.1): a capability on an
entity a connector provides stays in the ceiling only when the agent names that connector. Until
this column the list lived only in the template instance's document and was read once, at install,
to say whether the install served it. Each existing agent is backfilled from its own instance's
`effective_document`, which is the list it was installed with, so an agent installed from a template
keeps every connector it named. An agent with no instance (one built before templates) gets none,
and from this release it reaches no connected source, which is what M13.7.8 requires of an agent
bound to nothing.

**`contact` and `invoice` are renamed where a connector provided them.** Freshdesk and Xero both
provided `contact` and Xero and the demo both provided `invoice`, and a grant names no source, so
one capability reached both and no agent's list could narrow it. They are `freshdesk_contact`,
`xero_contact` and `xero_invoice` now. See `brain.agents.binding.AN_ENTITY_NAMES_ONE_SOURCE`. What
this migration does about the rows that already name them:

- **A live grant on a renamed entity is copied, never moved.** Each live `gate.capability_grant`
  whose noun is `contact` gains a copy naming `freshdesk_contact` if Freshdesk is connected on this
  install and one naming `xero_contact` if Xero is, with the same principal or team, scope, expiry,
  reason and grantor. `invoice` gains `xero_invoice` if Xero is connected. The original is left
  alone: entitlements are additive only, so nobody loses a read they had, and the original reaches
  only what still answers to its name (the demo's invoices). A copy that already exists is not
  written twice, so running this against a partly migrated install changes nothing it did before.
- **A capability pack** gains the same copies in its list, on the same rule.
- **An agent's own capabilities** gain the copies for the connectors that agent names, rather than
  for the ones the install has connected, because its list is the binding.
- **Rows that carry their source are renamed in place**: `proj.record`, `er.alias`,
  `er.identifier`, `er.link` and `gate.fast_path_rule`, where the source is the connector that
  provided the old name. They are the source's own records, and the source is in the row.

What is deliberately not rewritten, and why:

- **`agent.template_version.document` is signed.** Rewriting it breaks the signature
  `brain.agents.template.install` verifies. The two built-in templates that named these entities
  ship as version 2 with the new names, beside version 1, as `brain.ops.builtin_templates` adds
  every changed built-in.
- **`agent.template_instance` documents** are derived from a signed version and an overlay, and
  are rebuilt when the agent next accepts a version. The agent row is what a run reads.
- **`gate.field_policy`** carries no source, so a row naming `contact` cannot say whose it is.
- **History**: `gate.self_grant`, `gate.elevation_request`, `gate.access_request`,
  `gate.suspension`, `ops.outbox_event` and the memory tables record what was asked or held at the
  time, under the name it had then.
- **`know.classified_table`** is a company's own upload, named by the company.

The downgrade drops the column. The copied grants and renamed rows stay: on the release before
this one they name entities nothing provides, so they reach nothing there.

Task ids: M13.7.8, M13.8.1

Revision ID: 0186
Revises: 0154
"""

from __future__ import annotations

from alembic import op

revision = "0186"
# Main's head when this was written. Re-pointed at whichever migration is the head when it lands:
# nothing here depends on anything after 0154.
down_revision = "0154"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

#: Each shared name, the connector that provided it, and the name it has now. Kept as data here
#: rather than imported, because a migration says what it did on the day it ran.
RENAMED: tuple[tuple[str, str, str], ...] = (
    ("contact", "freshdesk", "freshdesk_contact"),
    ("contact", "xero", "xero_contact"),
    ("invoice", "xero", "xero_invoice"),
)

#: The capability's noun: what sits between the colon and the first dot.
NOUN = "split_part(split_part({column}, ':', 2), '.', 1)"

#: The capability with its noun replaced, verb and field kept.
RENAMED_CAPABILITY = (
    "split_part({column}, ':', 1) || ':' || r.new"
    " || substr(split_part({column}, ':', 2), length(r.old) + 1)"
)


def _renamed_values() -> str:
    return ", ".join(f"('{old}', '{provider}', '{new}')" for old, provider, new in RENAMED)


ADD_COLUMN = """
ALTER TABLE agent.agent
    ADD COLUMN connectors varchar(64)[] NOT NULL DEFAULT '{}'
"""

BACKFILL_CONNECTORS = """
UPDATE agent.agent AS a
   SET connectors = ARRAY(
        SELECT DISTINCT one
          FROM jsonb_array_elements_text(i.effective_document -> 'connectors') AS one
         ORDER BY one
       )
  FROM agent.template_instance AS i
 WHERE i.id = a.id
   AND jsonb_typeof(i.effective_document -> 'connectors') = 'array'
"""

COPY_GRANTS = f"""
WITH renamed(old, provider, new) AS (VALUES {_renamed_values()}),
connected AS (
    SELECT DISTINCT connector FROM ops.connector_connection WHERE disconnected_at IS NULL
),
copies AS (
    SELECT g.principal_id, g.team_path,
           {RENAMED_CAPABILITY.format(column="g.capability")} AS capability,
           g.scope, g.granted_by, g.reason, g.not_after
      FROM gate.capability_grant AS g
      JOIN renamed AS r ON {NOUN.format(column="g.capability")} = r.old
      JOIN connected AS c ON c.connector = r.provider
     WHERE g.deleted_at IS NULL
)
INSERT INTO gate.capability_grant
    (principal_id, team_path, capability, scope, granted_by, reason, not_after)
SELECT k.principal_id, k.team_path, k.capability, k.scope, k.granted_by, k.reason, k.not_after
  FROM copies AS k
 WHERE NOT EXISTS (
        SELECT 1 FROM gate.capability_grant AS e
         WHERE e.deleted_at IS NULL
           AND e.principal_id IS NOT DISTINCT FROM k.principal_id
           AND e.team_path IS NOT DISTINCT FROM k.team_path
           AND e.capability = k.capability
           AND e.scope = k.scope
       )
"""

COPY_INTO_PACKS = f"""
WITH renamed(old, provider, new) AS (VALUES {_renamed_values()}),
connected AS (
    SELECT DISTINCT connector FROM ops.connector_connection WHERE disconnected_at IS NULL
),
grown AS (
    SELECT p.id,
           ARRAY(
               SELECT DISTINCT one FROM (
                   SELECT unnest(p.capabilities) AS one
                   UNION
                   SELECT {RENAMED_CAPABILITY.format(column="held")}
                     FROM unnest(p.capabilities) AS held
                     JOIN renamed AS r ON {NOUN.format(column="held")} = r.old
                     JOIN connected AS c ON c.connector = r.provider
               ) AS every
               ORDER BY one
           ) AS capabilities
      FROM gate.capability_pack AS p
     WHERE p.deleted_at IS NULL
)
UPDATE gate.capability_pack AS p
   SET capabilities = g.capabilities, updated_at = now()
  FROM grown AS g
 WHERE g.id = p.id
   AND NOT (g.capabilities <@ p.capabilities)
"""

COPY_INTO_AGENTS = f"""
WITH renamed(old, provider, new) AS (VALUES {_renamed_values()}),
grown AS (
    SELECT a.id,
           a.capabilities || ARRAY(
               SELECT {RENAMED_CAPABILITY.format(column="held")}
                 FROM unnest(a.capabilities) WITH ORDINALITY AS h(held, position)
                 JOIN renamed AS r ON {NOUN.format(column="held")} = r.old
                WHERE r.provider = ANY (a.connectors)
                  AND NOT ({RENAMED_CAPABILITY.format(column="held")} = ANY (a.capabilities))
                ORDER BY h.position, r.new
           )::varchar(200)[] AS capabilities
      FROM agent.agent AS a
)
UPDATE agent.agent AS a
   SET capabilities = g.capabilities
  FROM grown AS g
 WHERE g.id = a.id
   AND cardinality(g.capabilities) > cardinality(a.capabilities)
"""

#: The tables whose rows carry their source and entity, renamed in place.
SOURCED: tuple[str, ...] = (
    "proj.record",
    "er.alias",
    "er.identifier",
    "er.link",
    "gate.fast_path_rule",
)


def _rename_in(table: str) -> str:
    return f"""
WITH renamed(old, provider, new) AS (VALUES {_renamed_values()})
UPDATE {table} AS t
   SET entity = r.new
  FROM renamed AS r
 WHERE t.source = r.provider
   AND t.entity = r.old
"""


def upgrade() -> None:
    op.execute(ADD_COLUMN)
    op.execute(BACKFILL_CONNECTORS)
    op.execute(COPY_GRANTS)
    op.execute(COPY_INTO_PACKS)
    op.execute(COPY_INTO_AGENTS)
    for table in SOURCED:
        op.execute(_rename_in(table))


def downgrade() -> None:
    op.execute("ALTER TABLE agent.agent DROP COLUMN connectors")
