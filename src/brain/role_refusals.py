"""The refusal that names the role a change needs, for a reader who can already open the page.

Needs-rupash 178 A: an agent's parts each have an editor, and **a refusal says which role would let
the person change it**. Before this, tools, connectors, the leash and the budget named a role, and
the model setting, the channels and the Connectors screen answered as if the thing did not exist,
so a person who could see the part learned nothing about whom to ask.

**The role is named only to somebody who can already open the page.** The role is not a secret: a
person who can open an agent's Settings, or the Connectors screen, knows the part exists, and
naming the role only tells them whom to ask. A caller who cannot open the page is still answered
by the one 404 the page gives everybody, so the sentence here never tells anybody a thing exists
that they could not see. `named_or_absent` is the whole of that decision: its caller says whether
the page was theirs to open, and it answers the sentence or hands back nothing.

**It never says whether the change would have been allowed.** The sentence is the same for every
agent and every source, whether or not one of that name exists, so naming the role discloses
nothing about what is there. See `A_REFUSAL_NAMES_ITS_ROLE_AND_NEVER_WHAT_IT_WOULD_HAVE_DONE`.

**Rejected: naming the capability string** (`admin:connector`). A console shows a role in words,
and a capability string is a vocabulary word the owner never asked a person to learn. The
connector sentence names the connector capability by its plain name, which is what M33.8.3 asks,
and the string stays in the ledger and the code.

Task ids: M39.8.1, M33.8.3
"""

from __future__ import annotations

from typing import Final

from fastapi.responses import JSONResponse

#: Why a refusal names a role, to whom, and what it leaves out.
A_REFUSAL_NAMES_ITS_ROLE_AND_NEVER_WHAT_IT_WOULD_HAVE_DONE: Final = (
    "A person who can open a page knows the part on it exists, so a refusal on that page says "
    "which role changes it and whom to ask. The sentence is the same whether or not the thing "
    "named exists and whether or not the change would have been allowed. A person who cannot "
    "open the page is answered by the page's one refusal and told nothing about a role."
)

#: The roles, in the words a person is told them in.
DEPARTMENT_ADMINISTRATOR: Final = "a department administrator for its department"
SUPER_ADMINISTRATOR: Final = "a Super Admin"

#: What each change is told it needs.
CHANGING_CHANNELS_NEEDS_THE_DEPARTMENT_ADMINISTRATOR: Final = (
    f"Changing where this agent answers needs {DEPARTMENT_ADMINISTRATOR}."
)
CHOOSING_A_MODEL_NEEDS_THE_SUPER_ADMIN: Final = (
    f"Choosing which model this agent uses needs {SUPER_ADMINISTRATOR}."
)
CONNECTING_A_SOURCE_NEEDS_THE_CONNECTOR_CAPABILITY: Final = (
    "Connecting, switching off or removing a source needs the connector capability for that "
    "source's department, which a department administrator is given for their own department "
    "and cannot give to anybody more widely than that."
)


def role_refusal(sentence: str) -> JSONResponse:
    """The 403 that carries one of the sentences above, in the body shape the console reads."""
    return JSONResponse(status_code=403, content={"message": sentence})
