"""Which merges leave the worker running, decided by what a release contains and nothing else.

**Found on the owner's staging install, and the same on every install that deploys on a timer.**
Every merge to main publishes an image, the server's timer pulls it, and `ops/deploy/brain-deploy`
recreates the app and then every other service built from the same image, the worker among them.
An acceptance run is thirty-five minutes and more, the worker is what runs it, and merges that
change nothing the worker runs (a page of the build documents, a test, a screen of the console,
a workflow file) killed the run in progress all night. The app has to be recreated by every merge
because it serves the console and the documents out of the image; the worker does not, so the
deploy script now leaves a worker running when the image it would move to is the one it is
already running, **as far as the worker is concerned**.

**The decision is a comparison of two fingerprints, and the fingerprint is computed where git
is.** CI writes a hash of every committed file the worker might run into the release manifest
baked into the image (`worker_fingerprint`, see `brain.ops.release_manifest`). The server has no
repository and the container has no `.git`, so the deploy script reads the fingerprint out of the
image about to be deployed and out of the image each worker is running, and compares them. Equal
means the same files, byte for byte, in everything the worker could run, whichever commits lie
between the two images. Rejected: a diff since the running commit. It needs the running commit's
history, which a server does not have, and it goes wrong the moment the timer skips a commit (two
merges within one tick are one deploy), because the diff is then between the wrong pair. A hash
of the content has no such pair to get wrong.

**The rule is a list of what is inert, and everything else restarts the worker.** `INERT_PREFIXES`
names the directories nothing the worker runs lives in; a path under none of them is treated as
something the worker runs. So a new top-level directory, a new `ops` script, a new compose file
or anything nobody thought about restarts the worker exactly as every merge did before this
module existed, and the cost of a gap in the list is the old behaviour rather than a stale
worker. Rejected: a list of what the worker runs (`src/`, `migrations/` and so on), because every
omission from it is a worker left on old code with every check green, which is the quiet
direction to be wrong in. `src/` as a whole is not narrowed to the modules the worker imports:
the import graph reaches the whole application (`brain.app` imports the estate), so any such
narrowing is either empty or a guess.

**When the answer cannot be had, the worker is restarted**
(`WHEN_THE_CHANGE_CANNOT_BE_TOLD_THE_WORKER_IS_RESTARTED`): a release built before this existed
carries no fingerprint, a build outside a repository computes none, a fingerprint that is not
sixty-four hexadecimal characters is not one, and a server that cannot open either image has no
pair to compare. Each of those is the old behaviour. The first deploy after this ships restarts
every worker once for the first reason.

**What a worker left running does not have, said plainly.** `docs/` is inert, so a worker started
on one release reads the build documents of that release for as long as it runs, and the
acceptance checks that read the requirements register or the work breakdown read them from that
copy. The app, which serves the documents, has the newest. The worker is replaced by the next
merge that changes anything it runs, which is the common case, and an install that needs the
documents refreshed sooner restarts the worker by hand (`BRAIN_DEPLOY_RECREATE_ALL`, below).
Rejected: counting the three or four documents the checks read as the worker's. The work
breakdown changes in nearly every documentation-only merge, so doing that gives back the restarts
this removes. The base image is also not in the fingerprint (a tag moves under a rebuild), so a
worker takes its base image's patches at the next merge that restarts it; the app takes them at
every one.

**Two things that it does not do.** It does not touch the app, which is recreated by every
deploy because the console and the documents are in its image. And it does not change which
commit a worker reports: a worker left running on the previous release still reports that
release's commit, and an acceptance run it makes is recorded under that commit. See
`brain.ops.acceptance_resume`, which says what that means for the Install page.

Task ids: M38.1.3.5, M38.5.1
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Final

# ------------------------------------------------------------------ written-down reasons
#: Why the list below names what is inert and not what the worker runs.
A_PATH_NOT_NAMED_INERT_RESTARTS_THE_WORKER: Final = (
    "A committed path is something the worker runs unless it lies under a directory named inert. "
    "A gap in the list costs a restart that was not needed, which is how every merge behaved "
    "before; a list of what the worker runs would put every omission on a worker left on old "
    "code with nothing red."
)

#: Why a release that carries no fingerprint, or two that cannot be compared, restart the worker.
WHEN_THE_CHANGE_CANNOT_BE_TOLD_THE_WORKER_IS_RESTARTED: Final = (
    "A worker is left running only when the image it runs and the image it would move to both "
    "carry a fingerprint of what the worker runs and the two are equal. A release without one, "
    "a fingerprint that is malformed, or an image the server cannot open restarts the worker, "
    "which is what every deploy did before this rule."
)

#: What a worker left running keeps from the release it started on.
THE_WORKER_KEEPS_THE_DOCUMENTS_OF_THE_RELEASE_IT_STARTED_ON: Final = (
    "The build documents are inert, so a worker left running reads the copy in the image it "
    "started on, and the app reads the newest. The next merge that changes anything the worker "
    "runs replaces it."
)

# ----------------------------------------------------------------------------- the rule
#: The directories nothing the worker runs lives in, each with its trailing slash so that
#: `docs-extra/` is not read as `docs/`. Held to a literal by a test, because widening this list is
#: the one edit that can leave a worker on old code.
INERT_PREFIXES: Final[tuple[str, ...]] = (
    # The build documents, the tracker and the generated status: served by the app.
    "docs/",
    # Never imported by a running process.
    "tests/",
    "e2e/",
    # The console's source, compiled into a bundle the application serves. Nothing the worker
    # runs reads it.
    "console/",
    # The record matcher builds its own image from its own directory.
    "matcher/",
    # The workflows run on GitHub and are not in the image.
    ".github/",
)

#: The key under which the manifest carries the fingerprint, read by `ops/deploy/brain-deploy`.
#: Written here and read there, so a test builds a real manifest and hands it to the script.
WORKER_FINGERPRINT_KEY: Final = "worker_fingerprint"

#: What a fingerprint looks like: a SHA-256 in lower-case hexadecimal. The deploy script's own
#: pattern is this one, so a value that is not this restarts the worker.
FINGERPRINT_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")

#: Domain separation, so a fingerprint made by another rule can never equal one made by this.
_SCHEMA: Final = b"brain.worker-fingerprint.v1\n"


def is_inert(path: str) -> bool:
    """Whether a committed path is one nothing the worker runs lives in. See the module."""
    return path.startswith(INERT_PREFIXES)


def fingerprint(entries: Iterable[tuple[str, str]]) -> str:
    """The fingerprint of `(path, blob id)` pairs, counting only what the worker could run.

    Empty when no pair counts, which is not a fingerprint of nothing but the absence of one, so
    that two releases whose inputs could not be read never compare equal.
    """
    counted = sorted((path, blob) for path, blob in entries if blob and not is_inert(path))
    if not counted:
        return ""
    digest = hashlib.sha256(_SCHEMA)
    for path, blob in counted:
        digest.update(f"{path}\0{blob}\n".encode("utf-8", "surrogateescape"))
    return digest.hexdigest()


def tree_entries(repo: Path, ref: str = "HEAD") -> tuple[tuple[str, str], ...]:
    """Every committed file of `ref` with its blob id, or nothing when git cannot be asked.

    The committed tree and not the working directory, so the files CI regenerates in a checkout
    before the build (the status and the tracker, all of them under `docs/`) cannot move it.
    """
    try:
        result = subprocess.run(  # noqa: S603  arguments are literals from this module
            ["git", "ls-tree", "-r", "-z", "--full-tree", ref],  # noqa: S607  git on PATH
            cwd=repo,
            capture_output=True,
            check=False,
        )
    except OSError:
        return ()
    if result.returncode != 0:
        return ()
    found: list[tuple[str, str]] = []
    for record in result.stdout.split(b"\0"):
        # `<mode> SP <type> SP <object> TAB <path>`; a line that is not that is not guessed at.
        head, tab, path = record.partition(b"\t")
        fields = head.split(b" ")
        if not tab or len(fields) != 3:
            continue
        found.append(
            (path.decode("utf-8", "surrogateescape"), fields[2].decode("ascii", "replace"))
        )
    return tuple(found)


def fingerprint_of(repo: Path, ref: str = "HEAD") -> str:
    """The fingerprint of what `ref` would put in a worker, or empty when it cannot be told."""
    return fingerprint(tree_entries(repo, ref))
