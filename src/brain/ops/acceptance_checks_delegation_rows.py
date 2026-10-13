"""Install checks for the delegation table: the database computes a child's reach as the rule does,
refuses a row that widens one, and the orchestrator holds no verb that could grant.

`gate.delegation` is the table a delegated run's reach is recorded in (migrations 0028, 0029 and
0033). Its trigger computes `parent intersect agent intersect subtask` in SQL and refuses any row
whose claimed reach is not a subset of it. The unit tests build their own scratch database to show
that. What they cannot show is that the **install's** database, as the migrations left it, holds the
table, the functions and the trigger, and answers the way the Python rule does. Nothing in the
application writes a delegation row yet, so these checks write the rows themselves, as the
application role, and the transaction they sit in is always rolled back.

**The table is insert-only to the application role, so a row is read back as the login.** The
migration grants `INSERT` and nothing else, so the stored child reach is read in a savepoint as the
role the run connected as, in the way `acceptance_operations_console_2.as_login` writes the
scheduler's rows, and the application role is set again afterwards. A login that may not read the
table says so by not running the check.

**The Python side is the one implementation.** The expected reach is `delegation.chain_reach`,
which folds `brain.ops.automation.flow_reach` over the hops; this module never calls `intersect`,
and `tests/invariants/test_single_implementation.py` would refuse it if it did.

**What is not claimed.** That an orchestrator runtime writes these rows when it delegates: it does
not exist (M18.5). These checks prove the database's half of the rule on an install.

Task ids: M18.3.1, M18.3.2, M18.3.3
"""

from __future__ import annotations

import inspect
import json
import pkgutil
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from sqlalchemy.sql import Executable

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2200

A, _B = RESERVED_DEPARTMENTS

#: SQLSTATE the delegation trigger refuses with, restated so a change in the migration fails here.
THE_TRIGGER_REFUSES_WITH: Final = "23514"

#: Said when the run's login may not read the delegation table.
THE_TABLE_IS_NOT_READABLE_HERE: Final = (
    "the login this check runs as may not read the delegation table, so a stored row cannot be "
    "compared with the rule"
)
#: Said when the install's database holds no delegation table.
NO_DELEGATION_TABLE_HERE: Final = (
    "this install's database holds no delegation table or no function that computes a child's "
    "reach, so the migrations that make them have not run"
)

THE_DATABASE_REACH_DIFFERED: Final = (
    "the child reach the database computed was not the reach the rule computes in Python"
)
A_NARROWING_ROW_WAS_REFUSED: Final = "a delegation row that narrows its parent was refused"
A_STORED_REACH_DIFFERED: Final = "a stored child reach was not the reach the rule computes"
A_WIDENING_ROW_WAS_STORED: Final = "a delegation row that widens its parent's reach was stored"
A_WIDENING_ROW_WAS_REFUSED_FOR_ANOTHER_REASON: Final = (
    "a widening delegation row was refused, but not by the narrowing trigger"
)
A_GRANT_VERB_WAS_FOUND: Final = "the orchestration package holds a verb that could grant reach"
THE_SCAN_FOUND_NOTHING_IN_A_GRANTING_SOURCE: Final = (
    "the scan for grant verbs found nothing in a source that constructs one"
)
NO_SOURCE_TO_SCAN: Final = "the orchestration package's source is not on this install"

#: A source that confers rather than narrows, so the scan is shown able to find one.
A_SOURCE_THAT_CONFERS: Final = (
    "def hand_out() -> int:\n    return Grant(capability='x', scope=None)\n"
)


# ------------------------------------------------------------------------ the helpers
def _where(**fields: str) -> Scope:
    return Scope(clauses=tuple(Clause(field=k, op=Op.EQ, value=v) for k, v in fields.items()))


def _reach(principal: str, *grants: tuple[str, Scope]) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(Grant(capability=Capability(value=v), scope=s) for v, s in grants),
    )


def _document(one: EntitlementSet) -> str:
    return json.dumps(one.model_dump(mode="json"))


def _shape(document: Any) -> tuple[Any, ...]:
    """A reach reduced to what it means, so SQL's rendering and Python's can be compared."""
    if isinstance(document, str):
        document = json.loads(document)
    return (
        document["principal_id"],
        tuple(
            sorted(
                (
                    one["capability"]["value"],
                    tuple(sorted(json.dumps(c, sort_keys=True) for c in one["scope"]["clauses"])),
                )
                for one in document["grants"]
            )
        ),
        document.get("not_after"),
    )


