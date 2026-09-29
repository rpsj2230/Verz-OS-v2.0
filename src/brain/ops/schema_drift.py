"""Which fields a connected source no longer answers: the policy of the nightly schema check.

A connector reads a source through a field mapping: `Status` becomes an invoice's `status`,
`description_text` a ticket's body. When the source renames or removes a field, the mapping
resolves nothing, `brain.connectors.rest.RestOperation.project` contributes nothing for the path
(rightly: a vendor omitting a field has said something different from one sending an empty
value), and every question that needed the field is answered "nothing found". That is the silent
failure this module exists to end: the answer reads as a fact about the company's records when it
is a fact about the connector.

**The schema is what the source answers, read once a night.** `brain.ops.schema_drift_run` asks
each connected source for the first page of each kind of record it reads, and, where the source
reads one record live by a call of its own, for one record by that call, and hands this module
what came back: which of the mapping's fields any record answered, out of how many records. A
source's own field list was the cheaper design and it is rejected: Xero publishes none, and
Freshdesk's names its fields differently from the keys its records carry (`requester` for
`requester_id`), so comparing it with a mapping would be a second mapping that could itself go
wrong. The paths the mapping reads are exactly what a tool depends on, so they are what is
checked. See `THE_SCHEMA_IS_WHAT_THE_SOURCE_ANSWERS`.

**A field is gone only when it was answered before.** Some fields are empty on most records of a
small company (a contact's tax number) and a source may leave an empty field out of a record
altogether, so a field no record answered tonight has not therefore been renamed. It is found gone
when an earlier night saw a record answer it and tonight no record does; a field no record has
ever answered is one this source leaves empty, and says nothing. **A night that read no record
says nothing either**: an empty ledger, a refused call or a spent allowance keep what the last
night found, rather than clearing a finding nobody fixed or raising one nobody saw. See
`A_FIELD_IS_GONE_ONLY_WHEN_IT_WAS_ANSWERED_BEFORE`.

**What is kept is field names and counts, never a value.** A finding names the mapping's own
targets, which are this release's words, and how many records were read. Nothing a record held is
kept, and the table's own check refuses anything but a name in either list.

**What it does to an answer.** A question whose rule reads a field its source no longer answers is
told the source could not be fully read, the degraded sentence, rather than that nothing was found,
and the Connectors screen shows the source as degraded. `brain.gate.answer` holds the first half
and `brain.console.connector_detail` the second. See `A_TOOL_WHOSE_FIELD_IS_GONE_ANSWERS_DEGRADED`.

Rejected: finding drift in the scheduled read itself, which already reads every page. It reads a
list, so a field only a one-record call returns (a ticket's body) would never be judged, and it
runs every few minutes, so a finding would flap with every page a small ledger happened to hold.

Scope: domain logic. Nothing here reads a table or makes a call.

Task ids: M11.8.7
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

# ------------------------------------------------------------------ written-down reasons

#: Why the check reads records rather than a field list.
THE_SCHEMA_IS_WHAT_THE_SOURCE_ANSWERS: Final = (
    "A connector reads a source through the paths its field mapping names, so a tool depends on "
    "those paths and on nothing else the source publishes. The check reads the first page of "
    "each kind of record the connector reads, and one record by the call a source reads one "
    "record by, and asks which mapped fields any of them answered. A vendor's own field list "
    "names fields differently from the keys its records carry, and some vendors publish none."
)

#: Why a field no record answered tonight is not yet a field that is gone.
A_FIELD_IS_GONE_ONLY_WHEN_IT_WAS_ANSWERED_BEFORE: Final = (
    "A field is found renamed or removed when an earlier night saw a record answer it and tonight "
    "no record does. A field no record has ever answered is one this source leaves empty, and a "
    "night that read no record says nothing, so it keeps what the last night found rather than "
    "clearing a finding nobody fixed or raising one nobody saw."
)

#: What a finding does to a question and to the Connectors screen.
A_TOOL_WHOSE_FIELD_IS_GONE_ANSWERS_DEGRADED: Final = (
    "A question that needs a field its source no longer answers is told the source could not be "
    "fully read, rather than that nothing was found, because nothing was found for a reason about "
    "the connector and not about the company's records. The source shows as degraded on the "
    "Connectors screen, naming the fields, so the person who can upgrade it knows what changed."
)

# --------------------------------------------------------------------- the figures

#: How often every connected source's schema is read. Nightly, as the owner asked.
SCHEMA_CHECK_EVERY: Final = timedelta(days=1)

#: What a kept field name looks like: a mapping target, and so this release's own word.
FIELD_NAME: Final = re.compile(r"^[a-z][a-z0-9_]{0,59}$")


class SchemaFindingError(ValueError):
    """A finding was built with something other than field names in it."""


# ------------------------------------------------------------------------ observed
@dataclass(frozen=True)
class Observation:
    """What one call answered: the fields the tool reading it depends on, and which it answered.

    One per call rather than one per kind of record, because a kind of record may be read by two
    calls (a list, and one record by its own call), each with its own mapping, and a call that
    failed says nothing about the fields only it reads.
    """

    depended: frozenset[str]
    answered: frozenset[str]
    #: How many records the call returned. Nought for a call that failed or found none.
    sampled: int

    def __post_init__(self) -> None:
        _names(self.depended)
        _names(self.answered)
        if self.sampled < 0:
            msg = f"a call cannot return {self.sampled} records"
            raise SchemaFindingError(msg)


@dataclass(frozen=True)
class SchemaFinding:
    """What the check concluded about one kind of record of one connection, on one night."""

    entity: str
    checked_at: datetime
    #: Records read across its calls tonight. Nought when no call read one.
    sampled: int
    #: The fields a record answered at the last night that read one.
    answered: tuple[str, ...]
    #: The fields answered on an earlier night that no record answers now.
    missing: tuple[str, ...]

    def __post_init__(self) -> None:
        _names((self.entity,))
        _names(self.answered)
        _names(self.missing)
        if set(self.answered) & set(self.missing):
            msg = "a field cannot be answered and missing on the same night"
            raise SchemaFindingError(msg)


def _names(names: Iterable[str]) -> None:
    for one in names:
        if not FIELD_NAME.fullmatch(one):
            msg = f"{one!r} is not a field name; a finding keeps names and never a value"
            raise SchemaFindingError(msg)


def judged(
    entity: str,
    observed: Sequence[Observation],
    previous: SchemaFinding | None,
    *,
    now: datetime,
) -> SchemaFinding:
    """Tonight's finding for one kind of record, from its calls and the last night's finding.

    See `A_FIELD_IS_GONE_ONLY_WHEN_IT_WAS_ANSWERED_BEFORE`. A call that read no record carries the
    last night's verdict on the fields it depends on; one that read some judges them afresh, and a
    field is missing only when it was known (answered or already missing) and is not answered now.
    A field one call answers is answered, whatever another call said about it.
    """
    known_answered = frozenset(() if previous is None else previous.answered)
    known_missing = frozenset(() if previous is None else previous.missing)
    answered: set[str] = set()
    missing: set[str] = set()
    for one in observed:
        if one.sampled == 0:
            answered |= known_answered & one.depended
            missing |= known_missing & one.depended
            continue
        now_answered = one.answered & one.depended
        answered |= now_answered
        missing |= ((known_answered | known_missing) & one.depended) - now_answered
    return SchemaFinding(
        entity=entity,
        checked_at=now,
        sampled=sum(one.sampled for one in observed),
        answered=tuple(sorted(answered)),
        missing=tuple(sorted(missing - answered)),
    )


def in_words(entity: str, missing: Sequence[str]) -> str:
    """One sentence for the Connectors screen: which fields of which records are no longer read.

    The field names are the mapping's own, with their underscores read as spaces, so the sentence
    names what the source stopped answering in this release's words and never in the vendor's.
    """
    fields = ", ".join(one.replace("_", " ") for one in missing)
    return f"Its {entity.replace('_', ' ')} records no longer answer: {fields}."
