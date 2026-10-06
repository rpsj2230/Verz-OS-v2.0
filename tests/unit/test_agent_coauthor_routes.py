"""The co-author over HTTP: asking for changes to a draft, and taking the ones the author chooses.

Driven through the real application, signed in with the token machinery
`tests/fixtures/console_http.py` shares, with the builder tests' in-memory draft store and a model
that answers from a script put where `brain.agent_coauthor_routes.calls_of` looks first. So these
tests prove the routes' decisions: who is refused with the one 404 and without a model call, what a
reply that is not a proposal is told, that asking writes nothing and taking writes exactly one
revision of exactly the named changes, and that a proposal edited on its way back changes nothing it
was not shown. The domain's own rules are `tests/unit/test_builder_coauthor.py`.

Task ids: M20.1.3
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from brain.agent_builder_routes import (
    ALREADY_PUBLISHED,
    CHECK_PATH,
    DRAFTS_PATH,
    MOVED,
    PUBLISH_PATH,
    REFUSED,
)
from brain.agent_coauthor_routes import (
    A_SUGGESTION_IS_NOT_A_CHANGE_UNTIL_ITS_AUTHOR_TAKES_IT,
    NO_ANSWER_NOW,
    NO_MODEL_HERE,
    SUGGEST_PATH,
    TAKE_PATH,
    calls_of,
)
from brain.builder.coauthor import ASK_CHARS
from brain.core.lane import Lane
from brain.models.disclosure import DataCategory
from brain.models.driver import (
    DriverFailure,
    DriverMessage,
    DriverResponse,
    ProviderUnavailable,
    TokenUsage,
)
from brain.models.metering import Meter
from brain.models.routing import Tier
from tests.unit.test_agent_builder_routes import (
    PERSONA,
    Console,
    a_document,
    at,
    not_changed,
    reaching_nothing,
    ready,
    saved,
    started,
)
from tests.unit.test_agent_builder_routes import (
    console as console,
)

NEWER = "Answer in one short sentence and name the invoice you read."


def reply(*changes: dict[str, Any]) -> str:
    return json.dumps({"changes": list(changes)})


@dataclass
class Scripted:
    """An executor that answers from a script, and remembers what it was asked and under what."""

    text: str = ""
    refuse: bool = False
    asked: list[dict[str, Any]] = field(default_factory=list)

    async def complete(
        self,
        messages: tuple[DriverMessage, ...],
        *,
        lane: Lane,
        meter: Meter,
        trace_id: str,
        tier: Tier | None = None,
        max_output_tokens: int | None = None,
        categories: tuple[DataCategory, ...] = (),
    ) -> DriverResponse:
        self.asked.append(
            {"messages": messages, "lane": lane, "tier": tier, "categories": categories}
        )
        if self.refuse:
            raise ProviderUnavailable(DriverFailure(deployment_id="d", status=503))
        return DriverResponse(
            deployment_id="d",
            model="m",
            text=self.text,
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            finish_reason="stop",
        )


def use(console_: Console, model: Scripted | None) -> None:
    console_.app.state.coauthor_calls = model


def ask(console_: Console, draft_id: str, revision: int, words: str = "make it shorter") -> Any:
    return console_.post(
        "u_admin", at(SUGGEST_PATH, draft_id=draft_id), {"revision": revision, "ask": words}
    )


def revisions(console_: Console, draft_id: str) -> int:
    return len(console_.memory.drafts[draft_id].revisions)


def persona_change(value: str = NEWER) -> dict[str, Any]:
    return {"path": "persona", "value": value}


def taking(proposal: dict[str, Any], *paths: str, **extra: Any) -> dict[str, Any]:
    """The body a page sends back: the proposal as drawn, and the paths taken."""
    return {
        "revision": proposal["revision"],
        "base_digest": proposal["base_digest"],
        "hunks": [
            {"path": one["path"], "before": one["before"], "after": one["after"]}
            for one in proposal["hunks"]
        ],
        "take": list(paths),
        **extra,
    }


# ------------------------------------------------------------------------------ asking
def test_asking_proposes_changes_in_the_forms_words_and_writes_nothing(console: Console) -> None:
    """The proposal names the path, where the form shows it, and the value before and after as JSON
    text; nothing reaches the draft; the model is asked under the draft category on the main tier,
    with the author's request and draft as its messages.

    Delete this and the co-author cannot be seen, or a suggestion arrives in the draft by being
    asked for, or the call is sent under a category that says nothing left for the provider."""
    draft_id, revision = ready(console, a_document())
    model = Scripted(reply(persona_change()))
    use(console, model)
    response = ask(console, draft_id, revision, "shorten the instructions")

    assert response.status_code == 200, response.text
    body = response.json()
    [hunk] = body["hunks"]
    assert (hunk["path"], hunk["where"]) == ("persona", "Instructions")
    assert json.loads(hunk["before"]) == PERSONA and json.loads(hunk["after"]) == NEWER
    assert body["revision"] == revision and body["dropped"] == []
    assert body["note"] == A_SUGGESTION_IS_NOT_A_CHANGE_UNTIL_ITS_AUTHOR_TAKES_IT
    assert revisions(console, draft_id) == revision
    [made] = model.asked
    assert made["categories"] == (DataCategory.AGENT_DRAFT,)
    assert (made["tier"], made["lane"]) == (Tier.MAIN, Lane.ANSWER)
    carried = " ".join(one.content for one in made["messages"])
    assert "shorten the instructions" in carried and PERSONA in carried


def test_a_reach_path_the_co_author_names_is_dropped_with_words_and_never_proposed(
    console: Console,
) -> None:
    """A change to the capabilities, the leash and the sealed identity is in `dropped` with its
    reason and not in `hunks`, beside a good change to the persona that is.

    Delete this and a draft that told the co-author to widen an agent could be widened by the
    suggestion a person then took."""
    draft_id, revision = ready(console, a_document())
    use(
        console,
        Scripted(
            reply(
                persona_change(),
                {"path": "authority.capabilities", "value": [{"value": "read:everything"}]},
                {"path": "guardrails.leash", "value": []},
            )
        ),
    )
    body = ask(console, draft_id, revision).json()

    assert [one["path"] for one in body["hunks"]] == ["persona"]
    assert {one["path"] for one in body["dropped"]} == {
        "authority.capabilities",
        "guardrails.leash",
    }
    assert all(one["message"] for one in body["dropped"])


def test_a_reply_that_is_not_a_proposal_is_refused_in_words_and_nothing_changes(
    console: Console,
) -> None:
    """A reply that is not JSON is a 409 with the domain's own sentence; the draft is unchanged.

    Delete this and a model that rambles is drawn as a proposal, or as a server error."""
    draft_id, revision = ready(console, a_document())
    use(console, Scripted("sorry, I cannot do that"))
    refused = ask(console, draft_id, revision)

    status, outcome, sentence = not_changed(refused)
    assert (status, outcome) == (409, REFUSED)
    assert "could not be read as a proposal" in sentence
    assert revisions(console, draft_id) == revision


def test_nothing_is_asked_of_a_model_for_somebody_elses_draft_a_blank_request_or_a_stale_page(
    console: Console,
) -> None:
    """A stranger's draft and a draft that does not exist are one 404 with no model call; a blank
    request and an overlong one are refused before one; a revision that is not the latest is told
    it moved; and a published draft cannot be asked about.

    Delete this and asking is a way to learn whether a draft exists, or every refusal costs a
    model call."""
    draft_id, revision = ready(console, a_document())
    model = Scripted(reply(persona_change()))
    use(console, model)

    stranger = console.post(
        "u_prefix", at(SUGGEST_PATH, draft_id=draft_id), {"revision": 1, "ask": "x"}
    )
    missing = console.post(
        "u_admin", at(SUGGEST_PATH, draft_id="nope"), {"revision": 1, "ask": "x"}
    )
    blank = ask(console, draft_id, revision, "   ")
    long = console.post(
        "u_admin",
        at(SUGGEST_PATH, draft_id=draft_id),
        {"revision": revision, "ask": "x" * (ASK_CHARS + 1)},
    )
    stale = ask(console, draft_id, revision + 1)

    assert stranger.status_code == missing.status_code == 404
    assert stranger.json()["message"] == missing.json()["message"]
    assert not_changed(blank)[:2] == (409, REFUSED)
    assert long.status_code == 422
    assert not_changed(stale)[:2] == (409, MOVED)
    assert model.asked == []


def test_a_process_with_no_model_and_a_ladder_that_cannot_answer_say_so_and_change_nothing(
    console: Console,
) -> None:
    """With no executor the answer says no model is set up; with one whose providers all fail the
    answer says it could not be reached; the draft is unchanged in both, and a working executor is
    asked afterwards, so neither answer was a lasting state.

    Delete this and an install with no provider shows a server error where a sentence belongs."""
    draft_id, revision = ready(console, a_document())
    use(console, None)
    console.app.state.models = None
    assert calls_of(_request(console)) is None
    nothing = ask(console, draft_id, revision)
    assert not_changed(nothing) == (409, "unavailable", NO_MODEL_HERE)

    use(console, Scripted(refuse=True))
    down = ask(console, draft_id, revision)
    assert not_changed(down) == (409, "unavailable", NO_ANSWER_NOW)
    assert revisions(console, draft_id) == revision

    use(console, Scripted(reply(persona_change())))
    assert ask(console, draft_id, revision).status_code == 200


def _request(console_: Console) -> Any:
    from starlette.requests import Request

    return Request({"type": "http", "app": console_.app, "headers": [], "method": "POST"})


# ------------------------------------------------------------------------------ taking
def test_taking_a_change_saves_exactly_that_change_as_the_next_revision_and_rejects_the_rest(
    console: Console,
) -> None:
    """Of two proposed changes the author takes one: a new revision holds the new persona and the
    old summary, the revision number moves by one, the page is told what is left to check, and the
    other change was never written.

    Delete this and taking is all-or-nothing, or writes what was not named."""
    draft_id, revision = ready(console, a_document())
    use(
        console,
        Scripted(
            reply(
                persona_change(),
                {"path": "identity.summary", "value": "Reads invoices for the finance team."},
            )
        ),
    )
    proposal = ask(console, draft_id, revision).json()
    took = console.post("u_admin", at(TAKE_PATH, draft_id=draft_id), taking(proposal, "persona"))

    assert took.status_code == 200, took.text
    assert took.json()["revision"] == revision + 1
    kept = json.loads(console.memory.drafts[draft_id].revisions[-1].body)
    assert kept["persona"] == NEWER
    assert kept["identity"].get("summary") != "Reads invoices for the finance team."
    assert revisions(console, draft_id) == revision + 1
    # The new revision is the latest, so the old check no longer stands for it.
    assert (
        console.post(
            "u_admin", at(CHECK_PATH, draft_id=draft_id), {"revision": revision}
        ).status_code
        == 409
    )


def test_a_proposal_edited_on_its_way_back_changes_nothing_it_was_not_shown(
    console: Console,
) -> None:
    """A page that sends a change to a path the co-author may not write, a before that is not what
    the draft holds, a digest that is not the revision's, or a path the proposal never held, is
    refused, and the draft is still the revision it was.

    Delete this and the take route is a way to write anything a request can spell."""
    draft_id, revision = ready(console, a_document())
    use(console, Scripted(reply(persona_change())))
    proposal = ask(console, draft_id, revision).json()
    path = at(TAKE_PATH, draft_id=draft_id)

    smuggled = taking(proposal, "persona")
    smuggled["hunks"].append({"path": "guardrails.leash", "before": None, "after": "[]"})
    wrong_before = taking(proposal, "persona")
    wrong_before["hunks"][0]["before"] = json.dumps("something the draft never held")
    wrong_digest = taking(proposal, "persona", base_digest="0" * 64)
    unknown = taking(proposal, "tier")

    for body in (smuggled, wrong_before, wrong_digest, unknown):
        refused = console.post("u_admin", path, body)
        assert refused.status_code == 409, body
    assert revisions(console, draft_id) == revision


def test_a_proposal_the_draft_moved_past_is_refused_and_a_retry_that_landed_is_one_revision(
    console: Console,
) -> None:
    """After the author saves a different revision, taking the old proposal is told it moved; and
    taking the same changes twice returns the revision the first wrote rather than a second one.

    Delete this and a suggestion made for last hour's draft overwrites this hour's, or a retry
    after a timeout writes the same change twice."""
    draft_id, revision = ready(console, a_document())
    use(console, Scripted(reply(persona_change())))
    proposal = ask(console, draft_id, revision).json()
    body = taking(proposal, "persona")
    path = at(TAKE_PATH, draft_id=draft_id)

    first = console.post("u_admin", path, body)
    again = console.post("u_admin", path, body)
    assert first.status_code == again.status_code == 200
    assert first.json()["revision"] == again.json()["revision"] == revision + 1
    assert revisions(console, draft_id) == revision + 1

    other_id, other_revision = ready(console, a_document("anything_else"))
    use(console, Scripted(reply(persona_change())))
    old = ask(console, other_id, other_revision).json()
    draft = console.get("u_admin", f"{DRAFTS_PATH}/{other_id}").json()
    document = {**draft["document"], "persona": "Typed in the meantime."}
    assert (
        saved(console, {"draft_id": other_id, "revision": other_revision}, document)
        == other_revision + 1
    )
    late = console.post("u_admin", at(TAKE_PATH, draft_id=other_id), taking(old, "persona"))
    assert not_changed(late)[:2] == (409, MOVED)


def test_somebody_elses_draft_cannot_have_changes_taken_into_it(console: Console) -> None:
    """The author's proposal sent by a second builder is the one 404, and the draft is unchanged.

    Delete this and a proposal is a way to write into a draft that is not yours."""
    draft_id, revision = ready(console, a_document())
    use(console, Scripted(reply(persona_change())))
    proposal = ask(console, draft_id, revision).json()
    stranger = console.post(
        "u_prefix", at(TAKE_PATH, draft_id=draft_id), taking(proposal, "persona")
    )
    assert stranger.status_code == 404
    assert revisions(console, draft_id) == revision


@pytest.mark.parametrize("who", ["u_none", "u_wide"])
def test_somebody_who_may_not_build_is_told_nothing_exists(console: Console, who: str) -> None:
    """A caller without the builder's capability is the one 404 on both routes, with no model call.

    Delete this and the co-author is open to somebody who may not make an agent."""
    draft = started(console)
    model = Scripted(reply(persona_change()))
    use(console, model)
    asked = console.post(
        who, at(SUGGEST_PATH, draft_id=draft["draft_id"]), {"revision": 1, "ask": "x"}
    )
    took = console.post(
        who,
        at(TAKE_PATH, draft_id=draft["draft_id"]),
        {"revision": 1, "base_digest": "x", "hunks": [], "take": ["persona"]},
    )
    assert (asked.status_code, took.status_code) == (404, 404)
    assert model.asked == []


def test_a_published_draft_is_not_asked_about_and_takes_no_changes(console: Console) -> None:
    """After the draft is published, asking and taking are each told it is published, with no model
    call and no new revision.

    Delete this and a suggestion can be written into a draft whose agent already exists, which is
    a change nothing will ever publish and a person will think they made."""
    draft_id, revision = ready(console, reaching_nothing())
    published = console.post("u_admin", at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})
    assert published.status_code == 201
    model = Scripted(reply(persona_change()))
    use(console, model)

    asked = ask(console, draft_id, revision)
    took = console.post(
        "u_admin",
        at(TAKE_PATH, draft_id=draft_id),
        {"revision": revision, "base_digest": "x", "hunks": [], "take": ["persona"]},
    )

    assert not_changed(asked) == (409, REFUSED, ALREADY_PUBLISHED)
    assert not_changed(took) == (409, REFUSED, ALREADY_PUBLISHED)
    assert model.asked == [] and revisions(console, draft_id) == revision
