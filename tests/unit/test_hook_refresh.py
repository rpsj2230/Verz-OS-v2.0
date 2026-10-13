"""The server's deploy hook is refreshed from the image before a release runs, if it parses.

`brain-deploy` is installed on a server once and a release that adds a step to it used to reach
the server only by somebody copying the file out of a checkout. On the first install the hook was
three weeks behind the repository: it had never started an optional service, applied a release's
vault policies or reported the server's container runtimes, and the console refused to switch the
script sandbox on for want of that report. `refresh_hook`, in the timer's script, copies the hook
out of the image about to be deployed.

The function is read out of `ops/deploy/brain-autodeploy` and run alone, in the shell it is written
for, against a stub `docker`: the rest of that script pulls an image, writes a heartbeat under
`/var/lib` and starts a deploy, none of which a test should do. What the rest of it does is the
business of `test_post_deploy.py` and `test_delivery_pipeline.py`.

Skipped where there is no `bash`; CI's runner has one.

Task ids: M38.1.3.3, M32.2.1.1
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AUTODEPLOY = REPO / "ops" / "deploy" / "brain-autodeploy"
HOOK = REPO / "ops" / "deploy" / "brain-deploy"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="the timer's script is bash")

#: A hook as an image might carry it: bash, parses, and says which version it is.
NEW_HOOK = "#!/usr/bin/env bash\necho new-hook\n"
OLD_HOOK = "#!/usr/bin/env bash\necho old-hook\n"

#: What the stub docker does with `create`, `cp` and `rm`, by what the image carries.
STUB = r"""#!/bin/sh
S="$STUB_STATE"
echo "$*" >> "$S/calls"
case "$1" in
  create) [ -f "$S/create_fails" ] && exit 1; echo stub-container ;;
  cp)
    [ -f "$S/image_hook" ] || exit 1
    cp "$S/image_hook" "$3" ;;
  rm) ;;
esac
exit 0
"""


def function_text() -> str:
    """`refresh_hook` as the script writes it: from its definition to its closing brace."""
    lines = AUTODEPLOY.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("refresh_hook() {"))
    end = next(i for i in range(start, len(lines)) if lines[i] == "}")
    return "\n".join(lines[start : end + 1]) + "\n"


@dataclass
class Refreshed:
    code: int
    output: str
    hook: Path
    calls: list[str]


def refresh(
    tmp_path: Path,
    *,
    installed: str | None,
    image: str | None,
    create_fails: bool = False,
) -> Refreshed:
    """Run `refresh_hook` once, with `installed` where the hook lives and `image` as the hook the
    image carries (None: it carries none)."""
    state = tmp_path / "state"
    bin_dir = tmp_path / "bin"
    server = tmp_path / "server"
    for one in (state, bin_dir, server):
        one.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(STUB, encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    (state / "calls").write_text("", encoding="utf-8", newline="\n")
    if image is not None:
        (state / "image_hook").write_text(image, encoding="utf-8", newline="\n")
    if create_fails:
        (state / "create_fails").write_text("1\n", encoding="utf-8", newline="\n")
    hook = server / "brain-deploy"
    if installed is not None:
        hook.write_text(installed, encoding="utf-8", newline="\n")
        hook.chmod(0o755)
    (tmp_path / "function.sh").write_text(function_text(), encoding="utf-8", newline="\n")
    assert BASH is not None
    done = subprocess.run(
        [
            BASH,
            "-c",
            'set -euo pipefail; IMAGE=registry.example/brain:latest; . "$FUNCTION"; refresh_hook',
        ],
        env={
            **os.environ,
            "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ.get('PATH', '')}",
            "STUB_STATE": state.as_posix(),
            "FUNCTION": (tmp_path / "function.sh").as_posix(),
            "HOOK": hook.as_posix(),
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return Refreshed(
        code=done.returncode,
        output=done.stdout + done.stderr,
        hook=hook,
        calls=(state / "calls").read_text(encoding="utf-8").splitlines(),
    )


def test_a_hook_older_than_the_image_s_is_replaced_and_the_old_one_is_kept(
    tmp_path: Path,
) -> None:
    """The case this exists for: the installed hook differs from the image's, the image's is
    installed executable, and the one it replaced is beside it as `.previous`.

    Delete this and a release that adds a step to the hook is deployed by the hook from before it,
    for as long as nobody copies a file."""
    ran = refresh(tmp_path, installed=OLD_HOOK, image=NEW_HOOK)

    assert ran.code == 0, ran.output
    assert ran.hook.read_text(encoding="utf-8") == NEW_HOOK
    assert os.access(ran.hook, os.X_OK)
    assert Path(f"{ran.hook}.previous").read_text(encoding="utf-8") == OLD_HOOK
    assert not Path(f"{ran.hook}.new").exists()
    assert "refreshed" in ran.output


def test_a_hook_that_is_already_the_image_s_is_left_alone(tmp_path: Path) -> None:
    """The positive half of the refusals below, and the common case: every tick of a server whose
    hook is current changes no file. Delete this and every deploy rewrites the hook and leaves a
    `.previous` that is the same file, which hides the real previous one.

    Nothing is written, so the file's identity is unchanged."""
    ran = refresh(tmp_path, installed=NEW_HOOK, image=NEW_HOOK)
    before = ran.hook.stat().st_ino

    assert ran.code == 0, ran.output
    assert ran.hook.read_text(encoding="utf-8") == NEW_HOOK
    assert ran.hook.stat().st_ino == before
    assert not Path(f"{ran.hook}.previous").exists()
    assert ran.output == ""


