"""The two tools a run reads a skill with: its instructions when asked for, and its scripts.

`brain.tools.skills` and `brain.tools.run_skill` decide what a skill is allowed to be and do, and
until this module neither reached a run. A model was shown a skill's card (`offered_cards`) and
had no way to ask for the rest, and `SkillScriptTool` was registered nowhere because it requires a
runner and there was no code that built one. The application's tool registry is built once at
start, so this is where the two are put in it, through the one door every tool uses.

**Progressive disclosure is two tools and a rule about who may ask (M12.2.8).** The card is in the
prompt and carries no body (`SkillCard` has nowhere to put one). The body comes from
`skill.read_instructions`, which answers for the skills **this run was offered**, which is
`brain.gate.model_lane.skills_offered`: pinned to this agent, approved, unmoved, and every tool
the skill names inside the run's reach. A skill that exists in the library, is approved and is
pinned to somebody else is therefore the same refusal as one that does not exist, for
`brain.tools.run_skill.SKILL_NOT_AVAILABLE`'s reason. Rejected: reading the library by name, which
would hand any agent holding the capability the instructions of every approved skill.

**One execution path, and it needs a sandbox somebody switched on (M12.2.9, M12.4.11).**
`skill.run_script` is registered only where `INSTALL_SERVICES` names `sandbox` and the release
started it under gVisor (`brain.ops.sandbox.sandbox_address`). Where there is none, no tool is
registered, which is `SkillScriptTool`'s own rule for a caller with no runner and
`brain.console.skill_library.THIS_INSTALL_RUNS_NO_SANDBOX`'s for an import carrying a script: a
skill with a script cannot arrive on such an install, and a tool that is present and cannot answer
safely is worse than one that is absent. The bytes the sandbox is sent are read from the library
by the skill's digest when the run asks, and `SandboxRunner` recomputes every file's sha256
against the hashes the approval covers before it posts anything, so a script that is not the one
approved never reaches the sandbox.

**The run's own reach is the script's, through the one intersection.** The run reach handed to a
tool is already `E(caller) ∩ agent_ceiling` (`brain.gate.roster.run_entitlement`), so it is
passed as both sides of `SkillScriptTool`'s own call: the intersection is idempotent and this
module adds no second implementation of the rule.

**A refusal is one sentence and a run goes on.** `SkillScriptError` is a `SkillError`, and
`brain.api_routes.RunToolCaller` turns it into the runtime's one refusal, so a skill that is not
available, a script changed since its approval and a sandbox that did not answer are all the
sentence every unavailable tool gets, and the reason is in the log.

Task ids: M12.2.8, M12.2.9, M12.4.11
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from brain.core.entitlement import Capability, EntitlementSet
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.tools.registry import ResultContract, ToolRegistry
from brain.tools.run_skill import (
    SKILL_NOT_AVAILABLE,
    RunOutcome,
    SandboxSpec,
    ScriptLeash,
    ScriptRequest,
    ScriptRun,
    SkillScriptError,
    SkillScriptTool,
)
from brain.tools.skills import SKILL_NAME_RE, ImportedSkill, SkillPin, body_of

if TYPE_CHECKING:
    import httpx

#: The tool that hands a model one offered skill's instructions, and the object it reads.
INSTRUCTIONS_TOOL: Final = "skill.read_instructions"
SKILL_INSTRUCTIONS_OBJECT: Final = "skill_instructions"
INSTRUCTIONS_CAPABILITY: Final = Capability(value=f"read:{SKILL_INSTRUCTIONS_OBJECT}")

#: The system both tools answer for: the first segment of their names, as the registry requires.
SKILL_SOURCE: Final = "skill"

INSTRUCTIONS_DESCRIPTION: Final = (
    "Read the full instructions of one of the skills offered to you, by name, when the task in "
    "front of you is the one its short description names"
)

#: What a run was offered, by skill name: the pin it holds and the approved skill that pin names.
type OfferedSkills = Mapping[str, tuple[SkillPin, ImportedSkill]]

#: Reads the scripts of one stored skill by its digest: path to bytes. `StoredSkills.script_bytes`.
type ScriptBytesReader = Callable[[str], Awaitable[Mapping[str, bytes]]]


class InstructionsRequest(BaseModel):
    """The whole of what a model may say about reading a skill: its name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    skill: str = Field(min_length=1, max_length=80)

    @field_validator("skill")
    @classmethod
    def _is_a_skill_name(cls, v: str) -> str:
        if not SKILL_NAME_RE.match(v):
            msg = f"skill name {v!r} is not a lowercase slug"
            raise ValueError(msg)
        return v


class SkillInstructions(Entity):
    """One offered skill's instructions, tagged so the redactor can walk it."""

    skill: str
    version: str
    instructions: str


def instructions_definition() -> ToolDefinition:
    """What the catalogue describes: a read of an offered skill, spending no credential."""
    return ToolDefinition(
        name=INSTRUCTIONS_TOOL,
        description=INSTRUCTIONS_DESCRIPTION,
        entity=SKILL_INSTRUCTIONS_OBJECT,
        args_schema=InstructionsRequest.model_json_schema(),
        required_capability=INSTRUCTIONS_CAPABILITY.value,
        side_effect=SideEffect.NONE,
        identity_mode=IdentityMode.DELEGATED,
        source=SKILL_SOURCE,
    )


