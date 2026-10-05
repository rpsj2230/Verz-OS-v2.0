"""A consent a person starts at a vendor is held here until the vendor answers, once, for them alone.

M11.8.6 has a connector that authorises by OAuth consented to from the console: the console sends
the administrator to the vendor's page, and the vendor sends them back with a code and the state the
consent was asked with. Between the two, this install has to hold what the answer is checked
against and the PKCE verifier the code is exchanged with. `ops.oauth_consent` is that, one row per
consent started.

**Single use, bound to the principal who started it, and short-lived, by the database.** A row is
inserted with `used_at` empty and `expires_at` `brain.connectors.oauth.CONSENT_LIFETIME_SECONDS`
after it was issued, and the one change ever made to it is setting `used_at`: the application role
is granted UPDATE on that column alone, and the update policy admits a row only while `used_at` is
empty and only into a row where it is set. Every policy holds `principal_id` to the actor the
transaction is attributed to (`brain.actor_id`), so a person cannot read, insert for, or use
somebody else's consent, whatever the application asks. `brain.ops.connector_consent` takes a
consent with one `UPDATE ... RETURNING` naming the state's digest, the person and the instant, so a
replayed state, a state issued to somebody else, an expired one and one never issued all come back
as no row, in one statement, and none of them can be told apart from another.

**The state is never stored; the verifier is stored sealed under it.** The row is found by
`state_digest`, the SHA-256 of the state, and `sealed_verifier` is the verifier sealed with a key
derived from the state, so the table alone opens no verifier. See
`brain.connectors.oauth.A_KEPT_VERIFIER_IS_SEALED_UNDER_THE_STATE_THE_TABLE_NEVER_HOLDS`.

**A consent is for a source, or a person's own (`kind`).** A source's consent is started by
somebody who may connect it and buys the one refresh token every read of the source uses; a
person's own consent is started by that person for their own account and buys a token read only
for their questions (`brain.connectors.oauth.ConsentKind`). The row says which, so the answer is
kept where its kind says and judged by the authority its kind asks, and the kind cannot be changed
after the row is written: it is not among the columns the application may update. Nothing else
differs, and the policies need no second rule: `principal_id` already names whose consent it is,
and every policy already holds it to the actor. Added in place rather than in a migration of its
own, because no install had applied `0180` when the personal consent was designed.

**No DELETE.** A consent used or expired stays as the record that it was started, by whom and when,
and holds nothing a reader could use. Rows are small and one is written per press of a button.

**The downgrade** drops the table; its policies and grants go with it.

Revised `0167` when it was written, and is re-pointed at whichever migration is the head when it
lands: nothing here depends on anything after `0068`'s connections. Now `0154`, main's head when
the Google Workspace connector was stacked on it.

Task ids: M11.8.6

Revision ID: 0180
Revises: 0154
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0180"
# The head of origin/main when this branch last took it in: 0154, which lands after 0167.
down_revision = "0154"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.oauth_consent",)

APP_ROLE = "brain_app"

#: Widths and grammars copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.oauth_consent` by `tests/unit/test_connector_consent.py`.
CONNECTOR_CHARS = 64
CONNECTOR_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,62}$"
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
PRINCIPAL_ID_CHARS = 128
DIGEST_PATTERN = r"^[0-9a-f]{64}$"
RETURN_ADDRESS_CHARS = 512
SEALED_CHARS = 256
#: `brain.connectors.oauth.ConsentKind`'s values, held equal by `test_connector_consent.py`.
KINDS: tuple[str, ...] = ("source", "person")
KIND_CHARS = 16

#: The actor a transaction is attributed to, empty when none was set.
ACTOR = "NULLIF(current_setting('brain.actor_id', true), '')"

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.oauth_consent ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY oauth_consent_read_by_its_principal ON ops.oauth_consent
        FOR SELECT TO brain_app
        USING (principal_id = {ACTOR})
    """,
    f"""
    CREATE POLICY oauth_consent_started_by_its_principal ON ops.oauth_consent
        FOR INSERT TO brain_app
        WITH CHECK (principal_id = {ACTOR} AND used_at IS NULL)
    """,
    f"""
    CREATE POLICY oauth_consent_used_once_by_its_principal ON ops.oauth_consent
        FOR UPDATE TO brain_app
        USING (principal_id = {ACTOR} AND used_at IS NULL)
        WITH CHECK (principal_id = {ACTOR} AND used_at IS NOT NULL)
    """,
)

#: SELECT and INSERT, and UPDATE of `used_at` alone. Never DELETE.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON ops.oauth_consent TO brain_app",
    "GRANT UPDATE (used_at) ON ops.oauth_consent TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "oauth_consent",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("state_digest", sa.String(64), nullable=False),
        sa.Column("connector", sa.String(CONNECTOR_CHARS), nullable=False),
        sa.Column("kind", sa.String(KIND_CHARS), nullable=False),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("return_address", sa.String(RETURN_ADDRESS_CHARS), nullable=False),
        sa.Column("sealed_verifier", sa.String(SEALED_CHARS), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"state_digest ~ '{DIGEST_PATTERN}'", name="state_digest_shape"),
        sa.CheckConstraint(f"connector ~ '{CONNECTOR_NAME_PATTERN}'", name="connector_shape"),
        sa.CheckConstraint(
            "kind IN (" + ", ".join(f"'{one}'" for one in KINDS) + ")", name="kind_known"
        ),
        sa.CheckConstraint(f"principal_id ~ '{IDENTIFIER}'", name="principal_id_shape"),
        sa.CheckConstraint("return_address LIKE 'https://%'", name="return_address_is_https"),
        sa.CheckConstraint("length(sealed_verifier) > 0", name="verifier_is_sealed"),
        sa.CheckConstraint("expires_at > issued_at", name="expires_after_issue"),
        sa.CheckConstraint("used_at IS NULL OR used_at >= issued_at", name="used_after_issue"),
        sa.UniqueConstraint("state_digest"),
        schema="ops",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grants go with the table.
    op.drop_table("oauth_consent", schema="ops")
