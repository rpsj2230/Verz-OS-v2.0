"""Every console read has a screen or a written reason it has none (M27.7.1).

The check itself is a piece of parsing, so most of these tests build a small tree of their
own: two console read modules, a route table, a page. That is deliberate rather than
convenient. A test written against this repository's own `src/brain/console` would go red
whenever somebody added a module or a route, which is the ordinary state of this tree, and a
test that goes red for correct work is one somebody deletes. The two tests that do read this
repository ask about its shape rather than about its contents.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from brain.ops import sweeps
from brain.ops.console_screens import (
    NO_SCREEN_NEEDED,
    NoScreen,
    Unopenable,
    console_reads,
    counted,
    exemption_gaps,
    modules_named_by_the_console,
    report_lines,
    routed_screen_keys,
    screen_keys,
    screens_declared,
    unopenable_reads,
)

#: A read that binds itself to a screen the way every module in this package does.
DECLARES_AGENTS = 'SOMETHING_SCREEN: Final = "agents"\n'
#: The same screen key, asked for inside a function, which is a borrow and not a declaration.
BORROWS_AGENTS = "def offered(reader):\n    return screen('agents').read.requires\n"
#: A route table with one route that serves that screen and one that serves nothing.
ROUTE_TABLE = """
export const routes = [
  { path: "agents", element: <Agents /> },
  { path: "agents/:agentId", element: <Agent /> },
  { path: "*", element: <NotFound /> },
];
"""
#: The same table with the screen's route taken out.
NO_ROUTES = 'export const routes = [{ path: "*", element: <NotFound /> }];\n'


def _tree(tmp_path: Path, *, reads: dict[str, str], console: dict[str, str]) -> tuple[Path, Path]:
    """One synthetic repository: some console reads, and a console source tree."""
    reads_root = tmp_path / "console_reads"
    console_root = tmp_path / "console_src"
    reads_root.mkdir()
    console_root.mkdir()
    for name, source in reads.items():
        (reads_root / f"{name}.py").write_text(source, encoding="utf-8", newline="\n")
    for name, source in console.items():
        path = console_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8", newline="\n")
    return reads_root, console_root


def _exemption(module: str) -> NoScreen:
    """A well-formed exemption for one module, so a test can vary only what it is about."""
    return NoScreen(
        module=module,
        consumed_by=(
            "brain.ops.something_else, which puts the one fact this module produces on top "
            "of whichever screen the reader had already opened for another reason"
        ),
        reason=(
            "There is no screen this module is about, and a screen of its own would show a "
            "measurement to an administrator who came to read something entirely different"
        ),
    )


# --------------------------------------------------------------- the finding and its absence
def test_a_console_read_no_route_and_no_page_names_is_reported(tmp_path):
    """Deleting this lets a console read exist with nothing in the browser that opens it.

    That is the state twenty-four of this repository's reads were in on 2026-09-16, and the
    whole of M27.7.1
    is that nothing said so: the module is finished from the tracker's point of view and
    invisible from a browser's.
    """
    reads_root, console_root = _tree(
        tmp_path,
        reads={"lonely": DECLARES_AGENTS},
        console={"App.tsx": NO_ROUTES},
    )
    found = unopenable_reads(reads_root, console_root, exempt=())
    assert [one.module for one in found] == ["lonely"]
    assert found[0].declares == ("agents",)


def test_a_console_read_whose_declared_screen_a_route_serves_is_not_reported(tmp_path):
    """Deleting this lets the check report every read, which satisfies a function that always
    reports and would put twenty-nine names on a list where twenty-four belong.

    The sibling of the test above and the reason it is worth anything: a guard tested only by
    its findings is satisfied by a check that finds everything.
    """
    reads_root, console_root = _tree(
        tmp_path,
        reads={"served": DECLARES_AGENTS},
        console={"App.tsx": ROUTE_TABLE},
    )
    assert unopenable_reads(reads_root, console_root, exempt=()) == ()


def test_a_console_read_the_console_source_names_is_not_reported(tmp_path):
    """Deleting this lets the second way a page declares a read stop counting.

    `console/src/pages/approvalsQuery.ts` names `brain.console.approvals` and that module
    declares no screen key of its own, so a check reading only declarations would report the
    one read this console demonstrably opens.
    """
    reads_root, console_root = _tree(
        tmp_path,
        reads={"approvals": "CARD = 1\n"},
        console={
            "App.tsx": NO_ROUTES,
            "pages/approvalsQuery.ts": "// the cards brain.console.approvals.card builds\n",
        },
    )
    assert unopenable_reads(reads_root, console_root, exempt=()) == ()
    assert "approvals" in modules_named_by_the_console(console_root)


def test_a_read_with_no_screen_key_at_all_says_so_rather_than_naming_none(tmp_path):
    """Deleting this lets the two ways of having no screen print the same sentence.

    They are different pieces of work. A module declaring a key nothing routes is waiting for
    a page; a module declaring no key is not wired to the registry either, so there is nothing
    for a page to be written against.
    """
    reads_root, console_root = _tree(
        tmp_path,
        reads={"unwired": "NOTHING = 1\n"},
        console={"App.tsx": ROUTE_TABLE},
    )
    found = unopenable_reads(reads_root, console_root, exempt=())
    assert found[0].declares == ()
    assert "declares no screen key" in found[0].line()
    assert "declares no screen key" not in Unopenable("x", ("agents",)).line()


# ----------------------------------------------------------- what counts as a declaration
def test_a_capability_borrowed_inside_a_function_is_not_a_screen_being_served():
    """Deleting this lets a dropdown make a module look reachable.

    `brain.console.usage_view` asks for `screen("agents").read.requires` to decide what a
    filter may offer. Read generously, seven modules looked served and five of them were
    borrowing a capability, which is this check failing in the direction that reads as good
    news.

    The third line is the same distinction at module level: a constant holding a screen key
    under a name that says nothing about screens is a value this module has no opinion about,
    and reading every module-level string would make one of those a declaration.
    """
    assert screens_declared(BORROWS_AGENTS) == ()
    assert screens_declared('SOMETHING_ELSE = "agents"\n') == ()
    assert screens_declared(DECLARES_AGENTS) == ("agents",)


def test_a_declaration_is_read_through_the_wrappers_this_package_declares_them_in():
    """Deleting this lets a module that serves several screens be read as serving none.

    `brain.console.global_surfaces.ESTATE_SCREEN` is a `MappingProxyType` of them and
    `brain.console.operate` declares two separately. A reader that only understood a bare
    string literal would report both as declaring nothing at all.

    Both answers come back in the registry's order rather than the module's, so a reader
    comparing a line of this report against a menu is comparing two lists in one order.
    Approvals is registered before Agents, which is why neither pair below is alphabetical.
    """
    mapping = 'ESTATE_SCREEN: Final = MappingProxyType({"a": "agents", "b": "approvals"})\n'
    assert screens_declared(mapping) == ("approvals", "agents")
    assert screens_declared('A_SCREEN = "agents"\nB_SCREEN = "approvals"\n') == (
        "approvals",
        "agents",
    )


def test_a_module_serving_one_screen_may_name_the_constant_for_the_screen_and_not_the_module():
    """Deleting this lets `SCREEN_KEY` and `THE_SCREEN` stop counting as declarations.

    Two modules use them and both are real: `brain.console.service_level_view.SCREEN_KEY` and
    `brain.console.staff_source_view.THE_SCREEN`. A module serving exactly one screen has no
    second screen to distinguish it from, so it names the constant for what it is. Emptying
    `SCREEN_DECLARATION_NAMES` survived every other test here: both modules stayed on the list
    of reads with no screen, and the line about each stopped naming the screen it is waiting
    for, which is the report going quietly vaguer rather than wrong.
    """
    assert screens_declared('SCREEN_KEY: Final = "service_levels"\n') == ("service_levels",)
    assert screens_declared('THE_SCREEN: Final = "staff_sources"\n') == ("staff_sources",)
    assert screens_declared(
        (Path("src/brain/console/service_level_view.py")).read_text(encoding="utf-8")
    ) == ("service_levels",)
    assert screens_declared(
        (Path("src/brain/console/staff_source_view.py")).read_text(encoding="utf-8")
    ) == ("staff_sources",)


def test_a_mapping_keyed_by_a_screen_name_is_not_a_declaration_of_that_screen():
    """Deleting this lets a key that happens to spell a screen name excuse a module.

    A declaration mapping is keyed by the kind of thing and valued by the screen it opens.
    Reading both halves would admit whatever the keys happen to be called, which is a value
    this check has no opinion about.
    """
    assert screens_declared('X_SCREEN: Final = {"agents": "not_a_screen_key"}\n') == ()


def test_the_index_route_names_its_screen_in_its_element_and_nowhere_else():
    """Deleting this loses the overview, which is the one screen with no path at all.

    It is the index route, so `<Overview />` is the only thing about it that says what it
    shows. A check reading paths alone would report every module serving the front page.
    """
    table = "export const routes = [{ index: true, element: <Overview /> }];\n"
    assert routed_screen_keys(table) == frozenset({"overview"})


def test_a_deep_link_is_the_same_screen_with_something_open():
    """Deleting this lets `agents/:agentId` be read as a screen key of its own.

    It would then match no registry key, and the Agents screen would be reported as having no
    route on a console that routes it twice.

    The first table holds the deep link on its own, because a table holding the plain path as
    well answers the same whether the segment is read or the whole path is, and a test that
    cannot tell the two apart is not asking this question.
    """
    deep_link_only = 'export const routes = [{ path: "agents/:agentId", element: <Agent /> }];\n'
    assert routed_screen_keys(deep_link_only) == frozenset({"agents"})
    assert routed_screen_keys(ROUTE_TABLE) == frozenset({"agents"})


def test_a_console_that_is_not_present_routes_nothing_rather_than_failing(tmp_path):
    """Deleting this makes the sweep fail on an install that ships the API without the console.

    That is a supported shape, and a sweep that cannot run there is a sweep somebody removes
    from the pipeline rather than one somebody fixes.
    """
    reads_root, console_root = _tree(tmp_path, reads={"lonely": DECLARES_AGENTS}, console={})
    found = unopenable_reads(reads_root, console_root, exempt=())
    assert [one.module for one in found] == ["lonely"]


def test_the_registry_and_the_vocabulary_are_not_console_reads():
    """Deleting this puts `reads.py` and `screens.py` on the list for ever.

    Neither decides what any particular reader may see: one is the vocabulary a console read
    is written in and the other is the registry of what a screen is. There is no screen that
    could be built for either, so a line asking for one is a line that can never be actioned.
    """
    reads = console_reads()
    assert "reads" not in reads
    assert "screens" not in reads
    assert "govern" in reads


# ------------------------------------------------------------------------- the exemptions
def test_an_exemption_without_a_reason_is_refused():
    """Deleting this makes an exemption a keystroke.

    It is the only way a module leaves this list without a screen being built for it, so it
    has to cost more than a flag does. Both fields, because an exemption that names a
    consuming surface and argues nothing is as easy to write as one that argues and names
    nothing.
    """
    with pytest.raises(ValueError, match="consumed_by"):
        NoScreen(module="x", consumed_by="another surface", reason=_exemption("x").reason)
    with pytest.raises(ValueError, match="reason"):
        NoScreen(module="x", consumed_by=_exemption("x").consumed_by, reason="not needed")
    with pytest.raises(ValueError, match="no module"):
        NoScreen(
            module="",
            consumed_by=_exemption("x").consumed_by,
            reason=_exemption("x").reason,
        )
    # And the positive case: a fully argued exemption is accepted, or the guard above is
    # satisfied by a type nobody can construct.
    assert _exemption("read_replica").module == "read_replica"


def test_the_exemption_list_is_held_exactly():
    """Deleting this lets the list grow silently, which is the count falling without a screen.

    Held as the exact tuple rather than as a length or a membership, so an exemption added,
    removed or repointed at another module is an edit somebody has to make here as well, in
    front of a reviewer.
    """
    assert tuple(one.module for one in NO_SCREEN_NEEDED) == ("read_replica",)


def test_an_exemption_naming_no_console_read_is_a_finding():
    """Deleting this lets an exemption excuse a module that does not exist.

    It reads as though it excuses something, it survives the module being renamed, and the
    module under the new name is then on the list with nothing explaining why the old
    argument no longer applies to it.
    """
    gaps = exemption_gaps(exempt=(_exemption("no_such_console_module"),))
    assert len(gaps) == 1
    assert "is not a console read" in gaps[0]


def test_an_exemption_for_a_module_that_now_has_a_screen_is_a_finding(tmp_path):
    """Deleting this lets an overtaken argument sit in the list for ever.

    The exemption is then doing nothing until the day somebody renames another module onto
    that name, at which point it silently excuses a module nobody argued about.
    """
    reads_root, console_root = _tree(
        tmp_path,
        reads={"served": DECLARES_AGENTS},
        console={"App.tsx": ROUTE_TABLE},
    )
    gaps = exemption_gaps(reads_root, console_root, exempt=(_exemption("served"),))
    assert len(gaps) == 1
    assert "the console now has one for it" in gaps[0]


def test_an_exemption_that_still_holds_is_not_a_finding(tmp_path):
    """Deleting this lets `exemption_gaps` report every exemption, which would make the gate
    it feeds red for a list that is doing exactly what it is for.

    The sibling of the two tests above, and the reason either means anything.
    """
    reads_root, console_root = _tree(
        tmp_path,
        reads={"lonely": DECLARES_AGENTS},
        console={"App.tsx": NO_ROUTES},
    )
    assert exemption_gaps(reads_root, console_root, exempt=(_exemption("lonely"),)) == ()
    assert exemption_gaps() == ()


def test_an_exempted_read_is_not_also_on_the_list(tmp_path):
    """Deleting this prints a line asking for work somebody has already argued against.

    The list is what a person reads to decide what to build next, so an entry that needs no
    work is noise on it, and the honesty of the list is kept by `exemption_gaps` instead.
    """
    reads_root, console_root = _tree(
        tmp_path,
        reads={"lonely": DECLARES_AGENTS},
        console={"App.tsx": NO_ROUTES},
    )
    assert unopenable_reads(reads_root, console_root, exempt=(_exemption("lonely"),)) == ()


# ------------------------------------------------------------- what a run prints, and where
def test_every_read_with_no_screen_is_named_on_a_line_of_its_own(tmp_path):
    """Deleting this lets the report become a count.

    A count of modules nobody can open is one more figure nobody can act on, which is the
    argument `sweep_traceability` already makes about printing its phantom ids rather than
    counting them. Each of these is a separate piece of work with a separate sentence about
    what is missing.
    """
    reads_root, console_root = _tree(
        tmp_path,
        reads={"one": DECLARES_AGENTS, "two": "NOTHING = 1\n"},
        console={"App.tsx": NO_ROUTES},
    )
    lines = report_lines(reads_root, console_root, exempt=())
    assert lines[0].startswith("note: 2 console read(s) have no screen in the browser")
    assert len(lines) == 3
    assert any("brain.console.one" in one for one in lines)
    assert any("brain.console.two" in one for one in lines)


def test_the_sweep_that_runs_on_every_push_is_the_one_that_prints_this():
    """Deleting this lets the report move somewhere nobody runs.

    `brain.ops.sweeps traceability` is the only sweep `ops/hooks/pre-push` runs against the
    commit and CI runs against the branch, so a note printed there is printed on every run and
    a note printed anywhere else is printed on none. Asserted against the parsed call
    expressions rather than a substring of the file, because a comment naming the function
    would satisfy a text search and this repository has had two tests pass that way.
    """
    calls = {
        ast.unparse(node.func)
        for node in ast.walk(ast.parse(inspect.getsource(sweeps.sweep_traceability)))
        if isinstance(node, ast.Call)
    }
    assert "console_screens.report_lines" in calls
    assert "console_screens.exemption_gaps" in calls


def test_this_repository_has_console_reads_nobody_can_open_and_names_every_one():
    """Deleting this lets the check pass on a tree it was written for by reporting nothing.

    Every other test here runs against a synthetic tree, so all of them would stay green with
    the roots pointed at an empty directory. This one asserts the shape of the real answer: the
    reads exist, the list is a strict subset of them, nothing exempted is on it, and every
    line names a module that is a file on disk.
    """
    figures = counted()
    assert figures["reads"] > 20
    assert 0 < figures["without_a_screen"] < figures["reads"]
    found = unopenable_reads()
    excused = {one.module for one in NO_SCREEN_NEEDED}
    for one in found:
        assert one.module not in excused
        assert (Path("src/brain/console") / f"{one.module}.py").is_file()
        assert set(one.declares) <= screen_keys()
    # The two the console demonstrably opens. `workspace` is named by `pages/Agent.tsx` and
    # `approvals` by `pages/approvalsQuery.ts`, so a check reporting either has stopped
    # reading the console source at all.
    assert {"workspace", "approvals"}.isdisjoint({one.module for one in found})
