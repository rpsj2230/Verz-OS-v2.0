"""The Settings screen's decisions: each value resolved as its readers do, and none a credential.

`brain.console.configuration` is pure, so every decision here is driven with the environment and the
saved values handed in, and the one thing it reads for itself, which modules read each setting, is
held against those modules' own source.

Task ids: M41.1.4, M41.1.5, M41.1.6, M41.1.7
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from brain.console.configuration import (
    EDITABLE_GROUPS,
    GROUP_ORDER,
    READ_BY,
    Source,
    branding_problem,
    findings,
    profile_told,
    realm_of,
    resolved,
    rows,
    shown,
)
from brain.install import BY_NAME, INSTALLATION, Belongs, InstallError, hold_saved, value_of
from brain.knowledge.search import BUILT_VECTOR_STORES
from brain.models.assembly import HOSTED_PROFILE, LOCAL_PROFILE

ISSUER = "https://id.northwind.example/realms/northwind"


@pytest.fixture(autouse=True)
def nothing_saved() -> Iterator[None]:
    """Every test starts with nothing held and leaves whatever was held before it."""
    before = hold_saved({})
    yield
    hold_saved(before)


@pytest.mark.parametrize("name", sorted(BY_NAME))
def test_a_value_and_its_source_agree_with_the_one_reader_for_every_setting(name: str) -> None:
    """**The screen resolves a value the way every reader does, or it shows an install that is not
    running.** Saved beats the environment, which beats the default, and a required setting nobody
    supplied is `missing` exactly where `value_of` raises.

    Delete this and the screen's order can drift from `brain.install.value_of`, so an administrator
    reads the environment's company name while every page draws the saved one."""
    declared = BY_NAME[name]
    saved = {name: "from-the-database"}
    env = {name: "from-the-file"}

    assert resolved(name, env, saved) == type(resolved(name, env, saved))(
        value_of(name, env, saved), Source.SAVED
    )
    assert resolved(name, env, {}).value == value_of(name, env, {})
    assert resolved(name, env, {}).source is Source.ENVIRONMENT
    if declared.required:
        with pytest.raises(InstallError):
            value_of(name, {}, {})
        assert resolved(name, {}, {}).source is Source.MISSING
    else:
        assert resolved(name, {}, {}).value == value_of(name, {}, {}) == declared.default
        assert resolved(name, {}, {}).source is Source.DEFAULT


def test_every_declared_setting_is_on_the_screen_once_identity_included() -> None:
    """The owner asked to see branding, the identity provider, the model profile and the storage
    locations. Identity is the group `brain.console.installation` leaves off This install, and a
    half-configured install is the one somebody opens this screen on, so it must answer there too.

    Delete this and a setting added to the declaration can be missing from the screen, or the
    screen can raise on an install whose issuer is not set yet."""
    drawn = rows(env={}, saved={})

    assert sorted(one.name for one in drawn) == sorted(BY_NAME)
    assert {one.group for one in drawn} == set(Belongs) == set(GROUP_ORDER)
    issuer = next(one for one in drawn if one.name == "INSTALL_OIDC_ISSUER")
    assert (issuer.value, issuer.source, issuer.editable) == ("", Source.MISSING, False)


def test_no_installation_setting_is_named_like_a_credential() -> None:
    """**The screen shows every declared value, so the declaration must hold no secret.** Keys,
    tokens and passwords live in the vault. Held over the names rather than trusted, because the
    next setting somebody declares is the one to check.

    Delete this and `INSTALL_PROVIDER_API_KEY` can be declared and drawn on the Settings screen."""
    words = ("KEY", "SECRET", "PASSWORD", "TOKEN", "CREDENTIAL")
    assert [one.name for one in INSTALLATION if any(word in one.name for word in words)] == []


def test_an_address_is_shown_without_anything_that_could_carry_a_credential() -> None:
    """A URL's user information, query and fragment are dropped, each part of a list judged on its
    own, and a value that is not a URL is shown as written.

    Delete this and `https://user:secret@store:8333` is drawn whole to everybody who may open the
    screen."""
    written = "https://user:secret@objects.example.test:8333/brain?token=abc#x,/auth/callback"

    assert shown(written) == "https://objects.example.test:8333/brain,/auth/callback"
    assert shown("Northwind Trading") == "Northwind Trading"
    drawn = {
        one.name: one.value
        for one in rows(env={"INSTALL_OBJECT_STORE_URL": "http://k:s@seaweedfs:8333"}, saved={})
    }
    assert drawn["INSTALL_OBJECT_STORE_URL"] == "http://seaweedfs:8333"


def test_only_branding_is_editable_and_every_row_says_when_a_change_applies() -> None:
    """A saved value applies on this process at once and elsewhere after a restart; a value from
    the file or the default applies after a restart. Delete this and an identity setting can be
    offered for editing from a browser, or a row can stop saying a restart is needed."""
    drawn = rows(env={"INSTALL_OIDC_ISSUER": ISSUER}, saved={"INSTALL_COMPANY_NAME": "Northwind"})

    assert (
        {one.group for one in drawn if one.editable} == set(EDITABLE_GROUPS) == {Belongs.BRANDING}
    )
    company = next(one for one in drawn if one.name == "INSTALL_COMPANY_NAME")
    issuer = next(one for one in drawn if one.name == "INSTALL_OIDC_ISSUER")
    assert "restarts" in company.applies and "next page" in company.applies
    assert "restarts" in issuer.applies and "next page" not in issuer.applies


