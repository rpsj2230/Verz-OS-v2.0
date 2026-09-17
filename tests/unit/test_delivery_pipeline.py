"""The path from a merge to a running container, read as data.

Every property here is one that fails silently when it stops holding. An image that stops
being signed still deploys. A rollback step deleted still leaves a green workflow. A
readiness gate removed makes deploys *faster*, and the first sign of trouble is a container
serving requests against a schema it does not match.

Parsed rather than grepped throughout: a substring search over YAML matches a commented-out
line as happily as a live one, and a commented-out deploy gate is precisely what this file
exists to catch.

The rollback behaviour itself is not asserted here. It lives in `ops/test-watch-and-deploy.sh`,
which drives the real script against a stubbed docker through six failure scenarios, because
a rollback is a sequence of decisions and not a line in a file.

Task ids: M0.5.3, M38.1.1.3, M38.1.2.2, M38.1.2.3, M38.1.2.4, M38.1.2.5, M38.1.3.1,
M38.1.3.2, M38.1.3.3, M38.1.3.4, M38.1.4.1, M38.1.4.3, M38.2.2.1, M30.2.2, M30.2.3, M30.2.4
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
import yaml

from brain.deployment.installer import PRODUCT_IMAGE

REPO = Path(__file__).resolve().parents[2]


def _workflow(name: str) -> dict[Any, Any]:
    parsed: dict[Any, Any] = yaml.safe_load(
        (REPO / ".github" / "workflows" / name).read_text(encoding="utf-8")
    )
    return parsed


def _steps(workflow: str, job: str) -> list[dict[str, Any]]:
    return list(_workflow(workflow)["jobs"][job].get("steps", []))


def _text_of(workflow: str, job: str) -> str:
    return "\n".join(
        str(step.get("run", "")) + " " + str(step.get("uses", "")) + " " + str(step.get("with", ""))
        for step in _steps(workflow, job)
    )


def _watcher() -> str:
    return (REPO / "ops" / "watch-and-deploy.sh").read_text(encoding="utf-8")


def _live(script: str) -> str:
    """A shell script with its comment lines removed.

    Everything in this file that reads a script rather than YAML needs this. A gate that has
    been commented out keeps every word it had, so a substring search cannot tell a command
    from an explanation of the command, and the explanation is usually left behind.
    """
    return "\n".join(
        line.split(" # ")[0] for line in script.splitlines() if not line.lstrip().startswith("#")
    )


def _compose(name: str) -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load((REPO / name).read_text(encoding="utf-8"))
    return parsed


# ------------------------------------------------------- building (M38.1.2.3, M38.1.2.5)
def test_the_image_is_tagged_with_the_commit_and_not_only_latest() -> None:
    """`latest` is a moving target: it names whatever was built most recently, so "roll back
    to the version before this one" has no answer once it has moved. A tag carrying the
    commit means every build stays addressable for as long as the registry keeps it."""
    build = next(s for s in _steps("deploy.yml", "build") if s.get("id") == "build")
    tags = str(build["with"]["tags"])
    assert "${{ steps.meta.outputs.sha }}" in tags
    assert "latest" in tags


def test_the_build_receives_the_commit_so_the_image_knows_what_it_is() -> None:
    """An image that cannot say which commit produced it is one nobody can match against a
    bug report. This is passed at build time rather than set at run time because a runtime
    variable can be overridden by whatever starts the container - and on this deployment it
    was, to the literal string `unknown`."""
    build = next(s for s in _steps("deploy.yml", "build") if s.get("id") == "build")
    assert "COMMIT_SHA=${{ steps.meta.outputs.sha }}" in str(build["with"]["build-args"])


def test_the_image_is_pushed_to_the_registry() -> None:
    build = next(s for s in _steps("deploy.yml", "build") if s.get("id") == "build")
    assert build["with"]["push"] is True
    assert "ghcr.io" in str(_workflow("deploy.yml")["env"]["REGISTRY"])


# ------------------------------------------------------------------- signing (M38.1.2.4)
def test_the_image_the_pipeline_pushes_is_the_image_the_server_pulls() -> None:
    """**Four files name one image and nothing held them equal.**

    The workflow published to `ghcr.io/${{ github.repository }}` while the compose file, the
    deploy script and the watcher each wrote `ghcr.io/rpsj2230/verz-brain-v2.0` by hand. That
    agreed for as long as nobody renamed the repository, and on 2026-09-06 somebody did:
    `verz-brain-v2.0` became `Verz-OS-v2.0` and the next push failed with `invalid tag
    "ghcr.io/rpsj2230/Verz-OS-v2.0:79204c6": repository name must be lowercase`.

    **The red build was luck, and the luck is the reason this test exists.** The new name
    happened to contain capital letters, which Docker refuses outright. A rename to a
    lowercase name would have built cleanly, pushed to a package nothing pulls, reported
    success, and left the server running the last image built under the old name with every
    check green. This repository has already had that exact failure once, when production sat
    fourteen commits behind because Deploy was conditional on CI.

    Compared as a set rather than pairwise, so a fifth file naming the image is covered the
    day it is added rather than the day somebody remembers to extend a chain of assertions.

    Delete this and the pipeline can publish to one address while the server pulls from
    another, which is invisible from both ends: the build is green because it pushed, and the
    server is healthy because it is running something."""
    published = str(_workflow("deploy.yml")["env"]["IMAGE"])
    compose = str(_compose("docker-compose.yml")["services"]["app"]["image"])
    script = (REPO / "ops" / "deploy.sh").read_text(encoding="utf-8")
    watcher = (REPO / "ops" / "deploy" / "brain-autodeploy").read_text(encoding="utf-8")

    # The compose file names no image since Needs Rupash item 51: `${APP_IMAGE:?...}` is
    # required, and the name is declared once in `brain.deployment.installer`. So the
    # pipeline is held to that declaration, and the compose file to reading the variable.
    assert published == PRODUCT_IMAGE, f"the product is {PRODUCT_IMAGE}, CI pushes {published}"
    assert compose.startswith("${APP_IMAGE:?"), f"compose chooses its image as {compose}"
    assert published in script, "ops/deploy.sh names an image the pipeline does not publish"
    assert published in watcher, "the watcher pulls an image the pipeline does not publish"


def test_the_published_image_is_a_name_docker_will_accept() -> None:
    """A container repository must be lowercase, and the one thing that reliably introduces a
    capital letter is a person naming a GitHub repository after a product.

    Asserted on the value rather than trusted to review, because the symptom is a failed
    build at the end of a pipeline rather than anything visible in the file. It cost a red
    deploy to learn once.

    Delete this and the image name can acquire a capital the next time it is edited, and the
    failure arrives minutes later in somebody else's log."""
    published = str(_workflow("deploy.yml")["env"]["IMAGE"])

    assert published == published.lower(), (
        f"{published} is not a legal container repository; Docker refuses it with "
        "'repository name must be lowercase' at the end of the build"
    )


