"""One command, safe to run twice, and printing no value it minted.

The four properties the installer rests on. Three of them are refusals on `Step`, which means
they are enforced when the plan is written rather than when a script is reviewed, and the
fourth is the answer to the question this module exists to settle: whether one command needs
the aggregate compose file `brain.ops.compose` argues against.

The step count is not in this docstring and used to be. It said twelve, the plan holds
fourteen since item 43 added the two steps that create the settings four containers mount and
the database the trace ledger connects to, and a number written in a sentence is the one that
stops being true. `test_every_step_that_writes_something_says_when_it_is_already_done` asserts
it against `len(PLAN)`, which is the only place it belongs.

The rendered script is checked structurally and then handed to `sh -n`, because a test that
asserted the text would be satisfied by a script that is not valid shell.

Task ids: M42.1.3, M42.3.1, M42.3.4, M42.5.15
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml

from brain.deployment.installer import (
    CREATED_DATABASES,
    INSTALL_ENV_FILE,
    INSTALL_HOME,
    INSTALL_SETTINGS,
    MOUNTED_SETTINGS,
    PLAN,
    TRACE_LEDGER_ROLE,
    TRACE_LEDGER_SERVICE,
    InstallerError,
    Step,
    compose_argv,
    compose_files_argument,
    health_report,
    one_command_blockers,
    rebuild_gaps,
    release_pinning_gaps,
    render,
    services_without_a_healthcheck,
    settings_not_created,
    settings_nothing_mounts,
    step_named,
    value_leaks_in,
)
from brain.deployment.requirements import files_for
from brain.ops.compose import databases_needed, described_services, mounted_paths
from brain.ops.leases import SealedSecret
from brain.ops.wiring import PROFILES, WiringError, components_for

REPO = Path(__file__).resolve().parents[2]


def parsed(names: tuple[str, ...]) -> dict[str, Any]:
    return {name: yaml.safe_load((REPO / name).read_text(encoding="utf-8")) for name in names}


def every_compose_file() -> dict[str, Any]:
    """Every compose file in the repository, which is the scope a pinning question has: a
    client pins the image, and the image is selected in files no single profile composes."""
    return parsed(tuple(sorted(one.name for one in REPO.glob("docker-compose*.yml"))))


def ok_step(**changes: Any) -> Step:
    """A valid step, so each refusal below is reached by changing exactly one thing."""
    values: dict[str, Any] = {
        "name": "do the thing",
        "run": "true",
        "why": "because otherwise the thing is not done",
        "on_failure": "run it again",
        "changes": False,
    }
    values.update(changes)
    return Step(**values)


# --- the one command -------------------------------------------------------------------


def test_one_command_installs_the_lite_profile_today_with_nothing_in_the_way() -> None:
    """**The answer to whether a one-command install needs the aggregate compose file.** Lite
    is one file and four services, and the only thing `one_command_blockers` finds about it is
    that nothing publishes a port, which is a fact about the reverse proxy rather than about
    the packaging. So one command works, over a file list, with no aggregate anywhere.

    Delete this and the claim in the module header is a paragraph nothing re-derives."""
    files = parsed(files_for("lite"))
    blockers = one_command_blockers("lite", files)

    assert compose_argv("lite") == (
        "docker",
        "compose",
        "-f",
        "docker-compose.lite.yml",
        "up",
        "-d",
    )
    assert len(blockers) == 1
    assert "publishes a port" in blockers[0]


def test_the_larger_profiles_are_blocked_by_one_thing_and_it_is_not_the_packaging() -> None:
    """The other half of the answer, and the half that stops it being an optimistic one.

    **This test measured five findings for `full` until 2026-09-10 and now measures two**,
    because three of them were the three parts of `docs/needs-rupash.md` item 43 and all three
    were fixed rather than excused: the object store is described once, the trace ledger's
    database is created by the plan, and the settings four containers read are created by it
    too. What is left for `standard` and `full` is a component with no service anywhere, which
    no packaging decision can close, and the port, which is a requirement on the server.

    This test is expected to fail as each is fixed, and that failure is the notification.
    Delete it and "one command" is claimed for profiles that cannot start."""
    standard = one_command_blockers("standard", parsed(files_for("standard")))
    assert len(standard) == 2
    assert any("presidio-analyzer" in one for one in standard)

    full = one_command_blockers("full", parsed(files_for("full")))
    assert len(full) == 2
    assert any("presidio-analyzer" in one for one in full)
    assert any("publishes a port" in one for one in full)
    # The three that were closed, each asserted as absent by the words the finding used, so a
    # reintroduction fails here rather than reading as an unchanged count.
    assert not any("-f flags" in one for one in full)
    assert not any("connects to database" in one for one in full)
    assert not any("no step of the install creates it" in one for one in full)


def test_the_relative_bind_mounts_are_not_counted_against_the_installer() -> None:
    """The distinction the whole module turns on. Those four mounts were empty for a
    deployment that stores its own copy of a compose file with no repository beside it. This
    installer unpacks the release into one directory and names every `-f` file absolutely
    underneath it, so the compose project directory is the release directory and `./ops/...`
    would have resolved even before item 43 named the paths absolutely.

    Both halves are still asserted, because the distinction outlives the mounts: `-f` paths are
    absolute under the release directory, and no finding here is about where a compose file was
    read from.

    Delete this and somebody folds the bind mounts into the blocker list, concludes the
    installer cannot work, and writes the aggregate file to fix it."""
    files = parsed(files_for("full"))
    from brain.ops.compose import relative_bind_mounts

    assert relative_bind_mounts(files) == ()
    assert all("bind mount" not in one for one in one_command_blockers("full", files))
    assert compose_files_argument("lite") == f"-f {INSTALL_HOME}/docker-compose.lite.yml"


# --- the settings the containers mount ---------------------------------------------------


def test_every_settings_file_a_container_mounts_is_one_the_install_creates() -> None:
    """**Part one of item 43, and the check is in both directions because only one of them is
    ever found by using the system.**

    Four containers read a settings file at startup. A mount with no file behind it is a
    container that starts with an empty directory in its place and no error anywhere, and what
    three of them are missing is a memory ceiling, an egress allowlist and a set of
    object-store credentials, so the container looks identical either way. The other direction
    is never found at all: a file the install creates that nothing mounts reads as
    configuration being honoured.

    Asked of every profile for the first direction, because a profile that mounts something
    nobody creates cannot come up, and of the whole product for the second, because every
    profile composes a subset.

    Delete this and a renamed mount is a container running without its configuration, or a
    renamed settings file is a copy nothing opens, and neither has a symptom."""
    for profile in sorted(PROFILES):
        assert settings_not_created(parsed(files_for(profile))) == (), profile
    assert settings_nothing_mounts(parsed(files_for("full"))) == ()

    # And the join is real rather than vacuous: all four are mounted, by four services.
    mounts = {
        (service, source)
        for _, service, source in mounted_paths(parsed(files_for("full")))
        if source.startswith(INSTALL_SETTINGS)
    }
    assert len(mounts) == len(MOUNTED_SETTINGS) == 4
    assert {service for service, _ in mounts} == {
        "automation-egress",
        "langfuse-clickhouse",
        "seaweedfs",
        "seaweedfs-init",
    }


def test_a_settings_file_nobody_creates_and_a_settings_file_nobody_mounts_are_both_found() -> None:
    """The positive case for a pair of checks whose real answer is an empty tuple. An all-clear
    with no proof that it can ever be otherwise is the failure `brain.ops.sweeps` keeps
    finding, and both directions here return `()` against the repository.

    Delete this and either check could be made to report nothing at all without a test
    noticing, which is the state the repository would agree with."""
    invented = {"a.yml": {"services": {"one": {"volumes": ["/srv/typo.conf:/etc/x:ro"]}}}}
    found = settings_not_created(invented)
    assert len(found) == 1
    assert "'/srv/typo.conf'" in found[0] and "no step of the install creates it" in found[0]

    orphaned = settings_nothing_mounts({"a.yml": {"services": {}}})
    assert len(orphaned) == len(MOUNTED_SETTINGS)
    assert all("no service anywhere mounts it" in one for one in orphaned)

    # A named volume is docker's to make and is not a path that can be absent, which is the
    # one exclusion either check has and the one that would make them useless if it widened.
    a_volume = {"a.yml": {"services": {"one": {"volumes": ["data:/var/lib"]}}}}
    assert settings_not_created(a_volume) == ()


def test_the_settings_step_copies_from_the_release_into_the_settings_directory() -> None:
    """The step reads the templates out of the unpacked release and writes them somewhere that
    an update does not replace, which is the same relationship the environment file has with
    `.env.example`. Both ends are asserted because the pair is the whole design: reading from
    the settings directory instead of the release would make the copy a self-assignment, and
    writing into the release directory would put a client's edited egress allowlist in the path
    the next unpack overwrites.

    Delete this and the step can be pointed at one directory twice, which passes every other
    test here and creates nothing."""
    step = step_named("create the settings the containers mount")

    for one in MOUNTED_SETTINGS:
        assert f'cp "{INSTALL_HOME}/ops/{one}" "{INSTALL_SETTINGS}/{one}"' in step.run
        assert f'test -f "{INSTALL_SETTINGS}/{one}"' in step.already_done
    assert f"{INSTALL_HOME}/ops" != INSTALL_SETTINGS
    assert INSTALL_SETTINGS.startswith(f"{INSTALL_HOME}/")


def test_a_profile_nobody_declared_cannot_be_installed_or_rendered() -> None:
    """A typo in a deployment variable would otherwise compose no files, report no blockers
    and render a script that starts nothing, all of which look like success.

    Delete this and `render("lte")` produces an installer for an empty stack."""
    with pytest.raises(WiringError, match="unknown profile"):
        compose_argv("lte")
    with pytest.raises(WiringError, match="unknown profile"):
        render("lte", services=1, memory_mib=1)
    with pytest.raises(WiringError, match="unknown profile"):
        one_command_blockers("lte", {})


# --- the plan --------------------------------------------------------------------------


def test_every_step_that_writes_something_says_when_it_is_already_done() -> None:
    """Safe to run twice is a property of every step, not of the script. The step that decides
    it is the one that mints the credentials: a second run without a guard writes a new
    database password beside a volume that still holds the old one, and the value that would
    have fixed it is gone.

    Delete this and a step added next year makes the whole installer unsafe to re-run, with
    nothing to say which one."""
    assert len(PLAN) == 14
    for step in PLAN:
        if step.changes:
            assert step.already_done.strip(), f"{step.name} writes and cannot say it is done"
        else:
            assert not step.already_done, f"{step.name} changes nothing and can be skipped"

    with pytest.raises(InstallerError, match="cannot say when it is already done"):
        ok_step(changes=True)
    with pytest.raises(InstallerError, match="reads as a step that can be skipped"):
        ok_step(changes=False, already_done="true")


def test_the_minting_guard_is_keyed_on_a_credential_and_not_on_the_file() -> None:
    """The guard that would have been wrong the obvious way. Keying it on the environment file
    existing is correct for an install that mints before anything else and silently wrong for
    one whose variables file arrived first: the file is there, nothing is minted, and the step
    reports it had nothing to do while every credential the stack needs is missing.

    Delete this and the two orderings of the same install behave differently."""
    step = step_named("mint this installation's secrets")
    assert "POSTGRES_PASSWORD" in step.already_done
    assert step.already_done != f'test -s "{INSTALL_HOME}/.env"'


def test_a_step_with_nothing_written_down_is_refused_at_the_point_it_is_declared() -> None:
    """`name`, `run`, `why` and `on_failure` are all required, and `on_failure` is the one
    M42.5.15 turns on: without it the person installing reads the shell's exit code and
    nothing else, at the moment they are least able to work out what to do.

    Both spellings of nothing, because `""` and `" "` are different values and a truthiness
    test only catches one of them.

    Delete this and the plan grows steps that print a number when they fail."""
    for empty in ("", " "):
        with pytest.raises(InstallerError, match="no name"):
            ok_step(name=empty)
        with pytest.raises(InstallerError, match="no run"):
            ok_step(run=empty)
        with pytest.raises(InstallerError, match="no why"):
            ok_step(why=empty)
        with pytest.raises(InstallerError, match="does not say what to do when it fails"):
            ok_step(on_failure=empty)


def test_a_step_that_would_print_a_credential_is_refused() -> None:
    """The installer is the single place a client's values are handled, which makes it the
    single place they can leak, and `brain.ops.independence` cannot see a value once it is in
    a terminal scrollback or a log. Three shapes: printing an expansion, tracing the script,
    and dumping the environment.

    Delete this and the next debugging line added to the mint step publishes every credential
    of every install it runs on."""
    with pytest.raises(InstallerError, match="would put a value where it can be read"):
        ok_step(run='echo "$POSTGRES_PASSWORD"')
    with pytest.raises(InstallerError, match="would put a value where it can be read"):
        ok_step(run="set -x\ntrue")
    with pytest.raises(InstallerError, match="would put a value where it can be read"):
        ok_step(run="printenv")
    with pytest.raises(InstallerError, match="would put a value where it can be read"):
        ok_step(changes=True, already_done='echo "${APP_ROLE_PASSWORD}"', run="true")


def test_printing_something_that_is_not_a_credential_is_not_a_leak() -> None:
    """The positive case, and the one that decides whether the rule is usable: a refusal that
    fired on `echo "step 3 of 12"` would be switched off within the hour, and the whole plan
    is built out of exactly that.

    Delete this and `value_leaks_in` can be made to refuse every line without failing."""
    assert value_leaks_in('printf "%s\\n" "step 3 of 12"') == ()
    assert value_leaks_in('echo "$BRAIN_PROFILE into $BRAIN_HOME"') == ()
    # A credential expanded outside an output command is the installer doing its job.
    assert value_leaks_in('POSTGRES_PASSWORD="$(openssl rand -hex 32)"') == ()


def test_exactly_one_step_is_allowed_to_present_a_value_and_it_is_the_setup_code() -> None:
    """The one deliberate exception. The setup code has to reach the person standing at the
    console or nobody can become the first administrator, which `brain.firstrun` already
    argues. What matters is that it is a declared flag on one step rather than a value that
    got through because its name happened not to match a pattern.

    Delete this and the exception spreads to whichever step somebody finds inconvenient."""
    presenting = [one for one in PLAN if one.presents_once]
    assert len(presenting) == 1
    assert presenting[0].name == "present the setup code, once"
    assert value_leaks_in(presenting[0].run), "the exception is not being exercised"


def test_a_step_nobody_declared_is_refused_rather_than_answered_with_nothing() -> None:
    """A caller handed None writes `if step is None: return` and the step silently stops being
    part of the install, which is the failure `brain.ops.wiring.component` refuses for the
    same reason.

    Delete this and a renamed step disappears from whatever was looking it up."""
    with pytest.raises(InstallerError, match="no step named"):
        step_named("mint the secrets")


# --- the databases the compose files do not create ---------------------------------------


def test_the_install_creates_exactly_the_databases_the_files_ask_for() -> None:
    """**Part two of item 43, and the equality is the whole test.** `POSTGRES_DB` creates one
    database on an empty data directory and the trace ledger's two services connect to a
    second one, so on a fresh install they failed with a message about a missing database
    rather than about the missing decision.

    Equality rather than a subset, in both directions at once. A database the files need and
    the plan does not create is two containers that cannot start. A database the plan creates
    that nothing connects to is a role and a database on a client's server that nobody can
    account for, which is the direction nothing else would ever report.

    The constant is then held to the step, because a name in a tuple creates nothing: what the
    plan says it creates and what the step's shell creates are two statements of one fact, and
    the second is the one that runs on a client's server.

    Delete this and a third database added to a connection string ships as a container that
    cannot start, or `CREATED_DATABASES` keeps creating one after the service that used it has
    gone."""
    assert set(databases_needed(parsed(files_for("full")))) == set(CREATED_DATABASES)
    assert CREATED_DATABASES == (("db", "langfuse"),)

    step = step_named("create the databases the compose files do not")
    for _, database in CREATED_DATABASES:
        assert f"create database {database} owner {TRACE_LEDGER_ROLE}" in step.run
        assert f"datname = '{database}'" in step.already_done


def test_the_login_the_install_creates_is_the_one_the_trace_ledger_signs_in_with() -> None:
    """A role created under a name nothing connects with is an install that reports success
    and a stack that cannot start, and nothing else here would compare the two: the connection
    string is in a compose file and the `create role` is in a shell fragment.

    Read out of `DATABASE_URL` rather than restated, so this tests the deployment rather than
    testing the constant against itself.

    Delete this and renaming the role in the plan, or the user in the URL, leaves two names
    that only meet on a client's server."""
    langfuse = parsed(("docker-compose.langfuse.yml",))["docker-compose.langfuse.yml"]
    urls = {
        urlsplit(str(body["environment"]["DATABASE_URL"]))
        for body in langfuse["services"].values()
        if body and "DATABASE_URL" in (body.get("environment") or {})
    }

    assert urls, "the trace ledger no longer holds a connection string to read"
    assert {one.username for one in urls} == {TRACE_LEDGER_ROLE}
    assert {one.path.lstrip("/").split("?")[0] for one in urls} == {CREATED_DATABASES[0][1]}
    assert TRACE_LEDGER_SERVICE in langfuse["services"]


