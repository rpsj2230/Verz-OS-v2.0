"""A person describes a skill, a model drafts it, and it lands as any import does.

M12.4.14 asks that a person create a skill by describing it in conversation: the system drafts the
instructions, the knowledge it needs, the tools it uses and some example tasks, and the draft
lands unreviewed and not executable, exactly like an import. This module is the half that reads a
model's reply, and it decides one thing: **what a model's words may become is a `SKILL.md` that
goes through the parser every other way in goes through, and nothing else.** The route
(`brain.skill_routes.draft_skill`) hands that text to the library as an undecided upload, which is
the state every import is in, so a drafted skill is reviewed by a second person, rehearsed against
its examples and approved before any agent can read its body, with no flag on the row saying a
model wrote it that could be mistaken for a mark of trust.

**The reply is untrusted input, and what it names is checked against what the install has.** A
reply that is not one JSON object is refused whole, with a sentence saying nothing was drafted.
Inside a readable reply, a tool the install does not register and a department it does not hold
are each dropped and reported as a finding in words, never kept: a skill naming a tool nobody
registered would be a skill that cannot do what it says, and one naming a department that does not
exist would be a need no agent could meet. The person is told which were left out, because a draft
that silently lost a step is one they would approve believing it complete.

**The model is never told what a skill may reach, and cannot write it.** `Skill` has no field for
a capability, a scope, a grant or a rung, and this reads six keys from a reply and no others, so a
reply carrying a `capabilities` or a `scope` key has it ignored and the skill is built without it.
What the model names in `tools` is a list of names the reviewer reads, as in a pasted file, and the
skill reaches what those tools would have reached for its caller anyway.

**The prompt is the person's own description and the names the install already shows them.** The
system message takes no parameters, so it is the same text for every person and sits in the
cacheable prefix. The user message carries the description, the tool names the install registers
with their one-line descriptions, and the department names. No document, row or other skill is in
it. Rejected: showing the model the library's existing skills so it could avoid duplicates. It
would put every skill's body into a prompt written by whoever asked, and the library already
refuses a name spelt as another and bytes it holds.

Scope: domain logic. Nothing here calls a model, opens a connection or reads a clock.

Task ids: M12.4.14
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from brain.models.driver import DriverMessage, Role
from brain.tools.skill_examples import EXAMPLES_HEADING, EXPECTS, MAX_EXAMPLES, MAX_TASK_CHARS
from brain.tools.skills import Skill, SkillError, markdown_of, skill_from_markdown

#: The longest description of a skill a person may give. Long enough for a procedure told in a few
#: paragraphs, short enough that it is a request and not a document.
DESCRIPTION_CHARS: Final = 4_000

#: How many words a model may spend on one draft. A skill is a page, not a book.
REPLY_TOKENS: Final = 2_000

#: The first version a drafted skill is given, below every real release so a reviewer reads it as
#: what it is.
DRAFT_VERSION: Final = "0.1.0"

#: Why a drafted skill is no more trusted than an imported one.
A_DRAFTED_SKILL_IS_AN_IMPORT_AND_NOTHING_MORE_TRUSTED: Final = (
    "A model wrote these words from a description, and the words are a procedure an agent will "
    "carry out. So the draft is stored undecided, its body withheld from every agent, and it is "
    "approved only by a second person after its examples have been rehearsed, exactly as a skill "
    "that arrived from a repository is. Nothing on the stored row says a model wrote it, because a "
    "mark that could be read as a reason to trust it would be the opposite of the rule."
)

#: What a person is told when a draft was read and part of it was left out.
LEFT_OUT: Final = "was left out of the draft"


class SkillDraftError(Exception):
    """A description or a reply that cannot become a draft, in words the person can act on."""


@dataclass(frozen=True)
class DraftFinding:
    """One thing the draft names that this install does not have, and what was done about it."""

    what: str
    message: str


@dataclass(frozen=True)
class SkillDraft:
    """The `SKILL.md` a reply became, the skill it parses to, and what was left out of it."""

    markdown: str
    skill: Skill
    findings: tuple[DraftFinding, ...]


def checked_description(text: str) -> str:
    """The person's description, trimmed, or a refusal naming the rule."""
    described = text.strip()
    if not described:
        msg = "describe what the skill should do; there was nothing to draft from"
        raise SkillDraftError(msg)
    if len(described) > DESCRIPTION_CHARS:
        msg = f"a description may be up to {DESCRIPTION_CHARS} characters; this one is longer"
        raise SkillDraftError(msg)
    return described


