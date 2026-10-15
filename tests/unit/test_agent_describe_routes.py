"""Describing an agent in your own words starts a draft and asks the co-author for it (M20.5.3).

Driven through the real application as `tests/unit/test_agent_coauthor_routes.py` is, with the model
answering from a script. These prove what the route decides: who is refused and with what left
behind, that the draft exists with revision one and holds nothing the model said until its author
takes it, that what is not drafted is said, and that a model that fails leaves a draft to ask again.
That the switch is read from PostgreSQL is the install check's.

Task ids: M20.5.3
"""

from __future__ import annotations

from typing import Any

from brain.agent_builder_routes import REFUSED, UNAVAILABLE
from brain.agent_coauthor_routes import NO_ANSWER_NOW, NO_MODEL_HERE, TAKE_PATH
from brain.agent_describe_routes import (
    DESCRIBE_PATH,
    DESCRIPTION_CHARS,
    NOT_DRAFTED,
)
from tests.unit.test_agent_builder_routes import Console, at
from tests.unit.test_agent_builder_routes import console as console
from tests.unit.test_agent_coauthor_routes import (
    NEWER,
    Scripted,
    persona_change,
    reply,
    taking,
    use,
)

WORDS = "An agent that answers questions about overdue invoices and names the invoice it read."


def describe(console_: Console, words: str = WORDS, pid: str = "u_admin") -> Any:
    return console_.post(pid, DESCRIBE_PATH, {"description": words})


def switched(console_: Console, on: bool = True) -> None:
    console_.app.state.describe_is_on = on


def test_a_description_starts_a_draft_and_proposes_what_the_model_said_without_applying_it(
    console: Console,
) -> None:
    """The draft exists at revision one and still holds the blank template's words, the suggestion
    is the co-author's own shape, the model was asked once, and the answer names what is not
    drafted.
    Delete this and the route can write a model's words into a draft with nobody having taken them,
    or answer a short proposal as though it were a finished agent."""
    switched(console)
    model = Scripted(text=reply(persona_change()))
    use(console, model)

    answered = describe(console)

    assert answered.status_code == 201, answered.text
    body = answered.json()
    stored = console.memory.drafts[body["draft_id"]]
    assert body["revision"] == len(stored.revisions) == 1
    assert [one["path"] for one in body["suggestion"]["hunks"]] == ["persona"]
    assert NEWER not in stored.revisions[0].body
    assert body["told"] is None
    assert body["not_drafted"] == list(NOT_DRAFTED)
    assert len(model.asked) == 1
    assert WORDS in model.asked[0]["messages"][-1].content


def test_taking_what_was_suggested_is_the_ordinary_take_and_writes_one_revision(
    console: Console,
) -> None:
    """The proposal a description returns is taken through the co-author's own route, by name, and
    writes the one revision a typed save would. Delete this and describing is a second way into a
    draft with rules of its own."""
    switched(console)
    use(console, Scripted(text=reply(persona_change())))
    body = describe(console).json()

    taken = console.post(
        "u_admin",
        at(TAKE_PATH, draft_id=body["draft_id"]),
        taking(body["suggestion"], "persona"),
    )

    assert taken.status_code == 200, taken.text
    assert len(console.memory.drafts[body["draft_id"]].revisions) == 2


def test_a_process_with_no_model_is_told_so_and_no_draft_is_made(console: Console) -> None:
    """Nothing to ask is refused before the draft is made, so a describe that cannot be answered
    leaves nothing in the person's list. Delete this and an install with no provider fills each
    builder's drafts with empty ones."""
    switched(console)
    use(console, None)
    console.app.state.models = None
    before = set(console.memory.drafts)

    answered = describe(console)

    assert answered.status_code == 409, answered.text
    assert answered.json()["outcome"] == UNAVAILABLE
    assert answered.json()["sentence"] == NO_MODEL_HERE
    assert set(console.memory.drafts) == before


def test_a_model_that_fails_leaves_a_draft_to_ask_again_and_says_why(console: Console) -> None:
    """The draft exists, the suggestion is null and the reason is the co-author's own sentence.
    Delete this and a failed call loses what the person wrote or hides that nothing came back."""
    switched(console)
    use(console, Scripted(refuse=True))

    answered = describe(console)

    assert answered.status_code == 201, answered.text
    body = answered.json()
    assert body["suggestion"] is None and body["told"] == NO_ANSWER_NOW
    assert body["draft_id"] in console.memory.drafts


def test_with_the_switch_off_the_route_is_the_one_404_and_calls_no_model(console: Console) -> None:
    """Off is absence, and nothing is sent to a provider. Delete this and the feature ships on.
    The same 404 a person who may not build gets, so the two cannot be told apart."""
    model = Scripted(text=reply(persona_change()))
    use(console, model)
    before = set(console.memory.drafts)

    off = describe(console)
    switched(console, False)
    still_off = describe(console)
    switched(console)
    may_not_build = describe(console, pid="u_wide")

    assert off.status_code == still_off.status_code == may_not_build.status_code == 404
    assert off.json()["message"] == still_off.json()["message"] == may_not_build.json()["message"]
    assert model.asked == [] and set(console.memory.drafts) == before


def test_a_blank_or_too_long_description_is_refused_and_makes_no_draft(console: Console) -> None:
    """A description past the limit is refused by the route's own validation and a request of only
    spaces by the co-author's rule, each before a draft exists. Delete this and either leaves an
    empty draft behind and costs a model call."""
    switched(console)
    model = Scripted(text=reply(persona_change()))
    use(console, model)
    before = set(console.memory.drafts)

    long = describe(console, "x" * (DESCRIPTION_CHARS + 1))
    blank = describe(console, "   ")

    assert long.status_code == 422
    assert blank.status_code == 409, blank.text
    assert blank.json()["outcome"] == REFUSED
    assert model.asked == [] and set(console.memory.drafts) == before


def test_the_drafts_page_says_whether_describing_would_be_answered(console: Console) -> None:
    """The page that decides whether to offer the card is told by the same question the route asks,
    so it is never drawn for a press the route would refuse. Delete this and New agent offers a
    control that answers with the one 404, or never offers one that works."""
    switched(console, False)
    off = console.get("u_admin", "/agent-drafts").json()["can_describe"]
    switched(console)
    on = console.get("u_admin", "/agent-drafts").json()["can_describe"]

    assert (off, on) == (False, True)