def test_the_image_name_does_not_move_when_the_repository_is_renamed() -> None:
    """The distinction this whole group turns on: `github.repository` is right in one place
    in this workflow and wrong in another.

    In the cosign identity it is correct and must stay, because that asserts where the
    workflow ran, and after a rename the workflow genuinely does run from the new name. In
    the image it is wrong, because that is a coordinate the server resolves, and the server
    is not renamed when the repository is.

    Delete this and the expression comes back the next time somebody tidies a hardcoded
    string out of a workflow, which is a reasonable-looking change that breaks deployment
    the next time the repository is renamed and not before."""
    published = str(_workflow("deploy.yml")["env"]["IMAGE"])

    assert "github.repository" not in published, (
        "the image is derived from the repository name again, so a rename will publish it "
        "somewhere the server does not look; see the cosign step for where that expression "
        "is correct"
    )
    # The positive sibling: the identity really does still use it, so this is a statement
    # about which of the two uses is right rather than a ban on the expression.
    assert "github.repository" in _text_of("deploy.yml", "build")


def test_the_image_is_signed() -> None:
    """Unsigned, "the registry has an image with this digest" is the only claim anybody can
    make about what is running. Signed, the claim is that this build came out of this
    workflow, which is the thing a person actually wants to know before trusting it."""
    assert "cosign sign" in _text_of("deploy.yml", "build")
    assert "sigstore/cosign-installer" in _text_of("deploy.yml", "build")


def test_what_is_signed_is_the_digest_and_never_the_tag() -> None:
    """A tag is a moving pointer. Signing `:latest` attests to whatever it points at today,
    which is exactly the thing an attacker moves; the digest *is* the image.

    Asserted on the argument rather than on the step existing, because a signing step that
    signs the wrong thing passes every check that only asks whether signing happens - and it
    is one character of difference in a shell line nobody reads twice."""
    sign = next(s for s in _steps("deploy.yml", "build") if "Sign" in str(s.get("name", "")))
    run = str(sign["run"])
    assert "@${DIGEST}" in run
    assert ":latest" not in run
    assert ":${{ steps.meta.outputs.sha }}" not in run


def test_the_verification_is_pinned_to_this_repository() -> None:
    """`cosign verify` with no identity constraint accepts a signature made by anybody at
    all, which is worse than not verifying: it produces a green tick meaning nothing.

    Both flags are needed. The issuer alone accepts any GitHub workflow anywhere; the
    identity alone would accept a certificate from a different issuer claiming the same
    name."""
    verify = next(s for s in _steps("deploy.yml", "build") if "Verify" in str(s.get("name", "")))
    run = str(verify["run"])
    assert "--certificate-identity-regexp" in run
    assert "github.com/${{ github.repository }}" in run
    assert "--certificate-oidc-issuer" in run


def test_signing_is_keyless() -> None:
    """A private signing key has to live somewhere, be rotated, and be revocable, and the
    somewhere is usually a repository secret that several people can read. Keyless binds the
    signature to this workflow's OIDC identity instead, so there is no key to steal.

    `id-token: write` is what makes it possible; without that permission cosign has nothing
    to prove who signed and silently wants a key file."""
    assert _workflow("deploy.yml")["permissions"]["id-token"] == "write"
    text = _text_of("deploy.yml", "build")
    assert "--key" not in text, "a key file appeared; keyless signing was replaced"


def test_the_signature_is_verified_in_the_same_run_that_made_it() -> None:
    """A signature nobody ever checks is a signature that can be silently broken. Verifying
    immediately catches a misconfigured signer on the build that introduced it, rather than
    on the day somebody first tries to verify and finds nothing was ever right."""
    names = [str(s.get("name", "")) for s in _steps("deploy.yml", "build")]
    signed = next(i for i, n in enumerate(names) if "Sign" in n)
    verified = next(i for i, n in enumerate(names) if "Verify" in n)
    assert signed < verified


# --------------------------------------------------- deploying (M38.1.3.1, M38.1.3.2)
def test_a_red_build_never_reaches_the_server() -> None:
    """The workflow fires on CI *completing*, not on CI passing - `workflow_run` runs
    whatever the outcome. Without the explicit conclusion check, a failing test suite
    deploys."""
    job = _workflow("deploy.yml")["jobs"]["build"]
    assert "github.event.workflow_run.conclusion == 'success'" in str(job["if"])


#: The step that asks the live site which commit it serves, and the only thing in the workflow
#: that can report a deploy as having happened.
LIVE_CHECK = "The site is actually serving this commit"


