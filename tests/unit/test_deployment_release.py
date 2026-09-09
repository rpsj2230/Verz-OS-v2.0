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

**The third half is the two scripts, and its tests run them.** An update and a rollback are
shell, and a test asserting the text of a script is satisfied by a script that will not run, so
every refusal below is exercised by cutting the rendered script at the step under test and
running it against a throwaway directory shaped like an install. What that catches and text
never would: a guard that is inverted, a copy that takes the wrong file, and a second run that
overwrites the one record a rollback has.

Task ids: M42.3.6, M42.3.8
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.deployment.installer import INSTALL_ENV_FILE, INSTALL_HOME, PLAN, Step, step_named
from brain.deployment.release import (
    A_BREAKING_SCHEMA_CHANGE_IS_NEVER_ROUTINE,
    A_ROLLBACK_RE_PINS_THE_CODE_AND_LEAVES_THE_SCHEMA,
    A_ROLLBACK_THAT_GUESSES_IS_WORSE_THAN_ONE_THAT_REFUSES,
    APPLIED_REVISION_QUERY,
    EXCLUDED,
    INCLUDED,
    LATEST_IS_AN_UNPIN_WEARING_AN_UPDATES_CLOTHES,
    NOT_A_RELEASE_TAG,
    PREVIOUS_MARKER,
    RECORDING_THE_PREVIOUS_RELEASE_AFTER_THE_NEW_ONE_RECORDS_THE_NEW_ONE,
    THE_IMAGE_VARIABLE,
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
    image_repository,
    included_by,
    install_needs,
    mounts_in,
    notes_from_tag_message,
    paths_the_install_reads,
    refusal,
    refused_by,
    release_marker,
    render_rollback,
    render_update,
    rollback_change,
    rollback_plan,
    update_plan,
)
from brain.deployment.requirements import files_for
from brain.ops.compose import relative_bind_mounts
from brain.ops.wiring import PROFILES

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "release.yml"
SCRIPTS = REPO / "ops" / "update"

#: The repository the compose files select, read once so every rendering below is the real one.
REPOSITORY = image_repository(compose_documents())


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
def test_the_template_and_the_four_settings_are_what_the_plan_reads_from_the_archive() -> None:
    """Read out of the plan rather than listed, so a step that starts reading a second file is
    a second file the archive owes it. The tarball the install downloads, the RELEASE marker it
    writes, the environment file it creates and the three settings directories it makes are all
    under the same directory and none of them is the archive's to carry.

    **This was one file until 2026-09-10 and is five.** Item 43 of `docs/needs-rupash.md` moved
    four settings files out of relative bind mounts and into a step that copies them from the
    release into `/opt/brain/settings`, so the reason the archive owes them moved from the
    compose files to the plan. The set is the same four paths, which is the point: it is
    derived from wherever the install actually reads them.

    Delete this and the derivation can quietly start counting written files as needed ones,
    which reads as the archive being incomplete and sends somebody looking for a file nobody
    ships."""
    assert paths_the_install_reads(PLAN) == (
        ".env.example",
        "ops/automation/egress.conf",
        "ops/langfuse/clickhouse-memory.xml",
        "ops/seaweedfs/provision.sh",
        "ops/seaweedfs/s3.json",
    )


