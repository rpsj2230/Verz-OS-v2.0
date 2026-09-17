"""One command on a fresh server, held against the plan it is a printout of.

The script under test is a file in this repository, which is the whole reason this module
exists. A rendered artefact checked in without a test comparing it to its renderer is a copy,
and the copy is the one a client's server runs; `test_deployment_release.py` makes the same
argument about `ops/update/update.sh` and this is the third of the three.

**Nothing here has been run on a server.** Every test below reads the script, parses it, or
hands it to a shell's syntax checker. No test starts a container, reaches a registry or
installs a package, because there is no Docker on the machine this suite runs on. So what is
proved is that the script says what the plan says, refuses what the requirements require, and
is valid shell. What is not proved is that it installs anything, and `docs/install/install.md`
says so in the same words.

Task ids: M42.5.1
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from brain.deployment.install_script import (
    CHECKS,
    DOCKER_APT_ROUTES,
    DOCKER_DNF_ROUTES,
    DOCKER_DOCUMENTATION_URL,
    DOCKER_PACKAGES_URL,
    FLAGS,
    HANDOVER,
    PREPARE,
    RELEASE_URL_VARIABLE,
    SCRIPT_PATH,
    SPLIT_ON_PURPOSE,
    Check,
    InstallScriptError,
    as_shell_text,
    checks_without_a_requirement,
    install_plan,
    refusal,
    render_install,
    requirements_without_a_check,
    unquoted_expansions,
)
from brain.deployment.installer import PLAN, Step, value_leaks_in
from brain.deployment.release import REPO, compose_documents
from brain.deployment.requirements import RUNTIME_REQUIREMENTS, files_for, spec_for
from brain.ops.wiring import PROFILES

#: The committed script, which is the artefact every test here is about.
SCRIPT: Path = REPO / SCRIPT_PATH

#: `# step 4 of 19: check the machine`, as the script writes its own table of contents.
HEADING = re.compile(r"^# step (\d+) of (\d+): (.+)$", re.MULTILINE)


def figures() -> tuple[dict[str, int], dict[str, int]]:
    """The containers and the memory each profile needs, out of the compose documents.

    Derived here rather than taken from the module under test, because a test that asked the
    renderer for the figures it renders would compare the renderer against itself, which is the
    trap CLAUDE.md records about a constant asserted against its own import.
    """
    files = compose_documents(REPO)
    specs = {
        profile: spec_for(profile, {name: files[name] for name in files_for(profile)})
        for profile in PROFILES
    }
    return (
        {name: one.containers for name, one in specs.items()},
        {name: one.memory_mib for name, one in specs.items()},
    )


def rendered() -> str:
    """The script as the module renders it today."""
    services, memory_mib = figures()
    return render_install(services=services, memory_mib=memory_mib)


def committed() -> str:
    """The script as it is checked in, read the way a client's server would receive it."""
    return SCRIPT.read_text(encoding="utf-8")


def test_the_committed_script_is_what_the_module_renders() -> None:
    """The one test the rendered shape exists for. A generated file checked into a repository
    is a copy that drifts, and this is what stops it: the file a fresh server fetches is the
    plan this suite tests, or the suite is red.

    Delete this and the plan and the shipped script part company, and the tested one is not the
    one that runs."""
    assert committed() == rendered()


def test_the_committed_script_has_unix_line_endings_and_nothing_else() -> None:
    """It is executed by /bin/bash on Linux, and a carriage return at the end of the shebang
    makes the kernel look for an interpreter whose name ends in one. CLAUDE.md records this
    breaking a shell script on the server already, from Python writing a file without
    `newline`.

    Delete this and a regeneration on Windows ships a script that fails on its first line with
    a message naming an interpreter nobody typed."""
    assert b"\r" not in SCRIPT.read_bytes()


