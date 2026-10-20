from pathlib import Path

from brain.ops.mutation import Mutation, verify

report = verify(
    [
        Mutation(
            label="turning the write on must leave the administrator's ledger entry",
            path="src/brain/ops/acceptance_freshdesk_reply.py",
            before="    if len(recorded) != before + 1 or administrator not in recorded:\n",
            after="    if False:\n",
            tests=("tests/unit/test_acceptance_freshdesk_reply.py",),
        ),
        Mutation(
            label="each delivery must verify as a receiver checks it",
            path="src/brain/ops/acceptance_freshdesk_reply.py",
            before="        or not signed\n",
            after="",
            tests=("tests/unit/test_acceptance_freshdesk_reply.py",),
        ),
        Mutation(
            label="the event must be delivered on a retry after the refusal",
            path="src/brain/ops/acceptance_freshdesk_reply.py",
            before="        len(receiver.requests) != 2\n        or len(bodies) != 1\n",
            after="        len(bodies) != 1\n",
            tests=("tests/unit/test_acceptance_freshdesk_reply.py",),
        ),
    ],
    repo=Path("."),
    carry=(),
)
print(report.table())
assert not report.survivors
