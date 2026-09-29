"""A skill from a repository commit or an address, an edit as a new version, categories, and the
words a reviewer is shown: `brain.console.skill_library`, `brain.tools.skills` and
`brain.tools.review` called directly.

The repository and the address answer from `tests/fixtures/skill_sources.py`, which records the
shapes GitHub documents and never contacts it. Every archive here is built in memory by `tarfile`
the way `git archive` builds one, so the reader is tested against the shape it will meet rather
than against a dictionary written to suit it.

**Every refusal has a sibling proving the permitted case goes through**, for CLAUDE.md's rule about
a guard tested only by its refusals.

Task ids: M12.2.1, M12.2.2, M12.2.3, M12.2.4, M12.2.6, M12.3.2, M12.4.12, M12.4.13
"""

from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

from brain.console import skill_library as library_module
from brain.console.skill_library import (
    MAX_ADDRESS_CHARS,
    MAX_CATEGORIES,
    LibrarySkill,
    SkillLibraryError,
    added,
    categories_from,
    chips,
    compared_with,
    decided,
    edited,
    github_source,
    read_github,
    read_package,
    read_url,
    url_source_problem,
)
from brain.tools.review import LineChange, content_diff
from brain.tools.skills import (
    A_DESCRIPTION_OPENS_BY_SAYING_WHEN_THE_SKILL_IS_USED,
    Skill,
    SkillError,
    SkillSource,
    SkillState,
    SourceKind,
    markdown_of,
    says_when_it_is_used,
    skill_from_markdown,
    version_key,
)
from tests.fixtures.skill_sources import (
    COMMIT,
    FOLDER,
    OWNER,
    REPOSITORY,
    REPOSITORY_ARCHIVE,
    SKILL_TEXT,
    raw_url,
    tarball,
)
from tests.unit.test_skill_library import IMPORTER, REVIEWER, SKILL_MD, text_with

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)

EDITOR = "u_editor"


def from_repository(archive: bytes = REPOSITORY_ARCHIVE, path: str = FOLDER) -> LibrarySkill:
    source = github_source(f"{OWNER}/{REPOSITORY}", COMMIT, path)
    return added(read_github(source, archive), by=IMPORTER, at=NOW)


def pasted(text: str = SKILL_MD, *, at: datetime = NOW) -> LibrarySkill:
    return added(read_package("SKILL.md", text.encode("utf-8")), by=IMPORTER, at=at)


# ---------------------------------------------------------------- from a repository (M12.2.2)
def test_a_skill_is_read_from_one_folder_of_one_commit_and_pinned_to_both() -> None:
    """**M12.2.2.** The `SKILL.md` in the folder asked for, at the commit asked for, arrives
    undecided with a source naming the repository, the commit, the folder and a digest of the
    exact bytes read; the licence beside it is left where it is rather than refusing the import.

    Delete this and a repository import can land a skill whose source names no commit, so the
    reviewer approved "whatever the branch said that day", or can refuse every real repository for
    carrying a licence."""
    one = from_repository()

    assert one.imported.state is SkillState.IMPORTED
    assert one.imported.skill == skill_from_markdown(SKILL_TEXT)
    source = one.imported.source
    assert source.kind is SourceKind.GITHUB
    assert (source.location, source.commit, source.path) == (
        f"{OWNER}/{REPOSITORY}",
        COMMIT,
        FOLDER,
    )
    assert source.content_digest == hashlib.sha256(SKILL_TEXT.encode("utf-8")).hexdigest()
    assert one.submitted_by == IMPORTER


def test_the_top_folder_is_read_when_no_folder_is_named_and_a_slash_is_forgiven() -> None:
    """A repository holding one skill keeps its `SKILL.md` at the top; a folder copied with a
    trailing slash is the same folder. Delete this and both common spellings of an import fail."""
    at_top = tarball({"SKILL.md": SKILL_TEXT.encode("utf-8")})

    assert from_repository(at_top, "").imported.source.path == ""
    assert github_source(f"{OWNER}/{REPOSITORY}", COMMIT, f"/{FOLDER}/").path == FOLDER


