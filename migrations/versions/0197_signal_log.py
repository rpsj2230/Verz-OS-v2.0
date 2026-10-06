"""The learning signal's log: what was noticed about each answer, by id and never in words.

`brain.memory.signals` decided in September what a signal is and nothing kept one: the detectors
took both texts and handed back a verdict that went nowhere, which made M16.2.8, "all signals
logged from the first migration", a sentence about a table that did not exist. This is that
table. `brain.tables.signal_log` holds the argument for each column.

**`mem.signal`** is one row per thing noticed about one answer: its kind from the closed
vocabulary, the conversation and the message it is about, the trace it was noticed on, the
person it happened for and when. **No question, no answer and no reason**, and no column one
could go in, which is `brain.memory.signals.A_SIGNAL_LOG_MUST_NOT_BECOME_A_SECOND_TRANSCRIPT`.
One row per kind per answer: see
`brain.tables.signal_log.ONE_ANSWER_IS_ONE_PIECE_OF_EVIDENCE_PER_KIND`.

**A retrieval is not logged here.** `ops.retrieval_event` (migration `0193`, #415) keeps M15.3.4's
retrieval log, read by `brain.knowledge.quality.signal`, and a second table for the same leaf
would be a second place for it to be wrong.

**A person reads their own rows and nobody else's, and that is the database's decision.** The
SELECT and INSERT policies pin the row to `app.principal_id`, so a signal is written in the name
of the person it happened for and read back only by them. SELECT and INSERT only: nothing is
updated and nothing deleted, so the table needs no ledger trigger to be its own history, which
is `0154`'s shape for a mark.

**The install-wide read is one `SECURITY DEFINER` function returning a shape with no person in
it.** Learning needs counts across everybody, and the policies above refuse exactly that. So
`mem.signal_counts(after, until)` returns how many signals of each kind were noticed in the
window, **grouped by kind and by nothing else**. There is no column a principal, a conversation
or a message could come back in, which is the enforceable half of
`brain.memory.signals.A_COUNT_PER_PERSON_IS_A_PERFORMANCE_REVIEW` moved into the database. It
pins its search path, names every object with its schema, reads no clock (both ends of the
window are the caller's), and is `STABLE`. EXECUTE is revoked from PUBLIC and granted to
`brain_app` alone, as `0177` does.

**The downgrade drops the function and the table.** A signal changes nothing by itself, so an
install downgraded past this migration answers exactly as it did, and learns from nothing again.

Task ids: M16.2.8, M9.2.4

Revision ID: 0197
Revises: 0196
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0197"
# The head of the migration train when this was merged onto it (0196, the tool attachments);
# re-pointed at whichever migration is the head when it lands, since nothing here depends on
# anything after 0154.
down_revision = "0196"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice. It points at
#: nothing: a conversation, a message and a trace are named by value, so a signal outlives an
#: erased conversation as a pointer that reaches nothing.
TABLES: tuple[str, ...] = ("mem.signal",)

APP_ROLE = "brain_app"

#: Widths and grammars copied for the reason `0009` gives about reading live code from a
#: migration, and held equal to `brain.tables.signal_log` by `tests/unit/test_signal_log.py`.
SIGNAL_CHARS = 16
TRACE_ID_CHARS = 64
PRINCIPAL_ID_CHARS = 128
TRACE_ID = r"^[A-Za-z0-9_.-]{1,64}$"
SIGNAL_IN = (
    "signal IN ('contradicted', 'copied', 'escalated', 'reasked', 'rejected', 'reopened', "
    "'taken_over')"
)

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE mem.signal ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY signal_read_by_its_person ON mem.signal
        FOR SELECT TO brain_app
        USING (principal_id = {PRINCIPAL})
    """,
    f"""
    CREATE POLICY signal_noticed_in_the_sessions_name ON mem.signal
        FOR INSERT TO brain_app
        WITH CHECK (principal_id = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: a signal is a record of something noticed.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON mem.signal TO brain_app",)

SIGNAL_COUNTS = "mem.signal_counts(timestamptz, timestamptz)"

#: How many signals of each kind were noticed in a window, and nothing about whose.
CREATE_SIGNAL_COUNTS = """
CREATE FUNCTION mem.signal_counts(
    p_after timestamptz,
    p_until timestamptz
)
RETURNS TABLE (
    signal character varying,
    noticed bigint
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, mem
AS $counts$
    SELECT s.signal, count(*)
    FROM mem.signal AS s
    WHERE s.at > p_after
      AND s.at <= p_until
    GROUP BY s.signal
    ORDER BY s.signal
$counts$
"""

FUNCTION_GRANTS: tuple[str, ...] = (
    f"REVOKE EXECUTE ON FUNCTION {SIGNAL_COUNTS} FROM PUBLIC",
    f"GRANT EXECUTE ON FUNCTION {SIGNAL_COUNTS} TO {APP_ROLE}",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)
    assert "now()" not in CREATE_SIGNAL_COUNTS.lower(), (
        "the window is the caller's, not the clock's"
    )
    op.create_table(
        "signal",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("signal", sa.String(SIGNAL_CHARS), nullable=False),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("message_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=True),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(SIGNAL_IN, name="signal_kind"),
        sa.CheckConstraint(f"trace_id IS NULL OR trace_id ~ '{TRACE_ID}'", name="trace_shape"),
        sa.CheckConstraint("length(btrim(principal_id)) > 0", name="principal_present"),
        sa.UniqueConstraint("signal", "message_id"),
        schema="mem",
    )
    op.create_index("ix_mem_signal_at", "signal", ["at"], schema="mem")
    op.create_index("ix_mem_signal_principal_id_at", "signal", ["principal_id", "at"], schema="mem")
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(CREATE_SIGNAL_COUNTS)
    for statement in FUNCTION_GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {SIGNAL_COUNTS}")
    # The policies and the grants go with the table.
    op.drop_table("signal", schema="mem")