def test_the_database_step_does_nothing_on_a_profile_with_no_trace_ledger() -> None:
    """One plan runs on every profile, and `lite` deploys no trace ledger. A step that created
    the database anyway would put a role and a database on a client's server for a component
    that machine does not run, which is the thing the second half of the equality test above
    exists to refuse.

    Asked of the composed project rather than of the profile name, because that is the
    question that matters: does this install run something that connects to it. Both the guard
    and the body ask it, so the step is skipped on lite rather than running and finding nothing
    to do.

    Delete this and the two can drift apart, and the interesting drift is the silent one: a
    body that runs where the guard said there was nothing to do."""
    step = step_named("create the databases the compose files do not")

    asks = f"config --services | grep -qx {TRACE_LEDGER_SERVICE}"
    assert asks in step.run
    assert asks in step.already_done
    assert step.already_done.startswith("! docker compose"), (
        "the guard has to be true when this profile runs no trace ledger, not false"
    )


def test_the_trace_ledger_password_never_reaches_a_command_line() -> None:
    """**The exposure `value_leaks_in` cannot see, so it is asserted here instead.** The
    obvious spelling is `psql -v name=<value>`, which puts a client's credential into the argv
    of a process every local user on that host can read out of `/proc` for as long as it runs,
    and argv is not an output builtin so the leak check would have passed it without a word.

    The statement is built by `sed` out of the environment file and delivered on psql's
    standard input, so the value is never anywhere but the file and the pipe. Asserted as the
    absence of the two shapes that would expose it and the presence of the one that does not,
    because the absence alone is satisfied by a step that does not create the role at all.

    Delete this and the next person to simplify this step reaches for `-v` and it looks
    correct in review."""
    step = step_named("create the databases the compose files do not")

    assert "create role" in step.run
    assert f'sed -n "s/^LANGFUSE_POSTGRES_PASSWORD={chr(92)}(' in step.run
    assert "-v LANGFUSE_POSTGRES_PASSWORD" not in step.run
    assert "$(" not in step.run, "a command substitution puts the value in a shell variable"
    assert value_leaks_in(step.run) == ()
    # And it refuses to run at all on an install that has not set one, rather than creating a
    # role with an empty password that the trace ledger would then fail to sign in with.
    assert 'grep -q "^LANGFUSE_POSTGRES_PASSWORD=."' in step.run


