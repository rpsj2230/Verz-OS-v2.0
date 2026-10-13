"""A person's settings, parsed, and what they hold back.

Task ids: M40.4.1.4, M40.5.2.1, M40.5.2.2, M40.5.2.3, M40.5.2.4
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from brain.gate.context import Channel
from brain.member.connections import NotificationKind
from brain.member.preferences import PreferenceKey, parse
from brain.tables.member_preference import KEYS
from brain.tell_later import Held, held_by

ZONE = ZoneInfo("Asia/Singapore")
#: Far outside any wall clock, and 23:30 in Singapore.
LATE = datetime(2019, 3, 4, 15, 30, tzinfo=UTC)
NOON = datetime(2019, 3, 4, 4, 0, tzinfo=UTC)


def test_the_keys_the_code_names_are_the_keys_the_table_allows() -> None:
    """The enum, the model's list and `0229`'s constraint hold five names. Delete this and a key
    can be written by the code that the database refuses, or the reverse."""
    import importlib.util
    from pathlib import Path

    assert {one.value for one in PreferenceKey} == set(KEYS)
    path = Path(__file__).parents[2] / "migrations" / "versions" / "0229_member_preference.py"
    spec = importlib.util.spec_from_file_location("m0229", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.KEYS) == set(KEYS)


def test_a_person_with_nothing_stored_has_every_quiet_default() -> None:
    """No row means learning on, no primary, no statement about any channel, an approval carried
    anywhere it may be, and no quiet hours. Delete this and a default can start holding messages
    back from everybody who never set anything."""
    settings = parse("p", {})
    assert not settings.learning_opted_out and settings.primary is None
    assert settings.notices == () and settings.quiet is None
    assert not settings.says(Channel.SLACK)
    assert settings.lets_an_approval_go_to(Channel.LARK)
    assert not settings.lets_an_approval_go_to(Channel.WHATSAPP)


def test_a_stored_value_that_does_not_parse_is_ignored_and_named_and_never_raises() -> None:
    """A row an older release or a hand wrote is skipped in the safe direction. Delete this and one
    person's bad row stops every message after theirs."""
    settings = parse(
        "p",
        {
            "learning_opt_out": {"on": "yes"},
            "primary_channel": {"channel": "carrier-pigeon"},
            "channel_notices": {"slack": ["gossip"]},
            "approval_route": {"channel": "slack"},
            "quiet_hours": {"start": "22:00", "end": "22:00"},
        },
    )
    assert set(settings.ignored) == {one.value for one in PreferenceKey}
    assert settings.quiet is None and settings.approval_route is None


def test_a_good_value_of_each_kind_is_read() -> None:
    """Each setting round-trips from its stored document. Delete this and a parser can ignore
    everything and pass the tests of ignoring."""
    settings = parse(
        "p",
        {
            "learning_opt_out": {"on": True},
            "primary_channel": {"channel": "slack"},
            "channel_notices": {"slack": ["digest"]},
            "approval_route": {"channel": "console"},
            "quiet_hours": {"start": "22:00", "end": "07:00"},
        },
    )
    assert settings.learning_opted_out and settings.primary is Channel.SLACK
    assert settings.wants(Channel.SLACK, NotificationKind.DIGEST)
    assert not settings.wants(Channel.SLACK, NotificationKind.AUTOMATION)
    assert settings.approval_route is Channel.CONSOLE
    assert settings.quiet is not None and settings.quiet.start == time(22)
    assert not settings.ignored


def test_quiet_hours_hold_a_digest_and_never_an_approval() -> None:
    """Inside the window a digest and an automation wait and an approval does not. Delete this and
    quiet hours hold an envelope until it has expired."""
    settings = parse("p", {"quiet_hours": {"start": "22:00", "end": "07:00"}})
    for kind in (NotificationKind.DIGEST, NotificationKind.AUTOMATION):
        assert held_by(settings, Channel.SLACK, kind, LATE, ZONE) is Held.QUIET_HOURS
        assert held_by(settings, Channel.SLACK, kind, NOON, ZONE) is None
    assert held_by(settings, Channel.SLACK, NotificationKind.APPROVAL, LATE, ZONE) is None


def test_a_channel_with_a_statement_holds_what_it_leaves_out_and_one_without_holds_nothing() -> (
    None
):
    """Only a person who said something about a channel has kinds held back on it. Delete this and
    every person without settings stops being sent their digest."""
    said = parse("p", {"channel_notices": {"slack": ["automation"]}})
    assert held_by(said, Channel.SLACK, NotificationKind.DIGEST, NOON, ZONE) is Held.NOT_WANTED
    assert held_by(said, Channel.SLACK, NotificationKind.AUTOMATION, NOON, ZONE) is None
    assert held_by(said, Channel.LARK, NotificationKind.DIGEST, NOON, ZONE) is None
    assert held_by(parse("p", {}), Channel.SLACK, NotificationKind.DIGEST, NOON, ZONE) is None
