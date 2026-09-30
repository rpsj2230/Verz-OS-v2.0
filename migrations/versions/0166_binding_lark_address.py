"""A chat binding can keep the person's Lark address beside its fingerprint, as personal data.

**Why a raw identity is now kept, when `0002` was written to keep none.** `auth.principal_identity`
holds the digest `brain.gate.ingress.identity_hash` makes and nothing else, so nothing on an install
could address a bound person until they wrote to the bot, and an approval card could reach an
approver only after they asked for it. The owner decided needs-rupash 118 on 2026-09-29, option B:
keep each linked person's Lark address so the card is sent the moment the approval is raised. So
`channel_address` is added beside `identity_hash`, and the fingerprint stays the only thing a sender
is looked up by.

**Personal data, and treated as such, by declarations rather than by care.** The column is written
only for Lark (`brain.ops.binding_store.ADDRESS_KEPT_ON`), and only with an address whose digest is
the row's own fingerprint, so it can hold nothing but the identity that row already stands for.
It is cleared when the binding is retired, by unbinding or rebinding (`brain.ops.binding_store`),
and cleared on every row about a person an erasure reaches (`brain.ops.erasure_store.CLEARED`),
retired rows included. No read the console serves selects it, and it never reaches a log, a URL or
the ledger: `0118`'s trigger records a bind and an unbind by channel alone and ignores an update
that retires nothing.

**Retention follows the binding.** The table's retention is the identity store's, argued in
`brain.ops.retention`; the address lives exactly as long as the live binding it sits on, because
every path that retires the row clears it in the same statement.

**Nullable, with no backfill and no check constraint.** A binding made before this release has no
address until that person next writes to the bot, which is when the address arrives on a verified
event and is kept (`brain.channels.inbound.AddressBook`). A constraint added to a table that exists
narrows what the release still serving during a deploy may write, which
`brain.deployment.compatibility` refuses; the release before this one never names the column, so a
nullable column changes nothing it does. The grant is `0002`'s table grant and the policies are
`0045`'s table policies, and both cover a new column without a statement here.

**The downgrade** drops the column and every address kept, which puts every install back to sending
a card only when it is asked for.

Task ids: M10.3.5, M10.2.7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0166"
# Stacked after #299's 0168 on this branch, as the train lands them. Re-pointed at whichever
# migration is the head when it lands: nothing here depends on a table a later migration builds.
down_revision = "0168"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice. This one adds
#: a column and no table.
TABLES: tuple[str, ...] = ()

SCHEMA = "auth"
TABLE = "principal_identity"
COLUMN = "channel_address"

#: The longest channel address kept: an identity a chat vendor issued, never a document. Held equal
#: to `brain.tables.identity.CHANNEL_ADDRESS_CHARS` by a test.
CHANNEL_ADDRESS_CHARS = 255

#: `0002`'s CREATE TABLE of `auth.principal_identity` as it reads today, for the model comparison in
#: `tests/unit/test_tables.py`. Held to the ALTER the upgrade emits by
#: `tests/unit/test_card_on_raise.py`.
AMENDS_CREATE_TABLE: dict[str, str] = {
    "principal_id VARCHAR(128) NOT NULL, bound_at TIMESTAMP WITH TIME ZONE NOT NULL, assurance "
    "SMALLINT DEFAULT 1 NOT NULL,": (
        "principal_id VARCHAR(128) NOT NULL, bound_at TIMESTAMP WITH TIME ZONE NOT NULL, "
        f"channel_address VARCHAR({CHANNEL_ADDRESS_CHARS}), assurance SMALLINT DEFAULT 1 NOT NULL,"
    ),
}


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(COLUMN, sa.String(CHANNEL_ADDRESS_CHARS), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(TABLE, COLUMN, schema=SCHEMA)