def test_the_script_stops_on_an_error_an_unset_variable_and_a_failed_pipe() -> None:
    """`set -eu` alone lets a pipeline whose left-hand side failed report success, and the plan
    contains one where that matters: sed reading the environment file into psql. Without
    pipefail that step creates no role and says it did.

    Delete this and the option can be dropped in a regeneration, and the install reports a step
    it did not perform."""
    lines = committed().splitlines()

    assert lines[0] == "#!/bin/bash"
    assert "set -euo pipefail" in lines[:8]


def test_the_script_quotes_every_variable_it_expands_except_the_two_that_must_split() -> None:
    """An unquoted expansion of a value that came from a flag, a prompt or somebody else's
    /etc/os-release is a path with a space in it becoming two arguments. The two exceptions are
    declared with a reason each, so a third one is a finding rather than a habit.

    Delete this and a release tag with a space in it, or a console address somebody pasted with
    a trailing word, silently becomes a different command."""
    assert unquoted_expansions(committed()) == ()
    assert set(SPLIT_ON_PURPOSE) == {"BRAIN_COMPOSE_FILES", "BRAIN_OS_ID"}


def test_an_unquoted_expansion_is_found_when_there_is_one() -> None:
    """The sibling of the test above, and without it that one is satisfied by a scanner that
    finds nothing anywhere. Both forms are checked, because `${NAME}` is the one a regular
    expression written for `$NAME` misses.

    Delete this and the guarantee above becomes a function that returns an empty tuple."""
    assert unquoted_expansions("cp $BRAIN_RELEASE /tmp")
    assert unquoted_expansions("cp ${BRAIN_RELEASE} /tmp")
    assert unquoted_expansions('x="$(cat $BRAIN_RELEASE)"')
    assert unquoted_expansions('cp "$BRAIN_RELEASE" /tmp') == ()


def test_a_dollar_inside_single_quotes_or_arithmetic_is_not_an_expansion() -> None:
    """The plan reads total memory with `awk '/MemTotal/ {print int($2 / 1024)}'`, and awk's
    own `$2` inside single quotes expands nothing at all. Arithmetic is the same kind of
    context: `$(( $N + 1 ))` expands a variable into a number and there is no word for a space
    to split. A scanner that counted quotes across the line would report the installer's own
    memory check and its own refusal counter as defects, which is how a check comes to be
    switched off rather than obeyed.

    Delete this and the quoting scanner is one false finding away from being deleted itself."""
    assert unquoted_expansions("awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo") == ()
    assert unquoted_expansions("N=$((N + 1))") == ()
    assert unquoted_expansions("N=$(( $BRAIN_REFUSALS + 1 ))") == ()
    assert unquoted_expansions("N=$( $BRAIN_REFUSALS )")


def test_every_requirement_of_a_server_is_asked_of_the_server() -> None:
    """A requirement in `RUNTIME_REQUIREMENTS` that no check asks about is a paragraph: it is
    documented, believed, and never tested on a single machine, and the install fails later as
    something that reads as a different fault.

    Delete this and a seventh requirement is added to the list and to no script, and the first
    machine without it is discovered by a client."""
    assert requirements_without_a_check() == ()
    assert checks_without_a_requirement() == ()
    assert len(CHECKS) == len(RUNTIME_REQUIREMENTS)


def test_every_requirement_reaches_the_rendered_script_with_the_reason_it_exists() -> None:
    """A refusal naming what is missing and not why is one somebody works around in ten
    minutes. The reason is read out of the requirement rather than retyped, so this asserts the
    requirement's own sentence is in the script, which is what fails when somebody writes a
    second copy of it.

    Delete this and the reasons drift out of the refusals one edit at a time, and the module
    that owns them goes on being correct while the script nobody reads goes on being wrong."""
    script = committed()

    for one in RUNTIME_REQUIREMENTS:
        assert as_shell_text(one.why) in script, one.what


def test_a_refusal_carries_the_minimum_version_when_the_requirement_states_one() -> None:
    """Two requirements state a version and four do not. A refusal that said "or newer is
    needed" with no number, or that stated a number for a requirement that has none, would be
    the refusal a person cannot act on.

    Delete this and the minimum can fall out of the refusal, leaving a person told their
    Docker is too old and not told what would be new enough."""
    engine = refusal("Docker Engine", "this machine runs $BRAIN_ENGINE")
    openssl = refusal("openssl", "openssl is not installed")

    assert "24.0 or newer is needed" in engine
    assert "or newer is needed" not in openssl


