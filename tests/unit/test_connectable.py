"""Which sources the console can connect, what each asks for, and the connector's own refusals.

`brain.ops.connectable` is a list of the product's connectors, and the failure worth testing first
is the list drifting from the connectors: a connector added to `brain.connectors` with no decision
here would be silently missing from the screen, and a source listed here whose manifest names
another source would connect one thing under another's name. Then the refusals, each with a
sibling that builds.

Task ids: M42.6.5
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from pathlib import Path
from typing import Final

import pytest

import brain.connectors
from brain.connectors.contract import AccessMode
from brain.connectors.manifest import manifest_digest
from brain.connectors.write_verification import builds_a_manifest
from brain.ops.connectable import (
    CONNECTABLE,
    MAX_SETTING_CHARS,
    NOT_FROM_THE_CONSOLE,
    READING_ROLE,
    NotConnectableError,
    blank_sentence,
    connectable,
    given,
    key_reference,
    manifest_for,
    settings_problems,
)
from brain.ops.credentials import CONNECTOR_NAME_PATTERN
from brain.ops.openbao import CONNECTOR_KEY_PREFIX
from brain.ops.secrets import VaultRole

REPO: Final = Path(__file__).resolve().parents[2]
SLOTS_DOC: Final = REPO / "ops" / "openbao" / "credential-slots.md"

#: One identifier per connectable source, shaped as the source's own would be and naming nobody.
IDENTIFIERS: Final = {
    "xero": "11111111-2222-3333-4444-555555555555",
    "hubspot": "12345678",
}


def settings_for(name: str, value: str | None = None) -> dict[str, str]:
    return {CONNECTABLE[name].settings[0].name: IDENTIFIERS[name] if value is None else value}


def modules_that_build_a_manifest() -> set[str]:
    """Read off the package, as `brain.connectors.write_verification.connectors` reads it."""
    found: set[str] = set()
    for info in pkgutil.iter_modules(brain.connectors.__path__):
        module = importlib.import_module(f"brain.connectors.{info.name}")
        if builds_a_manifest(module):
            found.add(info.name)
    return found


# ------------------------------------------------------------------ the list and the package


def test_every_connector_the_package_builds_is_decided_here_exactly_once() -> None:
    """Delete this and a connector added to `brain.connectors` is absent from the screen with
    nothing saying why, or a source is both offered and explained away. The package is read, not
    listed, and the count is asserted so an empty discovery cannot pass."""
    built = modules_that_build_a_manifest()

    assert len(built) >= 7
    assert not set(CONNECTABLE) & set(NOT_FROM_THE_CONSOLE)
    assert set(CONNECTABLE) | set(NOT_FROM_THE_CONSOLE) == built


@pytest.mark.parametrize("name", sorted(CONNECTABLE))
def test_a_connectable_source_builds_a_manifest_under_its_own_name_bound_to_its_own_slot(
    name: str,
) -> None:
    """The manifest's name is compared with the source's name and its module's own constant, not
    with the list's key alone, and its credential with the slot rule. Delete this and a source
    listed as one connector can build another's manifest, or bind its key somewhere the vault
    policy does not grant, and read-only can quietly stop being the binding."""
    module = importlib.import_module(f"brain.connectors.{name}")
    manifest = manifest_for(name, settings_for(name))

    assert manifest.name == name == module.CONNECTOR_NAME
    assert re.fullmatch(CONNECTOR_NAME_PATTERN, name)
    assert manifest.credential.ref.path == f"{CONNECTOR_KEY_PREFIX}{name}"
    assert manifest.credential.ref.role is VaultRole.WORKER is READING_ROLE
    assert manifest.credential.mode is AccessMode.READ_ONLY
    assert IDENTIFIERS[name] in manifest.scope.selectors
    assert key_reference(name) == manifest.credential.ref


@pytest.mark.parametrize("name", sorted(CONNECTABLE))
def test_a_source_s_key_hint_asks_for_exactly_the_scopes_its_slot_row_asks_for(name: str) -> None:
    """The scopes an administrator is told to request are the ones `credential-slots.md` argued for
    that connector. Delete this and the form's hint drifts from the document, and the scope asked
    for on install day is whichever one somebody last typed."""
    row = next(
        line
        for line in SLOTS_DOC.read_text(encoding="utf-8").splitlines()
        if line.startswith(f"| `connectors/creds/{name}`")
    )
    requested = row.split("|")[3]
    scopes = re.findall(r"`([a-z.]+)`", requested)

    assert scopes
    for scope in scopes:
        assert scope in CONNECTABLE[name].credential_hint


def test_every_source_the_console_cannot_connect_says_why_in_words() -> None:
    """Delete this and a reason can be left blank, which draws a source on the screen with nothing
    saying what connecting it would need."""
    for one in NOT_FROM_THE_CONSOLE.values():
        assert one.name and one.label
        # Lark's two are connected by Connect Lark on the same screen; the rest at the server.
        where = "Connect Lark" if one.name.startswith("lark_") else "connected at the server"
        assert where in one.why
    with pytest.raises(NotConnectableError):
        connectable("freshdesk")
    assert connectable("xero") is CONNECTABLE["xero"]


# ------------------------------------------------------------------------- the refusals


@pytest.mark.parametrize("name", sorted(CONNECTABLE))
def test_settings_that_build_have_no_problem_and_are_given_without_their_outer_whitespace(
    name: str,
) -> None:
    """The positive case every refusal below needs. Delete this and a judgement that refused every
    setting would pass the rest of the file."""
    padded = settings_for(name, f"  {IDENTIFIERS[name]}\n")

    assert settings_problems(CONNECTABLE[name], padded) == ()
    assert given(CONNECTABLE[name], padded) == settings_for(name)
    assert manifest_digest(manifest_for(name, padded)) == manifest_digest(
        manifest_for(name, settings_for(name))
    )


def test_a_blank_a_long_and_an_unasked_setting_are_each_told_by_field_and_nothing_is_built() -> (
    None
):
    """All of them at once, and the connector is not asked while any is outstanding, because a
    connection class handed a blank refuses it in words that send the person to the wrong box.
    Delete this and a form is refused one mistake at a time."""
    xero = CONNECTABLE["xero"]

    blank = settings_problems(xero, {"tenant_id": "  ", "region": "x"})
    long = settings_problems(xero, {"tenant_id": "a" * (MAX_SETTING_CHARS + 1)})
    at_limit = settings_problems(xero, {"tenant_id": "a" * MAX_SETTING_CHARS})

    assert [(one.field, one.code) for one in blank] == [
        ("region", "not_asked"),
        ("tenant_id", "blank"),
    ]
    assert [(one.field, one.code) for one in long] == [("tenant_id", "too_long")]
    assert at_limit == ()


@pytest.mark.parametrize("typed", ["*", "all", "one two", "tenant;drop"])
def test_an_identifier_the_connector_refuses_is_told_in_the_source_s_words(typed: str) -> None:
    """The refusal is the connection class's, applied by building the manifest, and the person is
    told this source's sentence rather than the connector's developer message. Delete this and a
    selector of `*`, which narrows nothing, is connected."""
    for name, kind in CONNECTABLE.items():
        found = settings_problems(kind, settings_for(name, typed))
        assert [(one.field, one.code, one.message) for one in found] == [
            (kind.settings[0].name, "refused", kind.settings[0].refused)
        ]


def test_the_blank_sentence_served_beside_the_form_is_the_one_the_judgement_answers() -> None:
    """The console says a blank setting's sentence before the confirmation opens, from what the API
    serves. Delete this and the served sentence and the refusal can part, so the page says one thing
    before the confirmation and the API another after it."""
    for kind in CONNECTABLE.values():
        [told] = [one for one in settings_problems(kind, {}) if one.code == "blank"]
        assert told.message == blank_sentence(kind.settings[0])
