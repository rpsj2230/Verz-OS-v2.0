from pathlib import Path
from brain.ops.mutation import Mutation, verify

T = ("tests/unit/test_acceptance_checks_starter.py",)
report = verify(
    [
        Mutation(
            label="the six roles are not held to six words",
            path="src/brain/ops/acceptance_checks_starter.py",
            before="if {one.value for one in roles()} != THE_SIX_ROLES or len(roles()) != len(THE_SIX_ROLES):",
            after="if False:",
            tests=T,
        ),
        Mutation(
            label="the idle limit the defaults name is not compared to the sign-in code's",
            path="src/brain/ops/acceptance_checks_starter.py",
            before='if declared["session_idle_minutes"] != str(int(SESSION_IDLE.total_seconds() // 60)):',
            after="if False:",
            tests=T,
        ),
        Mutation(
            label="a default becoming a setting is not noticed",
            path="src/brain/ops/acceptance_checks_starter.py",
            before='if any(name in BY_NAME or f"INSTALL_{name.upper()}" in BY_NAME for name in THE_FOUR_DEFAULTS):',
            after="if False:",
            tests=T,
        ),
    ],
    repo=Path("."),
    carry=(),
)
print(report.table())
print("survivors:", [s.label for s in report.survivors])
