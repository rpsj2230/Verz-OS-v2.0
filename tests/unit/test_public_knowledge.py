"""Knowledge marked public: who may mark it, what a stranger's statement asks, what `0171` holds.

Three things, each without a database. The rule in `brain.knowledge.public`, over stored items and
grants built here. The public reach in `brain.knowledge.search`, compiled to SQL and read as
structure. And `0171`, held to the model it copies and to `0120`'s audit function it replaces.
`tests/unit/test_public_knowledge_db.py` runs all three against PostgreSQL.

Task ids: M10.7.2
"""

from __future__ import annotations

import importlib.util
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import CheckConstraint, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import ClauseElement

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.identity.first_administrator import GOVERNANCE
from brain.knowledge.item import KnowledgeState
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.lifecycle import StoredItem
from brain.knowledge.public import (
    COMPANY_NEEDS_EVERY_DEPARTMENT,
    NEVER_PERSONAL,
    NOT_A_DEPARTMENT_GRANT,
    NOT_GRANTED,
    NOT_PUBLISHED,
    OUTSIDE_YOUR_DEPARTMENT,
    PUBLIC_MARKING,
    PublicMarking,
    marking_refusal,
)
from brain.knowledge.search import (
    EMBEDDING_DIMENSIONS,
    PUBLIC,
    PUBLIC_ROLE,
    SET_PUBLIC_ROLE,
    Reach,
    cjk_lexical_query,
    lexical_query,
    public_predicate,
    reach_predicate,
    session_settings,
    vector_query,
)
from brain.knowledge.visibility import PROMOTION_CAPABILITY, KnowledgeVisibility, Visibility
from brain.tables.knowledge import KnowledgeItemRow

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "migrations" / "versions"

#: Far from any clock, so no grant here lapses on a schedule nobody chose.
NOW = datetime(2999, 3, 1, 9, 0, tzinfo=UTC)


def migration(name: str) -> types.ModuleType:
    path = next(VERSIONS.glob(f"{name}_*.py"))
    spec = importlib.util.spec_from_file_location(f"m{name}_public", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def item(
    *,
    visibility: KnowledgeVisibility | None = None,
    state: KnowledgeState = KnowledgeState.PUBLISHED,
) -> StoredItem:
    return StoredItem(
        item_id="upload.hours",
        title="Opening hours",
        owner_id="u_steward",
        visibility=visibility or KnowledgeVisibility.of_department("web", owner_id="u_steward"),
        state=state,
        kind=KnowledgeKind.SOP,
    )


def holding(*scopes: Scope, capability: Capability = PUBLIC_MARKING) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_marker",
        grants=tuple(Grant(capability=capability, scope=scope) for scope in scopes),
    )


COMPANY = KnowledgeVisibility(level=Visibility.COMPANY)
PERSONAL = KnowledgeVisibility.personal("u_steward")
EVERYTHING = Scope.unrestricted()
WEB = Scope.department("web")
FINANCE = Scope.department("finance")


def refused(stored: StoredItem, marker: EntitlementSet, *, public: bool = True) -> str | None:
    return marking_refusal(stored, marker=marker, now=NOW, public=public)


# ------------------------------------------------------------------ who may mark (the rule)
def test_a_department_admin_marks_and_unmarks_their_own_departments_document() -> None:
    """**The positive half of the leaf's last clause.** Delete this and a rule refusing everybody
    would satisfy every refusal below, and nobody could ever put anything in front of the widget."""
    assert refused(item(), holding(WEB)) is None
    assert refused(item(), holding(WEB), public=False) is None
    assert (
        refused(
            item(),
            holding(Scope(clauses=(Clause(field="department", op=Op.IN, value=("web", "hr")),))),
        )
        is None
    )


def test_a_department_admin_is_refused_another_departments_document() -> None:
    """**The leaf's last clause.** Delete this and a Department Admin marks every department's
    knowledge public, which is the Super Admin's decision."""
    assert refused(item(), holding(FINANCE)) == OUTSIDE_YOUR_DEPARTMENT
    assert refused(item(), holding(FINANCE), public=False) == OUTSIDE_YOUR_DEPARTMENT


def test_a_company_wide_document_needs_a_grant_no_department_narrows() -> None:
    """A company-wide document is every department's, so one department's grant does not decide
    it and an unrestricted one does. Delete this and either a Department Admin decides for the
    whole company or a Super Admin cannot decide at all."""
    assert refused(item(visibility=COMPANY), holding(WEB)) == COMPANY_NEEDS_EVERY_DEPARTMENT
    assert refused(item(visibility=COMPANY), holding(EVERYTHING)) is None
    assert refused(item(), holding(EVERYTHING)) is None