class _Chain:
    """The three reaches a delegation is made of, and what the Python rule says the child is."""

    def __init__(self, h: Harness, tag: str) -> None:
        from brain.agents.model import CEILING_PRINCIPAL_PREFIX
        from brain.orchestration.contract import SUBTASK_CEILING_PREFIX
        from brain.orchestration.delegation import Hop, LensKind, chain_reach, child_hops

        who = h.principal(A, "delegator")
        scope = _where(department=A)
        self.parent = _reach(
            who,
            ("read:client.*", scope),
            ("read:invoice.total", scope),
            ("read:project.name", scope),
        )
        self.agent = _reach(
            f"{CEILING_PRINCIPAL_PREFIX}acceptance_{h.run}_{tag}",
            ("read:client.name", Scope()),
            ("read:invoice.*", Scope()),
        )
        self.subtask = _reach(
            f"{SUBTASK_CEILING_PREFIX}acceptance_{h.run}_{tag}",
            ("read:client.*", Scope()),
            ("read:invoice.total", _where(tier="gold")),
        )
        hops = child_hops(
            (),
            agent=Hop(lens_id=f"agent_{tag}", kind=LensKind.AGENT, ceiling=self.agent),
            subtask=Hop(lens_id=f"subtask_{tag}", kind=LensKind.SUBTASK, ceiling=self.subtask),
        )
        self.child = chain_reach(self.parent, hops)


def _insert(
    row_id: str,
    parent_id: str | None,
    run: str,
    child: str,
    parent_grants: EntitlementSet | None,
    chain: _Chain,
    claimed: EntitlementSet,
    at: Any,
) -> Executable:
    return text(
        "INSERT INTO gate.delegation (id, parent_id, run_id, child_id, parent_grants, "
        "agent_ceiling, subtask_ceiling, child_grants, decided_at) VALUES "
        "(CAST(:id AS uuid), CAST(:parent_id AS uuid), :run, :child, "
        "CAST(:parent_grants AS jsonb), CAST(:agent AS jsonb), CAST(:subtask AS jsonb), "
        "CAST(:claimed AS jsonb), :at)"
    ).bindparams(
        id=row_id,
        parent_id=parent_id,
        run=run,
        child=child,
        parent_grants=None if parent_grants is None else _document(parent_grants),
        agent=_document(chain.agent),
        subtask=_document(chain.subtask),
        claimed=_document(claimed),
        at=at,
    )


async def _as_login_rows(h: Harness, statement: Executable) -> list[Any]:
    """Rows read as the login the run connected as, in a savepoint, then the role set again."""
    from brain.session import SET_APPLICATION_ROLE

    try:
        async with h.connection.begin_nested():
            await h.connection.execute(text("RESET ROLE"))
            rows = list((await h.connection.execute(statement)).all())
            await h.connection.exec_driver_sql(SET_APPLICATION_ROLE)
    except DBAPIError as exc:
        raise CheckNotRunError(THE_TABLE_IS_NOT_READABLE_HERE) from exc
    return rows


async def _sql_child(h: Harness, chain: _Chain) -> Any:
    """What `gate.delegated_reach` computes for the chain, read as the login."""
    statement = text(
        "SELECT gate.delegated_reach(CAST(:p AS jsonb), CAST(:a AS jsonb), CAST(:s AS jsonb), :at)"
    ).bindparams(
        p=_document(chain.parent), a=_document(chain.agent), s=_document(chain.subtask), at=h.now
    )
    try:
        rows = await _as_login_rows(h, statement)
    except CheckNotRunError:
        raise
    except DBAPIError as exc:  # pragma: no cover - _as_login_rows converts it
        raise CheckNotRunError(NO_DELEGATION_TABLE_HERE) from exc
    return rows[0][0]


async def _refusal(h: Harness, statement: Executable) -> str | None:
    """The SQLSTATE the database refuses a statement with, as the application role, or None.

    In a session of its own whose work is rolled back either way, so the check's transaction
    carries on, as `brain.ops.acceptance_checks_skill_packages._statement_refusal` does.
    """
    async with h.sessions() as session:
        try:
            await session.execute(statement)
        except DBAPIError as refused:
            await session.rollback()
            return str(getattr(refused.orig, "sqlstate", "") or "")
        await session.commit()
    return None


async def _table_exists(h: Harness) -> bool:
    rows = await _as_login_rows(h, text("SELECT to_regclass('gate.delegation') IS NOT NULL"))
    return bool(rows and rows[0][0])