def test_a_requirement_nobody_declared_cannot_be_refused_over() -> None:
    """`refusal` reads `RUNTIME_REQUIREMENTS`, and a name that is not in it is a refusal with
    an empty reason in place of the sentence that stops somebody waiving it.

    Delete this and a typo in a requirement's name ships as a machine turned away for no stated
    reason."""
    with pytest.raises(InstallScriptError):
        refusal("a requirement nobody declared", "found nothing")


def test_a_check_that_cannot_refuse_is_refused_when_it_is_written() -> None:
    """A refusing check whose shell never calls `refuse` passes on every machine, including the
    ones it exists to turn away, and reads exactly like one that works. Refused at construction
    rather than at review, which is the argument `Step` already makes about a step that cannot
    say when it is done.

    Delete this and a check can be written that reports on a machine and never stops one."""
    with pytest.raises(InstallScriptError):
        Check(requirement="openssl", run='say "openssl might be missing"')
    with pytest.raises(InstallScriptError):
        Check(requirement="openssl", run='refuse "gone"', refuses=False)
    with pytest.raises(InstallScriptError):
        Check(requirement="openssl", run="   ")
    # The advisory case is the one a sibling guard does not cover: an empty run with
    # `refuses=True` is caught by the refusal check above whether or not this guard exists,
    # so without this line the guard on an empty shell is invisible.
    with pytest.raises(InstallScriptError):
        Check(requirement="openssl", run="   ", refuses=False)


def test_a_check_that_works_is_still_accepted() -> None:
    """The positive sibling of the refusals above. A guard tested only by what it rejects is
    satisfied by one that rejects everything, and a `Check` that refused every declaration
    would take the whole script with it.

    Delete this and the three refusals above are satisfied by a constructor that never
    succeeds."""
    asking = Check(requirement="openssl", run='command -v openssl || refuse "no openssl"')
    telling = Check(requirement="openssl", run='say "note: something"', refuses=False)

    assert asking.refuses
    assert not telling.refuses


def test_the_reverse_proxy_is_the_one_requirement_that_tells_rather_than_refuses() -> None:
    """Nothing running on the server can see the machine in front of it, so the check for the
    proxy is a sentence. A check that claimed to have verified it would be worse than one that
    says it cannot, because it is the requirement whose absence leaves a complete install
    reachable from nowhere.

    Delete this and either the proxy check starts refusing every correct install, or it
    quietly stops being mentioned at all."""
    proxy = [one for one in CHECKS if not one.refuses]

    assert [one.requirement for one in proxy] == ["a reverse proxy terminating TLS on 443"]
    assert "443" in committed()


def test_the_script_runs_the_plans_steps_in_the_plans_order() -> None:
    """The script is a printout of a plan, and this is the only thing that says so. A step
    reordered in the rendering mints credentials before the environment file exists; a step
    dropped leaves an install one step short and reporting success.

    Delete this and the renderer can quietly skip a step, and every other test here goes on
    passing because they all read the same script."""
    headings = HEADING.findall(committed())

    assert [name for _, _, name in headings] == [one.name for one in install_plan()]
    assert [int(number) for number, _, _ in headings] == list(range(1, len(headings) + 1))
    assert {int(total) for _, total, _ in headings} == {len(install_plan())}


def test_the_plan_is_the_installers_plan_with_the_machine_at_the_front() -> None:
    """`brain.deployment.installer.PLAN` is read by the update script, by the release archive's
    file list and by the manual sequence in the guide. This script adds to it rather than
    editing it, so those three are describing the same install they were describing before.

    Delete this and a prerequisite step added here can be moved into PLAN, which starts the
    update script installing Docker on a server that already has it."""
    plan = install_plan()

    assert plan[: len(PREPARE)] == PREPARE
    assert plan[len(PREPARE) : len(PREPARE) + len(PLAN)] == tuple(PLAN)
    assert plan[len(PREPARE) + len(PLAN) :] == HANDOVER