@pytest.mark.parametrize(
    ("archive", "path", "refusal"),
    [
        (REPOSITORY_ARCHIVE, "skills/missing", "no SKILL.md in the folder 'skills/missing'"),
        (
            tarball({"x.txt": b"x"}, links={f"{FOLDER}/SKILL.md": "/etc/passwd"}),
            FOLDER,
            "is not a regular file",
        ),
        (gzip.compress(b"not a tar archive at all" * 40), FOLDER, "not a tar archive"),
        (b"plain bytes", FOLDER, "not a gzip stream"),
    ],
    ids=["no skill there", "a symlink named SKILL.md", "gzip but not tar", "not gzip"],
)
def test_a_repository_archive_without_a_regular_skill_md_there_is_refused_saying_why(
    archive: bytes, path: str, refusal: str
) -> None:
    """Delete this and a symlink named `SKILL.md` is followed to wherever its author pointed it, or
    an archive that is not one raises from the library rather than refusing in words."""
    with pytest.raises(SkillLibraryError, match=refusal):
        from_repository(archive, path)


def test_an_archive_with_more_than_one_top_folder_is_not_a_commit_s_archive() -> None:
    """A commit's archive has exactly one top folder. Delete this and a crafted archive with a
    second tree could put a different `SKILL.md` where the path resolves."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for top in ("one", "two"):
            member = tarfile.TarInfo(f"{top}/SKILL.md")
            data = SKILL_TEXT.encode("utf-8")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))

    with pytest.raises(SkillLibraryError, match="not one folder"):
        from_repository(buffer.getvalue(), "")


def test_an_archive_that_inflates_past_the_ceiling_is_refused_before_a_member_is_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ceiling is on the inflated bytes, which is what a bomb is made of. The ceiling is
    lowered for the test, since the real one is sixty-four megabytes of zeros.

    Delete this and a small tarball inflating to gigabytes is read into memory whole."""
    monkeypatch.setattr(
        library_module, "MAX_UNPACKED_BYTES", len(gzip.decompress(REPOSITORY_ARCHIVE))
    )
    bomb = tarball({f"{FOLDER}/SKILL.md": SKILL_TEXT.encode("utf-8"), "pad.bin": bytes(10**6)})

    with pytest.raises(SkillLibraryError, match="inflates past"):
        from_repository(bomb)
    assert from_repository(REPOSITORY_ARCHIVE).name == "hosting-expiry"


@pytest.mark.parametrize(
    ("repository", "commit", "path", "refusal"),
    [
        ("not a repository", COMMIT, "", "not owner/repo"),
        (f"{OWNER}/{REPOSITORY}", "main", "", "not a full commit sha"),
        (f"{OWNER}/{REPOSITORY}", COMMIT[:12], "", "not a full commit sha"),
        (f"{OWNER}/{REPOSITORY}", COMMIT, "skills/../../etc", "not a folder name"),
    ],
    ids=["repository", "branch", "short sha", "dot dot"],
)
def test_a_source_that_could_move_or_escape_is_refused_before_anything_is_fetched(
    repository: str, commit: str, path: str, refusal: str
) -> None:
    """`github_source` is asked before the fetch, so a branch, a short sha or a path climbing out
    of the repository costs no connection. Delete this and a branch name is fetched and approved
    as if it were a commit."""
    with pytest.raises(SkillLibraryError, match=refusal):
        github_source(repository, commit, path)
    assert github_source(f"{OWNER}/{REPOSITORY}", COMMIT.upper(), ".claude/skills/x").commit == (
        COMMIT
    )


def test_a_repository_skill_carries_the_scripts_it_declares_and_is_refused_without_them() -> None:
    """**M12.4.11 from a repository.** A `SKILL.md` declaring a script the folder holds is read
    with the sha256 of that script's bytes, which its digest covers; one declaring a script the
    folder does not hold is refused, as an upload missing it is. A readme beside it is left unread.

    Delete this and a repository import stores a skill whose script nobody's approval covers, or
    refuses every repository skill with a script, which the upload path now admits."""
    scripted = SKILL_TEXT.replace("tools: [", "scripts: [run.py]\ntools: [")

    with pytest.raises(SkillLibraryError, match="declares the scripts"):
        from_repository(tarball({f"{FOLDER}/SKILL.md": scripted.encode("utf-8")}))
    read = from_repository(
        tarball(
            {
                f"{FOLDER}/SKILL.md": scripted.encode("utf-8"),
                f"{FOLDER}/run.py": b"print('expiry')\n",
                f"{FOLDER}/README.md": b"not part of the skill",
            }
        )
    )

    assert [(one.path, one.sha256) for one in read.imported.skill.script_files] == [
        ("run.py", hashlib.sha256(b"print('expiry')\n").hexdigest())
    ]
    assert read.scripts == {"run.py": b"print('expiry')\n"}


