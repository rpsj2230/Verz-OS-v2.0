"""The connectors reviewed on this install, made current where a declaration is about to be used.

`brain.ops.connector_catalogue` holds the approved definitions this process serves, and
`brain.ops.custom_connector_store.refresh` reads them. This module is where the web process asks for
that read, and the answer to "when" is the whole of it.

**Only on the paths that use a declaration, after their own refusal, never on every request.** The
first shape was a middleware that read the approved set before every API request. It kept a changed
definition out of every process at once, and it broke a property the rest of the product holds: a
refused caller must cause the same statements as a permitted one, and no read happens before the
refusal (`tests/unit/test_error_routes.py`, `test_tuning.py`, `test_agent_model_routes.py` measured
the extra statement). A screen that reads no connector has no reason to read the catalogue, and a
read before its refusal is a read a refused caller causes.

**So `current` is called where declarations are served from**: every Connectors route that reads a
source's declaration (after the connect authority or the screen's read is asked), the routes for
added APIs, the records route and the answer route before the registry, its row tools and its live
reads are looked at, and the worker at the start of each cycle
(`brain.ops.connector_sync_run.sync_on`, `brain.ops.connector_probe_run.probe_on`). Each of those is
asked by every caller alike, so it adds one statement to a refused caller and to a permitted one, or
none to either. See `A_DECLARATION_IS_MADE_CURRENT_WHERE_IT_IS_SERVED`.

**The property that survives: a definition changed after approval leaves every process before it is
served again.** Its change sets it back to unreviewed in the same statement, and every path that
serves a declaration reads the approved revisions immediately before it does, in whichever process
it runs, so the first use after the change is the use that drops it. The read is cheap: one
statement for the approved names and revisions, and a full row only for a revision this process has
not compiled (`brain.ops.custom_connector_store.approved_in`). What it does not cover, said plainly:
a screen that lists the registry's tools without using one (an agent's tool picker) may show a
changed definition's tool until the next serving path runs, and assigning it there reaches no data,
because every read goes through a path above.

Rejected: a timer, for the window it leaves, and a middleware, for the reason above.

Task ids: M11.7.8
"""

from __future__ import annotations

from typing import Any, Final

import structlog

from brain.ops.custom_connector_store import refresh
from brain.tools.registry import ToolRegistry

log = structlog.get_logger()

#: Why the catalogue is read where it is served and not on every request.
A_DECLARATION_IS_MADE_CURRENT_WHERE_IT_IS_SERVED: Final = (
    "The approved connector definitions are read immediately before a declaration is used: on "
    "the Connectors routes after their refusal, on the routes for added APIs, before the records "
    "and answer routes look at their tools, and at the start of each worker cycle. A route that "
    "uses no declaration reads nothing, so a refused caller is never the cause of a read the "
    "permitted one does not also cause, and a changed definition is dropped by the first use "
    "after its change, in whichever process makes it."
)


async def install_tools(state: Any, registry: ToolRegistry) -> None:
    """Put a built registry on the application, governed, recorded, and its passage search with it.

    Every call to a registered tool asks the switch table first, and each tool's catalogue row is
    written so a stop has a row to name. Never fatal: a catalogue row a switch needs is written by
    the switch itself. See `brain.tools.registry.ToolRegistry.govern`. The passage search the
    answer lane's model step reads through is the registered document tool's own handler, so the
    reach is decided where the tool decides it; None without a row source, which is a lane that
    abstains on a question no rule answers (`brain.api_routes.model_lane_of`).

    Called at start, and again whenever the connectors reviewed on this install change (M11.7.8),
    so a registry is only ever replaced whole: a request holding the old one finishes with it.
    """
    # Imported here: the routes that call `current` are imported by the module that owns these.
    from brain.api_routes import passage_search_for
    from brain.ops.tool_store import SessionSwitchSource, record_catalogue

    if state.db_sessions:
        registry.govern(SessionSwitchSource(state.db_sessions))
        try:
            await record_catalogue(state.db_sessions, registry)
        except Exception:
            log.exception("tool catalogue could not be recorded")
    state.tools = registry
    state.passage_search = passage_search_for(registry)


async def current(state: Any) -> bool:
    """Read the approved definitions and serve them, rebuilding the registry if they changed.

    True when the set changed. A process with no database reads nothing and changes nothing. See
    `A_DECLARATION_IS_MADE_CURRENT_WHERE_IT_IS_SERVED`.
    """
    sessions = getattr(state, "db_sessions", None)
    if not sessions:
        return False
    changed = await refresh(sessions)
    builder = getattr(state, "build_tools", None)
    if changed and callable(builder):
        await install_tools(state, builder())
    return changed
