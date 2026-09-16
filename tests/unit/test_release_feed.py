"""Looking for a newer release: switched off by default, asked in the background, never a tick.

The panel's reassuring answer is refused without a `Told`, so the first property that matters
here is that nothing short of a readable list over https produces one. Every failure is built as
the transport would raise it, and a fetch is handed in, so no test opens a socket.

The second is that no page waits for the list. `ReleaseWatch.answer` is asked with a fetch that
does not return until the test lets it, so a watch that asked inline would hand back the list's
answer on the first call instead of nothing, and the test fails rather than hangs.

Task ids: M42.3.9
"""

from __future__ import annotations

import ast
import asyncio
import http.client
import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain.console.version_view import (
    ANSWERS,
    SETTLED,
    TELLING_GOES_OFF_AFTER_DAYS,
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
    CHECK_VARIABLE,
    FEED_TIMEOUT_SECONDS,
    FEED_VARIABLE,
    LOOK_AGAIN_AFTER,
    MAX_FEED_BYTES,
    PRODUCT_RELEASES_URL,
    RETRY_A_FAILED_LOOK_AFTER,
    Look,
    ReleaseWatch,
    ask,
    feed_address,
    https_fetch,
    look_is_due,
    newest_release,
    notes_of,
)
from brain.ops.independence import vendor_hosts
from brain.runtime import choose_workers

#: Far outside any wall clock, because nothing here is about the present.
NOW = datetime(2099, 6, 1, 12, 0, tzinfo=UTC)

LIST = "https://releases.example.invalid/brain/releases"
MIRROR = "https://mirror.example.invalid/brain/releases"

REPO = Path(__file__).resolve().parents[2]

#: How many requests an hour the unauthenticated releases endpoint allows from one address, as
#: its own documentation states it. Written here rather than read, because it is a fact about
#: somebody else's service and this repository has nowhere else it could come from.
UNAUTHENTICATED_REQUESTS_AN_HOUR = 60


def release(
    tag: str, *, draft: bool = False, prerelease: bool = False, notes: str | None = None
) -> dict[str, object]:
    """One entry of the list, in the shape a repository's releases endpoint returns."""
    entry: dict[str, object] = {"tag_name": tag, "draft": draft, "prerelease": prerelease}
    if notes is not None:
        entry["html_url"] = notes
    return entry


class serving:  # noqa: N801 - read as a verb at the call site
    """A fetch answering with these entries, which records the addresses it was asked."""

    def __init__(self, *entries: dict[str, object]) -> None:
        self.entries = entries
        self.asked: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.asked.append(url)
        return json.dumps(list(self.entries)).encode()


class held:  # noqa: N801 - read as an adjective at the call site
    """A fetch that does not answer until `release` is called, and records whether it had.

    `finished` is filled only when the fetch returns, so a caller can tell a watch that returned
    before the list answered from one that waited for it.
    """

    def __init__(self, *entries: dict[str, object]) -> None:
        self.entries = entries
        self.gate = threading.Event()
        self.started = threading.Event()
        self.finished: list[str] = []

    def release(self) -> None:
        self.gate.set()

    def __call__(self, url: str) -> bytes:
        self.started.set()
        self.gate.wait(timeout=5)
        self.finished.append(url)
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


async def settled(watch: ReleaseWatch) -> None:
    """Wait for the look a watch started, and fail rather than wait for ever."""
    for _ in range(500):
        if not watch.looking:
            return
        await asyncio.sleep(0.01)
    msg = "the look never finished"
    raise AssertionError(msg)


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


# ----------------------------------------------------------------- where its notes are
def test_the_notes_are_the_https_address_the_list_gives_for_that_release() -> None:
    """**The link a client follows to decide whether to update.** It is the entry for the tag
    chosen as newest, not the first entry and not the newest entry's neighbour.

    Delete this and `notes_of` can return the first address in the list, which on a list ordered
    by date rather than by number is the notes of a hotfix to an older line."""
    listed = [
        release("v1.4.1", notes="https://releases.example.invalid/v1.4.1"),
        release("v1.5.0", notes="https://releases.example.invalid/v1.5.0"),
    ]

    assert notes_of(listed, "v1.5.0") == "https://releases.example.invalid/v1.5.0"
    assert notes_of(listed, "v1.4.1") == "https://releases.example.invalid/v1.4.1"
    assert notes_of(listed, "v9.9.9") == ""

    told = ask(LIST, fetch=serving(*listed), now=NOW)
    assert isinstance(told, Told)
    assert told.notes == "https://releases.example.invalid/v1.5.0"


