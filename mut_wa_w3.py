from pathlib import Path
from brain.ops.mutation import Mutation, verify

P = "src/brain/ops/acceptance_checks_w3.py"
T = ("tests/unit/test_acceptance_checks_w3.py",)
report = verify(
    [
        Mutation(
            label="the answering agent is not read off the request row",
            path=P,
            before="    if await _selected(h, 2) != agent_id:",
            after="    if False:",
            tests=T,
        ),
        Mutation(
            label="the asker's memory as a hint is not looked for",
            path=P,
            before="    if f\"- I want {hint} in every reply\" not in told or HINTS_HEADING not in told:",
            after="    if False:",
            tests=T,
        ),
        Mutation(
            label="an answer by the agent to somebody outside its audience is not noticed",
            path=P,
            before="    if await _selected(h, 4) == agent_id:",
            after="    if False:",
            tests=T,
        ),
    ],
    repo=Path("."),
    carry=(),
)
print(report.table())
print("survivors:", [s.label for s in report.survivors])
