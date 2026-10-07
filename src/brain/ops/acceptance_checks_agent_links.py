"""Install check for a link to one tab of one agent: where it lands for the person following it.

A console alert points at the exact place a person should look, and what the person follows has to
answer the same question the page asks: may this reader open this tab of this agent. The address of
every tab is `brain.console.workspace.deep_link` and where it lands is
`brain.agent_link_routes.agent_landing`, which asks the agent's audience and the tab strip the page
draws. The unit tests run the decision over a hand-made strip. What they cannot show is that, on an
install, with real grants and a real agent, a steward is taken to each tab the page offers them, a
colleague holding one tab is taken to that one, and every other link is answered with the
one sentence an agent that does not exist is answered with.

**The refusals are compared with one another, not with a constant.** A link to a tab the reader
holds nothing for, to a tab that does not exist, to an agent that does not exist and to something
that is not a link at all must read the same, because a route that said "forbidden" for one and
"not found" for another would turn the address bar into a question about which agents exist. The
check asks for all four and holds the four words equal.

**The tabs a steward is taken to are the ones the page populates**, read off the strip the same
route draws for them, so a tab nothing populates is not asked for and a tab this release adds is
asked for the day it is populated.

Task ids: M39.1.2.4
"""

from __future__ import annotations

from typing import Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_agent_console import _asking, _console, _request
from brain.ops.acceptance_run import Harness
from brain.ops.acceptance_workspace import installed_agent

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 845

A, B = RESERVED_DEPARTMENTS

A_STEWARD_WAS_NOT_TAKEN_THERE: Final = (
    "a steward following a link to a tab of their agent that the page offers them was not taken "
    "to that tab, at its address"
)
A_COLLEAGUE_WAS_TAKEN_TO_ONE_THEY_CANNOT_OPEN: Final = (
    "a reader following a link to a tab they hold no grant for was taken to it"
)
A_COLLEAGUE_WAS_NOT_TAKEN_TO_THEIRS: Final = (
    "a reader following a link to the one tab they hold was not taken to it"
)
THE_REFUSALS_DIFFER: Final = (
    "a link that cannot be followed was answered differently depending on why it cannot"
)


async def _landed(h: Harness, reader: str, link: str) -> tuple[str, str] | str:
    """Where the link lands for this reader, or the kind and words of the one refusal.

    The words a person is sent and the words the log keeps both, because each is one more place
    the reason could be told.
    """
    from brain.agent_link_routes import agent_landing
    from brain.core.errors import BrainError

    try:
        found = await agent_landing(_request(_console(h)), await _asking(h, reader), link)
    except BrainError as refused:
        return f"{type(refused).__name__}: {refused.public_message} / {refused}"
    return found.tab, found.address


@check(
    leaves=("M39.1.2.4",),
    sentence=(
        "A link to each tab of an agent lands, for its steward, on that tab at its address; for a "
        "colleague holding one tab it lands on that one and on no other; and a link to a tab they "
        "hold nothing for, to a tab that does not exist, to an agent that does not exist and to "
        "what is no link are answered in the same words."
    ),
)
async def a_link_to_an_agents_tab_lands_only_where_its_reader_may_open_it(h: Harness) -> None:
    from brain.agent_routes import agent_workspace
    from brain.console.reads import Plane, plane_capability
    from brain.console.workspace import Tab, deep_link, tab

    def read_of(one: Tab) -> str:
        return tab(one).read.requires.value

    await h.found_departments()
    steward, colleague = h.principal(A, "steward"), h.principal(A, "colleague")
    planes = tuple(plane_capability(one).value for one in Plane)
    everywhere = Scope.unrestricted()
    await h.person(
        steward,
        department=A,
        grants=tuple((one, everywhere) for one in (*(read_of(t) for t in Tab), *planes)),
    )
    await h.person(
        colleague,
        department=A,
        grants=tuple((one, everywhere) for one in (read_of(Tab.MEMORY), *planes)),
    )
    agent_id = await installed_agent(h, steward)

    strip = (await agent_workspace(_request(_console(h)), agent_id, await _asking(h, steward))).tabs
    populated = [Tab(one.tab) for one in strip]
    if not populated:
        raise CheckFailedError(A_STEWARD_WAS_NOT_TAKEN_THERE)
    for one in populated:
        link = deep_link(agent_id, one)
        if await _landed(h, steward, link) != (one.value, link):
            raise CheckFailedError(A_STEWARD_WAS_NOT_TAKEN_THERE)

    if await _landed(h, colleague, deep_link(agent_id, Tab.MEMORY)) != (
        Tab.MEMORY.value,
        deep_link(agent_id, Tab.MEMORY),
    ):
        raise CheckFailedError(A_COLLEAGUE_WAS_NOT_TAKEN_TO_THEIRS)
    refused = await _landed(h, colleague, deep_link(agent_id, Tab.SETTINGS))
    if not isinstance(refused, str):
        raise CheckFailedError(A_COLLEAGUE_WAS_TAKEN_TO_ONE_THEY_CANNOT_OPEN)

    words = {
        refused,
        await _landed(h, colleague, deep_link(agent_id, Tab.MEMORY).rsplit("/", 1)[0] + "/nowhere"),
        await _landed(h, colleague, deep_link(f"acceptance_{h.run}_nobody", Tab.MEMORY)),
        await _landed(h, colleague, "not a link at all"),
    }
    if len(words) != 1 or not all(isinstance(one, str) for one in words):
        raise CheckFailedError(THE_REFUSALS_DIFFER)