def test_every_step_that_writes_something_can_say_when_it_is_already_done() -> None:
    """Safe to run twice is a property of every step rather than of the script. There is no
    Docker on this machine, so the evidence is the guard the step carries: a changing step with
    no `already_done` repeats itself on the second run.

    Delete this and a step that writes can be added with no guard, and the second run of the
    installer mints a second database password beside a volume holding the first."""
    for one in install_plan():
        assert one.changes == bool(one.already_done.strip()), one.name


def test_the_script_guards_every_changing_step_and_skips_it_out_loud() -> None:
    """The guard has to reach the script, and it has to say it skipped. A second run that
    silently did nothing is indistinguishable at the terminal from one that silently did it
    again, and the person deciding whether to worry is reading the terminal.

    Delete this and the renderer can drop the guard while every step still declares one."""
    script = committed()
    changing = [one for one in install_plan() if one.changes]

    assert script.count("- already done, skipping") == len(changing)
    for one in changing:
        assert f"if {one.already_done}; then" in script, one.name


def test_the_second_run_mints_nothing_and_the_guard_is_keyed_on_a_credential() -> None:
    """The sharpest guard in the plan, asserted here because this script is the thing that runs
    it twice. Keyed on the file existing it would mint nothing on an install whose environment
    file arrived first, and keyed on nothing it writes a new database password beside a volume
    that still holds the old one.

    Delete this and a rewording of the guard can move it onto the file, and the failure is a
    stack that comes up unable to authenticate to its own data."""
    minting = next(one for one in install_plan() if one.name == "mint this installation's secrets")

    assert "POSTGRES_PASSWORD" in minting.already_done
    assert minting.already_done in committed()


def test_docker_is_not_installed_a_second_time_and_can_be_declined() -> None:
    """The one step that installs packages, and both halves of its guard. It skips on a machine
    that already has Docker with the compose plugin, and it skips on any machine when the
    person passed the flag saying they will install it themselves.

    Delete this and re-running the installer on a working server adds Docker's package
    repository again, and --no-install-docker becomes a flag that is parsed and ignored."""
    step = next(one for one in install_plan() if one.name == "install docker if it is missing")

    assert 'test "$BRAIN_INSTALL_DOCKER" = "no" ||' in step.already_done
    assert "command -v docker" in step.already_done
    assert "docker compose version" in step.already_done


def test_an_unrecognised_distribution_is_told_exactly_what_to_do() -> None:
    """The half of the Docker step that is not an install. A script that could not recognise a
    machine and said only that it had failed would leave a person with a working server, a
    documented product and nothing to type.

    Delete this and the unknown-distribution path becomes a refusal with no instruction in
    it."""
    script = committed()

    assert DOCKER_DOCUMENTATION_URL in script
    for name in (*DOCKER_APT_ROUTES, *DOCKER_DNF_ROUTES):
        assert name in script, name
    assert "docker-compose-plugin" in script


def test_dockers_own_addresses_are_declared_at_the_top_of_the_file_once() -> None:
    """The client-independence sweep refuses a URL to a host nothing declares, and it is right
    to: an address written into a function body is indistinguishable from one client's. Docker
    is where Docker is for every client this system will ever have, so it is declared the way a
    connector declares a vendor, and `brain.ops.independence.vendor_hosts` reads it from there.

    Delete this and the addresses drift back into the step that renders them, where the sweep
    cannot tell them from a value belonging to somebody's company."""
    from brain.ops.independence import vendor_hosts

    declared = vendor_hosts(REPO)

    assert "download.docker.com" in declared
    assert "docs.docker.com" in declared
    assert DOCKER_PACKAGES_URL.startswith("https://download.docker.com/")