# -------------------------------------------------------------------- from an address (M12.2.3)
def test_an_address_answering_a_skill_md_is_pinned_to_the_bytes_it_answered() -> None:
    """**M12.2.3.** Delete this and a URL import records no digest, so a later fetch returning
    other words cannot be told from the words that were approved."""
    body = SKILL_TEXT.encode("utf-8")
    package = read_url(raw_url(), body)

    assert package.skill == skill_from_markdown(SKILL_TEXT)
    assert package.source == SkillSource(
        kind=SourceKind.URL, location=raw_url(), content_digest=hashlib.sha256(body).hexdigest()
    )


def test_an_address_answering_a_zip_is_read_as_a_package_and_a_tarball_is_sent_elsewhere() -> None:
    """The bytes decide, never the address. Delete this and a zip at an address is parsed as text
    and refused as not UTF-8, or a repository tarball at an address is read with no commit."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SKILL.md", SKILL_TEXT)

    assert read_url(raw_url("skill.zip"), buffer.getvalue()).skill.name == "hosting-expiry"
    with pytest.raises(SkillLibraryError, match="by its name and a commit"):
        read_url(raw_url("archive.tar.gz"), REPOSITORY_ARCHIVE)


def test_an_address_that_is_not_https_or_is_longer_than_a_source_holds_is_refused_first() -> None:
    """Asked before the fetch. Delete this and an address the source would refuse after the fetch
    costs a connection to find out, or an http address is attempted at all."""
    assert url_source_problem(raw_url()) is None
    assert url_source_problem("http://raw.githubusercontent.com/x") is not None
    assert url_source_problem("https://raw.githubusercontent.com/" + "a" * MAX_ADDRESS_CHARS)
    declared = next(
        one.max_length
        for one in SkillSource.model_fields["location"].metadata
        if hasattr(one, "max_length")
    )
    assert declared == MAX_ADDRESS_CHARS


# ------------------------------------------------------------------ the description (M12.4.12)
@pytest.mark.parametrize(
    "description",
    [
        "Use when a client asks whether their domain is about to expire",
        "use WHEN   a ticket mentions renewal",
        "Use this skill when an invoice is overdue",
        "When a client asks for a quote",
        "Use if the hosting panel reports an error",
    ],
)
def test_a_description_that_opens_by_saying_when_is_read(description: str) -> None:
    """The permitted half of the rule. Delete this and a rule refusing every description passes
    the refusals below."""
    skill = skill_from_markdown(text_with(description=description))

    assert skill.description == description


@pytest.mark.parametrize(
    "description",
    [
        "Checks whether a client domain is close to renewal",
        "Use for hosting expiry",
        "Use when",
        "Whenever",
        "Usewhen a client asks",
    ],
)
def test_a_description_that_does_not_open_by_saying_when_is_refused(description: str) -> None:
    """**M12.4.12.** A description is the router's whole choice, so one opening on what the skill
    does, or on a subject, or on the bare words with no moment after them, is refused by the parser
    every import goes through.

    Delete this and skills are chosen between by position, which is the failure the router
    convention exists to prevent."""
    with pytest.raises(SkillError, match="does not open by saying when"):
        skill_from_markdown(text_with(description=description))
    assert not says_when_it_is_used(description)


def test_the_description_rule_is_stated_with_an_example_that_satisfies_it() -> None:
    """The reason quotes an example description, and the example has to pass the rule it
    illustrates. Delete this and the constant can teach a form the parser refuses."""
    example = A_DESCRIPTION_OPENS_BY_SAYING_WHEN_THE_SKILL_IS_USED.split("as in '")[1].split("'")[0]

    assert says_when_it_is_used(example)


# ------------------------------------------------------------------------ editing (M12.3.2)
def edit_of(one: LibrarySkill, **lines: str) -> str:
    return text_with(**({"version": "1.1.0"} | lines)).replace(
        "Look up the domain, then open a ticket.", "Look up the domain, then call the client."
    )


def test_an_edit_is_a_new_undecided_version_naming_the_one_it_came_from() -> None:
    """**M12.3.2.** Delete this and an edit can overwrite the approved version, or arrive already
    approved, or lose the record of which version it was made from."""
    approved = decided(pasted(), reviewer=REVIEWER, approve=True, at=NOW)

    new = edited(approved, edit_of(approved), by=EDITOR, at=LATER, library=(approved,))

    assert new.imported.state is SkillState.IMPORTED
    assert new.edited_from == approved.digest
    assert new.digest != approved.digest
    assert (new.submitted_by, new.submitted_at) == (EDITOR, LATER)
    assert new.imported.skill.version == "1.1.0"
    assert new.imported.source.kind is SourceKind.UPLOAD
    assert approved.imported.is_executable()


@pytest.mark.parametrize(
    ("lines", "refusal"),
    [
        ({"name": "hosting-renewal"}, "is a new skill"),
        ({"version": "1.0.0"}, "version later than 1.0.0"),
        ({"version": "0.9.0"}, "version later than 1.0.0"),
        ({"description": "Checks domains"}, "does not open by saying when"),
    ],
    ids=["rename", "same version", "earlier version", "description rule"],
)
def test_an_edit_that_renames_goes_back_or_breaks_a_rule_is_refused(
    lines: dict[str, str], refusal: str
) -> None:
    """An edit is held to every rule an import is, and to two of its own. Delete this and an edit
    can rename a skill into another's approval, or reuse a version number for different words."""
    one = pasted()

    with pytest.raises(SkillLibraryError, match=refusal):
        edited(one, edit_of(one, **lines), by=EDITOR, at=LATER, library=(one,))


