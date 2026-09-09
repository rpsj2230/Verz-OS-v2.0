"""The archive a client receives, and the three things its notes have to say.

Two halves and they fail for different people. The archive half is about what leaves this
repository: a path the install reads and the archive lacks is an install that stops on
somebody else's server, and a path the archive carries and a refusal names is this
repository arriving on it. The notes half is about what a client is told: the one field
nobody may type is whether the release changes their database, so every test here builds the
answer from migration source rather than from a verdict somebody handed it.

**Every refusal is exercised against a declaration built to fail as well as against the real
one.** That is `tests/unit/test_install_docs.py`' argument restated and the reason
`archive_gaps`, `carried_paths` and `refused_by` all take their inputs: a check that can only
be run against the healthy declaration has no test for the case it exists to find, and
`brain.ops.starter.starter_gaps` records what that costs, two refusals surviving a mutation
run because no test could hand them a bad case.

Named `test_deployment_release.py` rather than `test_release.py`, which is already taken by
`brain.release` and its wave tags. The package convention is the answer: every other module
under `brain.deployment` is tested in a file named after it.

Task ids: M42.3.8
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.deployment.installer import INSTALL_HOME, PLAN, Step
from brain.deployment.release import (
    A_BREAKING_SCHEMA_CHANGE_IS_NEVER_ROUTINE,
    EXCLUDED,
    INCLUDED,
    URGENCY,
    DatabaseChange,
    Level,
    ReleaseError,
    ReleaseNotes,
    Rule,
    Urgency,
    archive_files,
    archive_gaps,
    carried_paths,
    compose_documents,
    database_change,
    included_by,
    install_needs,
    mounts_in,
    notes_from_tag_message,
    paths_the_install_reads,
    refused_by,
    rollback_change,
)
from brain.deployment.requirements import files_for
from brain.ops.compose import relative_bind_mounts
from brain.ops.wiring import PROFILES

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "release.yml"


# ------------------------------------------------------------------ migration fixtures
#: A migration that only adds. Safe in both directions, which is what most releases are.
ADDITIVE = '''"""An ordinary index."""

revision = "0097"
down_revision = "0096"


def upgrade() -> None:
    op.create_index("ix_thing_a", "thing", ["a"], schema="core")


def downgrade() -> None:
    op.drop_index("ix_thing_a", "thing", schema="core")
'''

#: A migration that takes a column away, which the release before it still selects.
REMOVES_A_COLUMN = '''"""A column goes."""

revision = "0099"
down_revision = "0098"


def upgrade() -> None:
    op.drop_column("thing", "old_column", schema="core")


def downgrade() -> None:
    op.add_column("thing", sa.Column("old_column", sa.Text(), nullable=True), schema="core")
'''

#: A migration whose one operation no reading of the source can order.
CANNOT_BE_READ = '''"""A type changes."""

revision = "0096"
down_revision = "0095"


def upgrade() -> None:
    op.alter_column("thing", "a", type_=sa.String(10), schema="core")


def downgrade() -> None:
    op.alter_column("thing", "a", type_=sa.String(64), schema="core")
'''


def a_step(**changes: Any) -> Step:
    """One install step, so a test can change exactly the thing it is about."""
    values: dict[str, Any] = {
        "name": "do the thing",
        "run": "true",
        "why": "because otherwise the thing is not done",
        "on_failure": "run it again",
        "changes": False,
    }
    values.update(changes)
    return Step(**values)


def a_tree(root: Path, files: dict[str, str]) -> Path:
    """A throwaway tree with these files in it, parents created."""
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return root


# ================================================================= the declaration itself
def test_every_rule_in_the_declaration_says_why_it_is_there() -> None:
    """A pattern with no reason is a line the next reader either deletes while tidying or
    copies while adding, and both are decisions nobody made. It is the same requirement
    `brain.ops.starter.Default` puts on a default.

    Delete this and the include list becomes a list of paths, which is exactly the artefact
    that cannot be reviewed."""
    for rule in (*INCLUDED, *EXCLUDED):
        assert rule.why.strip(), rule.pattern
        assert rule.pattern.strip(), rule.why

    with pytest.raises(ReleaseError, match="no reason"):
        Rule("ops/somewhere", "  ")
    with pytest.raises(ReleaseError, match="matches nothing"):
        Rule("", "a rule with no pattern")


def test_the_archive_carries_every_compose_file_a_profile_composes() -> None:
    """The include list is derived from `files_for` rather than typed, so a ninth compose file
    added to a profile is in the archive the same day. Typed, it would be in the archive on the
    day somebody remembered, and the failure is a client running `docker compose -f` against a
    file that is not there.

    Both directions of the same fact are asserted, because they are two derivations and only
    one of them is the archive: `included_by` says the file is carried, and `install_needs` says
    the install would be missing it if it were not. A check with only the first would pass with
    the second returning nothing, which is a gaps check that has stopped asking about compose
    files at all.

    Delete this and the derivation can be replaced with a hand-written list that is right
    today."""
    needed = install_needs()
    for profile in PROFILES:
        for name in files_for(profile):
            assert included_by(name), f"{name} is composed by {profile} and not carried"
            assert name in needed, f"{name} is composed by {profile} and the check does not ask"


def test_the_archive_carries_no_history_no_workflow_and_no_source() -> None:
    """**The refusal this whole module exists for.** A client must never receive a copy of this
    repository: three commits in its history carry the first deployment's host and address in
    files that have since been cleaned, and a commit cannot be un-made. The archive is the
    structural answer, and it is only an answer if these are refused.

    Delete this and `.github` becomes carriable, which puts this deployment's registry, machine
    and signing identity on every client's server, and nothing else in the suite would say
    so."""
    refused = {
        ".git/config": "the history",
        ".github/workflows/ci.yml": "this repository's own pipeline",
        ".scratch/mutate.py": "agent scratch nothing sweeps",
        "tests/invariants/test_company_canaries.py": "the suite and its canaries",
        "src/brain/app.py": "a second copy of the product",
        "console/src/main.tsx": "the front end, which is built into the image",
        "docs/needs-rupash.md": "the owner's decision list",
        ".env": "one install's own credentials",
        "ops/keycloak/private.key": "a private key, inside a carried directory",
    }
    for path, what in refused.items():
        assert refused_by(path), f"{path} is carried and it is {what}"


def test_a_file_the_archive_carries_is_not_also_refused() -> None:
    """The positive half. A refusal list that refused everything would pass the test above and
    publish an empty archive, and an empty archive fails on the client's server rather than
    here.

    Delete this and a refusal broad enough to match `docs/install` or a compose file ships a
    tarball with nothing in it."""
    for path in (".env.example", "docker-compose.yml", "docs/install/install.md", "alembic.ini"):
        assert included_by(path), path
        assert not refused_by(path), path


def test_widening_an_include_still_cannot_get_a_refused_path_into_the_archive(
    tmp_path: Path,
) -> None:
    """None of the refusals is reachable from today's include list, which is the design and not
    an argument that the list is decoration: the refusals are the net under a widened include.
    This is the test that proves the net is there, by widening one.

    Delete this and the refusals become a comment. Somebody widens an include to fix a missing
    file, the workflow goes green, and the archive carries the history."""
    tree = a_tree(
        tmp_path,
        {
            ".github/workflows/ci.yml": "name: CI\n",
            ".github/keep.md": "kept\n",
        },
    )
    widened = (Rule(".github", "somebody widened this to fix a missing file"),)

    assert carried_paths(tree, widened) == (".github/keep.md", ".github/workflows/ci.yml")
    assert archive_files(tree, widened) == ()
    assert len(archive_gaps(carried=carried_paths(tree, widened), needed=(), client_values=())) == 2


def test_compiled_bytecode_is_not_a_file_of_this_repository(tmp_path: Path) -> None:
    """`migrations/versions/__pycache__` exists on every machine that has run the suite, and
    the archive carries the migrations. Refusing the bytecode afterwards would make the
    deployment check red on every developer's tree and in CI, so it is skipped while walking
    instead, which is the distinction `brain.ops.independence._searched_files` already makes.

    Delete this and the walk starts carrying one machine's compiled bytecode, or the check goes
    red everywhere and gets switched off."""
    tree = a_tree(
        tmp_path,
        {
            "migrations/versions/0001_x.py": "revision = '0001'\n",
            "migrations/versions/__pycache__/0001_x.cpython-313.pyc": "not text\n",
        },
    )
    assert carried_paths(tree, (Rule("migrations", "the evidence"),)) == (
        "migrations/versions/0001_x.py",
    )


# ==================================================== what the install expects to be there
def test_the_environment_template_is_the_one_file_the_plan_reads_from_the_archive() -> None:
    """Read out of the plan rather than listed, so a step that starts reading a second file is
    a second file the archive owes it. The tarball the install downloads, the RELEASE marker it
    writes and the environment file it creates are all under the same directory and none of
    them is the archive's to carry.

    Delete this and the derivation can quietly start counting written files as needed ones,
    which reads as the archive being incomplete and sends somebody looking for a file nobody
    ships."""
    assert paths_the_install_reads(PLAN) == (".env.example",)


def test_a_file_a_step_starts_reading_becomes_a_file_the_archive_owes_it() -> None:
    """The case the real plan cannot exercise, because today it reads one file. A step reading
    a second one is exactly the change that would break a client's install six months from now.

    Delete this and `paths_the_install_reads` could return a constant tuple and pass."""
    plan = (
        a_step(name="check", run=f'test -f "{INSTALL_HOME}/ops/newthing/limits.conf"'),
        *PLAN,
    )
    assert "ops/newthing/limits.conf" in paths_the_install_reads(plan)


def test_a_file_the_install_writes_is_not_one_the_archive_owes_it() -> None:
    """Three spellings, because the plan writes in three ways: a redirect, curl's output flag
    and the destination half of a copy. A reader that missed one would report the archive as
    missing a file the install creates, which is a finding nobody can act on and the fastest
    way to get a check ignored.

    Delete this and the written set can stop being computed, and the deployment check reports
    three files that must never be in an archive."""
    plan = (
        a_step(
            name="write things",
            changes=True,
            already_done=f'test -f "{INSTALL_HOME}/marker"',
            run=(
                f'curl -fsSL "$URL" -o "{INSTALL_HOME}/fetched.tar.gz"\n'
                f'printf "x" > "{INSTALL_HOME}/marker"\n'
                f'cp "{INSTALL_HOME}/template.conf" "{INSTALL_HOME}/live.conf"\n'
                f'cat "{INSTALL_HOME}/fetched.tar.gz" "{INSTALL_HOME}/live.conf"'
            ),
        ),
    )
    assert paths_the_install_reads(plan) == ("template.conf",)


def test_every_relative_bind_mount_is_a_path_the_archive_carries() -> None:
    """The failure that is silent on the client's server. A compose file mounting `./ops/x` on
    a server where the archive did not carry `ops/x` does not fail: docker creates an empty
    directory there and starts the container, so a memory ceiling, an egress allowlist and a
    set of object-store credentials go missing with every health check green.

    Delete this and a fifth mount added to a compose file is a silently misconfigured container
    on somebody else's machine, found by nobody."""
    mounts = mounts_in(compose_documents())

    assert mounts, "no bind mounts were read at all, so this test is watching nothing"
    for one in mounts:
        assert one in install_needs(), one
        assert included_by(one), f"{one} is bind-mounted and the archive does not carry it"


