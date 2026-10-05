"""Giving the sign-in service the mail relay: what the application prints, decides and records.

`brain.ops.sign_in_mail` is the application's half of the release step in
`ops/keycloak/accounts-client.sh`, which `tests/unit/test_accounts_client.py` runs against a
stand-in Keycloak. Here: the realm's settings made from a relay, the decision whether to write
them, and the record of what the realm read back, each beside the case that refuses. Nothing here
has called a Keycloak, a vault or a mail server.

Task ids: M40.7.1
"""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest

from brain.ops import sign_in_mail
from brain.ops.mail import MailSettings, Security
from brain.ops.sign_in_mail import (
    PASSWORD_KEY,
    SAME,
    UNSET,
    VISIBLE_KEYS,
    WRITE,
    Mirrored,
    Relay,
    SignInMailError,
    decide,
    matches,
    realm_mail,
    server,
    visible,
)

PASSWORD = "SENTINEL-relay-password-4f7a"
STARTTLS = MailSettings(
    host="smtp.example.net",
    port=587,
    security=Security.STARTTLS,
    sender="brain@example.com",
    username="relay-user",
)
TLS = MailSettings(
    host="smtp.example.net",
    port=465,
    security=Security.TLS,
    sender="brain@example.com",
    username="relay-user",
)
RELAY = Relay(settings=STARTTLS, version="v1")


def shown(settings: MailSettings, **changed: str) -> dict[str, str]:
    """What Keycloak shows for a realm holding this relay: the password masked."""
    return {**visible(settings), PASSWORD_KEY: "**********", **changed}


# ======================================================================== the realm's settings


def test_the_realm_is_given_the_relay_s_host_port_sender_user_and_security() -> None:
    """**Keycloak's own keys, as strings**, with authentication on and exactly one of starttls
    and ssl true for the relay's security.

    Delete this and a relay on port 465 could be given to the realm as STARTTLS, which Keycloak
    then fails to send with, and every Forgot password on the install silently sends nothing."""
    assert visible(STARTTLS) == {
        "host": "smtp.example.net",
        "port": "587",
        "from": "brain@example.com",
        "auth": "true",
        "user": "relay-user",
        "starttls": "true",
        "ssl": "false",
    }
    assert (visible(TLS)["starttls"], visible(TLS)["ssl"]) == ("false", "true")
    assert set(visible(STARTTLS)) == set(VISIBLE_KEYS)


def test_what_is_piped_into_kcadm_carries_the_password_and_nothing_else_is_shown_it() -> None:
    """`server` is the one output holding the password; the visible settings never do.

    Delete this and the password could be dropped from the realm's update, which Keycloak keeps
    as the old one, or leak into the part of the settings that is compared and printed."""
    made = server(RELAY, PASSWORD)
    assert made == {"smtpServer": {**visible(STARTTLS), PASSWORD_KEY: PASSWORD}}
    assert PASSWORD not in json.dumps(visible(STARTTLS))


def test_the_realm_s_settings_are_read_as_kcadm_prints_them() -> None:
    """Delete this and a realm with no mail set, which kcadm prints with an empty or no
    smtpServer, would be refused instead of read as holding nothing."""
    assert realm_mail(json.dumps({"smtpServer": {"host": "h", "port": 25}})) == {
        "host": "h",
        "port": "25",
    }
    assert realm_mail("{}") == {}
    assert realm_mail(json.dumps({"smtpServer": {}})) == {}
    for broken in ("not json", "[]", json.dumps({"smtpServer": "h"})):
        with pytest.raises(SignInMailError):
            realm_mail(broken)


# ======================================================================== the decision


def test_no_relay_leaves_the_realm_alone_whatever_it_holds() -> None:
    """**No relay, nothing touched.** Whether the realm holds nothing, settings a person typed by
    hand, or an old relay, the answer is `unset` and the script writes nothing.

    Delete this and an install with no relay would have mail settings somebody set by hand in
    Keycloak overwritten, or cleared, on every deploy."""
    typed_by_hand = {"host": "smtp.someone.example", "port": "25", "auth": "false"}
    for realm in ({}, typed_by_hand, shown(STARTTLS)):
        assert decide(None, realm, None) == UNSET
        assert decide(None, realm, Mirrored(version="v1", host="smtp.example.net")) == UNSET


