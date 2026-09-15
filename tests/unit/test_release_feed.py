"""Asking a release list which release is newest, and every way of not getting an answer.

The panel's reassuring answer is refused without a `Told`, so the property that matters here
is that nothing short of a readable list over https produces one. Every failure is built as the
transport would raise it, and a fetch is handed in, so no test opens a socket.

Task ids: M42.3.9
"""

from __future__ import annotations

import ast
import http.client
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from brain.console.version_view import (
    SETTLED,
    Panel,
    Running,
    Standing,
    Told,
    Unanswered,
    Unasked,
    VersionError,
    panel,
    running_release,
    standing_of,
)
from brain.deployment.release_feed import (
    FEED_VARIABLE,
    MAX_FEED_BYTES,
    ask,
    check,
    https_fetch,
    newest_release,
)

#: Far outside any wall clock, because nothing here is about the present.
NOW = datetime(2099, 6, 1, 12, 0, tzinfo=UTC)

LIST = "https://releases.example.invalid/brain/releases"

REPO = Path(__file__).resolve().parents[2]


def release(tag: str, *, draft: bool = False, prerelease: bool = False) -> dict[str, object]:
    """One entry of the list, in the shape a repository's releases endpoint returns."""
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease}


class serving:  # noqa: N801 - read as a verb at the call site
    """A fetch answering with these entries, which records the addresses it was asked."""

    def __init__(self, *entries: dict[str, object]) -> None:
        self.entries = entries
        self.asked: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.asked.append(url)
        return json.dumps(list(self.entries)).encode()


def answering(body: bytes) -> Callable[[str], bytes]:
    """A fetch answering every address with these bytes."""

    def fetch(url: str) -> bytes:
        return body

    return fetch


def refusing(error: BaseException) -> Callable[[str], bytes]:
    """A fetch that fails the way a transport does."""

    def fetch(url: str) -> bytes:
        raise error

    return fetch


def on(tag: str) -> Running:
    """An install whose marker and pin agree on `tag`."""
    return running_release(marker=tag, pinned_image=f"ghcr.io/example/brain:{tag}")


# ------------------------------------------------------------------- choosing the newest
def test_the_newest_release_is_ordered_by_its_numbers_and_not_as_text() -> None:
    """Delete this and `max` over the tags as strings can come back, which makes v1.9.0 newer
    than v1.10.0 and tells an install on v1.9.0 that it is up to date."""
    assert newest_release([release("v1.9.0"), release("v1.10.0"), release("v1.2")]) == "v1.10.0"


def test_drafts_prereleases_and_tags_that_are_not_releases_are_never_the_newest() -> None:
    """A draft is not published, a prerelease is not what a client installs, and `latest` is not
    a release at all. Each one read as newest makes an install report itself behind a release it
    cannot install, or current against a name that never changes.

    Delete this and any of the three can be chosen."""
    listed = [
        release("v9.0.0", draft=True),
        release("v8.0.0", prerelease=True),
        release("latest"),
        release("nightly-2099"),
        release("v1.4.0"),
    ]
    assert newest_release(listed) == "v1.4.0"


def test_an_entry_that_does_not_say_it_is_published_is_not_read_as_published() -> None:
    """The flags are read as the list states them, and a missing flag is not a false one.

    Delete this and an entry with no `draft` field at all, which is what a list of some other
    shape looks like, counts as a published release."""
    assert newest_release([{"tag_name": "v2.0.0"}]) is None
    assert newest_release([{"tag_name": "v2.0.0", "draft": False}]) is None


def test_a_single_release_object_is_read_as_a_list_of_one() -> None:
    """The latest-release endpoint answers with one object rather than an array.

    Delete this and an install pointed at that endpoint reads every answer as naming nothing."""
    assert newest_release(release("v1.4.0")) == "v1.4.0"


def test_a_list_naming_nothing_this_install_can_order_names_no_release() -> None:
    """The sibling of the positive cases. Delete this and `newest_release` can return the first
    tag it sees, which passes every test above that happens to list the newest first."""
    assert newest_release([]) is None
    assert newest_release([release("latest"), "not an entry", 7]) is None
    assert newest_release("v1.4.0") is None
    assert newest_release(None) is None


def test_a_longer_tag_does_not_outrank_a_later_release_for_its_length() -> None:
    """Numbers are compared left to right, so `v1.4.0.9` is older than `v1.5` however many parts it
    has, and the order the list gives them in decides nothing.

    Delete this and an ordering by length, or by position in the list, passes the text test."""
    assert newest_release([release("v1.4.0.9"), release("v1.5")]) == "v1.5"
    assert newest_release([release("v1.5"), release("v1.4.0.9")]) == "v1.5"


