"""The install acceptance check for what a department's builder is offered (M13.9.2).

`brain.agent_builder_routes.builder_form` serves the form an agent is written in, and for a builder
whose install authority is held in one department and not over everything it cuts the tools and
connectors to what that builder's own reach holds (`brain.builder.choices`). This reads that form as
two reserved builders of acceptance_a, through the route function the console calls, over the
install's own tool registry and the reach each person loads from the install's database: one who
holds the install authority over everything, and one who holds it in acceptance_a and reads the
knowledge library there and nothing else.

**What is held is read back from the grants, not from the module under test.** The cut list is
compared with the capability each registered tool requires and the grants the builder was given, so
the check does not ask `brain.builder.choices` whether it agrees with itself. It asserts the three
things the leaf names: the department's builder is offered the document search their department
holds, is offered no tool their department does not hold, and is told why the list is short; and the
builder over everything is served the form whole.

**Nothing about the install is assumed.** Both people and everything they were granted are the
check's, written inside its transaction and rolled back. The tools on the install are whatever it
has: the check says it was not run on an install whose registry holds no tool the department's
builder lacks, because there is then nothing a cut could be seen to leave out.

Task ids: M13.9.2
"""

from __future__ import annotations

import secrets
from typing import Any, Final

from brain.agents.creation import AGENT_INSTALL_CAPABILITY
from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_builder import KNOWLEDGE_READ, _body, _builder
from brain.ops.acceptance_checks_templates import _asking, _gallery, _request
from brain.ops.acceptance_run import Harness

A, _ = RESERVED_DEPARTMENTS

#: Where this module's check stands on the Install page, after the builder checks' own. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 411

#: The tool every install with a database registers that reads the knowledge library, the one
#: the department's builder is given the capability for.
DOCUMENT_SEARCH: Final = "knowledge.search_documents"

NOTHING_TO_LEAVE_OUT: Final = (
    "this install has no tool a department builder lacks, so there is nothing a cut could leave out"
)
NOT_TOLD_WHY: Final = "a department's builder was not told the tools offered are the ones held"
OFFERED_WHAT_IS_NOT_HELD: Final = "a department's builder was offered a tool their reach lacks"
NOT_OFFERED_WHAT_IS_HELD: Final = "a department's builder was not offered a tool their reach holds"
SUPER_ADMIN_CUT: Final = "a builder holding the install authority over everything was offered less"


def _offered(form: dict[str, Any], field: str) -> list[str] | None:
    """The tools the form lets one list name, or None when it names no limit."""
    for section in form.get("sections", []):
        authority = section.get("schema", {}).get("properties", {}).get("authority", {})
        found = authority.get("properties", {}).get(field)
        if found is not None:
            enum = found.get("items", {}).get("enum")
            if enum is not None:
                return [str(one) for one in enum]
            return [] if found.get("maxItems") == 0 else None
    return None


async def _wide_builder(h: Harness) -> str:
    """A reserved builder whose install authority is held over everything, with the gallery's reads.

    Not `_builder` plus a second grant: a person holds one grant of a capability, and the
    department one `_builder` always gives would be a duplicate of it.
    """
    from brain.agent_routes import TEMPLATE_SCREEN
    from brain.console.reads import plane_capability_for
    from brain.console.screens import screen

    read = screen(TEMPLATE_SCREEN).read
    wide = h.principal(A, "everywhere")
    await h.person(
        wide,
        department=A,
        grants=(
            (read.requires.value, Scope.unrestricted()),
            (plane_capability_for(read, read.plane).value, Scope.unrestricted()),
            (AGENT_INSTALL_CAPABILITY.value, Scope.unrestricted()),
        ),
    )
    return wide


@check(
    leaves=("M13.9.2",),
    sentence=(
        "A builder who makes agents in acceptance_a and reads its knowledge library is offered the "
        "document search and no tool their reach lacks, and told why; a builder who makes agents "
        "over everything is offered the form whole."
    ),
)
async def a_department_builder_is_offered_only_what_their_department_holds(h: Harness) -> None:
    from brain.agent_builder_routes import builder_form

    await h.found_departments()
    inside = await _builder(h, "dept", (KNOWLEDGE_READ, Scope.department(A)))
    over_everything = await _wide_builder(h)
    app = _gallery(h, secrets.token_hex(32))

    registry = app.state.tools
    reach = await h.reach(inside)
    lacked = [
        name
        for name in registry.names()
        if reach.scope_for(registry.get(name).capability, h.now) is None
    ]
    if not lacked or not registry.has(DOCUMENT_SEARCH):
        raise CheckNotRunError(NOTHING_TO_LEAVE_OUT)

    form = _body(await builder_form(_request(app), await _asking(h, inside)))
    offered = _offered(form, "allowed_tools")
    if not form.get("offer_note"):
        raise CheckFailedError(NOT_TOLD_WHY)
    if offered is None or set(offered) & set(lacked):
        raise CheckFailedError(OFFERED_WHAT_IS_NOT_HELD)
    if DOCUMENT_SEARCH not in offered:
        raise CheckFailedError(NOT_OFFERED_WHAT_IS_HELD)

    everything = _body(await builder_form(_request(app), await _asking(h, over_everything)))
    if everything.get("offer_note") or _offered(everything, "allowed_tools") is not None:
        raise CheckFailedError(SUPER_ADMIN_CUT)
