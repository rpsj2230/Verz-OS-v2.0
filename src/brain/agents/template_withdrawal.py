"""Withdrawing a template version from new installs, undoing it, and moving a template across.

`brain.agents.template` says a published version is signed once and never amended, and
`agent.template_version` is SELECT and INSERT only, so the three things an administrator needs of a
template that has been published (stop offering it, offer it again, hand it to another install) are
not edits. This module decides each of them as a value and writes nothing; `brain.ops.
template_withdrawal_store` keeps the rows and `brain.template_withdrawal_routes` is the door.

**A withdrawal is a row and so is its undoing, and the newest row is the state.** The version's own
row is untouched, so a withdrawn version is still a signed body with a digest, and `Withdrawal` is
`brain.console.skill_library.Retirement`'s shape for a template. Rejected: a `withdrawn_at` column
on the version, which an insert-only table cannot take and which would make the digest's neighbour
an editable fact; a delete, which no grant allows and which would leave every pinned instance
pointing at a row that is gone. See `A_WITHDRAWAL_IS_A_ROW_AND_NEVER_AN_EDIT`.

**An installed agent stays pinned, and that is structural.** An instance is pinned by the version's
digest through `agent.template_instance`, and nothing here reads or writes it; the withdrawal is
consulted only where something is about to be *offered* (the gallery, a version's install, an
upgrade). An agent whose version was withdrawn runs, is shown, is duplicated and is read exactly
as before. See `AN_INSTALLED_AGENT_STAYS_PINNED_TO_WHAT_IT_WAS_INSTALLED_FROM`.

**A document that leaves is the signed version and a document that arrives is a candidate.** The
export is the version as it is stored: the manifest, its digest, the signature and who signed it.
The signature is an HMAC under the exporting install's own key (`brain.agents.template._signature`
says why it is symmetric: the question it answers is whether this install's publishing path made
the manifest), so **no other install can verify it**, and a second install holding the document can
prove only that the body still digests to what the document says, which anybody editing it could
recompute. So an arrival is never trusted as signed: it is read, its digest checked for damage,
scanned for company details, and then signed *by the install importing it* as a version of its own,
which is what installing from it later verifies. Rejected: importing a document verbatim and
installing from it, which needs the exporter's key on the importer, and a key shared between two
companies proves nothing about which of them wrote a manifest. What would make the exporter's
signature checkable elsewhere is a public-key signature and a list of installs a company trusts,
which is `docs/needs-rupash.md`'s question and not decided here. See
`AN_EXPORT_IS_SIGNED_BY_THE_INSTALL_THAT_MADE_IT_AND_CHECKABLE_BY_NO_OTHER`.

**An arrival never joins a lineage already on the install.** It lands as version one of an id this
install does not hold, or it is the version already there; an id the install holds with other
contents, and the ids the product ships, are refused. Joining one would hand every agent installed
from that lineage an upgrade offer written by a document from somewhere else.

Task ids: M27.15.35
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from pydantic import JsonValue, ValidationError

from brain.agents.authoring import LeakItem, LiteralKind, scan
from brain.agents.catalogue import CATALOGUE
from brain.agents.template import (
    BLANK_TEMPLATE_ID,
    SignedManifest,
    TemplateError,
    TemplateManifest,
    manifest_from_document,
)

#: The leak scan's kinds that are a company's own detail: the shaped ones, never a whole paragraph
#: or a bare name. The agent import's `SHAPED`, written again here because a domain module does
#: not import a route module for a constant.
SHAPED_LITERALS: Final[frozenset[LiteralKind]] = frozenset(
    {LiteralKind.EMAIL, LiteralKind.URL, LiteralKind.MONEY, LiteralKind.PHONE, LiteralKind.CODE}
)

#: The two identity paths an import never reads as a company's detail. The template's id is its
#: name and is shaped like a code whenever it has digits in it, and the publisher is replaced by the
#: importer (`arrival`), so neither is carried and neither says anything about who wrote the rest.
#: The agent import reads the same two the same way.
IDENTITY_PATHS_THAT_ARE_NOT_DETAILS: Final[frozenset[str]] = frozenset(
    {"identity.template_id", "identity.published_by"}
)

# ------------------------------------------------------------------ written-down reasons
#: Why withdrawing is a row and not an edit.
A_WITHDRAWAL_IS_A_ROW_AND_NEVER_AN_EDIT: Final = (
    "A published template version is signed once and never amended, and every agent installed "
    "from it pins its digest, so hiding it from new installs is a new row beside it and undoing "
    "that is another. The newest row is the state; the rows before it are what it was. Nothing is "
    "updated and nothing is deleted."
)

#: Why a withdrawal leaves installed agents alone.
AN_INSTALLED_AGENT_STAYS_PINNED_TO_WHAT_IT_WAS_INSTALLED_FROM: Final = (
    "A withdrawal decides what is offered to a new install. An agent already installed names the "
    "version it was made from by digest, so it is read, run and duplicated exactly as before, and "
    "is neither moved to another version nor stopped by it."
)

#: Why a signed export cannot be verified by the install that receives it.
AN_EXPORT_IS_SIGNED_BY_THE_INSTALL_THAT_MADE_IT_AND_CHECKABLE_BY_NO_OTHER: Final = (
    "A template is signed with its install's own key, and nothing else holds that key. A document "
    "from another install therefore proves only that its body still matches the digest it carries, "
    "which anybody editing it can recompute, so an arrival is read, scanned and signed again by "
    "the install importing it, and what it was signed with elsewhere is reported and trusted for "
    "nothing."
)

#: What the schema of an exported document is called.
EXPORT_SCHEMA: Final = "brain.template.export.v1"

#: The longest reason a person may give, which is a sentence and not a document.
REASON_CHARS: Final = 240

#: The sentences a refusal says. Each is one literal, so a route may serve it as it is.
NO_REASON_GIVEN: Final = (
    "A withdrawal says why, in a sentence, so the people reading the list can tell."
)
REASON_TOO_LONG: Final = "The reason is longer than a sentence. Shorten it to 240 characters."
ALREADY_WITHDRAWN: Final = "This version is already withdrawn, so nothing was changed."
NOT_WITHDRAWN: Final = "This version is not withdrawn, so there is nothing to undo."
NOT_A_TEMPLATE_DOCUMENT: Final = (
    "That is not a template document this install can read, so nothing was imported."
)
DOCUMENT_WAS_CHANGED: Final = (
    "The document's body does not match the digest it carries, so it was changed after it was "
    "exported. Nothing was imported."
)
NOT_A_NAME_THIS_INSTALL_MAY_TAKE: Final = (
    "This install ships or already holds a different template under that id, so nothing was "
    "imported. Export it again under another id."
)
COMPANY_DETAILS_IN_THE_DOCUMENT: Final = (
    "The document holds details that look like a company's own (an address, a link, an amount, a "
    "number or a code), so nothing was imported. They are named by kind and place below."
)

#: A control character in a reason, which a page would draw as nothing and a log as a line break.
_CONTROL: Final = re.compile(r"[\x00-\x1f\x7f]")


class TemplateWithdrawalError(TemplateError):
    """A withdrawal, an undo or a transfer was asked in a shape nothing should be written from."""


@dataclass(frozen=True)
class Withdrawal:
    """One change to whether a version is offered: withdrawn from `at`, or the withdrawal undone."""

    template_id: str
    version: int
    withdrawn: bool
    set_by: str
    at: datetime
    reason: str = ""


def reason_of(said: str) -> str:
    """A reason as it is kept: trimmed, one sentence long, with no control characters in it.

    Refused rather than cut when too long, because a reason shortened without its writer seeing
    it says something its writer did not write.
    """
    kept = _CONTROL.sub(" ", said).strip()
    if not kept:
        raise TemplateWithdrawalError(NO_REASON_GIVEN)
    if len(kept) > REASON_CHARS:
        raise TemplateWithdrawalError(REASON_TOO_LONG)
    return kept


def withdrawing(current: Withdrawal | None, *, withdraw: bool) -> None:
    """Refuse a change that changes nothing: withdrawing what is withdrawn, undoing what is not.

    `current` is the newest row for the version, or None for a version never withdrawn. Without
    this the history reads a version withdrawn twice, and the second row says nothing a person who
    pressed the button twice did not already know.
    """
    standing = current is not None and current.withdrawn
    if withdraw and standing:
        raise TemplateWithdrawalError(ALREADY_WITHDRAWN)
    if not withdraw and not standing:
        raise TemplateWithdrawalError(NOT_WITHDRAWN)


def withdrawn_keys(newest: Mapping[tuple[str, int], Withdrawal]) -> frozenset[tuple[str, int]]:
    """The versions that are withdrawn now, from the newest row of each."""
    return frozenset(key for key, one in newest.items() if one.withdrawn)


def fully_withdrawn(
    on_file: Iterable[tuple[str, int]], withdrawn: frozenset[tuple[str, int]]
) -> frozenset[str]:
    """The template ids every stored version of which is withdrawn.

    The gallery falls back to the product's own card for an id nothing published stands behind, so
    an id whose published versions are all withdrawn would reappear as a built-in card that cannot
    be installed. Nothing on file for an id is not this: it is a template that ships and was never
    signed here, and it stays listed.
    """
    stored: dict[str, list[bool]] = {}
    for key in on_file:
        stored.setdefault(key[0], []).append(key in withdrawn)
    return frozenset(one for one, states in stored.items() if all(states))


# ----------------------------------------------------------------------- the document
def export_document(signed: SignedManifest) -> dict[str, JsonValue]:
    """A signed version as a document: what is stored of it, and nothing about who asked.

    The manifest is `TemplateManifest.document()`, the flat map a signature is taken over, so the
    digest in the document is the digest of exactly the body in it. No instance, overlay or answer
    to a placeholder is in it: a manifest has none, and `brain.agents.authoring` argues why.
    """
    document: dict[str, JsonValue] = {
        "schema": EXPORT_SCHEMA,
        "manifest": dict(signed.manifest.document()),
        "content_digest": signed.content_digest,
        "signature": signed.signature,
        "signed_by": signed.signed_by,
        "signed_at": signed.signed_at.isoformat(),
        "schema_version": signed.schema_version,
        "overview_path": signed.overview_path,
    }
    return document


def read_export(document: Mapping[str, Any]) -> SignedManifest:
    """A document as the signed version it claims to be, or a refusal that says which way it failed.

    The signature is not checked here, because nothing but the install that made it can: see
    `AN_EXPORT_IS_SIGNED_BY_THE_INSTALL_THAT_MADE_IT_AND_CHECKABLE_BY_NO_OTHER`. What is checked
    is that it is the shape this release writes and that the body digests to what the document
    says, which `SignedManifest` recomputes on construction.
    """
    if document.get("schema") != EXPORT_SCHEMA:
        raise TemplateWithdrawalError(NOT_A_TEMPLATE_DOCUMENT)
    body = document.get("manifest")
    if not isinstance(body, dict):
        raise TemplateWithdrawalError(NOT_A_TEMPLATE_DOCUMENT)
    try:
        manifest = manifest_from_document(body)
        signed_at = datetime.fromisoformat(str(document["signed_at"]))
        return SignedManifest(
            manifest=manifest,
            content_digest=str(document["content_digest"]),
            signature=str(document["signature"]),
            signed_by=str(document["signed_by"]),
            signed_at=signed_at,
            schema_version=int(document.get("schema_version") or 1),
            overview_path=str(document.get("overview_path") or ""),
        )
    except (KeyError, TypeError, ValueError, ValidationError) as damaged:
        # `SignedManifest` refuses a body that does not digest to its own digest with a
        # `ValueError`, and a missing or mistyped field is the others.
        if "was edited after it was signed" in str(damaged):
            raise TemplateWithdrawalError(DOCUMENT_WAS_CHANGED) from None
        raise TemplateWithdrawalError(NOT_A_TEMPLATE_DOCUMENT) from None


def company_details(manifest: TemplateManifest) -> tuple[LeakItem, ...]:
    """The shaped literals in a document's body: an address, a link, an amount, a number, a code.

    `brain.agents.authoring.scan`'s items of a shaped kind, which is what the agent import also
    puts in front of its person, less the template's id and its publisher, which an import never
    carries as anything but a name (`IDENTITY_PATHS_THAT_ARE_NOT_DETAILS`). Prose is not among them:
    a company's name written into a persona is something a person reads for, and the import's own
    confirmation step is where they do.
    """
    return tuple(
        one
        for one in scan(manifest.document()).items
        if one.kind in SHAPED_LITERALS
        and not set(one.locations) <= IDENTITY_PATHS_THAT_ARE_NOT_DETAILS
    )


def may_take_the_name(
    manifest: TemplateManifest, held: Mapping[int, TemplateManifest] | None
) -> bool:
    """Whether this install can hold a template under the document's id.

    Not the blank one and not one this release ships, which a published row would hide the card of;
    and not an id the install holds with other contents, which an import would otherwise extend
    with a version written elsewhere. The same contents under the same id are what `same_body`
    calls an import already made.
    """
    one = manifest.identity.template_id
    if one == BLANK_TEMPLATE_ID or any(
        one == shipped.identity.template_id for shipped in CATALOGUE
    ):
        return False
    return held is None or any(same_body(manifest, then) for then in held.values())


def same_body(one: TemplateManifest, other: TemplateManifest) -> bool:
    """Whether two manifests are one template, ignoring which version and who published them."""
    skipped = {"identity.version", "identity.published_by"}
    first, second = one.document(), other.document()
    return {k: v for k, v in first.items() if k not in skipped} == {
        k: v for k, v in second.items() if k not in skipped
    }


def arrival(received: SignedManifest, *, by: str) -> TemplateManifest:
    """The manifest this install publishes for a document: version one, published by the importer.

    The identity is the one thing that changes, which is what a lineage on this install needs, and
    every other path is the document's. The leash and the ceiling are the document's too, so a
    version that starts above Shadow is refused where every version is, at install.
    """
    identity = received.manifest.identity.model_copy(update={"version": 1, "published_by": by})
    return received.manifest.model_copy(update={"identity": identity})