def test_the_two_readers_of_the_bind_mounts_agree() -> None:
    """`brain.ops.compose.relative_bind_mounts` answers the operator's question as sentences and
    this answers the archive's as paths. Two readers of one thing is how they come to disagree,
    so the agreement is asserted rather than assumed.

    Delete this and one of the two can stop seeing a mount, which shows up as an archive that
    is complete by its own arithmetic."""
    documents = compose_documents()
    reported = relative_bind_mounts(documents)

    for one in mounts_in(documents):
        assert any(one in sentence for sentence in reported), f"{one} is seen by only one reader"
    assert len(reported) == len(
        [
            source
            for name in documents
            for body in dict(documents[name].get("services") or {}).values()
            for source in (body.get("volumes") or ())
            if str(source).startswith((".", "~"))
        ]
    )


# ===================================================================== the three refusals
def test_the_archive_this_repository_would_publish_has_nothing_wrong_with_it() -> None:
    """The deployment check, run with no arguments, which is what the release workflow runs
    before it builds anything. Every refusal below is exercised against a constructed case, and
    a suite of those alone would pass with the real declaration broken.

    Delete this and the archive can drift away from the install plan with every refusal test
    still green."""
    assert archive_gaps() == ()


def test_a_path_the_install_reads_and_the_archive_lacks_is_a_finding() -> None:
    """The first refusal. It is the one that fails on a server nobody here can see, so the
    finding names the path under the install directory rather than the repository, which is
    where the person reading it is standing.

    Delete this and the archive can stop carrying the environment template and the release
    still publishes."""
    findings = archive_gaps(
        carried=("docker-compose.yml",), needed=(".env.example",), client_values=()
    )

    assert len(findings) == 1
    assert findings[0].startswith(".env.example: ")
    assert f"{INSTALL_HOME}/.env.example" in findings[0]


