"""The skill library's install acceptance checks: registered, pinned, and passing on a real schema.

The pure half holds the checks to the suite, reads `INSTALL_ACCEPTANCE_SKILL_SOURCE` from its
raw value, holds the fixture it names to the rules the import applies (a full commit, an https
address, hosts on the list), and runs the import check with the setting unset or mistyped, which
is not run with nothing fetched. The pinned repository, commit, folder and address live here and
nowhere in the source: an install names its own. The database half builds PostgreSQL to
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
from typing import Any, cast
from urllib.parse import urlsplit

import pytest

from brain.ops import acceptance_checks_skills as skills
from brain.ops.acceptance import (
    FAILED,
    NOT_RUN,
    PASSED,
    Check,
    CheckNotRunError,
    check_modules,
    registered,
)
from brain.ops.acceptance_run import Harness
from brain.tools.fetch import SKILL_SOURCE_HOSTS, FetchedBytes, github_tarball_url
from brain.tools.skills import COMMIT_RE, SkillError
from tests.unit.test_acceptance import at_head, checks_in, counts

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

#: A public repository whose `SKILL.md` folders the product's parser accepts, as an install would
#: name it in `INSTALL_ACCEPTANCE_SKILL_SOURCE`. Pinned here and not in the source: which public
#: code a server fetches is the install's to choose, and the client-independence sweep refuses a
#: host compiled into the product.
REPOSITORY = "obra/superpowers"

#: The commit of that repository's v6.4.2 release, in full, as an import must name one.
COMMIT = "8ca22dba9a94f28898bbce59f2537ff4d87c747d"

#: The folder the repository import reads its one `SKILL.md` from.
FOLDER = "skills/verification-before-completion"

#: A second skill of the same commit, by its raw address: another skill, so another digest.
ADDRESS = (
    f"https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/skills/receiving-code-review/SKILL.md"
)

#: The whole setting, as `.env` or Install, Settings would hold it.
SOURCE = f"{REPOSITORY}@{COMMIT}:{FOLDER},{ADDRESS}"

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
    top = f"superpowers-{COMMIT}"
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
        tarball = github_tarball_url(REPOSITORY, COMMIT)
        if url == tarball:
            body = a_commit_tarball(
                FOLDER,
                a_skill_md("fetched-at-a-commit", "Use when a repository is imported at a commit"),
            )
            return FetchedBytes(body=body, final_url=url)
        if url == ADDRESS:
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
    assert "brain.ops.acceptance_checks_skills" in check_modules()
    assert {one.name: one.leaves for one in mine()} == LEAVES


def test_what_the_import_check_fetches_is_pinned_and_on_the_hosts_a_skill_comes_from() -> None:
    """The fixture held to the import's own rules, which live outside the check: a full commit
    sha, a raw address at that same commit and on the list, and an address for the refusal that is
    off it. Delete this and the check can fetch a branch that moves under it, or prove the host
    rule with an address the rule admits."""
    from brain.console.skill_library import github_source, url_source_problem

    assert COMMIT_RE.match(COMMIT)
    source = github_source(REPOSITORY, COMMIT, FOLDER)
    assert source.commit == COMMIT
    assert urlsplit(github_tarball_url(source.location, source.commit)).hostname in (
        SKILL_SOURCE_HOSTS
    )
    assert url_source_problem(ADDRESS) is None
    assert urlsplit(ADDRESS).hostname in SKILL_SOURCE_HOSTS
    assert f"/{COMMIT}/" in urlsplit(ADDRESS).path
    assert urlsplit(skills.OFF_THE_LIST).hostname not in SKILL_SOURCE_HOSTS


def test_the_setting_is_read_into_its_four_parts_and_nothing_else_is() -> None:
    """`owner/repository@commit:folder,address` from the raw value an install writes, and every
    shape missing a part is None rather than a partial source. Delete this and a mistyped setting
    can fetch a folder of the wrong repository, or an empty address."""
    assert skills.public_skills(SOURCE) == skills.PublicSkills(REPOSITORY, COMMIT, FOLDER, ADDRESS)
    assert skills.public_skills(f"  {REPOSITORY}@{COMMIT}:{FOLDER} , {ADDRESS} ") == (
        skills.PublicSkills(REPOSITORY, COMMIT, FOLDER, ADDRESS)
    )
    for broken in (
        "",
        "unset",
        f"{REPOSITORY}@{COMMIT}:{FOLDER}",
        f"{REPOSITORY}:{FOLDER},{ADDRESS}",
        f"{REPOSITORY}@{COMMIT},{ADDRESS}",
        f"@{COMMIT}:{FOLDER},{ADDRESS}",
        f"{REPOSITORY}@:{FOLDER},{ADDRESS}",
        f"{REPOSITORY}@{COMMIT}:,{ADDRESS}",
        f"{REPOSITORY}@{COMMIT}:{FOLDER},",
        f"{REPOSITORY}@{COMMIT}:{FOLDER},{ADDRESS},{ADDRESS}",
    ):
        assert skills.public_skills(broken) is None, broken


def test_the_setting_is_declared_unset_and_read_by_this_check_alone() -> None:
    """Declared in `brain.install` with `unset` as its default, so a fresh install fetches nothing,
    and named on the Settings screen as read by this module, read-only with its reason. Delete this
    and a default every install fetches can creep back in, or the value can sit on no screen."""
    from brain.console.configuration import EDITABLE_SETTINGS, READ_BY, READ_ONLY_BECAUSE
    from brain.install import BY_NAME

    declared = BY_NAME[skills.SKILL_SOURCE_SETTING]
    assert declared.default == "unset" and not declared.required
    assert skills.public_skills(declared.default) is None
    assert READ_BY[skills.SKILL_SOURCE_SETTING] == ("brain.ops.acceptance_checks_skills",)
    assert skills.SKILL_SOURCE_SETTING not in EDITABLE_SETTINGS
    assert READ_ONLY_BECAUSE[skills.SKILL_SOURCE_SETTING]


def _nothing_is_fetched() -> tuple[FakeGitHub, FakeGitHub]:
    raise AssertionError("the import check reached for a transport with no source named")


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (None, "this install names no public skill to import, so no import from GitHub was asked"),
        (
            "unset",
            "this install names no public skill to import, so no import from GitHub was asked",
        ),
        (
            f"{REPOSITORY}@{COMMIT}:{FOLDER}",
            "the public skill this install names is not a repository folder at a commit and an "
            "https address on an allowed host",
        ),
        (
            f"{REPOSITORY}@{COMMIT}:{FOLDER},https://skills.example.net/SKILL.md",
            "the public skill this install names is not a repository folder at a commit and an "
            "https address on an allowed host",
        ),
        (
            f"{REPOSITORY}@main:{FOLDER},{ADDRESS}",
            "the public skill this install names is not a repository folder at a full commit",
        ),
    ],
)
def test_the_import_check_is_not_run_and_fetches_nothing_until_the_install_names_a_source(
    monkeypatch: pytest.MonkeyPatch, value: str | None, reason: str
) -> None:
    """`AN_IMPORT_NOBODY_NAMED_IS_NOT_RUN`: unset, or set to something that is not a repository at
    a full commit and an allowed address, the check is not run with its own sentence, before it
    asks for a transport or touches the database. Delete this and a fresh install fetches from a
    host nobody chose, or reports a mistyped setting as a broken import."""
    from brain.install import hold_saved

    [imports] = [one for one in mine() if one.name.startswith("a_skill_is_imported")]
    if value is None:
        monkeypatch.delenv(skills.SKILL_SOURCE_SETTING, raising=False)
    else:
        monkeypatch.setenv(skills.SKILL_SOURCE_SETTING, value)
    monkeypatch.setattr(skills, "_transport", _nothing_is_fetched)
    held = hold_saved({})
    try:
        with pytest.raises(CheckNotRunError) as refused:
            # The harness is never reached: every refusal here comes before the first read.
            asyncio.run(imports.run(cast(Harness, object())))
    finally:
        hold_saved(held)
    assert str(refused.value) == reason


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
    monkeypatch.setenv(skills.SKILL_SOURCE_SETTING, SOURCE)
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
    monkeypatch.setenv(skills.SKILL_SOURCE_SETTING, SOURCE)
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


def test_the_skills_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here,
    beside the module's other tests, since 2026-09-30, so a package adding a check edits its own
    file and never a list every package appends to. Delete this and a check can drop out of the
    module with the page simply listing one fewer row."""
    assert checks_in("brain.ops.acceptance_checks_skills") == [
        "a_pasted_or_uploaded_skill_waits_undecided_and_unread",
        "a_skill_is_imported_from_a_github_commit_and_from_an_address",
        "an_edit_is_a_new_version_and_moves_no_agent_until_reassigned",
        "categories_are_kept_and_offered_from_what_a_reader_was_shown",
    ]
