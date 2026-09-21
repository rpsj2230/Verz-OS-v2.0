"""What the person typed, turned into the agent they named, for `select_agent` to decide on.

`brain.gate.select.select_agent` has an ADDRESSED stage ahead of bindings, rules and the
classifier, and it decides whether the person may use the agent they named with the same
visible set every stage uses. Its docstring leaves one thing to the caller: "resolving a name to
an id is the channel's job". This is that job, for both surfaces the task names, so the two
cannot resolve a name differently.

**The web application sends an id beside the question.** The picker offers only agents the
person may see, but the value arrives as text a client chose, so it is normalised here and
judged by `select_agent` like any other name.

**A chat addresses an agent with a mention that opens the message.** Only the opening mention
counts. Text quoted from a document or an email can carry an `@name`, and an address that
retrieved or pasted text can supply is an address somebody outside the company chooses, which
then chooses the agent, and therefore the tools, that handle the question.

**Nothing here decides who may use what.** A named agent the person may not use and a name that
never existed both reach `select_agent` as a name, and it gives both the same selection, so
DENIED and ABSENT stay one answer. A second check here would be a second answer to that
question, and the day the two disagree the permissive one is whichever runs first.

What this does not do yet, stated: no request path calls `select_agent`. `/answer` answers
without an agent, so neither surface has anywhere to send the chosen agent until the agent lane
exists; `test_gate_step_order` holds routing off `/answer` as an expected failure today.

Task ids: M3.9.8
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from brain.core.department import SLUG_PATTERN

#: A mention that opens a message: `@` and an agent id, then a separator or the end. The id
#: grammar is `SLUG_PATTERN`, which `AgentRecord.agent_id` uses, read rather than restated.
LEADING_MENTION: Final = re.compile(
    r"^\s*@(?P<agent>" + SLUG_PATTERN.removeprefix("^").removesuffix("$") + r")(?:[\s,:]+|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Address:
    """The question, and the id of the agent the person named, if any.

    `agent_id` is what `select_agent(addressed=...)` takes.
    """

    question: str
    agent_id: str | None = None


def from_web(question: str, agent_id: str | None) -> Address:
    """The web application's address: the picker's value, sent beside the question."""
    named = agent_id.strip().lower() if agent_id else ""
    return Address(question=question, agent_id=named or None)


def from_mention(text: str) -> Address:
    """A chat message's address: a leading `@agent_id`, taken off the question it opens."""
    found = LEADING_MENTION.match(text)
    if found is None:
        return Address(question=text)
    return Address(question=text[found.end() :].strip(), agent_id=found.group("agent").lower())