# --- the rendered script ---------------------------------------------------------------


def test_the_install_directory_is_the_one_every_message_and_runbook_names() -> None:
    """Pinned as a literal, because every assertion about the script uses `INSTALL_HOME` and a
    test that reads the constant to check the script that was rendered from the constant
    compares it with itself and passes for every path it could hold.

    It is load-bearing twice over: it is the directory a person changes into when the install
    has gone wrong, and it is the compose project directory that makes the four relative bind
    mounts resolve. Moving it is a decision, not an edit.

    Delete this and the path can be changed to anything, including one that does not exist on
    the distribution the client is running."""
    assert INSTALL_HOME == "/opt/brain"
    # And every step that writes guards on the place it writes. A step whose idempotence test
    # looks somewhere else is a step that reports it is done by reading the wrong thing.
    #
    # Two places, not one, and saying so is the point. The step that creates the trace ledger's
    # database reads the environment file under INSTALL_HOME and writes nothing there, so a
    # rule keyed on the path appearing in `run` would have demanded it guard on a file it does
    # not create. What it writes is a database, and asking the database is the honest guard.
    for step in PLAN:
        if not step.changes:
            continue
        writes_a_database = "psql" in step.run
        if not writes_a_database and INSTALL_HOME not in step.run:
            continue
        looks_at = "psql" if writes_a_database else INSTALL_HOME
        assert looks_at in step.already_done, (
            f"{step.name} writes to {looks_at} and guards on something else"
        )