def test_a_second_run_with_the_same_relay_writes_nothing() -> None:
    """The positive case of idempotence: the realm shows the relay and the relay has not changed
    since it was last given. Delete this and every deploy rewrites the realm's mail settings."""
    mirrored = Mirrored(version="v1", host="smtp.example.net")
    assert decide(RELAY, shown(STARTTLS), mirrored) == SAME


@pytest.mark.parametrize(
    ("realm", "mirrored"),
    [
        pytest.param({}, None, id="a realm with no mail"),
        pytest.param(shown(STARTTLS), None, id="the same settings typed by hand"),
        pytest.param(
            shown(STARTTLS), Mirrored(version="v0", host="smtp.example.net"), id="a new password"
        ),
        pytest.param(
            shown(STARTTLS, host="smtp.old.example"),
            Mirrored(version="v1", host="smtp.example.net"),
            id="a host changed in Keycloak",
        ),
        pytest.param(
            shown(TLS), Mirrored(version="v1", host="smtp.example.net"), id="another security"
        ),
    ],
)
def test_a_changed_relay_or_a_realm_that_drifted_is_written(
    realm: Mapping[str, str], mirrored: Mirrored | None
) -> None:
    """**A changed relay is picked up**: a new password shows only in the relay's digest, since
    Keycloak masks the one it holds, and settings changed in Keycloak by hand are put back.

    Delete this and a relay whose password was replaced keeps sending with the old one, or a
    realm edited by hand never holds the relay again."""
    assert decide(RELAY, realm, mirrored) == WRITE


def test_only_the_visible_settings_are_compared_and_never_the_password() -> None:
    """Delete this and a realm showing its masked password would never match, so every deploy
    would write it."""
    assert matches(STARTTLS, shown(STARTTLS))
    assert matches(STARTTLS, {**shown(STARTTLS), PASSWORD_KEY: "anything"})
    assert not matches(STARTTLS, {**shown(STARTTLS), "user": "someone-else"})


# ======================================================================== the record


@dataclass
class Executed:
    statements: list[Any] = field(default_factory=list)

    async def execute(self, statement: Any) -> None:
        self.statements.append(statement)


def test_what_the_realm_read_back_is_recorded_only_when_it_is_the_relay() -> None:
    """**The record the install check reads is written only for a realm that kept the relay**:
    the relay's digest and the host the realm reported, under `sign_in_mail`, by the release.

    Delete this and a realm that kept another relay, or nothing, could be recorded as given, and
    the install check would pass on it."""
    session = Executed()
    with pytest.raises(SignInMailError, match="did not keep"):
        asyncio.run(sign_in_mail.record(session, RELAY, shown(STARTTLS, host="smtp.other.example")))  # type: ignore[arg-type]
    assert session.statements == []

    asyncio.run(sign_in_mail.record(session, RELAY, shown(STARTTLS)))  # type: ignore[arg-type]
    written = {
        one.compile().params["key"]: one.compile().params["value"] for one in session.statements
    }
    assert written == {"sign_in_mail.version": "v1", "sign_in_mail.host": "smtp.example.net"}
    assert {one.compile().params["updated_by"] for one in session.statements} == {
        sign_in_mail.MIRRORED_BY
    }


# ======================================================================== the command


@dataclass
class Session:
    committed: bool = False

    async def commit(self) -> None:
        self.committed = True


@dataclass
class Password:
    value: str | None = PASSWORD
    reads: int = 0

    def read(self) -> str | None:
        self.reads += 1
        return self.value


@dataclass
class Place:
    relay: Relay | None = RELAY
    mirrored: Mirrored | None = None
    recorded: list[Mapping[str, str]] = field(default_factory=list)
    password: Password = field(default_factory=Password)
    session: Session = field(default_factory=Session)