# ------------------------------------------------- 1. the child reach in SQL (M18.3.1)
@check(
    leaves=("M18.3.1",),
    sentence=(
        "A delegation chain of a person, an agent ceiling and a subtask ceiling is folded by the "
        "database's own function to the reach the Python rule gives, a root row and a row "
        "beneath it carrying that reach are stored, and the stored child reach read back is the "
        "reach the rule computes."
    ),
)
async def the_database_computes_a_childs_reach_as_the_rule_does(h: Harness) -> None:
    if not await _table_exists(h):
        raise CheckNotRunError(NO_DELEGATION_TABLE_HERE)
    chain = _Chain(h, "reach")
    if _shape(await _sql_child(h, chain)) != _shape(chain.child.model_dump(mode="json")):
        raise CheckFailedError(THE_DATABASE_REACH_DIFFERED)

    from brain.orchestration.delegation import Hop, LensKind, chain_reach

    root_id, below_id = str(uuid.uuid4()), str(uuid.uuid4())
    run = f"acceptance_{h.run}_reach"
    if (
        await _refusal(
            h, _insert(root_id, None, run, "root", chain.parent, chain, chain.child, h.now)
        )
        is not None
    ):
        raise CheckFailedError(A_NARROWING_ROW_WAS_REFUSED)
    # A second hop beneath the root: the agent ceiling alone narrows the child again.
    narrower = _reach(chain.agent.principal_id, ("read:client.name", Scope()))
    second = chain_reach(chain.child, (Hop(f"agent_{run}", LensKind.AGENT, narrower),))
    below = _Chain(h, "reach")
    below.parent, below.agent, below.subtask = chain.child, narrower, chain.subtask
    if (
        await _refusal(
            h,
            _insert(
                below_id,
                root_id,
                run,
                "below",
                None,
                below,
                second,
                h.now + timedelta(seconds=1),
            ),
        )
        is not None
    ):
        raise CheckFailedError(A_NARROWING_ROW_WAS_REFUSED)
    stored = await _as_login_rows(
        h,
        text(
            "SELECT child_id, child_grants FROM gate.delegation WHERE run_id = :run "
            "ORDER BY decided_at"
        ).bindparams(run=run),
    )
    expected = {"root": chain.child, "below": second}
    if {name: _shape(doc) for name, doc in stored} != {
        name: _shape(one.model_dump(mode="json")) for name, one in expected.items()
    }:
        raise CheckFailedError(A_STORED_REACH_DIFFERED)


# ------------------------------------------------- 2. the trigger (M18.3.2)
@check(
    leaves=("M18.3.2",),
    sentence=(
        "A delegation row whose claimed reach holds a capability its parent does not is refused "
        "by the database with the narrowing trigger's own code, a row claiming a wider scope "
        "than its parent is refused, and the same chain claiming exactly the reach the rule "
        "computes is stored."
    ),
)
async def the_database_refuses_a_delegation_row_that_widens_its_parent(h: Harness) -> None:
    if not await _table_exists(h):
        raise CheckNotRunError(NO_DELEGATION_TABLE_HERE)
    chain = _Chain(h, "refusal")
    run = f"acceptance_{h.run}_refusal"
    extra_capability = _reach(
        chain.child.principal_id,
        *((g.capability.value, g.scope) for g in chain.child.grants),
        ("read:payroll.total", Scope()),
    )
    wider_scope = _reach(
        chain.child.principal_id,
        *((g.capability.value, Scope()) for g in chain.child.grants),
    )
    for label, claimed in (("capability", extra_capability), ("scope", wider_scope)):
        refused = await _refusal(
            h,
            _insert(str(uuid.uuid4()), None, run, label, chain.parent, chain, claimed, h.now),
        )
        if refused is None:
            raise CheckFailedError(A_WIDENING_ROW_WAS_STORED)
        if refused != THE_TRIGGER_REFUSES_WITH:
            raise CheckFailedError(A_WIDENING_ROW_WAS_REFUSED_FOR_ANOTHER_REASON)
    accepted = await _refusal(
        h,
        _insert(str(uuid.uuid4()), None, run, "exact", chain.parent, chain, chain.child, h.now),
    )
    if accepted is not None:
        raise CheckFailedError(A_NARROWING_ROW_WAS_REFUSED)


# ------------------------------------------------- 3. no grant verb (M18.3.3)
@check(
    leaves=("M18.3.3",),
    sentence=(
        "Every module of the orchestration package, as shipped on this install, is scanned for "
        "a function that returns a reach out of something other than a reach and for a grant "
        "built outside a ceiling producer, and none is found; the same scan finds one in a "
        "source that confers."
    ),
)
async def the_orchestrator_holds_no_verb_that_grants_reach(h: Harness) -> None:
    import brain.orchestration as package
    from brain.orchestration.delegation import grant_verbs_in

    del h
    scanned = 0
    for info in pkgutil.iter_modules(package.__path__, prefix="brain.orchestration."):
        module = __import__(info.name, fromlist=["_"])
        try:
            source = inspect.getsource(module)
        except OSError as exc:
            raise CheckNotRunError(NO_SOURCE_TO_SCAN) from exc
        scanned += 1
        if grant_verbs_in(source):
            raise CheckFailedError(A_GRANT_VERB_WAS_FOUND)
    if not scanned:
        raise CheckNotRunError(NO_SOURCE_TO_SCAN)
    if not grant_verbs_in(A_SOURCE_THAT_CONFERS):
        raise CheckFailedError(THE_SCAN_FOUND_NOTHING_IN_A_GRANTING_SOURCE)