def test_a_redirect_exempts_a_line_only_when_it_is_the_last_thing_on_it() -> None:
    """The exemption is anchored to the end of the line, and the anchor is what stops a
    compound command hiding behind it: `printf ... > /opt/brain/.env && echo "$SECRET"` writes
    one value where it belongs and prints another where it does not, and an unanchored pattern
    reads the whole line as a write to the environment file.

    Delete this and the widest rule in the module widens again, silently."""
    printf_n = chr(92) + chr(110)
    compound = f'printf "A=%s{printf_n}" "$a" > "/opt/brain/.env" && echo "$POSTGRES_PASSWORD"'
    leaks = value_leaks_in(compound)
    assert len(leaks) == 1
    assert "POSTGRES_PASSWORD" in leaks[0]


def test_the_rendered_script_numbers_every_step_against_the_plans_own_length() -> None:
    """M42.5.15 asks for output that says how far through it is. Numbered against `len(PLAN)`
    rather than against a number somebody typed, so adding a step renumbers the whole script
    instead of producing "step 13 of 12".

    Delete this and the progress count goes stale the first time the plan changes."""
    script = render("lite", services=4, memory_mib=3968)
    for number, step in enumerate(PLAN, 1):
        assert f"step {number} of {len(PLAN)}: {step.name}" in script
    assert f"{len(PLAN)} steps." in script


