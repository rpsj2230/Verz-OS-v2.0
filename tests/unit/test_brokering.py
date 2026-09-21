"""A brokered directory becomes an identity provider restricted to one company, or a reason.

Task ids: M41.1.5
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brain.console.configuration import (
    LOCAL_PROFILE_HAS_NO_MODEL_THAT_ANSWERS,
    findings,
    local_model_answers,
    profile_told,
)
from brain.identity.brokering import (
    BROKERED_BY,
    NOT_BROKERED_BY_THIS_RELEASE,
    VAULT_KEY,
    VAULT_REFERENCE,
    brokering,
    vault_file,
)
from brain.install import BY_NAME
from brain.models.default_ladder import LOCAL_COMPLETION_MODEL
from brain.ops.inference import SERVED_MODELS
from brain.setup_wizard import STAFF_SOURCE_BROKERS

REPO = Path(__file__).resolve().parents[2]

#: A Google Workspace company that has said everything, on a reserved documentation domain.
GOOGLE = {
    "directory": "google",
    "client_id": "1234-web.apps.googleusercontent.example",
    "staff_source": "google_workspace",
    "location": "northwind.example",
}
MICROSOFT = {
    "directory": "microsoft",
    "client_id": "00000000-0000-0000-0000-000000000001",
    "staff_source": "microsoft_entra",
    "location": "northwind.example",
}


def test_google_and_microsoft_are_brokered_to_the_companys_own_domain_or_tenant() -> None:
    """The positive case. Delete this and a `brokering` that refuses everything passes every
    refusal test below, and no company is ever brokered."""
    google = brokering(**GOOGLE)
    microsoft = brokering(**MICROSOFT)

    assert google.problem == "" and microsoft.problem == ""
    assert google.provider["providerId"] == "google"
    assert google.provider["config"]["hostedDomain"] == "northwind.example"
    assert google.provider["config"]["clientId"] == GOOGLE["client_id"]
    assert microsoft.provider["providerId"] == "microsoft"
    assert microsoft.provider["config"]["tenantId"] == "northwind.example"
    assert "hostedDomain" not in microsoft.provider["config"]
    assert google.provider["enabled"] is True
    json.dumps(google.provider)


def test_the_secret_in_the_entry_is_a_vault_reference_and_never_a_value() -> None:
    """Delete this and the entry can carry a secret, which is then in the realm file every
    import writes to a shared volume."""
    config = brokering(**GOOGLE).provider["config"]

    assert config["clientSecret"] == VAULT_REFERENCE == "${vault." + VAULT_KEY + "}"
    assert vault_file("brain") == "brain_brokered-directory-client-secret"
    assert vault_file("north_wind").startswith("north__wind_")


@pytest.mark.parametrize(
    ("change", "said"),
    [
        ({"location": "unset"}, "no google domain"),
        ({"location": ""}, "no google domain"),
        ({"staff_source": "spreadsheet"}, "no google domain"),
        ({"staff_source": "microsoft_entra"}, "no google domain"),
        ({"location": "*"}, "not one company's"),
        ({"location": "north wind.example"}, "not one company's"),
    ],
)
def test_google_without_one_companys_domain_is_not_brokered(
    change: dict[str, str], said: str
) -> None:
    """**A Google broker with no hosted domain signs in any Google account.** Delete this and a
    realm can be handed one, which gives a stranger an account here on first sign-in."""
    refused = brokering(**{**GOOGLE, **change})

    assert refused.provider == {}
    assert said in refused.problem


@pytest.mark.parametrize("tenant", ["common", "organizations", "consumers", "Common"])
def test_a_multi_tenant_microsoft_name_is_not_a_tenant(tenant: str) -> None:
    """Microsoft's `common`, `organizations` and `consumers` admit every tenant. Delete this and
    one of them can be written as the restriction and restrict nothing."""
    refused = brokering(**{**MICROSOFT, "location": tenant})

    assert refused.provider == {}
    assert "not one company's" in refused.problem


@pytest.mark.parametrize("client_id", ["unset", "", "  "])
def test_no_registered_application_means_no_broker_and_says_which_setting(client_id: str) -> None:
    """Delete this and a broker is emitted with no client id, which fails at the vendor's page."""
    refused = brokering(**{**GOOGLE, "client_id": client_id})

    assert refused.provider == {}
    assert "INSTALL_BROKERED_CLIENT_ID" in refused.problem


def test_lark_ldap_and_an_unknown_value_are_refused_with_a_reason_and_none_is_silent() -> None:
    """Delete this and `lark` can read as brokered while people sign in with realm passwords, or
    `none` can report a problem on every install that chose not to broker."""
    for directory in NOT_BROKERED_BY_THIS_RELEASE:
        refused = brokering(**{**GOOGLE, "directory": directory})
        assert refused.provider == {} and repr(directory) in refused.problem
    unknown = brokering(**{**GOOGLE, "directory": "okta"})
    assert unknown.provider == {} and "'okta'" in unknown.problem

    quiet = brokering(**{**GOOGLE, "directory": "none"})
    assert quiet.provider == {} and quiet.problem == ""


def test_the_pairing_of_directory_and_staff_source_is_the_wizards() -> None:
    """The wizard writes the broker from the staff source; this module reads the location only
    when the two agree. Delete this and the two tables can pair differently, so a wizard-chosen
    directory is never brokered."""
    for directory, source in BROKERED_BY.items():
        assert STAFF_SOURCE_BROKERS[source] == directory
    offered = set(STAFF_SOURCE_BROKERS.values()) - {"none"}
    assert offered <= set(BROKERED_BY) | set(NOT_BROKERED_BY_THIS_RELEASE)
    assert BY_NAME["INSTALL_BROKERED_DIRECTORY"].default == "none"
    assert BY_NAME["INSTALL_BROKERED_CLIENT_ID"].default == "unset"


def test_the_settings_screen_reports_a_directory_it_will_not_broker() -> None:
    """Delete this and a chosen directory that is not brokered is shown as a plain value."""
    chosen = {"INSTALL_BROKERED_DIRECTORY": "lark", "INSTALL_MODEL_PROFILE": "hosted"}
    brokered = {
        "INSTALL_BROKERED_DIRECTORY": "google",
        "INSTALL_BROKERED_CLIENT_ID": GOOGLE["client_id"],
        "INSTALL_STAFF_SOURCE": "google_workspace",
        "INSTALL_STAFF_SOURCE_LOCATION": "northwind.example",
    }

    assert any("'lark'" in one for one in findings(chosen, {}))
    assert findings(brokered, {}) == ()
    # A saved wizard answer outranks the environment here as everywhere.
    assert any(
        "'lark'" in one for one in findings(brokered, {"INSTALL_BROKERED_DIRECTORY": "lark"})
    )


def test_the_local_profile_sentence_says_when_nothing_local_can_answer() -> None:
    """The screen said questions were "answered by the inference server alone" while that server
    serves no model that writes an answer. Delete this and it can say so again."""
    served = {one.name for one in SERVED_MODELS}

    assert local_model_answers() is (LOCAL_COMPLETION_MODEL in served)
    local = profile_told({}, {})
    hosted = profile_told({"INSTALL_MODEL_PROFILE": "hosted"}, {})
    assert (LOCAL_PROFILE_HAS_NO_MODEL_THAT_ANSWERS in local) is not local_model_answers()
    assert LOCAL_PROFILE_HAS_NO_MODEL_THAT_ANSWERS not in hosted
