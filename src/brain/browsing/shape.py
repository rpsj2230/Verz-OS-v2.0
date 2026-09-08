"""The structural half of "asserted by test", read out of the source rather than promised.

Two leaves in M19 ask for an absence: a planner that never reads page content, and a rubric
written before anybody has seen the trajectory. An absence cannot be demonstrated by a test
that exercises the code, because the code as written does the right thing and the failure
mode is the next version of it. So this module reads the package the way
`tests/invariants/test_single_implementation.py` reads the source for a second `intersect`:
by parsing it, and by failing when a shape appears rather than when a behaviour does.

**Three checks, and they answer three different versions of the same question.**

`forbidden_imports` asks whether the planner could name the type page content arrives in.
Everything page-derived is defined in `brain.browsing.observation`, and `planning` and
`targets` must not reach it, directly or through any module in the package. This is the
cheapest check and the easiest to satisfy accidentally, which is why it is not the only one.

`plan_inputs_are_declared` asks whether page content could arrive through a field. A planner
that imports nothing dangerous but takes a `PlanRequest` which has grown a `snapshot` field
reads the page through the front door. So the transitive field types of the named functions'
parameters are walked, and page-derived types and `Trajectory` are refused anywhere in that
closure. `Any` and `object` are refused there too, because a parameter typed as either is a
parameter this check cannot see into and would pass while carrying anything at all.

`nothing_turns_page_content_into_a_plan` asks the question about the module nobody has
written. It scans every function in the package for one that takes a page-derived type and
returns a plan, a step or a rubric. That is the shape of the edit somebody makes in good
faith six months from now, called `replan_from_snapshot` or `refine_rubric`, because the run
failed and the page had the answer on it. The first two checks are about the code as it
stands and this one is about the code that has not been added.

**Names, not types, and the limit is worth stating.** This walks identifiers in annotations.
It cannot see through an alias declared in another package, it cannot see into a `dict[str,
Any]`, and it would not notice page text passed as a bare `str`. The `Any` refusal closes the
widest of those holes for the functions that matter; the rest are why
`observation.PAGE_AUTHORED` names the fields that carry attacker text, so a reader knows what
is being kept out rather than trusting a parser to find every route.

**Every check takes a root and defaults to this package.** A check that can only be pointed
at code satisfying it is a check that passes for the same reason an empty scan does. Every
one of these is exercised in both directions: against this package, where it must find
nothing, and against a planted module that violates it, where it must find exactly that.

Task ids: M19.2.1, M19.5.1
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final

#: The module every page-derived value lives in. Named once, because the whole argument is
#: that it is one module and a second one would make the import check meaningless.
QUARANTINED: Final = "observation"

#: The modules that must not be able to reach it, and the reason each is on the list.
#:
#: `planning` is M19.2.1. `targets` is here because a surface map learned from a page would
#: be a planner reading page content with a database row in between, which is the argument
#: `brain.browsing.targets` makes about itself.
MUST_NOT_SEE_THE_PAGE: Final[tuple[str, ...]] = ("planning", "targets")

#: What must never be produced from page content. Listed rather than derived, because the
#: point is a decision about which outputs are dangerous: a `Score` legitimately comes from a
#: run, and a `Plan` legitimately does not.
PLAN_TYPES: Final[frozenset[str]] = frozenset({"Plan", "Step", "Rubric", "Criterion"})

#: Types a planner or a rubric builder must not reach through a parameter, beyond the
#: page-derived ones. `Trajectory` is what M19.5.1 is about: it is not page content, it is
#: the run's own history, and a rubric that can see it grades what happened.
AFTER_THE_FACT: Final[frozenset[str]] = frozenset({"Trajectory", "Claim", "ActionRecord"})

#: Annotations this check cannot see into, refused where it matters most.
OPAQUE_ANNOTATIONS: Final[frozenset[str]] = frozenset({"Any", "object"})

#: The functions whose parameters are walked, and what each one must not reach.
#:
#: A mapping rather than a list so the reason travels with the entry: `plan` and
#: `render_brief` are the planner seam, `build_rubric` is the verification seam, and the day
#: a fourth appears it needs a line here saying which it is.
GUARDED_SIGNATURES: Final[Mapping[str, str]] = {
    "plan": "the planner",
    "render_brief": "the text a planner model would be given",
    "build_rubric": "the rubric, which must be written before the trajectory exists",
}

#: Where the package is, when nobody says otherwise.
PACKAGE: Final = Path(__file__).resolve().parent


def _modules(root: Path) -> dict[str, ast.Module]:
    """Every module in a package directory, parsed, by module name.

    Read as bytes and decoded rather than through `read_text`, for the reason
    `.scratch/guard_audit.py` gives about the same choice: universal newline translation
    produces text that does not match what other tools see, and a check comparing against
    source has to be looking at the same bytes.
    """
    found: dict[str, ast.Module] = {}
    for path in sorted(root.glob("*.py")):
        found[path.stem] = ast.parse(path.read_bytes().decode("utf-8"))
    return found


def _named(node: ast.AST | None) -> frozenset[str]:
    """Every identifier mentioned in an annotation, including attribute tails.

    `brain.browsing.observation.Snapshot` contributes `Snapshot`, and so does a bare
    `Snapshot`, so an import style cannot change the answer.
    """
    if node is None:
        return frozenset()
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            found.add(child.id)
        elif isinstance(child, ast.Attribute):
            found.add(child.attr)
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            # A quoted forward reference. Parsed rather than skipped, because quoting is the
            # obvious way round a check that only reads bare names.
            try:
                found |= _named(ast.parse(child.value, mode="eval").body)
            except SyntaxError:
                found.add(child.value)
    return frozenset(found)


def page_types(root: Path = PACKAGE) -> frozenset[str]:
    """Every class defined in the quarantined module.

    Derived rather than listed, so a new page-derived type is covered by every check here the
    moment it is written, rather than when somebody remembers to add its name.
    """
    module = _modules(root).get(QUARANTINED)
    if module is None:
        return frozenset()
    return frozenset(node.name for node in ast.walk(module) if isinstance(node, ast.ClassDef))


def field_graph(root: Path = PACKAGE) -> dict[str, frozenset[str]]:
    """Class name to every identifier its annotated fields mention.

    Only `AnnAssign` targets, which is what a dataclass field and a Pydantic field both are.
    A plain assignment is an enum member or a class constant, and neither carries a type a
    value could arrive through.
    """
    graph: dict[str, set[str]] = {}
    for module in _modules(root).values():
        for node in ast.walk(module):
            if not isinstance(node, ast.ClassDef):
                continue
            edges = graph.setdefault(node.name, set())
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign):
                    edges |= _named(statement.annotation)
    return {name: frozenset(edges) for name, edges in graph.items()}


def reachable(start: Iterable[str], graph: Mapping[str, frozenset[str]]) -> frozenset[str]:
    """Every type name reachable from these, through annotated fields.

    Iterative rather than recursive, because a self-referential type is a perfectly ordinary
    thing to write and a recursive walk over one does not return.

    **Termination is by construction rather than by a guard**, and that is a deliberate
    rewrite. The obvious shape is a queue with an `if name in seen: continue` at the top, and
    mutating that condition away does not make a test fail: it makes the process hang, on a
    cycle, inside a mutation harness that is waiting for pytest. So the pending set only ever
    receives names not already seen, and there is no branch to break.
    """
    seen: set[str] = set()
    pending = set(start)
    while pending:
        name = pending.pop()
        seen.add(name)
        pending |= graph.get(name, frozenset()) - seen
    return frozenset(seen)


def import_closure(root: Path = PACKAGE) -> dict[str, frozenset[str]]:
    """Which modules in the package each module can reach, transitively.

    Only imports naming `brain.browsing` are followed. An import of anything else is not
    interesting here: the claim is about one module in this package, and a module outside it
    cannot define a type this package treats as page-derived.
    """
    modules = _modules(root)
    direct: dict[str, set[str]] = {name: set() for name in modules}
    for name, tree in modules.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("brain.browsing."):
                    direct[name].add(node.module.rsplit(".", 1)[1])
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("brain.browsing."):
                        direct[name].add(alias.name.rsplit(".", 1)[1])
    closure: dict[str, frozenset[str]] = {}
    for name in modules:
        # Set-based for the reason `reachable` gives: two modules in a package importing each
        # other is ordinary, and a queue with a seen-check at the top turns the mutation of
        # that check into a hang rather than a failure.
        seen: set[str] = set()
        pending = set(direct[name])
        while pending:
            reached = pending.pop()
            seen.add(reached)
            pending |= direct.get(reached, set()) - seen
        closure[name] = frozenset(seen)
    return closure


def forbidden_imports(root: Path = PACKAGE) -> tuple[str, ...]:
    """Modules that must not be able to name page content and can.

    Transitive, because an indirect route is the one that happens: nobody imports
    `observation` into `planning`, somebody imports a helper that imports it.
    """
    closure = import_closure(root)
    gaps: list[str] = []
    for name in MUST_NOT_SEE_THE_PAGE:
        if name not in closure:
            continue
        if QUARANTINED in closure[name]:
            gaps.append(
                f"{name} reaches brain.browsing.{QUARANTINED}, so it can name the types page "
                "content arrives in; the claim that it never reads a page is then a claim "
                "about what its author intended rather than about what it can do"
            )
    return tuple(gaps)


def plan_inputs_are_declared(root: Path = PACKAGE) -> tuple[str, ...]:
    """The guarded functions' parameters, walked through every field they reach.

    A function is checked wherever it is defined, so moving `plan` into another module in the
    package does not move it out of scope. A guarded name that exists nowhere is reported
    too: a check that silently passes because the function was renamed is a check that has
    stopped running.
    """
    pages = page_types(root)
    graph = field_graph(root)
    refused = pages | AFTER_THE_FACT | OPAQUE_ANNOTATIONS
    gaps: list[str] = []
    seen: set[str] = set()
    for module_name, tree in _modules(root).items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name not in GUARDED_SIGNATURES:
                continue
            seen.add(node.name)
            named: set[str] = set()
            for argument in [*node.args.args, *node.args.posonlyargs, *node.args.kwonlyargs]:
                named |= _named(argument.annotation)
            for bad in sorted(reachable(named, graph) & refused):
                gaps.append(
                    f"{module_name}.{node.name} is {GUARDED_SIGNATURES[node.name]} and its "
                    f"parameters reach {bad}, so what it is given can carry what it must not "
                    "see"
                )
            for bad in sorted(named & OPAQUE_ANNOTATIONS):
                gaps.append(
                    f"{module_name}.{node.name} takes a parameter annotated {bad}, which "
                    "this check cannot see into, so it would pass while carrying anything"
                )
    for missing in sorted(set(GUARDED_SIGNATURES) - seen):
        gaps.append(
            f"no function named {missing} exists in the package, so the check on "
            f"{GUARDED_SIGNATURES[missing]} is passing because it found nothing to look at"
        )
    return tuple(gaps)


def nothing_turns_page_content_into_a_plan(root: Path = PACKAGE) -> tuple[str, ...]:
    """No function anywhere takes page content and returns a plan, a step or a rubric.

    The check about the module nobody has written yet. Both halves are walked through the
    field graph, so a function taking a wrapper around a `Snapshot` and returning a wrapper
    around a `Plan` is caught as readily as the obvious one.
    """
    pages = page_types(root)
    graph = field_graph(root)
    gaps: list[str] = []
    for module_name, tree in _modules(root).items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            named: set[str] = set()
            for argument in [*node.args.args, *node.args.posonlyargs, *node.args.kwonlyargs]:
                named |= _named(argument.annotation)
            takes = reachable(named, graph) & pages
            gives = reachable(_named(node.returns), graph) & PLAN_TYPES
            if takes and gives:
                gaps.append(
                    f"{module_name}.{node.name} takes {', '.join(sorted(takes))} and returns "
                    f"{', '.join(sorted(gives))}; a function that turns what the page said "
                    "into what to do next is prompt injection with a plan on the end of it"
                )
    return tuple(gaps)


#: Field names that would hold a credential value rather than a reference to one.
SECRET_SHAPED: Final[tuple[str, ...]] = (
    "password",
    "secret",
    "token",
    "credential",
    "passphrase",
    "api_key",
)


def secrets_do_not_travel(root: Path = PACKAGE) -> tuple[str, ...]:
    """No type outside the credentials module has a field a credential value could sit in.

    M19.4.1 is about where a placeholder becomes a value, and the way that rule stops holding
    is not somebody moving the resolution: it is a `password` field appearing on a plan or an
    action because it was convenient once. Checked on the name, because the type would be
    `str` either way and a `str` field is invisible to every other check here.
    """
    gaps: list[str] = []
    for module_name, tree in _modules(root).items():
        if module_name == "credentials":
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for statement in node.body:
                if not isinstance(statement, ast.AnnAssign):
                    continue
                if not isinstance(statement.target, ast.Name):
                    continue
                lowered = statement.target.id.lower()
                # One finding per field. `api_key_token` matches twice and saying the same
                # thing about one field twice turns a report into a count.
                if any(shape in lowered for shape in SECRET_SHAPED):
                    gaps.append(
                        f"{module_name}.{node.name}.{statement.target.id} could hold a "
                        "credential value outside the one module that resolves one, and "
                        "a value on a plan is a value in the trace and the retry"
                    )
    return tuple(gaps)


def browsing_gaps(root: Path = PACKAGE) -> tuple[str, ...]:
    """Every structural finding about the package, in one call.

    Ordered so the import finding comes first: it is the coarsest and the one whose fix
    usually removes the others.
    """
    return (
        *forbidden_imports(root),
        *plan_inputs_are_declared(root),
        *nothing_turns_page_content_into_a_plan(root),
        *secrets_do_not_travel(root),
    )
