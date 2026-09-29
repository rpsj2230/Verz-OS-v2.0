"""A report an agent produces for a person: the rows and fields its run may read, as an artifact.

`brain.console.agent_output` decided that an artifact is masked while it is built, at the run's
reach, and wrote `producible_fields` to say which fields of one record may go into one;
`brain.ops.artifact_store` keeps what is produced. Nothing produced anything, so the rule had no
file to apply to. This is the first producer, a CSV report over one entity's records, and the only
thing it decides is the shape of the file.

**Every row and every cell is decided at `E_run(caller, agent)`, before a byte is written.** A row
the run's reach does not admit for the entity is left out, and a field `producible_fields` does
not admit on a row is an empty cell on that row, so the file can never hold more than the person
asking could read through this agent. There is no step afterwards that could redact it, which is
`AN_ARTIFACT_IS_A_COPY_WHOSE_PERMISSIONS_STOPPED_TRAVELLING_WITH_IT`, and nothing here computes a
reach: `brain.console.workspace_capabilities.run_reach` does, and `producible_fields` asks
`brain.core.redaction.compute_mask`.

**A column is a field some row admits; a withheld field on another row is an empty cell.** The
same shape as the records screen's lock: the column exists because the reader may see it
somewhere, and nothing says why one cell is empty. A column no row admits is not in the file at
all, so a field the reader may never see is never named.

**The grants the content drew on are written onto the record** (`Artifact.drew_on`): the grant
that admitted the rows, and the grant behind each column that reached the file, as the run's
reach held them. A re-download is checked against them, so the person the report was produced
for is refused it once their reach no longer covers what it holds.

**A cell a spreadsheet would run is written as text.** A value beginning with `=`, `+`, `-` or `@`
is a formula to every spreadsheet that opens a CSV, and a record's field is somebody else's input,
so such a value is prefixed with an apostrophe. See
`A_FIELD_IS_DATA_AND_A_SPREADSHEET_WOULD_RUN_IT`.

**Nothing refuses to be empty quietly.** No admitted row, or no admitted column, is a refusal
rather than a file with a heading and nothing under it: an empty report reads as "there are none",
which is a statement about the company nobody established.

What calls it on an install today: the acceptance check. No agent's run renders a document yet;
a tool that does calls `produce_report` with its run's rows and inherits every rule above.

Task ids: M39.5.1.1, M39.5.1.4
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from brain.agents.model import AgentRecord
from brain.console.agent_output import (
    Artifact,
    ArtifactError,
    ArtifactInput,
    ArtifactKind,
    Provenance,
    producible_fields,
)
from brain.console.workspace_capabilities import run_reach
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import FieldPolicy
from brain.ops.artifact_store import Produced, StoredArtifacts

# ------------------------------------------------------------------ written-down reasons
#: Why a cell a spreadsheet would read as a formula is written as text.
A_FIELD_IS_DATA_AND_A_SPREADSHEET_WOULD_RUN_IT: Final = (
    "A CSV cell beginning with =, +, - or @ is a formula to every spreadsheet that opens it, and "
    "a record's field was typed by somebody else. So such a cell is written with an apostrophe "
    "in front, which a spreadsheet shows as the text it was."
)

#: What producing a report nothing admits is refused with.
NOTHING_THIS_RUN_MAY_READ_IS_A_REPORT: Final = (
    "No row or no field of these records is one this run may read, so there is no report to "
    "produce: an empty file would read as a report that found nothing."
)

# ------------------------------------------------------------------------ the figures
#: The media type a report is kept under.
REPORT_CONTENT_TYPE: Final = "text/csv"

#: The characters a spreadsheet reads a cell as a formula by.
FORMULA_LEADS: Final = ("=", "+", "-", "@")


@dataclass(frozen=True)
class Records:
    """The records a run read for a report: one entity, its policy, and what reading it needed.

    `read_as` is the capability the rows were read under, the row-level grant for the entity, and
    `source` is where they came from, for the provenance panel.
    """

    entity: str
    rows: tuple[Mapping[str, Any], ...]
    policy: FieldPolicy
    read_as: Capability
    source: str


@dataclass(frozen=True)
class Rendered:
    """A report's bytes and the grants they drew on."""

    body: bytes
    columns: tuple[str, ...]
    drew_on: tuple[Grant, ...]


def cell(value: Any) -> str:
    """One value as a cell: text as itself, a formula lead made text, nothing as nothing."""
    if value is None:
        return ""
    if isinstance(value, str):
        return f"'{value}" if value.startswith(FORMULA_LEADS) else value
    return str(value)


def rendered(
    records: Records, *, caller: EntitlementSet, agent: AgentRecord, now: datetime
) -> Rendered:
    """The report at `E_run(caller, agent)`, and the grants it drew on. See the module."""
    reach = run_reach(caller, agent)
    admitting = reach.scope_for(records.read_as, now)
    if admitting is None:
        raise ArtifactError(NOTHING_THIS_RUN_MAY_READ_IS_A_REPORT)
    rows = [dict(row) for row in records.rows if admitting.matches(dict(row))]
    allowed = [
        producible_fields(
            records.entity,
            tuple(row),
            caller=caller,
            agent=agent,
            policy=records.policy,
            row=row,
            now=now,
        )
        for row in rows
    ]
    columns: list[str] = []
    for fields in allowed:
        columns.extend(name for name in fields if name not in columns)
    if not rows or not columns:
        raise ArtifactError(NOTHING_THIS_RUN_MAY_READ_IS_A_REPORT)

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for row, fields in zip(rows, allowed, strict=True):
        writer.writerow([cell(row.get(name)) if name in fields else "" for name in columns])

    drew_on = [Grant(capability=records.read_as, scope=admitting)]
    for name in columns:
        rule = records.policy.rule_for(records.entity, name)
        if rule is None:
            continue
        held = reach.scope_for(rule.required_capability, now)
        if held is not None and all(one.capability != rule.required_capability for one in drew_on):
            drew_on.append(Grant(capability=rule.required_capability, scope=held))
    return Rendered(
        body=out.getvalue().encode("utf-8"), columns=tuple(columns), drew_on=tuple(drew_on)
    )


async def produce_report(
    store: StoredArtifacts,
    records: Records,
    *,
    caller: EntitlementSet,
    agent: AgentRecord,
    agent_version: str,
    run_id: str,
    inputs: Sequence[ArtifactInput],
    at: datetime,
    client_id: str = "",
    supersedes: str = "",
) -> Artifact:
    """Render a report at the run's reach and keep it for the person who asked."""
    made = rendered(records, caller=caller, agent=agent, now=at)
    return await store.keep(
        Produced(
            agent_id=agent.agent_id,
            kind=ArtifactKind.REPORT,
            run_id=run_id,
            agent_version=agent_version,
            caller_id=caller.principal_id,
            reach=run_reach(caller, agent),
            inputs=tuple(inputs),
            body=made.body,
            content_type=REPORT_CONTENT_TYPE,
            provenance=Provenance(sources=(records.source,)),
            client_id=client_id,
            drew_on=made.drew_on,
            supersedes=supersedes,
        ),
        at=at,
    )