def test_a_notes_address_that_is_not_https_is_dropped_rather_than_linked() -> None:
    """**A link somebody else chose the scheme of.** A copy of the list naming `javascript:` or
    plain http as a release's notes would put that on the screen as a link, so it is a release
    with no link. The release itself is still read: the answer about whether to update does not
    depend on the link.

    Delete this and the check in `notes_of` can go, after which `Told` refuses the value and the
    whole look fails over a link, which is a hostile copy of the list switching the check off."""
    for bad in ("javascript:alert(1)", "http://releases.example.invalid/v1.5.0", "  "):
        listed = [release("v1.5.0", notes=bad)]
        assert notes_of(listed, "v1.5.0") == "", bad
        told = ask(LIST, fetch=serving(*listed), now=NOW)
        assert isinstance(told, Told), bad
        assert told.tag == "v1.5.0"
        assert told.notes == ""


# ---------------------------------------------------------------------- asking the list
def test_an_install_that_has_not_switched_the_check_on_asks_nobody_and_says_so() -> None:
    """**The default, and the privacy decision as a test.** Off means no address, whatever a
    copy of the list is set to, and no address means no request.

    Delete this and naming a copy of the list becomes a second way to switch the check on, which
    is an outbound request nobody agreed to by setting the switch."""
    assert feed_address(switched_on=False, url="") == ""
    assert feed_address(switched_on=False, url=MIRROR) == ""

    fetch = serving(release("v1.4.0"))
    found = ask(feed_address(switched_on=False, url=MIRROR), fetch=fetch, now=NOW)

    assert isinstance(found, Unanswered)
    assert found.why is Unasked.SWITCHED_OFF
    assert CHECK_VARIABLE in found.detail
    assert fetch.asked == []


def test_switching_the_check_on_asks_the_products_list_unless_a_copy_is_named() -> None:
    """The positive sibling of the refusal above. On, with nothing else set, is the product's
    own published list; on, with a copy named, is that copy and not the product's.

    Delete this and `feed_address` can return nothing for everything, which passes the privacy
    test and is a check nobody can switch on."""
    assert feed_address(switched_on=True, url="") == PRODUCT_RELEASES_URL
    assert feed_address(switched_on=True, url="   ") == PRODUCT_RELEASES_URL
    assert feed_address(switched_on=True, url=f" {MIRROR} ") == MIRROR


def test_the_products_list_is_a_vendor_address_named_by_number_over_https() -> None:
    """**It belongs to the product, and it has to survive the product's repository being renamed
    again.** The independence sweep accepts it as a declared vendor host rather than refusing it as
    a client's, and it names the repository by number, which is the address a renamed
    repository's old name redirects to.

    Delete this and the address can be rewritten under an owner and a name, which goes on
    working until the next rename and then answers every install with a redirect or nothing."""
    assert PRODUCT_RELEASES_URL.startswith("https://api.github.com/repositories/")
    number = PRODUCT_RELEASES_URL.removeprefix("https://api.github.com/repositories/")
    assert number.split("/", 1)[0].isdigit()
    assert "api.github.com" in vendor_hosts(REPO)


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
        b"[]",
    ):
        found = ask(LIST, fetch=answering(body), now=NOW)
        assert isinstance(found, Unanswered), body
        assert found.why is Unasked.UNREADABLE


def test_an_answer_larger_than_a_release_list_could_be_is_refused() -> None:
    """Delete this and the ceiling can go, and the panel parses whatever size the address
    returns."""
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


def test_the_products_own_list_is_named_as_that_rather_than_as_an_address() -> None:
    """A client reads who said which release is newest, and an API address with a repository
    number in it is not an answer they can weigh.

    Delete this and the product's list is shown to a client as a string of path segments, while
    a copy they named still shows its own address, which is the one they would recognise."""
    product = ask(PRODUCT_RELEASES_URL, fetch=serving(release("v1.4.0")), now=NOW)
    copy = ask(MIRROR, fetch=serving(release("v1.4.0")), now=NOW)

    assert isinstance(product, Told) and isinstance(copy, Told)
    assert "published list of releases" in product.by
    assert PRODUCT_RELEASES_URL not in product.by
    assert MIRROR in copy.by