def test_a_directory_the_install_makes_is_not_one_the_archive_owes_it() -> None:
    """The fourth way the plan writes, and the one that cannot be a destination pattern.
    `mkdir` creates every operand it is given and the settings step passes it three, so a
    pattern naming "the path after the command" would have counted two of the three as files
    the archive owes the install, and the release would refuse to build over directories it was
    never supposed to carry.

    Delete this and the mkdir handling can be replaced by a pattern that looks equivalent and
    silently drops every operand after the first."""
    plan = (
        a_step(
            name="make three",
            run=f'mkdir -p "{INSTALL_HOME}/one" "{INSTALL_HOME}/two" "{INSTALL_HOME}/three"',
            changes=True,
            already_done=f'test -d "{INSTALL_HOME}/three"',
        ),
    )

    assert paths_the_install_reads(plan) == ()


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

    **There are none left, and that is why the second half of this test exists.** Item 43
    removed all four on 2026-09-10, so asserting over the repository's own documents would now
    be a loop over nothing wearing the clothes of a check. The constructed document is what
    keeps the rule measured: a mount added back has to be a path the archive carries, and one
    that is not is a finding rather than a silence.

    Delete this and a mount added to a compose file is a silently misconfigured container on
    somebody else's machine, found by nobody."""
    assert mounts_in(compose_documents()) == (), (
        "a relative bind mount is back; every one of them has to be a path the archive carries"
    )

    carried = {"services": {"one": {"volumes": ["./ops/seaweedfs/s3.json:/etc/x:ro"]}}}
    invented = {"services": {"one": {"volumes": ["./ops/nothing/here.conf:/etc/x:ro"]}}}

    for one in mounts_in({"a.yml": carried}):
        assert included_by(one), f"{one} is bind-mounted and the archive does not carry it"
    assert mounts_in({"a.yml": carried}) == ("ops/seaweedfs/s3.json",)
    assert not included_by(mounts_in({"a.yml": invented})[0])


def test_the_two_readers_of_the_bind_mounts_agree() -> None:
    """`brain.ops.compose.relative_bind_mounts` answers the operator's question as sentences and
    this answers the archive's as paths. Two readers of one thing is how they come to disagree,
    so the agreement is asserted rather than assumed.

    Both readers see nothing in this repository since item 43, so the agreement is also
    asserted on a constructed document. Two readers that agree because neither is looking is
    the same tick with none of the meaning.

    Delete this and one of the two can stop seeing a mount, which shows up as an archive that
    is complete by its own arithmetic."""
    invented = {"a.yml": {"services": {"one": {"volumes": ["./ops/x.conf:/etc/x:ro"]}}}}
    assert mounts_in(invented) == ("ops/x.conf",)
    assert len(relative_bind_mounts(invented)) == 1
    assert "./ops/x.conf" in relative_bind_mounts(invented)[0]

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


# ======================================== moving an install between two releases (M42.3.6)
def a_shell() -> str:
    """The POSIX shell on this machine, or a skip, matching `test_deployment_installer.py`."""
    shell = shutil.which("sh")
    if shell is None:  # pragma: no cover - CI runs on Linux, where sh always exists
        pytest.skip("no POSIX shell on this machine to run the rendered script")
    return shell


def an_install(root: Path, *, release: str = "v1.0.0", previous: str = "") -> Path:
    """A directory shaped like an install: the marker, the environment file, maybe the record."""
    root.mkdir(parents=True, exist_ok=True)
    root.joinpath("RELEASE").write_text(f"{release}\n", encoding="utf-8", newline="\n")
    root.joinpath(INSTALL_ENV_FILE).write_text(
        "POSTGRES_PASSWORD=kept\n", encoding="utf-8", newline="\n"
    )
    if previous:
        root.joinpath(PREVIOUS_MARKER).write_text(f"{previous}\n", encoding="utf-8", newline="\n")
    return root


def through(script: str, name: str) -> str:
    """The rendered script down to the end of the step with this name.

    Cut rather than run whole, because every step after the refusals talks to docker or to the
    release host. What is kept is the preamble and the steps in front of the one being tested,
    so the guard runs in the script it was rendered into rather than in a fixture of one line.
    """
    parts = script.split("\n# step ")
    kept = [parts[0]]
    for part in parts[1:]:
        kept.append(part)
        if part.split("\n", 1)[0].split(": ", 1)[1] == name:
            return "\n# step ".join(kept)
    msg = f"no step named {name!r} in the rendered script"
    raise AssertionError(msg)


