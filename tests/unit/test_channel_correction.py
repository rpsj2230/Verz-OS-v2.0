"""A wrong answer can be corrected from every channel adapter, and no outcome travels back.

The adapters are the ones `tests/invariants/test_channel_adapter_invariants.py` discovers, not
a list written here, so an adapter added tomorrow is in scope by existing. Each one is proved
twice: the correction line goes out through its own `send`, and a correction typed into it
comes back through its own `normalise` and is read.

Task ids: M34.2.2.1
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.channels.cards import CardRefusedError, render_body
from brain.channels.correction import (
    CORRECTION_ACKNOWLEDGEMENT,
    AnswerOnFile,
    CorrectionError,
    CorrectionRequest,
    acknowledge,
    correction_line,
    file_correction,
    read_correction,
    send_with_correction,
)
from brain.channels.email import Authentication, EmailAdapter, InboundEmail
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.redaction import OPAQUE_LABEL, ChannelPayload
from brain.core.scope import Scope
from brain.gate.compose import new_trace_ref
from brain.gate.context import Channel
from brain.gate.ingress import ChannelEvent
from brain.ops.feedback import FLAG_CAPABILITY, FlagReason
from tests.invariants.test_channel_adapter_invariants import ADAPTERS
from tests.unit import test_lark_channel as lark_fixtures
from tests.unit import test_slack as slack_fixtures
from tests.unit import test_teams as teams_fixtures
from tests.unit import test_telegram as telegram_fixtures

#: Far from any wall clock. The vendor fixtures carry their own instants for token checks.
AT = datetime(2099, 1, 1, tzinfo=UTC)
REF = new_trace_ref()
PAYLOAD = ChannelPayload(records=({"invoice": "INV-1"},))
SENDER = "someone@client.example"


def _lark(line: str) -> object:
    return lark_fixtures._raw(text=f"@_user_1 {line}", mentions=[lark_fixtures._mention_json()])


def _slack(line: str) -> object:
    return slack_fixtures._raw(text=f"<@U0BRAINBOT> {line}")


def _teams(line: str) -> object:
    return teams_fixtures._verified(text=f"<at>Brain</at> {line}")


def _telegram(line: str) -> object:
    return telegram_fixtures._verified(telegram_fixtures._update(text=line))


def _whatsapp(line: str) -> object:
    message = {
        "id": "wamid.1",
        "from": "+6500000000",
        "timestamp": "1757160000",
        "type": "text",
        "text": {"body": line},
    }
    return {"entry": [{"changes": [{"value": {"messages": [message]}}]}]}


def _email(line: str) -> object:
    # The reply quotes the answer, and the answer carried the offer naming every reason.
    return InboundEmail(
        message_id="<reply@mail.example>",
        from_header=SENDER,
        subject="Re: your answer",
        body=f"{line}\n\n> {correction_line(REF)}",
        received_at=AT,
        authentication=Authentication.PASSED,
        headers={},
    )


#: How a person types a line into each surface, by the module the adapter lives in.
INBOUND: dict[str, Callable[[str], object]] = {
    "lark": _lark,
    "slack": _slack,
    "teams": _teams,
    "telegram": _telegram,
    "whatsapp": _whatsapp,
    "email": _email,
}


def _event(text: str) -> ChannelEvent:
    return ChannelEvent(
        channel=Channel.SLACK,
        external_id="m_1",
        channel_identity="U0ASKER",
        text=text,
        received_at=AT,
    )


def _lead(department: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_lead",
        grants=(Grant(capability=FLAG_CAPABILITY, scope=Scope.department(department)),),
    )


def _request(reason: FlagReason = FlagReason.WRONG_SOURCES) -> CorrectionRequest:
    read = read_correction(_event(f"{reason.value} {REF}"))
    assert read is not None
    return read


# ------------------------------------------------------------ every adapter carries it


def test_every_adapter_discovered_has_an_inbound_fixture_here() -> None:
    """**The guard on the parametrised tests below.** They iterate the discovered adapters and
    look each one's fixture up here, so an adapter with no fixture would fail with a KeyError
    rather than a sentence, and one discovered under a new name would be skipped nowhere.

    Delete this and "every channel" becomes "the six channels somebody remembered"."""
    assert {module for module, _ in ADAPTERS} == set(INBOUND)


@pytest.mark.parametrize(("module", "cls"), ADAPTERS, ids=lambda v: getattr(v, "__name__", v))
def test_an_answer_sent_through_every_adapter_carries_the_correction_line(
    module: str, cls: type[Any]
) -> None:
    """**The outbound half of the leaf, per adapter.** The line reaches what that adapter
    actually delivers, under the answer rather than instead of it.

    Delete this and an adapter whose `send` ignores `body` delivers answers nobody can
    correct from where they read them, while the protocol says otherwise."""
    del module
    adapter = cls()

    send_with_correction(adapter, PAYLOAD, to="recipient_1", trace_ref=REF)

    delivered = adapter.sent[-1].body
    assert delivered.startswith(render_body(PAYLOAD))
    assert delivered.endswith(correction_line(REF))


@pytest.mark.parametrize(("module", "cls"), ADAPTERS, ids=lambda v: getattr(v, "__name__", v))
def test_no_adapter_lets_a_composed_body_drop_the_payloads_label(
    module: str, cls: type[Any]
) -> None:
    """**The price of putting `body` in the protocol.** A body composed by a caller is a body
    that can leave out the label saying nobody checked this payload, so every adapter asks
    the produced string, and a body that dropped it is refused rather than delivered.

    Delete this and the adapter that gained `body` for this leaf can deliver the opaque
    escape hatch as an ordinary answer, which is the one thing M10.1.5 exists to prevent."""
    del module
    adapter = cls()
    labelled = ChannelPayload(records=({"invoice": "INV-1"},), label=OPAQUE_LABEL)

    with pytest.raises(CardRefusedError):
        adapter.send(labelled, to="recipient_1", body="an answer with no label on it")
    assert adapter.sent == []

    send_with_correction(adapter, labelled, to="recipient_1", trace_ref=REF)
    assert OPAQUE_LABEL in adapter.sent[-1].body


@pytest.mark.parametrize(("module", "cls"), ADAPTERS, ids=lambda v: getattr(v, "__name__", v))
@pytest.mark.parametrize("reason", list(FlagReason), ids=lambda r: r.value)
def test_a_correction_typed_into_every_adapter_is_read_back_off_its_event(
    module: str, cls: type[Any], reason: FlagReason
) -> None:
    """**The inbound half of the leaf, per adapter and per reason.** What the surface puts in
    front of a typed line, a Lark placeholder, a Slack or Teams mention, an email's quoted
    offer below it, does not stop it being read.

    Delete this and a correction can be offered on a surface whose normaliser changes the
    line into something the reader no longer recognises."""
    adapter = cls()

    request = read_correction(adapter.normalise(INBOUND[module](f"{reason.value} {REF}")))

    assert request is not None, f"{module} lost a {reason.value} correction on the way in"
    assert request.reason is reason
    assert request.trace_ref == REF
    assert request.channel is adapter.capabilities().channel


# ------------------------------------------------------------ what a correction may be


def test_the_offer_names_every_reason_and_the_reference_and_is_not_itself_a_correction() -> None:
    """The line a person reads lists the whole vocabulary, so wrong sources is a choice they
    are shown. Read back as a message, the offer is not a correction somebody made.

    Delete this and the offer can omit a reason, which is a reason nobody in a channel can
    ever file."""
    line = correction_line(REF)

    assert all(reason.value in line for reason in FlagReason)
    assert line.endswith(REF)
    assert read_correction(_event(line)) is None


def test_an_offer_against_something_that_is_not_a_reference_is_refused() -> None:
    """A reference is one token of the alphabet the system mints. Anything else in the line
    points at nothing a person could correct.

    Delete this and a sentence can be put where the reference goes, and read back as one."""
    with pytest.raises(CorrectionError):
        correction_line("the invoice for SNM")


def test_a_line_with_a_sentence_after_the_reference_is_not_a_correction() -> None:
    """Reading the reason and dropping the sentence would tell the person their note was kept.

    Delete this and the reader can match a prefix, so "wrong_fact <ref> it is 48000" is
    filed as though the figure had been read."""
    assert read_correction(_event(f"wrong_fact {REF} the figure is 48000")) is None
    assert read_correction(_event(f"wrong_fact {REF}")) is not None


def test_only_the_first_line_is_read() -> None:
    """A quoted line below a question is somebody else's words, or an earlier exchange, and
    filing it would file it again under this sender's name. Blank lines before the first
    real one are skipped rather than counted.

    Delete this and a reply quoting a colleague's correction files it a second time."""
    assert read_correction(_event(f"what is outstanding\nwrong_fact {REF}")) is None
    read = read_correction(_event(f"\n   \nwrong_sources {REF}\n> quoted"))
    assert read is not None
    assert read.reason is FlagReason.WRONG_SOURCES


