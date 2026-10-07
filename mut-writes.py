from pathlib import Path

from brain.ops.mutation import Mutation, verify

report = verify(
    [
        Mutation(
            label="a write declared as changing nothing is refused",
            path="src/brain/ops/acceptance_checks_cloudflare.py",
            before="            one.side_effect is SideEffect.NONE or not one.name.startswith",
            after="            False or not one.name.startswith",
            tests=("tests/unit/test_acceptance_cloudflare.py",),
        ),
        Mutation(
            label="turning a write on must leave a ledger entry by its giver",
            path="src/brain/ops/acceptance_checks_cloudflare.py",
            before="    if len(entries) != before + 1 or entries[-1][0] != h.actor:",
            after="    if False:",
            tests=("tests/unit/test_acceptance_cloudflare.py",),
        ),
    ],
    repo=Path("."),
    carry=(),
)
print(report.table())
assert not report.survivors