def run_script(
    script: str, *, home: Path, args: Sequence[str] = ("lite",), url: str = ""
) -> subprocess.CompletedProcess[str]:
    """One cut script against a throwaway install directory.

    The install directory is substituted for the install home, and that is the only rewrite.
    These plans spell that path the way the install plan spells it and nothing parameterises
    it, and what is under test is what a guard does rather than which directory it looks in.
    """
    return subprocess.run(
        [a_shell(), "-s", "--", *args],
        input=script.replace(INSTALL_HOME, home.as_posix()),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env={**os.environ, "BRAIN_RELEASE_URL": url},
    )


def an_archive(path: Path, revisions: Sequence[str]) -> Path:
    """A release archive carrying one migration file per revision, as the workflow builds one."""
    root = path.parent / "built"
    versions = root / f"brain-{path.stem}" / "migrations" / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    for one in revisions:
        versions.joinpath(f"{one}_x.py").write_text(
            f'revision = "{one}"\ndown_revision = None\n', encoding="utf-8", newline="\n"
        )
    with tarfile.open(path, "w:gz") as archive:
        archive.add(root / f"brain-{path.stem}", arcname=f"brain-{path.stem}")
    return path


# ---------------------------------------------------------------- what an install records
def test_the_install_records_which_release_it_unpacked_and_never_which_image_it_runs() -> None:
    """**The finding this leaf turns on, asserted rather than argued.** The install plan writes
    the tag into a marker file and writes nothing that selects an image, so every container of
    a fresh install falls back to a compose default ending in `latest`: the marker and the
    running image disagree from the first day, and an update that only moved the marker would
    go on disagreeing while reporting a version.

    Delete this and the pin step can be dropped from both plans with every other test here
    still green, because nothing else asserts that anything anywhere writes the image
    variable."""
    assert release_marker(PLAN) == ("BRAIN_RELEASE", "RELEASE")
    assert [one.name for one in PLAN if THE_IMAGE_VARIABLE in one.run + one.already_done] == []

    defaults = {
        str(body.get("image", ""))
        for document in compose_documents().values()
        for body in dict(document.get("services") or {}).values()
        if isinstance(body, dict)
    }
    assert any(
        one.startswith(f"${{{THE_IMAGE_VARIABLE}:-") and one.endswith(":latest}")
        for one in defaults
    )

    pinning = [one for one in update_plan() if THE_IMAGE_VARIABLE in one.run]
    assert [one.name for one in pinning] == ["pin the image this install runs"]
    # Writes it, rather than merely naming it. The step reads the old line out as well as
    # writing the new one, so a check for the name alone passes with the write removed.
    assert f'printf "{THE_IMAGE_VARIABLE}=%s\\n"' in pinning[0].run


def test_a_plan_that_writes_no_release_tag_anywhere_is_refused_rather_than_defaulted() -> None:
    """The marker is read off the install plan rather than spelled a second time, so a rename
    there reaches both scripts. A default would render scripts that read a file no install has,
    which fails on somebody else's server with a message about a missing file.

    Delete this and the reader can start returning a constant pair and pass, which is a rename
    of the marker that silently keeps working here and stops working on a server."""
    with pytest.raises(ReleaseError, match="nothing on a server says which release"):
        release_marker((a_step(name="do nothing at all", run="true"),))
    assert "guess" in A_ROLLBACK_THAT_GUESSES_IS_WORSE_THAN_ONE_THAT_REFUSES


# --------------------------------------------------------------- recording, and its order
def test_the_update_records_the_release_it_replaces_before_it_writes_the_new_one() -> None:
    """**The ordering the whole update is shaped around.** The step that copies the marker sits
    in front of the step that overwrites it, so an update that fails anywhere after it still
    leaves a rollback something to go back to. The other order records the tag that was just
    installed, and it fails silently: the file exists, it holds a real tag, and it is the wrong
    one.

    Delete this and the two steps can be swapped, which changes nothing about whether the
    script runs and turns every rollback into a re-pin of the release being left."""
    names = [one.name for one in update_plan()]

    assert names.index("record the release this update replaces") < names.index(
        "download and unpack the release"
    )
    assert "the tag that was just installed" in (
        RECORDING_THE_PREVIOUS_RELEASE_AFTER_THE_NEW_ONE_RECORDS_THE_NEW_ONE
    )


