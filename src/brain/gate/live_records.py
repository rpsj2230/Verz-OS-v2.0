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

Task ids: M11.9.2, M11.5.5
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from brain.core.envelope import TypedResult
from brain.knowledge.rows import RowRecord


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
