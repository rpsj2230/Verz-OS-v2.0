"""An erasure request deletes a person's session memory rather than leaving it to expire (M16.1.1).

The drain is run against PostgreSQL built as `tests/unit/test_erasure_store.py` builds it, with a
fake of the two Valkey commands the session eraser uses, so what is asserted is which keys the
real drain deletes after reading the real conversation ids.

Task ids: M16.1.1
"""

from __future__ import annotations

import psycopg
import pytest

from brain.memory.formation import session_key
from brain.ops.erasure_store import (
    AN_ERASED_PERSONS_SESSION_MEMORY_IS_DELETED_NOT_LEFT_TO_EXPIRE,
    EstateEraser,
    SessionMemoryEraser,
    drain_erasure_queue,
)
from brain.ops.retention import Store
from tests.fixtures.scratch_postgres import sql
from tests.unit.test_erasure_store import NOW, Recording, a_person, estate, file


class Keys:
    """`SessionKeys` over a set, keeping every name it was asked to delete."""

    def __init__(self, *held: str) -> None:
        self.held = set(held)
        self.deleted: list[str] = []

    def exists(self, *names: str) -> int:
        return sum(1 for one in names if one in self.held)

    def delete(self, *names: str) -> int:
        self.deleted.extend(names)
        gone = self.held & set(names)
        self.held -= gone
        return len(gone)


def test_the_memory_store_s_removal_deletes_exactly_the_keys_of_the_persons_conversations() -> None:
    """**The positive case and its edge.** Erasing the memory store deletes the key of each
    conversation id it was handed for this person, counts them as removed beside the rows, and
    touches no other key: not another person's on the same thread, not this person's on a thread
    it was not handed.

    Delete this and the eraser can delete nothing, or delete by a broader rule than the names it
    built, which on a shared cache is another person's notes."""
    mine, theirs, elsewhere = (
        session_key("t1", "p_ada"),
        session_key("t1", "p_ben"),
        session_key("t9", "p_ada"),
    )
    keys = Keys(mine, theirs, elsewhere)
    estate_eraser = EstateEraser(
        Recording(),  # type: ignore[arg-type]
        sessions=SessionMemoryEraser(keys, ("t1", "t2")),
    )

    # The recording eraser counts and removes one row; the key is one more.
    assert estate_eraser.count_for(Store.MEMORY, "p_ada") == 1 + 1
    removal = estate_eraser.erase(Store.MEMORY, "p_ada")

    assert removal.removed == 1 + 1
    assert keys.deleted == [mine, session_key("t2", "p_ada")]
    assert keys.held == {theirs, elsewhere}
    assert AN_ERASED_PERSONS_SESSION_MEMORY_IS_DELETED_NOT_LEFT_TO_EXPIRE


def test_no_other_store_reaches_session_memory_and_none_handed_deletes_nothing() -> None:
    """The keys go with the memory store and with no other, and an estate eraser handed no
    session eraser, which is a process with no cache, removes what the rows say and nothing more.

    Delete this and session memory could be deleted while erasing an unrelated store, or the
    count for the memory store could include keys nobody deleted."""
    keys = Keys(session_key("t1", "p_ada"))
    with_sessions = EstateEraser(
        Recording(),  # type: ignore[arg-type]
        sessions=SessionMemoryEraser(keys, ("t1",)),
    )
    with_sessions.erase(Store.CONVERSATION, "p_ada")
    assert keys.deleted == []

    without = EstateEraser(Recording())  # type: ignore[arg-type]
    assert (
        without.erase(Store.MEMORY, "p_ada").removed
        == Recording().erase(Store.MEMORY, "p_ada").removed
    )


@pytest.mark.needs_db
def test_the_queue_deletes_the_session_keys_of_every_conversation_the_person_had() -> None:
    """**End to end on this database.** The drain reads the person's conversation ids before the
    conversations are erased and deletes their session keys as part of the memory store, so the
    keys are gone the moment the request is carried out; another person's key is untouched.

    Delete this and the drain can erase the conversations first and then have no ids left to name
    the keys by, which leaves every erased person's notes in the cache until they expire."""
    with estate("brain_session_erasure") as url:
        a_person(url, "p_ada")
        a_person(url, "p_ben")
        [(ada,)] = sql(url, "SELECT id FROM chat.conversation WHERE principal_id = 'p_ada'")
        [(ben,)] = sql(url, "SELECT id FROM chat.conversation WHERE principal_id = 'p_ben'")
        hers, his = session_key(str(ada), "p_ada"), session_key(str(ben), "p_ben")
        keys = Keys(hers, his)
        file(url, "p_ada")

        with psycopg.connect(url) as conn:
            drain_erasure_queue(conn, now=NOW, sessions=keys)
            conn.commit()

        assert keys.deleted == [hers]
        assert keys.held == {his}
        [(stores,)] = sql(url, "SELECT stores FROM ops.erasure_request")
        memory = next(one for one in stores if one["store"] == "memory")
        assert memory["reached"] is True and memory["removed"] >= 1


def test_the_worker_hands_the_drain_a_session_client_from_its_own_cache_setting() -> None:
    """The worker's erasure run builds the session client from the cache its settings name and
    hands it to the drain, read from the call expressions rather than from text.

    Delete this and the drain's session eraser can be wired in tests and handed nothing on an
    install, which is every erased person's notes left to expire."""
    import ast
    import inspect

    from brain.ops import schedule_runner

    tree = ast.parse(inspect.getsource(schedule_runner.erasure_queue))
    calls = {
        getattr(node.func, "id", ""): {one.arg: ast.unparse(one.value) for one in node.keywords}
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert calls["drain_erasure_queue"]["sessions"] == "sessions"
    assigned = [
        ast.unparse(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "sessions"
    ]
    assert assigned == ["session_keys_for(valkey_url) if valkey_url else None"]