def test_the_update_writes_down_the_release_that_was_there_before_it(tmp_path: Path) -> None:
    """The ordering above, as what actually lands on disk. Run against a directory holding one
    release, the recording step leaves a file naming that release and not the one being
    installed.

    Delete this and the index comparison above is satisfied by a step that copies the wrong
    file, or writes the target tag, or writes nothing at all."""
    home = an_install(tmp_path / "install", release="v1.0.0")
    script = through(
        render_update(repository=REPOSITORY), "record the release this update replaces"
    )

    done = run_script(script, home=home, args=("lite", "v1.1.0"), url="https://example.invalid/a")

    assert done.returncode == 0, done.stderr
    assert home.joinpath(PREVIOUS_MARKER).read_text(encoding="utf-8").strip() == "v1.0.0"


def test_a_second_run_of_the_update_does_not_record_the_release_it_just_installed(
    tmp_path: Path,
) -> None:
    """The guard that makes the copy safe to repeat. Once the marker names the target, the
    recording step has nothing to do: an unguarded copy run twice would record the release that
    was just installed as the one to go back to, which is a rollback to where you already are.

    Delete this and the step loses its guard, and the second run of an update that failed
    somewhere later destroys the only record of the release before it."""
    home = an_install(tmp_path / "install", release="v1.1.0", previous="v1.0.0")
    script = through(
        render_update(repository=REPOSITORY), "record the release this update replaces"
    )

    done = run_script(script, home=home, args=("lite", "v1.1.0"), url="https://example.invalid/a")

    assert done.returncode == 0, done.stderr
    assert "already done, skipping" in done.stdout
    assert home.joinpath(PREVIOUS_MARKER).read_text(encoding="utf-8").strip() == "v1.0.0"


# ------------------------------------------------------------------- the three refusals
def test_a_rollback_with_nothing_recorded_refuses_rather_than_guessing(tmp_path: Path) -> None:
    """**The refusal the second half of this leaf is about.** What a rollback could guess from
    is the tag it is already on or whatever the release host offers today, and both are guesses
    about a server nobody here can see. It is run at the worst moment of somebody's week, so it
    either goes back to the release this install was on or it stops and names the missing file.

    Delete this and the rollback can fall back to a default, which is a script that reports
    success and puts the install back on the release it was already running."""
    home = an_install(tmp_path / "install", release="v1.1.0")
    script = through(
        render_rollback(repository=REPOSITORY), "refuse without a record of the release being left"
    )

    done = run_script(script, home=home)

    assert done.returncode == 1
    assert "nothing here records the release" in done.stderr
    assert "guess" in A_ROLLBACK_THAT_GUESSES_IS_WORSE_THAN_ONE_THAT_REFUSES


def test_a_rollback_with_a_record_reads_it_and_says_where_it_is_going(tmp_path: Path) -> None:
    """The positive half, and a guard tested only by its refusals is satisfied by a script that
    refuses everything. The tag is printed before the archive for it is demanded, because the
    operator cannot supply that archive until they know which release this is going back to.

    Delete this and the refusal above can be made unconditional, which is a rollback that never
    rolls anything back."""
    home = an_install(tmp_path / "install", release="v1.1.0", previous="v1.0.0")
    script = through(
        render_rollback(repository=REPOSITORY), "read the release this rollback goes back to"
    )

    done = run_script(script, home=home, url="https://example.invalid/archive.tar.gz")

    assert done.returncode == 0, done.stderr
    assert "going back to v1.0.0" in done.stdout


def test_a_rollback_that_knows_its_tag_and_not_where_to_fetch_it_says_which_tag(
    tmp_path: Path,
) -> None:
    """The one asymmetry between the two scripts. The update demands the archive URL in its
    preamble; the rollback cannot, because the tag whose archive is wanted is read out of the
    install, so refusing before the tag is printed would refuse over a value nobody could have
    known to set.

    Delete this and the URL check moves into the preamble, where it fails with a sentence that
    does not say which release the operator is being asked to find."""
    home = an_install(tmp_path / "install", release="v1.1.0", previous="v1.0.0")
    script = through(
        render_rollback(repository=REPOSITORY), "read the release this rollback goes back to"
    )

    done = run_script(script, home=home, url="")

    assert done.returncode == 1
    assert "going back to v1.0.0" in done.stdout
    assert "BRAIN_RELEASE_URL" in done.stderr


