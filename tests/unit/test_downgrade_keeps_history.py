"""A downgrade over a ledger that already holds rows, measured against PostgreSQL.

CI's round trip on d960cf8 ran `alembic downgrade base` over the database the unit tests had just
filled and stopped at `0059`: re-adding the narrower subject grammar validated every row in
`obs.audit_entry`, and a row the newer release wrote under the wider grammar refused it. The ledger
is append-only, so nothing may be deleted to make room, and the same downgrade would stop any real
install rolling that release back. `brain.ops.migration_policy` now refuses a downgrade that adds a
check constraint without `NOT VALID`, which is a rule about what a migration declares. This file is
the property the declaration is for, on a database: the downgrade runs, the row written under the
newer release is still there, and the older rule still refuses the next write.

**The row is written by the ledger's own writer.** A feature switch inserted into `ops.setting`
is appended by `0059`'s trigger, so the entry is chained, hashed and shaped exactly as an install
would hold it, rather than a row this test composed to pass. The writes after the downgrade are
composed, because the downgrade removes that trigger: both carry the same action, actor, reach,
trace and details, differ only in the subject kind, and are chained with the ledger's own
`obs.audit_entry_hash`, so the only rule either can break is the subject grammar.

**It skips without a server**, which CI provides. With pgvector the chain is built to head and the
downgrade runs every revision after `0058`; without it `through_0059` builds `0059` from the
migrations its tables need, and the downgrade runs `0059`'s alone.

Task ids: none
"""

from __future__ import annotations

import psycopg
import pytest

from tests.fixtures.scratch_postgres import migrate, sql
from tests.unit.test_console_control_audit import through_0059
from tests.unit.test_credential_writes import entries

DATABASE = "brain_downgrade_keeps_history"

#: The constraint the downgrade re-creates, as `brain.db.NAMING_CONVENTION` names it.
SUBJECT_GRAMMAR = "ck_audit_entry_subject_grammar"

#: One chained entry, composed as `0003`'s append composes one: the next sequence number, the last
#: entry's hash as the parent, and `obs.audit_entry_hash` over the same values. Only the subject is
#: a parameter, so a refusal can come from nothing but what the subject is.
APPEND_WITH_SUBJECT = """
INSERT INTO obs.audit_entry (
    seq, at, actor_id, action, subject, ent_hash, trace_id, details, prev_hash, entry_hash
)
SELECT
    s.seq, s.at, 'u_operator', 'grant', %(subject)s::text, repeat('0', 32),
    'trace-after-downgrade', '{}'::jsonb, s.prev,
    obs.audit_entry_hash(
        s.seq, s.at, 'u_operator', 'grant', %(subject)s::text, repeat('0', 32),
        'trace-after-downgrade', '{}'::jsonb, s.prev
    )
FROM (
    SELECT
        COALESCE(max(e.seq) + 1, 0) AS seq,
        now() AS at,
        COALESCE(
            (SELECT x.entry_hash FROM obs.audit_entry x ORDER BY x.seq DESC LIMIT 1),
            repeat('0', 64)
        ) AS prev
    FROM obs.audit_entry e
) AS s
"""


def append(url: str, subject: str) -> None:
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(APPEND_WITH_SUBJECT, {"subject": subject})


def validated(url: str) -> bool:
    rows = sql(
        url,
        "SELECT convalidated FROM pg_constraint "
        "WHERE conrelid = 'obs.audit_entry'::regclass AND conname = %s",
        SUBJECT_GRAMMAR,
    )
    assert len(rows) == 1, f"{SUBJECT_GRAMMAR} is not on obs.audit_entry"
    return bool(rows[0][0])


def test_a_downgrade_past_0059_keeps_a_setting_entry_and_refuses_the_next_one() -> None:
    """The downgrade that failed CI, over a ledger holding a `setting:` entry, which is a subject
    kind only `0059` admits.

    It runs; the entry is still there, byte for byte; the re-created grammar is `NOT VALID`; a new
    `setting:` entry is refused by that grammar and by nothing else, while the same entry under a
    subject kind the older grammar admits is accepted, which is the positive half; and going
    forward to `0059` again re-creates the wider grammar validated, which every row satisfies.

    Delete this and the rule in `brain.ops.migration_policy` is the only evidence, and it reads what
    a migration declares rather than what PostgreSQL does with it: `NOT VALID` dropped by a
    SQLAlchemy upgrade, or a downgrade that deleted the entry to make room, would pass it. **Skips
    without a server.**"""
    with through_0059(DATABASE) as url:
        sql(
            url,
            "INSERT INTO ops.setting (key, value_type, value, description, updated_by) VALUES "
            "('feature.schedule_control', 'boolean', 'true', 'A switch', 'u_operator')",
        )
        before = [one for one in entries(url) if one.subject.startswith("setting:")]

        migrate(DATABASE, "downgrade", "0058")

        after = [one for one in entries(url) if one.subject.startswith("setting:")]
        at = sql(url, "SELECT version_num FROM alembic_version")
        grammar_validated = validated(url)
        with pytest.raises(psycopg.errors.CheckViolation) as refused:
            append(url, "setting:feature.written_after_the_downgrade")
        append(url, "principal:u_written_after_the_downgrade")
        admitted = [one.subject for one in entries(url)][-1]

        migrate(DATABASE, "upgrade", "0059")
        revalidated = validated(url)
        kept = [one for one in entries(url) if one.subject.startswith("setting:")]

    assert len(before) == 1
    assert before[0].subject == "setting:feature.schedule_control"
    assert at == [("0058",)]
    assert after == before
    assert grammar_validated is False
    assert refused.value.diag.constraint_name == SUBJECT_GRAMMAR
    assert admitted == "principal:u_written_after_the_downgrade"
    assert revalidated is True
    assert kept == before