def test_a_word_outside_the_vocabulary_is_not_a_correction() -> None:
    """The vocabulary is `FlagReason`, spelled as it is spelled there.

    Delete this and any word of the right shape becomes a reason the flag cannot hold."""
    assert read_correction(_event(f"wrong_everything {REF}")) is None
    assert read_correction(_event(f"WRONG_FACT {REF}")) is None


# ------------------------------------------------------------ filing, and saying nothing


def test_a_correction_from_a_lead_in_that_department_is_filed_with_its_reason() -> None:
    """The positive case the refusals are measured against: the reason typed in a channel is
    the reason on the flag, which is where wrong sources reaches the report.

    Delete this and a filing step that files nothing passes the acknowledgement test."""
    filed = file_correction(
        _request(),
        found=AnswerOnFile(question_id="G01a", department="web"),
        flagger=_lead("web"),
        now=AT,
    )

    assert filed is not None
    assert filed.reason is FlagReason.WRONG_SOURCES
    assert filed.trace_ref == REF
    assert filed.flagged_by == "u_lead"


def test_every_outcome_is_acknowledged_with_one_identical_message() -> None:
    """**DENIED and ABSENT at the channel.** Filed, refused because the sender holds nothing in
    that department, and a reference that resolved to nothing are three outcomes and one
    delivered message, byte for byte.

    Delete this and the reply can say "you cannot flag answers in finance", which tells anybody
    typing references which ones exist and where they are."""
    found = AnswerOnFile(question_id="G01a", department="web")
    outcomes = [
        file_correction(_request(), found=found, flagger=_lead("web"), now=AT),
        file_correction(_request(), found=found, flagger=_lead("finance"), now=AT),
        file_correction(_request(), found=None, flagger=_lead("web"), now=AT),
    ]
    delivered = []
    for _ in outcomes:
        adapter = EmailAdapter()
        acknowledge(adapter, to=SENDER)
        delivered.append(adapter.sent[-1])

    assert [one is not None for one in outcomes] == [True, False, False]
    assert delivered[0] == delivered[1] == delivered[2]
    assert delivered[0].body == CORRECTION_ACKNOWLEDGEMENT