def test_the_rendered_script_guards_each_writing_step_and_says_it_is_skipping() -> None:
    """Idempotence a person can see. A script that silently did nothing on a second run is
    indistinguishable from one that failed to do anything on the first.

    Delete this and the guards can be dropped from the renderer while the plan still declares
    them."""
    script = render("lite", services=4, memory_mib=3968)
    for step in PLAN:
        if not step.changes:
            continue
        assert f"if {step.already_done}; then" in script
        assert f"{step.name} - already done, skipping" in script


def test_the_rendered_script_fetches_an_archive_and_never_clones_a_repository() -> None:
    """A build input that clones is the shape `brain.ops.independence.duplication_gaps`
    refuses, and it refuses it for the reason that ends with a client running a copy no fix
    ever reached. An installer is a build input in every sense that matters.

    Delete this and the one-line convenience of `git clone` puts a second copy of this
    repository on every client's server."""
    from brain.ops.independence import FETCHES_A_REPOSITORY

    script = render("full", services=19, memory_mib=12864)
    assert FETCHES_A_REPOSITORY.search(script) is None
    assert "curl -fsSL" in script
    assert "tar -xzf" in script


def test_the_rendered_script_names_every_compose_file_under_the_release_directory() -> None:
    """The bind-mount answer, in the output rather than in the docstring. Compose resolves a
    relative path inside a compose file against the project directory, which is the directory
    the first `-f` file was read from, so absolute paths under the release directory are what
    make `./ops/seaweedfs/s3.json` resolve instead of becoming an empty directory.

    Delete this and the installer inherits the exact failure the aggregate compose file was
    rejected for."""
    script = render("full", services=19, memory_mib=12864)
    for name in files_for("full"):
        assert f"-f {INSTALL_HOME}/{name}" in script
    assert f'cd "{INSTALL_HOME}"' in script


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_the_rendered_script_is_valid_shell(profile: str) -> None:
    """A test asserting the text of a script is satisfied by a script that will not run. This
    is the only assertion here that the output is a program.

    Delete this and a quoting mistake in a step ships as an installer that fails on its first
    line, on a client's server, at the one moment nobody has a working system to debug with."""
    shell = shutil.which("sh")
    if shell is None:  # pragma: no cover - CI runs on Linux, where sh always exists
        pytest.skip("no POSIX shell on this machine to parse the rendered script")
    script = render(profile, services=4, memory_mib=1024)
    checked = subprocess.run(
        [shell, "-n"], input=script, capture_output=True, text=True, check=False, timeout=30
    )
    assert checked.returncode == 0, checked.stderr


# --- what the one command deploys ------------------------------------------------------


def test_no_service_anywhere_is_built_on_a_client_server(_: None = None) -> None:
    """M42.1.3. A `build:` key means the client's machine compiles its own copy of an image
    every other client pulls, which is then a different artefact with the same version number
    on it and nothing anywhere comparing the two. An untagged image is the quieter half of the
    same thing, because docker resolves a bare name to `:latest`.

    Delete this and the first `build:` added for convenience makes every install a different
    build of the product."""
    assert rebuild_gaps(every_compose_file()) == ()


def test_a_build_or_an_untagged_image_would_be_reported() -> None:
    """The positive case for a check whose real answer is an empty tuple. A check that is
    green because it looks at nothing is the failure `brain.ops.sweeps` keeps finding, and an
    all-clear with no proof that it can ever be otherwise is exactly that shape.

    Delete this and `rebuild_gaps` could return `()` unconditionally."""
    document = {
        "services": {
            "one": {"build": "."},
            "two": {"image": "pgvector/pgvector"},
            "three": {"image": "pgvector/pgvector:pg18"},
            "four": None,
        }
    }
    findings = rebuild_gaps({"one.yml": document})
    assert len(findings) == 2
    assert any("declares a build" in one for one in findings)
    assert any("no tag" in one for one in findings)


def test_one_variable_now_selects_every_container_of_this_product() -> None:
    """**M42.1.4, and this test read the opposite until 2026-09-09.**

    It was named "release pinning is spread over three variables and defaults to latest", and
    it was the measurement of a leaf that did not work: an install's containers were selected
    by `APP_IMAGE` and by `BRAIN_IMAGE`, so a client who pinned one of them left the realm
    importer on the other's default and could run two builds of one product at once. The guide
    said so out loud, in a row telling the reader to keep the two equal by hand, which is a
    version pin that depends on somebody remembering.

    One variable now, so a client holds a version back by setting one thing and no container
    escapes it. That is the leaf: pinning per client without a fork.

    The third variable, `STAGING_IMAGE`, is not part of that and is deliberately still its own.
    Staging exists to run a build production has not taken yet, so a staging stack reading
    production's variable is a staging stack that cannot stage. The test two below is that
    boundary, and this assertion is written as a filter on the findings rather than as an empty
    tuple so it keeps measuring the property it names while the `:latest` default is still a
    separate open question.

    Delete this and the variables drift apart again with nothing saying so."""
    findings = release_pinning_gaps(every_compose_file())

    assert [one for one in findings if "is selected by" in one] == []


