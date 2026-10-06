"""The learning signal's log: what was noticed about each answer, and what each retrieval returned.

`brain.memory.signals` decided what a signal is in September and nothing kept one: the detectors
took both texts and handed back a verdict that went nowhere, which made M16.2.8, "all signals
logged from the first migration", a sentence about a table that did not exist. This is that
table, and the retrieval log M15.3.4 asks for beside it. `brain.tables.signal_log` holds the
argument for each column.

**`mem.signal`** is one row per thing noticed about one answer: its kind from the closed
vocabulary, the conversation and the message it is about, the trace it was noticed on, the
person it happened for and when. **No question, no answer and no reason**, and no column one
could go in, which is `brain.memory.signals.A_SIGNAL_LOG_MUST_NOT_BECOME_A_SECOND_TRANSCRIPT`.
One row per kind per answer: see
`brain.tables.signal_log.ONE_ANSWER_IS_ONE_PIECE_OF_EVIDENCE_PER_KIND`.

**`mem.retrieval`** is one row per retrieval, at its trace: the ids of the passages the model was
shown, in ranked order, the positions among them the answer cited, and how long the search took.

**A person reads their own rows and nobody else's, and that is the database's decision.** Both
tables' SELECT and INSERT policies pin the row to `app.principal_id`, so a signal is written in
the name of the person it happened for and read back only by them. SELECT and INSERT only:
nothing is updated and nothing deleted, so neither table needs a ledger trigger to be its own
history, which is `0154`'s shape for a mark.

**The install-wide reads are two `SECURITY DEFINER` functions, each returning a shape with no
person in it.** Learning needs counts across everybody, and the policies above refuse exactly
that. So:

- `mem.signal_counts(after, until)` returns how many signals of each kind were noticed in the
  window, **grouped by kind and by nothing else**. There is no column a principal, a
  conversation or a message could come back in, which is the enforceable half of
  `brain.memory.signals.A_COUNT_PER_PERSON_IS_A_PERFORMANCE_REVIEW` moved into the database.
- `mem.retrieval_events(after, until, most)` returns each retrieval as
  `brain.knowledge.quality.RetrievalEvent` shapes it: how many passages, which positions were
  cited, how long. **No passage id, no trace and no principal**, which is that module's
  `THE_LOG_MEASURES_OUR_RANKING_AND_NEVER_THE_CORPUS` kept for every reader but the asker.

Each pins its search path, names every object with its schema, reads no clock (both ends of the
window are the caller's), and is `STABLE`. EXECUTE is revoked from PUBLIC and granted to
`brain_app` alone, as `0177` does.

**The downgrade drops the functions and both tables.** A signal changes nothing by itself, so an
install downgraded past this migration answers exactly as it did, and learns from nothing again.

Task ids: M16.2.8, M15.3.4, M9.2.4

Revision ID: 0197
Revises: 0170
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0197"
# The single head of origin/main when this was written (0170 revises 0184); re-pointed at
# whichever migration is the head when it lands, since nothing here depends on anything after 0154.
down_revision = "0170"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice. Neither points
#: at anything: a conversation, a message, a trace and a passage are named by value, so a signal
#: outlives an erased conversation as a pointer that reaches nothing.
TABLES: tuple[str, ...] = ("mem.signal", "mem.retrieval")

APP_ROLE = "brain_app"

#: Widths and grammars copied for the reason `0009` gives about reading live code from a
#: migration, and held equal to `brain.tables.signal_log` by `tests/unit/test_signal_log.py`.
SIGNAL_CHARS = 16
TRACE_ID_CHARS = 64
PRINCIPAL_ID_CHARS = 128
CHUNK_ID_CHARS = 128
TRACE_ID = r"^[A-Za-z0-9_.-]{1,64}$"
SIGNAL_IN = (
    "signal IN ('contradicted', 'copied', 'escalated', 'reasked', 'rejected', 'reopened', "
    "'taken_over')"
)
POSITIONS_ARE_INSIDE_WHAT_WAS_RETURNED = "0 < ALL (used) AND cardinality(chunk_ids) >= ALL (used)"

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE mem.signal ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE mem.retrieval ENABLE ROW LEVEL SECURITY",
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
    f"""
    CREATE POLICY retrieval_read_by_its_person ON mem.retrieval
        FOR SELECT TO brain_app
        USING (principal_id = {PRINCIPAL})
    """,
    f"""
    CREATE POLICY retrieval_kept_in_the_sessions_name ON mem.retrieval
        FOR INSERT TO brain_app
        WITH CHECK (principal_id = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: a signal is a record of something noticed.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON mem.signal TO brain_app",
    "GRANT SELECT, INSERT ON mem.retrieval TO brain_app",
)

SIGNAL_COUNTS = "mem.signal_counts(timestamptz, timestamptz)"
RETRIEVAL_EVENTS = "mem.retrieval_events(timestamptz, timestamptz, integer)"

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

#: Each retrieval in a window as a ranking measurement: no passage, no trace, no person.
CREATE_RETRIEVAL_EVENTS = """
CREATE FUNCTION mem.retrieval_events(
    p_after timestamptz,
    p_until timestamptz,
    p_most integer
)
RETURNS TABLE (
    returned integer,
    used smallint[],
    latency_ms integer
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, mem
AS $events$
    SELECT cardinality(r.chunk_ids), r.used, r.latency_ms
    FROM mem.retrieval AS r
    WHERE r.at > p_after
      AND r.at <= p_until
    ORDER BY r.at, r.id
    LIMIT greatest(p_most, 0)
$events$
"""

FUNCTION_GRANTS: tuple[str, ...] = (
    f"REVOKE EXECUTE ON FUNCTION {SIGNAL_COUNTS} FROM PUBLIC",
    f"GRANT EXECUTE ON FUNCTION {SIGNAL_COUNTS} TO {APP_ROLE}",
    f"REVOKE EXECUTE ON FUNCTION {RETRIEVAL_EVENTS} FROM PUBLIC",
    f"GRANT EXECUTE ON FUNCTION {RETRIEVAL_EVENTS} TO {APP_ROLE}",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)
    for body in (CREATE_SIGNAL_COUNTS, CREATE_RETRIEVAL_EVENTS):
        assert "now()" not in body.lower(), "the window is the caller's, not the clock's"
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
    op.create_table(
        "retrieval",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=False),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "chunk_ids",
            postgresql.ARRAY(sa.String(CHUNK_ID_CHARS)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "used",
            postgresql.ARRAY(sa.SmallInteger()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"trace_id ~ '{TRACE_ID}'", name="trace_shape"),
        sa.CheckConstraint("length(btrim(principal_id)) > 0", name="principal_present"),
        sa.CheckConstraint(POSITIONS_ARE_INSIDE_WHAT_WAS_RETURNED, name="used_inside_returned"),
        sa.CheckConstraint("latency_ms >= 0", name="latency_is_a_duration"),
        sa.UniqueConstraint("trace_id"),
        schema="mem",
    )
    op.create_index("ix_mem_retrieval_at", "retrieval", ["at"], schema="mem")
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(CREATE_SIGNAL_COUNTS)
    op.execute(CREATE_RETRIEVAL_EVENTS)
    for statement in FUNCTION_GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {RETRIEVAL_EVENTS}")
    op.execute(f"DROP FUNCTION {SIGNAL_COUNTS}")
    # The policies and the grants go with the tables.
    op.drop_table("retrieval", schema="mem")
    op.drop_table("signal", schema="mem")