def test_a_path_the_archive_carries_and_a_refusal_names_is_a_finding() -> None:
    """The second refusal, and it is reported rather than silently dropped. A build that
    quietly filtered the path would go green on the day somebody widened an include, which is
    the one day anybody wants to be told.

    Delete this and widening an include to `.github` publishes a green release with this
    deployment's pipeline in it."""
    findings = archive_gaps(carried=(".github/workflows/deploy.yml",), needed=(), client_values=())

    assert len(findings) == 1
    assert ".github/workflows/deploy.yml" in findings[0]
    assert "refused by" in findings[0]


def test_a_client_value_in_a_carried_file_is_a_finding() -> None:
    """The third refusal, and it is the question the independence sweep does not ask. That
    sweep asks whether a value is in the repository; this asks whether the file it is in gets
    handed to somebody else's company, which is the same value arriving by the one route the
    gate does not check.

    Delete this and a host in a carried runbook reaches every client who installs after it."""
    findings = archive_gaps(
        carried=("ops/openbao/UNSEAL.md",),
        needed=(),
        client_values=("ops/openbao/UNSEAL.md:12: a client host, 'brain.somewhere.example'",),
    )

    assert len(findings) == 1
    assert findings[0].startswith("ops/openbao/UNSEAL.md: ")
    assert "every other client" in findings[0]