def test_the_installer_never_pipes_a_downloaded_script_into_a_shell() -> None:
    """The route that was rejected: `curl https://get.docker.com | sh` is one line, it is
    Docker's own script, and Docker's own documentation says not to use it in production. The
    per-distribution routes are in the script instead, where a person can read what will run on
    their machine before it does.

    Delete this and the rejected design can come back as the fix for the next distribution
    nobody has a route for."""
    script = committed()

    assert "get.docker.com" not in script
    assert not re.search(r"curl[^\n|]*\|\s*(sh|bash)\b", script)


def test_only_the_step_that_hands_over_the_setup_code_prints_a_value() -> None:
    """The installer mints five values on the client's own machine and prints one of them. A
    script that echoed what it set has put a database password in a terminal scrollback and,
    under tee or CI, in a file nothing sweeps.

    Delete this and a step added to the plan can print a credential, because `Step` only
    refuses one that has not declared itself the exception."""
    leaking = [one.name for one in install_plan() if value_leaks_in(one.run)]

    assert leaking == ["present the setup code, once"]
    # The vault's unseal pieces are the second declared exception, and the name check cannot see
    # them: see `test_deployment_installer.py` and `test_vault_setup.py`.
    assert [one.name for one in install_plan() if one.presents_once] == [
        "initialise the secrets vault and show its unseal pieces, once",
        *leaking,
    ]


def test_the_rendered_script_puts_exactly_one_credential_in_front_of_a_person() -> None:
    """The same claim asserted about the script rather than about the plan, because the
    rendering is where a preamble, a usage message and a handover line get added and none of
    them is a `Step`. The handover says where to go and never repeats the value.

    Delete this and the preamble or the usage message can start printing a secret, and every
    test above goes on passing because they all read the plan."""
    printing = value_leaks_in(committed())

    assert len(printing) == 1
    assert "BRAIN_SETUP_SECRET" in printing[0]


def test_the_handover_never_invents_an_address_it_could_not_know() -> None:
    """Nothing in this deployment publishes a port, so there is no address to fall back to. A
    last line reading http://localhost:8000 would send the person to something that answers
    nothing, and they would spend the next twenty minutes deciding whether the install failed.

    Delete this and a helpful default address gets added, and it is wrong on every install."""
    script = committed()

    assert "localhost:8000" not in script
    assert "127.0.0.1:8000" in script  # the readiness probe, inside the app container
    assert "/first-run" in script
    assert 'if test -n "$BRAIN_CONSOLE_ADDRESS"; then' in script


def test_the_release_tag_is_required_and_latest_is_refused() -> None:
    """A default of `latest` is what makes an install unpinned: the next pull changes the
    version with nobody deciding anything. Refused here in the same words the update script
    refuses it, because an install that starts unpinned cannot be pinned by an update.

    Delete this and the tag acquires a default, and two servers installed on two days run two
    different releases and both report the same one."""
    script = committed()

    assert "--release is required and there is deliberately no default" in script
    assert 'test "$BRAIN_RELEASE" != "latest" ||' in script


def test_a_prompt_is_never_reached_when_there_is_no_terminal_to_ask_at() -> None:
    """Both prompts exist for a person on a fresh server, and both would block for ever in a
    deployment pipeline. The profile names the flag it wanted and stops; the console address is
    optional and is simply not asked for.

    Delete this and an install driven over ssh with no tty hangs on a question nobody sees."""
    script = committed()

    assert 'test -t 0 || fail "$2"' in script
    assert 'if test -z "$BRAIN_CONSOLE_ADDRESS" && test -t 0; then' in script
    assert "Pass --profile with one of" in script


def test_every_flag_the_script_parses_is_in_the_usage_message() -> None:
    """A flag that is parsed and undocumented is one only its author can use, and a flag
    documented and unparsed fails with "unknown option" for somebody following the usage
    message the script itself printed.

    Delete this and the two lists drift, and the first person to notice is the one reading the
    usage."""
    script = committed()
    parsed = set(re.findall(r"^\s{4}(--[a-z-]+)[|)]", script, re.MULTILINE))

    assert parsed == {flag for flag, _ in FLAGS}
    for flag, meaning in FLAGS:
        assert f"  {flag}" in script
        assert meaning in script


