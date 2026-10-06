"""Which sources the console can connect, what each asks for, and the connector's own refusals.

`brain.ops.connectable` is a list of the product's connectors, read off each connector's own
`CONNECTOR` declaration, and the failure worth testing first is the list drifting from the
connectors: a connector added to `brain.connectors` with no decision would be silently missing
from the screen, and a source listed here whose manifest names another source would connect one
thing under another's name. Then the refusals, each with a sibling that builds.

Task ids: M42.6.5, M11.1.6
"""

from __future__ import annotations

import dataclasses
import importlib
import pkgutil
import re
from pathlib import Path
from typing import Final

import pytest

import brain.connectors
from brain.connectors.contract import AccessMode
from brain.connectors.declaration import CredentialShape, shipped
from brain.connectors.manifest import manifest_digest
from brain.connectors.write_verification import builds_a_manifest
from brain.knowledge.connector_rows import ANSWERED_BY_PASSAGES, CONNECTOR_ROW_ENTITIES
from brain.ops.connectable import (
    CONNECTABLE,
    DECLARED_FORMS,
    MAX_SETTING_CHARS,
    NOT_FROM_THE_CONSOLE,
    READING_ROLE,
    THIS_INSTALL_CANNOT_READ_IT_YET,
    NotConnectableError,
    blank_sentence,
    connectable,
    given,
    key_reference,
    manifest_for,
    offered,
    settings_problems,
)
from brain.ops.credentials import CONNECTOR_NAME_PATTERN
from brain.ops.limits import connector_ceiling
from brain.ops.openbao import CONNECTOR_KEY_PREFIX
from brain.ops.secrets import VaultRole
from tests.fixtures.connector_examples import example_settings, identifier

REPO: Final = Path(__file__).resolve().parents[2]


def in_scope(identifier: str, selectors: tuple[str, ...]) -> bool:
    """Whether the scope names the identifier typed: as a selector, as what each is inside, as
    a database holds the views a Laravel connection names (`portal.v_client`), or as the list the
    selectors are, as a domains connection's are."""
    listed = tuple(one.strip() for one in identifier.split(","))
    return (
        identifier in selectors
        or all(one.startswith(f"{identifier}.") for one in selectors)
        or listed == selectors
    )


def settings_for(name: str, value: str | None = None) -> dict[str, str]:
    """Every setting a source asks for, as its declaration's example gives them, the first
    replaced by `value` when one is given."""
    first = identifier(name) if value is None else value
    return {**example_settings(name), CONNECTABLE[name].settings[0].name: first}


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
    assert in_scope(identifier(name), manifest.scope.selectors)
    assert key_reference(name) == manifest.credential.ref


@pytest.mark.parametrize("name", sorted(CONNECTABLE))
def test_a_source_s_key_hint_asks_for_exactly_the_scopes_its_slot_asks_for(name: str) -> None:
    """The scopes an administrator is told to request are the ones the source's vault slot is
    defined with: its own declaration's `scopes`, which `brain.ops.connector_slots` defines the slot
    from and `credential-slots.md`'s key slot table is held to (`test_vault_policies`). Delete this
    and the form's hint drifts from the slot, and the scope asked for on install day is whichever
    one somebody last typed.

    Read off the declaration since 2026-10-05, rather than off the prose table of leased paths
    nothing reads, which every connector had to add a row to and every connector PR conflicted in.
    """
    hint = CONNECTABLE[name].credential_hint
    if CONNECTABLE[name].credential_shape is CredentialShape.NONE:
        # A source that takes no key has no slot and no scope; its hint says nothing is kept.
        assert "nothing is kept" in hint
        assert shipped()[name].scopes is None
        return
    scopes = shipped()[name].scopes

    assert scopes is not None, f"{name} is offered and declares no scopes for its slot"
    assert scopes.request and scopes.refuse
    for scope in scopes.request:
        assert scope in hint, scope


def test_the_hint_check_reads_scopes_a_real_source_states() -> None:
    """**The positive anchor.** Xero's hint names its two read scopes and Freshdesk's its agent key,
    as each declares them. Delete this and a declaration whose scopes are empty, or a discovery that
    found no offered source, would pass the parametrised check above by having nothing to check."""
    xero_scopes = shipped()["xero"].scopes
    freshdesk_scopes = shipped()["freshdesk"].scopes
    assert xero_scopes is not None and freshdesk_scopes is not None
    assert xero_scopes.request == ("accounting.transactions.read", "accounting.contacts.read")
    assert "accounting.transactions.read" in CONNECTABLE["xero"].credential_hint
    assert freshdesk_scopes.request == ("an agent API key with read access",)
    assert "never an admin key" in CONNECTABLE["freshdesk"].credential_hint


