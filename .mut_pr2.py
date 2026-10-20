from pathlib import Path

from brain.ops.mutation import Mutation, verify

UP = "src/brain/agents/upgrade.py"
RT = "src/brain/agent_upgrade_routes.py"
LE = "src/brain/agents/learned.py"
ST = "src/brain/learned_instruction_store.py"
TE = "src/brain/agents/template.py"
PR = "src/brain/prompt_routes.py"

T_UP = (
    "tests/unit/test_agent_upgrade_needs.py",
    "tests/unit/test_agent_upgrade.py",
    "tests/unit/test_agent_upgrade_routes.py",
)
T_LE = ("tests/unit/test_agent_learned.py", "tests/unit/test_prompt_routes.py")
DB_LE = ("tests/unit/test_acceptance_learned_changes.py",)
DB_UP = ("tests/unit/test_acceptance_upgrade_needs.py",)

mutations = [
    Mutation(
        label="every required question is new",
        path=UP,
        before="    required = {one.key for one in reviewed.pinned.manifest.placeholders if one.required}",
        after="    required: set[str] = set()",
        tests=T_UP,
    ),
    Mutation(
        label="a question the new version does not require is new",
        path=UP,
        before="        if one.required and one.key not in required",
        after="        if one.key not in required",
        tests=T_UP,
    ),
    Mutation(
        label="a question the old version required is asked again",
        path=UP,
        before="        if one.required and one.key not in required",
        after="        if one.required",
        tests=T_UP,
    ),
    Mutation(
        label="an acceptance reports nothing unanswered",
        path=UP,
        before="    settled = settle(\n        candidate,\n        upgraded,\n        audience=audience,\n        unanswered=newly_required_placeholders(reviewed),",
        after="    settled = settle(\n        candidate,\n        upgraded,\n        audience=audience,\n        unanswered=(),",
        tests=T_UP,
    ),
    Mutation(
        label="the review reports nothing unanswered",
        path=UP,
        before="            audience=audience,\n            unanswered=newly_required_placeholders(reviewed),",
        after="            audience=audience,\n            unanswered=(),",
        tests=T_UP,
    ),
    Mutation(
        label="the review says nothing is needed when nothing is on offer is skipped",
        path=UP,
        before="    candidate = reviewed.candidate\n    if candidate is None:\n        return None",
        after="    candidate = reviewed.candidate\n    if False:\n        return None",
        tests=T_UP,
    ),
    Mutation(
        label="the review route never asks what the version needs",
        path=RT,
        before="    if reviewed is not None and reviewed.candidate is not None and tools is not None:",
        after="    if False:",
        tests=T_UP,
    ),
    Mutation(
        label="a need is told with the wrong kind",
        path=RT,
        before="            kind=one.kind.value, name=one.name, sentence=NEEDS_WORDS[one.kind].format(name=one.name)",
        after="            kind='tool', name=one.name, sentence=NEEDS_WORDS[one.kind].format(name=one.name)",
        tests=T_UP,
    ),
    Mutation(
        label="learning may change any path",
        path=LE,
        before="    if path not in LEARNABLE_PATHS:",
        after="    if False:",
        tests=T_LE,
    ),
    Mutation(
        label="learning replaces what a person set",
        path=LE,
        before="    if path in instance.overlay and instance.overlay_owners[path].source is not FieldSource.LEARNED:",
        after="    if False:",
        tests=T_LE,
    ),
    Mutation(
        label="learning replaces a learned value only when a person set it",
        path=LE,
        before="instance.overlay_owners[path].source is not FieldSource.LEARNED:",
        after="instance.overlay_owners[path].source is FieldSource.LEARNED:",
        tests=T_LE,
    ),
    Mutation(
        label="a learned change is recorded as an administrator's",
        path=LE,
        before="    return set_field(instance, path, value, by=approved_by, at=at, source=FieldSource.LEARNED)",
        after="    return set_field(instance, path, value, by=approved_by, at=at)",
        tests=T_LE,
    ),
    Mutation(
        label="the list includes what a person set",
        path=LE,
        before="        if owner.source is FieldSource.LEARNED and path in instance.overlay",
        after="        if path in instance.overlay",
        tests=T_LE,
    ),
    Mutation(
        label="the list includes an owner with no value behind it",
        path=LE,
        before="        if owner.source is FieldSource.LEARNED and path in instance.overlay",
        after="        if owner.source is FieldSource.LEARNED",
        tests=T_LE,
    ),
    Mutation(
        label="giving back a learned change may take an administrator's value",
        path=LE,
        before="    if path not in instance.overlay or owner is None or owner.source is not FieldSource.LEARNED:",
        after="    if path not in instance.overlay:",
        tests=T_LE,
    ),
    Mutation(
        label="the mark is the person who approved it",
        path=TE,
        before="    owner = FieldOwner(source=source, set_by=by, set_at=at)",
        after="    owner = FieldOwner(source=FieldSource.INSTANCE, set_by=by, set_at=at)",
        tests=T_LE,
    ),
    Mutation(
        label="the Prompts screen does not say a value was learned",
        path=PR,
        before="                machine_authored=owner.source is FieldSource.LEARNED,",
        after="                machine_authored=False,",
        tests=T_LE,
    ),
    Mutation(
        label="learning writes with the switch off",
        path=ST,
        before="        if not await is_on(session, AGENT_LEARNED_CHANGES):\n            return Applied(Outcome.SWITCHED_OFF, SWITCHED_OFF)",
        after="        if False:\n            return Applied(Outcome.SWITCHED_OFF, SWITCHED_OFF)",
        tests=DB_LE,
    ),
    Mutation(
        label="a stale approval is written",
        path=ST,
        before="        if found[1].effective_hash != expected_hash:",
        after="        if False:",
        tests=DB_LE,
    ),
    Mutation(
        label="the same words are written and marked as learned",
        path=ST,
        before="            if refusal:",
        after="            if False:",
        tests=DB_LE,
    ),
]

report = verify(mutations, repo=Path("."), carry=())
print(report.table())
print("SURVIVORS", [one.label for one in report.survivors])