def test_the_release_archive_address_is_read_under_the_name_the_other_scripts_read() -> None:
    """Three scripts run on one server by one person, and a value spelled two ways is a value
    somebody sets twice and gets wrong once. It is demanded in the preamble rather than in a
    step, so a run with it unset stops before anything is written.

    Delete this and the installer reads one name and the update script another."""
    script = committed()

    assert RELEASE_URL_VARIABLE == "BRAIN_RELEASE_URL"
    assert f'BRAIN_RELEASE_URL="${{{RELEASE_URL_VARIABLE}:?' in script


def test_every_profile_has_an_arm_carrying_its_files_its_count_and_its_memory() -> None:
    """The profile is chosen at the terminal and recorded nowhere, so all three of a profile's
    figures are spelled out and they come from one `ServerSpec`. Split across arms, a script
    could pin one profile's memory ceiling against another's file list and refuse a machine
    that was large enough.

    Delete this and a fourth profile appears in the product with no arm here, and installing it
    composes nothing."""
    script = committed()
    services, memory_mib = figures()

    for profile in PROFILES:
        arm = next(line for line in script.splitlines() if line.startswith(f"  {profile})"))
        assert f'BRAIN_SERVICES="{services[profile]}"' in arm
        assert f'BRAIN_MEMORY_MIB="{memory_mib[profile]}"' in arm
        for name in files_for(profile):
            assert f"-f /opt/brain/{name}" in arm


def test_a_profile_with_no_measured_figures_is_refused_rather_than_rendered() -> None:
    """A profile arm with no memory figure is an install onto a machine nothing measured, and
    the `-u` in the preamble would turn it into an unset variable at the memory check rather
    than a refusal anybody can read.

    Delete this and a profile added to `PROFILES` and to no specification renders a script that
    fails halfway through, on a server, with a shell message."""
    services, _ = figures()

    with pytest.raises(InstallScriptError):
        render_install(services=services, memory_mib={})


def test_a_backtick_in_a_requirements_reason_is_escaped_rather_than_run() -> None:
    """Docker Engine's stated reason names the Compose specification's `deploy` block in
    backticks, and a backtick inside a double-quoted shell string is a command substitution.
    Unescaped, a machine being turned away for an old engine would run `deploy` while being
    told why.

    Delete this and the next requirement written with Markdown in it becomes a command."""
    assert as_shell_text("the `deploy` block") == r"the \`deploy\` block"
    assert as_shell_text('a "quoted" word') == r"a \"quoted\" word"
    assert "`" not in re.sub(r"\\`", "", committed())


def test_the_script_is_valid_shell() -> None:
    """A test asserting the text of a script is satisfied by a script that will not run, which
    is the argument `test_deployment_installer.py` and `test_deployment_release.py` both make.
    This one is executed on a machine with nothing on it, where there is no working system to
    debug the failure with.

    Delete this and a quoting mistake in a refusal ships as an installer that fails on the line
    that was supposed to explain something."""
    shell = shutil.which("bash")
    if shell is None:  # pragma: no cover - CI runs on Linux, where bash exists
        pytest.skip("no bash on this machine to check the rendered script's syntax with")
    checked = subprocess.run(
        [shell, "-n"], input=committed(), capture_output=True, text=True, check=False, timeout=60
    )

    assert checked.returncode == 0, checked.stderr


