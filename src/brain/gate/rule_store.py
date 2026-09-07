"""Where the fast lane's rules come from, and why they are read once rather than per request.

`brain.gate.fast_lane` argues that a question shape is a row and not a regular expression in
a source file, so the fifth shape is a configuration change rather than a deployment.
`brain.tables.fast_lane` is that row. Nothing joined the two: `rules_from_rows` was called by
no code in `src`, so the table existed, the validator existed, and the lane was always handed
an empty tuple.

**Read once, at startup, and the staleness is stated rather than hidden.** A rule set fetched
per request would put a database round trip in front of the lane whose entire purpose is to
answer without one, which is the change that makes the fast lane slower than the slow one. So
the rules are loaded when the application starts, and a rule added or retired afterwards does
not take effect until the process restarts. That is a real limitation and the honest place to
say so is here and in the log line that records how many were loaded, rather than in a runbook
somebody reads after wondering why their new rule does nothing.

The rejected alternative was a time-based refresh, which trades one surprise for a worse one:
a rule set that changes underneath a running process means two answers to one question inside
one minute, with nothing in either answer saying which rule set produced it. A restart is
visible, ordered, and already how every other piece of this application's configuration
arrives.

**It adds nothing to the rows it reads, and validates every one.** `rules_from_rows` is the
validator and it is the one here: a row that does not satisfy `FastPathRule` is a row that
would match questions nobody wrote a rule for, and the table's own constraints are the second
copy of those checks rather than the first. A source that skipped validation to be permissive
about a malformed row would be admitting exactly the row that got there some other way, which
is what `brain.tables.fast_lane` says the table's constraints exist for.

**Retired rules are not loaded.** The table has no DELETE and retires with `deleted_at`,
because "which rule answered that question in March" is asked after a wrong answer. A loader
that ignored the column would answer with a rule somebody retired, which is the failure the
column exists to prevent showing up one layer up.

Same split as `brain.knowledge.row_store`: this holds a connection and no policy, and
`brain.gate.fast_lane` holds the policy and no connection. See `brain.ops.limits` for the
argument, which is that a matcher that opened a socket could not be tested at the boundary
where it goes wrong.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.gate.fast_lane import DECLARED_FIELDS, FastPathRule, rules_from_rows
from brain.tables.fast_lane import FastPathRuleRow

log = structlog.get_logger(__name__)

#: Why the rule set is frozen for the life of the process.
A_RULE_SET_THAT_CHANGES_MID_FLIGHT_GIVES_TWO_ANSWERS_TO_ONE_QUESTION: Final = (
    "The fast lane exists to answer without a database round trip, so fetching the rules per "
    "request would put back exactly the cost it was built to remove. Refreshing on a timer "
    "trades that for something worse: the same question answered two ways inside a minute, "
    "with nothing in either answer saying which rule set produced it. A restart is visible "
    "and ordered, and it is how every other piece of this application's configuration "
    "arrives. The cost is that a new rule does nothing until the process restarts, which is "
    "said here, in the startup log line, and nowhere else it could be missed."
)


async def load_rules(sessions: async_sessionmaker[AsyncSession]) -> tuple[FastPathRule, ...]:
    """Every live rule, validated, in a fixed order.

    Ordered by `rule_id` so two processes started from one database hold the same tuple in
    the same order. `match_rule` refuses a question two rules match rather than taking the
    first, so the order does not decide an answer today; it decides which rule a log line
    names when something else goes wrong, and an order that moves between processes makes two
    identical incidents read as two different ones.

    Only `DECLARED_FIELDS` are read, which is `rules_from_rows`' rule rather than one added
    here: a column added to the table is inert until somebody adds it to that tuple and to
    `FastPathRule`.
    """
    statement = (
        select(FastPathRuleRow)
        .where(FastPathRuleRow.deleted_at.is_(None))
        .order_by(FastPathRuleRow.rule_id)
    )
    async with sessions() as session:
        found = (await session.execute(statement)).scalars().all()

    rows = [{field: getattr(row, field) for field in DECLARED_FIELDS} for row in found]
    return rules_from_rows(rows)


def rule_ids(rules: Sequence[FastPathRule]) -> tuple[str, ...]:
    """The ids, for a log line that says which rules a process is holding.

    Ids and never templates. A template is the question shape somebody wrote, and a log line
    carrying it puts the shape of what this installation can be asked into a stream with
    different permissions from the rule table. The id names the row for anybody entitled to
    open it.
    """
    return tuple(one.rule_id for one in rules)