def test_a_personal_document_is_never_marked_even_by_somebody_who_decides_everything() -> None:
    """Delete this and a note its author shared with nobody reaches the internet on a press."""
    assert refused(item(visibility=PERSONAL), holding(EVERYTHING)) == NEVER_PERSONAL
    assert refused(item(visibility=PERSONAL), holding(EVERYTHING), public=False) == NEVER_PERSONAL


def test_only_a_published_document_is_marked_and_any_is_unmarked() -> None:
    """Delete this and a draft marked public reaches the widget the moment its author publishes
    it, with nobody deciding then; the unmark half is here so withdrawing is never refused by a
    state."""
    for state in (KnowledgeState.DRAFT, KnowledgeState.SUPERSEDED, KnowledgeState.ARCHIVED):
        assert refused(item(state=state), holding(WEB)) == NOT_PUBLISHED
        assert refused(item(state=state), holding(WEB), public=False) is None


def test_nobody_without_the_grant_decides_and_the_promotion_approval_is_not_it() -> None:
    """Delete this and approving a promotion, or a lapsed grant, becomes the decision over what
    the internet reads."""
    assert refused(item(), EntitlementSet(principal_id="u_marker", grants=())) == NOT_GRANTED
    assert refused(item(), holding(EVERYTHING, capability=PROMOTION_CAPABILITY)) == NOT_GRANTED
    lapsed = holding(EVERYTHING).model_copy(update={"not_after": NOW - timedelta(seconds=1)})
    assert refused(item(), lapsed) == NOT_GRANTED


def test_a_grant_scoped_by_anything_but_a_department_decides_nothing() -> None:
    """An owner's scope is satisfiable against every department, so a reduction that asked only
    that would read it as everything. Delete this and a grant nobody meant as a Super Admin's
    marks every document. A clause that tests nothing is still everything."""
    owner = Scope(clauses=(Clause(field="owner_id", op=Op.EQ, value="u_marker"),))
    anything = Scope(clauses=(Clause(field="department", op=Op.ANY),))
    assert refused(item(), holding(owner)) == NOT_A_DEPARTMENT_GRANT
    assert refused(item(visibility=COMPANY), holding(anything)) is None


def test_a_marking_is_a_person_and_a_time_both_or_neither() -> None:
    """`0171`'s check, in Python. Delete this and a marking naming nobody can be built."""
    assert not PublicMarking().is_public
    assert PublicMarking(marked_by="u_marker", marked_at=NOW).is_public
    with pytest.raises(ValueError, match="both or neither"):
        PublicMarking(marked_by="u_marker")
    with pytest.raises(ValueError, match="both or neither"):
        PublicMarking(marked_at=NOW)


def test_the_first_administrator_is_granted_the_public_decision() -> None:
    """Delete this and nobody on a fresh install holds the decision, and nobody can grant it,
    because a grant is bounded by what its writer holds."""
    assert PUBLIC_MARKING.value in GOVERNANCE
    assert PUBLIC_MARKING.value != PROMOTION_CAPABILITY.value


# ------------------------------------------------------------------ what a stranger's read asks
def sql(statement: ClauseElement) -> str:
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    compiled = statement.compile(dialect=dialect, compile_kwargs={"literal_binds": True})
    return " ".join(str(compiled).split())


def test_the_public_reach_is_its_own_predicate_and_shares_no_branch_with_a_persons() -> None:
    """Every conjunct of the public predicate, and nothing a person's reach carries. Delete this and
    the public reach could fall through to a person's predicate, whose company branch admits every
    company-wide document to anybody."""
    predicate = sql(reach_predicate(PUBLIC))
    assert predicate == sql(public_predicate())
    for conjunct in (
        "know.chunk.deleted_at IS NULL",
        "know.chunk.state = 'published'",
        "know.chunk.visibility != 'personal'",
        "know.chunk.document_id IN (SELECT know.item.item_id FROM know.item WHERE "
        "know.item.public_at IS NOT NULL AND know.item.state = 'published' AND "
        "know.item.visibility != 'personal')",
    ):
        assert conjunct in predicate
    person = sql(reach_predicate(Reach(principal_id="u_reader", departments=("web",))))
    assert "owner_id" in person and "owner_id" not in predicate
    assert "'company'" in person and "'company'" not in predicate


def test_every_leg_a_question_runs_carries_the_public_predicate() -> None:
    """Delete this and one leg of the search could reach past the marking while the others kept
    to it."""
    expected = sql(public_predicate())
    legs = (
        lexical_query("opening hours", reach=PUBLIC),
        cjk_lexical_query("营业时间", reach=PUBLIC),
        vector_query([0.0] * EMBEDDING_DIMENSIONS, reach=PUBLIC, model="m@r:1"),
    )
    for leg in legs:
        assert expected in sql(leg)


