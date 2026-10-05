"""Every connector this install can read, shipped or reviewed here, and the one function saying so.

`brain.connectors.declaration.shipped` is the connectors this release ships, found once per process
by walking a package. Since M11.7.8 an administrator can add a connector for a new API from the
console, by its specification and its field mapping, and it becomes available after a second person
reviews it, with no release. **So every reader of the declarations asks `declarations()`, which is
the shipped ones with the reviewed ones laid beneath them, and nothing keeps a second list.** The
lists that were read off `shipped()` once at import (`brain.ops.connectable.CONNECTABLE`,
`brain.ops.connector_sync.READINGS`, `brain.knowledge.connector_rows.CONNECTOR_ROW_ENTITIES` and
their siblings) are now `Derived` views: the same names and the same mapping interface, recomputed
from `declarations()` when the reviewed set changes, so no caller of any of them moved.

**A shipped name always wins.** The reviewed definitions are laid beneath the shipped ones, so a
definition named like a shipped connector could never replace it here; it is also refused at submit
(`brain.ops.custom_connector`), so the shadowed case is one that cannot be written.

**Re-read immediately before a declaration is served, never on a timer and never on every
request.** The reviewed set lives in `ops.custom_connector`, and a definition changed after
approval goes back to waiting, which has to take it off the screen, out of the registry and out of
the worker's plan in every process before it is used again. So every path that serves a declaration
reads the approved revisions first (`brain.reviewed_connectors.current` on the web side, `sync_on`
and `probe_on` in the worker), and the first use after a change is the use that drops it. A timer
would leave a window of whatever length somebody tuned; a read on every request was the first shape
and put a statement in front of every route's refusal, including routes that read no connector.
See `A_REVIEWED_CONNECTOR_IS_READ_BEFORE_IT_IS_SERVED`.

**What a check or a test lays over the catalogue is scoped to its own context.** `overlaid` sets a
context variable rather than the process's set, so an install acceptance check that approves a
definition inside its own transaction, which is rolled back, never offers it to a request being
served beside it.

Rejected: a registry the routes write into when a definition is approved. It would be right in the
process that served the approval and wrong in every other one, the worker included, until a restart,
which is the release the leaf exists to remove.

Scope: domain logic and a process-wide holder. Nothing here reads a table; `install` is handed what
`brain.ops.custom_connector_store.refresh` read.

Task ids: M11.7.8
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Iterator, Mapping
from contextvars import ContextVar
from types import MappingProxyType
from typing import Final, TypeVar

from brain.connectors.declaration import ConnectorDeclaration, shipped

K = TypeVar("K")
V = TypeVar("V")

# ------------------------------------------------------------------ written-down reasons
#: Why the reviewed set is read before a declaration is served rather than on a timer.
A_REVIEWED_CONNECTOR_IS_READ_BEFORE_IT_IS_SERVED: Final = (
    "A connector added from the console is offered, given tools and read only while its "
    "definition is approved, and a definition changed after approval waits for a second person "
    "again. So every path that serves a declaration reads the approved revisions first, after "
    "its own refusal, and the first use after a change drops it in whichever process makes it; "
    "a timer would leave a window, and a read on every request would put a statement in front of "
    "every refusal, including those of routes that read no connector."
)

#: Why a shipped connector's name cannot be taken by a reviewed one.
A_SHIPPED_NAME_ALWAYS_WINS: Final = (
    "A connector this release ships is reviewed in the repository and installed everywhere, and "
    "its name is its key slot, its cassettes and its screen. A definition added on one install "
    "is laid beneath the shipped ones, so it can never replace one, and a definition named like "
    "one is refused when it is submitted."
)

EMPTY: Final[Mapping[str, ConnectorDeclaration]] = MappingProxyType({})

_lock = threading.Lock()
#: The reviewed definitions this process serves, by name, and how many times the set changed.
_installed: Mapping[str, ConnectorDeclaration] = EMPTY
_generation = 0
#: What a check or a test laid over the catalogue for its own context, or None.
_scoped: ContextVar[tuple[int, Mapping[str, ConnectorDeclaration]] | None] = ContextVar(
    "connector_catalogue_scoped", default=None
)
_scoped_counter = 0


def reviewed() -> Mapping[str, ConnectorDeclaration]:
    """The reviewed definitions this context sees, by name: a check's own, or the process's."""
    scoped = _scoped.get()
    return _installed if scoped is None else scoped[1]


def generation() -> tuple[str, int]:
    """Which reviewed set this context sees, as a key a derived view can be cached by."""
    scoped = _scoped.get()
    return ("process", _generation) if scoped is None else ("scoped", scoped[0])


def declarations() -> Mapping[str, ConnectorDeclaration]:
    """Every connector this install can read: the shipped ones, and the reviewed ones beneath.

    The one function every reader of the declarations asks. See `A_SHIPPED_NAME_ALWAYS_WINS`.
    """
    extra = reviewed()
    built = shipped()
    if not extra:
        return built
    return MappingProxyType(dict(sorted({**extra, **built}.items())))


def install(found: Mapping[str, ConnectorDeclaration]) -> bool:
    """Make `found` the reviewed set this process serves. True when it changed anything.

    A name a shipped connector has is dropped rather than installed, for
    `A_SHIPPED_NAME_ALWAYS_WINS`'s reason, so the set held is exactly what `declarations` adds.
    """
    global _installed, _generation
    kept = {name: one for name, one in found.items() if name not in shipped()}
    with _lock:
        if dict(_installed) == kept:
            return False
        _installed = MappingProxyType(dict(sorted(kept.items())))
        _generation += 1
        return True


@contextlib.contextmanager
def overlaid(found: Mapping[str, ConnectorDeclaration]) -> Iterator[None]:
    """`found` as the reviewed set for this context only, for a check or a test, and then not."""
    global _scoped_counter
    with _lock:
        _scoped_counter += 1
        mark = _scoped_counter
    kept = {name: one for name, one in found.items() if name not in shipped()}
    token = _scoped.set((mark, MappingProxyType(dict(sorted(kept.items())))))
    try:
        yield
    finally:
        _scoped.reset(token)


class Derived(Mapping[K, V]):
    """A mapping read off `declarations()`, recomputed when the reviewed set changes.

    What the module-level lists that used to be read off `shipped()` once are now, so every caller
    keeps the name and the mapping interface it had. The computation is cached per reviewed set,
    and a context with a set of its own is computed for that set.
    """

    def __init__(
        self, compute: Callable[[Mapping[str, ConnectorDeclaration]], Mapping[K, V]]
    ) -> None:
        self._compute = compute
        self._cache: dict[tuple[str, int], Mapping[K, V]] = {}

    def _now(self) -> Mapping[K, V]:
        key = generation()
        found = self._cache.get(key)
        if found is None:
            found = MappingProxyType(dict(self._compute(declarations())))
            # One entry per set seen; a check's scoped set is not kept beyond the next one.
            self._cache = {key: found}
        return found

    def __getitem__(self, key: K) -> V:
        return self._now()[key]

    def __iter__(self) -> Iterator[K]:
        return iter(self._now())

    def __len__(self) -> int:
        return len(self._now())

    def __repr__(self) -> str:
        return f"Derived({dict(self._now())!r})"


#: Every declaration this install can read, as a mapping that is always current.
DECLARED: Final[Mapping[str, ConnectorDeclaration]] = Derived(lambda found: found)
