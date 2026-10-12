"""The field policy of a tool whose records no classification describes, so a run can read them.

A run redacts every tool result at the run's reach with a policy chosen for the tool's entity
(`brain.api_routes.policy_of`), and **an entity nobody classified gets the empty policy, which
withholds every field**. That is the right default for a row tool, where a missing classification
means nobody decided who may read a column. It is the wrong one for a tool whose whole result is a
fact about the call: the website check's status and certificate days, the output of a skill's
script, a skill's instructions. Those three registered, passed every registration rule and
returned a record whose every field a run then took out, so a model that asked for one was handed
an empty payload and said so. Measured on 2026-10-07: `redact` over a `WebsiteCheck` with the
policy `policy_of` gave it returned no record at all.

**Each field is read under one capability per tool, the tool's own where it is a read.** The tool
was admitted to the run because the run's reach holds its capability, and the record is a
function of that same call, so a field that asked for more would be a field the tool could be
called for and never answer. The script tool is the exception that is forced: it is called under
`invoke:`, and a field rule cannot ask for a permission to act, so its output is read under
`SCRIPT_OUTPUT_CAPABILITY`. Rejected: one rule per field under a `read:<entity>.<field>`
capability, which is how a classified entity does it, because nobody would ever grant eleven
capabilities named after a website check's columns, and a capability nobody grants is the same
silence as the empty policy with more paperwork.

**A scope on the capability still narrows the record**, because the redactor matches a grant's
scope against the record's own fields: a website check granted for one host reads the records
whose `website_host` is that host, which is the scope the tool itself asks first.

Task ids: M12.4.4, M12.2.8, M12.2.9
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel

from brain.core.entitlement import Capability
from brain.core.field_policy import Classification, FieldPolicy, FieldRule
from brain.tools.registry import SKILL_SCRIPT_OBJECT
from brain.tools.run_skill import ScriptRun
from brain.tools.skill_tools import (
    INSTRUCTIONS_CAPABILITY,
    SKILL_INSTRUCTIONS_OBJECT,
    SkillInstructions,
)
from brain.tools.website_check import (
    WEBSITE_CHECK_CAPABILITY,
    WEBSITE_CHECK_OBJECT,
    WebsiteCheck,
)

#: What reads a script's output: a read, because a field rule may not ask for a permission to act
#: (`FieldRule` refuses `invoke:`, "a permission to act is not a permission to see"). The tool
#: itself is called under `invoke:skill_script`, so an agent that is let run a script is granted
#: both, and the one that may run it without being told what it printed is granted the first.
SCRIPT_OUTPUT_CAPABILITY: Final = Capability(value=f"read:{SKILL_SCRIPT_OBJECT}")

#: What every `Entity` carries and the redactor reads as the record's tag and key, not as a field.
TAG_FIELDS: Final = frozenset({"entity", "id"})


def policy_over(
    model: type[BaseModel], *, entity: str, capability: str, classification: Classification
) -> FieldPolicy:
    """A rule for each field of `model`, all under `capability`. See the module docstring."""
    return FieldPolicy(
        rules=tuple(
            FieldRule.of(entity, name, capability, classification)
            for name in model.model_fields
            if name not in TAG_FIELDS
        )
    )


#: The policy of each such entity. A new tool of this kind is one more row, and the test that
#: reads the registry refuses a registered entity that is in neither this table nor a
#: classification, so the empty policy is never an accident.
OWN_RESULT_POLICIES: Final[Mapping[str, FieldPolicy]] = MappingProxyType(
    {
        WEBSITE_CHECK_OBJECT: policy_over(
            WebsiteCheck,
            entity=WEBSITE_CHECK_OBJECT,
            capability=WEBSITE_CHECK_CAPABILITY.value,
            classification=Classification.INTERNAL,
        ),
        SKILL_SCRIPT_OBJECT: policy_over(
            ScriptRun,
            entity=SKILL_SCRIPT_OBJECT,
            capability=SCRIPT_OUTPUT_CAPABILITY.value,
            classification=Classification.INTERNAL,
        ),
        SKILL_INSTRUCTIONS_OBJECT: policy_over(
            SkillInstructions,
            entity=SKILL_INSTRUCTIONS_OBJECT,
            capability=INSTRUCTIONS_CAPABILITY.value,
            classification=Classification.INTERNAL,
        ),
    }
)

__all__ = ["OWN_RESULT_POLICIES", "SCRIPT_OUTPUT_CAPABILITY", "TAG_FIELDS", "policy_over"]
