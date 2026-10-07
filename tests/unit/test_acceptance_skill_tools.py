"""The install checks for how an agent's run reads a skill, each passing on PostgreSQL at head and
each failing with the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: both checks
pass and leave nothing. Then each is shown failing: a run whose model is sent a skill's body before
it asks or is never sent it when it does, a skill nobody assigned handed over by name, a registry
holding no tool that runs a script, a script sent to the sandbox when its bytes are not the
approved ones, and a run in which the output a script printed is not handed back.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M12.2.8, M12.2.9, M12.4.11
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.core.envelope import TypedResult
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, SENTENCE_CHARS, registered
from brain.ops.acceptance_checks_skill_tools import CHECK_ORDER
from brain.settings import settings_from
from brain.tools import skill_tools
from brain.tools.skill_tools import InstructionsRequest, SkillInstructions
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_skill_tools"
_REAL_HANDLER = skill_tools.instructions_handler
DISCLOSURE = "a_skills_body_reaches_a_model_only_when_it_asks_for_it"
SCRIPT = "a_skills_script_runs_through_the_one_tool_and_only_as_approved"
WEBSITE = "a_run_checks_a_website_and_is_handed_what_it_found"

#: What these checks write beyond the suite's own list of tables.
ALSO_WRITTEN = ("agent.skill_script",)


def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Two checks, each naming exactly the leaves it proves. Delete this and a check can drift onto
    a leaf its sentence does not prove, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (DISCLOSURE, ("M12.2.8",)),
        (SCRIPT, ("M12.2.9", "M12.4.11")),
        (WEBSITE, ("M12.4.4",)),
    ]


def test_the_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [DISCLOSURE, SCRIPT, WEBSITE]


def test_the_module_stands_after_the_checks_whose_helpers_it_uses() -> None:
    """The key follows the skill library's checks and the packages' ones. Delete this and the page
    can list this module above the checks it depends on."""
    from brain.ops import acceptance_checks_skill_packages, acceptance_checks_skills

    assert (
        max(acceptance_checks_skills.CHECK_ORDER, acceptance_checks_skill_packages.CHECK_ORDER)
        < CHECK_ORDER
    )


def test_every_sentence_fits_the_page_and_every_reason_fits_the_column() -> None:
    """The sentences the page shows and the reasons it stores, each within its bound. Delete this
    and a sentence is cut short on the Install page or a reason is refused by the column."""
    import ast
    import inspect

    from brain.ops import acceptance_checks_skill_tools as module

    for one in registered((MODULE,)):
        assert 0 < len(one.sentence) <= SENTENCE_CHARS, one.name
    tree = ast.parse(inspect.getsource(module))
    named = {
        target.id: node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and isinstance(node.value, ast.Constant)
        for target in (node.target,)
    }
    reasons = [str(value) for key, value in named.items() if key.isupper() and key != "CHECK_ORDER"]
    assert len(reasons) >= 12
    assert all(len(reason) <= REASON_CHARS for reason in reasons if " " in reason)


@pytest.fixture(autouse=True)
def hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hosted profile, so the stand-in may be asked; no provider's key is needed for it. And a
    documentation site that answers in the process, so no test asks the network."""
    from brain.ops import acceptance_checks_skill_tools as module
    from tests.unit.test_website_check import Prober, Resolver

    monkeypatch.setenv("INSTALL_MODEL_PROFILE", "hosted")
    monkeypatch.setattr(module, "_website_transport", lambda: (Resolver(), Prober()))


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_skill_tools") as url:
        yield url


def run_tools(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def silent() -> Any:
    """The instructions handler answering with no record, as a tool that reads nothing would."""
    inner = _REAL_HANDLER()

    async def read(request: InstructionsRequest, **kwargs: Any) -> TypedResult[SkillInstructions]:
        result = await inner(request, **kwargs)
        return result.model_copy(update={"records": ()})

    return read


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_both_skill_tool_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The module as the worker runs it.** Both pass, and nothing a check wrote is left: no skill,
    script, agent, grant or request row. Delete this and a check that can never pass on a real
    schema, or one that leaves an agent holding a script tool, reaches the owner's server."""
    before = _counts(install)
    outcomes = run_tools(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 3
    assert _counts(install) == before


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_tools(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_body_sent_early_or_never_or_to_the_wrong_agent_fails_the_disclosure_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A card that carries the body, then a tool that hands nothing over, then one that answers
    for any approved skill. Delete this and M12.2.8 closes on a prompt that was never small, a
    tool that never answers, or one that reads the library by name."""
    from brain.tools import skill_tools
    from brain.tools.skills import SkillCard, offered_cards

    real_cards = offered_cards

    def with_body(skills: Any) -> Any:
        return tuple(
            SkillCard(
                name=card.name,
                description=f"{card.description} {one.skill.body}",
                version=card.version,
            )
            for card, one in zip(real_cards(skills), skills, strict=True)
        )

    with monkeypatch.context() as patched:
        patched.setattr("brain.api_routes.offered_cards", with_body)
        assert "before it asked" in _failed(install, DISCLOSURE)

    with monkeypatch.context() as patched:
        patched.setattr(skill_tools, "instructions_handler", silent)
        assert "not sent them" in _failed(install, DISCLOSURE)


@pytest.mark.needs_db
def test_a_script_run_with_the_wrong_bytes_or_no_output_fails_the_script_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runner's byte check removed, then a tool whose output the run drops. Delete this and
    M12.4.11 closes on a path that sends a changed script to the sandbox, and M12.2.9 on one that
    runs a script and tells nobody."""
    from brain.tools import run_skill

    real = run_skill.verify_script_bytes

    def unchecked(spec: Any, files: Any) -> None:
        return None

    with monkeypatch.context() as patched:
        patched.setattr("brain.ops.sandbox_client.verify_script_bytes", unchecked)
        assert "not the approved ones" in _failed(install, SCRIPT)
    assert real is run_skill.verify_script_bytes


@pytest.mark.needs_db
def test_a_website_check_a_run_cannot_read_or_that_reaches_another_host_fails_the_website_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tool's own policy taken away, so a run is handed an empty record, then a site nothing
    can reach, which is a check not run and never a failure of the product. Delete this and M12.4.4
    closes on a tool whose result a run is never shown, which is how it stood, or an install with
    no route out is told its website check is broken."""
    from brain.ops import acceptance_checks_skill_tools as module
    from brain.tools.own_results import OWN_RESULT_POLICIES
    from brain.tools.website_check import WEBSITE_CHECK_OBJECT

    without = {
        key: value for key, value in OWN_RESULT_POLICIES.items() if key != WEBSITE_CHECK_OBJECT
    }
    with monkeypatch.context() as patched:
        patched.setattr("brain.api_routes.OWN_RESULT_POLICIES", without)
        assert "no status" in _failed(install, WEBSITE)

    from tests.unit.test_website_check import Prober, Resolver

    class Everything(Prober):
        async def probe(self, target: Any, *, timeout_seconds: float) -> Any:
            self.probed.append(target)
            from brain.tools.website_check import ProbeAnswer, ProbeFailure

            return ProbeAnswer(elapsed_seconds=0.0, failure=next(iter(ProbeFailure)))

    monkeypatch.setattr(module, "_website_transport", lambda: (Resolver(), Everything()))
    [(outcome, reason)] = run_tools(install, WEBSITE).values()
    assert outcome == "not run" and "could not reach" in reason
