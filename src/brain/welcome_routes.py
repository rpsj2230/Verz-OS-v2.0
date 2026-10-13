"""The questions a new person is offered on their first visit to Ask, for their own department.

`brain.identity.lifecycle.welcome_questions` was written for the joiner's first day and nothing
served it: the Ask page said it suggested no question. This is the route, and it holds no
judgement of its own. **The questions are a function of the caller's admitted reach and their own
department, and of nothing else**: a question is offered only when the caller holds every
capability it names in that department, so one they would be refused is never shown, and the
function takes one department name, so a list of the company's departments cannot be built from
it. No count of what was left out is sent, because that count is the number of things the person
may not ask.

Rejected: questions generated from what each department has indexed. That reads the knowledge
estate to decide what to suggest, and a suggestion built from an entity a person cannot see
discloses it; the three templates, kept only where the caller holds what they need, disclose
nothing. If a department has indexed nothing, the answer to a suggested question is the ordinary
nothing-found one, which is what any question about nothing gets.

Task ids: M26.1.4
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.identity.lifecycle import LifecycleError, welcome_questions

#: Where the questions are read from.
WELCOME_PATH: Final = "/welcome"

router = APIRouter(prefix=API_PREFIX, tags=["welcome"])


class WelcomeView(BaseModel):
    """At most three questions, in the order they are offered, and nothing else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    questions: list[str]


@router.get(WELCOME_PATH, response_model=WelcomeView, responses=COMMON_RESPONSES)
async def welcome(asked: Asked) -> WelcomeView:
    """The starter questions this person may ask in their own department.

    A person with no department, or whose department is not a slug the questions can name, is
    offered none, which is the same answer as one who may ask none of them.
    """
    department = asked.caller.principal.primary_department
    if not department:
        return WelcomeView(questions=[])
    try:
        found = welcome_questions(asked.reach, department, now=asked.now)
    except LifecycleError:
        return WelcomeView(questions=[])
    return WelcomeView(questions=list(found))
