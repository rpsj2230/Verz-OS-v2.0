"""Live progress, generated from git history rather than typed by anyone.

A task is done when what it asks for exists and works on an install, and the evidence this
page counts is a commit on `main` that claims the task and carries its proof. Nothing is
marked done by hand, which is the only way a progress figure stays honest: a ticked checkbox
is a claim, a merged commit is evidence.

The rule: a task id in a commit **subject**, or on a `Closes:` line, closes that task, and a
commit made from `PROOF_REQUIRED_FROM` onwards closes it only when the same commit also
carries a `Proved-on-install:` or `Proved-in-ci:` line with words on it. Body prose closes
nothing, and an ancestor id closes none of its children. All three restrictions were added
after each let the number read higher than the truth.

**The proof rule is here as well as in the commit hook, because the hook can be skipped.**
On 2026-09-17 an audit reopened 1046 of the 1213 tasks this page counted as done, because
the owner's install did not show them working: they had been claimed on the strength of unit
tests over fakes. `brain.ops.conventions` now refuses a claim without proof, and `git commit
--no-verify` walks past it. So this page applies the same rule itself, reading proof through
the same `proofs_in`, and an unproved claim is not a claim here: it neither closes a task nor
settles one that an older commit closed or reopened. See
`brain.ops.conventions.A_CLAIM_NEEDS_PROOF`.

**Earlier commits are judged as they were, and that is not leniency.** The audit read every
claim made before the rule and reopened what the install did not bear out, so what stands
from before `PROOF_REQUIRED_FROM` has already been judged against the install. Applying the
rule to the whole history would reopen those 167 for want of a trailer that did not exist
when they were written. See `A_CLAIM_IS_JUDGED_BY_THE_RULE_IN_FORCE_WHEN_IT_WAS_COMMITTED`.

**`Reopens:` needs no proof.** Taking a claim back only lowers the count, which is never the
direction a mistake flatters.

The rule stops a forgotten proof, not a forged one. The instant compared is the committer
date git records, which a person can set, and a trailer is words a person types. Reading an
install from here was rejected: this runs in CI, where no install is reachable and none
should be, and a status page that failed when an install was down would report an outage as
lost work.

The deliberate consequence is that forgetting to write an id, or its proof, means the work
does not count. That is a nuisance exactly once and then never again, and it fails in the
safe direction.

**Every other status is typed, in one file, and cannot say DONE.** The owner asked on 2026-09-17
for each task to read OPEN, IN PROGRESS, READY FOR TESTING, BLOCKED with its reason, or DONE.
The first four are a person's statement about work in flight, which no commit can make, so they
live in `docs/wbs/progress.js`, reach `wbs.json` through `export.js`, and are read here by
`progress_of`. A leaf a commit closed is DONE whatever that file says: see
`A_CLOSED_LEAF_IS_DONE_WHATEVER_THE_PROGRESS_FILE_SAYS`.

Task ids: M38.3.1.1, M38.3.1.2, M38.3.1.3, M38.3.1.4, M38.2.1.1
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel

from brain.ops.conventions import proofs_in

TASK_ID_RE = re.compile(r"\bM\d+(?:\.\d+){1,4}\b")

#: The first instant at which a claim counts only with proof on the same commit. Compared with
#: the committer timestamp `git log` gives as `%ct`, which is in UTC seconds. The day after the
#: audit that `brain.ops.conventions.A_CLAIM_NEEDS_PROOF` describes.
PROOF_REQUIRED_FROM: Final = datetime(2026, 9, 18, tzinfo=UTC)

#: Why the proof rule has a start rather than covering the whole history.
A_CLAIM_IS_JUDGED_BY_THE_RULE_IN_FORCE_WHEN_IT_WAS_COMMITTED: Final = (
    "Every claim committed before the rule was read by the 2026-09-17 audit, and the ones the "
    "owner's install did not bear out were reopened with a Reopens: line, so what stands from "
    "before has already been judged against an install. Requiring proof of those as well would "
    "reopen them for want of a trailer that did not exist when they were written, and the page "
    "would read lower than the audit found. A rebase or an amend rewrites the committer date, "
    "so an old claim carried past the start is judged by the new rule, which is the safe "
    "direction."
)


#: The statuses a person may set in `docs/wbs/progress.js`. A leaf with no entry is OPEN.
OPEN: Final = "OPEN"
IN_PROGRESS: Final = "IN PROGRESS"
READY_FOR_TESTING: Final = "READY FOR TESTING"
BLOCKED: Final = "BLOCKED"
HAND_SET_STATUSES: Final = (OPEN, IN_PROGRESS, READY_FOR_TESTING, BLOCKED)

#: The one status computed rather than typed.
DONE: Final = "DONE"

#: Why the progress file cannot hold DONE and cannot override it.
A_CLOSED_LEAF_IS_DONE_WHATEVER_THE_PROGRESS_FILE_SAYS: Final = (
    "DONE means a commit on main claimed the leaf with proof, which is evidence; the progress "
    "file is a person's word about work in flight. A file entry that could say DONE would mark "
    "a task done by hand, and one that could hold a closed leaf at IN PROGRESS would hide "
    "delivered work, so DONE is refused in the file and a closed leaf's entry is ignored"
)

#: A commit as `docs/wbs/progress.js` accepts one: an abbreviated or full lowercase hash.
COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")


class LeafProgress(BaseModel):
    """A hand-set status for one leaf, as `docs/wbs/progress.js` states it."""

    status: str
    why: str = ""
    updated: str


class WaveRecord(BaseModel):
    """The deployed commit a wave closed at, recorded by whoever accepted it on staging."""

    commit: str
    recorded: str
    note: str = ""


class WaveProgress(BaseModel):
    wave: int
    name: str
    total: int
    done: int
    percent: float = 0.0
    #: Buildable leaves in this wave that no commit closed, by hand-set status. With `done`
    #: they sum to `total`, because a closed leaf counts only as done.
    in_progress: int = 0
    ready_for_testing: int = 0
    blocked: int = 0
    open: int = 0
    #: Leaves in this wave a person does on the week of a migration, left out of `total`.
    acts: int = 0
    #: Leaves in this wave decided as not needed as written, left out of `total` and `acts`.
    decided: int = 0


class ModuleProgress(BaseModel):
    module: str
    name: str
    wave: int
    total: int
    done: int
    #: Leaves in this module a person does rather than a commit, left out of `total`.
    acts: int = 0
    #: Leaves in this module decided as not needed as written, left out of `total` and `acts`.
    decided: int = 0


class Status(BaseModel):
    """What is built, as of a specific commit."""

    generated_at: str
    commit: str
    commit_subject: str = ""
    #: Buildable leaves only. See `THE_PERCENTAGE_COUNTS_WHAT_A_COMMIT_CAN_CLOSE`.
    total: int = 0
    done: int = 0
    percent: float = 0.0
    #: Leaves flagged in `docs/wbs/acts.js`: work a person does on the week of a migration,
    #: counted here and never in `total`, so they stay visible without holding the figure down.
    acts: int = 0
    #: Leaves flagged DECIDED: not needed as written, by the owner's decision. Neither in
    #: `total` nor in `acts`. See `A_LEAF_DECIDED_AGAINST_IS_NEITHER_BUILDABLE_NOR_A_CLIENT_TASK`.
    decided: int = 0
    current_wave: int | None = None
    waves: list[WaveProgress] = []
    modules: list[ModuleProgress] = []
    done_task_ids: list[str] = []
    #: Hand-set statuses of leaves no commit has closed, by id. A closed leaf is absent here
    #: whatever the progress file says, so a reader of this field cannot show it as anything
    #: but DONE.
    leaf_status: dict[str, LeafProgress] = {}
    #: The deployed commit each wave closed at, by wave number as a string.
    wave_records: dict[str, WaveRecord] = {}
    #: How many leaves closed since midnight UTC. Zero is a real and common answer, and
    #: showing it is the point: a page that only ever shows movement cannot show a stall.
    closed_today: int = 0
    #: The next few unclosed leaves in the current wave, in plan order. Answers "what is
    #: next" without anybody opening the tracker and reading down it.
    next_up: list[str] = []
    recent: list[dict[str, str]] = []


#: Only these lines carry claims. Prose does not.
CLOSES_RE = re.compile(r"^\s*closes:\s*(.+)$", re.IGNORECASE | re.MULTILINE)

#: How a mistaken claim is taken back. A trailer only, never the subject line, because a
#: subject mention is what causes the mistake this exists to correct.
#:
#: `M0.4.2` is the case that prompted it. A commit whose subject read "M0.4.2: mount the
#: Postgres volume at the path 18 expects" closed that leaf. The commit was about a volume
#: path; the leaf is `docker-compose.full.yml`, which deliberately does not exist, and an
#: earlier commit had said in its body that it was NOT claiming it. So the plan showed a
#: leaf as delivered because an id appeared in a sentence about something else.
#:
#: The alternative was to stop reading ids from subject lines at all. Measured before
#: choosing: exactly three leaves rest on a subject-line claim, and two of them are
#: deliberate ("M0.4.4: a seed command that refuses to run somewhere real"). Dropping the
#: rule would have un-closed two true claims to fix one false one.
REOPENS_RE = re.compile(r"^\s*reopens:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def reopened_ids(body: str) -> set[str]:
    """Task ids a commit takes back. Trailer only; the subject cannot reopen anything."""
    ids: set[str] = set()
    for line in REOPENS_RE.findall(body):
        ids.update(TASK_ID_RE.findall(line))
    return ids


def claimed_ids(subject: str, body: str) -> set[str]:
    """Task ids a commit actually claims.

    Read from the subject line and from `Closes:` lines only, never from body prose.

    That restriction was added after a commit whose body listed ten ids under
    "Deliberately NOT claimed, with the reason" and thereby claimed all ten. The parser
    has no concept of negation and cannot be given one reliably: "not M0.6.5", "M0.6.5 is
    not done" and "blocked: M0.6.5" all read identically to a scanner, and the failure is
    silent and in the wrong direction.

    So the rule is positional rather than semantic. A commit may discuss any id it likes
    in its body; only the subject and an explicit trailer count.
    """
    ids: set[str] = set(TASK_ID_RE.findall(subject))
    for line in CLOSES_RE.findall(body):
        ids.update(TASK_ID_RE.findall(line))
    return ids


def counted_ids(subject: str, body: str, committed_at: int) -> set[str]:
    """Task ids a commit's claim counts for on this page: `claimed_ids`, once proof is due.

    A commit made at or after `PROOF_REQUIRED_FROM` with no `Proved-on-install:` or
    `Proved-in-ci:` line in its body counts for nothing, as though it claimed nothing. Proof is
    read from the body only, because that is where a trailer is: a subject line reading like one
    is a sentence. `claimed_ids` keeps its meaning, what a commit says, and this is what the
    tracker believes of it.

    `committed_at` is the committer timestamp in UTC seconds, as `git log` prints `%ct`.
    """
    claimed = claimed_ids(subject, body)
    if committed_at >= PROOF_REQUIRED_FROM.timestamp() and not proofs_in(body):
        return set()
    return claimed


def _git(*args: str, cwd: Path | None = None) -> str:
    """Git's output as text, decoded as UTF-8 whatever the machine's codepage is.

    **`text=True` alone decodes with the platform's ANSI codepage, and that is a bug rather
    than a preference.** Git writes commit messages as UTF-8. On Windows the default is
    cp1252, so the first commit message containing a character it does not have takes the
    whole status page down: on 2026-09-09 a commit body quoting a Chinese phrase made
    `build_status` raise, and what raised was a decode inside `subprocess.run`, so the
    traceback named this line and not the commit. A curly quote pasted from a word processor
    does the same thing.

    `errors="replace"` rather than strict, because everything read here is a subject line, a
    body and a task id, and a replacement character in a subject is harmless while refusing to
    build the page is not. The ids themselves are ASCII by their own grammar, so no
    replacement can change one.
    """
    try:
        return subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=cwd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=30,
        ).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def closed_task_ids(repo: Path, ref: str = "HEAD") -> tuple[set[str], list[dict[str, str]]]:
    """Every task id claimed by a commit reachable from `ref`, newest first.

    See claimed_ids for what counts as a claim: the subject line and `Closes:` trailers,
    never body prose. See counted_ids for when a claim counts: from `PROOF_REQUIRED_FROM`,
    only with proof on the same commit.
    """
    raw = _git("log", ref, "--pretty=format:%H%x1f%ct%x1f%s%x1f%b%x1e", cwd=repo)

    # There is deliberately no `if not raw: return set(), []` here, and there was one until a
    # mutation showed it could not change an outcome. An empty string splits into one empty
    # entry, that entry has fewer than three fields, the loop skips it, and the function
    # returns the same empty pair the guard returned. A repository with no commits and a
    # machine with no git both arrive that way, so the path is exercised on every fresh
    # install rather than being rare: a guard that runs often and decides nothing is the
    # worst kind, because it reads as the thing keeping the reader safe.
    found: set[str] = set()
    #: Ids already settled by a newer commit. See the loop below.
    decided: set[str] = set()
    recent: list[dict[str, str]] = []
    for entry in raw.split("\x1e"):
        # Strip line endings only, never str.strip(). Python counts \x1c through \x1f as
        # whitespace, so a bare .strip() eats the trailing unit separator, and a commit
        # with an empty body (any one-line message, which is most of them) then splits
        # into three fields instead of four and is silently dropped. That would have
        # under-counted progress with no error anywhere.
        parts = entry.lstrip("\r\n").split("\x1f", 3)
        if len(parts) < 3:
            continue
        sha, ts, subject = parts[0], parts[1], parts[2]
        body = parts[3] if len(parts) > 3 else ""
        # Every record git writes starts with a hash and a number. One that does not came out
        # of a commit message holding the separators, and it is text somebody typed rather than
        # a commit: skipped, as `closed_since` skips it. Until the proof rule this was read only
        # for a record that claimed something, and then raised, which took the page down.
        try:
            committed_at = int(ts)
        except ValueError:
            continue
        closes = counted_ids(subject, body, committed_at)
        reopens = reopened_ids(body)
        # The most recent statement about an id wins, and `git log` walks newest first, so
        # the first commit to mention an id decides it. Without `decided`, an old `Closes:`
        # would put back what a newer `Reopens:` took away, and the correction would appear
        # to work on the day it was written and silently stop working afterwards.
        for tid in reopens - decided:
            decided.add(tid)
        for tid in closes - decided:
            decided.add(tid)
            found.add(tid)
        ids = sorted(closes - reopens)
        if ids and len(recent) < 20:
            recent.append(
                {
                    "sha": sha[:7],
                    "at": datetime.fromtimestamp(committed_at, UTC).isoformat(),
                    "subject": subject,
                    "closed": ",".join(ids),
                }
            )
    return found, recent


def closed_since(repo: Path, when: datetime, ref: str = "HEAD") -> set[str]:
    """Task ids claimed by commits made on or after `when`.

    **Filtered in Python, not with `git log --since`.** `--since` prunes the walk: it
    stops descending a line of history at the first commit older than the cutoff, so a
    single old commit sitting at the tip hides every newer commit behind it. That is not
    hypothetical - a rebase, a cherry-pick or any amended date produces exactly that
    shape, and the count comes back zero with no error anywhere. Found by a test that
    dated one commit to last week and expected the other three to still count.

    A separate walk rather than a filter over `recent`, because `recent` is capped at
    twenty entries: counting from it would be right on a quiet day and quietly wrong on a
    busy one, which is the worse of the two failures.

    `when` is passed in rather than computed here so the caller decides what "today"
    means. It has to be UTC: the build runs on a CI runner in one timezone, the server is
    in another and the person reading is in a third, and a day boundary that depends on
    who is asking gives three different answers to one question.
    """
    raw = _git("log", ref, "--pretty=format:%ct%x1f%s%x1f%b%x1e", cwd=repo)
    cutoff = when.timestamp()
    found: set[str] = set()
    for entry in raw.split("\x1e"):
        # There is deliberately no `if not entry.strip(): continue` here, and there was one
        # until a mutation showed it could not change an outcome. Every entry that `strip()`
        # empties holds no `\x1f`, so it splits into one part and the length test below
        # catches it. The format ends every record with the separator, so the last entry is
        # always empty and this path runs on every call: a guard that runs constantly and
        # decides nothing is worse than an absent one, because it reads as the thing keeping
        # the loop safe.
        #
        # `lstrip` of line endings only, never `strip()`: Python counts \x1c through
        # \x1f as whitespace, so a bare strip eats the unit separator and a one-line
        # message then splits wrongly. The same trap as in `closed_task_ids` above.
        parts = entry.lstrip("\r\n").split("\x1f", 2)
        # Reachable only by a commit message holding two record separators with nothing but
        # digits between them, which is the one shape the `int()` below does not refuse for
        # us: every other single-field entry is text, raises `ValueError` and is skipped
        # there. Narrow, and it is the difference between skipping a record and an
        # `IndexError` that takes the build status page down, so it stays and there is a test
        # that writes exactly that message.
        if len(parts) < 2:
            continue
        try:
            committed_at = int(parts[0])
        except ValueError:
            continue
        if committed_at < cutoff:
            continue
        # The tracker's rule rather than the bare claim, so "closed today" can never name a
        # leaf `closed_task_ids` does not count.
        found.update(counted_ids(parts[1], parts[2] if len(parts) > 2 else "", committed_at))
    return found


def _leaf_ids(node: Any, prefix: str, out: list[str]) -> None:
    """Walk the WBS exactly as the renderer numbers it, so ids line up with the tracker."""
    children = node.get("s") or []
    keys = node.get("k") or []
    for i, child in enumerate(children, start=1):
        cid = f"{prefix}.{i}"
        if isinstance(child, str):
            out.append(cid)
        else:
            _leaf_ids(child, cid, out)
    for i in range(1, len(keys) + 1):
        out.append(f"{prefix}.{len(children) + i}")


def _is_closed(leaf: str, closed: set[str]) -> bool:
    """A leaf counts as closed only when its own id is named. Ancestors close nothing.

    This was the other way round until 2026-09-04, on the reasoning that nobody lists
    forty leaf ids when a whole subtree lands together. That convenience was quietly
    inflating the number: a commit saying `M0.6` closed all seven children including
    connector cassettes, which were not written, and a commit saying `M0.3` closed the
    PgBouncer tasks, which do not exist yet either.

    Nothing warned, because an ancestor id is exactly what an honest commit for a large
    piece of work looks like. The page's entire claim is that it cannot show progress that
    does not exist, so the rule has to be the strict one and commits have to list what
    they actually closed.
    """
    return leaf in closed


#: Why the headline leaves out the leaves `docs/wbs/acts.js` flags.
THE_PERCENTAGE_COUNTS_WHAT_A_COMMIT_CAN_CLOSE: Final = (
    "An act is work a person does on the week of a migration, such as training staff or "
    "running the restore drill in front of a client, and no commit can close one. Counted "
    "in the denominator they hold the figure below 100 percent for ever, and a figure that "
    "stops rising reads as a build that has stalled. So total, done and percent count the "
    "leaves a commit can close, per wave and per module as well as overall, and acts are "
    "reported beside them as their own number rather than dropped."
)


def acts_of(module: dict[str, Any]) -> dict[str, Any]:
    """The act flags a module carries in the exported work breakdown, keyed by leaf id.

    The one place the flag is read off a module. `brain.migration.checklist.load_acts` builds
    its checklist from this, so the page and the checklist cannot disagree about which leaves
    are acts.
    """
    flags: dict[str, Any] = module.get("leaf_acts", {}) or {}
    return flags


#: Why a leaf decided against is counted on its own rather than as buildable or as an act.
A_LEAF_DECIDED_AGAINST_IS_NEITHER_BUILDABLE_NOR_A_CLIENT_TASK: Final = (
    "The owner can decide a leaf is not needed as written, as Needs Rupash item 58 did for "
    "nine plugin interfaces the extension-point register gives no plugin answer. Left in "
    "total it holds the percentage down with work nobody will do; folded into acts it "
    "appears as a client task on the week of a migration and on the delivery checklist, "
    "which is a person sent to do something that was decided against. So it is its own "
    "count, beside the other two, and the three together are the whole plan."
)

#: Why one leaf may not be both an act and decided.
A_LEAF_IS_EITHER_WORK_FOR_A_PERSON_OR_DECIDED_NEVER_BOTH: Final = (
    "flagged both as an act and as decided, so the checklist would list it while the "
    "status page counted it as not needed. export.js writes each flag to one field; a "
    "wbs.json holding both was edited by hand or left behind by a failed export"
)


def decided_of(module: dict[str, Any]) -> dict[str, Any]:
    """The DECIDED flags a module carries in the exported work breakdown, keyed by leaf id.

    The one place that flag is read off a module, and it refuses a leaf that `acts_of` also
    returns, because the checklist reads one field and this page the other, and a leaf in both
    is the two disagreeing about whether somebody has work to do.
    """
    flags: dict[str, Any] = module.get("leaf_decided", {}) or {}
    both = sorted(set(flags) & set(acts_of(module)))
    if both:
        reason = A_LEAF_IS_EITHER_WORK_FOR_A_PERSON_OR_DECIDED_NEVER_BOTH
        msg = f"{module['id']}: {', '.join(both)} {reason}"
        raise ValueError(msg)
    return flags


def _is_day(raw: object) -> bool:
    """Whether a value is a calendar day written YYYY-MM-DD."""
    if not isinstance(raw, str) or len(raw) != 10:
        return False
    try:
        date.fromisoformat(raw)
    except ValueError:
        return False
    return True


def progress_of(module: dict[str, Any]) -> dict[str, LeafProgress]:
    """The hand-set statuses a module carries in the exported work breakdown, keyed by leaf id.

    Refuses what `docs/wbs/progress.js` refuses, because `wbs.json` can be edited by hand or left
    behind by a failed export: an id that is not this module's leaf, a status outside
    `HAND_SET_STATUSES` (DONE included), BLOCKED with no reason, and an undated entry.
    """
    raw: dict[str, Any] = module.get("leaf_progress", {}) or {}
    leaves = set(module.get("leaf_ids", []))
    wrong: list[str] = []
    found: dict[str, LeafProgress] = {}
    for leaf, entry in raw.items():
        state = entry.get("status")
        why = str(entry.get("why") or "").strip()
        if leaf not in leaves:
            wrong.append(f"{leaf} is not a leaf of {module['id']}")
        if state not in HAND_SET_STATUSES:
            wrong.append(f"{leaf} has status {state!r}, which is none of {HAND_SET_STATUSES}")
        if state == BLOCKED and not why:
            wrong.append(f"{leaf} is BLOCKED with no reason")
        if not _is_day(entry.get("updated")):
            wrong.append(f"{leaf} has no updated day")
        if not wrong:
            found[leaf] = LeafProgress(status=state, why=why, updated=entry["updated"])
    if wrong:
        raise ValueError(f"{module['id']}: " + "; ".join(wrong))
    return found


def wave_records_of(wbs: dict[str, Any]) -> dict[str, WaveRecord]:
    """The recorded end-of-wave commits, refusing a wave that does not exist or a bad record."""
    names: dict[str, str] = wbs.get("wave_names", {})
    wrong: list[str] = []
    found: dict[str, WaveRecord] = {}
    for wave, rec in (wbs.get("wave_records", {}) or {}).items():
        if wave not in names:
            wrong.append(f"wave {wave} is not a wave")
        if not COMMIT_RE.match(str(rec.get("commit", ""))):
            wrong.append(f"wave {wave} records {rec.get('commit')!r}, which is not a commit")
        if not _is_day(rec.get("recorded")):
            wrong.append(f"wave {wave} has no recorded day")
        if not wrong:
            found[wave] = WaveRecord(
                commit=rec["commit"], recorded=rec["recorded"], note=str(rec.get("note") or "")
            )
    if wrong:
        raise ValueError("; ".join(wrong))
    return found


def build_status(repo: Path, wbs: dict[str, Any], ref: str = "HEAD") -> Status:
    closed, recent = closed_task_ids(repo, ref)
    wave_names: dict[str, str] = wbs.get("wave_names", {})

    modules: list[ModuleProgress] = []
    #: Wave to [buildable leaves, of those closed, acts, decided].
    per_wave: dict[int, list[int]] = {}
    total = done = acts = decided = 0
    matched: set[str] = set()
    #: Wave to hand-set status to how many unclosed buildable leaves hold it.
    per_wave_status: dict[int, dict[str, int]] = {}
    leaf_status: dict[str, LeafProgress] = {}

    for m in wbs.get("modules", []):
        leaves: list[str] = m.get("leaf_ids", [])
        wave = int(m.get("wave", 0))
        # A leaf can sit in a later wave than its module. M38 is the reason: the delivery
        # pipeline is wave 0, but "what is live after wave 3" cannot be done before wave 3.
        # Counting those against wave 0 puts work in the denominator that wave 0 cannot do,
        # so the wave could never reach 100% and the figure understated real progress.
        leaf_waves: dict[str, int] = m.get("leaf_waves", {})
        flags = acts_of(m)
        decisions = decided_of(m)
        hand_set = progress_of(m)
        m_total = m_done = m_acts = m_decided = 0
        for leaf in leaves:
            leaf_done = _is_closed(leaf, closed)
            if leaf_done:
                # Still listed as closed even for an act, so the tracker ticks it.
                matched.add(leaf)
            elif leaf in hand_set:
                # Only when not closed. See A_CLOSED_LEAF_IS_DONE_WHATEVER_THE_PROGRESS_FILE_SAYS.
                leaf_status[leaf] = hand_set[leaf]
            bucket = per_wave.setdefault(int(leaf_waves.get(leaf, wave)), [0, 0, 0, 0])
            # Before the act test, and neither in `total` nor in `acts`. See
            # A_LEAF_DECIDED_AGAINST_IS_NEITHER_BUILDABLE_NOR_A_CLIENT_TASK.
            if leaf in decisions:
                m_decided += 1
                bucket[3] += 1
                continue
            if leaf in flags:
                m_acts += 1
                bucket[2] += 1
                continue
            m_total += 1
            m_done += int(leaf_done)
            bucket[0] += 1
            bucket[1] += int(leaf_done)
            if not leaf_done:
                state = hand_set[leaf].status if leaf in hand_set else OPEN
                counts = per_wave_status.setdefault(int(leaf_waves.get(leaf, wave)), {})
                counts[state] = counts.get(state, 0) + 1
        modules.append(
            ModuleProgress(
                module=m["id"],
                name=m["name"],
                wave=wave,
                total=m_total,
                done=m_done,
                acts=m_acts,
                decided=m_decided,
            )
        )
        total += m_total
        done += m_done
        acts += m_acts
        decided += m_decided

    waves = [
        WaveProgress(
            wave=w,
            name=wave_names.get(str(w), f"Wave {w}"),
            total=t,
            done=d,
            percent=round(100 * d / t, 1) if t else 0.0,
            acts=a,
            decided=x,
            in_progress=per_wave_status.get(w, {}).get(IN_PROGRESS, 0),
            ready_for_testing=per_wave_status.get(w, {}).get(READY_FOR_TESTING, 0),
            blocked=per_wave_status.get(w, {}).get(BLOCKED, 0),
            open=per_wave_status.get(w, {}).get(OPEN, 0),
        )
        for w, (t, d, a, x) in sorted(per_wave.items())
    ]
    # The first unfinished wave. None means every wave is complete, so there is no
    # current wave rather than a misleading "wave 5".
    current = next((w.wave for w in waves if w.done < w.total), None)

    # Midnight UTC rather than local. The build runs on a CI runner in one timezone, the
    # server is in another and Rupash is in a third; "today" has to mean one thing or the
    # number changes depending on who is asking.
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    closed_today = len(closed_since(repo, midnight, ref) & set(matched))

    # Plan order, not id order. The WBS lists leaves in the sequence they are meant to be
    # done, and re-sorting them would answer a different question: `M12.1.10` sorts before
    # `M12.1.2` as a string, and the plan does not mean that.
    next_up: list[str] = []
    for m in wbs.get("modules", []):
        waves_by_leaf: dict[str, int] = m.get("leaf_waves", {})
        flags = acts_of(m)
        decisions = decided_of(m)
        for leaf in m.get("leaf_ids", []):
            # An act is not "next" for a build: no commit can close it. Nor is a leaf decided
            # against, which nobody is meant to close at all.
            if leaf in closed or leaf in flags or leaf in decisions:
                continue
            if current is not None and waves_by_leaf.get(leaf, int(m.get("wave", 0))) != current:
                continue
            next_up.append(leaf)
            if len(next_up) == 5:
                break
        if len(next_up) == 5:
            break

    return Status(
        generated_at=datetime.now(UTC).isoformat(),
        commit=_git("rev-parse", "--short", "HEAD", cwd=repo) or "unknown",
        commit_subject=_git("log", "-1", "--pretty=%s", cwd=repo),
        total=total,
        done=done,
        percent=round(100 * done / total, 1) if total else 0.0,
        acts=acts,
        decided=decided,
        current_wave=current,
        waves=waves,
        modules=modules,
        done_task_ids=sorted(matched),
        leaf_status=leaf_status,
        wave_records=wave_records_of(wbs),
        closed_today=closed_today,
        next_up=next_up,
        recent=recent,
    )


def load_wbs(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    for m in data.get("modules", []):
        if "leaf_ids" not in m:
            ids: list[str] = []
            for i, task in enumerate(m.get("tasks", []), start=1):
                _leaf_ids(task, f"{m['id']}.{i}", ids)
            m["leaf_ids"] = ids
    return data


#: Why a length mismatch refuses rather than zipping to the shorter of the two. The arrays are
#: positional, so one missing sentence does not lose one leaf: it shifts every leaf after it by
#: one, and each of them then reads as a confident, wrong sentence. A test anchored to a leaf
#: would be comparing a constant against its neighbour's specification and passing or failing
#: for reasons nobody could reconstruct.
A_SHORT_LIST_OF_SENTENCES_RENAMES_EVERY_LEAF: Final[str] = (
    "leaf_texts is positional and shorter than leaf_ids, which misattributes every leaf "
    "after the gap rather than losing one; re-run docs/wbs/export.js"
)


def leaf_sentences(path: Path) -> dict[str, str]:
    """What each leaf of the work breakdown actually says, by id.

    **The leaf sentence is the only thing outside a module that can settle whether the module
    got the leaf right.** Everything else a test could compare a constant against is written
    by the same person on the same afternoon. `TELEMETRY_FIELDS` names eighteen fields because
    M27.1.5 lists eighteen fields; a test that restates those names in the test file, or reads
    them back out of the module, is green for every list the module could hold.

    The sentences live in `docs/wbs/*.js` and Python cannot read those, which is why this went
    unchecked: reaching them meant shelling out to node from a test. `export.js` now writes
    them into `wbs.json` alongside the ids, positionally aligned and built in the same push so
    they cannot drift, and this is the reader.

    Absent rather than raising when a module predates the field, because `load_wbs` already
    tolerates a WBS without `leaf_ids` and a reader that refuses an older export would make
    this the one function that cannot run against a checkout from last week. A module carrying
    the field with the wrong number of sentences is the opposite case and refuses, for the
    reason named below.
    """
    found: dict[str, str] = {}
    for module in load_wbs(path).get("modules", []):
        ids: list[str] = module.get("leaf_ids", [])
        texts: list[str] = module.get("leaf_texts", [])
        if not texts:
            continue
        if len(ids) != len(texts):
            raise ValueError(f"{module['id']}: {A_SHORT_LIST_OF_SENTENCES_RENAMES_EVERY_LEAF}")
        found.update(zip(ids, texts, strict=True))
    return found


def main(repo: Path | None = None) -> int:
    """Write docs/status.json. Runs in CI before the image is built.

    `repo` is a parameter with the derived path as its default, and the argument for it is the
    refusal below. A function that can only ever be pointed at this repository has a
    missing-file branch nothing can reach, so the one line that decides what happens when the
    work breakdown is absent goes untested, and CI is where it would first run. It is also how
    `brain.ops.recovery.backup_policy_gaps` is written and for the same stated reason.
    """
    repo = Path(__file__).resolve().parents[2] if repo is None else repo
    wbs_path = repo / "docs" / "wbs.json"
    if not wbs_path.exists():
        print(f"no WBS at {wbs_path}")
        return 1
    status = build_status(repo, load_wbs(wbs_path))
    out = repo / "docs" / "status.json"
    out.write_text(status.model_dump_json(indent=2), encoding="utf-8")
    print(
        f"{status.done}/{status.total} tasks ({status.percent}%) - wave {status.current_wave}"
        f" - {status.acts} acts, {status.decided} decided"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
