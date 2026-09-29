"""The queue of skills waiting for somebody to read them.

A skill is instructions an agent follows with the tools its caller already holds. That is
the whole risk: a skill needs no permission of its own, because it borrows the reader's.
"Check the client's contract value and email the finance team" is a procedure, and if an
agent runs it for somebody who can do both, it happens - so the review is not a formality
about code quality, it is the only place a person decides whether a procedure should exist.

**The queue is ordered by how long something has waited, not by who submitted it.** A
priority field would be a way for whoever submits to jump the queue, and the person who most
wants their skill approved is exactly the person who would set it.

**A diff shows what changed, never a version number.** `diff_skills` names the fields, and a
review that showed "version 1.0.0 to 1.0.1" would let an author change the body while
bumping a patch number. The body is the part that matters and the version is the part an
author types.

**An approved skill that is then edited returns to the queue with no argument.**
`ImportedSkill.with_content` clears the review, and this module never re-approves anything:
there is no path here that takes something out of the queue except a person deciding.

**The review pane shows the words that changed, not only which fields did (M12.2.6).** A queue
entry names the changed fields, which is enough to sort a hundred of them; it is not enough to
decide one, because "body changed" on a page of instructions sends the reviewer to read the whole
page again, and a reviewer asked to find one altered sentence in forty is a reviewer who approves
without finding it. `content_diff` is the words: each frontmatter field before and after, and the
body line by line as kept, removed and added, in order, so the kept and removed lines are the old
body and the kept and added lines are the new one. Rejected: a unified diff as one string. It is
a format for a terminal, its hunk headers are numbers a reviewer has to decode, and a console
would have to parse it back into lines to colour them.

Task ids: M12.2.6
"""

from __future__ import annotations

import difflib
import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from brain.tools.skills import (
    ImportedSkill,
    ScriptFile,
    Skill,
    SkillExample,
    SkillState,
    diff_skills,
)

#: How long something may sit unreviewed before it is called out. Not an expiry: nothing is
#: auto-rejected, because an auto-rejection is a decision nobody made and the author would
#: simply resubmit. It is the line the queue view leads with.
STALE_AFTER = timedelta(days=7)


@dataclass(frozen=True)
class QueueEntry:
    """One thing waiting, and what a reviewer needs to decide about it.

    `changed` is empty for a first submission and holds field names for an edit. The
    distinction matters to a reviewer more than anything else on this type: a new skill has
    to be read in full, and an edit to an approved one needs only the changed fields read -
    which is the difference between a review that happens and one that is postponed.
    """

    skill: ImportedSkill
    waiting_since: datetime
    changed: tuple[str, ...] = ()

    @property
    def is_edit(self) -> bool:
        return bool(self.changed)

    def waited(self, now: datetime) -> timedelta:
        return now - self.waiting_since

    def is_stale(self, now: datetime) -> bool:
        return self.waited(now) >= STALE_AFTER


def pending(
    imported: Sequence[ImportedSkill],
    *,
    previous: dict[str, Skill] | None = None,
    submitted_at: dict[str, datetime] | None = None,
    now: datetime,
) -> tuple[QueueEntry, ...]:
    """Everything waiting for a decision, oldest first.

    **Oldest first, and there is no priority argument.** A priority field is a way for
    whoever submits to jump the queue, and the person who most wants their skill approved is
    exactly the person who would set it. Time waited is the one ordering nobody can game by
    caring more.

    Rejected skills are not here. A rejection is a decision, and a queue that showed
    decisions alongside things awaiting one would make the count meaningless - the number a
    person looks at is "how many are waiting for me".

    `previous` maps a skill name to the version last approved, so an edit can be shown as a
    diff. Absent, everything reads as a first submission, which is the safe direction: it
    asks for more reading rather than less.
    """
    prior = previous or {}
    when = submitted_at or {}
    entries: list[QueueEntry] = []
    for item in imported:
        if item.state is not SkillState.IMPORTED:
            continue
        name = item.skill.name
        was = prior.get(name)
        entries.append(
            QueueEntry(
                skill=item,
                # `now` when nobody recorded a submission time. Not the epoch: an unknown
                # time defaulting to 1970 would put every such entry at the top of a queue
                # ordered by age, which is the opposite of what an unknown means.
                waiting_since=when.get(name, now),
                changed=diff_skills(was, item.skill) if was is not None else (),
            )
        )
    return tuple(sorted(entries, key=lambda e: e.waiting_since))


