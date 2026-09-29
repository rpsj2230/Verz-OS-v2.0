"""The seam where the answer lane asks for a record to be read live, owned by the gate.

The gate decides what a caller may see and never fetches, which is why it imports no connector
(`tests/unit/test_repo_shape.py::test_the_gate_does_not_import_a_connector`). Reading a connected
source's record while somebody waits (M11.9.2) is fetching, so it happens outside the gate, in
`brain.ops.live_records`, and the gate knows it only through the two protocols here. What crosses
the seam back is the live record, typed as the row plane's, and what could not be read, as something
the lane can only ask two questions of: whether anything was left out, and what this asker may be
told about it.

**The notice is asked with the asker's reach and nothing else (M11.5.5).** `PartialRead.notice`
takes the sources the asker's own reach already discloses, which the lane has as its scope
statement, so an implementation cannot be handed a way to name a source to somebody who could not
see it.

Rejected: importing `brain.connectors.federation.PartialAnswer` and `brain.connectors.live_read`
here, which is how this module was first written. It worked, and it put a fetching path inside the
seam every permission decision passes through; a protocol keeps the direction of the dependency the
architecture's.

**A field its source no longer answers is a partial read too (M11.8.7).** The nightly schema
check (`brain.ops.schema_drift`) finds a mapped field no record answers any more, and a question
whose rule needs it is told so through the same seam, as `FieldsGone`: nothing was found for a
reason about the connector, so the asker is told the source could not be fully read rather than
that nothing exists, and the request is recorded as degraded. It names the source on the same
condition a failed read does. See `A_FIELD_ITS_SOURCE_NO_LONGER_ANSWERS_IS_NOT_AN_ABSENCE`.

Task ids: M11.9.2, M11.5.5, M11.8.7
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from brain.core.envelope import TypedResult
from brain.core.errors import Degraded
from brain.knowledge.rows import RowRecord

#: Why a question needing a field its source dropped is told the source was not fully read.
A_FIELD_ITS_SOURCE_NO_LONGER_ANSWERS_IS_NOT_AN_ABSENCE: Final = (
    "When the nightly schema check has found that a source no longer answers a field a question "
    "needs, reading it would find nothing, and nothing found reads as a fact about the company's "
    "records. So the asker is told the source could not be fully read, naming it only where "
    "their own reach already discloses it, and the request is recorded as degraded."
)


class PartialRead(Protocol):
    """What a live read left out, as the answer lane may use it.

    `brain.connectors.federation.PartialAnswer` is the implementation: `notice` names a failed
    source only when it is in `disclosable`, and `trace_lines` are for the operator's log.
    """

    @property
    def is_complete(self) -> bool: ...

    def notice(self, *, disclosable: frozenset[str]) -> str:
        """The sentence this asker is told, naming only sources their reach discloses."""
        ...

    def trace_lines(self) -> tuple[str, ...]:
        """Every source that failed and why, for the operator's log and never for the asker."""
        ...


@dataclass(frozen=True)
class Refreshed:
    """What reading an index hit live came to.

    `result` is the live records, laid over their index rows, or None when any of them could not
    be read, in which case `partial` says which source and why. `calls` is how many source calls
    were planned, for the request's tool count.
    """

    result: TypedResult[RowRecord] | None
    partial: PartialRead
    calls: int


@runtime_checkable
class LiveRecords(Protocol):
    """Reads the records an index hit found from their source, or says the pair is not read live."""

    async def refresh(
        self,
        result: TypedResult[RowRecord],
        *,
        source: str,
        entity: str,
        asker: str,
        trace_id: str = "",
    ) -> Refreshed | None:
        """The live records in place of `result`, or None to answer from `result` as it is."""
        ...


@dataclass(frozen=True)
class FieldsGone:
    """`PartialRead` for a question needing a field its source no longer answers (M11.8.7).

    See `A_FIELD_ITS_SOURCE_NO_LONGER_ANSWERS_IS_NOT_AN_ABSENCE`. The fields are for the trace;
    the asker is told the source's name only when `disclosable` holds it, and otherwise exactly
    the sentence every unreachable source produces, so the two cannot be told apart.
    """

    source: str
    entity: str
    fields: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return False

    def notice(self, *, disclosable: frozenset[str]) -> str:
        if self.source not in disclosable:
            return Degraded.public_message
        return (
            f"{self.source} no longer answers something this question needs, so it could not be "
            "answered from there. An administrator can see which on the Connectors screen."
        )

    def trace_lines(self) -> tuple[str, ...]:
        return (f"{self.source}: {self.entity} no longer answers {', '.join(self.fields)}",)
