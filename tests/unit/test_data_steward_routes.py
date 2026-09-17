"""An install whose setup named no data steward names one from the console, once, and only an
administrator over everything with a second factor can.

The first half drives the routes through `tests.fixtures.console_http` with a stub pool, for the
refusals that must come before the database. The second half is the owner's own case on a real
database: an administrator appointed before the steward screen existed names themselves over HTTP,
and a second appointment is refused in a sentence. **It skips without a server.**

Task ids: M27.9.9
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
import pytest

from brain.api import API_PREFIX
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.data_steward_routes import (
    APPOINTING_ANOTHER,
    APPOINTING_YOURSELF,
    NOBODY_APPOINTED,
    STEWARD_AUTHORITY,
    STEWARD_PATH,
    TOLD,
    StewardAsked,
    named_by,
)
from brain.identity.data_steward import (
    APPOINTED_WITH,
    APPOINTMENT_GRANT_ID,
    StewardRefusal,
)
from brain.identity.first_administrator import ADMINISTRATION
from tests.fixtures.console_http import console_client, get, headers, post
from tests.fixtures.scratch_postgres import sql
from tests.unit.test_connector_store import entries
from tests.unit.test_console_control_audit import pressed
from tests.unit.test_data_steward import ADMIN, at_setup, connectable_install, reach_of
from tests.unit.test_setup_wizard import INSIDE

PATH = f"{API_PREFIX}{STEWARD_PATH}"
EVERYWHERE = Scope.unrestricted()

#: `u_admin` holds the authority over everything; `u_narrow` holds it over one department; `u_none`
#: holds nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (Grant(capability=STEWARD_AUTHORITY, scope=EVERYWHERE),),
    "u_narrow": (Grant(capability=STEWARD_AUTHORITY, scope=Scope.department("web")),),
    "u_none": (),
}


# ------------------------------------------------------------------------- no server


@pytest.mark.parametrize("pid", ["u_none", "u_narrow"])
def test_a_caller_without_the_authority_over_everything_is_refused_alike_with_or_without_a_pool(
    pid: str,
) -> None:
    """The same refusal with a database and without one, for the read and the write, and nothing
    asked of the pool. Delete this and a department's holder names the steward for the whole
    install, or a caller with nothing learns whether this process has a database."""
    with console_client(GRANTS, database=False) as (client, _):
        without = post(client, pid, PATH, {"same_as_administrator": True})
        read_without = get(client, pid, PATH)
    with console_client(GRANTS) as (client, stub):
        with_pool = post(client, pid, PATH, {"same_as_administrator": True})
        read_with = get(client, pid, PATH)

    assert without.status_code == with_pool.status_code == 404
    assert without.json()["message"] == with_pool.json()["message"]
    assert read_without.status_code == read_with.status_code == 404
    assert read_without.json()["message"] == read_with.json()["message"]
    assert "admin:" not in without.json()["message"]
    assert stub.statements == []


def test_a_sign_in_without_a_second_factor_holding_the_authority_cannot_name_a_steward() -> None:
    """`brain.gate.admission` withholds every `admin:` capability from a session with no second
    factor, and naming a steward is one. Delete this and the capability can be moved to a verb the
    admission lets through, so the root of every data read is named by whoever has a password."""
    with console_client(GRANTS) as (client, stub):
        weak = post(client, "u_admin", PATH, {"same_as_administrator": True}, strong=False)

    assert weak.status_code == 404
    assert stub.statements == []


def test_what_is_typed_is_judged_by_the_wizard_s_steward_screen_before_anything_is_written() -> (
    None
):
    """Blank boxes for another person, and a name beside the administrator's own choice, are each
    told against their box by the wizard's own keys and sentences, with no database asked. Delete
    this and the console can appoint a person with no name, or keep a rule of its own that comes
    apart from the wizard's."""
    with console_client(GRANTS, database=False) as (client, _):
        blank = post(client, "u_admin", PATH, {"same_as_administrator": False})
        both = post(
            client, "u_admin", PATH, {"same_as_administrator": True, "full_name": "A Person"}
        )
        unaddressed = post(
            client,
            "u_admin",
            PATH,
            {"same_as_administrator": False, "full_name": "A Person", "work_address": "nobody"},
        )

    assert blank.status_code == both.status_code == unaddressed.status_code == 422
    assert [(one["field"], one["key"]) for one in blank.json()["problems"]] == [
        ("steward_full_name", "setup.error.steward_needed"),
        ("steward_work_address", "setup.error.steward_needed"),
    ]
    assert [(one["field"], one["key"]) for one in both.json()["problems"]] == [
        ("steward_full_name", "setup.error.steward_not_wanted")
    ]
    assert [(one["field"], one["key"]) for one in unaddressed.json()["problems"]] == [
        ("steward_work_address", "setup.error.not_an_address")
    ]
    assert all(one["message"] for one in blank.json()["problems"])


