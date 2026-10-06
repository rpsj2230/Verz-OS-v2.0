"""The install acceptance check for the co-author: it proposes through the install's own executor,
and nothing changes in the draft until its author takes a change.

`brain.agent_coauthor_routes` is asked, as a reserved builder of acceptance_a, through its own
route functions, the way the console does. The model is the executor the install built, with a
stand-in answering where a provider would, in the documented chat completions shape: which words
the draft ends with is what is held, and a stand-in answering after the transport is the product's
own adapter and executor, as
`brain.ops.acceptance_routing.A_FAILURE_SHAPE_IS_ANSWERED_IN_THE_PROCESS` argues. An install
keeping text on its own hardware plans no stand-in, so there the check says it was not run. The
template signing key is the check's own, for the reason
`brain.ops.acceptance_checks_templates.THE_WORKER_HOLDS_NO_SIGNING_KEY` gives, and everything is
written inside the check's transaction and rolled back.

**What it holds, in order.** Asking returns a change to the persona and one to the summary, each
as before and after, and writes no revision; a reply naming a path the co-author may not write
(what an agent may reach) is dropped with its sentence and never proposed; taking the persona
alone writes one revision whose persona is the proposed words and whose summary is what the author
had; and a proposal altered on its way back, naming a path the co-author may not write, is refused
and writes nothing.

Task ids: M20.1.3
"""

from __future__ import annotations

import json
import secrets
from typing import Any, Final, cast

from sqlalchemy import select

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_builder import _builder, _document, _draft, _saved_and_checked
from brain.ops.acceptance_checks_templates import _asking, _gallery, _request
from brain.ops.acceptance_models import STAND_IN
from brain.ops.acceptance_routing import ANSWERS, StandIns, stand_in_drivers, step
from brain.ops.acceptance_run import Harness

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 403

NOT_PROPOSED: Final = "the co-author's answer was not shown as changes to the draft"
WROTE_BY_ASKING: Final = "asking the co-author wrote a revision of the draft"
REACH_PROPOSED: Final = "a change to what an agent may reach was proposed to its author"
NOT_TAKEN: Final = "the change an author took did not become the next revision"
TOOK_MORE: Final = "a change the author did not take reached the draft"
ALTERED_TAKEN: Final = "a proposal altered on its way back changed the draft"

#: The persona the draft starts with, and the words the stand-in proposes in its place.
BEFORE: Final = "Answers an install acceptance check about the knowledge library and nobody else."
AFTER: Final = "Answers an install acceptance check in one short sentence."
SUMMARY: Final = "Reads the library for an acceptance check."


class CoauthorStandIn(StandIns):
    """The stand-in provider, answering the co-author's one call with a proposal.

    Everything else is `StandIns`: the host and the model are read and counted, and a model named
    for a failure shape fails as it does for the routing checks. Only the words an answering model
    says differ, because the co-author reads its reply as JSON and the routing checks read prose.
    """

    def __call__(self, request: Any) -> Any:
        import httpx

        response: httpx.Response = super().__call__(request)
        if response.status_code != 200:
            return response
        body = json.loads(response.content)
        body["choices"][0]["message"]["content"] = json.dumps(
            {
                "changes": [
                    {"path": "persona", "value": AFTER},
                    {"path": "identity.summary", "value": SUMMARY},
                    {"path": "authority.capabilities", "value": [{"value": "read:everything"}]},
                ]
            }
        )
        return httpx.Response(200, json=body)


def _body(answered: Any) -> dict[str, Any]:
    """A route's JSON body, whichever way it answered."""
    if hasattr(answered, "body"):
        return cast(dict[str, Any], json.loads(bytes(answered.body)))
    return cast(dict[str, Any], answered.model_dump(mode="json"))


async def _revisions(h: Harness, draft_id: str) -> list[dict[str, Any]]:
    """Every revision body the draft holds, oldest first."""
    import uuid

    from brain.tables.manifest_draft import ManifestRevisionRow

    rows = (
        await h.execute(
            select(ManifestRevisionRow.body)
            .where(ManifestRevisionRow.draft_id == uuid.UUID(draft_id))
            .order_by(ManifestRevisionRow.number)
        )
    ).scalars()
    return [one if isinstance(one, dict) else json.loads(one) for one in rows]