def test_an_edit_that_changes_nothing_or_reuses_a_held_version_is_refused() -> None:
    """Delete this and the library holds two identical versions, or two different procedures under
    one number."""
    one = pasted()
    already = pasted(edit_of(one), at=LATER)

    with pytest.raises(SkillLibraryError, match="is the same as"):
        edited(one, SKILL_MD, by=EDITOR, at=LATER, library=(one,))
    with pytest.raises(SkillLibraryError, match=r"already holds 'hosting-expiry' 1\.1\.0"):
        edited(
            one,
            edit_of(one).replace("call the client", "email the client"),
            by=EDITOR,
            at=LATER,
            library=(one, already),
        )


def test_the_markdown_an_edit_starts_from_reads_back_as_the_skill() -> None:
    """The console offers this text to edit. Delete this and an unchanged edit is a different
    skill, or a description opening with a bracket is offered as text that parses as a list."""
    skill = skill_from_markdown(SKILL_TEXT)

    assert skill_from_markdown(markdown_of(skill)) == skill
    with pytest.raises(SkillError, match="does not read back"):
        markdown_of(skill.model_copy(update={"description": "[draft] Use when"}))


def test_a_later_version_is_later_by_number_and_not_by_text() -> None:
    """Delete this and 1.10.0 reads as earlier than 1.9.0, so an edit bumping the minor version
    past nine is refused as going backwards."""
    assert version_key("1.10.0") > version_key("1.9.0")
    with pytest.raises(SkillError):
        version_key("1.0")


# ------------------------------------------------------------- the words that changed (M12.2.6)
def test_the_diff_is_the_old_body_and_the_new_body_line_by_line_with_fields_before_and_after() -> (
    None
):
    """**M12.2.6.** Kept and removed lines are exactly the old body, kept and added exactly the new,
    in order; each changed frontmatter field is named with both values.

    Delete this and the review pane can show a diff that drops a line, so a reviewer approves an
    edit whose one altered sentence never appeared on their screen."""
    old = skill_from_markdown(SKILL_MD)
    new = skill_from_markdown(
        text_with(version="1.1.0", tools="[crm.read_client]").replace(
            "Look up the domain, then open a ticket.",
            "Look up the domain.\nThen email every client their contract value.",
        )
    )

    diff = content_diff(old, new)

    assert diff.old_body() == tuple(old.body.split("\n"))
    assert diff.new_body() == tuple(new.body.split("\n"))
    assert [(line.change, line.text) for line in diff.body] == [
        (LineChange.REMOVED, "Look up the domain, then open a ticket."),
        (LineChange.ADDED, "Look up the domain."),
        (LineChange.ADDED, "Then email every client their contract value."),
    ]
    assert [(one.field, one.before, one.after) for one in diff.fields] == [
        ("version", "1.0.0", "1.1.0"),
        ("tools", "crm.read_client, desk.read_ticket", "crm.read_client"),
    ]
    assert diff.body_changed


