"""The transport a knowledge link is fetched over, with the connection stood in.

`brain.knowledge.link_fetch.LinkFetcher` opens `_PinnedHTTPSConnection`, and that class is replaced
here by one that records how it was opened and answers a scripted response, so no test touches a
socket or the network. What is tested is what the transport decides: which address it connects
to, what it hands back for a redirect, and what it says when the site will not answer.

Task ids: M7.1.2
"""

from __future__ import annotations

import http.client
from typing import Any, ClassVar

import pytest

from brain.knowledge import link_fetch
from brain.knowledge.link_fetch import USER_AGENT, LinkFetcher
from brain.tools.fetch import FetchedBytes
from brain.tools.skills import SkillError


class Answer:
    """A scripted HTTP answer, reading at most what it is asked for."""

    def __init__(self, status: int, body: bytes = b"", location: str | None = None) -> None:
        self.status = status
        self.body = body
        self.location = location
        self.asked: list[int] = []

    def getheader(self, name: str) -> str | None:
        return self.location if name == "Location" else None

    def read(self, amount: int) -> bytes:
        self.asked.append(amount)
        return self.body[:amount]


class Connection:
    """Stands in for `_PinnedHTTPSConnection`: records its opening and the request, answers."""

    opened: ClassVar[list[dict[str, Any]]] = []
    answer: ClassVar[Answer | BaseException] = Answer(200, b"<html></html>")

    def __init__(self, host: str, port: int, *, address: str, timeout: float, context: Any) -> None:
        self.record: dict[str, Any] = {"host": host, "port": port, "address": address}
        Connection.opened.append(self.record)

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        self.record.update(method=method, path=path, headers=headers)

    def getresponse(self) -> Answer:
        if isinstance(Connection.answer, BaseException):
            raise Connection.answer
        return Connection.answer

    def close(self) -> None:
        self.record["closed"] = True


@pytest.fixture(autouse=True)
def stood_in(monkeypatch: pytest.MonkeyPatch) -> None:
    Connection.opened = []
    monkeypatch.setattr(link_fetch, "_PinnedHTTPSConnection", Connection)


def test_the_connection_goes_to_the_checked_address_and_asks_as_the_name() -> None:
    """**The DNS rebinding half of the address rule.** The rule checked one address; connecting
    by name would look the name up again. Delete this and the transport can be changed to
    connect by name with every fetch test green, because those stand in for the transport."""
    Connection.answer = Answer(200, b"page")
    got = LinkFetcher().get_once(
        "https://www.example.org:8443/a/b?c=d", address="93.184.216.34", max_bytes=100
    )

    assert got == FetchedBytes(body=b"page", final_url="https://www.example.org:8443/a/b?c=d")
    (record,) = Connection.opened
    assert (record["host"], record["port"], record["address"]) == (
        "www.example.org",
        8443,
        "93.184.216.34",
    )
    assert (record["method"], record["path"]) == ("GET", "/a/b?c=d")
    assert record["headers"]["User-Agent"] == USER_AGENT
    assert record["closed"]


def test_a_redirect_is_handed_back_as_a_whole_address_and_not_followed() -> None:
    """The chain is where the rule is applied to every hop. Delete this and a relative Location
    reaches the rule as a path, or the transport follows it past the rule."""
    Connection.answer = Answer(301, location="/services/pricing")
    got = LinkFetcher().get_once("https://www.example.org/old", address="1.1.1.1", max_bytes=10)

    assert got == "https://www.example.org/services/pricing"
    assert len(Connection.opened) == 1


def test_a_site_that_will_not_answer_is_told_by_status_and_never_by_its_body() -> None:
    """The body of a refusal is the far side's text. Delete this and a 404 page's words reach
    the administrator's screen, or a 404 is stored as the page."""
    Connection.answer = Answer(404, b"<p>Secret internal NOTFOUNDWORD</p>")

    with pytest.raises(SkillError) as refused:
        LinkFetcher().get_once("https://www.example.org/gone", address="1.1.1.1", max_bytes=10)

    assert "answered 404" in str(refused.value)
    assert "NOTFOUNDWORD" not in str(refused.value)


def test_a_body_is_read_to_one_byte_past_the_ceiling_and_no_further() -> None:
    """So the size rule in `fetch` can refuse an oversized answer having received only the
    ceiling and one byte. Delete this and a gigabyte is read before anything counts it."""
    answer = Answer(200, bytes(1000))
    Connection.answer = answer

    got = LinkFetcher().get_once("https://www.example.org/big", address="1.1.1.1", max_bytes=10)

    assert answer.asked == [11]
    assert isinstance(got, FetchedBytes) and len(got.body) == 11


@pytest.mark.parametrize(
    ("failure", "said"),
    [
        (TimeoutError(), "did not answer within"),
        (ConnectionRefusedError(), "could not be reached (ConnectionRefusedError)"),
        (http.client.RemoteDisconnected("gone"), "could not be reached (RemoteDisconnected)"),
    ],
)
def test_a_network_failure_is_a_sentence_about_the_site(failure: BaseException, said: str) -> None:
    """Delete this and a timeout escapes as an exception the route answers with a 500."""
    Connection.answer = failure

    with pytest.raises(SkillError, match=said.replace("(", r"\(").replace(")", r"\)")):
        LinkFetcher().get_once("https://www.example.org/", address="1.1.1.1", max_bytes=10)


def test_the_transport_itself_refuses_an_address_that_is_not_https() -> None:
    """Unreachable through `fetch`, and still refused here, because this class opens the socket.
    Delete this and a caller that skips `fetch` sends a request in the clear."""
    with pytest.raises(SkillError, match="not an https address"):
        LinkFetcher().get_once("http://www.example.org/", address="1.1.1.1", max_bytes=10)
    assert Connection.opened == []
