from pathlib import Path

from brain.ops.mutation import Mutation, verify

T = ("tests/unit/test_console_explanations.py",)
E = "src/brain/console/explanations.py"
R = "src/brain/explanation_routes.py"

report = verify(
    [
        Mutation(
            label="an empty expiry matches every path",
            path=E,
            before='    if one.retired_by == "":\n        return False\n',
            after="",
            tests=T,
        ),
        Mutation(
            label="an unregistered act answers a default sentence",
            path=E,
            before="    return BY_ACT.get(act)\n",
            after="    return BY_ACT.get(act, EXPLANATIONS[0])\n",
            tests=T,
        ),
        Mutation(
            label="the route answers an unregistered act without raising",
            path=R,
            before="    if one is None:\n",
            after="    if False:\n",
            tests=T,
        ),
        Mutation(
            label="the route drops the lead from its body",
            path=R,
            before="lead=one.lead.value, ",
            after='lead="", ',
            tests=T,
        ),
        Mutation(
            label="an action loses its lead",
            path=E,
            before='        f"{SOON}changing who can find this agent.",',
            after='        "changing who can find this agent.",',
            tests=T,
        ),
        Mutation(
            label="two acts share an id",
            path=E,
            before='        "agent.browser",',
            after='        "agent.level",',
            tests=T,
        ),
        Mutation(
            label="an expiry widens to match a neighbouring route",
            path=E,
            before="/(audience|availability)\\b",
            after="/(audience|availability|skills)\\b",
            tests=T,
        ),
        Mutation(
            label="a note loses its lead",
            path=E,
            before='"its one-line summary.",\n        Lead.SOON,',
            after='"its one-line summary.",\n        Lead.NONE,',
            tests=T,
        ),
    ],
    repo=Path("."),
    carry=(
        "src/brain/console/explanations.py",
        "src/brain/explanation_routes.py",
        "src/brain/routers.py",
        "tests/unit/test_console_explanations.py",
    ),
)
print(report.table())
print("SURVIVORS", list(report.survivors))