@pytest.mark.parametrize(
    ("rendered", "step", "args", "previous"),
    [
        (
            render_update(repository=REPOSITORY),
            "refuse a tag that pins nothing",
            ("lite", NOT_A_RELEASE_TAG),
            "",
        ),
        (
            render_rollback(repository=REPOSITORY),
            "read the release this rollback goes back to",
            ("lite",),
            NOT_A_RELEASE_TAG,
        ),
    ],
    ids=["update", "rollback"],
)
def test_neither_script_will_put_an_install_on_a_tag_that_pins_nothing(
    tmp_path: Path, rendered: str, step: str, args: Sequence[str], previous: str
) -> None:
    """**Updating to `latest` is an unpin wearing an update's clothes.** The client has not
    moved to a release, they have stopped being pinned: the next pull changes the running
    version with nobody deciding anything, and the marker goes on naming a tag. Both directions
    refuse it, because a record written by an install that was never pinned would send a
    rollback there too.

    Delete this and the one word that undoes release pinning is the one word a hurried operator
    types, and both scripts accept it."""
    home = an_install(tmp_path / "install", release="v1.1.0", previous=previous)

    done = run_script(
        through(rendered, step), home=home, args=args, url="https://example.invalid/a"
    )

    assert done.returncode == 1
    assert NOT_A_RELEASE_TAG in done.stderr
    assert "not a release" in done.stderr
    assert "pinned" in LATEST_IS_AN_UNPIN_WEARING_AN_UPDATES_CLOTHES


def test_an_update_names_a_real_tag_and_gets_past_the_refusal(tmp_path: Path) -> None:
    """The positive sibling of the refusal above, for the reason CLAUDE.md gives: a guard
    tested only by what it rejects is satisfied by one that rejects everything, and an update
    script that refuses every tag is worse than none.

    Delete this and the refusal can be widened to any tag at all and stay green."""
    home = an_install(tmp_path / "install", release="v1.0.0")
    script = through(render_update(repository=REPOSITORY), "refuse a tag that pins nothing")

    done = run_script(script, home=home, args=("lite", "v1.1.0"), url="https://example.invalid/a")

    assert done.returncode == 0, done.stderr


def test_a_directory_with_no_environment_file_is_refused_before_anything_rewrites_one(
    tmp_path: Path,
) -> None:
    """The second half of the opening check, and it is not decoration. The pin step rewrites
    the environment file; against a directory that has none it would create one holding the pin
    and nothing else, so every credential the install minted would be gone and the script would
    report that it had pinned the release.

    Delete this and the quietest way to destroy an install is to run the update script in the
    wrong directory."""
    home = tmp_path / "install"
    home.mkdir()
    home.joinpath("RELEASE").write_text("v1.0.0\n", encoding="utf-8", newline="\n")
    script = through(render_update(repository=REPOSITORY), "check this directory holds an install")

    done = run_script(script, home=home, args=("lite", "v1.1.0"), url="https://example.invalid/a")

    assert done.returncode == 1
    assert "no environment file" in done.stderr


def test_an_unknown_profile_is_refused_by_name_rather_than_composing_nothing(
    tmp_path: Path,
) -> None:
    """These scripts take the profile because nothing an install leaves on disk records which
    one it was, and a typed profile that matched no arm would leave the compose file list
    empty: `docker compose up -d` with no `-f` would then recreate whatever a single default
    file names and report success.

    Delete this and a misspelled profile silently recreates part of an install."""
    home = an_install(tmp_path / "install")
    preamble = render_update(repository=REPOSITORY).split("\n# step ")[0]

    done = run_script(preamble, home=home, args=("lightweight", "v1.1.0"), url="https://x.invalid")

    assert done.returncode == 1
    assert "unknown profile" in done.stderr