def test_a_naive_moment_is_refused_rather_than_recorded() -> None:
    """Delete this and a telling can be recorded at a naive instant, which `Told` refuses only
    after the request has been made."""
    with pytest.raises(VersionError, match="naive"):
        ask(LIST, fetch=serving(), now=datetime(2099, 6, 1, 12, 0))


def test_the_switch_and_the_copy_are_read_from_the_install_configuration_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Both are settings, read in the one place settings are read.** `brain.settings.Settings`
    reads `BRAIN_RELEASE_CHECK` and `BRAIN_RELEASE_FEED_URL`, and nothing in
    `brain.deployment.release_feed` touches the environment. Setting each under its documented
    name and reading it back through `Settings` also holds `CHECK_VARIABLE` and `FEED_VARIABLE`
    to the fields' real names, which is what the sentence a client reads tells them to set.

    Delete this and the asking module can read the environment itself again, which is a second
    reader of one value."""
    from brain.app import Settings

    monkeypatch.delenv(CHECK_VARIABLE, raising=False)
    monkeypatch.delenv(FEED_VARIABLE, raising=False)
    assert Settings().release_check is False
    assert Settings().release_feed_url == ""
    monkeypatch.setenv(CHECK_VARIABLE, "true")
    monkeypatch.setenv(FEED_VARIABLE, MIRROR)
    assert Settings().release_check is True
    assert Settings().release_feed_url == MIRROR

    source = (REPO / "src" / "brain" / "deployment" / "release_feed.py").read_text(encoding="utf-8")
    reads_the_environment = [
        node
        for node in ast.walk(ast.parse(source))
        if (isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"})
        or (isinstance(node, ast.Name) and node.id in {"environ", "getenv"})
    ]
    assert reads_the_environment == []


def test_the_sentence_for_a_switched_off_check_names_the_switch_by_its_real_name() -> None:
    """The client's instruction is the variable to set, and it is spelled in a module that
    cannot import this one. Held here, against the name `Settings` is held to above.

    Delete this and the switch can be renamed in one place, leaving the screen telling every
    client to set a variable nothing reads."""
    assert CHECK_VARIABLE in ANSWERS[Standing.SWITCHED_OFF].what_to_do


def test_the_transport_refuses_anything_but_https_itself() -> None:
    """A caller can reach the transport without going through `ask`. Delete this and that
    caller reaches the one path `ask` refuses. No socket is opened: the refusal is first."""
    with pytest.raises(OSError, match="not an https address"):
        https_fetch("http://releases.example.invalid/list")


# ----------------------------------------------------------------- the background look
def test_no_answer_waits_for_the_release_list() -> None:
    """**The page never waits, as a test.** The list does not answer until this test lets it. A
    watch that asked inline would block here until the fetch gave up and then hand back the
    list's answer, so the first answer being nothing, while the fetch has still not returned, is
    the proof that the asking happens beside the request rather than in it.

    Delete this and `answer` can call `ask` directly, and every load of the updates screen
    waits for somebody else's server again."""
    fetch = held(release("v1.5.0"))
    watch = ReleaseWatch(fetch=fetch)

    async def scenario() -> None:
        try:
            first = watch.answer(LIST, now=NOW)
            assert first is None
            assert fetch.finished == []
            assert watch.looking
        finally:
            fetch.release()
        await settled(watch)
        later = watch.answer(LIST, now=NOW + timedelta(minutes=1))
        assert isinstance(later, Told)
        assert later.tag == "v1.5.0"

    asyncio.run(scenario())
    assert fetch.finished == [LIST]


def test_a_switched_off_watch_answers_at_once_and_starts_nothing() -> None:
    """Off is answered without a look, a task, or a request, every time it is asked.

    Delete this and a watch can start a look at an empty address, which `ask` answers without
    a request today and which a later change to `ask` could turn into one."""
    fetch = serving(release("v1.5.0"))
    watch = ReleaseWatch(fetch=fetch)

    async def scenario() -> None:
        for minutes in (0, 60 * 24):
            found = watch.answer("", now=NOW + timedelta(minutes=minutes))
            assert isinstance(found, Unanswered)
            assert found.why is Unasked.SWITCHED_OFF
            assert not watch.looking

    asyncio.run(scenario())
    assert fetch.asked == []
    assert watch.last is None


