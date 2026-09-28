"""What GitHub answers a skill import with, recorded as shapes, so no test ever contacts it.

A second file beside `tests/fixtures/cassettes.py` rather than recordings in that corpus, for the
reason `tests/fixtures/roster_payloads.py` gives about its own: those cassettes are a connector's
replies to a tool, counted by a coverage sweep over `brain.connectors`, and a skill import is not a
connector and has no tool. What is shared is the rule: **not one of these was captured from a live
answer, and each names the page its shape comes from.** The values (the owner, the repository, the
commit, the words of the skill) are invented; the envelope is the documentation's.

**The tarball of one commit.** `https://codeload.github.com/{owner}/{repo}/tar.gz/{sha}` answers
200 with a gzip stream of a tar whose one top folder is `{repo}-{sha}` and whose first header is a
pax global header carrying the commit id as `comment`. The folder name is GitHub's "Downloading
source code archives" page
(https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives);
the global header is `git archive`'s, which GitHub's archives are built by
(https://git-scm.com/docs/git-archive: "the commit ID is stored in a global extended pax header").
Directory entries are listed, as `git archive` lists them.

**The raw file of one path.** `https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}`
answers 200 with the file's bytes, and `https://github.com/{owner}/{repo}/raw/{ref}/{path}` answers
302 with that address as `Location`: the "Viewing a file" page's raw link
(https://docs.github.com/en/repositories/working-with-files/using-files/viewing-and-understanding-files).

Task ids: none
"""

from __future__ import annotations

import io
import tarfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from brain.tools.fetch import FetchedBytes

#: Invented. A public address, so the range rule admits it; nothing here resolves anything.
GITHUB_ADDRESS = "140.82.112.9"

OWNER = "example-org"
REPOSITORY = "agent-skills"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
FOLDER = "skills/hosting-expiry"

SKILL_TEXT = """---
name: hosting-expiry
description: Use when a client asks whether their domain or hosting is about to expire
version: 1.2.0
tools: [crm.read_client, desk.read_ticket]
---
Look up the client's domain, check its expiry date, and open a ticket if it is within a month.
"""


def tarball(
    files: Mapping[str, bytes],
    *,
    repository: str = REPOSITORY,
    commit: str = COMMIT,
    links: Mapping[str, str] | None = None,
) -> bytes:
    """A commit's archive as codeload serves it: one top folder, a pax global header, gzip.

    `files` maps a path inside the repository to its bytes; `links` maps a path to a symlink
    target, which is how a hostile repository would name something `SKILL.md`.
    """
    top = f"{repository}-{commit}"
    buffer = io.BytesIO()
    with tarfile.open(
        fileobj=buffer, mode="w:gz", format=tarfile.PAX_FORMAT, pax_headers={"comment": commit}
    ) as archive:
        folders: set[str] = {top}
        for path in [*files, *(links or {})]:
            parts = path.split("/")[:-1]
            for depth in range(1, len(parts) + 1):
                folders.add("/".join([top, *parts[:depth]]))
        for folder in sorted(folders):
            entry = tarfile.TarInfo(f"{folder}/")
            entry.type = tarfile.DIRTYPE
            entry.mode = 0o755
            archive.addfile(entry)
        for path, data in files.items():
            member = tarfile.TarInfo(f"{top}/{path}")
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
        for path, target in (links or {}).items():
            link = tarfile.TarInfo(f"{top}/{path}")
            link.type = tarfile.SYMTYPE
            link.linkname = target
            archive.addfile(link)
    return buffer.getvalue()


def tarball_url(owner: str = OWNER, repository: str = REPOSITORY, commit: str = COMMIT) -> str:
    return f"https://codeload.github.com/{owner}/{repository}/tar.gz/{commit}"


def raw_url(path: str = f"{FOLDER}/SKILL.md", ref: str = "main") -> str:
    return f"https://raw.githubusercontent.com/{OWNER}/{REPOSITORY}/{ref}/{path}"


def blob_raw_url(path: str = f"{FOLDER}/SKILL.md", ref: str = "main") -> str:
    """The repository page's raw link, which answers 302 to `raw_url`."""
    return f"https://github.com/{OWNER}/{REPOSITORY}/raw/{ref}/{path}"


#: The commit's archive holding the skill, a licence beside it, and an unrelated file elsewhere.
REPOSITORY_ARCHIVE = tarball(
    {
        f"{FOLDER}/SKILL.md": SKILL_TEXT.encode("utf-8"),
        f"{FOLDER}/LICENSE.txt": b"Licensed for use.\n",
        "README.md": b"# Agent skills\n",
    }
)


class Resolved:
    """A `brain.tools.fetch.Resolver` answering every name with one public address, or as told."""

    def __init__(self, answers: Mapping[str, Sequence[str]] | None = None) -> None:
        self.answers = dict(answers or {})
        self.asked: list[str] = []

    def resolve(self, host: str) -> Sequence[str]:
        self.asked.append(host)
        return self.answers.get(host, [GITHUB_ADDRESS])


@dataclass
class Recorded:
    """A `brain.tools.fetch.Fetcher` replaying recorded answers: bytes, or the next address.

    An address it holds no answer for is a failure the test sees, never a request anywhere.
    """

    answers: dict[str, bytes | str] = field(default_factory=dict)
    connected: list[tuple[str, str]] = field(default_factory=list)

    def get_once(self, url: str, *, address: str, max_bytes: int) -> FetchedBytes | str:
        del max_bytes
        self.connected.append((url, address))
        if url not in self.answers:
            msg = f"no recorded answer for {url}; a test must never reach a real host"
            raise AssertionError(msg)
        answer = self.answers[url]
        if isinstance(answer, bytes):
            return FetchedBytes(body=answer, final_url=url)
        return answer


def github() -> Recorded:
    """The recorded answers for this file's repository: its archive, and its raw file both ways."""
    return Recorded(
        answers={
            tarball_url(): REPOSITORY_ARCHIVE,
            raw_url(): SKILL_TEXT.encode("utf-8"),
            blob_raw_url(): raw_url(),
        }
    )
