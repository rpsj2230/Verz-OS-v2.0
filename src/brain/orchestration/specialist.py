"""A specialist is asked its subtask as a question, and what it answers is read as values.

`brain.orchestration.coordinator` runs a plan through a port (`Specialist`) and knows nothing of
how an agent is asked. This is the port's implementation for the agents this product has: the
subtask becomes one question put to the specialist **by the same function that answers a person**,
at the reach the engine folded, and the answer is read back as the values the contract promised.
It adds no second way to run an agent. The loop that hands a model its tools is
`brain.gate.runtime.AgentRuntime` and the only thing that reaches it is
`brain.api_routes.answered_for`, so a specialist's tool calls are judged at its reach, leashed,
metered and recorded exactly as a person's question is.

**The question carries the objective and what earlier steps found, and never a reach.** The reach
is not text: it is the `EntitlementSet` the engine folded and a route hands to `answered_for`, and
nothing a model reads can name or widen it. What earlier steps found is their **validated values**
(typed, bounded, with no prose field), so a later specialist is not handed a paragraph an earlier
one wrote, and a record a specialist read for one subtask reaches another only as the typed value
the contract let it return.

**The answer is read, never trusted.** The reply is searched for one JSON object and each field the
contract names is taken from it; anything else in the reply is dropped here, and anything the
contract does not accept is a stated gap one layer up. A reply with no object in it is read as no
values at all, which the contract refuses as a missing field, so a specialist that answered in
prose is a subtask that returned nothing and is stated as one. The cheaper design asks a model for
tool-call output and parses it, which would be a second tool loop; this reads the final answer the
one loop produced.

**A refusal is a refusal.** A specialist whose question was turned away (halted, over a budget,
no such agent for this asker) raises `SpecialistRefusedError`, which the engine states as a refused
child. It is the same outcome for an agent the asker cannot run and one that is stopped, so the
asker cannot tell the two apart.

Task ids: M18.5.2
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.orchestration.contract import FieldKind, FieldSpec
from brain.orchestration.coordinator import ChildWork, Delivered, SpecialistRefusedError

# ------------------------------------------------------------------ written-down reasons
#: Why the question carries no reach and the answer carries no tool output.
THE_QUESTION_CARRIES_WORDS_AND_THE_REACH_RIDES_ALONGSIDE: Final = (
    "The reach a specialist runs at is an entitlement set handed to the function that answers, "
    "never a sentence in the question, so nothing a model reads can name or widen it. What a "
    "specialist is told of earlier steps is their validated values and nothing else of them."
)

#: How a kind of value is asked for in words. Closed over `FieldKind` by the test that walks it.
KIND_WORDS: Final[Mapping[FieldKind, str]] = {
    FieldKind.IDENTIFIER: "a short reference such as a record id",
    FieldKind.LABEL: "a short word or phrase",
    FieldKind.INTEGER: "a whole number",
    FieldKind.DECIMAL: "a number",
    FieldKind.BOOLEAN: "true or false",
    FieldKind.TIMESTAMP: "a date and time in ISO 8601 with a time zone",
}


@dataclass(frozen=True)
class Answer:
    """What asking the specialist came to: its text, or that it was turned away, and its cost."""

    text: str | None
    refused: bool = False
    minor: int = 0
    seconds: float = 0.0


#: Puts a question to the specialist agent at the work's reach and says what it answered. The route
#: supplies it over `answered_for`, so a test can supply one over a script.
Asker = Callable[[ChildWork, str], Awaitable[Answer]]


def _plain(value: object) -> object:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def question_for(work: ChildWork) -> str:
    """The one question a subtask is put as: objective, earlier findings, and the answer's shape."""
    lines = [work.objective.strip()]
    if work.upstream:
        found = json.dumps(
            {key: dict(value) for key, value in sorted(work.upstream.items())},
            sort_keys=True,
            default=_plain,
        )
        lines.append(f"Earlier steps found, already checked: {found}")
    asked = "; ".join(f'"{spec.name}" ({KIND_WORDS[spec.kind]})' for spec in work.output)
    lines.append(
        f"Reply with one JSON object and nothing else, holding exactly these values: {asked}."
    )
    return "\n\n".join(lines)


def values_from(text: str, output: Sequence[FieldSpec]) -> dict[str, object]:
    """The values a reply holds for the fields the contract names, or none when it holds no object.

    The first JSON object in the text is read; a timestamp given as text is read as one. A field the
    reply lacks is simply absent, so the contract states it as missing, and a field the contract
    does not name is dropped here and never reaches the check.
    """
    start = text.find("{")
    if start < 0:
        return {}
    try:
        parsed, _ = json.JSONDecoder(parse_constant=_no_constant).raw_decode(text[start:])
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    values: dict[str, object] = {}
    for spec in output:
        if spec.name not in parsed:
            continue
        value = parsed[spec.name]
        if spec.kind is FieldKind.TIMESTAMP and isinstance(value, str):
            with contextlib.suppress(ValueError):
                value = datetime.fromisoformat(value)
        values[spec.name] = value
    return values


def _no_constant(name: str) -> object:
    """Refuse NaN and Infinity, which Python's JSON reader accepts and no JSON writer emits."""
    msg = f"{name} is not a JSON value"
    raise ValueError(msg)


class AskingSpecialist:
    """`coordinator.Specialist` over a function that asks an agent a question."""

    def __init__(self, ask: Asker) -> None:
        self._ask = ask

    async def run(self, work: ChildWork) -> Delivered:
        answer = await self._ask(work, question_for(work))
        if answer.refused or answer.text is None:
            raise SpecialistRefusedError
        return Delivered(
            values=values_from(answer.text, work.output),
            minor=answer.minor,
            seconds=answer.seconds,
        )
