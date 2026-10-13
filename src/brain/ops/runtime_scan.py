"""Reading the product's own source for a second place that gives a model tools.

M13.7.1 asks that every way work reaches an agent enters one runtime, and that something fails if
a second code path calls a model while holding tools. `brain.gate.runtime.AgentRuntime` is that
runtime. This module is the question "is there another?" written once, so the unit test that
guards it in the repository and the install check that asks it of the code actually deployed
read the same lists and cannot drift into two answers.

**What is read is the call, not the intent.** A model is asked through `.complete(`, so a module
containing that call is a place a model is asked. It is allowed only when it is the runtime or is
named below as a place that asks with no tools, and a module that asks while importing anything
that holds a tool catalogue, `invoke` or the runtime's protocol is a second loop whatever its
name. Rejected: a list of the modules that are allowed to import the runtime. A second loop does
not import the first; it is written beside it.

**The two allow-lists are named, and a name on one that no longer calls a model is a finding.**
A stale exception is a door left open for the next module that happens to take the name, so the
scan reports it rather than keeping it quiet.

Task ids: M13.7.1
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path
from typing import Final

#: The only module allowed to hand a model tools.
THE_RUNTIME: Final = "brain.gate.runtime"

#: Modules allowed to call a model at all, each for a reason that is not an agent run.
CALLS_A_MODEL_WITHOUT_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "brain.gate.model_lane",
        "brain.builder.coauthor",
        "brain.agent_coauthor_routes",
        "brain.skill_draft_routes",
        "brain.ops.model_probe_run",
        "brain.provider_routes",
        "brain.models.adapter",
    }
)

#: Modules whose `.complete(` is `brain.ops.connector_sync.ReadState.complete`, which asks whether
#: a read covered every entity and calls no model. Held to importing nothing that could reach one.
COMPLETE_THAT_IS_NOT_A_MODEL: Final[frozenset[str]] = frozenset(
    {"brain.ops.connector_sync", "brain.ops.connector_sync_run"}
)

#: Where a model is reached from: a module importing from one of these could call it.
MODEL_MODULES: Final[tuple[str, ...]] = (
    "brain.models",
    "brain.gate.model_lane",
    "brain.gate.runtime",
)

#: Names that mean a module holds a tool catalogue or the runtime's protocol.
TOOL_BEARING: Final[frozenset[str]] = frozenset(
    {"ProjectedCatalogue", "invoke", "project", "ToolProposal", "tools_block", "PROTOCOL"}
)

#: The fewest modules a read of the product's source can hold and still be the product's source.
#: Below it the scan is reading something else, and finding nothing there proves nothing.
AT_LEAST_THIS_MANY_MODULES: Final = 200


def parsed(root: Path) -> dict[str, ast.Module]:
    """Every module under `root` (the `brain` package), parsed, keyed by its dotted name."""
    found: dict[str, ast.Module] = {}
    for path in sorted(root.rglob("*.py")):
        module = ".".join(path.relative_to(root.parent).with_suffix("").parts)
        found[module] = ast.parse(path.read_text(encoding="utf-8"))
    return found


def calls_a_model(tree: ast.Module) -> bool:
    """Whether the module contains a `.complete(` call."""
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "complete"
        for node in ast.walk(tree)
    )


def imported_names(tree: ast.Module) -> set[str]:
    """Every name the module imports with `from ... import`."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
    return names


def imported_modules(tree: ast.Module) -> set[str]:
    """Every module the module imports from."""
    return {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}


def findings(trees: Mapping[str, ast.Module]) -> tuple[str, ...]:
    """What is wrong with where a model is called, as `<module>: <reason>`; empty when nothing.

    Reasons are fixed words and the module is the product's own dotted name, so a finding names
    code and never a person, a record or a value.
    """
    callers = {name for name, tree in trees.items() if calls_a_model(tree)}
    found: list[str] = []
    if THE_RUNTIME not in callers:
        found.append(f"{THE_RUNTIME}: the runtime itself calls no model, so the scan reads nothing")
    for name in sorted(COMPLETE_THAT_IS_NOT_A_MODEL):
        if name not in callers:
            found.append(f"{name}: an exception that no longer calls .complete(")
            continue
        if any(one.startswith(MODEL_MODULES) for one in imported_modules(trees[name])):
            found.append(f"{name}: reaches a model module though it asks no model")
        if imported_names(trees[name]) & TOOL_BEARING:
            found.append(f"{name}: holds a tool catalogue though it asks no model")
    unlisted = callers - CALLS_A_MODEL_WITHOUT_TOOLS - COMPLETE_THAT_IS_NOT_A_MODEL - {THE_RUNTIME}
    found.extend(f"{name}: a second place that calls a model" for name in sorted(unlisted))
    for name in sorted(callers - {THE_RUNTIME} - COMPLETE_THAT_IS_NOT_A_MODEL):
        if imported_names(trees[name]) & TOOL_BEARING:
            found.append(f"{name}: calls a model while holding a tool catalogue")
    return tuple(found)