def test_an_unchanged_body_is_every_line_kept_and_no_field_named() -> None:
    """The sibling of the one above. Delete this and a diff that marks everything changed passes
    it, which is a review pane that says nothing about what moved."""
    skill = skill_from_markdown(SKILL_TEXT)

    diff = content_diff(skill, skill)

    assert diff.fields == ()
    assert {line.change for line in diff.body} == {LineChange.KEPT}
    assert not diff.body_changed


def test_a_version_is_compared_with_the_newest_approved_before_it_or_else_its_parent() -> None:
    """What the review pane diffs against. Delete this and an edit is compared with itself, with a
    version added after it, or with nothing when an approved version exists."""
    first = decided(pasted(), reviewer=REVIEWER, approve=True, at=NOW)
    second = edited(first, edit_of(first), by=EDITOR, at=LATER, library=(first,))
    third = edited(
        second,
        edit_of(second, version="1.2.0").replace("call the client", "email the client"),
        by=EDITOR,
        at=LATER + timedelta(hours=1),
        library=(first, second),
    )
    library = (first, second, third)

    assert compared_with(first, library) is None
    assert compared_with(second, library) == first
    assert compared_with(third, library) == first
    lone = edited(pasted(), edit_of(pasted()), by=EDITOR, at=LATER, library=())
    assert compared_with(lone, (pasted(), lone)) == pasted()


# --------------------------------------------------------------------- categories (M12.4.13)
def test_categories_are_folded_deduplicated_and_sorted() -> None:
    """**M12.4.13.** Delete this and "Web maintenance" and "web-maintenance" are two chips, or a
    trailing comma is refused as a category."""
    assert categories_from(["Web maintenance", "web-maintenance", " SEO ", ""]) == (
        "seo",
        "web-maintenance",
    )
    assert categories_from([]) == ()


@pytest.mark.parametrize(
    ("typed", "refusal"),
    [
        (["finance/quotes"], "is not one this install keeps"),
        (["-leading"], "is not one this install keeps"),
        (["a" * 41], "is not one this install keeps"),
        ([f"c{n}" for n in range(MAX_CATEGORIES + 1)], f"at most {MAX_CATEGORIES}"),
    ],
    ids=["slash", "leading hyphen", "too long", "too many"],
)
def test_a_category_outside_the_grammar_or_one_too_many_is_refused(
    typed: list[str], refusal: str
) -> None:
    """Delete this and a category can carry a path or a sentence into a filter chip, or a skill
    can be filed in every category, which is filed in none."""
    with pytest.raises(SkillLibraryError, match=refusal):
        categories_from(typed)
    assert len(categories_from([f"c{n}" for n in range(MAX_CATEGORIES)])) == MAX_CATEGORIES


def test_chips_are_drawn_only_from_the_skills_the_reader_was_shown() -> None:
    """A category only a hidden skill carries is never a chip. Delete this and the filter names the
    filing of a skill the reader may not see, which is a fact about it they did not have."""
    filed = {"hosting-expiry": ("hosting", "seo"), "payroll-run": ("finance", "hr")}

    assert chips(filed, ["hosting-expiry"]) == ("hosting", "seo")
    assert chips(filed, ["hosting-expiry", "payroll-run"]) == ("finance", "hosting", "hr", "seo")
    assert chips(filed, []) == ()


def test_a_skill_carries_no_category_in_its_digest() -> None:
    """A label is not a procedure. Delete this and somebody adds categories to `Skill`, so that
    filing an approved skill sends it back to review."""
    assert "categories" not in Skill.model_fields