def instructions_handler() -> Callable[..., Awaitable[TypedResult[SkillInstructions]]]:
    """The handler: the instructions of a skill this run was offered, or the one refusal."""

    async def read_instructions(
        request: InstructionsRequest,
        *,
        entitlement: EntitlementSet,
        now: datetime | None = None,
        agent_id: str | None = None,
        skills: OfferedSkills | None = None,
    ) -> TypedResult[SkillInstructions]:
        """Hand over the body, which `body_of` refuses for a skill that is not approved."""
        del entitlement, agent_id
        held = (skills or {}).get(request.skill)
        if held is None:
            raise SkillScriptError(SKILL_NOT_AVAILABLE)
        _, imported = held
        record = SkillInstructions(
            entity=SKILL_INSTRUCTIONS_OBJECT,
            id=imported.skill.digest(),
            skill=imported.skill.name,
            version=imported.skill.version,
            instructions=body_of(imported),
        )
        return TypedResult(
            records=(record,),
            source=SKILL_SOURCE,
            fetched_at=now.isoformat() if now is not None else "",
        )

    return read_instructions


@dataclass(frozen=True)
class ScriptSandbox:
    """Where this install's scripts run: the sandbox's address, a client, and where bytes are read.

    `client` is the process's one HTTP client for the sandbox. It is a parameter so that the
    check and the tests answer from a transport in the process; the product builds it over the
    real network, and only where `address` is not None.
    """

    address: str
    client: httpx.Client
    script_bytes: ScriptBytesReader
    leash: ScriptLeash = field(default_factory=ScriptLeash)


@dataclass(frozen=True)
class SkillTools:
    """What the two tools are bound to. `scripts` is None where this install runs no sandbox."""

    scripts: ScriptSandbox | None = None


@dataclass(frozen=True)
class _Held:
    """`SkillLibrary` over the one skill a run was offered under this name, for this agent."""

    agent_id: str
    held: tuple[SkillPin, ImportedSkill]

    def pinned_skill(self, agent_id: str, skill_name: str) -> tuple[SkillPin, ImportedSkill] | None:
        _, imported = self.held
        if agent_id != self.agent_id or skill_name != imported.skill.name:
            return None
        return self.held


class _DescribeOnly:
    """A library and a runner for a tool built only to describe itself, which are never asked."""

    def pinned_skill(self, agent_id: str, skill_name: str) -> tuple[SkillPin, ImportedSkill] | None:
        return None

    def run(self, spec: SandboxSpec) -> RunOutcome:
        raise SkillScriptError(SKILL_NOT_AVAILABLE)


def script_definition() -> ToolDefinition:
    """The script tool's definition, which `SkillScriptTool` owns and this does not restate."""
    nothing = _DescribeOnly()
    return SkillScriptTool(library=nothing, runner=nothing).definition()


def script_handler(sandbox: ScriptSandbox) -> Callable[..., Awaitable[TypedResult[ScriptRun]]]:
    """The handler over a sandbox: the offered skill's script, run once, through the one tool."""
    from brain.ops.sandbox_client import SandboxRunner

    async def run_offered_skill_script(
        request: ScriptRequest,
        *,
        entitlement: EntitlementSet,
        now: datetime | None = None,
        agent_id: str | None = None,
        skills: OfferedSkills | None = None,
    ) -> TypedResult[ScriptRun]:
        """Read the bytes, hand them to the runner that checks them, and wait off the loop."""
        held = (skills or {}).get(request.skill)
        if agent_id is None or held is None:
            raise SkillScriptError(SKILL_NOT_AVAILABLE)
        files = dict(await sandbox.script_bytes(held[1].skill.digest()))
        tool = SkillScriptTool(
            library=_Held(agent_id, held),
            runner=SandboxRunner(sandbox.address, sandbox.client, lambda _digest: files),
            leash=sandbox.leash,
        )
        # The run reach is already the caller's narrowed by the agent's ceiling, so it is both
        # sides of the tool's own intersection; see the module docstring.
        return await asyncio.to_thread(
            tool.handler(),
            request,
            agent_id=agent_id,
            entitlement=entitlement,
            agent_ceiling=entitlement,
            now=now,
        )

    return run_offered_skill_script


def register_skill_tools(registry: ToolRegistry, tools: SkillTools) -> None:
    """Register the instructions tool always, and the script tool where there is a sandbox."""
    registry.register(
        instructions_definition(),
        instructions_handler(),
        result_contract=ResultContract.TYPED,
    )
    if tools.scripts is not None:
        registry.register(
            script_definition(),
            script_handler(tools.scripts),
            result_contract=ResultContract.TYPED,
        )


__all__ = [
    "INSTRUCTIONS_CAPABILITY",
    "INSTRUCTIONS_TOOL",
    "SKILL_INSTRUCTIONS_OBJECT",
    "SKILL_SOURCE",
    "InstructionsRequest",
    "OfferedSkills",
    "ScriptSandbox",
    "SkillInstructions",
    "SkillTools",
    "instructions_definition",
    "instructions_handler",
    "register_skill_tools",
    "script_definition",
    "script_handler",
]
