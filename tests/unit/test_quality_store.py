"""The quality tables and their pure rules: `0221` holds the model's shape, every row is a pointer
and a word, and the rules about regressions, decisions and cases hold on their own.

The database half is the install checks' (`tests/unit/test_acceptance_checks_quality.py`), which run
every store function and door over PostgreSQL at head.

Task ids: M28.3.1, M28.3.2, M28.3.3, M28.4.1, M28.5.3, M16.6.7, M16.7.14
"""

from __future__ import annotations

import asyncio
from dataclasses import fields
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.db import metadata
from brain.ops.feedback import CapturedCase
from brain.ops.quality_store import (
    DecisionError,
    ReleaseScore,
    case_document,
    decide,
    regressed,
)
from brain.tables.quality import CASE_KEYS, ItemKind, TierDecisionWord
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

MIGRATION = VERSIONS / "0221_quality_and_learning.py"
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
WHEN = datetime(2999, 6, 1, 12, 0, tzinfo=UTC)

TABLES = tuple(
    f"ops.{name}"
    for name in (
        "answer_flag",
        "regression_case",
        "quality_reading",
        "quality_annotation",
        "golden_score",
        "evaluation_candidate",
        "positive_example",
        "tier_decision",
    )
)


def test_the_migration_builds_each_table_exactly_as_the_model_declares_it() -> None:
    """Compared on rendered DDL, table by table, with every index. Delete this and a model can
    declare the closed vocabulary, the one-token reference or the two-person agreement while the
    database never has it."""
    emitted = squash(rendered("upgrade", MIGRATION))
    for name in TABLES:
        table = metadata.tables[name]
        assert squash(str(CreateTable(table).compile(dialect=DIALECT))) in emitted, name
        for index in table.indexes:
            assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted, index.name


def test_every_table_enables_row_security_and_is_granted_select_and_insert_alone() -> None:
    """Read off the emitted statements. Delete this and one of the eight can be rewritten or
    deleted by the application, and a judgement stops being a fact about a moment."""
    emitted = squash(rendered("upgrade", MIGRATION))
    for name in TABLES:
        assert f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY" in emitted, name
        assert f"GRANT SELECT, INSERT ON {name} TO brain_app" in emitted, name
    grants = [one for one in emitted.split(";") if "GRANT" in one and "ops." in one]
    assert grants and not any("UPDATE" in one or "DELETE" in one for one in grants)


def test_the_migration_names_its_tables_and_its_writers_once() -> None:
    """The lists the migration and `tests/unit/test_tables.py` read. Delete this and a table is
    built with no policy, or a policy names a table nothing builds."""
    module = migration_module(MIGRATION)
    assert tuple(module.TABLES) == TABLES
    assert tuple(table for table, _ in module.WRITERS) == TABLES


def test_a_kept_case_has_exactly_the_keys_a_captured_case_has_and_no_other() -> None:
    """The document's allow-list against the dataclass it is made from, outside both. Delete this
    and a field added to `CapturedCase` is refused by the table, or one added to the table is a
    place a value could arrive."""
    assert set(CASE_KEYS) == {one.name for one in fields(CapturedCase)}
    assert set(CASE_KEYS) == set(
        case_document(
            CapturedCase(
                question="q",
                held=(),
                answering_fields=("client.name",),
                locked_fields=(),
                mocked_from="synthetic_company",
                fault=__import__("brain.ops.feedback", fromlist=["FlagReason"]).FlagReason.STALE,
                origin_trace_ref="t1",
                origin_question_id="q1",
            )
        )
    )


def score(release: str, permission: int, passed: int, total: int) -> ReleaseScore:
    return ReleaseScore(
        release=release,
        ran_at=WHEN,
        permission_failures=permission,
        quality_passed=passed,
        quality_total=total,
    )


def test_a_release_regresses_on_a_permission_failure_or_a_lower_share_and_not_otherwise() -> None:
    """Both directions and the boundary. Delete this and a permission failure hides behind a good
    quality share, or a release that did exactly as well is called a regression."""
    before = score("r1", 0, 9, 10)
    assert regressed(score("r2", 1, 10, 10), before)
    assert regressed(score("r2", 0, 8, 10), before)
    assert not regressed(score("r2", 0, 9, 10), before)
    assert not regressed(score("r2", 0, 10, 10), before)
    assert not regressed(score("r2", 0, 0, 0), before)
    assert not regressed(score("r2", 0, 9, 10), score("r1", 1, 0, 0))


def test_a_release_with_no_quality_question_has_no_share_and_not_a_nought() -> None:
    """Delete this and nought of nothing reads as a failure of everything."""
    assert score("r", 0, 0, 0).quality_share is None
    assert score("r", 0, 1, 4).quality_share == 0.25


class _Never:
    """A session nothing may be written through, so a refused decision is refused before one."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"a refused decision touched the session ({name})")


@pytest.mark.parametrize(
    ("tier", "word"),
    [
        (3, TierDecisionWord.PROMOTED),
        (2, TierDecisionWord.APPROVED),
        (2, TierDecisionWord.DECLINED),
        (1, TierDecisionWord.PROMOTED),
        (0, TierDecisionWord.APPROVED),
    ],
)
def test_a_decision_the_tier_does_not_allow_is_refused_before_anything_is_written(
    tier: int, word: TierDecisionWord
) -> None:
    """Promotion is tier two's word and approval and decline are tier three's, and only those two
    tiers are decided by a person. Delete this and the word and the tier are free to disagree."""
    with pytest.raises(DecisionError):
        asyncio.run(
            decide(
                _Never(),  # type: ignore[arg-type]
                kind=ItemKind.EXAMPLE,
                ref="r",
                tier=tier,
                decision=word,
                decided_by="u_one",
                at=WHEN,
            )
        )
