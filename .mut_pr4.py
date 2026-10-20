from pathlib import Path

from brain.ops.mutation import Mutation, verify

CHOICES = "src/brain/builder/choices.py"
DESCRIBE = "src/brain/agent_describe_routes.py"
ROUTES = "src/brain/agent_builder_routes.py"
T_CHOICES = ("tests/unit/test_builder_choices.py",)
T_DESCRIBE = ("tests/unit/test_agent_describe_routes.py",)
T_FORM = ("tests/unit/test_builder_choices.py", "tests/unit/test_agent_builder_routes.py")

mutations = [
    Mutation(
        label="a department builder is told nothing is limited when the authority is wide enough",
        path=CHOICES,
        before="return held is not None and not scope_narrows(Scope.unrestricted(), held)",
        after="return held is not None",
        tests=T_CHOICES,
    ),
    Mutation(
        label="a builder with no install authority is limited too",
        path=CHOICES,
        before="return held is not None and not scope_narrows(Scope.unrestricted(), held)",
        after="return held is None or not scope_narrows(Scope.unrestricted(), held)",
        tests=T_CHOICES,
    ),
    Mutation(
        label="the choices ignore the side effect ceiling by capping it at none",
        path=CHOICES,
        before="max_side_effect=SideEffect.MONEY,",
        after="max_side_effect=SideEffect.NONE,",
        tests=T_CHOICES,
    ),
    Mutation(
        label="a connector is named by the tool and not by its source",
        path=CHOICES,
        before="connectors=tuple(sorted({registry.get(name).source for name in tools})),",
        after="connectors=tuple(sorted({name for name in tools})),",
        tests=T_CHOICES,
    ),
    Mutation(
        label="an empty offer is an empty enum instead of no room",
        path=CHOICES,
        before="    if names:\n        entries",
        after="    if True:\n        entries",
        tests=T_CHOICES,
    ),
    Mutation(
        label="a cut list may repeat a name",
        path=CHOICES,
        before='        cut["uniqueItems"] = True',
        after='        cut["uniqueItems"] = False',
        tests=T_CHOICES,
    ),
    Mutation(
        label="only the first tool list is cut",
        path=CHOICES,
        before="        for path in TOOL_PATHS:",
        after="        for path in TOOL_PATHS[:1]:",
        tests=T_CHOICES,
    ),
    Mutation(
        label="connectors are not cut",
        path=CHOICES,
        before="        if CONNECTOR_PATH in properties:",
        after="        if False:",
        tests=T_CHOICES,
    ),
    Mutation(
        label="the served form is never cut",
        path=ROUTES,
        before="    if limited_to_a_department(asked.reach, asked.now):",
        after="    if False:",
        tests=T_FORM,
    ),
    Mutation(
        label="the form is cut for everybody",
        path=ROUTES,
        before="    if limited_to_a_department(asked.reach, asked.now):",
        after="    if True:",
        tests=T_FORM,
    ),
    Mutation(
        label="a missing registry is not an empty offer",
        path=ROUTES,
        before="            if tools is not None\n            else Choices(tools=(), connectors=()),",
        after="            if tools is not None\n            else Choices(tools=('x.y',), connectors=('x',)),",
        tests=T_FORM,
    ),
    Mutation(
        label="the drafts page always offers describing",
        path=ROUTES,
        before="        can_describe=await describing_is_on(request),",
        after="        can_describe=True,",
        tests=T_DESCRIBE,
    ),
    Mutation(
        label="the switch is ignored when the test seam is not a bool",
        path=ROUTES,
        before="    if isinstance(found, bool):\n        return found\n    sessions = sessions_of(request)\n    return sessions is not None and await describe_is_on(sessions)",
        after="    return True",
        tests=T_DESCRIBE,
    ),
    Mutation(
        label="describing works with the switch off",
        path=DESCRIBE,
        before="    if not await describing_is_on(request):",
        after="    if False:",
        tests=T_DESCRIBE,
    ),
    Mutation(
        label="a blank description reaches the model",
        path=DESCRIBE,
        before="        checked_ask(body.description)\n",
        after="",
        tests=T_DESCRIBE,
    ),
    Mutation(
        label="a process with no model starts a draft anyway",
        path=DESCRIBE,
        before="    if calls_of(request) is None:",
        after="    if False:",
        tests=T_DESCRIBE,
    ),
    Mutation(
        label="a model that answered is treated as one that did not",
        path=DESCRIBE,
        before="        if answered.status_code == 200",
        after="        if answered.status_code != 200",
        tests=T_DESCRIBE,
    ),
    Mutation(
        label="a failed ask loses the reason it gives",
        path=DESCRIBE,
        before='            told=str(said.get("sentence", "")) or None,',
        after="            told=None,",
        tests=T_DESCRIBE,
    ),
    Mutation(
        label="the answer forgets what was not drafted",
        path=DESCRIBE,
        before="    not_drafted: list[str] = Field(default_factory=lambda: list(NOT_DRAFTED))",
        after="    not_drafted: list[str] = Field(default_factory=list)",
        tests=T_DESCRIBE,
    ),
    Mutation(
        label="the draft is started at the wrong revision's proposal",
        path=DESCRIBE,
        before="        request, draft_id, SuggestionAsked(revision=revision, ask=ask), asked",
        after="        request, draft_id, SuggestionAsked(revision=revision + 1, ask=ask), asked",
        tests=T_DESCRIBE,
    ),
]

report = verify(mutations, repo=Path("."), carry=())
print(report.table())
print("SURVIVORS", [one.label for one in report.survivors])