def test_the_deploy_waits_for_the_signature() -> None:
    """Counting a commit as deployed before its build has signed and verified it would mean the
    run reports as live the one build nobody has verified.

    Asserted as a job dependency rather than as step order, because that is how it is
    actually arranged and it is the stronger arrangement: `needs` makes the whole build job
    - sign and verify included - a precondition, where step order inside one job could be
    rearranged by anybody adding a step in the wrong place.

    The deploy job triggers nothing since M30.2.4: the server pulls. So what waits on the build
    is the check that the site serves the commit, and it is asserted by name because a job that
    `needs` the build and has lost that step goes green having checked nothing."""
    jobs = _workflow("deploy.yml")["jobs"]
    assert jobs["deploy"]["needs"] == "build"
    signing = [str(s.get("name", "")) for s in _steps("deploy.yml", "build")]
    assert any("Sign" in n for n in signing)
    assert any("Verify" in n for n in signing)
    assert any(str(s.get("name", "")) == LIVE_CHECK for s in _steps("deploy.yml", "deploy"))


# ------------------------------------------------ the server pulls, and nothing pushes (M30.2.4)
#: A stored credential for the deployment panel, as a workflow expression names one.
PANEL_CREDENTIAL = re.compile(r"\b(?:secrets|vars)\.COOLIFY_[A-Z_]+\b")

#: The deployment panel's deploy endpoint, which is what the removed step called.
PANEL_DEPLOY_ENDPOINT = "/api/v1/deploy"


def _strings(node: Any) -> list[str]:
    """Every key and every scalar in a parsed document, as text.

    Parsed rather than read, so the comment in `deploy.yml` recording what was removed and why
    is not a finding; and keys as well as values, so a variable named for the panel is read
    even when the value beside it is innocuous.
    """
    if isinstance(node, dict):
        return [text for key, value in node.items() for text in (str(key), *_strings(value))]
    if isinstance(node, list):
        return [text for one in node for text in _strings(one)]
    return [str(node)]


def _panel_references(document: Any) -> list[str]:
    return [
        one
        for one in _strings(document)
        if PANEL_CREDENTIAL.search(one) or PANEL_DEPLOY_ENDPOINT in one
    ]


def test_no_workflow_holds_a_deployment_panel_credential_or_calls_its_api() -> None:
    """**M30.2.4, pull-based deployment so the server needs no inbound access.** The server's own
    timer pulls a new image and installs it, so no workflow needs a way into the server and
    none may hold one.

    The job this replaced read three repository secrets and called the panel's deploy endpoint.
    The secrets were empty on every run and the panel's port is firewalled, so it deployed
    nothing, and it was still the one thing asking for the panel to be reachable from GitHub's
    address ranges and for a token able to redeploy every container to be stored in GitHub.

    Delete this and the step can be put back to fix a deploy that is not broken, which reopens
    both."""
    workflows = sorted(
        [
            *(REPO / ".github" / "workflows").glob("*.yml"),
            *(REPO / ".github" / "workflows").glob("*.yaml"),
        ]
    )
    assert workflows, "no workflow was read, so this asserts nothing"

    found = {path.name: _panel_references(_workflow(path.name)) for path in workflows}

    assert {name: refs for name, refs in found.items() if refs} == {}


def test_the_panel_check_finds_a_credential_wherever_a_step_can_name_one() -> None:
    """The sibling that proves the check above can fail. A walk that skipped step `env` blocks,
    `run` scripts or mapping keys would pass every workflow here, including one that put the
    trigger back, so it is run against the removed step's own shapes, and against the real
    registry login it must see and must not report.

    Delete this and the refusal above can be satisfied by a walker that reads nothing."""
    token = "${{ secrets.COOLIFY_TOKEN }}"
    removed = {"jobs": {"deploy": {"steps": [{"name": "Deploy", "env": {"TOKEN": token}}]}}}
    called = {"jobs": {"deploy": {"steps": [{"run": 'curl -X POST "$U/api/v1/deploy?uuid=$I"'}]}}}
    keyed = {"env": {"${{ vars.COOLIFY_URL }}": "x"}}

    assert _panel_references(removed) == [token]
    assert _panel_references(called) == ['curl -X POST "$U/api/v1/deploy?uuid=$I"']
    assert _panel_references(keyed) == ["${{ vars.COOLIFY_URL }}"]
    assert "${{ secrets.GITHUB_TOKEN }}" in _strings(_workflow("deploy.yml"))
    assert _panel_references({"env": {"TOKEN": "${{ secrets.GITHUB_TOKEN }}"}}) == []


def _live_assignment(script: str, name: str) -> str:
    """The value a shell script assigns to `name`, read off its live lines only."""
    for line in _live(script).splitlines():
        match = re.fullmatch(rf'\s*{name}="([^"]*)"\s*', line)
        if match:
            return match.group(1)
    raise AssertionError(f"the script assigns no {name}")


def test_the_server_deploys_the_one_tag_only_a_passing_build_moves() -> None:
    """The CI gate survives the trigger's removal because of this and nothing else. The timer
    watches `:latest`, `:latest` is pushed only by the build job, and the build job runs only
    when CI succeeded, so the tag moving is the statement that the gate passed.

    Point the timer at a tag a person or another workflow can move and a red build reaches the
    server with nothing in the workflow to say so. The image test above compares the repository
    half only, and an image ending `:main` passes it. Delete this and the gate is a comment."""
    published = str(_workflow("deploy.yml")["env"]["IMAGE"])
    build = next(s for s in _steps("deploy.yml", "build") if s.get("id") == "build")
    tags = [one.strip() for one in str(build["with"]["tags"]).splitlines() if one.strip()]
    deploy_dir = REPO / "ops" / "deploy"
    watched = _live_assignment(
        (deploy_dir / "brain-autodeploy").read_text(encoding="utf-8"), "IMAGE"
    )
    deployed = _live_assignment((deploy_dir / "brain-deploy").read_text(encoding="utf-8"), "IMAGE")

    assert watched == f"{published}:latest"
    assert deployed == watched
    assert "${{ env.IMAGE }}:latest" in tags
    job = _workflow("deploy.yml")["jobs"]["build"]
    assert "github.event.workflow_run.conclusion == 'success'" in str(job["if"])