def system_prompt() -> str:
    """The standing instruction. Takes no parameters, so it is one text for every request."""
    return (
        "You draft one skill for a company's AI assistant from a person's description. A skill is "
        "a short written procedure: when to use it, the steps, and which tools it uses. Reply with "
        "one JSON object and nothing else, with these keys: "
        '"name" (lowercase letters, digits, hyphens and underscores, starting with a letter), '
        '"description" (one sentence beginning "Use when"), '
        '"instructions" (the steps, plain text, one step per line), '
        '"tools" (a list of tool names chosen only from the list you are given, or an empty list), '
        '"knowledge" (a list of department names chosen only from the list you are given, naming '
        "the departments whose documents the steps read, or an empty list), "
        '"examples" (two to four objects, each with "task", a request a person would make, and '
        '"tools", the tool names a run of that task would use, chosen from your own tools list). '
        "Never invent a tool or a department. Never write a permission, a scope or an access rule."
    )


def draft_messages(
    description: str,
    *,
    tools: Sequence[tuple[str, str]],
    departments: Sequence[str],
) -> tuple[DriverMessage, DriverMessage]:
    """The two messages sent: the standing instruction, then the request.

    `tools` is each registered tool's name and one-line description, and `departments` the
    department names, both sorted here so two requests with the same answer to those questions send
    the same bytes.
    """
    listed = "\n".join(f"- {name}: {about}" for name, about in sorted(tools)) or "(none)"
    held = ", ".join(sorted(departments)) or "(none)"
    request = (
        f"Description of the skill:\n{checked_description(description)}\n\n"
        f"Tools you may name:\n{listed}\n\nDepartments you may name: {held}\n"
    )
    return (
        DriverMessage(role=Role.SYSTEM, content=system_prompt()),
        DriverMessage(role=Role.USER, content=request),
    )


def _object_of(reply: str) -> dict[str, Any]:
    """The one JSON object a reply holds, or a refusal saying nothing was drafted.

    A reply wrapped in a code fence is read, because a model asked for JSON often fences it; one
    with prose around it is not, since the prose is where a model argues itself into something.
    """
    text = reply.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced is not None:
        text = fenced.group(1)
    try:
        found = json.loads(text)
    except ValueError:
        found = None
    if not isinstance(found, dict):
        msg = "the model's reply was not a skill, so nothing was drafted; describe it again"
        raise SkillDraftError(msg)
    return found


def _text(found: dict[str, Any], key: str) -> str:
    value = found.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"the draft has no {key}, so nothing was drafted; describe it again"
        raise SkillDraftError(msg)
    return value.strip()


def _names(found: dict[str, Any], key: str) -> list[str]:
    value = found.get(key, [])
    if not isinstance(value, list):
        return []
    return [one.strip() for one in value if isinstance(one, str) and one.strip()]


def _kept(
    asked: Iterable[str], held: frozenset[str], kind: str, findings: list[DraftFinding]
) -> tuple[str, ...]:
    """The names the install holds, in order and once each; every other one is a finding."""
    kept: list[str] = []
    for name in asked:
        if name in held:
            if name not in kept:
                kept.append(name)
        else:
            findings.append(DraftFinding(what=name, message=f"the {kind} {name} {LEFT_OUT}"))
    return tuple(kept)


def read_reply(reply: str, *, tools: Iterable[str], departments: Iterable[str]) -> SkillDraft:
    """A model's reply as a draft skill, or a refusal. See the module docstring.

    The skill is written out as the `SKILL.md` it would be and read back through the one parser, so
    it is refused for exactly what a pasted file would be: a name that is not a slug, a description
    that does not open by saying when it is used, an example expecting a tool the skill does not
    list. The examples are written under the heading `brain.tools.skill_examples` reads, one line
    each, and an example naming a tool left out of the draft keeps its line with that tool removed
    and says so.
    """
    found = _object_of(reply)
    held_tools, held_departments = frozenset(tools), frozenset(departments)
    findings: list[DraftFinding] = []
    named_tools = _kept(_names(found, "tools"), held_tools, "tool", findings)
    named_departments = _kept(_names(found, "knowledge"), held_departments, "department", findings)

    lines: list[str] = []
    examples = found.get("examples", [])
    if isinstance(examples, list):
        for one in examples[:MAX_EXAMPLES]:
            if not isinstance(one, dict):
                continue
            task = one.get("task")
            if not isinstance(task, str) or not task.strip():
                continue
            expected = [name for name in _names(one, "tools") if name in named_tools]
            line_task = " ".join(task.split())[:MAX_TASK_CHARS]
            lines.append(f"- {line_task} {EXPECTS} {', '.join(expected) if expected else 'none'}")
    body = _text(found, "instructions")
    if lines:
        body = f"{body}\n\n{EXAMPLES_HEADING}\n" + "\n".join(dict.fromkeys(lines))
    try:
        built = Skill(
            name=_text(found, "name"),
            description=_text(found, "description"),
            version=DRAFT_VERSION,
            tools=named_tools,
            knowledge=named_departments,
            body=body,
        )
        markdown = markdown_of(built)
        skill = skill_from_markdown(markdown)
    except (SkillError, ValueError) as refused:
        msg = f"the draft was refused, so nothing was drafted: {refused}"
        raise SkillDraftError(msg) from None
    return SkillDraft(markdown=markdown, skill=skill, findings=tuple(findings))
