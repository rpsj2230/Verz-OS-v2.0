"""The skill tools a run reads a skill with, and the policy that lets a run read their results.

Four groups. The instructions tool answers for the skills a run was offered and for no others. The
script tool sends the sandbox the approved bytes and refuses before sending anything when the bytes
are not those, and is registered only where there is a sandbox. A run reads a tool's record only
because the tool has a policy of its own: the empty policy withholds every field, which is what a
website check, a script's output and a skill's instructions met until `brain.tools.own_results`.
And the caller that binds a run's agent and offered skills binds them only to the handlers that
declare them, and turns a skill's refusal into the runtime's one refusal.

Task ids: M12.2.8, M12.2.9, M12.4.11, M12.4.4
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import TypedResult
from brain.core.field_policy import FieldPolicy
from brain.core.redaction import redact
from brain.core.scope import Clause, Op, Scope
from brain.ops.sandbox import AnswerStatus, RunAnswer
from brain.tools.own_results import OWN_RESULT_POLICIES, SCRIPT_OUTPUT_CAPABILITY
from brain.tools.registry import SKILL_SCRIPT_OBJECT, ToolRegistry
from brain.tools.run_skill import (
    SCRIPT_CAPABILITY,
    SCRIPT_CHANGED_SINCE_APPROVAL,
    SKILL_NOT_AVAILABLE,
    ScriptRequest,
    SkillScriptError,
    assert_single_execution_path,
)
from brain.tools.skill_tools import (
    INSTRUCTIONS_CAPABILITY,
    INSTRUCTIONS_TOOL,
    SKILL_INSTRUCTIONS_OBJECT,
    InstructionsRequest,
    OfferedSkills,
    ScriptSandbox,
    SkillInstructions,
    SkillTools,
    instructions_handler,
    register_skill_tools,
    script_handler,
)
from brain.tools.skills import (
    ImportedSkill,
    Skill,
    SkillPin,
    SkillSource,
    SourceKind,
    execution_tool,
    script_sha256_of,
)
from brain.tools.startup import build_registry
from brain.tools.website_check import (
    WEBSITE_CHECK_CAPABILITY,
    WEBSITE_CHECK_OBJECT,
    ChainEnd,
    WebsiteCheck,
)

#: Pinned far from any wall clock, as `test_scope_and_capability` does.
NOW = datetime(2999, 1, 1, tzinfo=UTC)
REVIEWED_AT = datetime(2019, 3, 4, tzinfo=UTC)

SCRIPT = "scripts/check.py"
BYTES = b"print('3 accounts expire')\n"
BODY = "Check the expiry, then say which accounts are close."


def _offered(*, agent: str = "ops_agent", body: str = BODY) -> OfferedSkills:
    skill = Skill(
        name="hosting_expiry",
        description="Check which hosting accounts expire this month",
        version="1.0.0",
        scripts=(SCRIPT,),
        script_sha256=((SCRIPT, script_sha256_of(BYTES)),),
        body=body,
    )
    imported = ImportedSkill(
        skill=skill,
        source=SkillSource(kind=SourceKind.UPLOAD, location="x.zip", content_digest="a" * 64),
    ).approved_by("a_reviewer", REVIEWED_AT)
    pin = SkillPin(agent_id=agent, skill_name=skill.name, digest=skill.digest())
    return {skill.name: (pin, imported)}


def _reach(*capabilities: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id="p_asker",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted())
            for one in capabilities
        ),
    )


class _Sandbox:
    """A sandbox answering in the process from a transport, keeping every request it was sent."""

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        self.files = {SCRIPT: BYTES} if files is None else files

        def answer(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            self.sent.append(body)
            return httpx.Response(
                200,
                json=RunAnswer(
                    run_id=str(body["run_id"]),
                    status=AnswerStatus.COMPLETED,
                    exit_code=0,
                    output="3 accounts expire",
                    elapsed_seconds=0.01,
                ).to_json(),
            )

        self.client = httpx.Client(transport=httpx.MockTransport(answer))

    async def read(self, digest: str) -> dict[str, bytes]:
        return dict(self.files)

    def over(self) -> ScriptSandbox:
        return ScriptSandbox(
            address="http://sandbox.invalid:3100", client=self.client, script_bytes=self.read
        )


def _run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


# ------------------------------------------------------------------ the instructions tool


def test_an_offered_skill_hands_over_its_body_and_one_that_was_not_offered_does_not() -> None:
    """A skill offered to the run is read whole by name, and a name that is not among the offered,
    whether unknown or merely unassigned, is the one refusal. Delete this and either an agent
    cannot read what it was told it could, or any agent holding the capability reads any skill."""
    handler = instructions_handler()
    read = _run(
        handler(
            InstructionsRequest(skill="hosting_expiry"),
            entitlement=_reach(),
            now=NOW,
            skills=_offered(),
        )
    )
    [record] = read.records
    assert record.instructions == BODY
    assert record.entity == SKILL_INSTRUCTIONS_OBJECT
    with pytest.raises(SkillScriptError, match=SKILL_NOT_AVAILABLE):
        _run(
            handler(
                InstructionsRequest(skill="another_skill"),
                entitlement=_reach(),
                now=NOW,
                skills=_offered(),
            )
        )
    with pytest.raises(SkillScriptError, match=SKILL_NOT_AVAILABLE):
        _run(handler(InstructionsRequest(skill="hosting_expiry"), entitlement=_reach(), now=NOW))


# ---------------------------------------------------------------------- the script tool


def test_the_approved_bytes_are_sent_to_the_sandbox_once_and_its_answer_comes_back() -> None:
    """An offered skill's script runs through the sandbox with the bytes the approval covers, and
    its output is the record. Delete this and the tool can be registered, pass every rule and
    never reach a sandbox, which is where it stood until it was wired."""
    box = _Sandbox()
    ran = _run(
        script_handler(box.over())(
            ScriptRequest(skill="hosting_expiry", script=SCRIPT),
            entitlement=_reach(),
            now=NOW,
            agent_id="ops_agent",
            skills=_offered(),
        )
    )
    [record] = ran.records
    assert record.output == "3 accounts expire"
    assert len(box.sent) == 1
    assert box.sent[0]["digest"] == next(iter(_offered().values()))[1].skill.digest()


def test_a_script_changed_since_its_approval_is_refused_before_the_sandbox_is_asked() -> None:
    """Bytes in the library that are not the approved ones are refused in the product's own path,
    and nothing reaches the sandbox, for a changed file, an extra file and no file. Delete this and
    the byte check can be removed from the path a run takes with every check of the runner alone
    still green."""
    for files in (
        {SCRIPT: BYTES + b"import os\n"},
        {SCRIPT: BYTES, "scripts/other.py": BYTES},
        {},
    ):
        box = _Sandbox(files)
        with pytest.raises(SkillScriptError, match=SCRIPT_CHANGED_SINCE_APPROVAL):
            _run(
                script_handler(box.over())(
                    ScriptRequest(skill="hosting_expiry", script=SCRIPT),
                    entitlement=_reach(),
                    now=NOW,
                    agent_id="ops_agent",
                    skills=_offered(),
                )
            )
        assert box.sent == []


def test_a_script_nobody_offered_this_run_is_refused_without_a_lookup() -> None:
    """No agent, no offered skill and an offered skill of another name each refuse with the one
    sentence and read no bytes. Delete this and a run can reach a skill pinned to somebody else."""
    box = _Sandbox()
    handler = script_handler(box.over())
    request = ScriptRequest(skill="hosting_expiry", script=SCRIPT)
    for kwargs in (
        {"agent_id": None, "skills": _offered()},
        {"agent_id": "ops_agent", "skills": {}},
        {"agent_id": "ops_agent", "skills": None},
    ):
        with pytest.raises(SkillScriptError, match=SKILL_NOT_AVAILABLE):
            _run(handler(request, entitlement=_reach(), now=NOW, **kwargs))
    assert box.sent == []


def test_the_script_tool_is_registered_only_where_a_sandbox_runs() -> None:
    """The instructions tool is in every registry the builder returns with skill tools; the script
    tool only with a sandbox, and then as the one tool holding the script object. Delete this and
    an install with no sandbox offers a tool that cannot answer, or one with a sandbox has none."""
    without = build_registry(source="demo", skills=SkillTools())
    assert without.has(INSTRUCTIONS_TOOL)
    assert not without.has(execution_tool())
    with_one = build_registry(source="demo", skills=SkillTools(scripts=_Sandbox().over()))
    assert with_one.has(INSTRUCTIONS_TOOL)
    assert with_one.has(execution_tool())
    assert_single_execution_path(with_one)
    assert not build_registry(source="demo").has(INSTRUCTIONS_TOOL)


# ------------------------------------------------------------------- what a run may read


def _check_record() -> WebsiteCheck:
    return WebsiteCheck(
        entity=WEBSITE_CHECK_OBJECT,
        id="1",
        website_host="example.com",
        address="https://example.com/",
        outcome=ChainEnd.ANSWERED,
        status=200,
        final_address="https://example.com/",
        certificate_expires_in_days=40,
    )


def test_every_tool_that_answers_with_its_own_entity_has_a_policy_that_lets_its_reader_read() -> (
    None
):
    """A reach holding the tool's read capability is handed the record's fields, one without is
    handed none, and a grant scoped to another host reads none of a website check. Delete this and
    a registered tool can return a record every field of which a run then takes out, which was the
    state of the website check, a script's output and a skill's instructions."""
    cases = ((WEBSITE_CHECK_OBJECT, WEBSITE_CHECK_CAPABILITY.value, _check_record(), "status"),)
    for entity, capability, record, field in cases:
        policy = OWN_RESULT_POLICIES[entity]
        wrapped = TypedResult(records=(record,), source="s", fetched_at="x")
        held = redact(wrapped, entitlement=_reach(capability), policy=policy, now=NOW)
        assert held.payload.records
        assert held.payload.records[0][field] is not None
        refused = redact(wrapped, entitlement=_reach(), policy=policy, now=NOW)
        assert refused.payload.records == ()
        # The empty policy is what these results met before: nothing survives it.
        assert (
            redact(
                wrapped, entitlement=_reach(capability), policy=FieldPolicy(), now=NOW
            ).payload.records
            == ()
        )
    elsewhere = EntitlementSet(
        principal_id="p_asker",
        grants=(
            Grant(
                capability=WEBSITE_CHECK_CAPABILITY,
                scope=Scope(
                    clauses=(Clause(field="website_host", op=Op.IN, value=("other.example",)),)
                ),
            ),
        ),
    )
    wrapped = TypedResult(records=(_check_record(),), source="s", fetched_at="x")
    assert (
        redact(
            wrapped,
            entitlement=elsewhere,
            policy=OWN_RESULT_POLICIES[WEBSITE_CHECK_OBJECT],
            now=NOW,
        ).payload.records
        == ()
    )


def test_the_script_output_and_the_instructions_are_read_under_their_own_read_capabilities() -> (
    None
):
    """A script's output is read under a `read:` capability, since a field rule cannot ask for a
    permission to act, and the skill tools' capabilities and objects are the ones the registry holds
    them to. Delete this and the output of a script is withheld from the run that ran it, or read
    by anybody allowed to call the tool."""
    assert SCRIPT_OUTPUT_CAPABILITY.value == f"read:{SKILL_SCRIPT_OBJECT}"
    assert SCRIPT_OUTPUT_CAPABILITY != SCRIPT_CAPABILITY
    registry = ToolRegistry()
    register_skill_tools(registry, SkillTools(scripts=_Sandbox().over()))
    for definition in registry.definitions():
        assert definition.entity in OWN_RESULT_POLICIES
    assert INSTRUCTIONS_CAPABILITY.value == f"read:{SKILL_INSTRUCTIONS_OBJECT}"


def test_a_run_reads_the_website_check_the_registry_holds_and_not_an_empty_record() -> None:
    """`policy_of`, over the registry the application builds with the website check and the skill
    tools, gives each of their entities a policy with rules, so the record a run is handed has
    fields. Delete this and `policy_of` can stop consulting the tools' own policies, and the three
    tools register, pass and answer a run with nothing, which is what they did."""
    from brain.api_routes import policy_of
    from brain.tools.website_check import WebsiteCheckTool

    registry = build_registry(
        source="demo",
        website=WebsiteCheckTool(resolver=None, prober=None),  # type: ignore[arg-type]
        skills=SkillTools(scripts=_Sandbox().over()),
    )
    chosen = policy_of(registry)
    seen = {definition.entity for definition in registry.definitions()}
    assert {WEBSITE_CHECK_OBJECT, SKILL_SCRIPT_OBJECT, SKILL_INSTRUCTIONS_OBJECT} <= seen
    for definition in registry.definitions():
        if definition.entity in OWN_RESULT_POLICIES:
            assert chosen(definition).rules, definition.name


# ----------------------------------------------------------------------- the run's caller


def test_a_run_binds_its_agent_and_skills_only_to_a_handler_that_declares_them() -> None:
    """`RunToolCaller` hands `agent_id` and `skills` to a handler declaring those parameters and to
    no other, and a skill's refusal becomes the runtime's one refusal while any other error stays
    an error. Delete this and either the skill tools are called with no agent, or every other
    tool is called with arguments it does not take, or one refused script ends the whole run."""
    from brain.api_routes import RunToolCaller
    from brain.core.envelope import IdentityMode, SideEffect, ToolDefinition
    from brain.gate.runtime import ToolRefusedError

    registry = ToolRegistry()
    register_skill_tools(registry, SkillTools(scripts=_Sandbox().over()))
    caller = RunToolCaller(registry, agent_id="ops_agent", skills=_offered())
    by_name = {definition.name: definition for definition in registry.definitions()}
    reach = _reach(INSTRUCTIONS_CAPABILITY.value)

    async def ask(name: str, arguments: dict[str, Any], *, skills: Any = None) -> Any:
        use = caller if skills is None else RunToolCaller(registry, agent_id="a", skills=skills)
        return await use.call(tool=by_name[name], arguments=arguments, entitlement=reach, now=NOW)  # type: ignore[misc]

    read = asyncio.run(ask(INSTRUCTIONS_TOOL, {"skill": "hosting_expiry"}))
    assert read.records[0].instructions == BODY
    with pytest.raises(ToolRefusedError):
        asyncio.run(ask(INSTRUCTIONS_TOOL, {"skill": "hosting_expiry"}, skills={}))

    seen: list[set[str]] = []

    def plain(
        request: InstructionsRequest, *, entitlement: EntitlementSet, now: Any = None
    ) -> TypedResult[SkillInstructions]:
        seen.append({"plain"})
        return TypedResult[SkillInstructions](records=(), source="s")

    other = ToolRegistry()
    other.register(
        ToolDefinition(
            name="skill.read_other",
            description="Reads something else",
            entity="skill_other",
            args_schema=InstructionsRequest.model_json_schema(),
            required_capability="read:skill_other",
            side_effect=SideEffect.NONE,
            identity_mode=IdentityMode.DELEGATED,
            source="skill",
        ),
        plain,
    )
    [definition] = other.definitions()
    RunToolCaller(other, agent_id="ops_agent", skills=_offered()).call(
        tool=definition, arguments={"skill": "hosting_expiry"}, entitlement=reach, now=NOW
    )
    assert seen == [{"plain"}]
