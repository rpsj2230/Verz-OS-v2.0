"""The skill library's install acceptance checks: registered, pinned, and passing on a real schema.

The pure half holds the checks to the suite and the fixture they fetch to the rules the import
applies: a full commit, an https address, hosts on the list. The database half builds PostgreSQL to
head and runs the four checks as the worker would, with GitHub replaced by a fake transport that
answers the pinned commit's tarball and one raw file, so no test here reaches the network. Every
check passes, and afterwards every table a check wrote to holds what it held before, which is
`brain.ops.acceptance.NOTHING_A_CHECK_WRITES_IS_EVER_COMMITTED` measured for the skill tables. The
import check is then run against a GitHub that does not answer, which is not run, and one that
answers with a redirect off the list, which fails: the two sides of
`brain.ops.acceptance_checks_skills.AN_IMPORT_THAT_CANNOT_REACH_GITHUB_IS_NOT_RUN`.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M38.5.1
"""

from __future__ import annotations

import asyncio
import io
import sys
import tarfile
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import pytest

from brain.ops import acceptance_checks_skills as skills
from brain.ops.acceptance import CHECK_MODULES, FAILED, NOT_RUN, PASSED, Check, registered
from brain.tools.fetch import SKILL_SOURCE_HOSTS, FetchedBytes, github_tarball_url
from brain.tools.skills import COMMIT_RE, SkillError
from tests.unit.test_acceptance import at_head, counts

#: Each skill check and the leaves it proves, as the coordinator scoped them.
LEAVES = {
    "a_pasted_or_uploaded_skill_waits_undecided_and_unread": (
        "M12.2.1",
        "M12.2.4",
        "M12.2.5",
        "M12.4.12",
    ),
    "a_skill_is_imported_from_a_github_commit_and_from_an_address": ("M12.2.2", "M12.2.3"),
    "an_edit_is_a_new_version_and_moves_no_agent_until_reassigned": (
        "M12.2.6",
        "M12.3.2",
        "M12.4.6",
    ),
    "categories_are_kept_and_offered_from_what_a_reader_was_shown": ("M12.4.13",),
}

#: A public address the fake resolver answers with. Nothing ever connects to it.
PUBLIC_ADDRESS = "140.82.121.4"

#: Every table the skill checks write to, which must hold afterwards what it held before.
WRITTEN_BY_SKILL_CHECKS = (
    "agent.skill",
    "agent.skill_review",
    "agent.skill_category",
    "agent.skill_assignment",
    "agent.agent",
    "agent.template_instance",
    "agent.template_version",
)


def mine() -> tuple[Check, ...]:
    return tuple(one for one in registered() if one.name in LEAVES)


def a_skill_md(name: str, description: str) -> bytes:
    return f"---\nname: {name}\ndescription: {description}\n---\nFollow the check.\n".encode()


