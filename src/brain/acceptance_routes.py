"""`/api/acceptance.json`: what each install acceptance check came to on the commit this serves.

The read half of `brain.ops.acceptance_run`, in the shape `/api/deploy-checks.json` has: public,
read-only, and carrying passed, failed or not run with a reason the check's source wrote, never
anything a check read (`brain.ops.acceptance.A_RESULT_NAMES_NO_DATA`). A task is closed from this
document, so it names the commit it describes, and `?commit=` reads an earlier one's results
rather than letting a newer run stand for a release that was never checked.

**Every check in the suite is listed, whether or not it ran.** A check this build declares with no
recorded result says not run, so a deploy the worker has not reached yet reads as unchecked rather
than as the last commit's pass. The suite is the one `registered` returns in this process, which
is the image the worker runs.

Task ids: M38.5.1
"""

from __future__ import annotations

import re
from typing import Any, Final

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.acceptance import registered, served
from brain.routing_routes import sessions_of
from brain.tables.acceptance import COMMIT_PATTERN, AcceptanceResultRow

router = APIRouter(tags=["docs"])

ACCEPTANCE_PATH: Final = "/api/acceptance.json"

#: A commit as the table holds one. Anything else is answered as the commit this process serves.
_COMMIT: Final = re.compile(COMMIT_PATTERN)


def newest_run_of(commit: str) -> Any:
    """Every row of the newest run recorded for one commit."""
    newest = (
        select(AcceptanceResultRow.run_id)
        .where(AcceptanceResultRow.commit == commit)
        .order_by(AcceptanceResultRow.started_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    return select(
        AcceptanceResultRow.check_name,
        AcceptanceResultRow.leaves,
        AcceptanceResultRow.outcome,
        AcceptanceResultRow.reason,
        AcceptanceResultRow.started_at,
        AcceptanceResultRow.checked_at,
    ).where(AcceptanceResultRow.run_id == newest)


async def newest_rows(
    sessions: async_sessionmaker[AsyncSession] | None, commit: str
) -> list[dict[str, Any]]:
    """The newest run's rows for one commit, instants as text, or none without a database.

    One read for this page and for the Requirement checks screen, which shows each requirement the
    checks proving its leaves, so the two cannot disagree about what a release was seen to do.
    """
    if sessions is None:
        return []
    async with sessions() as session:
        found = (await session.execute(newest_run_of(commit))).mappings().all()
    return [
        {
            **dict(one),
            "started_at": one["started_at"].isoformat(timespec="seconds"),
            "checked_at": one["checked_at"].isoformat(timespec="seconds"),
        }
        for one in found
    ]


@router.get(ACCEPTANCE_PATH, response_class=JSONResponse)
async def acceptance_json(
    request: Request, commit: str = Query(default="", max_length=40)
) -> JSONResponse:
    """The newest recorded run of the acceptance checks for this commit, or for `commit`."""
    from brain.settings import Settings

    asked = commit if commit and _COMMIT.match(commit) else Settings().resolved_commit()
    rows = await newest_rows(sessions_of(request), asked)
    body = served(asked, registered(), rows)
    return JSONResponse(body, headers={"cache-control": "no-store"})
