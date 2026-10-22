"""A request whose write meets a full disk is told so in a sentence, and any other error is not.

The application is the real one with one route added that raises what each fault raises at the
database driver and the operating system. Every refusal has a sibling that still fails as before:
a handler that answered every database error with the full-disk sentence would pass the first half.

Task ids: M30.4.5
"""

from __future__ import annotations

import errno

import psycopg.errors
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from brain.app import Settings, create_app
from brain.ops.reliability import WriteRefusedForSpace


def served(error: BaseException) -> TestClient:
    app = create_app(Settings(env="development"))

    @app.get("/api/v1/fault-for-the-disk-test")
    async def fault() -> None:
        raise error

    return TestClient(app, raise_server_exceptions=False)


def driver_disk_full() -> OperationalError:
    return OperationalError("INSERT", {}, psycopg.errors.DiskFull("could not extend file"))


@pytest.mark.parametrize(
    "error",
    [driver_disk_full(), OSError(errno.ENOSPC, "No space left on device")],
    ids=["database", "operating-system"],
)
def test_a_write_that_meets_a_full_disk_is_a_503_with_the_stated_sentence(
    error: BaseException,
) -> None:
    """Both ways a full disk arrives. Delete this and a person is told something went wrong by a
    500 that names nothing, on the one fault whose cure is a single command."""
    with served(error) as client:
        answer = client.get("/api/v1/fault-for-the-disk-test")
    assert answer.status_code == 503
    body = answer.json()
    assert body["message"] == WriteRefusedForSpace.public_message
    assert (
        "53100" not in answer.text and "No space" not in answer.text and "INSERT" not in answer.text
    )
    assert "trace_id" in body


def test_the_sentence_does_not_claim_nothing_was_saved() -> None:
    """A request may have kept an earlier step. Delete this and the sentence promises a clean
    failure the request path cannot give."""
    assert "may not have been saved" in WriteRefusedForSpace.public_message


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("INSERT", {}, psycopg.errors.UndefinedTable("no such table")),
        OSError(errno.ENOENT, "No such file"),
    ],
    ids=["database", "operating-system"],
)
def test_any_other_database_or_operating_system_error_fails_as_it_did(
    error: BaseException,
) -> None:
    """The sibling. Delete this and every database error is called a full disk, which sends an
    administrator to free space on a server that has plenty."""
    with served(error) as client:
        answer = client.get("/api/v1/fault-for-the-disk-test")
    assert answer.status_code == 500
    assert WriteRefusedForSpace.public_message not in answer.text
