"""The plugin boundary: what may extend this platform, on what terms, and what may not.

Four modules, split along the line between what a point is and what a plugin at one may do.

- `points`: the register. Every extension point M29 names, which of CLAUDE.md's three answers
  it takes, the contract it is defined by, and where a plugin at it runs.
- `manifest`: what a plugin says about itself, and every shape of reach it is refused a way
  to say.
- `lifecycle`: install, enable, disable, upgrade, rollback, and the drain that makes an
  upgrade safe. Nothing arrives enabled, because there is no transition that would do it.
- `contract`: the two properties M29.2.6 asks for, checked before a plugin is given anything.

The dependency runs one way. `manifest` and `lifecycle` know nothing about the register;
`contract` reads all three and is the only module that decides whether a plugin may run. That
direction is why a manifest can never widen a point's terms: the terms are not in the file the
plugin wrote.

**This is not `brain.ext`, and the two are not competing.** `brain.ext` is where a loaded
extension's own code would sit, and its docstring is right that everything there is untrusted
by construction and that nothing this system depends on belongs in it. What is here is the
opposite kind of code: the rules a plugin is held to, which have to be tested in this
repository because they are the product. A rule living beside the thing it constrains is a
rule that ships with it.

**No interface is defined here.** Ten of the sixteen points name a contract that already
exists in the module that owns it, and rewriting them under this package would be ten second
implementations of contracts the repository already has. Six name no contract at all and are
recorded as undecided rather than invented. See
`points.A_PROTOCOL_NOTHING_IMPLEMENTS_MAKES_THE_REGISTER_COMPLETE_AND_WORSE`.

Nothing here opens a socket, reads a file, imports a plugin or runs one. Loading is a separate
problem with a separate risk, and everything in this package is a question that has to be
answered before loading is even a sensible thing to attempt.
"""

from __future__ import annotations

from brain.plugins.contract import (
    PluginContractError,
    PluginRun,
    assert_cannot_see_unredacted,
    plan_run,
    points_a_plugin_may_take,
    unmet,
    would_be_refused,
)
from brain.plugins.lifecycle import (
    PLUGIN_ADMIN,
    PLUGIN_NOT_AVAILABLE,
    TRANSITIONS,
    Drain,
    InFlight,
    Installed,
    LifecycleError,
    PluginState,
    administered,
    assert_transition,
    disable,
    enable,
    install,
    may_remove,
    rollback,
    state_of,
    still_running,
    upgrade,
    version_for,
)
from brain.plugins.manifest import (
    ConfigKey,
    ManifestError,
    PluginManifest,
    declared_reach_keys,
    manifest_from,
)
from brain.plugins.points import (
    BY_NAME,
    POINTS,
    Answer,
    Carries,
    Direction,
    ExtensionPoint,
    IsolationTier,
    PointError,
    contract_gaps,
    point_named,
    points_answering,
    undecided_points,
)

__all__ = [
    "BY_NAME",
    "PLUGIN_ADMIN",
    "PLUGIN_NOT_AVAILABLE",
    "POINTS",
    "TRANSITIONS",
    "Answer",
    "Carries",
    "ConfigKey",
    "Direction",
    "Drain",
    "ExtensionPoint",
    "InFlight",
    "Installed",
    "IsolationTier",
    "LifecycleError",
    "ManifestError",
    "PluginContractError",
    "PluginManifest",
    "PluginRun",
    "PluginState",
    "PointError",
    "administered",
    "assert_cannot_see_unredacted",
    "assert_transition",
    "contract_gaps",
    "declared_reach_keys",
    "disable",
    "enable",
    "install",
    "manifest_from",
    "may_remove",
    "plan_run",
    "point_named",
    "points_a_plugin_may_take",
    "points_answering",
    "rollback",
    "state_of",
    "still_running",
    "undecided_points",
    "unmet",
    "upgrade",
    "version_for",
    "would_be_refused",
]