# ---------------------------------------------------------------------- asking the list
def test_an_install_that_names_no_list_asks_nobody_and_says_so() -> None:
    """**The default, and the privacy decision as a test.** No variable, no request.

    Delete this and an unset variable can fall through to a default address, which is the
    outbound connection nobody agreed to."""
    fetch = serving(release("v1.4.0"))

    found = ask("", fetch=fetch, now=NOW)

    assert isinstance(found, Unanswered)
    assert found.why is Unasked.NO_SOURCE
    assert FEED_VARIABLE in found.detail
    assert fetch.asked == []


def test_a_list_that_is_not_https_is_not_asked() -> None:
    """Delete this and a list served over plain http can be rewritten on the path into one whose
    newest release is whatever is already running, which the panel would draw as a tick."""
    fetch = serving(release("v1.4.0"))

    found = ask("http://releases.example.invalid/list", fetch=fetch, now=NOW)

    assert isinstance(found, Unanswered)
    assert found.why is Unasked.UNREADABLE
    assert fetch.asked == []


def test_a_list_that_cannot_be_reached_is_an_answer_that_is_not_a_tick() -> None:
    """**Fail closed.** A timeout, a refused connection and a broken response are all a list that
    said nothing.

    Delete this and a transport error can escape to whatever renders the panel, where the
    commonest handling of an exception is to draw nothing, and nothing beside a version reads
    as fine."""
    for error in (
        TimeoutError("timed out"),
        ConnectionRefusedError("refused"),
        http.client.RemoteDisconnected("closed"),
    ):
        found = ask(LIST, fetch=refusing(error), now=NOW)
        assert isinstance(found, Unanswered), error
        assert found.why is Unasked.UNREACHABLE
        assert type(error).__name__ in found.detail


def test_an_answer_that_is_not_a_readable_list_of_releases_is_not_a_tick() -> None:
    """Delete this and a captive portal's login page, or an error page served with a 200, can be
    parsed into an answer."""
    for body in (
        b"<html>sign in to continue</html>",
        json.dumps({"message": "Not Found"}).encode(),
    ):
        found = ask(LIST, fetch=answering(body), now=NOW)
        assert isinstance(found, Unanswered), body
        assert found.why is Unasked.UNREADABLE


def test_an_answer_larger_than_a_release_list_could_be_is_refused() -> None:
    """Delete this and the ceiling can go, and the panel parses whatever size the address
    returns while a person waits for a console screen."""
    # A list that would otherwise be read, so the size is the only thing that can refuse it.
    # Found by a mutation that survived: the first version padded an empty list, which is
    # refused as naming no release whether or not the ceiling exists.
    readable = json.dumps([release("v1.4.0")]).encode()
    oversized = readable[:-1] + b" " * MAX_FEED_BYTES + b"]"
    assert isinstance(ask(LIST, fetch=answering(readable), now=NOW), Told)

    found = ask(LIST, fetch=answering(oversized), now=NOW)

    assert isinstance(found, Unanswered)
    assert found.why is Unasked.UNREADABLE


def test_a_readable_list_is_a_telling_that_says_where_it_came_from_and_when() -> None:
    """The positive case. Every refusal above is satisfied by a function that never answers.

    Delete this and `ask` can return `Unanswered` for everything."""
    found = ask(LIST, fetch=serving(release("v1.3.0"), release("v1.4.0")), now=NOW)

    assert isinstance(found, Told)
    assert found.tag == "v1.4.0"
    assert found.at == NOW
    assert LIST in found.by


def test_a_naive_moment_is_refused_rather_than_recorded() -> None:
    """Delete this and a telling can be recorded at a naive instant, which `Told` refuses only
    after the request has been made."""
    with pytest.raises(VersionError, match="naive"):
        ask(LIST, fetch=serving(), now=datetime(2099, 6, 1, 12, 0))


