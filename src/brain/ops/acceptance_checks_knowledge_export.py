"""The install acceptance check for the knowledge inventory: what leaves is what the reader may see.

The check calls `brain.knowledge_export_routes.export_knowledge`, the function the Knowledge
screen's export presses, against the install's own schema through the harness's sessions as the
application role. What it proves is the sentence of M25.3.3 on the install: a document placed in
one department leaves in that department's reader's file with its level and department stated and
who that reaches in words, never leaves in another department's reader's file, carries no word of
what it says, and is recorded under its taker with the ledger entry the Exports log's trigger
writes.

**It does not assume the install holds no other document.** The install's own documents are in the
list of every reader whose reach admits them, and the file of any reader holds them. So the check
looks for its own document by its id, and for its own word, and says nothing about the rest.

**The refusal is asked beside the success.** A person holding no knowledge grant at all is refused
as an unknown route is, and nothing is recorded for them. A guard asked only for its refusal is
satisfied by a route that refuses everybody.

Task ids: M25.3.3
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _upload
from brain.ops.acceptance_operations_console import asking_as, console_for, refused, traced
from brain.ops.acceptance_people_console import ledger
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2140

A, B = RESERVED_DEPARTMENTS

#: The reference the check's exports carry. A token, as the table requires.
EXPORT_REFERENCE: Final = "ACCEPTANCE-CHECK"


@check(
    leaves=("M25.3.3",),
    sentence=(
        "A document uploaded into acceptance_a is in the knowledge inventory a member there takes, "
        "stated as a department document of acceptance_a with who it reaches and none of what it "
        "says, is not in the inventory a member of acceptance_b takes, and the inventory is "
        "recorded under its taker in the ledger; a person with no knowledge grant is refused."
    ),
)
async def the_inventory_holds_what_the_reader_may_see_and_no_text(h: Harness) -> None:
    from brain.knowledge.ingest import MediaType, ParseFailure
    from brain.knowledge_export_routes import COLUMNS, KnowledgeAsked, export_knowledge
    from brain.ops.export import ExportReason

    await h.found_departments()
    uploader, in_a, in_b, nobody = (
        h.principal(A, "library"),
        h.principal(A, "member"),
        h.principal(B, "member"),
        h.principal(A, "nobody"),
    )
    await h.person(in_a, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(in_b, department=B, grants=_in(B, *KNOWLEDGE_READS))
    await h.person(uploader, department=A, grants=_in(A, *KNOWLEDGE_READS, "admin:knowledge"))
    await h.person(nobody, department=A)

    word = h.word()
    read = await _upload(
        h,
        uploader,
        filename="Inventory.md",
        declared=MediaType.MARKDOWN.value,
        body=f"# Acceptance inventory\n\n{word}\n".encode(),
    )
    if isinstance(read, ParseFailure):
        raise CheckFailedError("a well-formed document the door accepts could not be read")
    item_id = read.item.item_id

    c = console_for(h)
    asking = KnowledgeAsked(
        reason=ExportReason.INTERNAL_INVESTIGATION, reason_reference=EXPORT_REFERENCE
    )

    async def taken(principal_id: str, n: int) -> dict[str, Any]:
        asked = await asking_as(h, principal_id)
        async with traced(h, n):
            answered = await export_knowledge(c.request("POST"), asking, asked)
        if answered.status_code != 200:
            raise CheckFailedError("a reader of knowledge could not take the inventory")
        body: dict[str, Any] = json.loads(bytes(answered.body))
        return body

    mine = await taken(in_a, 1)
    if next(csv.reader(io.StringIO(mine["document"])), []) != list(COLUMNS):
        raise CheckFailedError("the inventory did not begin with its header")
    rows = list(csv.DictReader(io.StringIO(mine["document"])))
    found = [one for one in rows if one["Document id"] == item_id]
    if len(found) != 1:
        raise CheckFailedError("a document in the reader's department was not in their inventory")
    stated = found[0]
    if (stated["Level"], stated["Department"], stated["Who may read it"]) != (
        "department",
        A,
        f"people in {A}",
    ):
        raise CheckFailedError("the inventory did not state the document's level and department")
    if word in mine["document"]:
        raise CheckFailedError("the inventory carried a word of what a document says")

    theirs = await taken(in_b, 2)
    if item_id in theirs["document"]:
        raise CheckFailedError("a reader in another department was given the document")

    recorded = [
        one
        for one in await ledger(h, in_a)
        if one[0] == "publish" and one[1].startswith("artifact:")
    ]
    if len(recorded) != 1:
        raise CheckFailedError("the inventory is not in the ledger under its taker")

    async with traced(h, 3):
        if not await refused(
            export_knowledge(c.request("POST"), asking, await asking_as(h, nobody))
        ):
            raise CheckFailedError("a person with no knowledge grant was given an inventory")
    if await ledger(h, nobody):
        raise CheckFailedError("a refused inventory left an entry under the person refused")
