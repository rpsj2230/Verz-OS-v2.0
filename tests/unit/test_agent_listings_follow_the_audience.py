"""Every place the product reads many agents asks whose they are before it names one.

A personal agent is listed, opened and used by its owner alone. That is one function,
`brain.agents.model.visible_agent_ids` (and `runnable_agent_ids` for what may answer), and it holds
only while every surface that reads the agent table asks it. This walks the source for each module
that reads agents in bulk and requires it to name that function or to be listed below with the
reason it need not, so a new roster, picker, dashboard or export that forgets the audience fails
here and not on an install, where it would have told a person which of their colleagues had made an
agent.

**Reading the source is the check, and it is checked.** The table below is held to the source in
both directions: a module that reads agents and is neither asking nor listed fails, and an entry
whose module no longer reads agents in bulk fails, so the list of reasons cannot outlive what they
excuse.

Task ids: M39.10.3
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

SRC: Final = Path(__file__).resolve().parents[2] / "src" / "brain"

#: The calls that read the agent table for more than one agent.
BULK_READS: Final = frozenset(
    {
        "every_agent",
        "every_agent_with_install",
        "every_agent_with_install_hash",
        "read_stored_agents",
    }
)

#: The questions that decide whether a person may see or use an agent.
AUDIENCE_QUESTIONS: Final = frozenset(
    {"visible_agent_ids", "runnable_agent_ids", "visible_to", "viewer_of", "viewer_for"}
)

#: Modules that read agents in bulk and do not name the audience question, and why each is right.
READS_WITHOUT_ASKING_THE_AUDIENCE: Final[dict[str, str]] = {
    "agent_oversight_routes.py": (
        "Its own list, under the audit capability, through brain.agents.oversight.overseen: it "
        "names the agent and offers nothing to do with it."
    ),
    "agent_roster.py": (
        "The answer lane's reader hands every agent to brain.gate.roster.answer_roster, which "
        "keeps runnable_agent_ids' answer for the person asking (held below)."
    ),
    "agent_upgrade_routes.py": (
        "Reads the one agent a route named and the route asks visible() of it before answering."
    ),
    "builder/draft_store.py": (
        "Reads the one agent a draft names; the builder's routes ask visible() of it first."
    ),
    "ops/stewardship_store.py": (
        "Lists the agents a person stewards for that person alone, by their own id."
    ),
    "staff_source_routes.py": (
        "Reads a leaver's agents into brain.console.staff_source_view.transfers_for, which never "
        "lists a personal agent (held in tests/unit/test_staff_sync_routes.py)."
    ),
}


def calls_in(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called = node.func
            found.add(called.id if isinstance(called, ast.Name) else getattr(called, "attr", ""))
    return found


def readers() -> dict[str, ast.Module]:
    """Every module that calls a bulk read of agents, other than an install check, by path."""
    found: dict[str, ast.Module] = {}
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        if relative.startswith("ops/acceptance_checks_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        selects_agents = any(
            isinstance(node, ast.Call)
            and getattr(node.func, "id", "") == "select"
            and node.args
            and getattr(node.args[0], "id", "") == "AgentRow"
            for node in ast.walk(tree)
        )
        if (calls_in(tree) & BULK_READS) or selects_agents:
            found[relative] = tree
    return found


def test_every_module_that_reads_agents_in_bulk_asks_the_audience_or_is_excused() -> None:
    """A module that reads many agents and names no audience question, and is not in the table of
    reasons, is a listing that could show a person another person's personal agent.

    Delete this and a new roster that forgets the audience reaches an install unseen."""
    unasked = {path for path, tree in readers().items() if not calls_in(tree) & AUDIENCE_QUESTIONS}

    assert unasked == set(READS_WITHOUT_ASKING_THE_AUDIENCE), (
        "modules reading agents without asking whose they are: "
        f"{sorted(unasked - set(READS_WITHOUT_ASKING_THE_AUDIENCE))}; "
        f"entries excusing a module that no longer needs it: "
        f"{sorted(set(READS_WITHOUT_ASKING_THE_AUDIENCE) - unasked)}"
    )


def test_the_walk_finds_the_modules_that_call_the_audience_question_and_not_only_import_it() -> (
    None
):
    """The table's modules and the asking ones are disjoint by construction; a module is asking only
    when it calls the question (importing it asks nothing), and the asking set is not empty, so the
    check above has something to be false about.

    Delete this and the walk could find no readers at all and pass."""
    found = readers()
    asking = {path for path, tree in found.items() if calls_in(tree) & AUDIENCE_QUESTIONS}

    assert len(asking) >= 8
    assert not asking & set(READS_WITHOUT_ASKING_THE_AUDIENCE)
    assert {
        "agent_routes.py",
        "estate_routes.py",
        "skill_routes.py",
        "artifact_routes.py",
    } <= asking


def test_the_excuse_that_leans_on_another_function_names_it() -> None:
    """The answer lane's roster keeps what `runnable_agent_ids` answers, and the person's own agents
    page is built through `my_agents`, which asks the audience.

    Delete this and the table's reason for the roster is a promise nothing holds."""
    roster = ast.parse((SRC / "gate" / "roster.py").read_text(encoding="utf-8"))
    activity = ast.parse((SRC / "member_activity.py").read_text(encoding="utf-8"))
    mine = ast.parse((SRC / "mine_routes.py").read_text(encoding="utf-8"))

    assert "runnable_agent_ids" in calls_in(roster)
    assert {"runnable_agent_ids", "visible_agent_ids"} & calls_in(activity)
    assert "my_agents" in calls_in(mine)