def test_the_configured_list_is_read_from_the_install_configuration_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The address is a setting, read in the one place settings are read.**
    `brain.settings.Settings` reads `BRAIN_RELEASE_FEED_URL`, and nothing in
    `brain.deployment.release_feed` touches the environment, so the variable has one reader and a
    fallback address cannot be written into the asking module where a client would not look.
    Setting the variable under its documented name and reading it back through `Settings` also
    holds `FEED_VARIABLE` to the field's real name.

    Delete this and the asking module can read the environment itself again, which is a second
    reader of one value."""
    from brain.app import Settings

    monkeypatch.delenv(FEED_VARIABLE, raising=False)
    assert Settings().release_feed_url == ""
    monkeypatch.setenv(FEED_VARIABLE, LIST)
    assert Settings().release_feed_url == LIST

    source = (REPO / "src" / "brain" / "deployment" / "release_feed.py").read_text(encoding="utf-8")
    reads_the_environment = [
        node
        for node in ast.walk(ast.parse(source))
        if (isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"})
        or (isinstance(node, ast.Name) and node.id in {"environ", "getenv"})
    ]
    assert reads_the_environment == []

    assert isinstance(check(now=NOW, url="", fetch=refusing(AssertionError())), Unanswered)
    told = check(now=NOW, url=f" {LIST} ", fetch=serving(release("v2.0")))
    assert isinstance(told, Told)


def test_the_transport_refuses_anything_but_https_itself() -> None:
    """A caller can reach the transport without going through `ask`. Delete this and that
    caller reaches the one path `ask` refuses. No socket is opened: the refusal is first."""
    with pytest.raises(OSError, match="not an https address"):
        https_fetch("http://releases.example.invalid/list")


# ---------------------------------------------------------------- what the panel draws
def test_no_way_of_not_getting_an_answer_reaches_the_reassuring_standing() -> None:
    """**The leaf's failure mode, closed.** An install running the newest release there is,
    whose list did not answer, is not told it is up to date.

    Delete this and `CANNOT_ASK` can be folded into the comparison, and a firewall rule that
    blocks the list turns into a tick."""
    running = on("v1.4.0")
    for why in Unasked:
        unanswered = Unanswered(why=why, detail="it did not answer", at=NOW)
        standing = standing_of(running, unanswered, now=NOW)
        assert standing not in SETTLED
        built = panel(running, unanswered, now=NOW)
        assert built.standing is standing
        assert built.told_days_ago is None

    assert standing_of(running, Unanswered(Unasked.NO_SOURCE, "unset", NOW), now=NOW) is (
        Standing.NOBODY_HAS_SAID
    )
    assert standing_of(running, Unanswered(Unasked.UNREACHABLE, "timed out", NOW), now=NOW) is (
        Standing.CANNOT_ASK
    )
    assert standing_of(running, Unanswered(Unasked.UNREADABLE, "html", NOW), now=NOW) is (
        Standing.CANNOT_ASK
    )


def test_a_panel_cannot_claim_the_reassuring_answer_on_an_unanswered_question() -> None:
    """Delete this and a renderer can build the tick directly from an unanswered question."""
    unanswered = Unanswered(why=Unasked.UNREACHABLE, detail="timed out", at=NOW)

    with pytest.raises(VersionError, match="nobody has said"):
        Panel(running=on("v1.4.0"), told=unanswered, standing=Standing.CURRENT, told_days_ago=0)


def test_an_answered_list_is_compared_the_way_a_recorded_one_is() -> None:
    """The asking and the comparison meet here, and the positive half of both is asserted.

    Delete this and the panel can treat a list's answer differently from a recorded one."""
    told = ask(LIST, fetch=serving(release("v1.4.0")), now=NOW)
    assert isinstance(told, Told)

    assert panel(on("v1.4.0"), told, now=NOW).standing is Standing.CURRENT
    assert panel(on("v1.3.0"), told, now=NOW).standing is Standing.BEHIND


def test_an_unanswered_question_must_say_what_happened_and_when() -> None:
    """Delete this and a panel can be built with a reason that is blank, which is the blank with
    a label `Unanswered` exists to prevent."""
    with pytest.raises(VersionError, match="nothing saying what happened"):
        Unanswered(why=Unasked.UNREACHABLE, detail="  ", at=NOW)
    with pytest.raises(VersionError, match="naive"):
        Unanswered(why=Unasked.UNREACHABLE, detail="timed out", at=datetime(2099, 6, 1))


# ------------------------------------------------------------------ module properties
def test_the_panel_module_still_reaches_nothing_and_the_asking_module_reads_no_clock() -> None:
    """The asking was added to its own module so the panel's claim about itself stays true, and
    the asking takes `now` so its boundaries are testable.

    Delete this and a fetch or a clock read can arrive in either module unremarked."""
    source = (REPO / "src" / "brain" / "deployment" / "release_feed.py").read_text(encoding="utf-8")
    clocks = [
        node.func.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"now", "utcnow", "today"}
    ]
    assert clocks == []


def test_the_variable_is_documented_where_a_client_updates_an_install() -> None:
    """Delete this and the switch that turns the reminder on exists only in a module docstring,
    which no client reads."""
    guide = (REPO / "docs" / "install" / "update-and-rollback.md").read_text(encoding="utf-8")

    assert f"`{FEED_VARIABLE}`" in guide
