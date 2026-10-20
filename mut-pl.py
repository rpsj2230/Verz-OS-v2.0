from pathlib import Path

from brain.ops.mutation import Mutation, verify

report = verify(
    [
        Mutation(
            label="the pooler is capped at its own pool",
            path="docker-compose.yml",
            before='      MAX_DB_CONNECTIONS: "20"\n',
            after='      MAX_DB_CONNECTIONS: "40"\n',
            tests=("tests/unit/test_install_docs.py",),
        ),
    ],
    repo=Path("."),
    carry=(),
)
print(report.table())
assert not report.survivors
