"""What a department's builder is offered to choose from: what their department holds (M13.9.2).

M13.9.2 asks that a department administrator create an agent for their own department in the same
flow as a Super Admin and be able to choose only the tools, connectors, skills and knowledge their
department holds. **The same flow is the same form**, so this does not build a second one: it cuts
the choices on the form that is already served, for the one reader the rule is about. A reader whose
install authority is held over everything is served the form as it is, which is what M13.9.1 asked
for, and a reader whose authority is held in a department is served the same form with the lists of
tools and connectors reduced to the ones their own reach admits.

**What "holds" means is the catalogue's answer and not a new one.** `brain.gate.catalogue.project`
is the one place that decides which tools an entitlement admits, so the choices are asked of it,
over every tool the registry has, rather than restated from capabilities here: a second opinion
about who may reach what is the one that is permissive on the day the two differ. A connector is
held when a tool of its source is. A connector with no tool this reach admits is one the department
has nothing to do with.

**This is what is offered, and not what is refused.** An authored list is intent and never
authorisation (M20.1.5): a name typed into the API that the form would not have offered still
cannot reach anything the author does not hold, because the ceiling a publish puts into the world is
derived on the server, and a publish reaching further than its author waits for a second person who
holds it. Refusing the name at save would change that decided behaviour for every builder and move
a question the owner decided, so this narrows the offer and leaves the gate alone. Whether a save
should refuse the name outright is a question for the owner and is on the Needs you page.

**An empty offer is a form that cannot name anything.** JSON Schema refuses an empty `enum`, so a
department holding no tool is served a list with no room in it (`maxItems: 0`), which says the same
thing in a form the library draws.

**Rejected: offering the choices to everybody.** A Super Admin who deliberately was not granted a
department's data would be unable to name that department's tools in a draft that a colleague who
does hold them then approves, which is the flow M20.1.5 exists for.

Skills and knowledge are not cut here. A skill's library is one company-wide object, and which
skills a department holds is decided by what each skill's tools need, which the library page shows;
and an agent's knowledge is not a section of the form at all (`brain.builder.form.SET_ELSEWHERE`),
it is set on the agent's own page behind that page's own reach. Both are named in the commit so
that nobody reads this module as having closed them.

Task ids: M13.9.2
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from brain.agents.creation import AGENT_INSTALL_CAPABILITY
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import SideEffect
from brain.core.scope import Scope
from brain.core.scope_sql import scope_narrows
from brain.gate.catalogue import AgentCeiling, project
from brain.tools.registry import ToolRegistry

#: The one sentence the console draws over a cut form.
THE_OFFER_IS_WHAT_YOUR_DEPARTMENT_HOLDS: Final = (
    "You can choose the tools and connectors your department holds. Anything else waits for "
    "somebody who holds it."
)

#: The manifest paths whose entries are tool names, and the one whose entries are connector names.
TOOL_PATHS: Final = ("authority.allowed_tools", "authority.required_tools")
CONNECTOR_PATH: Final = "connectors"


@dataclass(frozen=True)
class Choices:
    """The tools and connectors a reader's own reach admits, each sorted and without repeats."""

    tools: tuple[str, ...]
    connectors: tuple[str, ...]


def limited_to_a_department(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reader makes agents in a department and not over everything.

    False for a reader with no install authority at all, because the rule is about the person who
    has it in one place, and a person making their own agent is held to a rule of their own
    (`brain.agents.kinds.A_PERSON_MAKES_ONLY_THEIR_OWN_PERSONAL_AGENT`).
    """
    held = reach.scope_for(AGENT_INSTALL_CAPABILITY, now)
    return held is not None and not scope_narrows(Scope.unrestricted(), held)


def held_choices(registry: ToolRegistry, reach: EntitlementSet, now: datetime) -> Choices:
    """The tools this reach admits, and the sources they belong to."""
    everything = AgentCeiling(
        agent_id="builder_choices",
        allowed_tools=frozenset(registry.names()),
        max_side_effect=SideEffect.MONEY,
    )
    tools = tuple(sorted(project(registry, reach, everything, now=now).names))
    return Choices(
        tools=tools,
        connectors=tuple(sorted({registry.get(name).source for name in tools})),
    )


def _narrowed(fragment: Mapping[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    """A list-of-names field with its entries limited to `names`."""
    cut: dict[str, Any] = deepcopy(dict(fragment))
    entries: dict[str, Any] = dict(cut.get("items", {}))
    if names:
        entries["enum"] = list(names)
        cut["uniqueItems"] = True
    else:
        cut["maxItems"] = 0
    cut["items"] = entries
    return cut


def offered(document: Mapping[str, Any], choices: Choices) -> dict[str, Any]:
    """The form document with tools and connectors limited to these choices.

    A copy: `brain.builder.form.form_document` is the model's own description and is held equal to
    the console's fixture by a test, so the cut is made on what is served and never on it.
    """
    served: dict[str, Any] = deepcopy(dict(document))
    for section in served.get("sections", []):
        properties: dict[str, Any] = section.get("schema", {}).get("properties", {})
        authority: dict[str, Any] = properties.get("authority", {}).get("properties", {})
        for path in TOOL_PATHS:
            field = path.partition(".")[2]
            if field in authority:
                authority[field] = _narrowed(authority[field], choices.tools)
        if CONNECTOR_PATH in properties:
            properties[CONNECTOR_PATH] = _narrowed(properties[CONNECTOR_PATH], choices.connectors)
    return served
