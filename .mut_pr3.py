from pathlib import Path

from brain.ops.mutation import Mutation, verify

VIS = "src/brain/knowledge/visibility.py"
LIFE = "src/brain/agents/lifecycle.py"
GS = "src/brain/console/global_surfaces.py"
RC = "src/brain/builder/run_cost.py"
RT = "src/brain/agent_builder_routes.py"
PUB = "src/brain/builder/publish.py"

T_H = ("tests/unit/test_holds_for_level.py",)
T_GS = ("tests/unit/test_global_surfaces.py", "tests/unit/test_holds_for_level.py")
T_RC = ("tests/unit/test_run_cost.py", "tests/unit/test_agent_builder_cost_hold.py")
T_RT = ("tests/unit/test_agent_builder_cost_hold.py", "tests/unit/test_agent_builder_routes.py")

mutations = [
    Mutation(
        label="the company needs nothing over everything",
        path=VIS,
        before="            return scope_narrows(Scope.unrestricted(), held)",
        after="            return True",
        tests=T_H,
    ),
    Mutation(
        label="a department's authority is not asked about that department",
        path=VIS,
        before="        case Visibility.DEPARTMENT if department:",
        after="        case Visibility.DEPARTMENT if False:",
        tests=T_H,
    ),
    Mutation(
        label="a department's authority is held over any department",
        path=VIS,
        before="            return scope_narrows(department_scope(department), held)",
        after="            return True",
        tests=T_H,
    ),
    Mutation(
        label="holding nothing is enough",
        path=VIS,
        before="    if held is None:\n        return False\n    match to_level:",
        after="    if False:\n        return False\n    match to_level:",
        tests=T_H,
    ),
    Mutation(
        label="a promotion is approved without asking how wide the authority is",
        path=VIS,
        before="    if not holds_for_level(entitlement, PROMOTION_CAPABILITY, proposal.to_level, now):",
        after="    if False:",
        tests=T_H,
    ),
    Mutation(
        label="an agent is published without asking how wide the authority is",
        path=LIFE,
        before="    if not holds_for_level(publisher, AGENT_PUBLICATION_CAPABILITY, PUBLICATION_LEVEL, now):",
        after="    if False:",
        tests=T_H,
    ),
    Mutation(
        label="the queue offers a request wider than the reader's authority",
        path=GS,
        before="    if not holds_for_level(entitlement, PROMOTION_CAPABILITY, request.record.to_level, now):\n        return False",
        after="    if False:\n        return False",
        tests=T_GS,
    ),
    Mutation(
        label="the console offers company publication to anybody holding the capability",
        path=GS,
        before="    return holds_for_level(entitlement, AGENT_PUBLICATION_CAPABILITY, PUBLICATION_LEVEL, now)",
        after="    return entitlement.scope_for(AGENT_PUBLICATION_CAPABILITY, now) is not None",
        tests=T_GS,
    ),
    Mutation(
        label="a run costing the ceiling exactly is held",
        path=RC,
        before="    if cost <= ceiling_minor:",
        after="    if cost < ceiling_minor:",
        tests=T_RC,
    ),
    Mutation(
        label="a run costing less than the ceiling is held",
        path=RC,
        before="    if cost <= ceiling_minor:",
        after="    if cost <= ceiling_minor and False:",
        tests=T_RC,
    ),
    Mutation(
        label="an agent in no department is priced against nothing and held",
        path=RC,
        before="    if not department or ceiling_minor is None:",
        after="    if ceiling_minor is None:",
        tests=T_RC,
    ),
    Mutation(
        label="a department with no ceiling holds everything",
        path=RC,
        before="    if not department or ceiling_minor is None:",
        after="    if not department:",
        tests=T_RC,
    ),
    Mutation(
        label="a document with no tier is priced as free",
        path=RC,
        before="    if not isinstance(tier, str) or not isinstance(tools, list):\n        return None",
        after="    if not isinstance(tier, str) or not isinstance(tools, list):\n        return 0",
        tests=T_RC,
    ),
    Mutation(
        label="the price ignores the tools a manifest allows",
        path=RC,
        before="    return run_cost(manifest.tier, len(manifest.authority.allowed_tools))",
        after="    return run_cost(manifest.tier, 0)",
        tests=T_RC,
    ),
    Mutation(
        label="a publish held for its cost still needs the approver to hold everything it reaches",
        path=RT,
        before="    if widened and approval_refusal(",
        after="    if approval_refusal(",
        tests=T_RT,
    ),
    Mutation(
        label="the hold is not asked for a publish that does not widen",
        path=RT,
        before="    if second_people_needed(view.widened) > 0 or hold is not None:",
        after="    if second_people_needed(view.widened) > 0:",
        tests=T_RT,
    ),
    Mutation(
        label="a widening held for its cost says the cheaper reason",
        path=RT,
        before="                if hold is not None and not view.widened",
        after="                if hold is not None",
        tests=T_RT,
    ),
    Mutation(
        label="the hold is on whatever the switch says",
        path=RT,
        before="    if sessions is None or not await cost_hold_is_on(sessions):",
        after="    if sessions is None:",
        tests=("tests/unit/test_acceptance_publish_cost.py",),
    ),
    Mutation(
        label="the record shows no cost",
        path=PUB,
        before="                cost_minor=cost_of_document(one.document),",
        after="                cost_minor=None,",
        tests=("tests/unit/test_run_cost.py", "tests/unit/test_publication_store.py"),
    ),
    Mutation(
        label="no department with no ceiling is a hold with ceiling zero",
        path=RT,
        before="    return True, None if row is None else row.ceiling_minor",
        after="    return True, 0 if row is None else row.ceiling_minor",
        tests=("tests/unit/test_acceptance_publish_cost.py",),
    ),
]

report = verify(mutations, repo=Path("."), carry=())
print(report.table())
print("SURVIVORS", [one.label for one in report.survivors])
