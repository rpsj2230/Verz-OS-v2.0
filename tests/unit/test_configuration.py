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
    EDITABLE_SETTINGS,
    LABELS,
    READ_BY,
    READ_ONLY_BECAUSE,
    SECTION_OF,
    SECTION_ORDER,
    SECTION_TITLES,
    Section,
    Source,
    findings,
    normalised,
    profile_told,
    realm_of,
    resolved,
    rows,
    setting_problem,
    shown,
)
from brain.install import BY_NAME, INSTALLATION, InstallError, hold_saved, value_of
from brain.knowledge.search import BUILT_VECTOR_STORES
from brain.locale import currency, time_zone
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
    assert set(SECTION_OF) == set(BY_NAME) == set(LABELS)
    assert {one.section for one in drawn} == set(Section) == set(SECTION_ORDER)
    assert set(SECTION_TITLES) == set(Section)
    assert [one.section for one in drawn] == sorted(
        (one.section for one in drawn), key=SECTION_ORDER.index
    )
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


#: Settings that would lock everybody out or lose track of the company's data if changed from a
#: browser, which the owner's brief of 2026-09-28 names as staying read only.
MUST_STAY_READ_ONLY = frozenset(
    {
        "INSTALL_OIDC_ISSUER",
        "INSTALL_OIDC_REALM",
        "INSTALL_OIDC_CLIENT_ID",
        "INSTALL_OIDC_REDIRECT_URIS",
        "INSTALL_OBJECT_STORE_URL",
        "INSTALL_VECTOR_STORE",
        "INSTALL_EMBEDDING_DIMENSIONS",
    }
)


def test_every_setting_is_changed_here_or_says_why_not_and_every_row_says_when_it_applies() -> None:
    """Every setting is either changed on this screen or carries a one-line reason, never both
    and never neither; the ones that would break sign-in or data are never changed here; the
    currency, the time zone and the branding are. A value saved here says it reaches this server
    at once and the worker within a minute; a value from the file says a restart.

    Delete this and an issuer can be offered for editing from a browser, a setting can be
    read only with nothing saying why, or a row can stop saying when a change takes effect."""
    drawn = rows(env={"INSTALL_OIDC_ISSUER": ISSUER}, saved={"INSTALL_COMPANY_NAME": "Northwind"})

    assert EDITABLE_SETTINGS.isdisjoint(READ_ONLY_BECAUSE)
    assert EDITABLE_SETTINGS | set(READ_ONLY_BECAUSE) == set(BY_NAME)
    assert set(READ_ONLY_BECAUSE) >= MUST_STAY_READ_ONLY
    assert {"INSTALL_CURRENCY", "INSTALL_TIME_ZONE", "INSTALL_COMPANY_NAME"} <= EDITABLE_SETTINGS
    for one in drawn:
        assert one.editable == (one.read_only_because == ""), one.name
    company = next(one for one in drawn if one.name == "INSTALL_COMPANY_NAME")
    issuer = next(one for one in drawn if one.name == "INSTALL_OIDC_ISSUER")
    assert "worker" in company.applies and "next page" in company.applies
    assert "restarts" in issuer.applies and "next page" not in issuer.applies
    assert "installer" in issuer.read_only_because


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


def test_the_model_setting_is_named_by_its_own_words_and_never_as_the_profile() -> None:
    """Found on the owner's install on 2026-09-29: Settings said "The profile is 'hosted'" about
    where answers are made while Capacity called the install's size its profile, one word for two
    things on two Platform screens. Delete this and the sentence can say "the profile" again."""
    hosted = profile_told({"INSTALL_MODEL_PROFILE": HOSTED_PROFILE}, {})
    local = profile_told({}, {})

    for said in (hosted, local):
        assert said.startswith(f"{LABELS['INSTALL_MODEL_PROFILE']} is ")
        assert "profile" not in said.lower()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("INSTALL_COMPANY_NAME", "Northwind Trading"),
        ("INSTALL_PRODUCT_NAME", "Knowledge Desk"),
        ("INSTALL_LOGO_URL", "https://assets.northwind.example/logo.svg"),
        ("INSTALL_LOGO_URL", "/icon.svg"),
        ("INSTALL_ACCENT_COLOUR", "#1f7a5c"),
        ("INSTALL_SENDER_ADDRESS", "no-reply@northwind.example"),
        ("INSTALL_LOCALES", "en"),
        ("INSTALL_LOCALES", "zh-Hans, en"),
        ("INSTALL_CURRENCY", "SGD"),
        ("INSTALL_CURRENCY", " sgd "),
        ("INSTALL_TIME_ZONE", "Asia/Singapore"),
        ("INSTALL_TIME_ZONE", "UTC"),
        ("INSTALL_MODEL_PROFILE", "hosted"),
        ("INSTALL_MODEL_PROFILE", "local"),
    ],
)
def test_a_sensible_value_may_be_saved(name: str, value: str) -> None:
    """The positive sibling of every refusal below. Delete this and a check refusing everything
    passes them all, and no install can change its own name or its currency."""
    assert setting_problem(name, value) == ""


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
        ("INSTALL_OIDC_REDIRECT_URIS", "https://console.northwind.example/"),
        ("INSTALL_OBJECT_STORE_URL", "https://objects.northwind.example"),
        ("INSTALL_EMBEDDING_DIMENSIONS", "768"),
        ("INSTALL_MODEL_ENDPOINT", "http://inference-server:8080"),
        ("INSTALL_LARK_USES", "knowledge_wiki"),
        ("INSTALL_STAFF_SOURCE", "spreadsheet"),
        ("INSTALL_NOT_DECLARED", "anything"),
        ("INSTALL_LOCALES", "fr"),
        ("INSTALL_LOCALES", " , "),
        ("INSTALL_CURRENCY", "XXX"),
        ("INSTALL_CURRENCY", "dollars"),
        ("INSTALL_CURRENCY", "S$"),
        ("INSTALL_TIME_ZONE", "Mars/Olympus"),
        ("INSTALL_TIME_ZONE", "/etc/passwd"),
        ("INSTALL_TIME_ZONE", "../UTC"),
        ("INSTALL_MODEL_PROFILE", "online"),
    ],
)
def test_a_value_that_would_draw_wrong_or_a_setting_not_changed_here_is_refused(
    name: str, value: str
) -> None:
    """Each refusal is a sentence saying what to type instead. Delete this and an identity setting
    can be saved from a browser, a `javascript:` logo lands in the header's image source, or the
    currency is saved as the code meaning none."""
    assert setting_problem(name, value) != ""


def test_a_saved_currency_is_capitals_and_is_what_the_money_figures_are_rendered_in() -> None:
    """The owner types sgd and Asia/Singapore; the saved values are what `brain.locale` hands every
    money figure and timestamp. Delete this and a lower-case code is saved, which the locale reader
    refuses, and every cost falls back to no currency."""
    assert normalised("INSTALL_CURRENCY", " sgd ") == "SGD"
    assert normalised("INSTALL_COMPANY_NAME", " sgd ") == "sgd"
    hold_saved(
        {
            "INSTALL_CURRENCY": normalised("INSTALL_CURRENCY", "sgd"),
            "INSTALL_TIME_ZONE": normalised("INSTALL_TIME_ZONE", " Asia/Singapore "),
        }
    )

    assert currency() == "SGD"
    assert time_zone().key == "Asia/Singapore"