def test_every_image_still_defaults_to_a_moving_tag_and_that_is_a_decision() -> None:
    """**Not the leaf, and a decision rather than a defect.**

    M42.1.4 asks that a client who pins can hold a version back, and that works. This is the
    other question: what happens to a client who pins nothing.
    `${APP_IMAGE:-...:latest}` means an install that pins nothing follows whatever `latest`
    points at on the day it pulls. The obvious repair is `:?`, the same shape `ops/deploy.sh`
    took for the host it used to guess, and it was tried and reverted on 2026-09-09 for a
    reason worth recording: the image name lives in the default, so a reference with no default
    names no image, and the duplicate-variable check one test up goes blind. Removing the
    default would trade a finding somebody can act on for a check that reports nothing.

    It is also a live decision rather than a tidy-up. This deployment's automatic deploy pulls
    `latest`, so requiring the variable stops it until somebody sets one. That is Needs Rupash
    item 51.

    The count is asserted so a seventh service added with a moving tag fails here rather than
    joining a number nobody re-derives.

    Delete this and the open half of the question stops being measured, and the reason item 51
    is on the page at all is a sentence in a commit message."""
    findings = release_pinning_gaps(every_compose_file())

    assert len([one for one in findings if "follows whatever latest" in one]) == 6


def test_a_second_variable_selecting_one_image_inside_one_stack_is_still_a_finding() -> None:
    """The check has to keep working now that the tree is clean, and a check that can only be
    run against a healthy declaration cannot be shown to fail.

    Both defaults name one image, which is what makes this the case the check is for. The
    first draft gave the first service `${APP_IMAGE:?set it}`, and a reference with no default
    names no image, so the two services were two different images and the document could not
    have produced the finding it asserts.

    **Two files rather than one, because that is the shape the real defect had.** The
    application declared `APP_IMAGE` in `docker-compose.yml` and the realm importer declared
    `BRAIN_IMAGE` in `docker-compose.keycloak.yml`, and the two are one install because
    neither file names a project of its own. A version of this written against a single
    document passed while the grouping key was the file name, which is a check that would
    have found nothing in the tree it was written for.

    Delete this and the tree passing is the only evidence the check does anything."""
    application = {"services": {"app": {"image": "${APP_IMAGE:-ghcr.io/x/brain:v1.2.3}"}}}
    beside_it = {"services": {"realm": {"image": "${OTHER_IMAGE:-ghcr.io/x/brain:v1.2.3}"}}}

    found = release_pinning_gaps(
        {"docker-compose.yml": application, "docker-compose.keycloak.yml": beside_it}
    )

    assert any("one install runs two builds of one product" in one for one in found)


def test_a_stack_of_its_own_may_pin_the_same_image_separately() -> None:
    """**The other side of that check, and getting it wrong cost a full suite run.**

    On 2026-09-09 the duplicate-variable finding was acted on by pointing every image
    reference in the repository at `APP_IMAGE`, staging included. Staging is where a candidate
    release is tried before production takes it, so one variable for both is a staging stack
    that can only ever run what production already runs, which is not a staging stack.

    A file that declares `name:` is its own compose project rather than an overlay merged into
    the install, and that is the distinction the check now makes. It is read out of the files
    rather than kept as a list of exceptions here, so a second stack added later is right
    without anybody remembering this.

    Delete this and the next reader unifies the variables again, because the finding says to
    and nothing says not to."""
    overlay = {"services": {"app": {"image": "${APP_IMAGE:-ghcr.io/x/brain:v1.2.3}"}}}
    beside_it = {
        "name": "brain-staging",
        "services": {"app": {"image": "${STAGING_IMAGE:-ghcr.io/x/brain:v1.2.3}"}},
    }

    assert release_pinning_gaps({"a.yml": overlay, "b.yml": beside_it}) == ()

    two_inside_the_named_one = {
        "name": "brain-staging",
        "services": {
            "app": {"image": "${STAGING_IMAGE:-ghcr.io/x/brain:v1.2.3}"},
            "worker": {"image": "${STAGING_WORKER_IMAGE:-ghcr.io/x/brain:v1.2.3}"},
        },
    }
    found = release_pinning_gaps({"b.yml": two_inside_the_named_one})

    assert any("inside one stack" in one for one in found), "a name is not an exemption"


def test_an_image_pinned_to_a_tag_by_one_variable_is_reported_as_clean() -> None:
    """The positive case, and it is what the fix looks like: one variable, and a default that
    is a version rather than a promise to change.

    Delete this and the check cannot distinguish a fixed deployment from the current one."""
    document = {
        "services": {
            "app": {"image": "${BRAIN_IMAGE:-ghcr.io/example/brain:v1.2.3}"},
            "worker": {"image": "${BRAIN_IMAGE:-ghcr.io/example/brain:v1.2.3}"},
            "db": {"image": "pgvector/pgvector:pg18"},
            "inference": {"image": "${INFERENCE_IMAGE:?no image is published yet}"},
            "broken": None,
        }
    }
    assert release_pinning_gaps({"one.yml": document}) == ()


# --- what to check after deploying -----------------------------------------------------


