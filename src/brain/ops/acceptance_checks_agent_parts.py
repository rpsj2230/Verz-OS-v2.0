"""The install acceptance check for what an agent is composed of: twelve parts.

The owner decided on needs item 180 (2026-10-12, option B) that tools and workflows are parts of an
agent in their own right, beside its persona, knowledge, connectors, skills, channels, availability,
leash, model policy, memory and automations. `brain.console.workspace.Part` is the list the
workspace is arranged by, and this asks it on the install, as the page's own route reads it.

**The twelve are written out here, in this check's own words, and not derived from the enum.**
Comparing the enum with itself would pass for any list, which is the constant-against-itself
mistake CLAUDE.md names. Each part must also say how it reaches an agent, which is what decides
whether an attachment for it is accepted: a tool and a workflow are pinned references, a persona
is a column and is refused as an attachment, so the page cannot be made to carry a second one.
And an agent installed on the install with a tool allowed is shown carrying that tool by the page's
own route, to the reader who may read its settings.

**Not proved here: a workflow.** Nothing stores a workflow yet (M17.4.2), so the part is listed
and its page section says there are none. That a stored workflow can be attached and followed is
that task's, and this check says only that the part exists and can be referred to.

Task ids: M39.1.1.1
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_agent_page import _app, _page, _tab_read
from brain.ops.acceptance_workspace import LOCAL_READ, LOCAL_TOOL, installed_agent

if TYPE_CHECKING:
    from brain.ops.acceptance_run import Harness

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1540

#: What an agent is composed of, as the work breakdown names it and in this check's own words.
TWELVE: Final = frozenset(
    {
        "persona",
        "knowledge",
        "connectors",
        "skills",
        "tools",
        "workflows",
        "channels",
        "availability",
        "leash",
        "model_policy",
        "memory",
        "automations",
    }
)

NOT_TWELVE: Final = "an agent is not composed of exactly the twelve named parts"
SUPPLY_MISSING: Final = "a part of an agent does not say how it reaches the agent"
A_TOOL_COULD_NOT_BE_PINNED: Final = "a tool could not be attached to an agent as a pinned part"
A_WORKFLOW_COULD_NOT_BE_PINNED: Final = "a workflow could not be attached to an agent as a part"
A_PERSONA_WAS_ATTACHED: Final = "a persona was accepted as an attachment, a second copy of one"
THE_TOOL_WAS_NOT_SHOWN: Final = "the agent's page did not show the tool it carries"
THE_WORKSPACE_DISAGREED: Final = "the workspace's own diagnostic found something wrong with it"


@check(
    leaves=("M39.1.1.1",),
    sentence=(
        "An agent is composed of twelve named parts, tools and workflows among them, each saying "
        "how it reaches the agent; a tool and a workflow can be attached as pinned references and "
        "a persona cannot; and an agent installed with a tool is shown carrying it on its page."
    ),
)
async def an_agent_is_composed_of_twelve_parts_with_tools_and_workflows(h: Harness) -> None:
    from brain.console.reads import Plane, plane_capability
    from brain.console.workspace import (
        SUPPLY,
        Attachment,
        Part,
        Supply,
        WorkspaceError,
        workspace_gaps,
    )

    if {one.value for one in Part} != TWELVE:
        raise CheckFailedError(NOT_TWELVE)
    if set(SUPPLY) != set(Part):
        raise CheckFailedError(SUPPLY_MISSING)
    if workspace_gaps():
        raise CheckFailedError(THE_WORKSPACE_DISAGREED)
    for part in (Part.TOOLS, Part.WORKFLOWS):
        if SUPPLY[part] is not Supply.PINNED:
            raise CheckFailedError(SUPPLY_MISSING)
    try:
        Attachment(part=Part.TOOLS, ref=LOCAL_TOOL, version="1")
    except WorkspaceError as refused:
        raise CheckFailedError(A_TOOL_COULD_NOT_BE_PINNED) from refused
    try:
        Attachment(part=Part.WORKFLOWS, ref="acceptance-workflow", version="1")
    except WorkspaceError as refused:
        raise CheckFailedError(A_WORKFLOW_COULD_NOT_BE_PINNED) from refused
    try:
        Attachment(part=Part.PERSONA, ref="another persona", version="1")
    except WorkspaceError:
        pass
    else:
        raise CheckFailedError(A_PERSONA_WAS_ATTACHED)

    await h.found_departments()
    steward = h.principal(A, "parts_steward")
    planes = tuple(plane_capability(one).value for one in Plane)
    await h.person(
        steward,
        department=A,
        grants=[
            (one, Scope.unrestricted()) for one in (_tab_read("settings"), LOCAL_READ, *planes)
        ],
    )
    agent_id = await installed_agent(
        h, steward, suffix="parts", capabilities=(LOCAL_READ,), allowed_tools=(LOCAL_TOOL,)
    )
    page: Any = await _page(h, _app(h), agent_id, steward)
    shown = {} if page.profile is None else {one.name for one in page.profile.tools}
    if LOCAL_TOOL not in shown:
        raise CheckFailedError(THE_TOOL_WAS_NOT_SHOWN)