def stale(entries: Sequence[QueueEntry], now: datetime) -> tuple[QueueEntry, ...]:
    """The ones that have waited too long.

    Reported rather than acted on. Nothing here auto-rejects: an auto-rejection is a
    decision nobody made, the author would resubmit, and the queue would be the same length
    with one more round trip in it.
    """
    return tuple(e for e in entries if e.is_stale(now))


@dataclass(frozen=True)
class QueueSummary:
    """What the console shows above the list. Counts only.

    No names. A summary naming the skills waiting would be readable by whoever can see the
    console, and a skill's name describes a procedure somebody wants to run - which is a
    fact about what a team is doing. The list below it is the place for names, and it is
    behind the same permission the console is.
    """

    waiting: int = 0
    edits: int = 0
    stale: int = 0

    @property
    def first_submissions(self) -> int:
        return self.waiting - self.edits


def summarise(entries: Sequence[QueueEntry], now: datetime) -> QueueSummary:
    return QueueSummary(
        waiting=len(entries),
        edits=sum(1 for e in entries if e.is_edit),
        stale=len(stale(entries, now)),
    )


# ------------------------------------------------------------ the words that changed (M12.2.6)
#: The frontmatter a reviewer reads, in the order a `SKILL.md` declares it, then the sha256 of each
#: script's bytes and the example tasks, which travel beside it (M12.4.11, M12.3.4). The body is
#: diffed by line and never shown here as one value.
DIFFED_FIELDS: Final[tuple[str, ...]] = (
    "name",
    "description",
    "version",
    "tools",
    "scripts",
    "script_files",
    "examples",
)


class LineChange(enum.StrEnum):
    """What happened to one line of a body between two versions."""

    KEPT = "kept"
    REMOVED = "removed"
    ADDED = "added"


@dataclass(frozen=True)
class DiffLine:
    """One line of the body, and whether the new version kept, removed or added it."""

    change: LineChange
    text: str


@dataclass(frozen=True)
class FieldChange:
    """One frontmatter field that differs, with both values as a reviewer reads them."""

    field: str
    before: str
    after: str


@dataclass(frozen=True)
class SkillDiff:
    """What an edit changed: the frontmatter fields that differ, and the body line by line."""

    fields: tuple[FieldChange, ...]
    body: tuple[DiffLine, ...]

    @property
    def body_changed(self) -> bool:
        return any(line.change is not LineChange.KEPT for line in self.body)

    def old_body(self) -> tuple[str, ...]:
        return tuple(line.text for line in self.body if line.change is not LineChange.ADDED)

    def new_body(self) -> tuple[str, ...]:
        return tuple(line.text for line in self.body if line.change is not LineChange.REMOVED)


def _shown(value: object) -> str:
    """A field as the reviewer reads it: a list joined with commas, anything else as written.

    A script is its path and the sha256 of its bytes, and an example its task and what is expected
    of it, so a changed byte or a reworded expectation reads as that rather than as a model's repr.
    """
    if isinstance(value, tuple):
        return ", ".join(_item(item) for item in value)
    return str(value)


def _item(item: object) -> str:
    if isinstance(item, ScriptFile):
        return f"{item.path} ({item.sha256})"
    if isinstance(item, SkillExample):
        return f"{item.task} -> {item.expected}"
    return str(item)


def content_diff(old: Skill, new: Skill) -> SkillDiff:
    """The words that changed between two versions of a skill, for the review pane (M12.2.6).

    `autojunk` is off: its heuristic treats a line that recurs often, a blank line or a closing
    bracket, as noise to be skipped when matching, which on a document of instructions is
    exactly the line whose removal changes the meaning of the step after it.
    """
    fields = tuple(
        FieldChange(field=name, before=_shown(getattr(old, name)), after=_shown(getattr(new, name)))
        for name in DIFFED_FIELDS
        if getattr(old, name) != getattr(new, name)
    )
    before = old.body.split("\n") if old.body else []
    after = new.body.split("\n") if new.body else []
    lines: list[DiffLine] = []
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            lines.extend(DiffLine(LineChange.KEPT, text) for text in before[i1:i2])
            continue
        lines.extend(DiffLine(LineChange.REMOVED, text) for text in before[i1:i2])
        lines.extend(DiffLine(LineChange.ADDED, text) for text in after[j1:j2])
    return SkillDiff(fields=fields, body=tuple(lines))
