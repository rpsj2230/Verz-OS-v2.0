"""The browser harness's people: named in a fixture, given credentials only by the job that runs it.

Task ids: M27.10.6
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brain.ops.browser_harness import (
    CODE_POLICY,
    KIND_KEY,
    TEST_DOMAIN,
    WITH_A_SECOND_FACTOR,
    WITHOUT_A_SECOND_FACTOR,
    HarnessError,
    fixture_problems,
    main,
    realm_with_people,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "e2e" / "fixtures" / "people.json"
SOURCE = REPO / "ops" / "keycloak" / "realm-export.json"
ORIGIN = "http://localhost:8000/auth/callback"
MINTED = {
    "INSTALL_OIDC_REDIRECT_URIS": ORIGIN,
    "INSTALL_OIDC_REALM": "brain",
    "INSTALL_OIDC_CLIENT_ID": "brain-console",
    "E2E_ADMIN_PASSWORD": "minted-in-this-test-1",
    "E2E_ADMIN_CODE_SECRET": "minted-in-this-test-2",
    "E2E_READER_PASSWORD": "minted-in-this-test-3",
}


def people() -> list[dict[str, object]]:
    loaded = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    return loaded


def test_the_fixture_holds_no_credential_and_no_address_outside_the_test_domain() -> None:
    """`A_CREDENTIAL_IN_A_FIXTURE_IS_A_CREDENTIAL_IN_A_REPOSITORY`, held against the real file. The
    job mints the passwords and the one-time-code secret per run, so the file never needs one.
    Delete this and a password pasted into the fixture to debug a run is in a public repository's
    history for ever, or a person in it is given somebody's real address."""
    assert fixture_problems(people()) == ()
    assert [one["email"] for one in people()] == [f"admin@{TEST_DOMAIN}", f"reader@{TEST_DOMAIN}"]
    assert {one[KIND_KEY] for one in people()} == {WITH_A_SECOND_FACTOR, WITHOUT_A_SECOND_FACTOR}


@pytest.mark.parametrize(
    ("change", "said"),
    [
        ({"credentials": [{"type": "password", "value": "x"}]}, "credentials is a credential"),
        ({"attributes": {"secret": ["x"]}}, "secret is a credential"),
        ({"password": "x"}, "password is a credential"),
        ({"email": "someone@a-real-company.com"}, f"email is not at {TEST_DOMAIN}"),
        ({KIND_KEY: "anything"}, "names no credential kind"),
    ],
)
def test_a_fixture_with_a_credential_or_a_real_address_is_refused(
    change: dict[str, object], said: str
) -> None:
    """Each way the fixture could go wrong, found wherever it is nested. Delete this and the guard
    above can be satisfied by a check that looks at nothing."""
    tampered = [{**people()[0], **change}, people()[1]]
    found = fixture_problems(tampered)
    assert any(said in one for one in found), found


def test_the_realm_is_the_product_s_own_with_the_two_people_and_their_minted_credentials() -> None:
    """The realm every install imports, addressed to the job, plus both people with the credentials
    the job minted and nothing asked of them at sign-in. Delete this and the harness can sign in to
    a realm the product never ships, or the administrator arrives with no second factor."""
    realm = json.loads(realm_with_people(FIXTURE, MINTED, source=SOURCE))
    console = next(one for one in realm["clients"] if one["clientId"] == "brain-console")
    assert ORIGIN in console["redirectUris"]
    added = {one["username"]: one for one in realm["users"] if one["username"].startswith("e2e-")}
    admin, reader = added["e2e-admin"], added["e2e-reader"]
    assert [one["type"] for one in admin["credentials"]] == ["password", "otp"]
    assert admin["credentials"][0]["value"] == MINTED["E2E_ADMIN_PASSWORD"]
    assert json.loads(admin["credentials"][1]["secretData"]) == {
        "value": MINTED["E2E_ADMIN_CODE_SECRET"]
    }
    assert json.loads(admin["credentials"][1]["credentialData"]) == CODE_POLICY
    assert [one["type"] for one in reader["credentials"]] == ["password"]
    assert admin["requiredActions"] == reader["requiredActions"] == []
    assert KIND_KEY not in admin and KIND_KEY not in reader
    assert "service-account-brain-accounts" in {one["username"] for one in realm["users"]}


