from pathlib import Path

from brain.ops.mutation import Mutation, verify

TESTS = (
    "tests/unit/test_lark_sign_in.py",
    "tests/unit/test_lark_sign_in_routes.py",
)
report = verify(
    [
        Mutation(
            label="the bridge redeems a code only for the broker's own return address",
            path="src/brain/identity/lark_sign_in.py",
            before="        and parts.path.endswith(BROKER_RETURN_SUFFIX)",
            after="        and True",
            tests=TESTS,
        ),
        Mutation(
            label="the bridge refuses a client id that is not this install's application",
            path="src/brain/identity/lark_sign_in.py",
            before='        or form.get("client_id") != client_id',
            after="        or False",
            tests=TESTS,
        ),
        Mutation(
            label="an install not brokering to Lark has nothing at the bridge's address",
            path="src/brain/lark_sign_in_routes.py",
            before='    if not broker.provider or broker.provider.get("alias") != ALIAS:',
            after="    if False:",
            tests=TESTS,
        ),
    ],
    repo=Path("."),
    carry=(),
)
print(report.table())
assert not report.survivors
