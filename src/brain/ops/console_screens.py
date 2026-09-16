"""Which console reads a person can actually open, and which are decisions nobody can reach.

There are about thirty modules under `src/brain/console` and every one of them decides what a
reader may see. There are six pages and a first-run wizard under `console/src`. Those two
numbers have never been compared by anything, and M27's leaves were closed by the modules, so
the tracker counted a screen the day its reader decision was written rather than the day
somebody could open it. **A read nobody can open is a screen nobody has**, and the tracker said
otherwise for as long as nothing asked.

**The correspondence is read out of the source at both ends, because a hand-written table is
the thing that goes stale.** A module says which screen it serves by binding itself to the
registry in a module-level constant: `SPEND_OF_OTHERS_SCREEN`, `SCOPES_SCREEN`, `SCREEN_KEY`,
`THE_SCREEN`. That idiom is already this package's own and `brain.console.govern` argues for it
by name. The route table says which screens exist in a browser: `console/src/App.tsx` exports
`routes`, and a route names a path and an element. A screen key is in the browser when a route
path or a route element names it. Nothing in either list is typed out here.

**A `screen("limits")` call inside a function is a borrow and not a declaration**, which is the
one distinction this module turns on. `brain.console.usage_view` asks for
`screen("agents").read.requires` to decide what a filter may offer; it does not serve the
Agents screen, and counting that as service would have marked it reachable on the strength of a
dropdown. Read generously, seven modules looked served and five of them were borrowing.
Declarations are module-level and deliberate; borrows are wherever a capability is needed.

**A page may also name the module directly, and two do.** `console/src/pages/Agent.tsx` cites
`brain.console.workspace` and `console/src/pages/approvalsQuery.ts` cites
`brain.console.approvals`. That citation is the only way a page declares which read it serves,
so it counts, and it is why `approvals.py` is not on the list below despite declaring no key of
its own: the page reached for the module rather than for the registry.

**A finding here is certain and a pass is only probable**, and the check is written in that
direction on purpose. Everything it admits is something the console source actually names; it
does not follow the chain from a page through `/api/v1` to the module that answers, so a module
named only by an HTTP route module and never by the console can pass. What cannot happen is the
other error: a module no route and no page names anywhere is a module nobody can open, and that
is what gets printed. See `A_FINDING_IS_CERTAIN_AND_AN_ABSENCE_OF_ONE_IS_ONLY_PROBABLE`.

**This reports and does not fail, and the exemption list is the half that is a gate.** Measured
on 2026-09-16: twenty-nine console reads, four of them opened by a page, one exempted below and
twenty-four with nothing in a browser that reaches them. A check that lands red at twenty-four
of twenty-nine is a check somebody switches off, and this repository has written down twice what
happens to a check that is red the day it lands: `sweep_house_style` was scoped to what was
already clean and `sweep_traceability` calls its own advisory notes a backlog that predates the
check. So the count is printed on every run of `brain.ops.sweeps traceability`, which is the
sweep the pre-push hook runs against the commit and CI runs against the branch, and it goes to
zero by screens being built. What is refused outright is an exemption that has gone stale or
names nothing, because an exemption is the only way a module leaves this list without a screen
being built for it, and a list that can be extended quietly is a backlog with a lid on it.

Scope: reads files and parses them. Nothing here opens a connection, reads a clock or renders
anything, and every root is a parameter with a default so a test can point it at a tree of its
own rather than at this repository.

Task ids: M27.7.1
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from brain.console.screens import SCREENS

REPO: Final[Path] = Path(__file__).resolve().parents[3]
#: Where the reader decisions live. One module per surface, none of which renders anything.
CONSOLE_READS: Final[Path] = REPO / "src" / "brain" / "console"
#: The browser console's own source, which is TypeScript and outside `src`.
CONSOLE_SOURCE: Final[Path] = REPO / "console" / "src"

#: Why the count is printed rather than being a number nobody sees.
A_READ_NOBODY_CAN_OPEN_IS_A_SCREEN_NOBODY_HAS: Final = (
    "A console module decides what a reader may see and renders nothing, so it is finished "
    "from the tracker's point of view and invisible from a browser's. M27's leaves were "
    "closed by those modules, which made the tracker count screens nobody could open. The "
    "two lists are compared now, and the modules with no screen are named on every run, "
    "because a number that is not printed is a gap nobody is reminded of."
)

#: Why a module-level constant is a declaration and a call inside a function is not.
A_CAPABILITY_BORROWED_FOR_A_FILTER_IS_NOT_A_SCREEN_BEING_SERVED: Final = (
    "brain.console.usage_view asks for screen('agents').read.requires to decide what a "
    "dropdown may offer. It does not serve the Agents screen. Counting every screen key a "
    "module mentions marked five modules reachable on the strength of a borrowed capability, "
    "which is this check failing in the direction that reads as good news. A module declares "
    "the screen it serves in a module-level constant, which is the idiom this package "
    "already uses and argues for, and it borrows a capability wherever it needs one."
)

#: Why a pass here is weaker than a finding.
A_FINDING_IS_CERTAIN_AND_AN_ABSENCE_OF_ONE_IS_ONLY_PROBABLE: Final = (
    "This reads the console's own source and asks whether anything in it names the module or "
    "a screen key the module declares. It does not follow a page through /api/v1 to the "
    "module that answers the request, so a module reached only that way passes without a "
    "page naming it. That is the error this check is willing to make. The one it is not "
    "willing to make is the reverse: a module nothing in the console names anywhere cannot "
    "be opened by anybody, whatever else is true, so every line it prints is a real gap."
)

#: Why the backlog is a note and the exemption list is a gate.
AN_EXEMPTION_IS_THE_ONLY_WAY_THIS_COUNT_FALLS_WITHOUT_A_SCREEN_BEING_BUILT: Final = (
    "The count is advisory because it would be red on arrival, and this repository has twice "
    "recorded what happens to a check that lands red: it gets switched off. The exemption "
    "list is not advisory, because it is the one way a module can leave the list without "
    "anybody building a screen. An exemption naming a module that does not exist, or one "
    "that has since been given a screen, is therefore a finding rather than a note: it is "
    "the number going down for a reason nobody would accept if they were told about it."
)

#: The modules under `console/` that are not reads, and why each is excluded.
#:
#: `reads` is the vocabulary a console read is written in and `screens` is the registry of what
#: a screen is; neither decides what any particular reader may see, and both would otherwise be
#: reported for ever with no screen that could be built for them.
NOT_A_READ: Final[frozenset[str]] = frozenset({"__init__", "reads", "screens"})

#: The names a module declares its screen under. The suffix is the common form; the two whole
#: names are the ones already in use for a module that serves exactly one screen.
SCREEN_DECLARATION_SUFFIX: Final = "_SCREEN"
SCREEN_DECLARATION_NAMES: Final[frozenset[str]] = frozenset({"SCREEN_KEY", "THE_SCREEN"})

#: The route table, as `console/src/App.tsx` writes it. Parsed rather than imported, because
#: this is Python reading TypeScript and there is no third option that does not involve
#: running a bundler inside a sweep.
_ROUTE_PATH_RE: Final = re.compile(r'path:\s*"([^"]*)"')
_ROUTE_ELEMENT_RE: Final = re.compile(r"element:\s*[(\s]*<([A-Za-z][A-Za-z0-9_]*)")
#: How a page names the read it serves, which is the only way one declares it today.
_CITED_MODULE_RE: Final = re.compile(r"brain\.console\.([a-z_][a-z0-9_]*)")
#: What is read under `console/src`. The generated API schema is excluded nowhere, because a
#: module named in it is named by the console either way.
CONSOLE_SUFFIXES: Final[frozenset[str]] = frozenset({".ts", ".tsx"})


def screen_keys() -> frozenset[str]:
    """Every key the registry holds, which is what a declaration is matched against.

    Read from `SCREENS` rather than listed, so a screen added to the registry is one this
    check knows about without anybody editing this file.
    """
    return frozenset(one.key for one in SCREENS)


@dataclass(frozen=True)
class NoScreen:
    """One console read that genuinely has no screen, and the argument for it.

    Three fields and none of them optional, which is `brain.console.screens.Disclosure`'s
    construction and for the same reason: a flag can be set while tidying and a sentence
    naming the surface that consumes the module instead cannot.

    `consumed_by` is the load-bearing one. It names the module or the surface that reads this
    one, so a reviewer can open that and disagree. An exemption arguing only that a screen is
    not needed is one nobody can check.
    """

    module: str
    #: The surface that consumes this read instead, named so a reviewer can go and read it.
    consumed_by: str
    #: Why that is the right place for it, rather than a screen of its own.
    reason: str

    def __post_init__(self) -> None:
        if not self.module:
            msg = "an exemption naming no module excuses every module and none"
            raise ValueError(msg)
        for name, value in (("consumed_by", self.consumed_by), ("reason", self.reason)):
            if len(value.split()) < 8:
                msg = (
                    f"{self.module} is exempted from having a screen with a {name} of "
                    f"{value!r}, which is a flag with a longer name. "
                    f"{AN_EXEMPTION_IS_THE_ONLY_WAY_THIS_COUNT_FALLS_WITHOUT_A_SCREEN_BEING_BUILT}"
                )
                raise ValueError(msg)


#: Every console read that has no browser screen and should not have one.
#:
#: One entry. It is deliberately hard to add to: `tests/unit/test_console_screens.py` holds
#: this tuple exactly, so growing it is an edit somebody has to make to a test as well, in
#: front of a reviewer, with the argument written out here beside the module's name.
NO_SCREEN_NEEDED: Final[tuple[NoScreen, ...]] = (
    NoScreen(
        module="read_replica",
        consumed_by=(
            "brain.routing_routes, which puts brain.console.read_replica.StalenessBanner on a "
            "response that was answered from the replica, and brain.ops.replica_store, which "
            "measures the lag the decision is made against. Neither is a screen: the banner is "
            "a line on top of whichever screen the reader had already opened."
        ),
        reason=(
            "This module decides which copy of the database answers a console read and what "
            "the page must say when that copy is behind. It declares no screen key because "
            "there is no screen it is about, and a screen of its own would be a page showing "
            "replication lag to an administrator who came to read something else. The fact it "
            "produces belongs on the screen the reader is already looking at."
        ),
    ),
)


@dataclass(frozen=True)
class Unopenable:
    """One console read with no browser screen, and which of the two ways it has none.

    The two are worth telling apart and the line says which. A module that declares a screen
    key nothing routes is waiting for a page to be written; a module that declares no key at
    all is not wired to the registry either, so there is nothing for a page to be written
    against and the work is larger than it looks.
    """

    module: str
    #: The registry keys this module binds itself to, in the order the registry holds them.
    declares: tuple[str, ...]

    def line(self) -> str:
        """The sentence printed on every run. Names the module and what is missing."""
        if self.declares:
            return (
                f"brain.console.{self.module} declares {', '.join(self.declares)} and no "
                "route in console/src/App.tsx serves any of them"
            )
        return (
            f"brain.console.{self.module} declares no screen key, so no route could reach it "
            "and nothing in console/src names it"
        )


def console_reads(root: Path = CONSOLE_READS) -> tuple[str, ...]:
    """Every module under `console/` that decides what a reader may see, in name order.

    Everything except `NOT_A_READ`. A positive list of read modules would be a second registry
    to keep in step with the directory, and the failure of one is a module added and never
    checked, which is exactly the shape this whole check exists to catch.
    """
    return tuple(sorted(path.stem for path in root.glob("*.py") if path.stem not in NOT_A_READ))


def screens_declared(source: str, keys: Iterable[str] | None = None) -> tuple[str, ...]:
    """The registry keys one module's source declares, in the registry's own order.

    A module-level assignment to a name ending in `_SCREEN`, or to one of
    `SCREEN_DECLARATION_NAMES`, whose value is a string, a mapping of them or a sequence of
    them. See `A_CAPABILITY_BORROWED_FOR_A_FILTER_IS_NOT_A_SCREEN_BEING_SERVED` for what is
    deliberately not read: a `screen("x")` call anywhere inside a function.

    Registry order rather than alphabetical, so a reader comparing this against a menu is
    comparing two lists in one order.
    """
    known = frozenset(keys) if keys is not None else screen_keys()
    found: set[str] = set()
    for node in ast.parse(source).body:
        names = _assigned_names(node)
        if not any(
            name.endswith(SCREEN_DECLARATION_SUFFIX) or name in SCREEN_DECLARATION_NAMES
            for name in names
        ):
            continue
        value = getattr(node, "value", None)
        if value is None:
            continue
        found.update(one for one in _string_literals(value) if one in known)
    return tuple(one.key for one in SCREENS if one.key in found)


def _assigned_names(node: ast.stmt) -> tuple[str, ...]:
    """The names one module-level statement binds, which is empty for anything else."""
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return (node.target.id,)
    if isinstance(node, ast.Assign):
        return tuple(one.id for one in node.targets if isinstance(one, ast.Name))
    return ()


def _string_literals(node: ast.expr) -> tuple[str, ...]:
    """Every string a declaration's value holds, through the wrappers this package uses.

    `MappingProxyType({...})` and `frozenset({...})` are both in use for a declaration that
    names several screens, so a call's arguments are read as well as a bare literal. Keys of a
    mapping are deliberately not read: `brain.console.global_surfaces.ESTATE_SCREEN` is keyed
    by the kind of thing and valued by the screen, and reading both halves would admit a key
    that happened to spell a screen name.
    """
    if isinstance(node, ast.Constant):
        return (node.value,) if isinstance(node.value, str) else ()
    found: list[str] = []
    if isinstance(node, ast.Dict):
        for value in node.values:
            found.extend(_string_literals(value))
    elif isinstance(node, ast.Tuple | ast.List | ast.Set):
        for element in node.elts:
            found.extend(_string_literals(element))
    elif isinstance(node, ast.Call):
        for argument in node.args:
            found.extend(_string_literals(argument))
    return tuple(found)


def routed_screen_keys(route_table: str, keys: Iterable[str] | None = None) -> frozenset[str]:
    """The screen keys the browser's route table reaches, read out of `App.tsx`.

    Two ways a route names a screen and both are needed. Most routes name it in the path, and
    the overview names it in the element: it is the index route, so it has no path at all, and
    `<Overview />` is the only thing about that route that says what it shows.

    The first segment of the path rather than the whole path, because `agents/:agentId` is the
    Agents screen with one agent open and not a screen of its own.
    """
    known = frozenset(keys) if keys is not None else screen_keys()
    found = {one.strip("/").split("/")[0] for one in _ROUTE_PATH_RE.findall(route_table)}
    found.update(one.lower() for one in _ROUTE_ELEMENT_RE.findall(route_table))
    return frozenset(found & known)


def modules_named_by_the_console(root: Path = CONSOLE_SOURCE) -> frozenset[str]:
    """Every `brain.console.<module>` the browser console's own source names.

    This is how a page declares which read it serves, and there is no other way today. Read
    across the whole tree rather than only `pages/`, because a page's query module is where the
    citation usually sits and a component is where the rest of them do.
    """
    found: set[str] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in CONSOLE_SUFFIXES:
            continue
        found.update(_CITED_MODULE_RE.findall(path.read_text(encoding="utf-8")))
    return frozenset(found)


def unopenable_reads(
    reads_root: Path = CONSOLE_READS,
    console_root: Path = CONSOLE_SOURCE,
    exempt: Iterable[NoScreen] = NO_SCREEN_NEEDED,
) -> tuple[Unopenable, ...]:
    """Every console read a person cannot open in a browser, in name order.

    A read is openable when the console source names its module, or when a route serves a
    screen key it declares. Exempted modules are dropped here rather than being reported with
    a note beside them, because the list is what somebody reads to decide what to build next
    and an entry that needs no work is noise on it. `exemption_gaps` is what keeps the
    exemptions honest.
    """
    excused = {one.module for one in exempt}
    keys = screen_keys()
    routed = routed_screen_keys(_route_table(console_root), keys)
    cited = modules_named_by_the_console(console_root)
    found: list[Unopenable] = []
    for module in console_reads(reads_root):
        if module in excused or module in cited:
            continue
        declares = screens_declared((reads_root / f"{module}.py").read_text(encoding="utf-8"), keys)
        if set(declares) & routed:
            continue
        found.append(Unopenable(module=module, declares=declares))
    return tuple(found)


def exemption_gaps(
    reads_root: Path = CONSOLE_READS,
    console_root: Path = CONSOLE_SOURCE,
    exempt: Iterable[NoScreen] = NO_SCREEN_NEEDED,
) -> tuple[str, ...]:
    """Everything wrong with the exemption list itself, which is the half that is a gate.

    Two failures and both are the count falling for a reason nobody would accept. An exemption
    naming a module that is not a console read excuses nothing and reads as though it does; an
    exemption for a module that now has a screen is an argument that has been overtaken, and
    leaving it there means the next module renamed onto that name is excused silently.

    See `AN_EXEMPTION_IS_THE_ONLY_WAY_THIS_COUNT_FALLS_WITHOUT_A_SCREEN_BEING_BUILT`.
    """
    reads = set(console_reads(reads_root))
    keys = screen_keys()
    routed = routed_screen_keys(_route_table(console_root), keys)
    cited = modules_named_by_the_console(console_root)
    gaps: list[str] = []
    for one in exempt:
        if one.module not in reads:
            gaps.append(
                f"{one.module} is exempted from having a screen and is not a console read, "
                "so the argument for it is about a module nobody can open or build"
            )
            continue
        declares = screens_declared(
            (reads_root / f"{one.module}.py").read_text(encoding="utf-8"), keys
        )
        if one.module in cited or set(declares) & routed:
            gaps.append(
                f"{one.module} is exempted from having a screen and the console now has one "
                "for it, so the exemption is an argument that has been overtaken and the "
                "next module renamed onto that name would be excused by it silently"
            )
    return tuple(gaps)


def _route_table(console_root: Path) -> str:
    """The route table's source, or nothing at all when the console is not present.

    An empty string rather than a failure, because an install that ships the API without the
    browser console is a supported shape and a sweep that cannot run there is a sweep that
    gets removed. With no route table nothing is routed, which is the honest answer.
    """
    table = console_root / "App.tsx"
    return table.read_text(encoding="utf-8") if table.is_file() else ""


def report_lines(
    reads_root: Path = CONSOLE_READS,
    console_root: Path = CONSOLE_SOURCE,
    exempt: Iterable[NoScreen] = NO_SCREEN_NEEDED,
) -> tuple[str, ...]:
    """What a run prints: the count, then one line per read with no screen.

    Every module on its own line rather than a comma-joined list. Twenty-four names on one
    line is a line nobody reads to the end, and each of these is a separate piece of work with
    a separate sentence about what is missing.
    """
    found = unopenable_reads(reads_root, console_root, exempt)
    excused = tuple(one.module for one in exempt)
    lines = [
        f"note: {len(found)} console read(s) have no screen in the browser, "
        f"{len(excused)} exempted with a written reason"
    ]
    lines.extend(f"      {one.line()}" for one in found)
    return tuple(lines)


def counted(
    reads_root: Path = CONSOLE_READS,
    console_root: Path = CONSOLE_SOURCE,
    exempt: Iterable[NoScreen] = NO_SCREEN_NEEDED,
) -> Mapping[str, int]:
    """The three figures, for a test that wants them without parsing printed lines."""
    return {
        "reads": len(console_reads(reads_root)),
        "without_a_screen": len(unopenable_reads(reads_root, console_root, exempt)),
        "exempt": len(tuple(exempt)),
    }
