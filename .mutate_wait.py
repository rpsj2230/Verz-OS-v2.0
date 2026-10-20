from pathlib import Path

from brain.ops.mutation import Mutation, verify

AW = "src/brain/ops/approval_wait.py"
INS = "src/brain/console/installation.py"
RT = "src/brain/install_routes.py"
TESTS = (
    "tests/unit/test_install_approval_wait_route.py",
    "tests/unit/test_approval_wait.py",
    "tests/unit/test_install_routes.py",
)
NEW = TESTS[:1]

LEAK = (
    "return (\n        *approval_wait_facts(typical_wait(pairs)),\n"
    "        Fact(\n            name='decided approvals',\n"
    "            source=__import__('brain.console.installation', fromlist=['Source']).Source.MEASURED,\n"
    "            value=str(len(pairs)),\n        ),\n    )"
)

mutations = [
    Mutation(
        "a decision stamped before its raising is clamped to no wait",
        AW,
        "waits = [max((decided - raised).total_seconds(), 0.0) for raised, decided in pairs]",
        "waits = [(decided - raised).total_seconds() for raised, decided in pairs]",
        TESTS,
    ),
    Mutation("nothing decided has no typical wait", AW, "    if not waits:", "    if False:", TESTS),
    Mutation("the typical wait is a median", AW, "statistics.median(waits)", "statistics.mean(waits)", TESTS),
    Mutation(
        "no wait is never wanted",
        AW,
        "    if typical is None:\n        return False",
        "    if False:\n        return False",
        TESTS,
    ),
    Mutation(
        "push is due only strictly past the stated hours",
        AW,
        "        > timedelta(hours=PUSH_IS_DUE_ABOVE_HOURS)",
        "        >= timedelta(hours=PUSH_IS_DUE_ABOVE_HOURS)",
        TESTS,
    ),
    Mutation(
        "the look-back is a quarter",
        AW,
        "LOOKBACK: Final = timedelta(days=90)",
        "LOOKBACK: Final = timedelta(days=9000)",
        TESTS,
    ),
    Mutation(
        "the view names two columns and no more",
        AW,
        '"SELECT raised_at, decided_at FROM gate.approval_wait"',
        '"SELECT raised_at, decided_at, id FROM gate.approval_wait"',
        TESTS,
    ),
    Mutation(
        "the view is the one read, not the suspension table",
        AW,
        "FROM gate.approval_wait",
        "FROM gate.suspension",
        TESTS,
    ),
    Mutation("under a minute is worded as such", AW, "    if minutes < 1:", "    if minutes < 0:", TESTS),
    Mutation(
        "one hour is singular",
        AW,
        'f"{hours} hour" + ("" if hours == 1 else "s")',
        'f"{hours} hour" + ("" if hours == 9 else "s")',
        TESTS,
    ),
    Mutation("a database that could not be asked is unknown", INS, "    if not readable:", "    if False:", TESTS),
    Mutation(
        "nothing decided is unknown, not zero",
        INS,
        "    if typical is None:",
        "    if False:",
        TESTS,
    ),
    Mutation(
        "the push sentence follows the verdict",
        INS,
        "    due = push_is_wanted(typical)",
        "    due = True",
        TESTS,
    ),
    Mutation(
        "a process with no database asks nothing",
        RT,
        '    if not isinstance(found, async_sessionmaker):\n        return ()\n    try:\n        async with found() as session:\n            pairs',
        '    if False:\n        return ()\n    try:\n        async with found() as session:\n            pairs',
        TESTS,
    ),
    Mutation(
        "an unreadable view is unknown, not an empty wait",
        RT,
        "        return approval_wait_facts(None, readable=False)",
        "        return approval_wait_facts(None)",
        TESTS,
    ),
    Mutation(
        "a failing database is caught",
        RT,
        'except SQLAlchemyError as error:\n        log.warning("approval waits not read"',
        'except ZeroDivisionError as error:\n        log.warning("approval waits not read"',
        TESTS,
    ),
    Mutation(
        "the install screen checks the capability",
        RT,
        '    _permitted(asked.reach, "install", asked.now)\n    settings = settings_of(request)\n    facts = install_facts(',
        '    settings = settings_of(request)\n    facts = install_facts(',
        TESTS,
    ),
    Mutation(
        "the capability is checked before the view is read",
        RT,
        '    _permitted(asked.reach, "install", asked.now)\n    settings = settings_of(request)\n    facts = install_facts(',
        '    await _approval_wait_facts(request, asked.now)\n    _permitted(asked.reach, "install", asked.now)\n    settings = settings_of(request)\n    facts = install_facts(',
        TESTS,
    ),
    Mutation(
        "no count of decided approvals reaches the page",
        RT,
        "    return approval_wait_facts(typical_wait(pairs))",
        "    " + LEAK,
        TESTS,
    ),
]

mutations = mutations[13:]
report = verify(mutations, repo=Path("."), carry=())
print(report.table())
print("SURVIVORS:", [v.label for v in report.survivors])