def test_a_look_is_not_started_again_while_one_is_running() -> None:
    """Three loads of the screen while the list is slow are one request, not three.

    Delete this and a slow list is asked once per load, and the screen being opened by three
    administrators at once is three requests leaving the network for one answer."""
    fetch = held(release("v1.5.0"))
    watch = ReleaseWatch(fetch=fetch)

    async def scenario() -> None:
        try:
            for seconds in (0, 1, 2):
                assert watch.answer(LIST, now=NOW + timedelta(seconds=seconds)) is None
            await asyncio.to_thread(fetch.started.wait, 5)
        finally:
            fetch.release()
        await settled(watch)

    asyncio.run(scenario())
    assert fetch.finished == [LIST]


def test_an_answered_look_is_used_until_its_interval_and_then_looked_at_again() -> None:
    """Both intervals, at their boundaries, and the look that has not happened yet.

    Delete this and either comparison can be off by one or reversed: a watch that looks on every
    load passes the background test above, and so does one that never looks again."""
    told = Told(tag="v1.5.0", at=NOW, by="the list")
    failed = Unanswered(why=Unasked.UNREACHABLE, detail="timed out", at=NOW)
    second = timedelta(seconds=1)

    assert look_is_due(None, NOW)
    assert not look_is_due(Look(LIST, told), NOW + LOOK_AGAIN_AFTER - second)
    assert look_is_due(Look(LIST, told), NOW + LOOK_AGAIN_AFTER)
    assert not look_is_due(Look(LIST, failed), NOW + RETRY_A_FAILED_LOOK_AFTER - second)
    assert look_is_due(Look(LIST, failed), NOW + RETRY_A_FAILED_LOOK_AFTER)
    assert not look_is_due(Look(LIST, told), NOW - second)


def test_the_watch_looks_again_only_once_the_interval_has_passed() -> None:
    """The same rule through the watch rather than the predicate, so a watch that ignored the
    predicate is caught as well as a predicate that was wrong.

    Delete this and `answer` can start a look on every call, which the predicate's own test does
    not see."""
    fetch = serving(release("v1.5.0"))
    watch = ReleaseWatch(fetch=fetch)

    async def scenario() -> None:
        watch.answer(LIST, now=NOW)
        await settled(watch)
        assert isinstance(watch.answer(LIST, now=NOW + LOOK_AGAIN_AFTER / 2), Told)
        assert not watch.looking
        watch.answer(LIST, now=NOW + LOOK_AGAIN_AFTER)
        await settled(watch)

    asyncio.run(scenario())
    assert fetch.asked == [LIST, LIST]


def test_a_look_finished_after_the_moment_asked_about_is_not_shown_to_that_moment() -> None:
    """Two requests interleave: one starts a look, the look finishes, and a request whose clock
    was read before the look started asks. From that moment nothing had been looked at, so it is
    answered as not looked yet rather than handed a telling from its own future, which
    `standing_of` refuses as two clocks disagreeing.

    Delete this and that interleaving is a server error on the updates screen."""
    fetch = serving(release("v1.5.0"))
    watch = ReleaseWatch(fetch=fetch)

    async def scenario() -> None:
        watch.answer(LIST, now=NOW)
        await settled(watch)
        assert watch.answer(LIST, now=NOW - timedelta(seconds=1)) is None
        assert not watch.looking
        assert isinstance(watch.answer(LIST, now=NOW), Told)

    asyncio.run(scenario())


def test_a_look_at_one_list_is_not_the_answer_for_another() -> None:
    """A process whose configured list changed is answered about the list it is set to ask.

    Delete this and a watch can hand the product's answer to an install now pointed at its own
    copy, which is a list it was not set to read and a request it did not agree to recorded as
    one it did."""
    fetch = serving(release("v1.5.0"))
    watch = ReleaseWatch(fetch=fetch)

    async def scenario() -> None:
        watch.answer(LIST, now=NOW)
        await settled(watch)
        assert watch.answer(MIRROR, now=NOW + timedelta(seconds=1)) is None
        await settled(watch)

    asyncio.run(scenario())
    assert fetch.asked == [LIST, MIRROR]


