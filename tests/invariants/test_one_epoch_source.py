"""An answer key's source epochs have one source, the counter, and a second one fails the build.

`brain.gate.caches.ONE_EPOCH_SOURCE_KEYS_AN_ANSWER`. Until 2026-10-06 the repository held two
designs for the same number: `CachedFreshness` derived an epoch per source and entity from
`proj.record.last_seen_at`, and the answer route read `proj.source_epoch`'s counter. Nothing read
the first, which is why nothing broke, and nothing would have stopped somebody wiring it in beside
the second. These read the source rather than run it, because a second epoch source is a shape
in the code: another reader of epochs, an epoch computed from a timestamp, or the answer route
taking its epochs from somewhere other than the one function.

Task ids: M6.2.5
"""

from __future__ import annotations

import ast
from pathlib import Path

from brain.gate.caches import ONE_EPOCH_SOURCE_KEYS_AN_ANSWER

SRC = Path(__file__).resolve().parents[2] / "src" / "brain"


def _modules() -> list[tuple[str, ast.Module]]:
    return [
        (path.relative_to(SRC).as_posix(), ast.parse(path.read_text(encoding="utf-8")))
        for path in sorted(SRC.rglob("*.py"))
    ]


def epoch_readers(modules: list[tuple[str, ast.Module]]) -> set[str]:
    """Every class with an `epochs` method, which is the `SourceEpochs` shape, by module."""
    found: set[str] = set()
    for name, tree in modules:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                isinstance(item, ast.AsyncFunctionDef | ast.FunctionDef) and item.name == "epochs"
                for item in node.body
            ):
                found.add(f"{name}:{node.name}")
    return found


def epochs_from_a_timestamp(modules: list[tuple[str, ast.Module]]) -> set[str]:
    """Every `<something>.last_seen_at.timestamp()`, which is how an epoch is read off a time."""
    found: set[str] = set()
    for name, tree in modules:
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "timestamp"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "last_seen_at"
            ):
                found.add(f"{name}:{node.lineno}")
    return found


def test_the_counter_and_its_read_through_are_the_only_readers_of_epochs() -> None:
    """**ONE_EPOCH_SOURCE_KEYS_AN_ANSWER, by reader.** The protocol, the database's reader and the
    cache's read-through over it, and nothing else in the product has an `epochs` method. Delete
    this and a second reader can be added and installed on the application's state, and the
    answer key carries whichever one was installed last."""
    assert "from nowhere else" in ONE_EPOCH_SOURCE_KEYS_AN_ANSWER
    assert epoch_readers(_modules()) == {
        "ops/connector_sync_store.py:SourceEpochs",
        "ops/connector_sync_store.py:StoredSourceEpochs",
        "ops/connector_sync_store.py:ReadThroughSourceEpochs",
    }


def test_no_epoch_is_read_off_a_records_last_seen_at() -> None:
    """**ONE_EPOCH_SOURCE_KEYS_AN_ANSWER, by derivation.** The retired design's one line, an epoch
    from `last_seen_at.timestamp()`, appears nowhere. Delete this and it can come back, an epoch
    that moves on every confirming read and never on a deletion."""
    assert epochs_from_a_timestamp(_modules()) == set()


def test_the_checks_can_see_what_they_refuse() -> None:
    """The positive sibling: both scans find the shapes they look for when the shapes are there, so
    an empty answer above means absent and not unseen. Delete this and either scan can return
    nothing for every tree and both tests above stay green for ever."""
    planted = ast.parse(
        "class Second:\n"
        "    async def epochs(self):\n"
        "        return {r.source: int(r.last_seen_at.timestamp()) for r in rows}\n"
    )

    assert epoch_readers([("planted.py", planted)]) == {"planted.py:Second"}
    assert epochs_from_a_timestamp([("planted.py", planted)]) == {"planted.py:3"}


def test_the_answer_route_keys_on_the_one_reader_and_the_app_installs_the_read_through() -> None:
    """The answer route passes `await source_epochs_of(...)` to `caching_of` and nothing else, and
    the lifespan installs `ReadThroughSourceEpochs` over `StoredSourceEpochs`. Delete this and the
    route can take its epochs from anywhere, and the cache can be built and never installed."""
    routes = ast.parse((SRC / "api_routes.py").read_text(encoding="utf-8"))
    epochs_arguments = [
        ast.unparse(node.args[3])
        for node in ast.walk(routes)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "caching_of"
    ]
    assert epochs_arguments == ["await source_epochs_of(request.app.state)"]

    app = ast.parse((SRC / "app.py").read_text(encoding="utf-8"))
    installed = [
        ast.unparse(node.value)
        for node in ast.walk(app)
        if isinstance(node, ast.Assign)
        and any(ast.unparse(target) == "app.state.source_epochs" for target in node.targets)
    ]
    assert installed == [
        "ReadThroughSourceEpochs(StoredSourceEpochs(app.state.db_sessions), "
        "source_epochs_cache(answer_client))"
    ]
