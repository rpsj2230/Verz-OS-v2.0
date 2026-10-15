from pathlib import Path
from brain.ops.mutation import Mutation, verify

report = verify(
    [
        Mutation(
            label="the sync places people unless departments are managed on People",
            path="src/brain/identity/departments_from.py",
            before="return departments_from(env, saved) is DepartmentsFrom.STAFF_SOURCE",
            after="return departments_from(env, saved) is not DepartmentsFrom.STAFF_SOURCE",
            tests=("tests/unit/test_departments_from.py",),
        ),
        Mutation(
            label="Sync now is not run where no source the worker reads is chosen",
            path="src/brain/ops/acceptance_checks_people.py",
            before="if chosen is None or chosen.name not in READERS or not chosen.ready:",
            after="if False:",
            tests=("tests/unit/test_acceptance_checks_people.py",),
        ),
        Mutation(
            label="People reports nobody's standing under the install's source",
            path="src/brain/directory_routes.py",
            before="StaffMemberRow.source == source,\n        )\n    )\n\n\ndef standings_by_person",
            after="StaffMemberRow.source == source + 'x',\n        )\n    )\n\n\ndef standings_by_person",
            tests=("tests/unit/test_acceptance_checks_people.py",),
        ),
    ],
    repo=Path("."),
    carry=(),
)
print(report.table())
print("survivors:", [s.label for s in report.survivors])
