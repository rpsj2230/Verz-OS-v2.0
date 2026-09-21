"""The steps and boxes the Staff sources screen shows for each kind of staff source.

`brain.console.staff_source_guide` is product text: what a company does in its vendor's console
before this install can read its staff list. These tests hold the text to what the code that reads
each source actually needs, so a guide cannot tell somebody to grant less than the reader uses, and
hold the guide's shape to the credential the nightly reader splits.

Task ids: M27.7.2, M1.8.6
"""

from __future__ import annotations

import pytest

from brain.connectors.staff_directories import LARK_PLATFORMS, LARK_SCOPES
from brain.console.staff_source_guide import (
    GUIDES,
    LOCATION,
    Guide,
    GuideField,
    field_problems,
    guide_for,
)
from brain.identity.staff_adapters import (
    ADDRESS_COLUMNS,
    GOOGLE_SHEET,
    GOOGLE_WORKSPACE,
    LARK,
    LDAP,
    MICROSOFT_ENTRA,
)
from brain.identity.staff_source import SELECTABLE_BY_NAME, selectable_names
from brain.ops import staff_sync_run
from brain.ops.staff_sync_run import READERS, client_credential


def connectable(guide: Guide) -> bool:
    """Asked through a call, so a type checker does not carry one answer across a monkeypatch."""
    return guide.connectable


def steps(source: str) -> str:
    found = guide_for(source)
    assert found is not None
    return " ".join(found.steps)


def test_the_screen_offers_the_five_kinds_of_source_a_company_keeps_its_people_in() -> None:
    """Delete this and a kind of source the owner asked for can drop off the connect flow."""
    assert [one.source for one in GUIDES] == [
        LARK,
        MICROSOFT_ENTRA,
        GOOGLE_WORKSPACE,
        GOOGLE_SHEET,
        LDAP,
    ]
    assert all(one.source in selectable_names() for one in GUIDES)
    assert all(one.steps and one.title and one.where for one in GUIDES)


def test_the_lark_steps_name_the_console_the_scopes_the_data_range_the_release_and_the_keys() -> (
    None
):
    """The owner's Lark steps, in order, and every scope the Lark walk reads with.

    Delete this and the guide can drop the release step, which is the one people miss: scopes
    and the data range do nothing until a version is released."""
    text = steps(LARK)
    found = guide_for(LARK)
    assert found is not None

    assert "open.larksuite.com/app" in text
    for scope in LARK_SCOPES.split():
        assert scope in text
    assert "contact:user.base:readonly" in text
    assert "contact:department.base:readonly" in text
    assert '"Permissions & Scopes"' in text
    assert '"All members"' in text
    assert "release" in text.lower()
    assert '"Credentials & Basic Info"' in text
    order = [text.index(one) for one in ("Permissions & Scopes", "All members", "Version")]
    assert order == sorted(order)
    assert [box.key for box in found.fields] == [LOCATION, "app_id", "app_secret"]
    assert [box.secret for box in found.fields] == [False, False, True]
    assert all(platform in found.fields[0].help for platform in LARK_PLATFORMS)


def test_the_microsoft_steps_ask_for_the_application_permission_with_admin_consent() -> None:
    """The nightly run exchanges a client secret for an application token, which carries only
    application permissions. Delete this and the guide can say delegated, which the wizard's
    sign-in needs and the nightly run cannot use: every run would read nobody."""
    text = steps(MICROSOFT_ENTRA)

    assert "User.Read.All" in text
    assert '"Application permissions"' in text
    assert "Grant admin consent" in text
    assert '"Value"' in text
    assert staff_sync_run.MICROSOFT_APPLICATION_SCOPE.endswith("/.default")


def test_the_sheet_steps_share_the_sheet_enable_the_api_and_name_the_columns_the_reader_reads() -> (
    None
):
    """Delete this and the guide can omit the sharing step, and an API key reads nothing else."""
    text = steps(GOOGLE_SHEET)

    assert "Anyone with the link" in text
    assert "Google Sheets API" in text
    assert "API key" in text
    assert ADDRESS_COLUMNS[0].title() in text


