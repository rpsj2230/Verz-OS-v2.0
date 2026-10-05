"""A stored skill keeps the bytes of every script it carries, and the database checks their sha256.

M12.4.11 asks that a skill's approval digest cover the bytes of every script it carries, so a script
changed after approval is refused before it runs. Until this migration a skill that declared a
script was refused at the door, because the digest covered the script's name and nothing held its
bytes. `brain.tools.skills.Skill.script_sha256` now puts each script's sha256 into the digest, and
this table is where the bytes are kept.

**`agent.skill_script` is one row per script of one stored skill version**, keyed by the skill's
digest and the script's path. The digest is the version's key in `agent.skill`, so a script belongs
to exactly the version a reviewer approved, and an edited script is a new version with a new digest
and a new row; nothing is ever updated.

**The database refuses a row whose sha256 is not the sha256 of its bytes.** The check computes it
with PostgreSQL's own `sha256`, so a hash cannot be written beside bytes it does not describe by any
route, the application's or a hand repair's. Rejected: trusting the writer to compute it, which is
the shape that lets a store bug turn into an approval of something nobody reviewed.

**Who writes a row is the person who added the skill**, in the same transaction: the insert policy
admits a row only for a skill the session's principal submitted, which is `0056`'s rule for the
skill itself. Everybody reads, as everybody reads `agent.skill`; what an agent may run is decided by
the approval and the pin, not by who can see the bytes. SELECT and INSERT, never UPDATE or DELETE.

No ledger entry: the skill's own insert is the entry, and its digest now covers these bytes.

**The downgrade** drops the table. A skill with scripts stored under this migration then reads back
without them and no longer digests to its key, so the library leaves it out, which is
`brain.ops.skill_store`'s rule for a row that does not construct, and its approval is not honoured.

Revises `0167`, the head of main when this was written.

Task ids: M12.4.11

Revision ID: 0178
Revises: 0167
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0178"
# The head of origin/main when this was written; re-pointed when it lands.
down_revision = "0167"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.skill_script",)

APP_ROLE = "brain_app"

#: Restated rather than imported, so this migration means what it meant when it was written.
DIGEST_CHARS = 64
PATH_CHARS = 200
MAX_SCRIPT_BYTES = 64 * 1024
PATH_PATTERN = r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.skill_script ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY skill_script_readable ON agent.skill_script
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY skill_script_added_with_its_skill ON agent.skill_script
        FOR INSERT TO brain_app
        WITH CHECK (EXISTS (
            SELECT 1 FROM agent.skill s
             WHERE s.digest = skill_script.digest AND s.submitted_by = {PRINCIPAL}
        ))
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE. See the module docstring.
GRANTS: tuple[str, ...] = (f"GRANT SELECT, INSERT ON agent.skill_script TO {APP_ROLE}",)


def upgrade() -> None:
    op.create_table(
        "skill_script",
        sa.Column(
            "digest",
            sa.String(DIGEST_CHARS),
            sa.ForeignKey("agent.skill.digest"),
            primary_key=True,
        ),
        sa.Column("path", sa.String(PATH_CHARS), primary_key=True),
        sa.Column("sha256", sa.String(DIGEST_CHARS), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(f"path ~ '{PATH_PATTERN}'", name="path_shape"),
        sa.CheckConstraint(f"sha256 ~ '{SHA256_PATTERN}'", name="sha256_shape"),
        sa.CheckConstraint(
            "encode(sha256(content), 'hex') = sha256", name="sha256_is_the_contents"
        ),
        sa.CheckConstraint(
            f"octet_length(content) BETWEEN 1 AND {MAX_SCRIPT_BYTES}", name="content_bounded"
        ),
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies go with the table.
    op.drop_table("skill_script", schema="agent")
