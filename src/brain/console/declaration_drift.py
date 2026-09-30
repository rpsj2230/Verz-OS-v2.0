"""What changed in a source's declaration since its connection was agreed, in plain words.

A release can change what a shipped connector does: an operation added, a field kept in its index,
a description saying it now reads a ticket's body. A connection agreed under the old declaration is
then no longer read until a person with the installation authority accepts the new one, and that
acceptance is deliberate by the registry's rule (`brain.connectors.registry`: upgrade is
deliberate, reconnect never clears it). The Connectors screen showed a "Declaration changed" pill
and nothing else, so the person accepted a change they were never shown. This is what they are
shown.

**Computed here, from the declaration agreed and the declaration now, and never in the browser.**
Since `0157` a connection keeps the canonical text its digest is the hash of
(`brain.connectors.manifest.digest_input`). That text is believed only when its SHA-256 is the
pinned digest, so a row edited by hand cannot put words in front of somebody about to accept. The
current declaration's text is built the same way, and the two are compared field by field: the
operations (a tool, by name, with its description and whether it writes), the entities indexed and
each field kept, and the few settings of the whole (what it is pinned to, its ceiling, how it is
reached, what the source says about who may see a row). See
`A_CHANGE_IS_SHOWN_BEFORE_IT_IS_ACCEPTED`.

**The words are the declaration's own.** An operation is described by its own description, which
is written for exactly this reader; a field by its entity and its name. Nothing here paraphrases a
connector, so a connector's author controls what a person reads when they accept it.

**A connection agreed before `0157` has no agreed text**, or one that no longer hashes to its pin.
Then nothing can say what changed, and inventing a diff would be worse than none: the screen says
the old declaration was not kept and lists everything the new one does, so what is accepted is
still read in full first. See `WHAT_WAS_AGREED_WAS_NOT_KEPT`.

Rejected: sending both declarations to the console and comparing them there. The browser would hold
the rule for what counts as a change, a second copy of it, and the one a person reads would be the
one nobody tests against the connectors.

Task ids: M27.11.9, M33.5.1.1
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from brain.connectors.manifest import ConnectorManifest, digest_input

# ------------------------------------------------------------------ written-down reasons

#: Why the screen lists what changed before the accept is offered.
A_CHANGE_IS_SHOWN_BEFORE_IT_IS_ACCEPTED: Final = (
    "A source whose declaration changed is not read until a person with the installation "
    "authority accepts the new one. What they accept is listed first, computed on the server from "
    "the declaration the connection agreed to and the one this release ships, in the declaration's "
    "own words, so nobody accepts a change they were not shown."
)

#: What the screen says when the agreed declaration was not kept.
WHAT_WAS_AGREED_WAS_NOT_KEPT: Final = (
    "This connection was agreed before this system kept what was agreed, so what changed cannot "
    "be listed. Everything the source does under this release is listed instead: read it before "
    "accepting."
)

#: What accepting does, said on its confirmation.
ACCEPTING_A_CHANGED_DECLARATION: Final = (
    "The connection is agreed again under this release's declaration, with the same settings and "
    "the same key, and is read again from its next run. The ledger records the change with the "
    "digest agreed before and the one agreed now."
)

#: The parts of a declaration outside its operations and entities, with the words for each.
WHOLE: Final[Mapping[str, str]] = {
    "scope": "What it is pinned to",
    "ceiling": "Its call ceiling",
    "transport": "How it is reached",
    "permission_sync": "What the source tells this system about who may see a row",
    "name": "Its name",
}

#: How each kind of change is shown.
ADDED: Final = "added"
REMOVED: Final = "removed"
CHANGED: Final = "changed"


@dataclass(frozen=True)
class DriftLine:
    """One change, as a sentence, and for a changed thing what it said before."""

    kind: str
    what: str
    was: str = ""


@dataclass(frozen=True)
class DeclarationDrift:
    """What changed, when it can be said, or everything the declaration does now when it cannot."""

    #: Whether the agreed declaration was kept and still hashes to the pinned digest.
    known: bool
    lines: tuple[DriftLine, ...]
    #: Everything the current declaration does, in words, when `known` is False.
    now_does: tuple[str, ...]
    was_version: str
    now_version: str


def agreed_declaration(agreed: str, pinned_digest: str) -> Mapping[str, Any] | None:
    """The agreed declaration, parsed, only when its SHA-256 is the pin. None otherwise."""
    if not agreed or hashlib.sha256(agreed.encode("utf-8")).hexdigest() != pinned_digest:
        return None
    parsed = json.loads(agreed)
    return parsed if isinstance(parsed, Mapping) else None


def _words(name: str) -> str:
    return name.replace("_", " ")


def _by(items: object, key: str) -> dict[str, Mapping[str, Any]]:
    found: dict[str, Mapping[str, Any]] = {}
    if isinstance(items, Sequence):
        for one in items:
            if isinstance(one, Mapping) and isinstance(one.get(key), str):
                found[one[key]] = one
    return found


def _describe(tool: Mapping[str, Any]) -> str:
    text = str(tool.get("description") or tool.get("name") or "")
    return text if tool.get("side_effect") in (None, "none") else f"{text} It changes the source."


def _tool_lines(was: Mapping[str, Any], now: Mapping[str, Any]) -> list[DriftLine]:
    before, after = _by(was.get("tools"), "name"), _by(now.get("tools"), "name")
    lines = [
        DriftLine(ADDED, f"Now also: {_describe(after[name])}")
        for name in after
        if name not in before
    ]
    lines += [
        DriftLine(REMOVED, f"No longer: {_describe(before[name])}")
        for name in before
        if name not in after
    ]
    lines += [
        DriftLine(CHANGED, f"Now: {_describe(after[name])}", _describe(before[name]))
        for name in after
        if name in before and after[name] != before[name]
    ]
    return lines


def _fields(entity: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return _by(entity.get("fields"), "name")


def _entity_lines(was: Mapping[str, Any], now: Mapping[str, Any]) -> list[DriftLine]:
    before, after = _by(was.get("projections"), "entity"), _by(now.get("projections"), "entity")
    lines: list[DriftLine] = []
    for name, entity in after.items():
        fields = ", ".join(_words(one) for one in _fields(entity))
        if name not in before:
            lines.append(
                DriftLine(ADDED, f"Now also keeps an index of each {_words(name)}: {fields}")
            )
            continue
        old, new = _fields(before[name]), _fields(entity)
        lines += [
            DriftLine(ADDED, f"Now also keeps in its index: a {_words(name)}'s {_words(field)}")
            for field in new
            if field not in old
        ]
        lines += [
            DriftLine(REMOVED, f"No longer keeps: a {_words(name)}'s {_words(field)}")
            for field in old
            if field not in new
        ]
        lines += [
            DriftLine(
                CHANGED,
                f"Uses a {_words(name)}'s {_words(field)} to "
                f"{', '.join(new[field].get('uses') or ()) or 'nothing'}",
                ", ".join(old[field].get("uses") or ()) or "nothing",
            )
            for field in new
            if field in old and new[field] != old[field]
        ]
        if entity.get("visibility") != before[name].get("visibility"):
            lines.append(
                DriftLine(CHANGED, f"Who may be told each {_words(name)} is decided differently")
            )
    lines += [
        DriftLine(REMOVED, f"No longer keeps an index of each {_words(name)}")
        for name in before
        if name not in after
    ]
    return lines


def _whole_lines(was: Mapping[str, Any], now: Mapping[str, Any]) -> list[DriftLine]:
    lines: list[DriftLine] = []
    for key, label in WHOLE.items():
        if was.get(key) == now.get(key):
            continue
        if isinstance(now.get(key), str) and isinstance(was.get(key), str):
            lines.append(DriftLine(CHANGED, f"{label}: {now[key]}", str(was[key])))
        else:
            lines.append(DriftLine(CHANGED, f"{label} changed"))
    return lines


def now_does(current: Mapping[str, Any]) -> tuple[str, ...]:
    """Everything a declaration does, in words: each operation, then what each entity keeps."""
    tools = [_describe(one) for one in _by(current.get("tools"), "name").values()]
    kept = [
        f"Keeps in its index of each {_words(name)}: "
        + ", ".join(_words(field) for field in _fields(entity))
        for name, entity in _by(current.get("projections"), "entity").items()
    ]
    return (*tools, *kept)


def drift(agreed: str, pinned_digest: str, current: ConnectorManifest) -> DeclarationDrift:
    """What changed between the declaration agreed and `current`. See the module docstring."""
    now = json.loads(digest_input(current))
    was = agreed_declaration(agreed, pinned_digest)
    now_version = str(now.get("version") or "")
    if was is None:
        return DeclarationDrift(
            known=False, lines=(), now_does=now_does(now), was_version="", now_version=now_version
        )
    lines = (*_tool_lines(was, now), *_entity_lines(was, now), *_whole_lines(was, now))
    return DeclarationDrift(
        known=True,
        lines=tuple(lines),
        now_does=(),
        was_version=str(was.get("version") or ""),
        now_version=now_version,
    )