def test_the_health_report_prints_what_ready_means_for_every_component() -> None:
    """M42.3.4 asks for a health check somebody can read the output of, and the readable half
    is the hard one: `ok` per container tells the reader a process is up, which is liveness
    wearing readiness' clothes. Every component in `brain.ops.wiring` carries a `ready_when`
    sentence for this moment and nothing had ever printed one.

    The healthcheck line is asserted per service rather than as one substring anywhere in the
    report, and that is not symmetry. The report reads each service's body out of the file that
    describes it, and the object store is named in the trace ledger's file and described in the
    object store's: taken from the naming file it has no healthcheck, so the report would tell
    an operator to check by hand a container that has one. A single "has a healthcheck" in the
    whole report passes either way, because eighteen other services have one.

    Delete this and the post-install check goes back to reporting that containers exist."""
    files = parsed(files_for("full"))
    report = health_report("full", files)
    for one in components_for("full"):
        assert one.ready_when in report, f"{one.name} has a readiness sentence nobody prints"
    assert "has a healthcheck" in report

    for service, where in described_services(files).items():
        body = files[where[0]]["services"][service]
        if body.get("healthcheck"):
            assert f"{service}: has a healthcheck" in report, (
                f"{service} declares a healthcheck and the report says to check it by hand"
            )


def test_every_long_running_service_declares_a_healthcheck_and_the_one_shots_do_not() -> None:
    """A container with no healthcheck counts as running the instant its process starts, so
    `depends_on: service_healthy` cannot wait for it. The two exceptions are one-shots, which
    are ready when they have exited and would never pass a healthcheck at all.

    Delete this and a service added without one makes `depends_on` wait for nothing, which
    fails only under load and only sometimes."""
    assert services_without_a_healthcheck(parsed(files_for("full"))) == ()

    document = {
        "services": {
            "one": {"image": "a:1"},
            "two": {"image": "a:1", "restart": "no"},
            "three": {"image": "a:1", "healthcheck": {"test": ["CMD", "true"]}},
            "four": None,
        }
    }
    findings = services_without_a_healthcheck({"one.yml": document})
    assert len(findings) == 1
    assert "'one'" in findings[0]


def test_a_credential_written_into_this_installs_own_file_is_not_a_leak() -> None:
    """Without this the rule refuses the one thing the installer exists to do. Minting is
    `printf ... >> /opt/brain/.env`, which is a print of a credential and is also correct, so
    the destination has to be the rule rather than the command.

    A check that refuses the correct implementation is a check somebody deletes, which is why
    both directions are asserted here and not only the refusal.

    Delete this and the mint step cannot be written, or the redirect exemption widens until it
    covers a print to a log file."""
    newline = chr(92) + "n"
    minting = (
        "{\n"
        f'  printf "POSTGRES_PASSWORD=%s{newline}" "$(openssl rand -hex 32)"\n'
        '} >> "/opt/brain/.env"'
    )
    assert value_leaks_in(minting) == ()
    assert value_leaks_in(f'printf "POSTGRES_PASSWORD=%s{newline}" "$x" > "/opt/brain/.env"') == ()

    # The same command with any other destination, which is the failure.
    assert value_leaks_in(f'printf "POSTGRES_PASSWORD=%s{newline}" "$x" >> "/var/log/install.log"')
    assert value_leaks_in(f'printf "POSTGRES_PASSWORD=%s{newline}" "$x"')


def test_a_credential_read_out_of_a_file_and_printed_is_caught_as_well() -> None:
    """The hole the first version of this rule had, and it let through the one step in the
    plan that certainly prints a credential: the setup code is read with
    `grep BRAIN_SETUP_SECRET ... | cut` inside a command substitution, so the name is a bare
    word rather than an expansion and a check looking for `$NAME` saw nothing.

    Delete this and the exception flag stops being load-bearing, because nothing would ever
    have needed it."""
    newline = chr(92) + "n"
    assert value_leaks_in(f'printf "%s{newline}" "$(grep BRAIN_SETUP_SECRET /opt/brain/.env)"')
    # Prose is not a credential, whatever words it contains.
    assert value_leaks_in(f'printf "%s{newline}" "set your password on the next screen"') == ()


def test_the_redirect_exemption_covers_its_own_group_and_nothing_above_it() -> None:
    """The exemption is what lets the mint step be written, and it is also the widest
    hole in this rule, so its edges are asserted rather than assumed. Two of them: a
    redirect that is not closing a brace group takes only its own line, and a group that
    is exempted stops at its opening brace rather than swallowing whatever came before it.

    Both were survivors of the guard audit, which is to say either could be removed with
    every other test still green, and each one removed hides a real print of a credential.

    Delete this and the exemption widens until a leak on the line above a redirect is
    invisible."""
    printf_n = chr(92) + chr(110)
    # A leak above a single-line redirect. Only the redirected line is exempt.
    two_lines = chr(10).join(
        (
            f'printf "%s{printf_n}" "$(grep BRAIN_SETUP_SECRET /opt/brain/.env)"',
            f'printf "A=%s{printf_n}" "$a" > "/opt/brain/.env"',
        )
    )
    assert value_leaks_in(two_lines)

    # A leak above an exempted brace group. The walk back stops at the opening brace.
    group = chr(10).join(
        (
            f'printf "POSTGRES_PASSWORD=%s{printf_n}" "$a"',
            "{",
            f'  printf "APP_ROLE_PASSWORD=%s{printf_n}" "$b"',
            '} >> "/opt/brain/.env"',
        )
    )
    leaks = value_leaks_in(group)
    assert len(leaks) == 1
    assert "POSTGRES_PASSWORD" in leaks[0]


def test_the_rendered_script_prints_exactly_one_value_and_it_is_the_setup_code() -> None:
    """The whole script rather than one step, because the renderer wraps every step in output
    of its own and a rule proved only against the plan would miss a leak the renderer added.

    Delete this and `render` could start echoing what each step set, which is precisely the
    line somebody adds while debugging an install that will not come up."""
    script = render("lite", services=4, memory_mib=3968)
    leaks = value_leaks_in(script)
    assert len(leaks) == 1
    assert "BRAIN_SETUP_SECRET" in leaks[0]