def test_a_look_that_fails_in_a_way_nobody_foresaw_is_kept_as_a_failed_look() -> None:
    """`ask` turns every transport failure it knows into an answer. Anything else raised inside
    a look is kept as a failed look too, so the screen says the check failed rather than
    repeating an older answer with nothing saying the new look went wrong.

    Delete this and a look that raised leaves the last answer in place, and a list that has
    started answering with something this code cannot parse keeps showing yesterday's tick."""
    watch = ReleaseWatch(fetch=refusing(ValueError("not what anybody expected")))

    async def scenario() -> None:
        watch.answer(LIST, now=NOW)
        await settled(watch)

    asyncio.run(scenario())
    assert watch.last is not None
    assert isinstance(watch.last.outcome, Unanswered)
    assert watch.last.outcome.why is Unasked.UNREACHABLE
    assert "ValueError" in watch.last.outcome.detail


def test_the_intervals_sit_inside_the_staleness_window_and_the_vendors_allowance() -> None:
    """**Constants held against things outside themselves.** A healthy check has to look again
    well before the panel calls its answer stale; a failed look is retried sooner than a good
    one is refreshed, and never while the previous request could still be waiting; and every
    worker process this product can start, retrying a list that refuses, stays inside what the
    releases endpoint allows one address in an hour.

    Delete this and either interval can be moved past the point where it is right, and nothing
    else notices until an install is drawn as stale with the check working or is refused by the
    list for asking too often."""
    most_workers = choose_workers(memory_mb=10**6, cores=10**3)
    retries_an_hour = timedelta(hours=1) / RETRY_A_FAILED_LOOK_AFTER

    assert timedelta(days=TELLING_GOES_OFF_AFTER_DAYS) > LOOK_AGAIN_AFTER
    assert RETRY_A_FAILED_LOOK_AFTER < LOOK_AGAIN_AFTER
    assert timedelta(seconds=FEED_TIMEOUT_SECONDS) < RETRY_A_FAILED_LOOK_AFTER
    assert most_workers * retries_an_hour <= UNAUTHENTICATED_REQUESTS_AN_HOUR


# ---------------------------------------------------------------- what the panel draws
def test_no_way_of_not_getting_an_answer_reaches_the_reassuring_standing() -> None:
    """**The leaf's failure mode, closed.** An install running the newest release there is,
    whose list did not answer, is not told it is up to date.

    Delete this and `CHECK_FAILED` can be folded into the comparison, and a firewall rule that
    blocks the list turns into a tick."""
    running = on("v1.4.0")
    for why in Unasked:
        unanswered = Unanswered(why=why, detail="it did not answer", at=NOW)
        standing = standing_of(running, unanswered, now=NOW)
        assert standing not in SETTLED
        built = panel(running, unanswered, now=NOW)
        assert built.standing is standing
        assert built.told_days_ago is None

    assert standing_of(running, None, now=NOW) is Standing.NOT_LOOKED_YET
    assert standing_of(running, Unanswered(Unasked.SWITCHED_OFF, "off", NOW), now=NOW) is (
        Standing.SWITCHED_OFF
    )
    assert standing_of(running, Unanswered(Unasked.UNREACHABLE, "timed out", NOW), now=NOW) is (
        Standing.CHECK_FAILED
    )
    assert standing_of(running, Unanswered(Unasked.UNREADABLE, "html", NOW), now=NOW) is (
        Standing.CHECK_FAILED
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
def test_the_asking_module_reads_no_clock() -> None:
    """The asking takes `now` so its boundaries are testable, and the background look records
    the moment of the request that started it rather than reading the process clock.

    Delete this and a clock read can arrive in the watch, after which the interleaving test above
    passes on a fast machine and fails on a loaded one."""
    source = (REPO / "src" / "brain" / "deployment" / "release_feed.py").read_text(encoding="utf-8")
    clocks = [
        node.func.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"now", "utcnow", "today", "time", "monotonic"}
    ]
    assert clocks == []


def test_both_variables_are_documented_where_a_client_updates_an_install() -> None:
    """Delete this and the switch that turns the reminder on exists only in a module docstring,
    which no client reads."""
    guide = (REPO / "docs" / "install" / "update-and-rollback.md").read_text(encoding="utf-8")

    assert f"`{CHECK_VARIABLE}=true`" in guide
    assert f"`{FEED_VARIABLE}`" in guide