def test_the_code_policy_is_the_realm_s_own() -> None:
    """A credential stating another policy than the realm's would be read differently by Keycloak
    and by the browser that computes the code. Held against the realm file, not against itself."""
    realm = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert CODE_POLICY["digits"] == realm["otpPolicyDigits"]
    assert CODE_POLICY["period"] == realm["otpPolicyPeriod"]
    assert CODE_POLICY["algorithm"] == realm["otpPolicyAlgorithm"]
    assert realm["otpPolicyType"] == CODE_POLICY["subType"]


@pytest.mark.parametrize(
    "missing", ["E2E_ADMIN_PASSWORD", "E2E_ADMIN_CODE_SECRET", "E2E_READER_PASSWORD"]
)
def test_a_run_that_minted_no_credential_is_refused_rather_than_signed_in_without_one(
    missing: str,
) -> None:
    """Delete this and a job that forgot to mint the code's secret imports an administrator with
    a password alone, and every admin screen refuses them for a reason the run never says."""
    env = {key: value for key, value in MINTED.items() if key != missing}
    with pytest.raises(HarnessError, match="minted no"):
        realm_with_people(FIXTURE, env, source=SOURCE)


def test_the_command_says_how_it_is_used() -> None:
    """Delete this and the job's one call can drift from the command's shape unnoticed."""
    assert main([]) == 64


PAGES = REPO / "e2e" / "pages"
WORKFLOW = REPO / ".github" / "workflows" / "browser.yml"
OVERRIDE = REPO / "e2e" / "docker-compose.e2e.yml"


def test_every_module_group_of_the_console_has_a_page_object() -> None:
    """Every `ModuleGroup` has `e2e/pages/<group>.ts`, and the registry imports every one of them.

    Deleting this lets a module join the console's menu with no page object, and the harness's own
    check of that (`specs/modules.spec.ts`) only runs where Docker and a browser do. This one runs
    in every unit shard, so the gap shows on the commit that opens it.
    """
    from brain.console.screens import ModuleGroup

    files = {path.stem for path in PAGES.glob("*.ts")} - {"index", "module"}
    assert files == {group.value for group in ModuleGroup}
    registry = (PAGES / "index.ts").read_text(encoding="utf-8")
    imported = {
        line.split(" from ")[1].strip().strip(";").strip('"').removeprefix("./")
        for line in registry.splitlines()
        if line.startswith("import {") and " from " in line
    }
    assert {group.value for group in ModuleGroup} <= imported


def test_every_value_the_harness_stack_requires_is_minted_or_set_by_the_job() -> None:
    """Each `${NAME:?...}` the e2e override requires is minted in the workflow or set on the job.

    Deleting this leaves an unset variable to be found by `docker compose up` after a ten-minute
    image build, as an interpolation error naming the variable and nothing about why it is unset.
    The minted ones must also be masked, which is the half that matters: an unmasked password in a
    public repository's job log is a password in a public log.
    """
    import re

    import yaml

    required = set(re.findall(r"\$\{([A-Z0-9_]+):\?", OVERRIDE.read_text(encoding="utf-8")))
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["browser"]
    steps = {step.get("name", ""): step for step in job["steps"]}
    mint = steps["Every credential this run needs, minted here and masked"]["run"]
    minted = set(re.findall(r"^\s*mint ([A-Z0-9_]+) \d+$", mint, flags=re.MULTILINE))
    exported = set(
        re.findall(r'echo "([A-Z0-9_]+)=', "\n".join(s.get("run", "") for s in steps.values()))
    )
    assert "::add-mask::$value" in mint
    assert required <= minted | exported | set(job["env"])
    assert {"E2E_ADMIN_PASSWORD", "E2E_READER_PASSWORD", "E2E_ADMIN_CODE_SECRET"} <= minted
    assert "BRAIN_SETUP_SECRET" in minted
