"""Install acceptance check for opening another department's document: each opening is on the ledger.

The owner's requirement (M27.15.1) is that opening the text of a document that sits in a department
the reader does not belong to is a read apart from seeing it listed, revocable, and written down
every time with the document and the reader named. The separate read is `read:knowledge` over the
department, which the People screen grants and withdraws; what this check proves is the half that
can be forgotten, the entry.

**It is the library's own passages route, called as the route is.** The check adds a document in
one reserved department, opens its text through `brain.knowledge_lifecycle_routes.version_text`
as a reader who belongs to the other department and holds the read over the first, and reads the
ledger for the entry the opening left. Rejected: writing the entry from the check, which would
prove the check's copy of the route and leave the route free to stop writing it.

**Three readers, and each is asked.** The reader across the line leaves exactly one entry naming
the reader as the actor and the document as the subject, and the entry says the kind of record and
nothing of the text. The document's steward, who belongs to its department, opens it and leaves
none, because a read inside the department is not the read the line is about. A person in the other
department holding no read over the first is answered as the document being absent and leaves none:
a refusal is not a disclosure. A check that asked only the first would pass for a route that wrote
an entry for every opening of every document, which is the log Option B describes and the one the
set of declared reads exists to prevent.

Task ids: M27.15.1
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2710

A, B = RESERVED_DEPARTMENTS


@check(
    leaves=("M27.15.1",),
    sentence=(
        "A person who belongs to one department and holds the read over another opens the text of "
        "a document there, and the ledger holds one entry naming the document and the reader and "
        "none of the text; the document's own steward opening it leaves none, and a person with no "
        "read over that department is told it is absent and leaves none."
    ),
)
async def opening_another_departments_document_leaves_an_entry(h: Harness) -> None:
    from fastapi import FastAPI
    from starlette.requests import Request

    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.knowledge_lifecycle_routes import version_text
    from brain.ops.acceptance_checks_lifecycle import _added
    from brain.ops.acceptance_operations_console import asking_as, refused, traced

    await h.found_departments()
    steward = h.principal(A, "steward")
    across = h.principal(B, "across")
    stranger = h.principal(B, "stranger")
    await h.person(
        steward, department=A, grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value)
    )
    await h.person(across, department=B, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(stranger, department=B, grants=_in(B, *KNOWLEDGE_READS))
    document = await _added(h, steward, h.word())

    serving = FastAPI()
    serving.state.settings = h.settings
    serving.state.db_sessions = h.sessions
    request = Request({"type": "http", "app": serving, "headers": [], "method": "GET"})

    async def entries() -> list[tuple[str, str]]:
        found = await h.execute(
            text(
                "SELECT actor_id, details::text FROM obs.audit_entry"
                " WHERE action = 'record_read' AND subject = :subject ORDER BY seq"
            ).bindparams(subject=f"entity:{document}")
        )
        return [(str(who), str(said)) for who, said in found.all()]

    async with traced(h, 1):
        opened = await version_text(request, await asking_as(h, across), document)
    if not opened.passages:
        raise CheckFailedError("a reader holding the read over the department was shown no text")
    written = await entries()
    if [who for who, _ in written] != [across]:
        raise CheckFailedError("an opening across departments did not leave exactly one entry")
    if any(one.text in said for one in opened.passages for _, said in written):
        raise CheckFailedError("the entry for an opening carried some of the text")

    async with traced(h, 2):
        inside = await version_text(request, await asking_as(h, steward), document)
    if not inside.passages:
        raise CheckFailedError("the document's own steward was shown no text")
    if len(await entries()) != 1:
        raise CheckFailedError("a reader inside the department left an entry for opening it")

    async with traced(h, 3):
        turned_away = await refused(version_text(request, await asking_as(h, stranger), document))
    if turned_away is not True:
        raise CheckFailedError("a person with no read over the department was shown the document")
    if len(await entries()) != 1:
        raise CheckFailedError("a refused opening left an entry")
