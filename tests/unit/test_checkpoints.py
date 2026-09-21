"""Where a graph's saved state is allowed to go, and the connection it may not use.

Every test here is about a checkpointer that would be constructed, would appear to work, and
would either put payload rows somewhere no sweep enumerates or fail only in production.

No task ids. `brain.ops.checkpoints` claims none: langgraph is not a dependency and nothing
builds a graph, so M32.4.1.2 is served rather than closed. These tests exist because the
decisions are real even where the saver is not, and because the worker refuses a bad one
today.
"""

from __future__ import annotations

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.db import SCHEMAS
from brain.ops.checkpoints import (
    BRANCH_CHANNEL_PREFIX,
    CHECKPOINT_SCHEMA,
    ERROR_CHANNEL,
    INTERRUPT_CHANNEL,
    START_CHANNEL,
    TASKS_CHANNEL,
    CheckpointerConfig,
    CheckpointerError,
    checkpoint_refusals,
    connection_refusals,
    owner_of,
)
from brain.ops.queue import SEARCH_PATH_SQL, pooler_url_findings

APP_URL = "postgresql+psycopg://brain:pw@pgbouncer:5432/brain"
DIRECT_URL = "postgresql+psycopg://brain:pw@db:5432/brain"


class RecordingConnection:
    """Records what a pool's `configure` step runs, and whether it left the connection idle."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.committed = False

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executed.append((sql, params))

    def commit(self) -> None:
        self.committed = True


# --------------------------------------------------- the connection
def test_a_checkpointer_handed_the_applications_own_connection_string_is_refused() -> None:
    """The application connects through the transaction pooler, and the saver prepares its
    statements server-side. A pooler in transaction mode hands the next statement to a
    backend that never saw the prepare, which fails in production and nowhere else because a
    development machine has no pooler. Delete this and the fourth instance of the pooler bug
    in this repository ships."""
    refusals = connection_refusals(APP_URL, app_url=APP_URL)

    assert any("application's own connection string" in r for r in refusals)


def test_a_checkpointer_url_naming_the_pooler_is_refused_on_its_own() -> None:
    """The same fault reached differently: a checkpointer with its own variable, set to the
    pooler because that is what the other variable said. Delete this and only the exact-match
    case is caught, and the exact match is the one somebody fixes first."""
    assert any("transaction pooler" in r for r in connection_refusals(APP_URL))


def test_a_direct_checkpointer_url_is_accepted_without_comment() -> None:
    """A check that refuses everything is a check that gets disabled. Delete this and
    `connection_refusals` could return a finding unconditionally and every refusal test above
    would still pass while no worker could ever start."""
    assert connection_refusals(DIRECT_URL, app_url=APP_URL) == ()


def test_the_pooler_detection_is_the_queues_and_not_a_second_copy() -> None:
    """Asserted structurally rather than by both happening to be right today. The house rule
    is that the copy which drifts is the one nobody is looking at, and every failure in this
    family is silent, so the drift is found by the thing it was meant to prevent.

    Delete this and `brain.ops.checkpoints` can grow its own list of pooler hostnames, which
    reads as tidier and is the fourth copy of a rule this repository has already been bitten
    by three times."""
    assert connection_refusals(APP_URL) == pooler_url_findings(APP_URL)
    assert connection_refusals(f"{DIRECT_URL}?prepare_threshold=0") == pooler_url_findings(
        f"{DIRECT_URL}?prepare_threshold=0"
    )


# --------------------------------------------------- where the tables land
def test_the_checkpoint_schema_is_one_the_row_level_security_sweep_enumerates() -> None:
    """The whole of what the schema choice buys. `brain.ops.sweeps.sweep_rls` reads
    `brain.db.SCHEMAS` and looks nowhere else, and the saver creates its own tables with no
    row-level security on them. In a named schema that is a red sweep somebody acts on; in
    `public` it is nothing at all.

    Delete this and `CHECKPOINT_SCHEMA` can be set to a schema that reads sensibly and is not
    enumerated, which is the same outcome as leaving it at the default."""
    assert CHECKPOINT_SCHEMA in SCHEMAS


def test_the_checkpoint_schema_is_not_one_that_promised_to_hold_no_payloads() -> None:
    """`obs` holds metadata and no payloads, and its retention argument was made on the
    strength of that; `mem` holds what the system learnt rather than what happened; `chat` is
    a transcript. A checkpoint is the run so far, so filing it in any of the three makes one
    of those sentences quietly stop being true in a schema whose rules were argued elsewhere.

    Delete this and `CHECKPOINT_SCHEMA` can be moved to `obs`, which reads as the
    observability schema, is enumerated by the sweep, and passes every other test here."""
    assert CHECKPOINT_SCHEMA not in {"obs", "mem", "chat"}
    assert CHECKPOINT_SCHEMA == "agent"


def test_a_checkpointer_configured_into_a_schema_nobody_declared_is_refused() -> None:
    """`public` is the default the library would use and it is the one answer this repository
    has already ruled out: `brain.db` calls a table there one nobody decided the
    classification of. Delete this and the refusal becomes a comment."""
    with pytest.raises(CheckpointerError, match="row-level security"):
        CheckpointerConfig(url=DIRECT_URL, schema="public")


def test_the_search_path_names_the_schema_and_leaves_public_off_it() -> None:
    """A path of `agent,public` creates new tables in `agent` and finds existing ones in
    `public`, so an install that has already run once with the default keeps reading the
    tables nothing enumerates and the fix silently does nothing.

    Delete this and appending `public` looks like a safe compatibility measure, which is
    exactly the edit that makes the schema move a no-op."""
    conn = RecordingConnection()
    CheckpointerConfig(url=DIRECT_URL).configure(conn)  # type: ignore[arg-type]

    assert conn.executed == [(SEARCH_PATH_SQL, (CHECKPOINT_SCHEMA,))]
    assert "public" not in str(conn.executed)
    assert conn.committed


# --------------------------------------------------- the two unsafe settings
def test_a_checkpointer_that_prepares_statements_server_side_is_refused() -> None:
    """`brain.session` sets `prepare_threshold=None` on the application engine for this exact
    reason, and a checkpointer that quietly did not would be the same bug in a second place.
    Delete this and the field becomes documentation."""
    with pytest.raises(CheckpointerError, match="prepare"):
        CheckpointerConfig(url=DIRECT_URL, prepare_threshold=5)


def test_a_checkpointer_in_pipeline_mode_is_refused() -> None:
    """Separate from the prepare threshold on purpose: they are two assumptions about the
    backend staying the same and a single "safe mode" flag would let one be fixed while the
    other stayed wrong. Delete this and pipeline mode arrives as a performance improvement
    with no error to connect it to the resume that stops working."""
    with pytest.raises(CheckpointerError, match="pipeline"):
        CheckpointerConfig(url=DIRECT_URL, pipeline=True)


def test_a_checkpointer_with_no_connection_string_is_refused() -> None:
    """An empty string is a valid value for a string field, which is how `DATABASE_URL`
    unset once produced an application that skipped its migrations and reported healthy.
    Delete this and a saver with nowhere to save is constructible."""
    with pytest.raises(CheckpointerError, match="nowhere to save"):
        CheckpointerConfig(url="   ")


# --------------------------------------------------- what a resumed run may read back
def _a_reach(principal_id: str = "p_1") -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=(
            Grant(capability=Capability(value="read:ticket.status"), scope=Scope.unrestricted()),
        ),
        not_after=None,
    )


def test_a_reach_saved_under_a_declared_channel_is_refused() -> None:
    """**The resume property itself.** A resumed run must never keep reach its caller no longer
    has, and the only thing that guarantees it is that a checkpoint cannot hold one: the state
    has to be rebuilt through the gate, and the gate resolves the reach at that instant. An
    `EntitlementSet` is not a list, a dictionary or a long string, so the two older rules both
    admitted it under `node`, and a grant revoked while the run was suspended would have been
    read back out of the store intact.

    Delete this and the scalar rule can be dropped as redundant with the container rule, which
    it reads as, and the checkpoint becomes a stored permission decision again."""
    refusals = checkpoint_refusals({"node": _a_reach()})

    assert len(refusals) == 1
    assert "'node'" in refusals[0]
    assert "EntitlementSet" in refusals[0]


def test_a_scope_saved_under_a_declared_channel_is_refused() -> None:
    """A `Scope` is the other half of a permission decision and the likelier one to be saved,
    because it looks like a description of which records a run wants and `record_refs` is
    exactly that channel. Delete this and the rule can be narrowed to the entitlement type
    alone, which leaves the half that says which rows."""
    refusals = checkpoint_refusals({"record_refs": Scope.unrestricted()})

    assert len(refusals) == 1
    assert "'record_refs'" in refusals[0]


def test_bytes_under_a_declared_channel_are_refused_whatever_their_length() -> None:
    """The length bound applies to text only, so a payload handed over as bytes was admitted
    at any size. A reference is text. Delete this and `bytes` can be added to the scalar
    types as a harmless primitive, which is the route a serialised record takes into the
    store."""
    assert checkpoint_refusals({"question_id": b"q"}) != ()
    assert checkpoint_refusals({"question_id": b"x" * 500}) != ()


def test_every_scalar_a_reference_is_made_of_is_still_admitted() -> None:
    """The positive sibling of the three refusals above. A type rule tested only by what it
    refuses is satisfied by one that refuses everything, and that rule would leave a graph
    unable to save a step count, a node name, a flag or an empty channel while every refusal
    test stayed green.

    Delete this and any one of the scalar types can fall off the tuple, which is found by the
    first graph that saves `step`, in production."""
    assert (
        checkpoint_refusals(
            {
                "run_id": "r_1",
                "principal_id": "p_1",
                "node": "retrieve",
                "step": 3,
                "question_id": None,
                "pending_tool": True,
                "record_refs": 1.5,
            }
        )
        == ()
    )


# --------------------------------------------------- the framework's own channels
def test_the_reserved_channel_names_are_the_librarys_own() -> None:
    """Asserted against the library's constants rather than against this module's, so a release
    that renames one fails here. Delete this and a renamed channel falls through to the
    allowlist, which refuses it, and every graph stops saving with a message about a channel
    nobody declared."""
    from langgraph._internal._constants import INTERRUPT
    from langgraph.checkpoint.serde.types import ERROR, TASKS
    from langgraph.constants import START

    assert (START_CHANNEL, INTERRUPT_CHANNEL, ERROR_CHANNEL, TASKS_CHANNEL) == (
        START,
        INTERRUPT,
        ERROR,
        TASKS,
    )


def test_a_routing_marker_may_hold_nothing_and_only_nothing() -> None:
    """A real graph writes `branch:to:<node>` with no value on every edge. Delete this and the
    marker can become a place to put a value under a name the allowlist never sees."""
    assert checkpoint_refusals({f"{BRANCH_CHANNEL_PREFIX}fetch": None}) == ()
    assert checkpoint_refusals({f"{BRANCH_CHANNEL_PREFIX}fetch": "t_1"}) != ()


def test_the_runs_input_is_judged_as_the_channel_writes_it_holds() -> None:
    """The input is the one reserved channel that legitimately holds a mapping, so it is the one
    most worth hiding a payload in. Its references pass; a list inside it, a reserved name inside
    it, or an input that is not a mapping at all is refused.

    Delete this and `__start__` can carry the retrieved passages into the very first save."""
    assert checkpoint_refusals({START_CHANNEL: {"run_id": "r_1", "principal_id": "p_1"}}) == ()
    assert checkpoint_refusals({START_CHANNEL: {"record_refs": ["t_1", "t_2"]}}) != ()
    assert checkpoint_refusals({START_CHANNEL: {START_CHANNEL: {"run_id": "r_1"}}}) != ()
    assert checkpoint_refusals({START_CHANNEL: "r_1"}) != ()


def test_an_interrupt_may_ask_with_a_reference_and_nothing_else() -> None:
    """What a paused run asked with is saved, so it is held to the same rule as any value. The
    library writes interrupts as a tuple of objects carrying `value`.

    Delete this and `interrupt({"passages": [...]})` saves the passages under a reserved name."""
    from langgraph.types import Interrupt

    assert checkpoint_refusals({INTERRUPT_CHANNEL: (Interrupt(value="approve t_1"),)}) == ()
    assert checkpoint_refusals({INTERRUPT_CHANNEL: (Interrupt(value={"passages": ["a"]}),)}) != ()
    assert checkpoint_refusals({INTERRUPT_CHANNEL: (Interrupt(value="x" * 500),)}) != ()


def test_an_error_and_fanned_out_work_are_never_admitted() -> None:
    """An exception's message is whatever the failing code put in it, and a `Send` carries an
    argument of the author's choosing. Delete this and either can be admitted by name."""
    assert checkpoint_refusals({ERROR_CHANNEL: RuntimeError("record t_1")}) != ()
    assert checkpoint_refusals({TASKS_CHANNEL: "anything"}) != ()