def test_every_refusal_the_store_can_make_is_told_in_a_sentence_that_changes_nothing() -> None:
    """Delete this and a refusal added to the store reaches the administrator as a fault, or a
    sentence can stop saying that nothing was written, which is the fact they need before trying
    again."""
    assert set(TOLD) == set(StewardRefusal)
    assert all(
        "Nothing was changed" in one or "nothing was changed" in one for one in TOLD.values()
    )
    assert "Replacing" in TOLD[StewardRefusal.ALREADY_APPOINTED]


def test_the_body_names_the_caller_only_by_saying_so_and_otherwise_a_new_person() -> None:
    """Delete this and the choice can be read the wrong way round, so a person asking to name
    somebody else names themselves, or the name typed is dropped."""
    mine = named_by(StewardAsked(same_as_administrator=True), caller="u_me", minted="u_new")
    theirs = named_by(
        StewardAsked(same_as_administrator=False, full_name=" A Person ", work_address="a@b.c"),
        caller="u_me",
        minted="u_new",
    )

    assert (mine.principal_id, mine.display_name, mine.same_as_administrator) == ("u_me", "", True)
    assert (theirs.principal_id, theirs.display_name, theirs.same_as_administrator) == (
        "u_new",
        "A Person",
        False,
    )


def test_the_authority_is_an_administration_capability_every_first_administrator_holds() -> None:
    """So the owner's install, appointed before this screen, is granted it at the next start by
    `brain.identity.administration_reconciliation`. Delete this and the screen can ask for a
    capability nobody on an existing install holds, which is the missing bootstrap again."""
    assert STEWARD_AUTHORITY.value in ADMINISTRATION
    assert STEWARD_AUTHORITY.verb == "admin"


# ------------------------------------------------------------------------ the database


def test_an_administrator_names_themselves_steward_over_http_once_and_is_told_why_not_twice() -> (
    None
):
    """The owner's staging case end to end. An administrator appointed with no steward, signed in
    with the reach the resolver returns for them, is told nobody is appointed; names themselves the
    steward and is answered with themselves; and naming another person afterwards is a 409 with the
    sentence saying a steward is not replaced, with no principal minted. The appointment's grants
    are in the ledger against the administrator with their reach's digest. Delete this and the
    route can be green over a stub while the application role cannot write the appointment, or a
    second request replaces the steward. **Skips without a server.**"""
    with connectable_install("brain_steward_console") as url:
        at_setup(url, None)
        signed_in = {ADMIN: reach_of(url, ADMIN).grants}

        async def name(client: httpx.AsyncClient) -> dict[str, Any]:
            said: dict[str, Any] = {}
            before = await client.get(PATH, headers=headers(ADMIN))
            named = await client.post(
                PATH, json={"same_as_administrator": True}, headers=headers(ADMIN)
            )
            again = await client.post(
                PATH,
                json={
                    "same_as_administrator": False,
                    "full_name": "Somebody Else",
                    "work_address": "somebody.else@company.internal",
                },
                headers=headers(ADMIN),
            )
            said["before"] = (before.status_code, before.json())
            said["named"] = (named.status_code, named.json())
            said["again"] = (again.status_code, again.json()["message"], again.json()["trace_id"])
            return said

        said = pressed(url, signed_in, name)
        # Nobody but the administrator: the refused request minted no principal.
        principals = sql(url, "SELECT id FROM auth.principal WHERE id <> %s", ADMIN)
        granted = sql(
            url,
            "SELECT principal_id, capability FROM gate.capability_grant WHERE id = %s",
            APPOINTMENT_GRANT_ID,
        )
        recorded = [
            (one.actor_id, one.ent_hash != "0" * 32)
            for one in entries(url)
            if one.subject == f"grant:{APPOINTMENT_GRANT_ID}"
        ]
        holds = reach_of(url, ADMIN)

    assert said["before"] == (
        200,
        {
            "appointed": False,
            "principal_id": None,
            "display_name": None,
            "told": NOBODY_APPOINTED,
            "appointing_another": APPOINTING_ANOTHER,
            "appointing_yourself": APPOINTING_YOURSELF,
        },
    )
    status, body = said["named"]
    assert (status, body["appointed"], body["principal_id"]) == (200, True, ADMIN)
    assert said["again"][:2] == (409, TOLD[StewardRefusal.ALREADY_APPOINTED])
    assert said["again"][2]
    assert principals == []
    assert granted == [(ADMIN, "read:console.content")]
    assert recorded == [(ADMIN, True)]
    for one in APPOINTED_WITH:
        scope = holds.scope_for(Capability(value=one), INSIDE)
        assert scope is not None and scope.is_unrestricted()