def test_a_client_value_in_a_file_the_archive_does_not_carry_is_not_a_finding() -> None:
    """The positive half of the third refusal, and the reason it is not a second copy of the
    sweep. This repository's own workflows carry this deployment's address today and are pinned
    as doing so by `test_deployment_audit.py`; none of it is in the archive, and a check that
    reported them here would be red on arrival and switched off.

    Delete this and the finding becomes a duplicate of a gate that already runs, which is the
    shape `tests/invariants/test_single_implementation.py` exists to refuse."""
    assert (
        archive_gaps(
            carried=("docs/install/install.md",),
            needed=(),
            client_values=(".github/workflows/deploy.yml:3: a client host, 'x.example.org'",),
        )
        == ()
    )


# ============================================== whether the release changes the database
def test_a_release_carrying_no_migration_says_it_does_not_change_the_database() -> None:
    """The common case and the one a client acts on most often: no migration means the update
    is a container swap and there is no database decision to make on the way back either.

    Delete this and every release can report a schema change, which is the direction that gets
    a notes field ignored rather than the direction that costs somebody data."""
    notes = ReleaseNotes(
        tag="v0.1.0", what_changed=("Approvals load faster",), urgency=Urgency.ROUTINE
    )

    assert notes.database is DatabaseChange.NONE
    assert notes.going_back is DatabaseChange.NONE
    assert "does not change your database" in notes.render()


def test_whether_it_changes_the_database_is_derived_and_there_is_no_field_to_type_it_in() -> None:
    """**The requirement M42.3.8 turns on.** A person typing "no schema change" on a release
    that has one is the failure the field exists to prevent, so there is no field: the answer is
    a property computed from the migrations the release carries, and the only way to publish the
    wrong one is to publish a release that does not contain the migration it contains.

    Delete this and somebody adds a `database=` argument for the one release where the reading
    is inconvenient, which is the release it matters on."""
    assert "database" not in ReleaseNotes.__dataclass_fields__
    assert "going_back" not in ReleaseNotes.__dataclass_fields__

    notes = ReleaseNotes(
        tag="v0.2.0",
        what_changed=("A column nobody was using is gone",),
        urgency=Urgency.IMPORTANT,
        migrations={"0099_x.py": REMOVES_A_COLUMN},
    )

    assert notes.database is DatabaseChange.BREAKING
    assert "does not change your database" not in notes.render()
    assert "cannot use" in notes.render()


