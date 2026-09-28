"""A person binds a chat account with a one-time code, and every bind and unbind is audited.

**`auth.binding_code`: the nonce ledger (M10.3.1, M10.3.2).** One row per code a signed-in person
was shown: a digest of the channel and the code, the person, the identity provider's session it
was shown in, when it was minted, when it lapses and when it was used. `brain.tables.binding_code`
argues the columns. **SELECT, INSERT and UPDATE, and no DELETE**: a code is used or it lapses and
is never removed. The update policy admits only a row whose `used_at` is null, so a spent code
cannot be spent again or brought back by any statement the application role makes, and the insert
policy admits only an unspent row. `USING (true)` for the read, because the one reader is
`brain.ops.binding_store`, which finds a row only by the digest of a code somebody presented.

**Every chat binding and unbinding is written to the audit ledger, from the database (M10.3.4).**
A trigger on `auth.principal_identity` appends a `channel_binding` entry under
`principal:<person>` with `{"change": "bound" | "unbound", "channel": <channel>}`: `bound` for a
live row inserted, `unbound` for a live row retired, and nothing for the console channel, whose
rows are sign-in links and are recorded as `sign_in` by `0047`. A trigger rather than the store,
for `0047`'s reason: a binding made at a prompt is as much a way in as one made from a chat. **A
change with no actor named is recorded as `unattributed` and never refused**, in both directions,
as `0095b` records a disable. `0047` refuses an unnamed sign-in binding, and that was tried here
and rejected: every chat bind the application makes names its person through
`brain.ops.binding_store`, and the other writers of a non-console row, the email identities
`brain.identity.staff_sync` reads among them, would fail outright; an entry saying a binding
appeared that nobody claimed is the finding an audit looks for, and it is kept. The identity is
never in the entry.

**A new action, `channel_binding`, and `0105`'s list superseded.** `brain.audit.ledger` argues the
member. Whichever later migration re-states the action list has to carry it, and
`tests/unit/test_tables.py` compares the chain of supersessions with the model's list, so one that
drops it fails there rather than on an install.

**The append is `0003`'s, one more copy of that block**, for the reason `0047` gives against
editing a function every grant in production goes through.

**The downgrade** drops the trigger, its function and the table, which forgets every unused code
(each then answers as a wrong one, which is what a code is after its ten minutes anyway), and puts
`0105`'s action list back `NOT VALID`, for `0026`'s reason: an entry already recorded stays. The
bindings themselves are `auth.principal_identity`'s rows and are untouched.

Task ids: M10.3.1, M10.3.2, M10.3.4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0118"
# The head of origin/main when this was committed (d654f1f4, 0121, which landed before it); 0118 is
# the number the Wave 2 plan holds for the channels screen and binding.
down_revision = "0121"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("auth.binding_code",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason about reading live code from a migration, and held equal to
#: `brain.tables.binding_code` by `tests/unit/test_channel_binding.py`.
CHANNELS = (
    "channel IN ('api', 'console', 'email', 'lark', 'scheduler', 'slack', 'teams', 'telegram', "
    "'webhook', 'whatsapp', 'widget')"
)
DIGEST_SHAPE = "code_digest ~ '^[0-9a-f]{64}$'"
CODE_DIGEST_CHARS = 64
CHANNEL_CHARS = 16
PRINCIPAL_ID_CHARS = 128
SESSION_ID_CHARS = 120

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is `0105`'s.
WIDENED_ACTIONS = (
    "action IN ('agent_owner', 'approval', 'breach', 'break_glass', 'certification', "
    "'channel_binding', 'compose_change', 'connector', 'credential', 'deny', 'elevation', "
    "'entity_merge', 'erasure', 'grant', 'instructions', 'leash_change', 'legal_hold', 'memory', "
    "'organisation', 'principal_state', 'publish', 'record_read', 'retention', 'revoke', "
    "'routing', 'session_end', 'setting', 'sign_in', 'skill', 'vault_access', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('agent_owner', 'approval', 'breach', 'break_glass', 'certification', "
    "'compose_change', 'connector', 'credential', 'deny', 'elevation', 'entity_merge', 'erasure', "
    "'grant', 'instructions', 'leash_change', 'legal_hold', 'memory', 'organisation', "
    "'principal_state', 'publish', 'record_read', 'retention', 'revoke', 'routing', "
    "'session_end', 'setting', 'sign_in', 'skill', 'vault_access', 'webhook')"
)

#: What this migration replaces: `0105`'s action list, the one in the database.
SUPERSEDES: dict[str, str] = {NARROWER_ACTIONS: WIDENED_ACTIONS}

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT, UPDATE ON auth.binding_code TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE auth.binding_code ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY binding_code_readable ON auth.binding_code
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY binding_code_mintable ON auth.binding_code
        FOR INSERT TO brain_app
        WITH CHECK (used_at IS NULL)
    """,
    """
    CREATE POLICY binding_code_spendable ON auth.binding_code
        FOR UPDATE TO brain_app
        USING (used_at IS NULL)
        WITH CHECK (true)
    """,
)

