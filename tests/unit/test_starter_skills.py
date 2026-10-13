"""The eight starter skills read as files, name only registered tools and carry examples.

Each refusal has the sibling that proves the thing still works. What is held is that furnishing
cannot write anything a pasted file could not, and that a tool renamed in a release is a failing
test and not a starter skill that stopped working on every install.

Task ids: M12.4.7
"""

from __future__ import annotations

from typing import Any, cast

from brain.console.skill_library import read_package
from brain.knowledge.row_store import SessionRowSource
from brain.tools.registry import TOOL_NAME_RE
from brain.tools.skill_examples import examples_of
from brain.tools.skills import FRONTMATTER_KEYS, SkillState
from brain.tools.starter_skills import STARTER_SKILLS, STARTER_VERSION
from brain.tools.startup import build_registry
from brain.tools.website_check import WEBSITE_CHECK_TOOL

#: The eight names M12.4.7 lists, in the owner's order.
NAMES = (
    "seo-audit",
    "keyword-research",
    "website-health-check",
    "ticket-analysis",
    "complaint-analysis",
    "monthly-seo-report",
    "proposal-generation",
    "website-troubleshooting",
)


def _registered() -> set[str]:
    """The tools an install registers, as `build_registry` builds them, the website check included.

    The website check is registered only where the application hands it a transport, so its name is
    added from the constant that registers it.
    """
    registry = build_registry(source="local", records=SessionRowSource(cast(Any, None)))
    return {one.name for one in registry.definitions()} | {WEBSITE_CHECK_TOOL}


def test_the_eight_skills_are_the_ones_the_requirement_lists() -> None:
    """The owner's eight, no more and no fewer, each once.

    Delete this and a skill the requirement names is dropped, or a ninth that nobody asked for
    arrives on every install."""
    assert tuple(one.name for one in STARTER_SKILLS) == NAMES


def test_every_starter_skill_is_a_package_the_one_parser_reads_and_nothing_privileged() -> None:
    """Read through `read_package`, each is an undecided upload at the first version declaring only
    keys a pasted file may, and a description saying when it is used.

    Delete this and a starter skill can carry a key, a script or a description a pasted file would
    be refused for, which is furnishing doing what no administrator could."""
    for starter in STARTER_SKILLS:
        package = read_package("SKILL.md", starter.markdown.encode("utf-8"))
        skill = package.skill
        assert skill.name == starter.name
        assert skill.version == STARTER_VERSION
        assert skill.description.lower().startswith("use when ")
        assert skill.scripts == () and skill.script_sha256 == ()
        declared = {
            line.partition(":")[0] for line in starter.markdown.split("---")[1].strip().splitlines()
        }
        assert declared <= FRONTMATTER_KEYS


def test_every_tool_a_starter_skill_names_is_one_the_install_registers() -> None:
    """Each name in each skill, and in each skill's examples, is in the registry an install builds.

    Delete this and a tool renamed in a release leaves eight skills naming something that is gone,
    learned about at an agent's first run."""
    registered = _registered()
    for starter in STARTER_SKILLS:
        skill = read_package("SKILL.md", starter.markdown.encode("utf-8")).skill
        assert skill.tools, starter.name
        assert all(TOOL_NAME_RE.match(name) for name in skill.tools)
        assert set(skill.tools) <= registered, (starter.name, set(skill.tools) - registered)
        for example in examples_of(skill):
            assert set(example.expects) <= set(skill.tools)


def test_every_starter_skill_carries_examples_a_rehearsal_can_read() -> None:
    """Two to four examples each, with a task of its own, and at least one expecting a tool.

    Delete this and a skill arrives that cannot be rehearsed, so nobody can approve it by the rule
    that approval waits for a rehearsal."""
    for starter in STARTER_SKILLS:
        examples = examples_of(read_package("SKILL.md", starter.markdown.encode("utf-8")).skill)
        assert 2 <= len(examples) <= 4, starter.name
        assert len({one.task for one in examples}) == len(examples)
        assert any(one.expects for one in examples), starter.name


def test_a_starter_skill_added_is_undecided_and_not_executable() -> None:
    """Added as the store adds one, by first run, each is imported and cannot be run or read.

    Delete this and furnishing can produce a skill an agent can read before a person has."""
    from datetime import UTC, datetime

    from brain.console.skill_library import added
    from brain.tools.skills import SkillError, body_of

    for starter in STARTER_SKILLS:
        one = added(
            read_package("SKILL.md", starter.markdown.encode("utf-8")),
            by="first-run",
            at=datetime(2019, 3, 4, tzinfo=UTC),
        )
        assert one.imported.state is SkillState.IMPORTED
        assert not one.imported.is_executable()
        try:
            body_of(one.imported)
        except SkillError:
            continue
        raise AssertionError(f"{starter.name} was readable before a review")