def test_a_release_that_only_adds_is_one_the_previous_release_can_still_run_against() -> None:
    """Read from migration source rather than from a verdict handed to the check, because a
    test that builds the value the function produces has tested nothing. This one is additive
    in both directions, which is what most releases are and what the notes have to be able to
    say without alarming anybody.

    Delete this and the fold can answer breaking for everything and still pass its refusal
    tests, which is a client taking a window for a release that needed none."""
    migrations = {"0097_x.py": ADDITIVE}

    assert database_change(migrations) is DatabaseChange.COMPATIBLE
    assert rollback_change(migrations) is DatabaseChange.COMPATIBLE


def test_the_direction_is_asked_by_swapping_the_two_arguments_of_one_reader() -> None:
    """`0022` in this repository widens a check constraint, so the new schema accepts everything
    the old code writes and the old schema rejects what the new code writes. Forward it is safe
    and backward it is not, and that asymmetry is the shape of every widening ever written.
    `brain.deployment.compatibility.changes_in` answers both by swapping its two arguments, and
    a second implementation here would be a second answer about the direction nobody tests
    until they need it.

    Delete this and `rollback_change` can be made a copy of `database_change`, and the notes
    tell a client that going back is a tag change on the release where it is not."""
    real = (REPO / "migrations" / "versions" / "0022_compose_change_action.py").read_text(
        encoding="utf-8"
    )
    migrations = {"0022_compose_change_action.py": real}

    assert database_change(migrations) is DatabaseChange.COMPATIBLE
    assert rollback_change(migrations) is DatabaseChange.BREAKING


def test_a_change_the_source_cannot_be_read_for_is_neither_safe_nor_breaking() -> None:
    """Three verdicts rather than two, for the reason `brain.deployment.compatibility` argues:
    folded into safe, an unreadable narrowing ships under a green tick; folded into breaking,
    every release is alarming and the field stops being read. A client reading "part of this
    could not be read from the source" is being told something true that they can act on.

    Delete this and the third answer folds into one of the other two, and which one it folds
    into decides whose Saturday it costs."""
    migrations = {"0096_x.py": CANNOT_BE_READ}

    assert database_change(migrations) is DatabaseChange.UNREADABLE
    assert (
        "could not be read"
        in ReleaseNotes(
            tag="v0.3.0",
            what_changed=("A field holds longer values",),
            urgency=Urgency.IMPORTANT,
            migrations=migrations,
        ).render()
    )


def test_the_worst_migration_in_a_release_is_the_one_the_notes_report() -> None:
    """A release of nine safe migrations and one narrowing needs the window, so the fold takes
    the worst rather than counting. A client acts on the hardest thing in the release.

    Delete this and a release can report the verdict of whichever migration sorted first, which
    on a release with ten of them is arbitrary."""
    assert (
        database_change({"0097_x.py": ADDITIVE, "0099_x.py": REMOVES_A_COLUMN})
        is DatabaseChange.BREAKING
    )
    assert (
        database_change({"0097_x.py": ADDITIVE, "0096_x.py": CANNOT_BE_READ})
        is DatabaseChange.UNREADABLE
    )


# ================================================================ what the notes must say
def test_a_release_that_breaks_the_database_cannot_be_called_routine() -> None:
    """The two fields are written by different halves of the same person and this is the pair
    that has to agree. Routine means install it whenever, which is a client scheduling no window
    and taking no backup, and a release the previous version cannot run against needs both.

    Delete this and the urgency and the database answer can contradict each other in the one
    direction that costs data."""
    with pytest.raises(ReleaseError, match="routine"):
        ReleaseNotes(
            tag="v0.4.0",
            what_changed=("An unused column is gone",),
            urgency=Urgency.ROUTINE,
            migrations={"0099_x.py": REMOVES_A_COLUMN},
        )

    ReleaseNotes(
        tag="v0.4.0",
        what_changed=("An unused column is gone",),
        urgency=Urgency.IMPORTANT,
        migrations={"0099_x.py": REMOVES_A_COLUMN},
    )
    assert "backup" in A_BREAKING_SCHEMA_CHANGE_IS_NEVER_ROUTINE


