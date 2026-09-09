"""Where a capability applies.

A Scope is a row predicate, stored as jsonb and evaluated both in Python (for local
objects) and in SQL (for queries). It composes by conjunction only.

That restriction is the whole design. Disjunction would let two narrow grants combine
into a wider one, which means you could never answer "what can this person see?" by
reading their grants, you would have to solve a satisfiability problem. Conjunction-only
means composing scopes can only ever narrow, so the reachable set of any grant set is
computable by inspection.

**This module used to render its own SQL and no longer does.** `Scope.to_sql` and
`Clause.to_sql` were deleted on 2026-09-09 by the owner's decision on item 40 of
`docs/needs-rupash.md`. The only renderer is `brain.core.scope_sql.compile_where`, and the
Python half of the pair is `matches` below. Do not add a second one back, whatever it is
called: `tests/invariants/test_single_implementation.py` now reads the source for the shape
rather than for the name, because the name is what the old check watched and the old copy
was called something else.

Four reasons. The first is structural and the other three were measured, by compiling the
same scope both ways and reading what came back:

**It was a second answer to the question this system exists to answer.** Two renderings of
"who may see which row" are reasonable in isolation and drift, and the one that drifts is
found by a permission being wrong rather than by a test. That is what the
single-implementation invariant forbids, and the invariant missed this one because it counted
the name `compile_where`.

**It hard-coded the JSON path, so it could not use a promoted column.** `to_sql` always
emitted `row_data ->> 'department'`. `compile_where` takes a `ColumnLayout` and emits
`k.department` for a field that has a real column, which is the difference between a scope an
index can serve and a scope that becomes a scan.

**It never called `assert_conjunctive`, which is the check that stops a scope widening
rather than narrowing.** A clause of `IN` with an empty member list rendered as
`row_data ->> 'd' = ANY(:s0)` with `[]` bound; `compile_where` refuses the same scope before
compiling anything.

**It could not say an impossible scope was impossible.** Two contradictory equalities
rendered as a conjunction of both, which returns nothing and is indistinguishable from an
empty table; `compile_where` returns `FALSE` with `certainly_empty` set, so the caller can
say why the answer was empty.

The item also recorded the two disagreeing on `IN` given a bare string. That half has since
moved and the record should not be read as current: `Clause` refuses that shape at
construction, and the duplicate check inside `_check_clause` was removed as unreachable
earlier the same day, so the two now agree on every clause the type can hold. The four
reasons above are the ones that still hold, and none of them needed a divergence to matter.

Task ids: M0.2.2
"""

from __future__ import annotations

import enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Op(enum.StrEnum):
    """The predicate grammar. Deliberately small.

    There is no NOT and no OR. Adding either would break the narrowing guarantee that
    `Scope.intersect` depends on.
    """

    EQ = "eq"
    IN = "in"
    PREFIX = "prefix"
    ANY = "any"


class Clause(BaseModel):
    """One field test."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.]*$")
    op: Op
    value: str | tuple[str, ...] | None = None

    @model_validator(mode="after")
    def _value_shape_cannot_make_sql_wider_than_python(self) -> Self:
        """Refuse only the shapes where the two evaluators disagree, and nothing else.

        This is a narrow rule on purpose. Plenty of odd clauses are merely useless: `EQ`
        with a None value, or an empty `IN`, match nothing in Python and nothing in SQL.
        They agree, and they fail closed, so refusing them here would be a different job
        (authoring-time sanity, which `scope_sql` does) and would make them impossible to
        write a test about.

        Two shapes genuinely diverge, and in both the SQL side is the wider one:

        - `IN` given a bare string. `matches` requires a tuple and admits nothing, while a
          renderer calling `list("abc")` admits "a", "b" and "c" as three values.
        - `PREFIX` given a non-string. `matches` admits nothing, while a renderer taking
          `str(None)` produces `LIKE 'None%'`, which matches any row whose value starts
          with "None".

        Both sentences named `to_sql` until it was deleted on 2026-09-09. The renderer they
        describe is now `brain.core.scope_sql.compile_where`, which reaches neither shape
        because this validator refuses both before a `Clause` exists to compile.
        """
        if self.op is Op.IN and not isinstance(self.value, tuple):
            msg = (
                f"an IN clause needs a tuple, not {type(self.value).__name__}; "
                "a bare string is admitted character by character in SQL"
            )
            raise ValueError(msg)
        if self.op is Op.PREFIX and not isinstance(self.value, str):
            msg = (
                f"a PREFIX clause needs a string, not {type(self.value).__name__}; "
                "anything else is rendered into the LIKE pattern and matches rows"
            )
            raise ValueError(msg)
        return self

    def matches(self, row: dict[str, Any]) -> bool:
        if self.op is Op.ANY:
            return True
        actual = row.get(self.field)
        if actual is None:
            # Absent is not permitted. A missing field must never satisfy a predicate,
            # or a partially-projected row would widen access by omission.
            return False
        actual_s = str(actual)
        if self.op is Op.EQ:
            return actual_s == self.value
        if self.op is Op.IN:
            return isinstance(self.value, tuple) and actual_s in self.value
        return isinstance(self.value, str) and actual_s.startswith(self.value)


class Scope(BaseModel):
    """A conjunction of clauses. Empty means unrestricted; that is only ever legitimate
    on a grant that was explicitly written as company-wide.

    Clauses are normalised on construction: deduplicated and sorted. Conjunction is both
    commutative and idempotent, so this changes no meaning, but it makes two scopes that
    admit the same rows serialise identically, which `EntitlementSet.ent_hash` depends on.
    Without it, intersecting a scope with itself yields duplicate clauses and a different
    hash, so the same caller would miss their own cache entry and appear in traces as a
    different principal.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    clauses: tuple[Clause, ...] = ()

    @field_validator("clauses")
    @classmethod
    def _normalise(cls, v: tuple[Clause, ...]) -> tuple[Clause, ...]:
        seen: dict[tuple[str, str, str], Clause] = {}
        for c in v:
            seen[(c.field, str(c.op), repr(c.value))] = c
        return tuple(seen[k] for k in sorted(seen))

    @classmethod
    def unrestricted(cls) -> Self:
        return cls(clauses=())

    @classmethod
    def department(cls, name: str) -> Self:
        return cls(clauses=(Clause(field="department", op=Op.EQ, value=name),))

    def matches(self, row: dict[str, Any]) -> bool:
        return all(c.matches(row) for c in self.clauses)

    def intersect(self, other: Scope) -> Scope:
        """Conjunction. The result can only be narrower than either input, never wider,
        which is the property the whole permission model rests on."""
        return Scope(clauses=self.clauses + other.clauses)

    def is_unrestricted(self) -> bool:
        return len(self.clauses) == 0 or all(c.op is Op.ANY for c in self.clauses)