def test_every_setting_names_a_module_that_actually_reads_it() -> None:
    """**A setting nothing reads is a field that changes nothing.** Each module named is opened and
    must contain the setting's name, or the constant that holds it.

    Delete this and `INSTALL_SENDER_ADDRESS` can go back to being declared, drawn, saved and read by
    nothing, which is where it was until 2026-09-17."""
    assert set(READ_BY) == set(BY_NAME)
    for name, modules in READ_BY.items():
        assert modules, name
        for dotted in modules:
            # This module names every setting in `READ_BY` itself, so citing it proves nothing.
            assert dotted != "brain.console.configuration", name
            module = importlib.import_module(dotted)
            assert module.__file__ is not None
            source = Path(module.__file__).read_text(encoding="utf-8")
            assert f'"{name}"' in source, f"{dotted} does not read {name}"


def test_a_realm_the_issuer_does_not_name_is_a_finding_and_a_matching_one_is_not() -> None:
    """The installer creates `INSTALL_OIDC_REALM` and tokens are checked against the issuer, so a
    difference is a realm nobody signs in to. Delete this and the two can disagree in silence."""
    matching = {"INSTALL_OIDC_ISSUER": ISSUER, "INSTALL_OIDC_REALM": "northwind"}
    differing = {"INSTALL_OIDC_ISSUER": ISSUER, "INSTALL_OIDC_REALM": "brain"}
    unshaped = {"INSTALL_OIDC_ISSUER": "https://id.northwind.example", "INSTALL_OIDC_REALM": "x"}

    assert realm_of(ISSUER) == "northwind"
    assert findings(matching, {}) == ()
    assert len(findings(differing, {})) == 1 and "'northwind'" in findings(differing, {})[0]
    assert len(findings(unshaped, {})) == 1
    assert findings({}, {}) == ()


def test_a_vector_store_this_release_does_not_build_is_a_finding() -> None:
    """Delete this and `INSTALL_VECTOR_STORE=qdrant` reads as configured while every embedding goes
    on being written to PostgreSQL."""
    assert BY_NAME["INSTALL_VECTOR_STORE"].default in BUILT_VECTOR_STORES
    assert findings({"INSTALL_VECTOR_STORE": "postgres"}, {}) == ()
    assert "'qdrant'" in findings({"INSTALL_VECTOR_STORE": "qdrant"}, {})[0]


def test_the_profile_sentence_follows_the_router_rule_on_where_text_may_go() -> None:
    """`brain.models.assembly.local_only` is the rule, so the sentence is asked of it both ways.
    Delete this and the screen can say no text leaves a hosted install."""
    assert BY_NAME["INSTALL_MODEL_PROFILE"].default == LOCAL_PROFILE
    local = profile_told({}, {})
    hosted = profile_told({"INSTALL_MODEL_PROFILE": HOSTED_PROFILE}, {})

    assert "no text leaves this install" in local
    assert "no text leaves this install" not in hosted and "may be sent text" in hosted


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("INSTALL_COMPANY_NAME", "Northwind Trading"),
        ("INSTALL_PRODUCT_NAME", "Knowledge Desk"),
        ("INSTALL_LOGO_URL", "https://assets.northwind.example/logo.svg"),
        ("INSTALL_LOGO_URL", "/icon.svg"),
        ("INSTALL_ACCENT_COLOUR", "#1f7a5c"),
        ("INSTALL_SENDER_ADDRESS", "no-reply@northwind.example"),
    ],
)
def test_a_sensible_branding_value_may_be_saved(name: str, value: str) -> None:
    """The positive sibling of every refusal below. Delete this and a check refusing everything
    passes them all, and no install can change its own name."""
    assert branding_problem(name, value) == ""


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("INSTALL_COMPANY_NAME", "   "),
        ("INSTALL_COMPANY_NAME", "x" * 201),
        ("INSTALL_COMPANY_NAME", "Northwind\nTrading"),
        ("INSTALL_LOGO_URL", "http://assets.northwind.example/logo.svg"),
        ("INSTALL_LOGO_URL", "https://user:pw@assets.northwind.example/logo.svg"),
        ("INSTALL_LOGO_URL", "//assets.northwind.example/logo.svg"),
        ("INSTALL_LOGO_URL", "javascript:alert(1)"),
        ("INSTALL_ACCENT_COLOUR", "green"),
        ("INSTALL_SENDER_ADDRESS", "not an address"),
        ("INSTALL_OIDC_ISSUER", ISSUER),
        ("INSTALL_OBJECT_STORE_URL", "https://objects.northwind.example"),
        ("INSTALL_NOT_DECLARED", "anything"),
    ],
)
def test_a_branding_value_that_would_draw_wrong_or_a_setting_not_changed_here_is_refused(
    name: str, value: str
) -> None:
    """Each refusal is a sentence saying what to type instead. Delete this and an identity setting
    can be saved from a browser, or a `javascript:` logo lands in the header's image source."""
    assert branding_problem(name, value) != ""
