"""Nothing of a database URL or its password survives `brain.ops.safe_error`.

Task ids: M38.5.1
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr
from datetime import UTC, datetime

import psycopg
import pytest

from brain.ops import post_deploy
from brain.ops.safe_error import REDACTED, describe, redact, url_password

#: The shape found on the owner's install: a bare `%` libpq refuses, and a `$` beside it.
PASSWORD = "Zq7%kx$Pw9r!Lm%4v"
URL = f"postgresql://brain_app:{PASSWORD}@db.internal:5432/brain?sslmode=require"


def _pieces_of_the_password() -> list[str]:
    """Every run of three or more characters from the password: none may appear in an output."""
    return [PASSWORD[i : i + 3] for i in range(len(PASSWORD) - 2)]


def _assert_nothing_of_the_password(text: str) -> None:
    assert PASSWORD not in text
    for piece in _pieces_of_the_password():
        assert piece not in text, (piece, text)
    assert "db.internal" not in text
    assert "brain_app" not in text


def _the_real_driver_error() -> psycopg.Error:
    """psycopg's own refusal of this URL, raised locally: conninfo is parsed before any socket."""
    with pytest.raises(psycopg.Error) as caught:
        psycopg.connect(URL)
    return caught.value


def test_the_driver_really_quotes_the_password_back() -> None:
    """The premise. If psycopg stops echoing the password, the tests below prove nothing new, and
    this goes red to say so rather than leaving them green over a message with nothing to hide."""
    message = str(_the_real_driver_error())
    assert any(piece in message for piece in _pieces_of_the_password())


def test_describe_keeps_the_class_and_none_of_the_password() -> None:
    """Delete this and the post-deploy log line that leaked on 2026-09-21 has no test at all."""
    described = describe(_the_real_driver_error(), secrets=[PASSWORD])

    assert described.startswith("ProgrammingError: ")
    _assert_nothing_of_the_password(described)


def test_describe_removes_the_password_without_being_told_it() -> None:
    """The quoted literal is what libpq refused, so it goes even when no secret is known: a call
    site cannot forget to pass the password it does not have."""
    _assert_nothing_of_the_password(describe(_the_real_driver_error()))


@pytest.mark.parametrize(
    "message",
    [
        f"could not connect to {URL}",
        f"connection failed: host=db.internal user=brain_app password={PASSWORD} dbname=brain",
        f"connection failed: brain_app:{PASSWORD}@db.internal:5432",
        f"Value error, database_url={URL!r} is not accepted",
        f'missing "=" after "{PASSWORD}" in connection info string',
        f"invalid percent-encoded token: {PASSWORD}",
    ],
)
def test_every_shape_a_connection_string_arrives_in_is_removed(message: str) -> None:
    """One per way a driver, libpq or pydantic has been seen to echo a connection string."""
    _assert_nothing_of_the_password(describe(RuntimeError(message), secrets=[PASSWORD]))


def test_a_message_with_nothing_secret_keeps_its_sentence() -> None:
    """The positive case: a redactor that blanked everything would pass every test above."""
    assert describe(ValueError("the queue was not installed")) == (
        "ValueError: the queue was not installed"
    )
    assert redact("no URL here") == "no URL here"
    assert describe(KeyError()) == "KeyError"


def test_the_password_is_read_out_of_a_url_libpq_refuses() -> None:
    assert url_password(URL) == PASSWORD
    assert url_password("postgresql://brain@db/brain") == ""
    assert url_password("host=db") == ""


def test_the_post_deploy_verdict_log_carries_no_part_of_the_password() -> None:
    """The exact path that leaked: a check raising the driver's error inside `run_checks`."""

    def leaking_check() -> None:
        psycopg.connect(URL)

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        verdict = post_deploy.run_checks(
            "abc123",
            rls=leaking_check,
            canaries=lambda: None,
            schema=leaking_check,
            invariants=leaking_check,
            now=datetime(2999, 1, 1, tzinfo=UTC),
        )

    logged = stderr.getvalue()
    assert "ProgrammingError" in logged
    assert REDACTED in logged
    _assert_nothing_of_the_password(logged)
    _assert_nothing_of_the_password(str(verdict))
    assert verdict.rls == post_deploy.FAILED
