"""The deployment history as the Version and updates screen reads it: newest first, chain checked.

`brain.ops.deployments` holds the chain and `brain.ops.deployment_store` writes it into
`ops.deployment_record`. This is the read, and it holds no connection: `recorded` is a statement
the route executes on the application's session, and `history_from` turns the rows into what the
screen shows. The split is `brain.ops.limits` and `brain.ops.limit_store`'s, and here it is also
what keeps the write out of every module the application's sessions reach, which
`brain.ops.application_privileges` would otherwise report as an INSERT `brain_app` is not granted.

**The whole chain is read and verified on every load, and only the newest few are shown.** A
verification over the rows on the screen alone would pass a history whose older half had been
edited, and the older half is where an edit made to hide something would be. A deploy is a few
rows a day on a busy install, so reading all of them is affordable for a screen opened rarely.
See `A_HISTORY_CHECKED_OVER_WHAT_IS_SHOWN_IS_NOT_CHECKED`.

**A broken chain is shown with the history, never instead of it.** The rows are what somebody
investigating a bad deploy needs, and a screen that hid them because a digest disagreed would
withhold the evidence at the moment it matters. `broken` names the sequence numbers that do not
hold, and the screen says so above the list.

**No count.** The screen shows the newest `SHOWN` deploys and never "12 of 340": nothing about a
deploy is hidden from anybody who may open the screen, and the install screens keep one rule
about counts (`brain.install_routes`).

Task ids: M38.1.3.5
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol

from sqlalchemy import Select, select

from brain.ops.deployments import ChainedDeployment, Deployment, DeploymentChain
from brain.tables.deployment_record import DeploymentRecordRow

#: How many deploys the screen lists, newest first.
SHOWN: Final = 20

#: Why the chain is verified over every row and not over the rows on the screen.
A_HISTORY_CHECKED_OVER_WHAT_IS_SHOWN_IS_NOT_CHECKED: Final = (
    "Each link names the digest of the one before it, so verifying the newest twenty rows alone "
    "passes a history whose older rows were edited, removed or reordered: the twenty agree with "
    "each other whatever came before them. The older rows are where an edit made to hide a bad "
    "release would be, so the whole chain is read and verified and only the newest are drawn."
)

#: What the screen says when the chain holds.
THE_HISTORY_HOLDS: Final = (
    "Every deploy recorded here links to the one before it, so none has been edited, removed or "
    "reordered since it was written."
)

#: What the screen says when it does not.
THE_HISTORY_DOES_NOT_HOLD: Final = (
    "Some deploys recorded here no longer link to the one before them, so the history was changed "
    "after it was written. The rows are shown as they are stored."
)

#: What the screen says when no deploy has been recorded yet.
NOTHING_RECORDED_YET: Final = (
    "No deploy has been recorded on this install yet. The deploy script records one each time it "
    "finishes, whether the new version came up, was held back or was rolled back."
)


class RecordRow(Protocol):
    """The columns a stored deploy is read back from. `DeploymentRecordRow` is one."""

    # Read-only properties, so a mapped column (a descriptor) satisfies the protocol under mypy.
    @property
    def seq(self) -> int: ...
    @property
    def at(self) -> datetime: ...
    @property
    def outcome(self) -> str: ...
    @property
    def commit(self) -> str: ...
    @property
    def image(self) -> str: ...
    @property
    def previous(self) -> str: ...
    @property
    def task_ids(self) -> Sequence[str]: ...
    @property
    def prev_hash(self) -> str: ...
    @property
    def entry_hash(self) -> str: ...


@dataclass(frozen=True)
class History:
    """The newest deploys and whether the chain they belong to holds."""

    shown: tuple[ChainedDeployment, ...]
    broken: tuple[int, ...]

    @property
    def says(self) -> str:
        if not self.shown:
            return NOTHING_RECORDED_YET
        return THE_HISTORY_DOES_NOT_HOLD if self.broken else THE_HISTORY_HOLDS


def recorded() -> Select[Any]:
    """Every stored deploy, oldest first, which is the order the chain is verified in.

    Named columns, read with `.all()`: `.scalars()` on a Core connection yields only `seq`."""
    return select(*DeploymentRecordRow.__table__.columns).order_by(DeploymentRecordRow.seq)


def chain_from_rows(rows: Iterable[RecordRow]) -> DeploymentChain:
    """The stored chain, with the stored digests rather than recomputed ones.

    Recomputing them here would make every row agree with itself, which is the failure
    `brain.ops.deployments.ChainedDeployment` stores the digest to avoid.
    """
    return DeploymentChain(
        entries=[
            ChainedDeployment(
                seq=row.seq,
                deployment=Deployment(
                    at=row.at,
                    outcome=row.outcome,
                    commit=row.commit,
                    image=row.image,
                    previous=row.previous,
                    task_ids=tuple(sorted(row.task_ids)),
                ),
                prev_hash=row.prev_hash,
                entry_hash=row.entry_hash,
            )
            for row in rows
        ]
    )


def history_from(rows: Iterable[RecordRow], *, shown: int = SHOWN) -> History:
    """The newest `shown` deploys, newest first, and the verdict over every row."""
    chain = chain_from_rows(rows)
    newest = tuple(reversed(chain.entries[-shown:])) if shown > 0 else ()
    return History(shown=newest, broken=chain.verify())
