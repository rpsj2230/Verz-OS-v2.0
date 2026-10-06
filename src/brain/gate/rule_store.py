"""Where the fast lane's rules come from: the rule table, read on every question for the asker.

`brain.gate.fast_lane` argues that a question shape is a row and not a regular expression in
a source file, so the fifth shape is a configuration change rather than a deployment.
`brain.tables.fast_lane` is that row. Nothing joined the two: `rules_from_rows` was called by
no code in `src`, so the table existed, the validator existed, and the lane was always handed
an empty tuple.

**Read on every question, since 2026-10-06, and read once at start before that.** This module
argued for the start-time read: a rule set fetched per request puts a database round trip in
front of the lane whose purpose is to answer without one, and a rule set refreshed on a timer
answers one question two ways inside a minute. M6.5.1 overrules the first half of that. It asks
that a department's administrator add a rule from the console and that the rule answer *from the
next request*, and a rule that waits for a restart is a rule its writer cannot test, cannot
trust, and learns about from the log line this module used to point them at. So the answer route
reads the live rules for the asker on every question, through `rules_for_asker`, which is
`brain.ops.classification_store.classified_lane_of`'s choice about uploaded tables for the same
reason: one small indexed query, paid so that a change reaches the next question rather than the
next restart. The fast lane still makes no model call and reaches no tool; the query is the
gate's, not the lane's, and the lane's own reads stay `brain_fastlane`'s.

**The two-answers objection does not survive the change, and was about a timer.** A timer
changes the rule set at a moment nobody chose, so two people asking at the same minute could be
answered by two rule sets and nothing would say why. Here the rule set changes when an
administrator writes, each question is matched against the rules as they stood when it was
asked, and the request's ledger row names the rule that answered. Two answers either side of a
write are the write, which is what the administrator asked for. See
`A_RULE_ANSWERS_FROM_THE_NEXT_QUESTION`.

**A department's rule is matched only for that department's askers** (`0199`). `rules_for_asker`
reads the rules the whole install asks with and the rules of the asker's own department, which is
`Principal.primary_department`, the department a halt or a budget already judges a person by. A
rule two departments both wrote in the same words is two rules, each matched only for its own
department's askers, so neither department's questions fall through because of the other's. See
`A_DEPARTMENTS_RULE_ANSWERS_ITS_OWN_ASKERS_ALONE`. Rejected: deciding which department rules
apply from the asker's grants, which say what a person may read and not where they sit, so a
finance reader granted one web table would be answered by every web rule. Rejected: putting the
department on `FastPathRule` and filtering in the matcher, which would make the matcher read a
fact about a person, the thing `brain.gate.fast_lane.match_rule` says nothing about the caller
reaches.

**It adds nothing to the rows it reads, and validates every one.** `rules_from_rows` is the
validator and it is the one here: a row that does not satisfy `FastPathRule` is a row that
would match questions nobody wrote a rule for, and the table's own constraints are the second
copy of those checks rather than the first. A rule set that does not validate is answered as no
rules and logged, so the lane abstains rather than the route failing.

**Retired rules are not loaded.** The table has no DELETE and retires with `deleted_at`,
because "which rule answered that question in March" is asked after a wrong answer. A loader
that ignored the column would answer with a rule somebody retired, which is the failure the
column exists to prevent showing up one layer up.

Same split as `brain.knowledge.row_store`: this holds a connection and no policy, and
`brain.gate.fast_lane` holds the policy and no connection. See `brain.ops.limits` for the
argument, which is that a matcher that opened a socket could not be tested at the boundary
where it goes wrong.

Task ids: M6.5.1
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.gate.fast_lane import DECLARED_FIELDS, FastPathRule, rules_from_rows
from brain.ops.classification_store import Writer
from brain.tables.audit import attributed_to
from brain.tables.fast_lane import FastPathRuleRow

log = structlog.get_logger(__name__)

#: Why the rules are read on every question rather than once at start.
A_RULE_ANSWERS_FROM_THE_NEXT_QUESTION: Final = (
    "A rule a department's administrator adds is a rule they test by asking, and a rule set read "
    "once at start answers that test with the old rules until somebody restarts the process. So "
    "the answer route reads the live rules for the asker on every question, one small query, as "
    "it reads the uploaded tables. The rule set changes when somebody writes it, never on a "
    "timer, and the ledger row of each request names the rule that answered it."
)

#: Why a department's rule is matched for its own askers and nobody else's.
A_DEPARTMENTS_RULE_ANSWERS_ITS_OWN_ASKERS_ALONE: Final = (
    "A rule a department writes is that department's configuration, so it is matched only for "
    "askers whose department it is, read off the person and never off their grants. Two "
    "departments writing the same words hold two rules, each answering its own askers, so "
    "neither can make the other's questions fall through. A rule with no department is the "
    "whole install's and is matched for everyone, as every rule was before departments had any."
)


def live_rules(department: str | None) -> Select[tuple[FastPathRuleRow]]:
    """The live rules an asker in `department` is matched against: the install's and their own.

    `None` reads the install's rules alone, which is what an asker with no department, a canary
    and the matrix gate are matched against.
    """
    applies = (
        FastPathRuleRow.department.is_(None)
        if department is None
        else or_(FastPathRuleRow.department.is_(None), FastPathRuleRow.department == department)
    )
    return (
        select(FastPathRuleRow)
        .where(FastPathRuleRow.deleted_at.is_(None), applies)
        .order_by(FastPathRuleRow.rule_id)
    )


async def load_rules(
    sessions: async_sessionmaker[AsyncSession], *, department: str | None = None
) -> tuple[FastPathRule, ...]:
    """Every live rule an asker in `department` is matched against, validated, in a fixed order.

    Ordered by `rule_id` so two processes reading one database hold the same tuple in the same
    order. `match_rule` refuses a question two rules match rather than taking the first, so the
    order does not decide an answer today; it decides which rule a log line names when something
    else goes wrong, and an order that moves between processes makes two identical incidents
    read as two different ones.

    Only `DECLARED_FIELDS` are read, which is `rules_from_rows`' rule rather than one added
    here: a column added to the table, `department` included, is inert to the matcher until
    somebody adds it to that tuple and to `FastPathRule`.
    """
    async with sessions() as session:
        found = (await session.execute(live_rules(department))).scalars().all()
    rows = [{field: getattr(row, field) for field in DECLARED_FIELDS} for row in found]
    return rules_from_rows(rows)


async def rules_for_asker(state: Any, department: str | None) -> tuple[FastPathRule, ...]:
    """The rules this question is matched against, read now. Empty on a process with no store.

    The answer route's one call, beside `classified_lane_of`. A rule table that cannot be read,
    or a rule set that does not validate, is an empty rule set and a log line rather than a
    failed question: the lane abstains for every question, which is the same answer it gives
    when no rule matches, and the log line says which of the two this is.
    """
    sessions = getattr(state, "db_sessions", None)
    if not isinstance(sessions, async_sessionmaker):
        return ()
    try:
        return await load_rules(sessions, department=department)
    except Exception as exc:
        log.warning("fast path rules unavailable", error=type(exc).__name__)
        return ()


def rule_ids(rules: Sequence[FastPathRule]) -> tuple[str, ...]:
    """The ids, for a log line that says which rules a question was matched against.

    Ids and never templates. A template is the question shape somebody wrote, and a log line
    carrying it puts the shape of what this installation can be asked into a stream with
    different permissions from the rule table. The id names the row for anybody entitled to
    open it.
    """
    return tuple(one.rule_id for one in rules)


# ------------------------------------------------------------------ the console's writes
@dataclass(frozen=True)
class KeptRule:
    """One live rule as the console lists it: what it is, whose it is, and who wrote it."""

    rule: FastPathRule
    department: str | None
    created_by: str
    created_at: datetime


class StoredRules:
    """`gate.fast_path_rule` for the console: the live rules, an addition and a retirement.

    Decides nothing about who may do which: `brain.rule_routes` asks the grants. What the table
    decides itself, under `0199`'s insert policy, is that a rule is written in its writer's
    name, so every write here runs `attributed_to` first.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def live(self) -> tuple[KeptRule, ...]:
        """Every live rule, of every department and the install's, ordered by id."""
        statement = (
            select(FastPathRuleRow)
            .where(FastPathRuleRow.deleted_at.is_(None))
            .order_by(FastPathRuleRow.rule_id)
        )
        async with self._sessions() as session:
            found = (await session.execute(statement)).scalars().all()
        rows = [{field: getattr(row, field) for field in DECLARED_FIELDS} for row in found]
        return tuple(
            KeptRule(
                rule=rule,
                department=row.department,
                created_by=row.created_by,
                created_at=row.created_at,
            )
            for rule, row in zip(rules_from_rows(rows), found, strict=True)
        )

    async def add(self, rule: FastPathRule, *, department: str | None, writer: Writer) -> bool:
        """Write one rule; False, writing nothing, when its id or its words are already live."""
        values = {field: getattr(rule, field) for field in DECLARED_FIELDS}
        statement = (
            pg_insert(FastPathRuleRow)
            .values(**values, department=department, created_by=writer.actor_id)
            .on_conflict_do_nothing()
            .returning(FastPathRuleRow.rule_id)
        )
        async with self._sessions() as session, session.begin():
            for setting in _attributed(writer):
                await session.execute(setting)
            written = (await session.execute(statement)).scalar_one_or_none()
        return written is not None

    async def retire(self, rule_id: str, *, writer: Writer) -> bool:
        """Retire one live rule, stamped by its own statement; False when none was live."""
        statement = (
            update(FastPathRuleRow)
            .where(FastPathRuleRow.rule_id == rule_id, FastPathRuleRow.deleted_at.is_(None))
            # `0045`: a retirement is stamped with the statement's own instant, which is what
            # lets the statement read back the row it retired and nothing after it can.
            .values(deleted_at=func.statement_timestamp())
        )
        async with self._sessions() as session, session.begin():
            for setting in _attributed(writer):
                await session.execute(setting)
            done = await session.execute(statement)
        return int(getattr(done, "rowcount", 0) or 0) == 1


def _attributed(writer: Writer) -> tuple[Any, ...]:
    return attributed_to(
        actor_id=writer.actor_id, ent_hash=writer.ent_hash, trace_id=writer.trace_id
    )