def _unit_lines(unit: str) -> list[str]:
    """A systemd unit as the lines systemd reads: comments and blank lines dropped."""
    return [
        line.strip()
        for line in unit.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _written_units(installer: str) -> dict[str, str]:
    """The units an install script writes, by file name, read out of its heredocs."""
    return {
        match.group(1): match.group(2)
        for match in re.finditer(
            r"^cat > /etc/systemd/system/(\S+) <<'UNIT'\n(.*?)^UNIT$", installer, re.M | re.S
        )
    }


def test_the_units_the_install_script_writes_are_the_units_this_repository_ships() -> None:
    """The timer reaches a server through heredocs inside `brain-install-autodeploy`, and the unit
    files beside it are what a reader, the checklist and `install_docs.scheduled_job_gaps` read.
    Two copies and nothing held them equal: change the interval in the file and the server keeps
    the old one while every document describes the new.

    Compared line by line with comments dropped, because the two copies explain themselves in
    different words and that is allowed; what systemd reads is not. The script must also switch
    the timer on and the service must run the pull script, or the install writes two files that
    do nothing. Delete this and the pull deploy is whichever copy was edited last."""
    deploy_dir = REPO / "ops" / "deploy"
    installer = (deploy_dir / "brain-install-autodeploy").read_text(encoding="utf-8")
    written = _written_units(installer)

    assert sorted(written) == ["brain-autodeploy.service", "brain-autodeploy.timer"]
    for name, unit in written.items():
        shipped = (deploy_dir / name).read_text(encoding="utf-8")
        assert _unit_lines(unit) == _unit_lines(shipped), name
    service = _unit_lines((deploy_dir / "brain-autodeploy.service").read_text(encoding="utf-8"))
    assert "ExecStart=/usr/local/bin/brain-autodeploy" in service
    assert "systemctl enable --now brain-autodeploy.timer" in _live(installer).splitlines()


def _seconds(value: str) -> int:
    match = re.fullmatch(r"(\d+)(min|s)", value)
    assert match, f"{value!r} is not a span this test reads"
    return int(match.group(1)) * (60 if match.group(2) == "min" else 1)


def test_the_live_check_outlasts_the_servers_pull_interval() -> None:
    """The check that the site serves this commit is the only thing in the workflow that can go
    red about a deploy now, so its patience has to fit the timer it waits on. Three intervals:
    the tick that just missed the push, the tick that sees it, and the deploy that tick starts,
    which the unit's own comment puts at a couple of minutes.

    A timer lengthened past that turns every healthy deploy into a red build, and a check that
    is red for a working system is one somebody deletes. The check also has to be waiting for
    the commit this run built rather than one it was told about. Delete this and the two numbers
    live in two files with a comment in each asserting they agree."""
    live = next(s for s in _steps("deploy.yml", "deploy") if s.get("name") == LIVE_CHECK)
    waited = re.search(r"deadline=\$\(\(SECONDS \+ (\d+)\)\)", str(live["run"]))
    assert waited, "the live check no longer states how long it waits"
    timer_path = REPO / "ops" / "deploy" / "brain-autodeploy.timer"
    timer = dict(
        line.split("=", 1)
        for line in _unit_lines(timer_path.read_text(encoding="utf-8"))
        if "=" in line
    )

    assert int(waited.group(1)) >= 3 * _seconds(timer["OnUnitActiveSec"])
    assert live["env"]["SHA"] == "${{ needs.build.outputs.sha }}"


def test_migrations_run_before_the_new_image_takes_traffic() -> None:
    """M38.1.3.2. Asserted where it actually happens, which is the application's own
    lifespan rather than the workflow: `run_migrations` is awaited before the readiness
    dictionary is populated, so an instance cannot report ready against a schema it has not
    finished changing.

    In the workflow it would be a separate container that has to be sequenced by hand. In
    the lifespan it is a line of Python that cannot be got wrong by ordering two YAML steps
    the wrong way round."""
    app = (REPO / "src" / "brain" / "app.py").read_text(encoding="utf-8")
    migrated = app.index("run_migrations, settings.migration_database_url")
    served = app.index("app.state.ready[DATABASE_PART] = await database_probe()")
    assert migrated < served


# ----------------------------------------------- the health gate (M38.1.3.3, M38.1.3.4)
def test_readiness_and_not_liveness_is_what_the_deploy_waits_for() -> None:
    """A container that is up but cannot reach its database passes liveness and answers
    questions from whatever it can still reach. That is the failure this whole distinction
    exists for, and gating on the wrong one makes it invisible."""
    watcher = _watcher()
    assert "/health/ready" in watcher
    assert "/health/live" in watcher  # used for the commit, not for the gate
    ready_at = watcher.index("wait_ready()")
    assert "/health/ready" in watcher[ready_at : ready_at + 600]


def test_a_failed_rollout_rolls_back_to_a_pinned_digest() -> None:
    """Not to `:latest`, which by then points at the broken build - rolling back to it would
    redeploy the thing that just failed and read as the rollback having worked."""
    watcher = _watcher()
    assert "PREVIOUS" in watcher
    assert "rolled_back" in watcher


def test_a_digest_that_keeps_failing_is_left_alone() -> None:
    """Without a ceiling the watcher retries a broken image every three minutes forever,
    and each attempt takes the service down for the length of a rollout. The failure count
    is keyed on the digest so a new build starts with a clean slate."""
    watcher = _watcher()
    assert "FAIL_LIMIT" in watcher


@pytest.mark.parametrize(
    "outcome", ["deployed", "rolled_back", "failed_no_rollback", "rollback_failed"]
)
def test_every_way_a_deploy_can_end_is_recorded(outcome: str) -> None:
    """Recording only the successes makes the record useless for the question it is kept
    for. "It has never gone wrong" and "we only write a line when it goes right" look
    identical in a file that contains only successes."""
    assert outcome in _watcher()


# -------------------------------------- the migration round trip (M0.5.3, M38.1.2.2)
def _migration_step() -> dict[str, Any]:
    """The CI step that exercises the migration, found by what it runs rather than by name.

    A step is located by its `run` containing `alembic`, so renaming the step does not break
    this and deleting the commands does.
    """
    steps = [
        step for step in _steps("ci.yml", "tests") if "alembic" in _live(str(step.get("run", "")))
    ]
    assert len(steps) == 1, f"expected one migration step in CI, found {len(steps)}"
    return steps[0]


def test_ci_takes_the_migrations_forward_back_and_forward_again() -> None:
    """A migration that cannot be reversed is a deploy with no way back, and a downgrade that
    raises is otherwise discovered at three in the morning by whoever is trying to use it.

    The second upgrade is not redundant: a migration that is not idempotent breaks the second
    replica rather than the first, which makes it a rollout failure rather than a deploy
    failure and sends somebody to look at the orchestrator.

    Asserted as an ordered sequence rather than as three memberships. Presence alone passes on
    `upgrade head` twice with the downgrade deleted, which is the exact half of the round trip
    that costs nothing to remove and proves nothing once removed.
    """
    run = _live(str(_migration_step()["run"]))
    order = [
        run.index("alembic upgrade head"),
        run.index("alembic downgrade base"),
        run.rindex("alembic upgrade head"),
    ]
    assert order == sorted(order), f"the round trip is out of order or incomplete: {run}"
    assert order[0] != order[2], "upgrade runs once; a non-idempotent migration would pass"


def test_the_round_trip_runs_in_every_shard_over_the_database_its_tests_filled() -> None:
    """**The order is the point, and it has already paid for itself.** On 2026-09-17 the round
    trip ran `alembic downgrade base` over the database the unit tests had just filled and
    stopped at `0059`, on a rollback every migration's docstring said was fine. A round trip
    over an empty database would have passed.

    The unit suite runs in shards since the same day, and each shard has a database of its
    own, so the round trip and the schema check run in the shard job after its tests, with no
    `if` to confine them to one shard: every shard's database is taken back and forward again
    after its own tests have written to it.

    Delete this and the migration step can move before the tests, or into a job of its own
    with an empty database, and CI goes back to proving a rollback on a database nobody uses.
    """
    steps = _steps("ci.yml", "tests")
    job = _workflow("ci.yml")["jobs"]["tests"]
    suite = [
        index
        for index, step in enumerate(steps)
        if any(
            line.split()[:3] == ["uv", "run", "pytest"]
            for line in _live(str(step.get("run", ""))).splitlines()
        )
    ]
    migration = steps.index(_migration_step())
    schema = [
        index
        for index, step in enumerate(steps)
        if "brain.ops.schema_check" in _live(str(step.get("run", "")))
    ]

    assert len(job["strategy"]["matrix"]["shard"]) > 1
    assert "postgres" in job["services"]
    assert len(suite) == 1 and len(schema) == 1
    assert suite[0] < migration < schema[0]
    assert "if" not in steps[migration], "the round trip is confined to some shards"
    assert "if" not in steps[schema[0]], "the schema check is confined to some shards"


def test_the_round_trip_asserts_it_landed_at_head_rather_than_trusting_the_exit_code() -> None:
    """`alembic downgrade` followed by `alembic upgrade` can leave the database at a revision
    that is not head without either command failing, because a branch point resolves to
    whichever head Alembic picks. The step therefore checks where it ended up.

    Deleting this leaves a round trip that reports success from a database in the wrong state,
    which is worse than not running it: the deploy afterwards believes the schema is current.
    """
    run = _live(str(_migration_step()["run"]))
    assert "alembic current" in run
    assert "(head)" in run


def test_the_database_ci_migrates_is_the_one_production_runs() -> None:
    """What makes the round trip evidence rather than exercise. Migration 0001 installs four
    extensions and creates a role with NOBYPASSRLS; both are properties of a specific
    PostgreSQL image, and neither is exercised by a different one.

    Compared against the deployed compose file rather than pinned to a literal, so upgrading
    production's database is one edit and CI follows. Deleting this lets CI drift onto stock
    `postgres:latest`, where `CREATE EXTENSION vector` fails and, worse, where it might not:
    an image without pgvector that happens to have it vendored would pass while proving
    nothing about the image production actually runs.
    """
    ci_image = _workflow("ci.yml")["jobs"]["tests"]["services"]["postgres"]["image"]
    deployed = _compose("docker-compose.yml")["services"]["db"]["image"]
    assert ci_image == deployed, (
        f"CI migrates against {ci_image} and production runs {deployed}; the round trip is "
        "no longer evidence about production's database"
    )


# ------------------------------------------------- the pre-push hook (M38.1.1.3)
#: The gates that must run before anything leaves the laptop, and the substring that proves
#: each one runs. Deliberately the same strings CI is asserted with in `test_ci_workflow`, so
#: the two lists cannot describe different gates while both look maintained.
LOCAL_GATES = (
    ("lint", "ruff check"),
    ("types", "mypy"),
    ("invariants", "pytest tests/invariants"),
)


@pytest.mark.parametrize(("gate", "command"), LOCAL_GATES)
def test_the_pre_push_hook_runs_the_same_gate_ci_does(gate: str, command: str) -> None:
    """A hook that runs a subset of CI is a hook that says "green" and then a queue that says
    red, which teaches people to ignore the hook. A hook that runs something CI does not is
    worse: the gate can be skipped with `--no-verify` and nothing behind it ever checks.

    So both places are asserted from one list. Deleting this lets the two drift, and drift is
    invisible: each file on its own still reads like a complete set of gates.
    """
    hook = _live((REPO / "ops" / "hooks" / "pre-push").read_text(encoding="utf-8"))
    assert command in hook, f"the pre-push hook no longer runs the {gate} gate"

    ci = "\n".join(
        _live(str(step.get("run", "")))
        for job in _workflow("ci.yml")["jobs"].values()
        for step in job.get("steps", [])
    )
    assert command in ci, f"the hook runs the {gate} gate and CI does not"


def test_the_hook_stops_the_push_when_it_cannot_run_the_gates() -> None:
    """The failure mode a hook has that a CI job does not. This one resolves `uv` by hand
    because git hooks inherit whatever environment git was launched from, and on Windows that
    is often not the shell where uv is on PATH.

    A hook that cannot find its tools and exits zero is worse than no hook: it prints nothing
    alarming, the push succeeds, and everybody believes the gates ran. Deleting this makes
    that a one-character change nobody reviews.
    """
    hook = _live((REPO / "ops" / "hooks" / "pre-push").read_text(encoding="utf-8"))
    assert "set -e" in hook, "a failing gate no longer stops the script"
    # Split on a line that is exactly `fi`, not on the substring: "cannot find uv" contains
    # one, which cut the branch in half and made this pass for the wrong reason.
    branch = hook[hook.index('if [ -z "$UV" ]') :]
    body = branch.split("\nfi\n")[0]
    assert "exit 1" in body, f"a missing uv lets the push through: {body}"


def test_the_hook_is_a_file_git_can_be_pointed_at_rather_than_one_it_finds() -> None:
    """`ops/hooks/` is not `.git/hooks/`, so this runs for nobody until `core.hooksPath` is
    set. The instruction has to live with the hook, because the person who needs it is the
    person who has just cloned and has not run it.

    Deleting this lets the line be tidied out of the header, after which the hook is a file
    in the repository that nothing executes and every reader assumes is running.
    """
    hook = (REPO / "ops" / "hooks" / "pre-push").read_text(encoding="utf-8")
    assert "core.hooksPath ops/hooks" in hook


# --------------------------------------------- the environment ladder (M38.1.4.1)
def test_the_stack_a_developer_runs_locally_is_the_stack_that_deploys() -> None:
    """`docker compose up` in this checkout, with no `-f`, resolves `docker-compose.yml`,
    which is the file Coolify deploys. One file means a local stack cannot drift from the
    deployed one, and that is the entire value of having local compose at all.

    Deleting this lets a service be dropped from the file that a developer runs and a
    dependency then be added against a component only production has.
    """
    services = _compose("docker-compose.yml")["services"]
    assert set(services) == {"app", "pgbouncer", "db", "cache"}
    # Through the pooler, locally as well. A developer connecting straight to Postgres would
    # never meet the prepared-statement and advisory-lock behaviour that only appears behind
    # a transaction pooler, which is where two bugs in this project have already lived.
    assert "pgbouncer" in services["app"]["environment"]["DATABASE_URL"]


@pytest.mark.parametrize(
    "override",
    [
        "docker-compose.override.yml",
        "docker-compose.override.yaml",
        "compose.override.yml",
        "compose.override.yaml",
    ],
)
def test_no_compose_file_is_applied_behind_the_developers_back(override: str) -> None:
    """Docker merges an override file automatically and says nothing about it. A committed
    one means the stack somebody runs is not the stack they are reading, which is where
    "works on my machine" comes from and why it is so hard to see.

    Deleting this makes committing one a change of four lines that nothing questions.
    """
    assert not (REPO / override).exists(), f"{override} is merged automatically and silently"


def test_the_local_stack_can_run_an_image_built_on_this_machine() -> None:
    """Without the override, `docker compose up` pulls the last published image and a
    developer debugs code they did not write. The symptom is that a change appears to have no
    effect, which sends people to look at their own code first.

    CI takes the same path, building `brain:ci` and setting `APP_IMAGE`, so this is the
    mechanism the `stack` job depends on rather than a convenience nobody uses.
    """
    image = str(_compose("docker-compose.yml")["services"]["app"]["image"])
    assert image.startswith("${APP_IMAGE:?"), f"the app image is fixed at {image}"
    stack_env = _workflow("ci.yml")["jobs"]["stack"]["env"]
    assert "APP_IMAGE" in stack_env


def test_the_database_password_has_no_default_in_any_profile() -> None:
    """The one variable deliberately left without a fallback. A default here is a password
    that works on a laptop, and a password that works on a laptop is the one that ends up on
    a server because nothing ever forced anybody to choose another.

    Compose fails loudly on an unset variable with no default, which is the desired
    behaviour: a local stack that will not start is better than one that starts with a known
    password. Deleting this makes adding `:-postgres` an obvious kindness.
    """
    for name in ("docker-compose.yml", "docker-compose.lite.yml", "docker-compose.staging.yml"):
        text = (REPO / name).read_text(encoding="utf-8")
        defaulted = re.findall(r"\$\{([A-Z_]*POSTGRES_PASSWORD):-", text)
        assert not defaulted, f"{name} gives {defaulted} a default value"


# ----------------------------- production deploys on every push, no tagging (M38.1.4.3)
def test_production_deploys_on_every_push_rather_than_on_a_tag() -> None:
    """Decision 22 on the Needs Rupash page, and it changed the plan rather than the code.
    The leaf originally read "deployed only from a tagged release that passed staging"; he
    asked for automatic deploys on every push and has them, so both the WBS and this assert
    what actually happens.

    The trigger is `workflow_run` on CI rather than `push`, because a push that fails CI must
    not deploy. That is the same "every push" with the gate kept.

    Deleting this lets the pipeline drift back to release tagging, which is the safer
    arrangement and is not the one he chose. A quiet return to it would mean pushes stop
    reaching the server with nothing announcing that they have.
    """
    triggers = _workflow("deploy.yml")[True]
    assert "workflow_run" in triggers
    assert triggers["workflow_run"]["workflows"] == ["CI"]
    assert triggers["workflow_run"]["branches"] == ["main"]
    assert "completed" in triggers["workflow_run"]["types"]


def test_nothing_in_the_deploy_waits_for_a_tag() -> None:
    """The other half of decision 22, and the half that decays. A tag trigger can be added
    beside the existing one without removing anything, so the workflow still deploys on every
    push and now also on a tag, and the two arrangements coexist until somebody assumes the
    tag is what matters.

    Checked over the triggers and over every job's condition, because a tag gate is as easily
    an `if:` as a trigger.
    """
    workflow = _workflow("deploy.yml")
    triggers = workflow[True]
    assert "release" not in triggers
    assert "create" not in triggers
    assert "tags" not in str(triggers.get("push", {})), "a tag now triggers the deploy"
    for name, job in workflow["jobs"].items():
        assert "refs/tags" not in str(job.get("if", "")), f"the {name} job waits for a tag"


def test_the_release_record_is_complete_without_anybody_tagging_anything() -> None:
    """The consequence of no tagging that would otherwise be discovered at the first release.
    `choose_span` prefers a `wave-*` tag and falls back to the parent commit, so a repository
    that has never been tagged still produces a manifest carrying the ids that commit closed.

    Without the fallback the manifest would be silently empty on every build until somebody
    cut the first release, and a mechanism nobody has seen work is a mechanism discovered
    broken on the day it matters. Asserted against a real repository rather than a mocked
    `git`, because what is being tested is what git answers.
    """
    import subprocess
    import tempfile

    from brain.ops.release_manifest import build_manifest

    with tempfile.TemporaryDirectory() as where:
        repo = Path(where)
        env = {
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@x",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@x",
        }
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        (repo / "a").write_text("1", encoding="utf-8", newline="\n")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "root"], check=True, env={**env})
        (repo / "a").write_text("2", encoding="utf-8", newline="\n")
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-qam", "M9.9.9: a thing"], check=True, env={**env}
        )

        manifest = build_manifest(repo)

    assert manifest.span == "commit", "no tag exists, so the span must fall back to the parent"
    assert manifest.task_ids == ("M9.9.9",), "the manifest carries no ids without a tag"


