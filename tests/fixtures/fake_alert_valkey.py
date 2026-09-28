"""A literal Valkey for `brain.ops.denial_alert_store`: strings with expiries and sorted sets.

Literal where it matters: `zadd` replaces a member that already exists, so writing one alert twice
leaves one member, which is the property the store's writes rest on; `zremrangebyrank` takes the
real negative-index form; and every key comes back from `scan_iter` as bytes, as a client built
with `decode_responses=False` returns it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any


class FakeAlertValkey:
    def __init__(self, *, raises: Exception | None = None) -> None:
        self.strings: dict[str, str] = {}
        self.sets: dict[str, dict[str, float]] = {}
        self.ttls: dict[str, int] = {}
        self.raises = raises

    def _check(self) -> None:
        if self.raises is not None:
            raise self.raises

    def scan_iter(self, match: str | None = None, count: int | None = None) -> Iterator[Any]:
        del count
        self._check()
        prefix = (match or "*").rstrip("*")
        for name in [*self.strings, *self.sets]:
            if name.startswith(prefix):
                yield name.encode("utf-8")

    def get(self, name: str) -> Any:
        self._check()
        found = self.strings.get(name)
        return None if found is None else found.encode("utf-8")

    def set(self, name: str, value: str, ex: int | None = None) -> object:
        self._check()
        self.strings[name] = value
        if ex is not None:
            self.ttls[name] = ex
        return True

    def zadd(self, name: str, mapping: Mapping[str, float]) -> object:
        self._check()
        self.sets.setdefault(name, {}).update(mapping)
        return len(mapping)

    def zremrangebyscore(self, name: str, min: Any, max: Any) -> object:  # noqa: A002
        del min
        members = self.sets.get(name, {})
        for member, score in list(members.items()):
            if score <= float(max):
                del members[member]
        return None

    def zremrangebyrank(self, name: str, min: int, max: int) -> object:  # noqa: A002
        ordered = sorted(self.sets.get(name, {}).items(), key=lambda pair: pair[1])
        doomed = ordered[min : (None if max == -1 else max + 1)]
        for member, _ in doomed:
            del self.sets[name][member]
        return len(doomed)

    def expire(self, name: str, time: int) -> object:
        self.ttls[name] = time
        return True

    def zrevrange(self, name: str, start: int, end: int) -> Any:
        self._check()
        ordered = sorted(self.sets.get(name, {}).items(), key=lambda pair: -pair[1])
        chosen = ordered[start : (None if end == -1 else end + 1)]
        return [member.encode("utf-8") for member, _ in chosen]