def test_a_runs_owner_is_read_from_its_state_or_from_its_input() -> None:
    """The first save holds only the input, so the owner has to be read from there too, and a
    state naming nobody answers empty rather than raising.

    Delete this and the guarded saver cannot tell who owns the very first checkpoint of a run."""
    assert owner_of({"principal_id": "p_1"}) == "p_1"
    assert owner_of({START_CHANNEL: {"principal_id": "p_2"}}) == "p_2"
    assert owner_of({"principal_id": "p_1", START_CHANNEL: {"principal_id": "p_2"}}) == "p_1"
    assert owner_of({"run_id": "r_1"}) == ""
    assert owner_of({"principal_id": 7}) == ""


def test_a_safe_configuration_is_constructible_and_says_where_its_tables_go() -> None:
    """The positive sibling of the three refusals above. A guard tested only by what it
    refuses is satisfied by a constructor that refuses everything, and that constructor would
    make the checkpointer unconfigurable while every refusal test stayed green.

    Delete this and the defaults can drift to values nothing can be built with."""
    config = CheckpointerConfig(url=DIRECT_URL)

    assert config.schema == CHECKPOINT_SCHEMA
    assert config.prepare_threshold is None
    assert config.pipeline is False
    conn = RecordingConnection()
    config.configure(conn)  # type: ignore[arg-type]
    assert conn.executed == [(SEARCH_PATH_SQL, (CHECKPOINT_SCHEMA,))]
