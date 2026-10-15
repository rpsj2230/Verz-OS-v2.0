from pathlib import Path

from brain.ops.mutation import Mutation, verify

report = verify(
    [
        Mutation(
            label="readiness asks the engine the sessions are bound to now",
            path="src/brain/session.py",
            before="        return await check_reachable(bound_engine(sessions, home))\n",
            after="        return await check_reachable(home)\n",
            tests=("tests/unit/test_readiness.py",),
        ),
    ],
    repo=Path("."),
    carry=(),
)
print(report.table())
assert not report.survivors
