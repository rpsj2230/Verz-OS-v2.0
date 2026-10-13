"""The install acceptance check that a change of embedding model moves the chunks, and moves nothing
else.

M7.3.5 is "re-embedding on model change with a rebuild command", and until `brain.knowledge.reembed`
nothing registered the task a rebuild is carried out by. The check runs the rebuild as the worker
does, on a document in each of the two reserved departments, over a model server the check made.

**Two documents, each embedded on one model and then rebuilt onto another.** Each is added in its
own reserved department by its own librarian and embedded under the revision the check names as the
old one, so every chunk carries that identity. The check then asks the product's own
`run_reembed_page` for the page after the key just below each document, as the worker's own
login (the page reads across every owner and the application role would see only what a person
reaches), under the revision it names as the new one. The page must find both documents' chunks and
queue one window each, for the owner of each, and **it must embed nothing itself**: the transport
the check made has not been asked yet. Each queued window is then run by the product's own
`run_embed_job` as that owner, and every chunk of both documents ends on the new identity with the
owner, department, visibility and state it started with.

**What the page found elsewhere on the install is left alone.** A real install holds real chunks
that are stale for a model the check made up, and the page finds them too; their windows are in the
queue the check holds and are never run, so nothing but the two documents the check wrote is
embedded. The page is asked to start after the key just below each document, so the check reads the
same key-ordered scan a resumed rebuild does and not a scan of everything.

**What the check does not show, and why its leaf is held.** The server is a transport the check
made, so what is proved is the product's page, its windows and its guards, and not that a real
model server embeds anything: M7.3.5 is held in `docs/proof-sweep-holds.json` and closes only when
a rebuild has run on an install whose model server answers (needs-rupash 120). The owner's M7.7.8
wording also says answers keep using the previous vectors while it runs, which the product decided
against (`brain.knowledge.embedding.A_MIXED_CORPUS_HAS_NO_VECTOR_LEG`); that narrowing is
needs-rupash 186, so this check does not name M7.7.8.

Task ids: M7.3.5
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Final

from sqlalchemy import select

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _upload
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1120

A, B = RESERVED_DEPARTMENTS

#: How many stale chunks the page reads at most: a real install holds real chunks that are stale for
#: a model the check made up, and the check reads the scan from just below its own document.
PAGE_OF_THE_CHECK: Final = 5_000

# ------------------------------------------------------------------ written-down reasons
#: What the made-up transport holds, and what it never does.
THE_TRANSPORT_IS_MADE_FOR_THE_CHECK: Final = (
    "The model server's transport is made in memory for this check and answers as the server's "
    "contract says. Nothing is sent to a socket, so a pass shows the product's page, windows and "
    "guards behave as written and shows nothing about a model server of the owner's."
)


@dataclass
class _Answer:
    status_code = 200
    body: object

    def json(self) -> object:
        return self.body


@dataclass
class _Server:
    """A transport that answers one unit-length vector per input under the model it was sent."""

    sent: list[Mapping[str, Any]] = field(default_factory=list)

    def post(self, url: str, *, json: Any, timeout: float) -> _Answer:
        self.sent.append(json)
        width = int(json["model"]["dimensions"])
        vectors = []
        for one in json["inputs"]:
            seed = int.from_bytes(hashlib.sha256(str(one["text"]).encode()).digest()[:8], "big")
            drawn = random.Random(seed)  # noqa: S311 - a direction for a made-up vector
            raw = [drawn.gauss(0.0, 1.0) for _ in range(width)]
            norm = sum(value * value for value in raw) ** 0.5
            vectors.append({"chunk_id": one["chunk_id"], "values": [value / norm for value in raw]})
        return _Answer({"model": json["model"], "vectors": vectors})


class _AsTheLogin:
    """Sessions that run one statement as the login the run connected as, inside the check's
    transaction, and put the application role back afterwards.

    The page reads across every owner, which the application role's policy would refuse, so the
    worker runs it on its own login. The check's transaction is already on the application role, so
    this steps out of it for the one read and back in, in a savepoint, as
    `brain.ops.acceptance_operations_console_2.as_login` does for the scheduler's run record.
    """

    def __init__(self, h: Harness) -> None:
        self._h = h
        self._nested: Any = None

    def __call__(self) -> _AsTheLogin:
        return self

    async def __aenter__(self) -> _AsTheLogin:
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        why: BaseException | None,
        where: TracebackType | None,
    ) -> None:
        return None

    def begin(self) -> _AsTheLogin:
        return self

    async def execute(self, statement: Any) -> Any:
        from sqlalchemy import text

        from brain.session import SET_APPLICATION_ROLE

        async with self._h.connection.begin_nested():
            await self._h.connection.execute(text("RESET ROLE"))
            result = await self._h.connection.execute(statement)
            rows = result.mappings().all()
            await self._h.connection.exec_driver_sql(SET_APPLICATION_ROLE)
        return _Rows(rows)


@dataclass
class _Rows:
    rows: Any

    def mappings(self) -> _Rows:
        return self

    def all(self) -> Any:
        return self.rows


@check(
    leaves=("M7.3.5",),
    sentence=(
        "A document in each reserved department, embedded on one model, is found by the rebuild's "
        "page under another as the worker's login; the page queues one window per owner and embeds "
        "nothing itself, each window run as its owner leaves every chunk on the new model with its "
        "owner, department, visibility and state unchanged."
    ),
)
async def a_model_change_moves_every_chunk_and_changes_no_permission(h: Harness) -> None:
    from brain.knowledge.chunk_store import reach_of, run_embed_job
    from brain.knowledge.embed_policy import served_embedding_model
    from brain.knowledge.embed_queue import EMBED_TASK, MODEL_ARGUMENT, OWNER_ARGUMENT
    from brain.knowledge.ingest import MediaType, ParseFailure
    from brain.knowledge.reembed import run_reembed_page
    from brain.knowledge.search import CHUNK, session_settings
    from brain.ops.acceptance_documents import a_markdown_document
    from brain.ops.inference_client import InferenceEmbeddingClient

    old_revision, new_revision = f"acceptance-{h.run}-old", f"acceptance-{h.run}-new"
    old, new = (
        served_embedding_model(revision=old_revision),
        served_embedding_model(revision=new_revision),
    )
    await h.found_departments()
    people: dict[str, str] = {}
    documents: dict[str, str] = {}
    for department in (A, B):
        person = h.principal(department, "library")
        await h.person(
            person,
            department=department,
            grants=_in(department, *KNOWLEDGE_READS, "admin:knowledge"),
        )
        read = await _upload(
            h,
            person,
            filename=f"Rebuild-{department[-1]}.md",
            declared=MediaType.MARKDOWN.value,
            body=a_markdown_document("Rebuild", f"{h.word()} {department}"),
            department=department,
        )
        if isinstance(read, ParseFailure):
            raise CheckFailedError("a well-formed document the door accepts could not be read")
        people[department], documents[department] = person, read.item.item_id

    server = _Server()
    client = InferenceEmbeddingClient(
        transport=server, url="http://inference.acceptance.invalid/embed"
    )

    async def read_back(department: str) -> list[tuple[Any, ...]]:
        async with h.sessions() as session:
            held = await reach_of(session, people[department], now=h.now)
            if held is None:
                raise CheckFailedError("the owner of a document reached none of it to read back")
            for setting in session_settings(held):
                await session.execute(setting)
            rows = (
                await session.execute(
                    select(
                        CHUNK.c.chunk_id,
                        CHUNK.c.ordinal,
                        CHUNK.c.embedding_model,
                        CHUNK.c.owner_id,
                        CHUNK.c.department,
                        CHUNK.c.visibility,
                        CHUNK.c.state,
                    )
                    .where(CHUNK.c.document_id == documents[department])
                    .order_by(CHUNK.c.ordinal)
                )
            ).all()
        return [tuple(one) for one in rows]

    # Embedded on the old model, as an upload with a worker would have left them.
    for department in (A, B):
        first = await read_back(department)
        if not first:
            raise CheckFailedError("a document that was added holds no chunk")
        await run_embed_job(
            document_id=documents[department],
            first_ordinal=int(first[0][1]),
            last_ordinal=int(first[-1][1]),
            model=old.identity,
            owner_id=people[department],
            sessions=h.sessions,
            service=client,
            revision=old_revision,
            now=h.now,
        )
    before = {department: await read_back(department) for department in (A, B)}
    if any(row[2] != old.identity for rows in before.values() for row in rows):
        raise CheckFailedError("a chunk was not left on the model that embedded it")
    sent_before = len(server.sent)

    # The worker's page, as its own login, after the key just below the first document.
    queued: list[Any] = []

    async def hold(job: Any) -> None:
        queued.append(job)

    for document in documents.values():
        await run_reembed_page(
            _AsTheLogin(h),  # type: ignore[arg-type]
            hold,
            after_chunk_id=document[:-1],
            size=PAGE_OF_THE_CHECK,
            model=new.identity,
            revision=new_revision,
        )
    if len(server.sent) != sent_before:
        raise CheckFailedError("the rebuild's page embedded a chunk itself")
    ours = {str(dict(one.args)["document_id"]): one for one in queued if one.task == EMBED_TASK}
    for department in (A, B):
        job = ours.get(documents[department])
        if job is None:
            raise CheckFailedError("the page did not find a stale document of a department")
        if dict(job.args)[OWNER_ARGUMENT] != people[department]:
            raise CheckFailedError("a window was queued for somebody other than the owner")
        if dict(job.args)[MODEL_ARGUMENT] != new.identity:
            raise CheckFailedError("a window was queued for another model than the one served")
        await run_embed_job(
            document_id=documents[department],
            first_ordinal=int(dict(job.args)["first_ordinal"]),
            last_ordinal=int(dict(job.args)["last_ordinal"]),
            model=str(dict(job.args)[MODEL_ARGUMENT]),
            owner_id=str(dict(job.args)[OWNER_ARGUMENT]),
            sessions=h.sessions,
            service=client,
            revision=new_revision,
            now=h.now,
        )

    for department in (A, B):
        after = await read_back(department)
        if len(after) != len(before[department]):
            raise CheckFailedError("a rebuild changed how many chunks a document holds")
        if any(row[2] != new.identity for row in after):
            raise CheckFailedError("a chunk was left on the old model after the rebuild")
        if [row[3:] for row in after] != [row[3:] for row in before[department]]:
            raise CheckFailedError("a rebuild changed a chunk's owner, department or level")