def test_a_release_stating_nothing_that_changed_is_refused() -> None:
    """A version number with no notes is what M42.3.8 exists to stop being published. A client
    reading it has no way to decide whether to install, so they do not, and the release that
    mattered is behind the four that did not.

    Delete this and an empty notes field publishes, which reads as a release with nothing in
    it rather than as notes nobody wrote."""
    with pytest.raises(ReleaseError, match="states nothing"):
        ReleaseNotes(tag="v0.5.0", what_changed=(), urgency=Urgency.ROUTINE)
    with pytest.raises(ReleaseError, match="empty note line"):
        ReleaseNotes(tag="v0.5.0", what_changed=("   ",), urgency=Urgency.ROUTINE)
    with pytest.raises(ReleaseError, match="names nothing"):
        ReleaseNotes(tag="  ", what_changed=("A thing changed",), urgency=Urgency.ROUTINE)


def test_a_note_naming_a_module_or_a_task_id_is_a_commit_subject_and_is_refused() -> None:
    """A client's IT team has no source tree, no module names and no task ids. A note reading
    "fix leash.py resume path, closes M12.2.4" is a commit subject pasted into the one field
    written for somebody outside this repository, and it reads as coverage: the release has
    notes and nobody can act on them.

    Delete this and the plain-English half of M42.3.8 becomes a field that is filled in, which
    is not the same as a field that is written."""
    for line in (
        "Fixed the resume path in leash.py",
        "Reworked src/brain/gate for speed",
        "Closes M12.2.4 and M12.2.6",
        "Added coverage under tests/unit",
    ):
        with pytest.raises(ReleaseError, match=r"commit subject|names"):
            ReleaseNotes(tag="v0.6.0", what_changed=(line,), urgency=Urgency.ROUTINE)

    ReleaseNotes(
        tag="v0.6.0",
        what_changed=("Approvals no longer time out when the connection is slow",),
        urgency=Urgency.ROUTINE,
    )


def test_every_urgency_carries_an_argument_and_a_rule_about_what_a_client_does() -> None:
    """A level is a word until somebody says what to do about it, and three people read
    "important" three ways. A fourth level added without both is a label a client cannot act
    on, and this is what makes adding one a decision rather than an accident.

    Delete this and an urgency can be added with no rule, and `render` raises on the first
    release that uses it."""
    assert set(URGENCY) == set(Urgency)
    for level in Urgency:
        assert URGENCY[level].urgency is level
        assert URGENCY[level].why.strip()
        assert URGENCY[level].what_a_client_does.strip()
    assert len({URGENCY[one].what_a_client_does for one in Urgency}) == len(Urgency)

    with pytest.raises(ReleaseError, match="no what_a_client_does"):
        Level(urgency=Urgency.ROUTINE, why="because it is", what_a_client_does="")


def test_the_rendered_notes_answer_the_three_questions_the_leaf_asks() -> None:
    """M42.3.8 asks for three things and this is the shape they reach a client in. Headings
    rather than a paragraph, because this is read on the day somebody is deciding whether to
    install now or on Friday, and the database line is the one they scroll for.

    Delete this and the three can drift into one paragraph, and the answer a client needs
    stops being findable."""
    rendered = ReleaseNotes(
        tag="v0.7.0",
        what_changed=("Approvals load for companies with more than two thousand people",),
        urgency=Urgency.SECURITY,
        migrations={"0097_x.py": ADDITIVE},
    ).render()

    assert rendered.startswith("# v0.7.0\n")
    assert "## What changed" in rendered
    assert "## Does this change your database" in rendered
    assert "## How urgent this is" in rendered
    assert "- Approvals load for companies with more than two thousand people" in rendered
    assert "**Security.**" in rendered
    assert "What to do: " in rendered
    assert rendered.endswith("\n")


def test_a_tag_message_with_no_urgency_fails_the_release_rather_than_defaulting() -> None:
    """A default is what makes every release routine, including the one that was not, which is
    the same argument `brain.deployment.installer` makes about a release tag defaulting to
    `latest`. Failing the build is the only moment anybody is still in a position to fix it.

    Delete this and a tag message somebody wrote in a hurry publishes as routine."""
    with pytest.raises(ReleaseError, match="Urgency"):
        notes_from_tag_message("v0.8.0", "- Approvals load faster\n")
    with pytest.raises(ReleaseError, match="not an urgency"):
        notes_from_tag_message("v0.8.0", "Urgency: whenever\n\n- Approvals load faster\n")


