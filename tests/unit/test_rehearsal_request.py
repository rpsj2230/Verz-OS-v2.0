"""The request for a rehearsal: its body, finding it among a bucket's other objects, and putting it.

The dates are 2999 for the reason CLAUDE.md records.

Task ids: M30.3.9
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from brain.ops.backup_manifest import DRILL_SUFFIX, MANIFEST_SUFFIX
from brain.ops.drill_service import REQUEST_KEY
from brain.ops.rehearsal_request import Pending, pending_in, put_request, request_body

AT = datetime(2999, 6, 15, 12, 0, tzinfo=UTC)
OTHERS = (
    (f"database-1{MANIFEST_SUFFIX}", json.dumps({"backup_id": "database-1"})),
    (f"database-1-drill-1{DRILL_SUFFIX}", json.dumps({"backup_id": "database-1"})),
)


def test_a_listing_with_no_request_among_other_objects_has_no_pending_request() -> None:
    """Only the request's own name counts. Delete this and any manifest or record in the bucket
    reads as a request nobody has answered, and the button is disabled for ever."""
    assert pending_in(OTHERS) is None
    assert pending_in(()) is None


def test_the_request_is_found_among_other_objects_with_its_time_and_who_asked() -> None:
    """The positive sibling. Delete this and a request is never seen once the bucket holds
    anything else."""
    body = request_body(at=AT, by="u_example").decode()
    assert pending_in((*OTHERS, (REQUEST_KEY, body))) == Pending(at=AT, by="u_example")


@pytest.mark.parametrize(
    "content",
    ["not json", "{}", '{"requested_at": "2999-06-15T12:00:00", "requested_by": "u"}', "[]"],
)
def test_a_request_that_cannot_be_read_is_still_waiting_with_no_time(content: str) -> None:
    """The service answers the object and not its content. Delete this and a hand-made file the
    service will act on is hidden from the screen."""
    assert pending_in(((REQUEST_KEY, content),)) == Pending(at=None, by=None)


def test_a_request_with_no_offset_on_its_time_is_refused_to_be_written() -> None:
    """Delete this and the screen shows the time at this machine's offset."""
    with pytest.raises(ValueError):
        request_body(at=datetime(2999, 1, 1), by="u_example")


def test_putting_a_request_writes_one_object_under_the_request_key_in_the_backup_bucket() -> None:
    """Delete this and the request is left under a key the service never looks at."""
    puts: list[tuple[str, str, bytes, str]] = []

    class Backend:
        def put_object(self, bucket_name: str, key: str, body: bytes, content_type: str) -> None:
            puts.append((bucket_name, key, body, content_type))

        def get_object(self, bucket_name: str, key: str) -> bytes:
            raise AssertionError

        def delete_object(self, bucket_name: str, key: str) -> None:
            raise AssertionError

        def list_objects(self, bucket_name: str, prefix: str) -> list[str]:
            raise AssertionError

    put_request(Backend(), at=AT, by="u_example")  # type: ignore[arg-type]
    [(bucket, key, body, kind)] = puts
    assert (bucket, key, kind) == ("backups", REQUEST_KEY, "application/json")
    assert json.loads(body)["requested_by"] == "u_example"
