from pathlib import Path

from brain.ops.mutation import Mutation, verify

report = verify(
    [
        Mutation(
            label="a citation carries the instant its field was read",
            path="src/brain/gate/compose.py",
            before="                    fetched_at=payload.fetched_at,\n",
            after='                    fetched_at="",\n',
            tests=("tests/unit/test_acceptance_live_answers.py",),
        ),
        Mutation(
            label="the check refuses an answer that does not cite the read time",
            path="src/brain/ops/acceptance_checks_live_answers.py",
            before="        and one.fetched_at\n",
            after="",
            tests=("tests/unit/test_acceptance_live_answers.py",),
        ),
        Mutation(
            label="the Connectors area names the leaf its recorded checks prove",
            path="src/brain/requirement_check_routes.py",
            before='    "Connectors": ("M11.8.8",),\n',
            after="",
            tests=("tests/unit/test_requirement_check_routes.py",),
        ),
    ],
    repo=Path("."),
    carry=(),
)
print(report.table())
assert not report.survivors
