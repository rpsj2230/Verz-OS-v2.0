"""A document records how it arrived and, for a link, the address, so a link can be fetched again.

The agent's Knowledge section lists what an agent draws on and could not say whether a document
arrived as a file or as a link (M39.9.1.1), or offer to fetch a link again (M39.9.1.5), because
`know.item` recorded neither. The only trace of a link was the first line of its text, which a
list does not read and which a file may also begin with, so reading it would have been a guess.

**Two nullable columns on `know.item`: `arrived_as` and `source_url`.** `arrived_as` is `file` or
`link`; `source_url` is the address the person gave, before any redirect, and only a link has one.
Both are written by the doors that add a document (`brain.knowledge.uploads`), and by the refetch,
which writes a new version carrying the same address.

**Nothing is backfilled, on purpose.** Every document added before this migration has neither
column set, and a list says "unknown" for it. A backfill would read a document's text to decide,
which is the guess the columns exist to avoid, and a wrong "link" on a file would offer a fetch of
an address that is not there.

**The release before this one keeps working.** It never names either column, so both are null in
every row it writes; the two checks admit null for each, so no row it can write is refused. The
application role holds the table's privileges already and no policy changes: a row is read and
written under the policy it was always under, and the ledger trigger names only the columns that
changed, never their values, so an address never enters the ledger.

**The address stays on the row.** It is read only by the refetch, for a person who may act on the
document, and no list returns it: a share link carries a token.

The downgrade drops the checks and the columns, and with them every recorded address.

Task ids: M39.9.1.1, M39.9.1.5

Revision ID: 0226
Revises: 0212
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0226"
# The head of origin/main when this was written. Other builders' numbers sit between, in the same
# train, so the coordinator relinks this behind whichever of them lands last.
down_revision = "0212"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

#: The longest address the link door accepts, `brain.knowledge.item.MAX_SOURCE_URL_CHARS`.
SOURCE_URL_CHARS = 2048

ARRIVED_AS_A_FILE_OR_LINK = "arrived_as IS NULL OR arrived_as IN ('file', 'link')"
AN_ADDRESS_BELONGS_TO_A_LINK = (
    f"source_url IS NULL OR (arrived_as = 'link' AND length(source_url) BETWEEN 1 AND "
    f"{SOURCE_URL_CHARS})"
)


def upgrade() -> None:
    assert "arrived_as" in ARRIVED_AS_A_FILE_OR_LINK
    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.add_column("item", sa.Column("arrived_as", sa.String(8), nullable=True), schema="know")
    op.add_column("item", sa.Column("source_url", sa.Text(), nullable=True), schema="know")
    op.create_check_constraint(
        "arrived_as_a_file_or_link", "item", ARRIVED_AS_A_FILE_OR_LINK, schema="know"
    )
    op.create_check_constraint(
        "an_address_belongs_to_a_link", "item", AN_ADDRESS_BELONGS_TO_A_LINK, schema="know"
    )


def downgrade() -> None:
    op.drop_constraint("an_address_belongs_to_a_link", "item", schema="know", type_="check")
    op.drop_constraint("arrived_as_a_file_or_link", "item", schema="know", type_="check")
    op.drop_column("item", "source_url", schema="know")
    op.drop_column("item", "arrived_as", schema="know")