def test_every_source_the_console_cannot_connect_says_why_in_words() -> None:
    """Delete this and a reason can be left blank, which draws a source on the screen with nothing
    saying what connecting it would need."""
    for one in NOT_FROM_THE_CONSOLE.values():
        assert one.name and one.label
        # Lark's two are connected by Connect Lark on the same screen, and since 2026-09-30
        # (M11.7.7) nothing else is connected at the server: the rest are declared forms this
        # install cannot read yet, and say so.
        if one.name.startswith("lark_"):
            assert "Connect Lark" in one.why
        else:
            assert one.name in DECLARED_FORMS
            assert (one.why, one.guide) == (THIS_INSTALL_CANNOT_READ_IT_YET, ())
    with pytest.raises(NotConnectableError):
        connectable("lark_base")
    assert connectable("xero") is CONNECTABLE["xero"]


def test_a_source_the_console_offers_is_one_this_install_reads() -> None:
    """`A_SOURCE_THE_CONSOLE_OFFERS_IS_ONE_THIS_INSTALL_READS`, over every declaration: a form
    is offered exactly when it has a reading or a live lookup, a recorded ceiling, and an answer
    on Ask. Delete this and the screen can offer a connection that keeps its key and reads
    nothing, which is what Google Drive and Laravel were until 2026-09-30, and HubSpot, which had
    a reading and no ceiling.

    Computed from the declarations, `brain.ops.limits` and the Ask rows rather than typed as a
    set since 2026-10-05, so a connector added is judged here with nothing edited. Xero being
    offered and Lark's two not is the anchor that keeps a discovery finding nothing from passing."""
    declared = shipped()
    expected = {
        name
        for name, one in declared.items()
        if one.console is not None
        and (one.reading is not None or one.live is not None)
        and connector_ceiling(name) is not None
        # `A_SOURCE_THE_CONSOLE_OFFERS_IS_ONE_ASK_ANSWERS_FROM`: and Ask answers from it.
        and (name in CONNECTOR_ROW_ENTITIES or name in ANSWERED_BY_PASSAGES)
    }

    assert set(CONNECTABLE) == expected
    assert {"xero", "freshdesk"} <= set(CONNECTABLE)
    assert not {"lark_base", "lark_wiki"} & set(CONNECTABLE)


def test_a_form_with_no_way_to_be_read_is_listed_and_not_offered() -> None:
    """The rule driven from both sides on one real declaration. Xero as it ships is offered; Xero
    with neither its reading nor its live lookup, and Xero under a name no ceiling is recorded for,
    are each listed as not readable yet and offered nowhere. Delete this and the rule can be
    satisfied by a function that offers everything, or by one that offers nothing."""
    from brain.connectors import xero

    real = xero.CONNECTOR
    offers, listed = offered({"xero": real})
    assert set(offers) == {"xero"} and listed == {}

    unread = dataclasses.replace(real, reading=None, live=None)
    offers, listed = offered({"xero": unread})
    assert offers == {}
    assert (listed["xero"].why, listed["xero"].guide) == (THIS_INSTALL_CANNOT_READ_IT_YET, ())

    unmeasured = dataclasses.replace(real, name="nowhere", ceiling=None)
    offers, listed = offered({"nowhere": unmeasured})
    assert offers == {} and listed["nowhere"].why == THIS_INSTALL_CANNOT_READ_IT_YET


def test_a_source_read_and_answerable_by_nothing_is_not_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`A_SOURCE_THE_CONSOLE_OFFERS_IS_ONE_ASK_ANSWERS_FROM`, from both sides and both ways of
    answering. Xero's declaration under Lark Base's name has a reading and a ceiling and nothing
    Ask answers from, and is not offered; the same with the name among the passage readers is
    offered, as Xero itself is through its classifications. Delete this and the screen can offer
    a source that is read into the index and never answers a question, which HubSpot was."""
    import brain.ops.connectable as connectable
    from brain.connectors import lark_base, xero

    read_only = dataclasses.replace(xero.CONNECTOR, name="lark_base", ceiling=lark_base.CEILING)
    offers, listed = offered({"lark_base": read_only})
    assert offers == {} and listed["lark_base"].why == THIS_INSTALL_CANNOT_READ_IT_YET

    monkeypatch.setattr(connectable, "ANSWERED_BY_PASSAGES", frozenset({"lark_base"}))
    offers, _ = offered({"lark_base": read_only})
    assert set(offers) == {"lark_base"}
    assert set(offered({"xero": xero.CONNECTOR})[0]) == {"xero"}


# ------------------------------------------------------------------------- the refusals


@pytest.mark.parametrize("name", sorted(CONNECTABLE))
def test_settings_that_build_have_no_problem_and_are_given_without_their_outer_whitespace(
    name: str,
) -> None:
    """The positive case every refusal below needs. Delete this and a judgement that refused every
    setting would pass the rest of the file."""
    padded = settings_for(name, f"  {identifier(name)}\n")

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
        told = [one for one in settings_problems(kind, {}) if one.code == "blank"]
        assert [(one.field, one.message) for one in told] == [
            (setting.name, blank_sentence(setting)) for setting in kind.settings
        ]