@check(
    leaves=("M20.1.3",),
    sentence=(
        "A builder of acceptance_a asks the co-author, through the install's own executor, to "
        "change a draft: it proposes the persona and the summary as before and after, drops a "
        "change to what an agent may reach, and writes nothing; taking the persona alone writes "
        "one revision holding it and not the summary; a proposal altered to carry a reach "
        "change is refused."
    ),
)
async def the_coauthor_proposes_and_nothing_changes_until_taken(
    h: Harness,
) -> None:
    """The routes read the request's trace id from the logging context, so the check binds its own
    for the length of the run and leaves nothing bound after it."""
    import structlog

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        await _held(h)


async def _held(h: Harness) -> None:
    from brain.agent_coauthor_routes import (
        HunkSent,
        SuggestionAsked,
        SuggestionTaken,
        suggest_changes,
        take_suggestions,
    )
    from brain.models.routing import DEFAULT_TIER
    from brain.ops.acceptance_models import askable, models_for, pinned
    from brain.ops.acceptance_routing import constrained

    await h.found_departments()
    await constrained(h, ())
    responder = CoauthorStandIn()
    models = await models_for(h, standing=stand_in_drivers(h, responder))
    askable(await models.calls.planned(), STAND_IN)
    await pinned(h, (step(ANSWERS, tier=DEFAULT_TIER),))

    builder = await _builder(h, "coauthor")
    app = _gallery(h, secrets.token_hex(32))
    app.state.models = models
    asking = await _asking(h, builder)
    draft = await _draft(h, app, builder)
    agent_id = str(draft["agent_id"])
    revision = await _saved_and_checked(h, app, builder, draft, _document(agent_id, persona=BEFORE))
    held = await _revisions(h, str(draft["draft_id"]))

    proposed = _body(
        await suggest_changes(
            _request(app),
            draft["draft_id"],
            SuggestionAsked(revision=revision, ask="say it in one short sentence"),
            asking,
        )
    )
    if {one["path"] for one in proposed.get("hunks", [])} != {"persona", "identity.summary"}:
        raise CheckFailedError(NOT_PROPOSED)
    if "authority.capabilities" in {one["path"] for one in proposed["hunks"]}:
        raise CheckFailedError(REACH_PROPOSED)
    if not any(one["path"] == "authority.capabilities" for one in proposed["dropped"]):
        raise CheckFailedError(REACH_PROPOSED)
    if len(await _revisions(h, str(draft["draft_id"]))) != len(held):
        raise CheckFailedError(WROTE_BY_ASKING)

    altered = [
        *(
            {"path": one["path"], "before": one["before"], "after": one["after"]}
            for one in proposed["hunks"]
        ),
        {"path": "guardrails.leash", "before": None, "after": "[]"},
    ]
    try:
        refused = await take_suggestions(
            _request(app),
            draft["draft_id"],
            SuggestionTaken(
                revision=proposed["revision"],
                base_digest=proposed["base_digest"],
                hunks=[HunkSent(**one) for one in altered],
                take=["persona"],
            ),
            asking,
        )
        status = refused.status_code
    except Exception:
        status = 409
    if status == 200 or len(await _revisions(h, str(draft["draft_id"]))) != len(held):
        raise CheckFailedError(ALTERED_TAKEN)

    taken = await take_suggestions(
        _request(app),
        draft["draft_id"],
        SuggestionTaken(
            revision=proposed["revision"],
            base_digest=proposed["base_digest"],
            hunks=[
                HunkSent(path=one["path"], before=one["before"], after=one["after"])
                for one in proposed["hunks"]
            ],
            take=["persona"],
        ),
        asking,
    )
    after = await _revisions(h, str(draft["draft_id"]))
    if taken.status_code != 200 or len(after) != len(held) + 1:
        raise CheckFailedError(NOT_TAKEN)
    newest = after[-1]
    if newest.get("persona") != AFTER:
        raise CheckFailedError(NOT_TAKEN)
    if newest.get("identity", {}).get("summary") == SUMMARY:
        raise CheckFailedError(TOOK_MORE)
