"""The repository conventions that are checkable, checked.

They share one property: each is the kind of rule that a team agrees to, follows for a
fortnight, and then stops following without anybody deciding to. A convention nothing
enforces is a convention that describes the past.

**A commit message names the leaf ids it closes.** The status page is generated from
those ids, so a commit that closes a task without saying so leaves the plan describing
work that is finished, and the next person to read it plans around a gap that is not
there. Enforced by `ops/hooks/commit-msg`, which calls into here.

**A branch is named for its module.** Twelve tracks run concurrently and they collide in
exactly one way: two branches that sound alike get reviewed as though they were the same
work. The module id in the name makes that impossible to do by accident.

**Only leaf ids close anything.** A parent id is a summary of its children; letting one
close a task would mark work done that nobody did. This is the rule that most wants
enforcing, because writing `Closes: M12` is the natural thing to type and it is always
wrong.

**A fix for a problem found on an install says why it is the product's fix.** The owner runs
an install as a staging server, and a finding there arrives with a hand repair already on
that server. The commit that answers it carries `Found-on:` and `Generic-because:`, and the
second is what makes the author ask whether a company nobody here has met would have hit the
same fault. A `Found-on:` line without its reason is refused. A message that merely talks
about an install gets a note, because words cannot tell a finding from a mention and a rule
that refused on a guess would be switched off. See `AN_INSTALL_IS_NOT_THE_PRODUCT` and the
section of `CLAUDE.md` it names.

**A claim carries its proof on the same commit.** On 2026-09-17 an audit reopened 1046 of the
1213 tasks the tracker counted as done. Every one had been closed by a claim, most of them
backed by unit tests over fakes, and the owner's install showed none of the 1046 working. The
standard since is that a task is done when what it asks for exists and works on an install, so
a message that claims a leaf, on a `Closes:` line or in its subject, also carries a
`Proved-on-install:` line saying what was done on an install and what was seen, or, for a leaf
that lives only in the repository, a `Proved-in-ci:` line naming the CI job that runs it. See
`A_CLAIM_NEEDS_PROOF`. A proof names what was done and seen and never where: see
`A_PROOF_NAMES_NO_ADDRESS`.

**The hook is half of that rule and `brain.status` is the other half.** `git commit
--no-verify` skips this module entirely, so the tracker refuses to count an unproved claim on
its own, from `brain.status.PROOF_REQUIRED_FROM`. Both read proof through `proofs_in`, so the
hook cannot accept a trailer the tracker then ignores. What the hook adds is the moment: a
refusal here costs one retry, and a claim the tracker silently declines to count costs a task
that looks done to its author and open to everybody else.

**Taking a claim back needs no proof.** A `Reopens:` line only ever lowers the count, which is
never the direction a mistake flatters, and an id the same message reopens is not a claim.

Rejected: enforcing any of this in CI alone. CI runs after the commit exists, so the
message is already written and the fix is a rebase. A hook that refuses at commit time
costs one retry; the same rule in CI costs a rewrite of history or a second commit
apologising for the first.

Task ids: M38.1.1.1, M38.1.1.2, M42.6.8
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

#: A leaf id has at least three parts. `M12` is a module, `M12.1` is a group, and neither
#: is a thing anybody does; `M12.1.1` is. Requiring the third part is what makes
#: `Closes: M12` fail rather than silently closing ten tasks.
LEAF_ID_RE = re.compile(r"^M\d+(?:\.\d+){2,4}$")

#: Any id at all, including the parents, so the refusal can say which kind was written.
#: Zero dots is allowed here and nowhere else: `M12` is a module id, which is the most
#: likely thing to be typed and the one whose refusal most needs to explain itself. A
#: pattern that did not match it fell through to "not a task id", which is both unhelpful
#: and untrue.
ANY_ID_RE = re.compile(r"\bM\d+(?:\.\d+){0,4}\b")

#: The one line a commit may close tasks on. Deliberately not "anywhere in the message":
#: a message that discusses M12.1.1 in a paragraph about why it was *not* done would
#: otherwise close it.
#:
#: Case-insensitive, as `brain.status.CLOSES_RE` is, and kept equal to it by a test. Until
#: 2026-09-17 this read `Closes:` only, so a `closes:` line was a claim the tracker counted and
#: a line this module never checked: a group id on it closed the group, and an unproved claim
#: on it would have passed the proof rule below.
CLOSES_LINE_RE = re.compile(r"^\s*closes:\s*(.+)$", re.IGNORECASE | re.MULTILINE)

#: The line a mistaken claim is taken back on. Kept equal to `brain.status.REOPENS_RE` by a
#: test, for the reason `SUBJECT_ID_RE` gives: this module runs in a commit hook.
REOPENS_LINE_RE = re.compile(r"^\s*reopens:\s*(.+)$", re.IGNORECASE | re.MULTILINE)

#: Why a claim is refused without proof on the same commit.
A_CLAIM_NEEDS_PROOF = (
    "On 2026-09-17 an audit reopened 1046 of the 1213 tasks the tracker counted as done: each "
    "had been closed by a claim backed by tests over fakes, and the owner's install did not show "
    "it working. A task is done when what it asks for exists and works on an install. So a claim "
    "carries a Proved-on-install: line saying what was done on an install and what was seen, "
    "or, for a leaf that lives only in the repository, a Proved-in-ci: line naming the CI job "
    "that runs it. The tracker does not count a claim without one, whether or not this hook ran."
)

#: The two trailers that prove a claim. Case-insensitive like every other trailer the tracker
#: reads, and read from the body only, as git's `%b` is: see `body_of`.
PROOF_RE = re.compile(r"^\s*proved-(?:on-install|in-ci):(.*)$", re.IGNORECASE | re.MULTILINE)

#: Why a proof may not carry an address.
A_PROOF_NAMES_NO_ADDRESS = (
    "A proof says what was done on an install and what was seen, never where. A commit message "
    "is pushed and kept for ever, and the audit commit that prompted the proof rule named the "
    "install by its address in its own body. An address is configuration of one install, which "
    "CLAUDE.md keeps out of everything committed, and the proof is no weaker without it."
)

#: A bare IPv4, kept equal to `brain.ops.independence.IPV4` by a test rather than imported:
#: that module pulls in the settings loader, which costs a second on every commit.
IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)

#: Where git's subject ends and its body begins: the first line holding nothing but spaces.
PARAGRAPH_BREAK_RE = re.compile(r"\n[ \t]*\n")

#: The ids `brain.status.claimed_ids` reads out of a subject line: at least one dot, so a
#: module id such as `M27` in a subject is prose and a group id such as `M27.9` is a claim.
#: Kept equal to `brain.status.TASK_ID_RE` by a test rather than imported, because this
#: module runs in a commit hook and `brain.status` pulls in the work breakdown loader.
SUBJECT_ID_RE = re.compile(r"\bM\d+(?:\.\d+){1,4}\b")

#: Why a group id in a subject is refused and not merely noted.
A_SUBJECT_IS_READ_AS_A_CLAIM = (
    "The status page counts every id in a subject line as closed, so a subject naming a group "
    "closes the group, and the traceability test fails in CI after the commit has deployed "
    "nowhere. Measured on 2026-09-17, when a subject saying the plan was appended as M27.9 to "
    "M27.14 turned CI red. Name leaves, or leave ids out of the subject."
)

#: `<module-id>/<short-name>`, e.g. `M12/tool-registry`. The module id first so the
#: branch list sorts by module rather than by whoever named theirs "fix".
BRANCH_RE = re.compile(r"^M\d+(?:\.\d+)*/[a-z][a-z0-9-]*$")

#: Why a finding from an install has to say its fix is generic.
AN_INSTALL_IS_NOT_THE_PRODUCT = (
    "A problem seen on one install is two questions: what that install needs, and whether "
    "the product is wrong for every install. A commit answering a finding from an install "
    "says why its fix is generic, or it is one company's repair shipped to every company."
)

#: The trailer naming where a problem was found. Any value: `staging`, `first install`.
FOUND_ON_RE = re.compile(r"^\s*Found-on:[ \t]*(.*)$", re.M)

#: The trailer saying why the fix belongs to every install. It needs words after the colon.
GENERIC_BECAUSE_RE = re.compile(r"^\s*Generic-because:[ \t]*(\S.*)$", re.M)

#: Phrases that usually mean a message is answering something seen on a live install.
#: Deliberately short: a note that fires on every commit is a note nobody reads.
INSTALL_MENTION_RE = re.compile(
    r"\bstaging\b|\b(?:own|live) install\b|\bon (?:his|her|their|the owner's) server\b",
    re.I,
)

#: Branches that exist for reasons other than a track. `main` is the trunk; the rest are
#: what a person types when they are about to throw the branch away, and refusing those
#: would make the rule something people work around rather than follow.
EXEMPT_BRANCHES = frozenset({"main", "HEAD"})


@dataclass(frozen=True)
class Refusal:
    """Why a message or a branch name was refused, in words a person can act on.

    Carries the offending text as well as the reason. A hook that prints only "invalid
    commit message" makes the author guess which of three rules they broke, and guessing
    wrong twice is how a rule gets disabled.
    """

    reason: str
    subject: str

    def __str__(self) -> str:
        return f"{self.reason}\n  got: {self.subject}"


def leaf_ids_in(message: str) -> tuple[str, ...]:
    """The ids a message actually closes, from the `Closes:` line only.

    Returns them in the order written rather than sorted, because a refusal that quotes
    them back should quote what was typed.
    """
    ids: list[str] = []
    for line in CLOSES_LINE_RE.findall(message):
        ids.extend(part.strip() for part in re.split(r"[,\s]+", line) if part.strip())
    return tuple(ids)


def body_of(message: str) -> str:
    """Everything after the subject paragraph, which is what git's `%b` hands the tracker.

    Git's subject is the first paragraph rather than the first line: a message with no blank
    line after its first line has a subject running on into whatever follows and an empty body.
    So a proof trailer typed directly under the subject is not in `%b`, and the tracker does not
    see it. Splitting here on the first blank line rather than the first newline is what stops
    this hook accepting a trailer the tracker then ignores, which would be a task that looks
    proved to its author and open to everybody else.
    """
    parts = PARAGRAPH_BREAK_RE.split(message.strip(), maxsplit=1)
    return parts[1] if len(parts) > 1 else ""


def proofs_in(body: str) -> tuple[str, ...]:
    """The words on every proof trailer in a commit body, in the order written.

    An empty trailer is left out rather than counted. A colon with nothing after it is the
    cheapest way to satisfy the letter of the rule, and it proves nothing, so neither this hook
    nor `brain.status`, which reads proof through this function, treats one as proof.
    """
    return tuple(value.strip() for value in PROOF_RE.findall(body) if value.strip())


def reopened_in(body: str) -> set[str]:
    """Ids a commit body takes back on a `Reopens:` line, as `brain.status.reopened_ids` reads.

    The body only. A subject reading `Reopens: M0.4.2` is a claim to the tracker, which reads
    every id in a subject as one, so it is a claim here too and needs its proof.
    """
    ids: set[str] = set()
    for line in REOPENS_LINE_RE.findall(body):
        ids.update(SUBJECT_ID_RE.findall(line))
    return ids


def check_commit_message(message: str) -> Refusal | None:
    """None if the message may be committed, a Refusal otherwise.

    A message with no `Closes:` line at all is allowed. Not every commit closes a task:
    a fix to a fix, a revert, a formatting pass and a merge all legitimately close
    nothing, and a rule that demanded an id from them would be satisfied with a made-up
    one. What is refused is a `Closes:` line that does not mean what it says.
    """
    subject = message.strip().splitlines()[0] if message.strip() else ""
    if not subject:
        return Refusal("a commit message needs a subject line", "(empty)")

    if FOUND_ON_RE.search(message) and not GENERIC_BECAUSE_RE.search(message):
        return Refusal(
            "a commit with a Found-on: line says why its fix belongs to every install, on a "
            "Generic-because: line. " + AN_INSTALL_IS_NOT_THE_PRODUCT,
            subject,
        )

    # The subject is a claim too, because `brain.status.claimed_ids` reads ids from the
    # subject as well as from the trailer. So a group id there closes a group exactly as a
    # trailer would, and is refused for the same reason. See A_SUBJECT_IS_READ_AS_A_CLAIM.
    for one in SUBJECT_ID_RE.findall(subject):
        if not LEAF_ID_RE.match(one):
            return Refusal(
                f"{one} in the subject is a module or group id, and the subject is read as a "
                f"claim. {A_SUBJECT_IS_READ_AS_A_CLAIM}",
                subject,
            )

    # Only the Closes: line and the subject claim. If the body mentions ids elsewhere, that is
    # prose: a message explaining why M12.1.1 was left alone must not close it.
    closes = leaf_ids_in(message)
    for one in closes:
        if LEAF_ID_RE.match(one):
            continue
        if ANY_ID_RE.fullmatch(one):
            return Refusal(
                f"{one} is a module or group id, and those close nothing. A parent is a "
                "summary of its children; closing one would mark work done that nobody "
                "did. Name the leaves.",
                subject,
            )
        return Refusal(f"{one!r} on the Closes: line is not a task id", subject)

    body = body_of(message)
    proofs = proofs_in(body)
    for proof in proofs:
        if IPV4_RE.search(proof) or "://" in proof:
            return Refusal(f"a proof names an address. {A_PROOF_NAMES_NO_ADDRESS}", subject)

    # By here every id in the subject and on the Closes: line is a leaf. An id the same commit
    # reopens is not counted by the tracker, so it needs no proof either.
    claimed = (set(SUBJECT_ID_RE.findall(subject)) | set(closes)) - reopened_in(body)
    if claimed and not proofs:
        return Refusal(
            f"{', '.join(sorted(claimed))} claimed with no Proved-on-install: or Proved-in-ci: "
            f"line saying what proves it. {A_CLAIM_NEEDS_PROOF}",
            subject,
        )
    return None


def already_closed(message: str, repo: Path) -> tuple[str, ...]:
    """Leaf ids on this message's `Closes:` line that an earlier commit already closed.

    A warning rather than a refusal, and the distinction is the point. Re-claiming is
    sometimes exactly right: a leaf claimed on a thin implementation and later given the
    test that proves it should say so, and the count is a set so nothing double-counts.
    What is wrong is doing it *without noticing*, which produces a commit message
    announcing eight closures that moves the number by nothing.

    Written after doing that twice in one session. Both times the mistake was the same:
    listing leaves that had no test naming them, and reading "untested" as "unclaimed".
    They are different questions and the second one was never asked.

    Returns the ids, so the hook can say which. Silence is what let this happen twice.
    """
    claimed = set(leaf_ids_in(message))
    if not claimed:
        return ()
    # Imported here rather than at module scope: this module is called from a git hook on
    # every commit, and `brain.status` pulls in the WBS loader, which is a cost the other
    # two rules do not need to pay.
    from brain.status import closed_task_ids

    try:
        closed, _ = closed_task_ids(repo)
    except Exception:
        # Outside a repository, or git is unavailable. A hook that fails because it could
        # not answer an advisory question would block a commit for no reason.
        return ()
    return tuple(sorted(claimed & closed))


def unmarked_install_finding(message: str) -> bool:
    """Whether a message talks about an install and carries no `Found-on:` line.

    A note and never a refusal. "Staging" in a message may be a finding, a mention of the
    deploy chain or a sentence about why something was not done, and only the author knows
    which. The note asks the question; the trailer is how the answer gets written down.
    """
    return bool(INSTALL_MENTION_RE.search(message)) and not FOUND_ON_RE.search(message)


def check_branch_name(name: str) -> Refusal | None:
    """None if the branch may exist, a Refusal otherwise."""
    if name in EXEMPT_BRANCHES:
        return None
    if BRANCH_RE.match(name):
        return None
    return Refusal(
        "a branch is named <module-id>/<short-name>, for example M12/tool-registry. "
        "Twelve tracks run at once and the module id is what stops two of them being "
        "reviewed as though they were the same work.",
        name,
    )


def main(argv: list[str] | None = None) -> int:
    """`python -m brain.ops.conventions <path-to-commit-message-file>`.

    Reads a file rather than a string because that is the interface git's `commit-msg`
    hook offers: git writes the message to a temporary file and passes the path.
    """
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python -m brain.ops.conventions <commit-message-file>", file=sys.stderr)
        return 2

    message = Path(args[0]).read_text(encoding="utf-8")
    refusal = check_commit_message(message)
    if refusal is not None:
        print(f"refused: {refusal}", file=sys.stderr)
        return 1

    # Advisory, and printed after the refusals so it is the last thing on screen. Exit
    # code stays 0: this is a note, not a veto.
    repeats = already_closed(message, Path(__file__).resolve().parents[3])
    if repeats:
        print(
            f"note: already closed by an earlier commit: {', '.join(repeats)}\n"
            "      Fine if you are adding the test that proves it. The count will not move.",
            file=sys.stderr,
        )
    if unmarked_install_finding(message):
        print(
            "note: this message talks about an install. If the commit answers a problem found\n"
            "      there, add Found-on: and Generic-because: lines; see CLAUDE.md.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