# ------------------------ the pipeline itself is provably working (M38.2.2.1)
def test_the_commit_that_is_running_can_be_discovered_from_the_image_it_shipped_in() -> None:
    """W0 ships nothing user-facing, so the only thing it can prove is that the pipeline
    works, and the only evidence of that is being able to name what is live.

    Three files have to agree for that to work and none of them imports another: CI writes
    the manifest into the build context, the Dockerfile copies it into the image, and
    `read_manifest` opens it at a compiled-in path. Any two agreeing and the third differing
    produces no error anywhere. The container starts, health checks pass, and `/health/live`
    answers "unknown" - which is what it did on the live server, while the status page beside
    it reported the truth.

    Deleting this makes the three drift silently, and the cost is a deployment nobody can
    identify and therefore nobody can roll back with confidence.
    """
    from brain.ops.release_manifest import MANIFEST_PATH

    written = re.findall(
        r"brain\.ops\.release_manifest\s*>\s*(\S+)", _text_of("deploy.yml", "build")
    )
    assert written == ["RELEASE.json"], f"CI writes {written} rather than one manifest"

    copies = [
        (source, destination)
        for source, destination in re.findall(
            r"^COPY\s+(?:--\S+\s+)*(\S+)\s+(\S+)\s*$",
            (REPO / "Dockerfile").read_text(encoding="utf-8"),
            re.M,
        )
        if fnmatch.fnmatch(written[0], source)
    ]
    assert len(copies) == 1, f"the Dockerfile does not copy {written[0]} into the image"

    _, destination = copies[0]
    assert PurePosixPath(destination) / written[0] == PurePosixPath(MANIFEST_PATH.as_posix()), (
        f"the image carries the manifest at {destination}{written[0]} and the code reads "
        f"{MANIFEST_PATH.as_posix()}"
    )


