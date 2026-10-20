"""Mutation run for the coverage wiring. Untracked scratch; never staged."""

from pathlib import Path

from brain.ops.mutation import Mutation, verify

UNIT = ("tests/unit/test_adoption_coverage.py",)
DB = ("tests/unit/test_acceptance_checks_adoption.py",)
COV = "src/brain/console/adoption_coverage.py"
ROUTE = "src/brain/adoption_coverage_routes.py"
WELCOME = "src/brain/welcome_routes.py"
STORE = "src/brain/ops/coverage_store.py"

mutations = [
    Mutation(
        label="a department outside the reach is skipped, not just a department with no rule",
        path=COV,
        before="        if place is None or place not in reachable:\n            continue",
        after="        if place is None:\n            continue",
        tests=UNIT,
    ),
    Mutation(
        label="every connected source is nameable",
        path=COV,
        before="        if connection.connector in nameable:",
        after="        if True:",
        tests=UNIT,
    ),
    Mutation(
        label="a department with a recommendation is listed as having none",
        path=COV,
        before="        if suggestion is None:\n            unsuggested.append(place)",
        after="        if suggestion is not None:\n            unsuggested.append(place)",
        tests=UNIT,
    ),
    Mutation(
        label="a department-only offer admits an organisation-wide source",
        path=COV,
        before="        if only_for is not None and not scoped:\n            continue",
        after="        if False:\n            continue",
        tests=UNIT,
    ),
    Mutation(
        label="a connected source is offered again",
        path=COV,
        before="        if one.console is None or name in connected:\n            continue",
        after="        if one.console is None:\n            continue",
        tests=UNIT,
    ),
    Mutation(
        label="a source with no live lookup counts as records",
        path=COV,
        before="                    if one.reading is not None and one.live is not None",
        after="                    if one.reading is not None",
        tests=UNIT,
    ),
    Mutation(
        label="a source that asks for a department reaches every department",
        path=COV,
        before="            places = reachable[:1]",
        after="            places = reachable",
        tests=UNIT,
    ),
    Mutation(
        label="no department means no offers",
        path=COV,
        before="reachable = tuple(sorted(set(departments))) or (WHOLE_COMPANY,)",
        after="reachable = tuple(sorted(set(departments))) or ('x',)",
        tests=UNIT,
    ),
    Mutation(
        label="a question may be about a kind of record the person cannot read",
        path=COV,
        before="                    and _may_ask_about(entity, entitlement, now, place)",
        after="                    and True",
        tests=UNIT,
    ),
    Mutation(
        label="a source for another department feeds a person's questions",
        path=COV,
        before="        if department_of(manifests.get(connection.connector)) != department:\n            continue",
        after="        if False:\n            continue",
        tests=UNIT,
    ),
    Mutation(
        label="a source with no live lookup is checkable",
        path=COV,
        before="    checkable = frozenset(name for name, one in declared.items() if one.live is not None)",
        after="    checkable = frozenset(name for name, one in declared.items())",
        tests=UNIT,
    ),
    Mutation(
        label="the merged line counts a source that was never read",
        path=COV,
        before="        synced_parts = [(last, held) for last, held in parts if last is not None]",
        after="        synced_parts = [(last, held) for last, held in parts]",
        tests=UNIT,
    ),
    Mutation(
        label="the department setting is spelled differently",
        path=COV,
        before='DEPARTMENT_SETTING: Final = "department"',
        after='DEPARTMENT_SETTING: Final = "team"',
        tests=UNIT,
    ),
    Mutation(
        label="the coverage view ignores its switch",
        path=ROUTE,
        before="    if not await coverage_is_on(request):",
        after="    if False:",
        tests=DB,
    ),
    Mutation(
        label="the first connector is given to a reader without the Connectors grant",
        path=ROUTE,
        before='    if not permitted(screen("connectors").read, asked.reach, asked.now):',
        after="    if False:",
        tests=DB,
    ),
    Mutation(
        label="questions from data ignore their switch",
        path=WELCOME,
        before="    if not await starter_from_data_is_on(request):",
        after="    if False:",
        tests=DB,
    ),
    Mutation(
        label="questions from data are built for a department that is not a slug",
        path=WELCOME,
        before="    if not department or not SLUG_RE.match(department):",
        after="    if not department:",
        tests=("tests/unit/test_welcome_routes.py",),
    ),
    Mutation(
        label="the count is not bounded to the departments it is asked for",
        path=STORE,
        before="WHERE deleted_at IS NULL AND fields->>'department' IN :departments ",
        after="WHERE deleted_at IS NULL AND fields->>'department' NOT IN :departments ",
        tests=DB,
    ),
]

import os

only = [x for x in os.environ.get("ONLY", "").split("|") if x]
if only:
    mutations = [m for m in mutations if any(x in m.label for x in only)]
report = verify(mutations, repo=Path("."), carry=())
print(report.table())
print("SURVIVORS:", [s.label for s in report.survivors])
