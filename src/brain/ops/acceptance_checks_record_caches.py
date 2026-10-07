"""Install checks for the retrieval cache and the embedding cache, in the install's own cache.

`brain.cache.retrieval_cache` and `embedding_cache` keep, in Valkey, a search's ranked references
with the asker's reach in the key (M6.2.3) and a vector under a digest of exactly the content and
the model it was made by (M6.2.4). Their unit tests run over a dictionary. What they cannot show is
that, on an install, over the real cache and the real document search, a search asked again is
served from the cache and a reader whose reach differs is not served what it holds for another, and
that a vector round-trips through the real store under a key that moves with the content and the
model and carries nothing of any caller.

**The cache is the install's and the keys are the check's own.** Every key the check writes is
named by the wrapper that wrote it and deleted by name when the check ends, whatever happened, which
is `brain.ops.acceptance.WHAT_THE_DATABASE_CANNOT_ROLL_BACK_IS_REMOVED_BY_NAME`; a word nothing
else holds is searched for, so no real question can find what the check stored. The check is not run
where the process was given no cache address.

**A hit is read from the cache's own health counters, not from a faster answer.** The retrieval
cache's `CacheHealth` counts hits and writes; a second identical search must add one hit and no
write, and a search by a reader with a different reach must add neither a hit nor an answer.

**The retrieval is re-read after a change.** The key carries the corpus epoch, which an upload
moves, so a cached ranking cannot outlive the chunks it names: a document added after the first
search is found by the same words asked again, as a miss.

**Not proved here: M6.2.5, the projection freshness cache.** What it keeps is a reading of
every source's counter for a short while, and the claim that a change is seen within that while is
a statement about time the check cannot make without waiting the while out.

Task ids: M6.2.3, M6.2.4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, cast

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.cache import ValkeyClient

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 850

A, B = RESERVED_DEPARTMENTS

NO_CACHE: Final = (
    "the worker running this check was not given the cache address the application uses, so "
    "there is no cache to ask"
)
NOT_FOUND: Final = "a search over the check's own document did not find it"
NOT_SERVED_FROM_THE_CACHE: Final = "a search asked again was not served from the cache"
SERVED_ACROSS_REACH: Final = "a reader of another reach was served a search kept for somebody else"
STALE_AFTER_A_CHANGE: Final = "a document added after a search was not found by the same words"
THE_KEY_DID_NOT_MOVE: Final = "an embedding's key did not move with its content and its model"
THE_KEY_SAID_ITS_CONTENT: Final = "an embedding's key carried its content or its model in the clear"
NOT_ROUND_TRIPPED: Final = "a vector kept in the cache was not read back as it was kept"


@dataclass
class _Kept[T]:
    """A record cache over the install's, keeping the name of every key it writes."""

    inner: Any
    keys: list[str] = field(default_factory=list)

    def get(self, key: str) -> T | None:
        found: T | None = self.inner.get(key)
        return found

    def set(self, key: str, value: T, ttl_seconds: int) -> None:
        self.keys.append(key)
        self.inner.set(key, value, ttl_seconds)


def _client(h: Harness, kept: list[_Kept[Any]]) -> ValkeyClient:
    """The install's cache, with every key the wrappers in `kept` wrote removed afterwards."""
    from brain.cache import make_client

    if not h.settings.valkey_url:
        raise CheckNotRunError(NO_CACHE)
    client = make_client(h.settings.valkey_url)

    def removed() -> None:
        names = [name for one in kept for name in one.keys]
        if names:
            cast(Any, client).delete(*names)

    h.removes(cast(Any, client).close)
    h.removes(removed)
    return client


@check(
    leaves=("M6.2.3",),
    sentence=(
        "In the install's own cache, a document search asked twice is served the second time from "
        "the cache with the same passages; a reader of another department asking the same words "
        "is served nothing of it; and a document added afterwards is found by the same words."
    ),
)
async def a_cached_retrieval_is_served_only_to_the_reach_it_was_ranked_for(h: Harness) -> None:
    from brain.cache import CacheHealth, retrieval_cache
    from brain.knowledge.document_tools import DocumentSearch, searcher
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_checks import _upload
    from brain.ops.acceptance_documents import a_markdown_document

    kept: list[_Kept[Any]] = []
    client = _client(h, kept)
    health = CacheHealth()
    cache: _Kept[Any] = _Kept(retrieval_cache(client, health=health))
    kept.append(cache)

    await h.found_departments()
    keeper, reader, other = h.principal(A, "keeper"), h.principal(A, "reader"), h.principal(B, "r")
    await h.person(keeper, department=A, grants=_in(A, "admin:knowledge", *KNOWLEDGE_READS))
    await h.person(reader, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(other, department=B, grants=_in(B, *KNOWLEDGE_READS))
    word = h.word()
    for filename in ("RetrievalOne.md",):
        await _upload(
            h,
            keeper,
            filename=filename,
            declared="text/markdown",
            body=a_markdown_document("Retrieval", f"{word} is how this is found."),
            department=A,
        )
    search = searcher(SessionRowSource(h.sessions), None, cache)
    question = DocumentSearch(question=word)

    async def ask(who: str) -> tuple[str, ...]:
        found = await search(question, entitlement=await h.reach(who), now=h.now)
        return tuple(sorted(str(one.id) for one in found.records))

    first = await ask(reader)
    if not first:
        raise CheckFailedError(NOT_FOUND)
    if (health.hits, health.writes) != (0, 1):
        raise CheckFailedError(NOT_SERVED_FROM_THE_CACHE)
    if await ask(reader) != first or (health.hits, health.writes) != (1, 1):
        raise CheckFailedError(NOT_SERVED_FROM_THE_CACHE)

    if await ask(other) or health.hits != 1:
        raise CheckFailedError(SERVED_ACROSS_REACH)

    await _upload(
        h,
        keeper,
        filename="RetrievalTwo.md",
        declared="text/markdown",
        body=a_markdown_document("Retrieval again", f"{word} is also here."),
        department=A,
    )
    if len(await ask(reader)) <= len(first) or health.hits != 1:
        raise CheckFailedError(STALE_AFTER_A_CHANGE)


@check(
    leaves=("M6.2.4",),
    sentence=(
        "In the install's own cache, a vector is kept under a key that is the same for the same "
        "content whoever holds it and different for other content or another model, and is read "
        "back as it was kept and by nobody holding a different key."
    ),
)
async def an_embedding_is_kept_under_its_content_and_model_alone(h: Harness) -> None:
    from brain.cache import embedding_cache
    from brain.gate.caches import CachedEmbedding, embedding_key

    kept: list[_Kept[Any]] = []
    client = _client(h, kept)
    cache: _Kept[Any] = _Kept(embedding_cache(client))
    kept.append(cache)
    content = f"Acceptance {h.word()} passage"
    model = f"acceptance-model-{h.word()}"

    key = embedding_key(content, model=model)
    if (
        key != embedding_key(content, model=model)
        or key == embedding_key(content + " ", model=model)
        or key == embedding_key(content, model=model + "x")
    ):
        raise CheckFailedError(THE_KEY_DID_NOT_MOVE)
    if content in key or model in key:
        raise CheckFailedError(THE_KEY_SAID_ITS_CONTENT)

    values = (0.25, -0.5, 0.125)
    cache.set(key, CachedEmbedding(key=key, model=model, values=values), 60)
    found = cache.get(key)
    if found is None or found.values != values or found.model != model:
        raise CheckFailedError(NOT_ROUND_TRIPPED)
    if cache.get(embedding_key(content, model=model + "x")) is not None:
        raise CheckFailedError(NOT_ROUND_TRIPPED)