# ------------------------------------------------------- the database the rollback leaves
def test_a_rollback_refuses_when_the_database_is_past_the_release_it_goes_back_to(
    tmp_path: Path,
) -> None:
    """**A rollback re-pins the code and leaves the schema.** Migrations run forward at startup
    under an advisory lock and nothing runs a downgrade against a client's data, so going back
    puts the older code in front of whatever the newer release left. The answerable version of
    that on a server is whether the database sits at a revision the target release does not
    carry, and it is asked of the archive before anything is unpacked or recreated.

    Delete this and the check becomes a line of shell nobody has run, which is the same thing
    as no check: the failure it exists for arrives as an application that will not start, after
    the containers have already been recreated."""
    archive = an_archive(tmp_path / "v1.0.0.tar.gz", ("0001", "0002"))
    step = next(
        one for one in rollback_plan() if one.name == "check the database is not past that release"
    )
    line = next(one for one in step.run.splitlines() if "--wildcards" in one)
    preamble = 'fail() { printf "%s\\n" "$1" >&2; exit 1; }\n'
    # The archive is named relatively and the shell is run in its directory, because GNU tar
    # reads a Windows path as a remote host and fails before it has opened anything.
    checked = line.replace(f"{INSTALL_HOME}/going-back-$BRAIN_RELEASE.tar.gz", archive.name)

    def asked(revision: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [a_shell(), "-s"],
            input=f'{preamble}applied="{revision}"\n{checked}\n',
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            cwd=archive.parent,
        )

    ahead, level = asked("0003"), asked("0002")

    assert ahead.returncode == 1
    assert "migrated past what the release you are going back to carries" in ahead.stderr
    assert level.returncode == 0, level.stderr
    assert "downgrade" in A_ROLLBACK_RE_PINS_THE_CODE_AND_LEAVES_THE_SCHEMA