def test_a_local_build_still_works_without_a_manifest() -> None:
    """The reason the Dockerfile's source is a pattern rather than a literal. `COPY` fails on
    a missing literal path and succeeds with zero matches on a glob, and a manifest only
    exists in CI.

    A build that requires it would break for the only person able to fix it, and the absence
    is not an error anyway: the application treats no manifest as "running from a checkout".
    Deleting this invites tidying the brackets away, which turns `docker build .` into a
    failure with a message about a missing file nobody has ever created by hand.
    """
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    source = next(
        s
        for s, _ in re.findall(r"^COPY\s+(?:--\S+\s+)*(\S+)\s+(\S+)\s*$", dockerfile, re.M)
        if fnmatch.fnmatch("RELEASE.json", s)
    )
    assert source != "RELEASE.json", "a literal path makes a build without a manifest fail"


def test_the_realm_the_identity_stack_imports_ships_inside_the_image() -> None:
    """**Written after the identity stack turned out not to be deployable on this host.**

    `docker-compose.keycloak.yml` used to bind-mount the realm from `./ops/keycloak/`, which
    works when the compose file sits in a git working tree. This Coolify installation does not
    do that: measured on the server on 2026-09-07, its resource directory holds a `.env`, a
    `README.md` and a stored compose, with no repository anywhere near it. The relative path
    resolved to nothing, and the first deploy would have failed with a message about a missing
    file rather than about a missing checkout.

    So the realm travels in the image, and this asserts both halves: the Dockerfile copies it,
    and the compose reads it from where the Dockerfile puts it. Either alone is satisfied by a
    pair that disagrees, which is a container that starts and a Keycloak with no realm in it,
    where every sign-in fails with nothing near the login page to say why.

    Delete this and the realm drops out of the image the next time somebody trims what the
    build copies, and nothing notices until an identity deploy that has always been rare."""
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    compose = (REPO / "docker-compose.keycloak.yml").read_text(encoding="utf-8")

    copied = {
        destination
        for source, destination in re.findall(
            r"^COPY\s+(?:--\S+\s+)*(\S+)\s+(\S+)\s*$", dockerfile, re.M
        )
        if source == "ops/keycloak/realm-export.json"
    }
    assert copied, "the Dockerfile does not copy the realm, so the import job has nothing to read"

    inside = copied.pop()
    assert inside in compose, (
        f"the Dockerfile puts the realm at {inside} and the compose reads it from somewhere "
        "else, so Keycloak starts with no realm and every sign-in fails"
    )
    assert "./ops/keycloak/realm-export.json:" not in compose, (
        "the compose bind-mounts the realm from the working tree again, which is the thing "
        "that does not exist where this is deployed"
    )

    # **And the middle, which is where the first version of this went wrong.** Asserting the
    # Dockerfile copies the realm and the compose reads it back proves the two ends agree and
    # says nothing about whether the build can see the file at all. `.dockerignore` excluded
    # `ops`, so the COPY failed on the build machine with "not found" while every test here
    # passed. Docker is not installed on the development laptop, so this test is the only
    # thing standing between that mistake and CI.
    wanted = "ops/keycloak/realm-export.json"
    excluded = False
    for line in (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines():
        rule = line.strip()
        if not rule or rule.startswith("#"):
            continue
        negated = rule.startswith("!")
        pattern = rule.removeprefix("!")
        parts = wanted.split("/")
        prefixes = ["/".join(parts[: n + 1]) for n in range(len(parts))]
        if any(fnmatch.fnmatch(one, pattern) for one in prefixes):
            excluded = not negated

    assert not excluded, (
        f".dockerignore excludes {wanted}, so the COPY above fails on the build machine with "
        "a message about a missing file while every check in this test still passes"
    )


def test_every_postgres_18_mounts_its_volume_where_18_expects_it() -> None:
    """**Written because the lesson was recorded in one compose file and missed in the next.**

    PostgreSQL 18 keeps its data in a major-version subdirectory so `pg_upgrade --link` never
    crosses a mount boundary, so its volume goes at `/var/lib/postgresql` and not at
    `/var/lib/postgresql/data`. Mounting the old path makes it refuse to start with a message
    about finding data in an "unused mount/volume", which reads like corruption and is only
    convention.

    `docker-compose.yml` has carried that explanation since it was written.
    `docker-compose.keycloak.yml` was written afterwards, mounted the old path, and
    restart-looped on the server on 2026-09-07 the first time anybody deployed it. A comment
    in one file is not a check on another.

    **Parsed, and version-aware, because the first version of this test was neither.** It
    scanned the text for the old path and failed on the two files whose comments explain the
    rule, which is the substring trap this repository has hit three times today. It also would
    have condemned `docker-compose.automation.yml`, which runs `postgres:16-alpine` and is
    correct exactly as it is: on 16 the data path is the right mount. The rule belongs to 18
    and later, so the test reads the image and applies it only there.

    Delete this and the next Postgres 18 added here repeats the first one's mistake, and the
    symptom is a container that restarts for ever with a message about corruption."""
    import yaml

    checked = 0
    for path in sorted(REPO.glob("docker-compose*.yml")):
        compose = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, service in (compose.get("services") or {}).items():
            image = str(service.get("image", ""))
            # Both spellings this repository uses: `postgres:18-alpine` for Keycloak's own
            # database and `pgvector/pgvector:pg18` for the application's, which carries the
            # extension and puts the major after a `pg`.
            version = re.search(r"(?:postgres|pgvector):(?:pg)?(\d+)", image)
            if version is None or int(version.group(1)) < 18:
                continue
            checked += 1
            mounts = [str(one) for one in (service.get("volumes") or [])]
            assert not any(one.endswith(":/var/lib/postgresql/data") for one in mounts), (
                f"{path.name} service {name} runs {image} and mounts its volume at "
                "/var/lib/postgresql/data, which 18 refuses to start from"
            )
            assert any(one.endswith(":/var/lib/postgresql") for one in mounts), (
                f"{path.name} service {name} runs {image} and mounts no data volume at "
                "/var/lib/postgresql, so its database does not survive a restart"
            )

    assert checked >= 2, (
        f"only {checked} Postgres 18 services were checked; this test is meant to cover the "
        "application's database and Keycloak's, so a count below two means it found neither"
    )


def test_a_deploy_is_recorded_with_the_commit_the_running_process_reports() -> None:
    """What makes the record evidence rather than an intention. Recording the SHA the deployer
    asked for says what it tried to deploy; asking the container says what is serving.

    Those differed here for real. Coolify resolved a `${COMMIT_SHA:-unknown}` default at save
    time and stored the literal, so the deploy record said one thing and the running image
    knew another. Deleting this lets the watcher go back to recording its own intention, which
    reads identically in the log and is wrong exactly when it matters.
    """
    watcher = _live(_watcher())
    assert "/health/live" in watcher.split("running_commit()")[1][:400]
    deployed = next(
        line for line in watcher.splitlines() if line.strip().startswith("record deployed")
    )
    assert "$(running_commit)" in deployed, (
        f"the deploy record does not ask the container what it is running: {deployed.strip()}"
    )
