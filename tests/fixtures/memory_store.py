"""An object store held in a dictionary, for the queued-upload tests.

`brain.ops.storage.StorageBackend` is four methods, and a queued upload uses three of them: the
route puts an original and a ticket, the worker gets both and puts the ticket back. This keeps
what was put, with its content type, and raises for a key that was never put, as every backend
does in its own words.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Iterator


class MissingObjectError(KeyError):
    """A key nothing was put under."""


class MemoryStore:
    """`StorageBackend` over a dictionary keyed by bucket and key."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}

    def put_object(self, bucket_name: str, key: str, body: bytes, content_type: str) -> None:
        self.objects[(bucket_name, key)] = (body, content_type)

    def get_object(self, bucket_name: str, key: str) -> bytes:
        try:
            return self.objects[(bucket_name, key)][0]
        except KeyError:
            raise MissingObjectError(key) from None

    def delete_object(self, bucket_name: str, key: str) -> None:
        self.objects.pop((bucket_name, key), None)

    def list_objects(self, bucket_name: str, prefix: str) -> Iterator[str]:
        return iter(
            sorted(
                key
                for bucket, key in self.objects
                if bucket == bucket_name and key.startswith(prefix)
            )
        )

    def names(self) -> list[str]:
        return sorted(key for _, key in self.objects)