def test_the_rollback_asks_the_database_which_revision_it_is_on() -> None:
    """The other half of the check, which the archive fixture above cannot exercise: the
    revision is read out of the running database rather than guessed from what the install
    directory happens to hold, and an unanswered read is its own refusal with its own sentence.

    Delete this and the read can be replaced by a value from the install directory, which is
    the release's own idea of where the schema should be rather than where it is."""
    step = next(
        one for one in rollback_plan() if one.name == "check the database is not past that release"
    )

    # Against the alembic configuration rather than against the constant itself: the query names
    # the table in the connection's default schema, and it is right exactly while nothing in the
    # migration environment moves it.
    assert "version_table" not in (REPO / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "alembic_version" in APPLIED_REVISION_QUERY
    assert APPLIED_REVISION_QUERY in step.run
    assert "exec -T db psql" in step.run
    assert "did not answer with the migration revision" in step.run
    assert not step.changes, "the check writes nothing, so it can be run before any decision"


def test_the_rollback_reads_the_archive_before_it_unpacks_it() -> None:
    """Why this plan does not reuse the installer's download step the way the update does. The
    check has to run while the install is still whole: unpacked first, a refusal would leave
    the older release's files on disk with the marker naming a tag the containers are not
    running, which is a worse state than the one being refused.

    Delete this and the two steps can be reordered into the shape that reads more naturally and
    leaves an install describing itself wrongly every time the check fires."""
    names = [one.name for one in rollback_plan()]

    assert (
        names.index("fetch the archive of that release")
        < names.index("check the database is not past that release")
        < names.index("unpack it and record which release this install is on")
    )


def test_a_rollback_forgets_the_record_it_acted_on(tmp_path: Path) -> None:
    """A rollback goes back one release. Left in place, the record would send a second run back
    to the release this one just left, so the two scripts oscillate between two tags with every
    run reporting success. Removed, the second run refuses and asks for a decision, which is
    what going back two releases actually needs.

    Delete this and the last step can go, and the pair becomes a loop somebody discovers by
    running it twice."""
    plan = rollback_plan()

    assert plan[-1].name == "forget the release this rollback left"
    assert f'rm -f "{INSTALL_HOME}/{PREVIOUS_MARKER}"' == plan[-1].run

    home = an_install(tmp_path / "install", release="v1.0.0", previous="v1.0.0")
    home.joinpath(PREVIOUS_MARKER).unlink()
    done = run_script(
        through(
            render_rollback(repository=REPOSITORY),
            "refuse without a record of the release being left",
        ),
        home=home,
    )
    assert done.returncode == 1


# ------------------------------------------------------------------- what the scripts are
def test_the_image_an_update_pins_is_read_off_the_compose_files() -> None:
    """The reference is already in every compose file, so a copy of it in the module would be
    the copy that stops matching. Only the default is read, because that is where the image
    name lives: `${APP_IMAGE}` with no default names no image at all.

    Delete this and the repository becomes a literal somebody keeps in step by hand, which is
    the arrangement that puts a client's containers on an image that stopped being published."""
    assert image_repository(compose_documents()) == REPOSITORY
    assert f"${{{THE_IMAGE_VARIABLE}:-{REPOSITORY}:latest}}" in {
        str(body.get("image", ""))
        for document in compose_documents().values()
        for body in dict(document.get("services") or {}).values()
        if isinstance(body, dict)
    }


def test_compose_files_selecting_two_repositories_or_none_are_refused() -> None:
    """Both refusals, against documents built to fail, because a check that can only be run
    against the healthy declaration has no test for the case it exists to find. No reference is
    a pin that sets a variable nothing reads and reports success. Two references is one script
    pinning half an install, which is the failure `release_pinning_gaps` describes arriving
    through the update instead of through a compose file.

    Delete this and both refusals survive a mutation run, for the reason
    `brain.ops.starter.starter_gaps` records: no test could hand them a bad case."""
    with pytest.raises(ReleaseError, match="no service"):
        image_repository({"a.yml": {"services": {"app": {"image": f"${{{THE_IMAGE_VARIABLE}}}"}}}})
    with pytest.raises(ReleaseError, match="two builds of one product"):
        image_repository(
            {
                "a.yml": {"services": {"app": {"image": f"${{{THE_IMAGE_VARIABLE}:-one/x:v1}}"}}},
                "b.yml": {"services": {"job": {"image": f"${{{THE_IMAGE_VARIABLE}:-two/y:v1}}"}}},
            }
        )
    assert (
        image_repository(
            {"a.yml": {"services": {"app": {"image": f"${{{THE_IMAGE_VARIABLE}:-one/x:v1}}"}}}}
        )
        == "one/x"
    )


def test_a_refusal_the_shell_would_act_on_rather_than_print_is_refused() -> None:
    """This is the one place in the repository where prose is compiled into shell. A `$` in a
    refusal expands to nothing at the exact moment somebody most needs to read it, so the
    operator gets a sentence with a hole in it and no sign a word was ever there, and a
    backtick does not leave a hole at all: it runs.

    Delete this and a reason written with a variable name in it reaches a client's terminal as
    a gap, on the day their update stopped."""
    assert refusal("test -f x", "there is no x here") == 'test -f x || fail "there is no x here"'
    for bad in ("set $HOME first", 'quote "this"', "run `date` first"):
        with pytest.raises(ReleaseError, match="acts on rather than prints"):
            refusal("test -f x", bad)


@pytest.mark.parametrize(
    "rendered",
    [render_update(repository=REPOSITORY), render_rollback(repository=REPOSITORY)],
    ids=["update", "rollback"],
)
def test_each_rendered_script_is_valid_shell(rendered: str) -> None:
    """A test asserting the text of a script is satisfied by a script that will not run, which
    is the argument `test_deployment_installer.py` makes about the installer. These two are
    worse if they will not run: they are executed on the day an install is already broken.

    Delete this and a quoting mistake in a refusal ships as a rollback that fails on its first
    line, at the one moment nobody has a working system to debug with."""
    checked = subprocess.run(
        [a_shell(), "-n"], input=rendered, capture_output=True, text=True, check=False, timeout=60
    )

    assert checked.returncode == 0, checked.stderr


@pytest.mark.parametrize("name", ["update.sh", "rollback.sh"])
def test_the_committed_scripts_are_what_the_module_renders(name: str) -> None:
    """A generated file checked into a repository is a copy that drifts, and this is the check
    that stops it: the file a client's server receives is the plan this suite tests, or the
    suite is red. The installer has no such file at all, and `docs/install/install.md` says so;
    these two are carried because the moment somebody needs the rollback is the moment they are
    least able to fetch anything.

    Delete this and the plan and the shipped script part company, and the tested one is not the
    one that runs."""
    render = render_update if name == "update.sh" else render_rollback

    assert SCRIPTS.joinpath(name).read_text(encoding="utf-8") == render(repository=REPOSITORY)


def test_the_archive_carries_the_two_scripts_and_the_install_does_not_read_them() -> None:
    """They reach a client's server with the release, because a rollback script fetched at the
    moment it is needed is one more thing that can be unreachable. They are not in
    `install_needs`, and that is right rather than an oversight: no step of the install reads
    them and no compose file mounts them, so they are carried because an include names them.

    Delete this and the include can be dropped, and a client's server holds a marker it cannot
    act on."""
    for name in ("ops/update/update.sh", "ops/update/rollback.sh"):
        assert included_by(name), name
        assert not refused_by(name), name
        assert name not in install_needs()
    assert set(carried_paths(REPO)) >= {"ops/update/update.sh", "ops/update/rollback.sh"}


def test_each_profile_has_an_arm_naming_the_compose_files_that_profile_composes() -> None:
    """The profile is an argument because nothing an install leaves on disk records which one
    it was, so the three answers are spelled out and a fourth profile appears here the day it
    is declared rather than the day somebody remembers.

    Delete this and a profile added to the product has no arm, and an update against an install
    of it composes nothing."""
    for rendered in (render_update(repository=REPOSITORY), render_rollback(repository=REPOSITORY)):
        arms = {
            line.strip().split(")", 1)[0]: line
            for line in rendered.splitlines()
            if "BRAIN_COMPOSE_FILES=" in line and line.startswith("  ")
        }
        assert set(arms) == set(PROFILES)
        for profile in PROFILES:
            for name in files_for(profile):
                assert f"-f {INSTALL_HOME}/{name}" in arms[profile]


def test_both_scripts_end_on_the_installers_own_readiness_check() -> None:
    """Readiness is what tells a person the swap worked, and it is the installer's step object
    rather than a copy of it: a second copy would be a second answer to the only question
    either script is run to have answered, and only one of the two would ever be corrected.

    Delete this and the check can be rewritten here as liveness, which passes for a container
    that is up and cannot reach its database."""
    ready = step_named("wait for the application to report ready")

    assert update_plan()[-1] is ready
    assert rollback_plan()[-2] is ready
    assert "download and unpack the release" in [one.name for one in update_plan()]
    assert step_named("download and unpack the release") in update_plan()


def test_both_scripts_create_a_settings_file_a_new_release_adds() -> None:
    """Four containers read a settings file at startup, mounted by absolute path from a
    directory the install creates once. A release that adds a fifth would reach a server with
    nobody creating it, and a bind mount whose source does not exist is the failure that starts
    the container anyway, with every health check green.

    The installer's own step is used, so its per-file guard comes with it: a file already there
    is left alone, which is what makes an edited egress allowlist survive an update.

    Delete this and an update refreshes the release directory and not the settings beside it,
    which is the exact failure the settings directory was introduced to close, arriving one
    release later."""
    settings = step_named("create the settings the containers mount")

    for plan in (update_plan(), rollback_plan()):
        names = [one.name for one in plan]
        assert settings in plan
        assert names.index(settings.name) > names.index("change into the release directory")
        assert names.index(settings.name) < names.index("pin the image this install runs")