def test_google_workspace_is_shown_with_its_steps_and_is_never_offered_as_connectable() -> None:
    """Google Workspace has no nightly reader on this version, and the screen says so in words.

    Delete this and a form could save a Workspace secret that nothing will ever read."""
    found = guide_for(GOOGLE_WORKSPACE)
    assert found is not None

    assert found.steps
    assert not found.connectable
    assert "cannot be connected" in found.unavailable
    assert GOOGLE_WORKSPACE not in READERS


def test_a_source_is_connectable_exactly_when_the_nightly_sync_has_a_reader_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LDAP lights up the day a reader is registered, with nothing in the guide changing.

    The positive half matters as much: Lark, Microsoft and a sheet are connectable today. Delete
    this and the guide can offer a form for a source nothing reads, or hide one somebody can."""
    # LDAP is counted by the registry rather than assumed, because its reader is built separately.
    expected = {LARK, MICROSOFT_ENTRA, GOOGLE_SHEET} | ({LDAP} if LDAP in READERS else set())
    assert {one.source for one in GUIDES if one.connectable} == expected
    ldap = guide_for(LDAP)
    assert ldap is not None
    registered = {**READERS, LDAP: READERS[LARK]}
    monkeypatch.setattr("brain.console.staff_source_guide.READERS", registered)
    assert connectable(ldap)
    assert ldap.unavailable == ""
    monkeypatch.setattr(
        "brain.console.staff_source_guide.READERS",
        {name: one for name, one in READERS.items() if name != LDAP},
    )
    assert not connectable(ldap)
    assert "no nightly reader" in ldap.unavailable


@pytest.mark.parametrize("source", [LARK, MICROSOFT_ENTRA])
def test_the_credential_a_form_makes_is_the_one_the_nightly_reader_splits(source: str) -> None:
    """Delete this and the screen could keep `<secret>:<identifier>`, refused every night."""
    found = guide_for(source)
    assert found is not None
    ident, secret = found.credential_fields
    values = {LOCATION: "larksuite.com", ident: " cli_abc ", secret: "s3cret-value"}

    assert client_credential(found.credential_from(values)) == ("cli_abc", "s3cret-value")


def test_every_secret_box_goes_to_the_vault_and_the_location_never_does() -> None:
    """The guide refuses a secret outside the credential and a location inside it.

    Delete this and a secret box could be sent and kept nowhere, or the location could be kept
    where the screen can never show which directory the install reads."""
    for one in GUIDES:
        secrets = {box.key for box in one.fields if box.secret}
        assert secrets <= set(one.credential_fields)
        assert LOCATION not in one.credential_fields
    with pytest.raises(ValueError, match="secret that is not part"):
        Guide(
            source=LARK,
            title="t",
            where="w",
            steps=("s",),
            fields=(GuideField(key="stray", label="Stray", help="h", secret=True),),
            credential_fields=(),
        )
    with pytest.raises(ValueError, match="location in the vault"):
        Guide(
            source=LARK,
            title="t",
            where="w",
            steps=("s",),
            fields=(GuideField(key=LOCATION, label="Where", help="h"),),
            credential_fields=(LOCATION,),
        )
    with pytest.raises(ValueError, match="not a staff source"):
        Guide(source="nowhere", title="t", where="w", steps=("s",), fields=(), credential_fields=())
    assert "nowhere" not in SELECTABLE_BY_NAME


def test_a_missing_box_is_named_by_its_label_and_a_stray_box_repeats_nothing_sent() -> None:
    """Delete this and a refusal could echo what somebody pasted into a box that does not exist."""
    found = guide_for(LARK)
    assert found is not None
    pasted = "SENTINEL-pasted-secret-7f3a"

    missing = field_problems(found, {LOCATION: "larksuite.com", "app_id": "cli_a"})
    stray = field_problems(
        found,
        {LOCATION: "larksuite.com", "app_id": "cli_a", "app_secret": "x", pasted: pasted},
    )
    complete = field_problems(
        found, {LOCATION: "larksuite.com", "app_id": "cli_a", "app_secret": "x"}
    )

    assert missing == ('"App Secret" is empty.',)
    assert len(stray) == 1
    assert pasted not in " ".join(stray)
    assert complete == ()