def test_shellcheck_has_nothing_to_say_about_the_script() -> None:
    """The check this suite cannot write for itself. `unquoted_expansions` answers one question
    about quoting and shellcheck answers about fifty more, including the ones nobody here
    thought to ask.

    It skips rather than fails when shellcheck is absent, and the skip says so out loud, which
    is the difference between a gate that is not installed and a gate that passed.

    Delete this and the script loses the only review of it that was not written by the person
    who wrote the script."""
    tool = shutil.which("shellcheck")
    if tool is None:
        pytest.skip(
            "shellcheck is not installed on this machine, so the script's quoting is held only "
            "by test_the_script_quotes_every_variable_it_expands_except_the_two_that_must_split "
            "and by bash -n"
        )
    checked = subprocess.run(  # pragma: no cover - runs only where shellcheck is installed
        [tool, "--shell=bash", "--severity=warning", "-"],
        input=committed(),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    assert checked.returncode == 0, checked.stdout  # pragma: no cover


def test_the_archive_carries_the_script_and_no_step_of_the_install_reads_it() -> None:
    """The copy inside the archive is never how anybody obtains this script, because running
    the script is what fetches the archive. It is carried as the record of what was run, and so
    that somebody re-running the installer after an update runs the one belonging to the
    release on that server rather than whichever is newest.

    Delete this and the include can be dropped, and a server ends up holding a release it
    cannot say which installer produced."""
    from brain.deployment.release import included_by, install_needs, refused_by

    assert included_by(SCRIPT_PATH)
    assert not refused_by(SCRIPT_PATH)
    assert SCRIPT_PATH not in install_needs()


def test_the_steps_that_check_the_machine_write_nothing() -> None:
    """The first step and the last are checks, and a check that wrote something would be a step
    that had changed a machine it then refused. "Nothing has been written" is what its refusal
    says, and this is what makes that sentence true.

    Delete this and a check can acquire a side effect, and a machine turned away has been
    edited."""
    checking = ("check this machine can run it", "check the docker on this machine is new enough")

    for name in checking:
        step = next(one for one in install_plan() if one.name == name)
        assert not step.changes
        assert not step.already_done
        assert "Nothing has been written" in step.on_failure


def test_every_step_says_what_to_do_when_it_fails() -> None:
    """`Step` requires the sentence and this asserts it is an instruction rather than a
    restatement. A person at a fresh server reading "the command exited 1" has been told
    nothing they did not watch happen.

    Delete this and an added step can carry a failure line that names the error and no
    action."""
    for one in install_plan():
        assert one.on_failure.strip()
        assert one.why.strip()


def test_the_handover_step_prints_and_changes_nothing() -> None:
    """It runs after the step that presents the setup code, and it is separate from it so that
    `presents_once`, which is the exemption from the leak check, sits on the smallest possible
    step rather than on one that also prints three paragraphs of prose.

    Delete this and the handover can be folded into the exempted step, which widens the one
    hole in the leak check from one line to a paragraph."""
    assert len(HANDOVER) == 1
    assert not HANDOVER[0].changes
    assert not HANDOVER[0].presents_once
    assert value_leaks_in(HANDOVER[0].run) == ()


def test_a_step_is_still_refused_when_it_writes_and_cannot_say_it_is_done() -> None:
    """The positive control for every idempotence claim above. All of them read `already_done`,
    and all of them are satisfied by a `Step` that accepts anything.

    Delete this and the guard that makes "safe to run twice" enforceable is untested here, and
    this module is the one that runs the script twice."""
    with pytest.raises(Exception, match=r"already done|run twice|repeats"):
        Step(
            name="write something",
            run="touch /opt/brain/thing",
            why="it needs to exist",
            on_failure="make the directory writable",
            changes=True,
        )


def test_an_apostrophe_in_a_comment_does_not_hide_the_expansions_after_it() -> None:
    """The step headings are comments and carry prose, and the scanner read the apostrophe in
    `mint this installation's secrets` as an opening quote until the next one, so every expansion
    between the two went unread. Found when the vault steps added an odd number of apostrophes and
    the scanner reported quoted expansions as unquoted. Delete this and the scanner can go back to
    reading comments, which hides unquoted expansions as readily as it invents them."""
    assert unquoted_expansions('# the installation\'s secrets\necho "$A"\n', allowed={}) == ()
    found = unquoted_expansions("# the installation's secrets\necho $A\n", allowed={})
    assert len(found) == 1
    assert found[0].startswith("$A ")
    assert unquoted_expansions('echo "${#A}" "$#"\n', allowed={}) == ()