@pytest.fixture
def place(monkeypatch: pytest.MonkeyPatch) -> Place:
    here = Place()

    class Engine:
        async def dispose(self) -> None:
            return None

    @asynccontextmanager
    async def sessions() -> AsyncIterator[Session]:
        yield here.session

    async def relay_of(session: Any, password: Any) -> Relay | None:
        return here.relay

    async def mirrored_of(session: Any) -> Mirrored | None:
        return here.mirrored

    async def record(session: Any, relay: Relay, realm: Mapping[str, str]) -> None:
        if not matches(relay.settings, realm):
            raise SignInMailError("the sign-in service did not keep the relay's settings")
        here.recorded.append(realm)

    monkeypatch.setattr(sign_in_mail, "_process", lambda: (here.password, Engine(), sessions))
    monkeypatch.setattr(sign_in_mail, "relay_of", relay_of)
    monkeypatch.setattr(sign_in_mail, "mirrored_of", mirrored_of)
    monkeypatch.setattr(sign_in_mail, "record", record)
    return here


def run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], flag: str, stdin: str = ""
) -> tuple[int, str, str]:
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    code = sign_in_mail.main([flag])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_decide_prints_one_word_and_never_the_password(
    place: Place, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Delete this and the script's `case` could be handed a sentence it does not know, or the
    deploy's journal a password."""
    realm = json.dumps({"smtpServer": shown(STARTTLS)})
    assert run(monkeypatch, capsys, "--decide", realm) == (0, "write\n", "")
    place.mirrored = Mirrored(version="v1", host="smtp.example.net")
    assert run(monkeypatch, capsys, "--decide", realm) == (0, "same\n", "")
    place.relay = None
    assert run(monkeypatch, capsys, "--decide", realm) == (0, "unset\n", "")
    assert place.password.reads == 0


def test_server_prints_the_settings_with_the_password_only_to_standard_output(
    place: Place, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """**The one place the password is printed is the pipe into kcadm.** Standard error, which
    the deploy's journal keeps, holds nothing, and no relay or no password is a refusal in words.

    Delete this and the password could reach the journal, or an empty password could be written
    into the realm, which leaves Forgot password sending nothing."""
    code, out, err = run(monkeypatch, capsys, "--server")
    assert (code, err) == (0, "")
    assert json.loads(out) == server(RELAY, PASSWORD)

    place.password.value = None
    code, out, err = run(monkeypatch, capsys, "--server")
    assert (code, out) == (1, "")
    assert "no relay password" in err and PASSWORD not in err
    place.relay = None
    code, out, err = run(monkeypatch, capsys, "--server")
    assert (code, out) == (1, "")


def test_read_back_records_only_a_realm_that_kept_the_relay(
    place: Place, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Delete this and the install check could be told the realm holds the relay when Keycloak
    kept something else, or a write that was refused could be recorded as given."""
    kept = json.dumps({"smtpServer": shown(STARTTLS)})
    code, out, err = run(monkeypatch, capsys, "--read-back", kept)
    assert (code, err) == (0, "")
    assert "smtp.example.net" in out and PASSWORD not in out
    assert place.recorded == [shown(STARTTLS)] and place.session.committed

    place.session.committed = False
    other = json.dumps({"smtpServer": shown(STARTTLS, host="smtp.other.example")})
    code, out, err = run(monkeypatch, capsys, "--read-back", other)
    assert (code, out) == (1, "")
    assert "did not keep" in err
    assert len(place.recorded) == 1 and not place.session.committed


def test_the_command_takes_one_known_flag(
    place: Place, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Delete this and a typo in the script runs a different step than the one it names."""
    assert sign_in_mail.main([]) == 2
    assert sign_in_mail.main(["--write"]) == 2
    assert sign_in_mail.main(["--decide", "--server"]) == 2
    assert run(monkeypatch, capsys, "--decide", "not json")[0] == 1