def test_a_tag_message_states_the_urgency_and_every_other_line_is_what_changed() -> None:
    """The message is the one part of a release a person writes, so it is read in the shape
    people write one: a header line and a list. The urgency line is removed from what changed,
    because a client reading "Urgency: security" as a thing that changed is reading a field
    name.

    Delete this and the urgency line reappears in the notes as a bullet, or the list markers
    do."""
    notes = notes_from_tag_message(
        "v0.9.0",
        "Urgency: security\n\n- Sessions end when they should\n* Sign-in stops looping\n",
        {"0097_x.py": ADDITIVE},
    )

    assert notes.urgency is Urgency.SECURITY
    assert notes.what_changed == ("Sessions end when they should", "Sign-in stops looping")
    assert notes.database is DatabaseChange.COMPATIBLE


# ================================================================= the workflow, as data
def _workflow() -> dict[Any, Any]:
    """Parsed, never grepped. A substring search over YAML passes on a commented-out line as
    happily as a live one, which is exactly what this file is checking for."""
    parsed: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return parsed


def _run_commands() -> str:
    """Every `run:` in the workflow, concatenated. What the release build actually executes."""
    return "\n".join(
        str(step["run"])
        for job in _workflow()["jobs"].values()
        for step in job.get("steps", [])
        if "run" in step
    )


def test_the_release_workflow_builds_the_archive_on_a_tag() -> None:
    """A release archive published on a branch push is one that exists for a commit nobody can
    ask for by name, and the installer pins a tag. `workflow_dispatch` is beside it so a tag
    that failed to build once can be built again without moving it.

    Delete this and the trigger can become `push: branches` and every commit publishes a
    release."""
    triggers = _workflow()[True]

    assert triggers["push"]["tags"] == ["v*"]
    assert "tag" in triggers["workflow_dispatch"]["inputs"]
    assert _workflow()["permissions"]["contents"] == "write"


def test_the_release_workflow_asks_the_module_for_the_file_list() -> None:
    """**The property that stops the workflow and the tests being two lists.** The archive is
    built from whatever the module prints, so a file the declaration adds is in the next release
    with nobody editing YAML, and a test asserting the declaration is asserting the archive.

    Delete this and somebody replaces the list with `tar --exclude` flags, which is how it is
    usually written, and the exclusions stop being anything a test can read."""
    commands = _run_commands()

    assert 'brain.deployment.release files > "$RUNNER_TEMP/files.txt"' in commands
    assert '-T "$RUNNER_TEMP/files.txt"' in commands
    assert "brain.deployment.release gaps" in commands
    assert "brain.deployment.release notes" in commands
    assert "brain.deployment.release migrations-path" in commands


def test_the_release_workflow_spells_no_path_the_archive_carries_or_refuses() -> None:
    """The other half of the same property, and the half that catches the slow version of the
    failure: a workflow that asks the module for the list and then adds one path of its own is
    a second declaration, and the second one is the one nothing tests.

    Delete this and `--exclude .github` reappears beside the module call, agrees with it for a
    month, and stops agreeing on the day an include is widened."""
    # The module's own invocations are removed first, and the distinction is the whole point:
    # `release migrations-path` is the workflow asking where the migrations live, which is the
    # opposite of spelling the path, and it contains one of the patterns as a substring.
    commands = re.sub(r"brain\.deployment\.release \S+", "", _run_commands())

    for rule in (*INCLUDED, *EXCLUDED):
        if "*" in rule.pattern:
            continue
        assert rule.pattern not in commands, f"{rule.pattern} is spelled in the workflow"


def test_the_release_workflow_refuses_before_it_builds_and_publishes_what_it_built() -> None:
    """Order, which a membership check alone would pass. A client value found after the tarball
    is published is a release to withdraw from servers that have already fetched it; found
    before, it is a red build. And the notes that reach the release are the rendered ones rather
    than the tag message, or the derivation is computed and thrown away.

    Delete this and the gaps step can move below the publish step, which changes nothing about
    whether the workflow passes."""
    steps = [str(one.get("run", "")) for one in _workflow()["jobs"]["archive"]["steps"]]
    order = {
        "gaps": next(i for i, one in enumerate(steps) if "release gaps" in one),
        "tar": next(i for i, one in enumerate(steps) if "tar -czf" in one),
        "publish": next(i for i, one in enumerate(steps) if "gh release create" in one),
    }

    assert order["gaps"] < order["tar"] < order["publish"]
    assert '--notes-file "$RUNNER_TEMP/notes.md"' in steps[order["publish"]]
    assert "--strip-components" not in "\n".join(steps), "the installer strips, not the build"