# --- the setup pair --------------------------------------------------------------------------


def test_the_setup_code_and_the_instant_it_was_minted_are_written_by_one_guarded_step() -> None:
    """The two halves of one value. `brain.firstrun.derived_enrolment` reads both and refuses a
    file carrying one of them, which is only a safe rule if this repository cannot produce that
    file: written in two steps, a run that died between them would leave a secret with no
    instant and an install nobody can claim, reachable without anybody hand-editing anything.

    One group, one redirect and one `already_done` therefore, and the guard is the same one
    that keeps a second run from re-minting the database password. That is what makes a restart
    unable to move the window: neither line is ever written twice.

    Delete this and the instant can drift into a step of its own, where a second run of the
    installer would write a new one beside the old secret and reopen the hour."""
    step = step_named("mint this installation's secrets")
    lines = step.run.splitlines()

    opened = [i for i, line in enumerate(lines) if line.strip() == "{"]
    closed = [i for i, line in enumerate(lines) if line.strip().startswith("}")]
    assert len(opened) == 1 and len(closed) == 1, "the mint step is no longer one written group"

    written = {
        line.split('"')[1].split("=")[0] for line in lines[opened[0] + 1 : closed[0]] if '"' in line
    }
    assert {"BRAIN_SETUP_SECRET", "BRAIN_SETUP_ISSUED_AT"} <= written, (
        f"the setup pair is not written together; this group writes {sorted(written)}"
    )
    assert value_leaks_in(step.run) == ()
    assert step.changes and "POSTGRES_PASSWORD" in step.already_done


def test_the_instant_the_installer_writes_is_one_python_reads_back_as_an_aware_time() -> None:
    """The join crosses a language boundary, and this is the only test on either side of it.
    `date` writes the instant into the environment file and `brain.app.Settings` parses it back
    into a `datetime` that `brain.firstrun.Enrolment` refuses unless it carries a zone, so a
    format without the `Z`, or with a space instead of the `T`, produces an install whose
    wizard raises on every screen rather than one that refuses politely.

    The format is read out of the step rather than restated, so this tests what the installer
    will actually run. `strftime` and `date` share these codes, which is what makes the
    round trip meaningful rather than a test of Python against itself.

    Delete this and the two ends can disagree about a date format, with the failure appearing
    on a client's server on install day."""
    minting = step_named("mint this installation's secrets").run
    found = re.search(r"date -u \+(\S+?)\)", minting)
    assert found, f"the mint step no longer writes an instant with date: {minting}"

    written = datetime(2026, 1, 6, 9, 0, tzinfo=UTC).strftime(found.group(1))
    read_back = datetime.fromisoformat(written)

    assert read_back == datetime(2026, 1, 6, 9, 0, tzinfo=UTC)
    assert read_back.tzinfo is not None, "a naive instant is one Enrolment refuses"


def test_running_the_template_and_mint_steps_produces_an_enrolment(tmp_path: Path) -> None:
    """**The only test anywhere that runs a step of this plan rather than reading it.** Every
    other test here asserts about the text; this one copies the template, mints into the copy
    with a real shell, and takes the result through the settings object to the enrolment the
    wizard is handed. Two steps of twelve, and it is the two that decide whether an install can
    be claimed at all.

    It also settles the one thing the template change made ambiguous. `.env.example` carries
    `BRAIN_SETUP_SECRET=` blank, because M31.3.1.2 says every setting the application reads is
    documented there, and the mint step appends the real value to a copy of that file. So the
    install's environment file holds the name twice, and this asserts that what a reader gets
    is the minted one rather than the blank. That was already true of `APP_ROLE_PASSWORD` and
    nothing had ever checked it.

    Delete this and the plan goes back to being prose that is only ever read."""
    shell = shutil.which("sh")
    if shell is None or shutil.which("openssl") is None:  # pragma: no cover - CI has both
        pytest.skip("no POSIX shell with openssl on this machine to run a step of the plan")

    from brain.app import Settings
    from brain.deployment.variables import parse_env
    from brain.firstrun import claim

    home = tmp_path / "install"
    home.mkdir()
    shutil.copyfile(REPO / ".env.example", home / ".env.example")
    for name in (
        "write the environment file from the template",
        "mint this installation's secrets",
    ):
        script = step_named(name).run.replace(INSTALL_HOME, home.as_posix())
        ran = subprocess.run(
            [shell, "-eu", "-c", script], capture_output=True, text=True, check=False, timeout=60
        )
        assert ran.returncode == 0, f"{name}: {ran.stderr}"

    values = parse_env((home / INSTALL_ENV_FILE).read_text(encoding="utf-8"))
    secret, minted = values["BRAIN_SETUP_SECRET"], values["BRAIN_SETUP_ISSUED_AT"]
    assert len(secret) == 64, "the blank from the template won over the minted value"

    settings = Settings(
        env="development",
        setup_secret=SealedSecret(secret),
        # Parsed here rather than passed as text, because `Settings` declares a `datetime` and
        # a keyword argument is checked against the declaration: what proves the string the
        # shell wrote is readable is that this parse succeeds on it.
        setup_issued_at=datetime.fromisoformat(minted),
    )
    enrolment = settings.setup_enrolment()

    assert enrolment is not None
    assert claim(enrolment, presented=secret, now=enrolment.issued_at).accepted
