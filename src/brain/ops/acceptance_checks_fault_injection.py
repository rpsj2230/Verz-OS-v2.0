"""Install acceptance checks for a provider that answers badly: a 429 is walked past and is not
ill health, and a reply that is not a completion stops the chain with a stated reason.

`brain.ops.acceptance_routing` proves the closed trigger set with a 404, a 503, a content refusal
and a refused connection. M30.4.4 asks for the two it does not inject: **a rate limit** and **a
malformed response**, through the real answer route on the install. Each runs the whole path a
person's question takes, the upload, the passage search, the answer lane, the executor planning from
the ladder in the database, the attempt rows and the request row, inside the check's one
rolled-back transaction.

**The failure shapes are answered in the process, by the same kind of stand-in as the routing
checks.** The product's own transport over an `httpx.MockTransport`, at an address under `.invalid`,
so nothing leaves the server. A real provider cannot be made to rate-limit or to send rubbish on the
day a deploy is checked, and asking one to would spend money to prove one shape of five.

**What a 429 must do.** Move the question to the next step and answer it, count one fallback, and be
recorded as a rate limit. And **it must not open the step's breaker**, however many questions it
limits in a row, because a limit is a fact about the caller's volume and not about the provider's
health: a breaker opened by limits takes a working provider out of rotation for the burst that
limited it. Three limited questions in a row is the breaker's own threshold, so three is the count
asked.

**What a malformed reply must do.** A reply that is not a completion (a body that is not JSON, a
JSON body with no choices) is not in the closed set, which is the property
`brain.models.routing.QUALITY_FALLBACK_REJECTED` protects: the next step would receive the same
request and the chain would be spending money to shop for a reply that parses. So the chain stops
at that step, the next step is never sent the question, the attempt is recorded as stopped, and the
asker is told what was found and that no answer was composed, which is the abstention the answer
lane already gives when it retrieved and could not answer.

Task ids: M30.4.4
"""

from __future__ import annotations

import json
from typing import Final

import httpx

from brain.models.evidence import OK, STOPPED
from brain.models.routing import DEFAULT_TIER, BreakerState, FallbackTrigger
from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_models import STAND_IN, STAND_IN_ADDRESS, pinned, trace_of
from brain.ops.acceptance_routing import (
    ANSWERS,
    StandIns,
    answered,
    asking,
    breaker_state,
    request_of,
    standing_by,
    step,
    walked,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2324

#: What each stand-in model does, by the model name its step asks for.
RATE_LIMITED: Final = "rate-limited"
NOT_JSON: Final = "not-json"
NO_CHOICES: Final = "no-choices"

#: The attempt outcome a rate limit is recorded as.
RATE_LIMITED_OUTCOME: Final = FallbackTrigger.RATE_LIMITED.value

#: The 429 body, in the chat completions shape OpenAI documents for its error object.
LIMIT_BODY: Final = {
    "error": {
        "message": "Rate limit reached for requests",
        "type": "requests",
        "param": None,
        "code": "rate_limit_exceeded",
    }
}

#: How many limited questions in a row the breaker's own threshold counts.
LIMITED_IN_A_ROW: Final = 3


class FaultStandIns(StandIns):
    """`StandIns` that also rate-limits and sends rubbish, by the model a request names."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        model = str(json.loads(request.content).get("model", ""))
        if model == RATE_LIMITED:
            self.asked[(request.url.host, model)] += 1
            return httpx.Response(429, json=LIMIT_BODY, headers={"retry-after": "1"})
        if model == NOT_JSON:
            self.asked[(request.url.host, model)] += 1
            return httpx.Response(200, content=b"<html>not a completion</html>")
        if model == NO_CHOICES:
            self.asked[(request.url.host, model)] += 1
            return httpx.Response(200, json={"id": "chatcmpl-acceptance", "choices": []})
        return super().__call__(request)


# -------------------------------------------------------------- 1. a rate limit (M30.4.4)
@check(
    leaves=("M30.4.4",),
    sentence=(
        "Behind a step answering 429, a question from a member of acceptance_a is answered by the "
        "next step with one fallback, the limit is recorded as a rate limit, and three limited "
        "questions in a row leave the step's breaker closed."
    ),
)
async def a_rate_limit_is_walked_past_and_does_not_open_the_breaker(h: Harness) -> None:
    s = await standing_by(h, responder=FaultStandIns())
    await pinned(h, (step(RATE_LIMITED), step(ANSWERS)))
    limited = step(RATE_LIMITED).deployment_id
    for n in range(1, LIMITED_IN_A_ROW + 1):
        one = await asking(h, s.app, s.reader, s.paired.question, n)
        row = await request_of(h, trace_of(h, n))
        if not answered(one):
            raise CheckFailedError("a question behind a rate-limited step was not answered")
        if row.get("fallback_count") != 1:
            raise CheckFailedError("a rate limit was not counted as one fallback")
        if [x[1:3] for x in await walked(h, trace_of(h, n))] != [
            (RATE_LIMITED, RATE_LIMITED_OUTCOME),
            (ANSWERS, OK),
        ]:
            raise CheckFailedError("a rate limit was not recorded as a rate limit")
    if await breaker_state(s.models, limited, h.now) != BreakerState.CLOSED.value:
        raise CheckFailedError("three rate limits in a row opened the step's breaker")


# ------------------------------------------------------- 2. a malformed reply (M30.4.4)
@check(
    leaves=("M30.4.4",),
    sentence=(
        "Behind a step whose reply is not JSON the chain stops at that step and the asker is told "
        "no model could be reached; behind one whose reply has no choices the asker is told what "
        "was found and that no answer was composed; in neither is the next step sent the question."
    ),
)
async def a_reply_that_is_not_a_completion_is_not_shopped_to_another_step(h: Harness) -> None:
    from brain.gate.abstain import AbstentionReason
    from brain.gate.answer import Answered
    from brain.models.driver import ProviderUnavailable

    s = await standing_by(h, responder=FaultStandIns())
    await pinned(h, (step(NOT_JSON), step(ANSWERS)))
    stopped = await asking(h, s.app, s.reader, s.paired.question, 1)
    if not isinstance(stopped, ProviderUnavailable):
        raise CheckFailedError("a reply that was not JSON was not told as a stop")
    if await walked(h, trace_of(h, 1)) != [(STAND_IN, NOT_JSON, STOPPED, DEFAULT_TIER)]:
        raise CheckFailedError("a reply that was not JSON did not stop at its step")
    await pinned(h, (step(NO_CHOICES), step(ANSWERS)))
    empty = await asking(h, s.app, s.reader, s.paired.question, 2)
    if (
        not isinstance(empty, Answered)
        or empty.composed is not None
        or empty.abstention is None
        or empty.abstention.reason is not AbstentionReason.RETRIEVED_BUT_NOT_ANSWERING
    ):
        raise CheckFailedError("a reply with no choices was not told as an answer not composed")
    if await walked(h, trace_of(h, 2)) != [(STAND_IN, NO_CHOICES, OK, DEFAULT_TIER)]:
        raise CheckFailedError("a reply with no choices was tried on another step")
    if s.responder.sent_to(STAND_IN_ADDRESS, ANSWERS):
        raise CheckFailedError("the step behind a malformed reply was sent the question")
