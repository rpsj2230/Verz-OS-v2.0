"""The install acceptance check for the egress scrub: what a hosted model would be sent here.

One check, because the leaf is one path: the drivers the install builds at start
(`brain.ops.model_service.drivers_for`), handed the analyser this install's profile deploys
(`brain.ops.pii.analyzer_address` over its own settings), asked a question carrying a made-up
NRIC, email, number and name. The provider is the check's own recorded answerer, so nothing is sent
anywhere: what is read is the body the transport would have posted, and the answer it puts back.

**The analyser is the install's own, and it is really asked.** Where the profile deploys one, the
check calls it at its address with the check's made-up text, exactly as a question would, and an
English name that no rule can find has to leave as a placeholder. An analyser that does not
answer fails the check rather than passing it on the rules alone, because on such an install every
question's names are reaching the provider and the Install page is the one place that would say
so. Where the profile deploys none, the rules' scrub is what is checked, and the sentence says so.

**No socket to a provider is opened and no key is read.** The provider client is an
`httpx.MockTransport` that answers by echoing the placeholders it was sent, and the key is a
made-up string handed to the transport, never the install's.

Task ids: M32.2.2.1
"""

from __future__ import annotations

import asyncio
import json
import re
import secrets
from functools import partial
from typing import Final

import httpx

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 385

#: The hosted provider the check's question is put to. Any hosted one would do: the scrub is in the
#: one transport they all share.
PROVIDER: Final = "anthropic"

#: An English name no rule describes, which only the analyser can find. Common enough that a
#: model of names recognises it, and nobody's in particular.
ENGLISH_NAME: Final = "Michael Thompson"

#: Said where the install deploys an analyser and a name no rule finds would still have left.
ANALYSER_DID_NOT_FIND_A_NAME: Final = (
    "this install deploys a personal data analyser, and an English name no rule can find would "
    "have reached a hosted model: the analyser did not answer, or did not find it"
)

#: What the recorded provider reads placeholders with.
TOKENS: Final = re.compile(r"\[[a-z_]+_\d+\]")


def _made_up_values() -> dict[str, str]:
    """Values made up for one run, so the check scrubs nobody's."""
    from brain.ops.pii import nric_check_letter

    digits = "".join(str(secrets.randbelow(10)) for _ in range(7))
    return {
        "nric": f"S{digits}{nric_check_letter('S', digits)}",
        "email": f"acceptance.{secrets.token_hex(4)}@example.com",
        "phone": f"9{secrets.randbelow(10**3):03d} {secrets.randbelow(10**4):04d}",
        "patronymic": "Nur Aisyah binti Abdullah",
        "english": ENGLISH_NAME,
    }


@check(
    leaves=("M32.2.2.1",),
    sentence=(
        "A question carrying a made-up NRIC, email, number and names, put to a hosted model "
        "through the drivers this install builds, would leave with each value replaced by a "
        "placeholder, an English name included where the install deploys its analyser, and its "
        "answer comes back with the values put back; nothing is sent to any provider."
    ),
)
async def a_hosted_model_is_sent_placeholders_and_the_reader_the_values(h: Harness) -> None:
    from brain.models.driver import DriverMessage, DriverRequest, Role
    from brain.models.wire import http_transport
    from brain.ops.egress import analyser
    from brain.ops.model_service import drivers_for
    from brain.ops.pii import analyzer_address

    values = _made_up_values()
    posted: list[str] = []

    def provider(call: httpx.Request) -> httpx.Response:
        body = call.content.decode("utf-8")
        posted.append(body)
        echoed = " ".join(TOKENS.findall(body))
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": echoed}],
                "stop_reason": "end_turn",
                "usage": {},
            },
        )

    address = analyzer_address(h.settings.profile, h.settings.presidio_url)
    with (
        httpx.Client(transport=httpx.MockTransport(provider)) as recorded,
        httpx.Client(follow_redirects=False) as own,
    ):
        detector = analyser(address, own) if address else None
        # The install's own transport, handed a made-up key so none of the install's is read.
        transport = partial(http_transport, detector=detector, key=lambda: "acceptance")
        drivers = drivers_for(recorded, inference_address="", make_transport=transport)
        question = (
            f"Is {values['english']} ({values['nric']}, {values['email']}, {values['phone']}) "
            f"the same customer as {values['patronymic']}?"
        )
        request = DriverRequest(
            deployment_id=f"{PROVIDER}.acceptance",
            model="acceptance",
            messages=(
                DriverMessage(
                    role=Role.SYSTEM, content=f"The customer on file is {values['nric']}."
                ),
                DriverMessage(role=Role.USER, content=question),
            ),
            timeout_seconds=30.0,
        )
        answer = await asyncio.to_thread(drivers[PROVIDER].complete, request)

    if len(posted) != 1:
        raise CheckFailedError("the question was not posted once to the hosted provider")
    must_leave = [values[k] for k in ("nric", "email", "phone", "patronymic")]
    if detector is not None:
        if values["english"] in posted[0]:
            raise CheckFailedError(ANALYSER_DID_NOT_FIND_A_NAME)
        must_leave.append(values["english"])
    if any(value in posted[0] for value in must_leave):
        raise CheckFailedError("a value a hosted model would have been sent was not scrubbed")
    sent = json.loads(posted[0])
    if not TOKENS.search(json.dumps(sent)):
        raise CheckFailedError("a hosted model would have been sent no placeholder at all")
    if any(value not in answer.text for value in must_leave):
        raise CheckFailedError("the answer did not come back with its values put back")
