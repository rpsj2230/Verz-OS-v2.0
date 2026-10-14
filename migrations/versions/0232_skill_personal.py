"""A skill a person added for themselves is theirs until the department takes it.

`brain.member_library` built a personal library (M40.3.2): a person adds a skill by one of three
routes, sees it with its source, version and review state, offers it to the department, and may put
it only on agents they steward until the department has accepted it. The skill store had no way to
say a skill belongs to somebody, so none of that could be kept.

**`agent.skill_personal` is one row for each skill a person added as their own**: the skill's digest,
the person, when, and when they offered it to the department, empty until they did. The skill
itself stays where every skill is, in `agent.skill`, which is why a skill taken into the
department's library is the same bytes under the same digest and a decision about it is the same
review row. A skill with a row here and no offer is **not in the department's library**: the
library reads (`brain.ops.skill_store.library_of`) leave it out, so an administrator never lists
somebody's unfinished skill.

**Read by the application with `USING (true)`**, because the library statement must know which skills
to leave out, and a row names a digest and a person, never a word of the skill. **Written as the
person**: an insert is held to the person the session names, and an update may only set the offer,
once, as that person. Never DELETE: a skill the department has decided about stays decided.

**The downgrade** drops the table: every personal skill is then an ordinary skill in the library,
which is the state before the table. An unfinished skill becomes visible to administrators, which is
stated rather than hidden because the downgrade has nothing else to do with it.

Task ids: M40.3.2.1, M40.3.2.2, M40.3.2.3, M40.3.2.4

Revision ID: 0232
Revises: 0231
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0232"
# Follows 0231, the head of main when this was landed. Nothing here depends on 0226 to 0231.
down_revision = "0231"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing: the digest and the person are values, so
#: a row outlives a skill's retirement and a person leaving.
TABLES: tuple[str, ...] = ("agent.skill_personal",)

APP_ROLE = "brain_app"

#: Widths held equal to `brain.tables.skill_personal`.
DIGEST_CHARS = 64
PRINCIPAL_ID_CHARS = 128
DIGEST_PATTERN = "^[0-9a-f]{64}$"

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.skill_personal ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY skill_personal_readable ON agent.skill_personal
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY skill_personal_added_by_its_owner ON agent.skill_personal
        FOR INSERT TO brain_app
        WITH CHECK (owner_id = {PRINCIPAL} AND submitted_at IS NULL)
    """,
    f"""
    CREATE POLICY skill_personal_offered_by_its_owner ON agent.skill_personal
        FOR UPDATE TO brain_app
        USING (owner_id = {PRINCIPAL} AND submitted_at IS NULL)
        WITH CHECK (owner_id = {PRINCIPAL} AND submitted_at IS NOT NULL)
    """,
)

#: SELECT and INSERT, and UPDATE of the offer alone. Never DELETE.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.skill_personal TO brain_app",
    "GRANT UPDATE (submitted_at) ON agent.skill_personal TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    op.create_table(
        "skill_personal",
        sa.Column("digest", sa.String(DIGEST_CHARS), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "made_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"digest ~ '{DIGEST_PATTERN}'", name="digest_shape"),
        sa.CheckConstraint("length(btrim(owner_id)) > 0", name="owner_present"),
        schema="agent",
    )
    op.create_index(
        "ix_agent_skill_personal_owner_id", "skill_personal", ["owner_id"], schema="agent"
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The index, the policies and the grants go with the table.
    op.drop_table("skill_personal", schema="agent")