#: The words the trigger appends: `brain.audit.record.ChannelBindingChange`'s.
BINDING_TRIGGER_FUNCTION = """
CREATE FUNCTION auth.record_channel_binding() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_change text;
    v_actor text;
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF NEW.channel = 'console' THEN
        RETURN NULL;
    END IF;
    IF tg_op = 'INSERT' THEN
        IF NEW.deleted_at IS NOT NULL THEN
            RETURN NULL;
        END IF;
        v_change := 'bound';
    ELSE
        IF OLD.deleted_at IS NOT NULL OR NEW.deleted_at IS NULL THEN
            RETURN NULL;
        END IF;
        v_change := 'unbound';
    END IF;

    v_actor := NULLIF(current_setting('brain.actor_id', true), '');
    v_details := jsonb_build_object('change', v_change, 'channel', NEW.channel);
    IF v_actor IS NULL THEN
        v_actor := 'unattributed';
        v_details := v_details || jsonb_build_object('actor', 'unattributed');
    END IF;

    -- The append, as 0003's gate.record_entitlement_change and every trigger since write it.
    PERFORM pg_advisory_xact_lock(8274419004);
    SELECT COALESCE(max(e.seq) + 1, 0) INTO v_seq FROM obs.audit_entry e;
    SELECT COALESCE(
        (SELECT e.entry_hash FROM obs.audit_entry e ORDER BY e.seq DESC LIMIT 1),
        repeat('0', 64)
    ) INTO v_prev;
    v_ent_hash := COALESCE(NULLIF(current_setting('brain.ent_hash', true), ''), repeat('0', 32));
    v_trace := COALESCE(
        NULLIF(current_setting('brain.trace_id', true), ''),
        'tx.' || pg_current_xact_id()::text
    );
    v_entry := obs.audit_entry_hash(
        v_seq, v_at, v_actor, 'channel_binding', 'principal:' || NEW.principal_id, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, v_actor, 'channel_binding', 'principal:' || NEW.principal_id,
                v_ent_hash, v_trace, v_details, v_prev, v_entry);

    GET DIAGNOSTICS v_written = ROW_COUNT;
    IF v_written <> 1 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'the ledger already holds seq ' || v_seq
                      || '; the audit entry was not appended',
            ERRCODE = 'restrict_violation',
            HINT = 'an append that is discarded silently is the failure this refuses';
    END IF;
    RETURN NULL;
END;
$$
"""

BINDING_TRIGGER = """
CREATE TRIGGER principal_identity_records_channel_binding
    AFTER INSERT OR UPDATE ON auth.principal_identity
    FOR EACH ROW EXECUTE FUNCTION auth.record_channel_binding()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    op.create_table(
        "binding_code",
        sa.Column("code_digest", sa.String(CODE_DIGEST_CHARS), nullable=False),
        sa.Column("channel", sa.String(CHANNEL_CHARS), nullable=False),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("session_id", sa.String(SESSION_ID_CHARS), nullable=False),
        sa.Column("minted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(DIGEST_SHAPE, name="digest_shape"),
        sa.CheckConstraint(CHANNELS, name="channel"),
        sa.CheckConstraint("channel <> 'console'", name="not_the_sign_in_channel"),
        sa.CheckConstraint("length(btrim(session_id)) > 0", name="session_present"),
        sa.CheckConstraint("expires_at >= minted_at", name="expires_after_minting"),
        sa.CheckConstraint("used_at IS NULL OR used_at >= minted_at", name="used_after_minting"),
        sa.ForeignKeyConstraint(["principal_id"], ["auth.principal.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("code_digest"),
        schema="auth",
    )
    op.create_index(
        "ix_auth_binding_code_principal_id", "binding_code", ["principal_id"], schema="auth"
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)
    # The bare constraint name, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.execute(BINDING_TRIGGER_FUNCTION)
    op.execute(BINDING_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER principal_identity_records_channel_binding ON auth.principal_identity")
    op.execute("DROP FUNCTION auth.record_channel_binding()")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", NARROWER_ACTIONS, schema="obs", postgresql_not_valid=True
    )
    # The index, the policies and the grant go with the table.
    op.drop_table("binding_code", schema="auth")