def test_a_public_statement_runs_as_the_public_role_and_names_nobody() -> None:
    """The settings are the role alone: no principal and no department reaches a policy. Delete
    this and a public statement could run as the application, whose policies admit company-wide
    documents to a connection that set nothing."""
    settings = session_settings(PUBLIC)
    assert [str(one) for one in settings] == [SET_PUBLIC_ROLE]
    assert f"SET LOCAL ROLE {PUBLIC_ROLE}" == SET_PUBLIC_ROLE
    assert migration("0171").PUBLIC_ROLE == PUBLIC_ROLE


# ------------------------------------------------------------------ what 0171 holds
def test_0171_copies_the_models_two_checks() -> None:
    """Delete this and the model and the database can disagree about whether a marking names a
    person, or whether a personal document may be marked."""
    checks = {
        one.name: str(one.sqltext)
        for one in cast("Table", KnowledgeItemRow.__table__).constraints
        if isinstance(one, CheckConstraint)
    }
    module = migration("0171")
    assert checks["ck_item_a_public_marking_is_a_person_and_a_date"] == (
        module.A_MARKING_IS_A_PERSON_AND_A_DATE
    )
    assert (
        checks["ck_item_a_personal_item_is_never_public"] == module.A_PERSONAL_ITEM_IS_NEVER_PUBLIC
    )
    assert module.ITEM_COLUMNS_ADDED == ("public_by", "public_at")
    assert {"public_by", "public_at"} <= set(cast("Table", KnowledgeItemRow.__table__).c.keys())


def test_0171s_policies_are_for_the_public_role_alone_and_state_the_predicates_conditions() -> None:
    """Delete this and the second wall can name the application, admitting its rows to every
    request, or drop a condition the first wall keeps, so a statement missing the predicate reads
    a draft or an unmarked document."""
    module = migration("0171")
    item_policy, chunk_policy = (" ".join(one.split()) for one in module.RLS)
    for policy in (item_policy, chunk_policy):
        assert "FOR SELECT TO brain_public" in policy
        assert "brain_app" not in policy
        assert "public_at IS NOT NULL" in policy
        assert "state = 'published'" in policy
        assert "visibility <> 'personal'" in policy
    assert "deleted_at IS NULL" in chunk_policy
    assert "i.item_id = chunk.document_id" in chunk_policy
    assert all("brain_public" in one and "brain_app" not in one for one in module.PUBLIC_GRANTS)
    assert module.MEMBERSHIP == "GRANT brain_public TO brain_app WITH INHERIT FALSE, SET TRUE"


def test_0171_puts_0120s_audit_function_back_and_adds_only_which_way_the_marking_went() -> None:
    """Delete this and the downgrade can leave a function naming columns that are gone, or the
    upgrade can change what every other item entry records."""
    ours, theirs = migration("0171"), migration("0120")
    assert ours.ITEM_AUDIT_FUNCTION_AS_0120_SHIPPED == theirs.ITEM_AUDIT_FUNCTION
    added = ours.ITEM_AUDIT_FUNCTION.replace(ours._PUBLIC, "")
    assert added == theirs.ITEM_AUDIT_FUNCTION
    assert "jsonb_build_object('public', NEW.public_at IS NOT NULL)" in ours._PUBLIC
    assert "NEW.public_at IS DISTINCT FROM OLD.public_at" in ours._PUBLIC


def test_0171_emits_what_it_declares_and_its_downgrade_takes_it_away() -> None:
    """On the SQL Alembic renders, not the file's text. Delete this and a statement sitting in a
    constant that `upgrade` never runs would pass every test above."""
    from tests.unit.test_tables import rendered, squash

    path = next(VERSIONS.glob("0171_*.py"))
    up, down = squash(rendered("upgrade", path)), squash(rendered("downgrade", path))
    module = migration("0171")
    assert "ALTER TABLE know.item ADD COLUMN public_by VARCHAR(128)" in up
    assert "ALTER TABLE know.item ADD COLUMN public_at TIMESTAMP WITH TIME ZONE" in up
    for statement in (*module.PUBLIC_GRANTS, *module.RLS, module.MEMBERSHIP):
        assert squash(statement) in up
    assert squash(module.ITEM_AUDIT_FUNCTION) in up
    assert squash(module.ITEM_AUDIT_FUNCTION_AS_0120_SHIPPED) in down
    for statement in (*module.DOWNGRADE_RLS, *module.REVOKES):
        assert squash(statement) in down
    assert "ALTER TABLE know.item DROP COLUMN public_at" in down