def a_commit_tarball(folder: str, skill_md: bytes) -> bytes:
    """A tarball shaped as GitHub builds one for a commit: one top folder, the tree under it."""
    top = f"superpowers-{skills.PUBLIC_SKILLS_COMMIT}"
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as archive:
        for name, data in (
            (f"{top}/README.md", b"A readme."),
            (f"{top}/{folder}/SKILL.md", skill_md),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return out.getvalue()


@dataclass
class FakeGitHub:
    """GitHub as the import's transport sees it, or a GitHub that does not answer.

    `answers` False resolves every name to nothing, which is what the install's resolver says when
    DNS fails. `redirect_to` answers every address with a redirect there.
    """

    answers: bool = True
    redirect_to: str = ""

    def resolve(self, host: str) -> Sequence[str]:
        return (PUBLIC_ADDRESS,) if self.answers else ()

    def get_once(self, url: str, *, address: str, max_bytes: int) -> FetchedBytes | str:
        if self.redirect_to:
            return self.redirect_to
        tarball = github_tarball_url(skills.PUBLIC_SKILLS_REPOSITORY, skills.PUBLIC_SKILLS_COMMIT)
        if url == tarball:
            body = a_commit_tarball(
                skills.PUBLIC_SKILL_FOLDER,
                a_skill_md("fetched-at-a-commit", "Use when a repository is imported at a commit"),
            )
            return FetchedBytes(body=body, final_url=url)
        if url == skills.PUBLIC_SKILL_ADDRESS:
            body = a_skill_md("fetched-from-an-address", "Use when a skill arrives by its address")
            return FetchedBytes(body=body, final_url=url)
        msg = "the fake GitHub holds no such address"
        raise SkillError(msg)


def unreachable() -> tuple[FakeGitHub, FakeGitHub]:
    """A transport that reaches nothing, for any run of the suite that must not use the network."""
    nowhere = FakeGitHub(answers=False)
    return nowhere, nowhere


# ------------------------------------------------------------------------ without a server
def test_the_skill_checks_are_in_the_suite_and_prove_the_skill_library_s_leaves() -> None:
    """The module is one the registry imports, and each check names the leaves it was scoped to.
    Delete this and the skill checks can fall out of the run with the Install page listing four
    fewer rows, or close a leaf they do not exercise."""
    assert "brain.ops.acceptance_checks_skills" in CHECK_MODULES
    assert {one.name: one.leaves for one in mine()} == LEAVES


def test_what_the_import_check_fetches_is_pinned_and_on_the_hosts_a_skill_comes_from() -> None:
    """The fixture held to the import's own rules, which live outside the check: a full commit
    sha, a raw address at that same commit and on the list, and an address for the refusal that is
    off it. Delete this and the check can fetch a branch that moves under it, or prove the host
    rule with an address the rule admits."""
    from brain.console.skill_library import github_source, url_source_problem

    assert COMMIT_RE.match(skills.PUBLIC_SKILLS_COMMIT)
    source = github_source(
        skills.PUBLIC_SKILLS_REPOSITORY, skills.PUBLIC_SKILLS_COMMIT, skills.PUBLIC_SKILL_FOLDER
    )
    assert source.commit == skills.PUBLIC_SKILLS_COMMIT
    assert urlsplit(github_tarball_url(source.location, source.commit)).hostname in (
        SKILL_SOURCE_HOSTS
    )
    assert url_source_problem(skills.PUBLIC_SKILL_ADDRESS) is None
    assert urlsplit(skills.PUBLIC_SKILL_ADDRESS).hostname in SKILL_SOURCE_HOSTS
    assert f"/{skills.PUBLIC_SKILLS_COMMIT}/" in urlsplit(skills.PUBLIC_SKILL_ADDRESS).path
    assert urlsplit(skills.OFF_THE_LIST).hostname not in SKILL_SOURCE_HOSTS


def test_the_transport_the_check_uses_is_the_one_the_import_route_hands_the_fetch() -> None:
    """The check proves the install's own transport, not a stand-in. Delete this and the import
    check could be passing over a fetcher no route uses."""
    from brain.ops.skill_fetch import HttpsFetcher, SystemResolver

    fetcher, resolver = skills._transport()
    assert type(fetcher) is HttpsFetcher and type(resolver) is SystemResolver


# --------------------------------------------------------------------------- a real run
def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine
    from brain.settings import settings_from

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def skill_counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in WRITTEN_BY_SKILL_CHECKS
    }


@pytest.mark.needs_db
def test_on_a_real_database_every_skill_check_passes_and_leaves_nothing_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The four checks as the worker runs them, against PostgreSQL at head, with GitHub faked.**
    Each passes with no reason, and every table any of them wrote to, the skill library's, the
    agent's install and the ledger among them, holds afterwards exactly what it held before.
    Delete this and a check that cannot pass on the real schema, or one that commits a skill to a
    client's library, reaches the owner's server first."""
    github = FakeGitHub()
    monkeypatch.setattr(skills, "_transport", lambda: (github, github))
    with at_head("brain_acceptance_skills") as url:
        before = (counts(url), skill_counts(url))
        outcomes = run_checks(url, mine())
        after = (counts(url), skill_counts(url))

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


@pytest.mark.needs_db
def test_the_import_check_is_not_run_when_github_is_silent_and_fails_when_its_rules_refuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A GitHub that resolves to nothing never asked the product anything, so the check is not
    run with its own sentence; a GitHub that answers with a redirect to a host off the list is the
    import's rule refusing, so the check fails. Delete this and an install with no route out
    reports its import as broken, or a broken import hides behind not run."""
    [imports] = [one for one in mine() if one.name.startswith("a_skill_is_imported")]
    with at_head("brain_acceptance_skills_fetch") as url:
        monkeypatch.setattr(skills, "_transport", unreachable)
        silent = run_checks(url, (imports,))
        refusing = FakeGitHub(redirect_to="https://skills.example.net/SKILL.md")
        monkeypatch.setattr(skills, "_transport", lambda: (refusing, refusing))
        refused = run_checks(url, (imports,))

    assert silent[imports.name] == (
        NOT_RUN,
        "GitHub did not answer this server, so no import from it could be asked",
    )
    assert refused[imports.name] == (
        FAILED,
        "GitHub answered and the import's own rules refused it",
    )