@pytest.mark.parametrize(
    ("image", "why"),
    [
        (None, "carries no deploy hook"),
        ("", "does not parse"),
        ("echo not-bash\n", "does not parse"),
        ("#!/usr/bin/env bash\nif then fi (\n", "does not parse"),
        ("#!/bin/sh\necho posix\n", "does not parse"),
    ],
    ids=["no hook in the image", "empty", "no shebang", "syntax error", "not bash"],
)
def test_an_image_s_hook_that_is_missing_empty_or_does_not_parse_never_replaces_a_working_one(
    tmp_path: Path, image: str | None, why: str
) -> None:
    """Each way the image's file can be wrong leaves the installed hook as it was, says so, and
    exits zero, because the deploy goes on with the hook it has. Delete this and a release built
    with a broken hook takes down every server's deploy mechanism, which is the one thing that
    could ship the fix."""
    ran = refresh(tmp_path, installed=OLD_HOOK, image=image)

    assert ran.code == 0, ran.output
    assert ran.hook.read_text(encoding="utf-8") == OLD_HOOK
    assert not Path(f"{ran.hook}.previous").exists()
    assert why in ran.output


def test_an_image_that_cannot_be_opened_leaves_the_installed_hook_and_the_deploy_goes_on(
    tmp_path: Path,
) -> None:
    """`docker create` failing (the image is gone, the disk is full) is not a reason to stop the
    deploy it was about to be part of. Delete this and a full disk stops the one mechanism that
    would be used to clear it."""
    ran = refresh(tmp_path, installed=OLD_HOOK, image=NEW_HOOK, create_fails=True)

    assert ran.code == 0, ran.output
    assert ran.hook.read_text(encoding="utf-8") == OLD_HOOK
    assert "could not open" in ran.output


def test_a_server_with_no_hook_yet_is_given_the_image_s(tmp_path: Path) -> None:
    """Nothing to compare with and nothing to keep: the image's is installed and no `.previous` is
    written for a file that did not exist. Delete this and a missing hook makes the refresh itself
    fail on the copy of a file that is not there."""
    ran = refresh(tmp_path, installed=None, image=NEW_HOOK)

    assert ran.code == 0, ran.output
    assert ran.hook.read_text(encoding="utf-8") == NEW_HOOK
    assert not Path(f"{ran.hook}.previous").exists()


def test_the_hook_this_repository_ships_passes_the_refresh_s_own_checks(tmp_path: Path) -> None:
    """The real file, offered as the image's: it starts with a bash shebang and parses, so the
    refresh would install it. Delete this and the guard can be tightened until it refuses the
    hook it exists to deliver, every server keeps the old one, and every test above still passes."""
    ran = refresh(tmp_path, installed=OLD_HOOK, image=HOOK.read_text(encoding="utf-8"))

    assert ran.code == 0, ran.output
    assert ran.hook.read_bytes() == HOOK.read_bytes()


def test_the_timer_s_script_refreshes_the_hook_before_it_runs_it_and_the_image_carries_it() -> None:
    """Two facts held to the files. The refresh is called on a line before the hook is run, so the
    release being deployed runs with its own hook, and the Dockerfile copies both scripts into the
    image where the refresh and the documented one-time copy look for them, with the ignore file
    letting them through.

    Delete this and the call can be removed or moved after the deploy, or the image can stop
    carrying the file, with the function itself still tested and nothing ever calling it."""
    live = [
        line.strip()
        for line in AUTODEPLOY.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    ]
    assert live.count("refresh_hook") == 1
    assert live.index("refresh_hook") + 1 == live.index("/usr/local/bin/brain-deploy")

    copies = {
        parts[-1]: parts[-2]
        for line in (REPO / "Dockerfile").read_text(encoding="utf-8").splitlines()
        if line.startswith("COPY ") and (parts := line.split())
    }
    ignored = (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for name in ("brain-deploy", "brain-autodeploy"):
        assert copies[f"/app/ops/deploy/{name}"] == f"ops/deploy/{name}"
        assert f"!ops/deploy/{name}" in ignored
    assert re.search(r'cp "\$cid:/app/ops/deploy/brain-deploy"', AUTODEPLOY.read_text("utf-8"))
