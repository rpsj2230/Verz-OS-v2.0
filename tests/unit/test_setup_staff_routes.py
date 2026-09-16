"""The staff list screen, end to end over HTTP: choose a source, sign in to it, pull the list.

M42.5.7 is claimed on the tests in this file, and on what they prove rather than on what the
module says. **Choose**: the wizard refuses a directory with nowhere to read it from and a
spreadsheet pointed somewhere, and the appointment hands both answers to the store that writes
them through `brain.ops.install_settings`, as settings the install can then read. **Sign in**:
the sign-in route answers the vendor's page for a holder of the setup code, and the trial
exchanges the code that comes back, with the verifier and the application's secret, at the
vendor's own address. **Pull**: the directory is walked with the token that exchange returned
and the plan a first run would make comes back, naming the people it would add.

**The vendor is a stand-in and nothing here has called one.** The stand-in is attached where the
process looks for a directory client, and it answers with the page shapes in
`tests/fixtures/roster_payloads.py`. A real sign-in needs an application the company registers
at its own directory, which is said on the screen and in `docs/install/authentication.md`.

Task ids: M42.5.7
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from brain.app import create_app
from brain.connectors.staff_directories import (
    GOOGLE_EXCHANGE_URL,
    MICROSOFT_LOGIN_HOST,
    REGISTRATION,
    RETURN_PATH,
    Answer,
    Outbound,
)
from brain.identity.staff_adapters import GOOGLE_WORKSPACE, LARK, MICROSOFT_ENTRA, SPREADSHEET
from brain.identity.staff_source import (
    STAFF_SOURCE_LOCATION_SETTING,
    STAFF_SOURCE_SETTING,
    selected_source,
)
from brain.install import hold_saved
from brain.setup_staff_routes import REGISTRATION_PATH, SIGN_IN_PATH, TRIAL_PATH
from brain.setup_wizard import (
    STAFF_SOURCE_BROKERS,
    StepId,
    answer,
    new_draft,
    settings_from,
)
from tests.fixtures.roster_payloads import (
    ENTRA_USERS_PAGE_ONE,
    ENTRA_USERS_PAGE_TWO,
    SPREADSHEET_EXPORT,
)
from tests.unit.test_setup_routes import EVERY_SCREEN, Store, appointing, body, minted_settings
from tests.unit.test_setup_wizard import INSIDE, SECRET, WRONG, an_enrolment

TENANT = "8f1a0e5c-0000-4000-8000-00000000000a"
RETURN = f"https://brain.example.invalid{RETURN_PATH}"
STATE = "S" * 32
CHALLENGE = "C" * 43
VERIFIER = "v" * 64
CLIENT = "client-id-123"
#: A client secret nothing else could contain.
CLIENT_SECRET = "CLIENT-SECRET-SENTINEL-51d0"
TOKEN = "ACCESS-TOKEN-SENTINEL-3e9a"


class Directory:
    """Microsoft, in memory: a token for the right exchange, and two pages of people for it."""

    def __init__(self) -> None:
        self.sent: list[Outbound] = []

    async def __call__(self, outbound: Outbound) -> Answer:
        self.sent.append(outbound)
        if outbound.url.startswith(f"https://{MICROSOFT_LOGIN_HOST}/"):
            form = outbound.form or {}
            right = (
                form.get("client_secret") == CLIENT_SECRET
                and form.get("code") == "RETURNED-CODE"
                and form.get("code_verifier") == VERIFIER
            )
            if not right:
                return Answer(400, {"error_description": "AADSTS70008: the code has expired"})
            return Answer(200, {"access_token": TOKEN, "token_type": "Bearer"})
        if outbound.headers.get("Authorization") != f"Bearer {TOKEN}":
            return Answer(401, {"error": {"message": "no token"}})
        if "skiptoken" in outbound.url:
            return Answer(200, ENTRA_USERS_PAGE_TWO)
        return Answer(200, ENTRA_USERS_PAGE_ONE)


@contextmanager
def serving(
    store: Store | None = None, fetch: Callable[[Outbound], Any] | None = None
) -> Iterator[TestClient]:
    app = create_app(minted_settings())
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.first_administrators = store if store is not None else Store()
        if fetch is not None:
            app.state.staff_directory_fetch = fetch
        yield c


@pytest.fixture(autouse=True)
def nothing_saved() -> Iterator[None]:
    """Saved installation values live on a module, so each test starts and ends with none."""
    before = hold_saved({})
    yield
    hold_saved(before)


def sheet_text(rows: tuple[tuple[str, ...], ...]) -> str:
    return "\n".join(",".join(row) for row in rows) + "\n"


def trial_body(**given: str) -> dict[str, str]:
    return {"setup_code": SECRET, **given}


def signed_in_trial() -> dict[str, str]:
    return trial_body(
        staff_source=MICROSOFT_ENTRA,
        location=TENANT,
        client_id=CLIENT,
        client_secret=CLIENT_SECRET,
        code="RETURNED-CODE",
        verifier=VERIFIER,
        redirect_uri=RETURN,
    )


def would_add(response: Any) -> list[str]:
    plan = response.json()["trial"]["plan"]
    assert plan is not None, response.json()
    return [one["work_address"] for one in plan["would_add"]]


# ============================================================ choose
def test_a_directory_pointed_nowhere_and_a_spreadsheet_pointed_somewhere_are_refused() -> None:
    """The two directions of the location rule, beside the box, and the positive of each.

    Delete this and a person finishes the wizard with a directory chosen and pointed nowhere,
    which every read after install refuses, or with a location written for a spreadsheet that
    nothing will ever read."""

    def problems(values: Mapping[str, str]) -> list[str]:
        _, found = answer(
            new_draft(),
            StepId.STAFF_SOURCE,
            values,
            an_enrolment(),
            SECRET,
            administrators=0,
            now=INSIDE,
        )
        return [one.key for one in found]

    assert problems({"staff_source": MICROSOFT_ENTRA}) == ["setup.error.location_needed"]
    assert problems({"staff_source": LARK, "staff_source_location": "lark.example"}) == [
        "setup.error.location_unusable"
    ]
    assert problems({"staff_source": SPREADSHEET, "staff_source_location": "x.example"}) == [
        "setup.error.location_not_wanted"
    ]
    assert problems({"staff_source": MICROSOFT_ENTRA, "staff_source_location": TENANT}) == []
    assert problems({"staff_source": LARK, "staff_source_location": "larksuite.com"}) == []
    assert problems({"staff_source": SPREADSHEET}) == []


def test_the_chosen_list_and_where_it_is_are_written_with_the_appointment() -> None:
    """The wizard writes what it collects. Both answers reach the store the appointment hands its
    settings to, which writes them through `brain.ops.install_settings` in the same transaction,
    and the pair is one `selected_source` accepts, so the install can read its own choice.

    Delete this and the staff list screen can go back to setting only the brokered directory,
    which leaves every install reading no staff list with nothing saying why."""
    chosen = {"staff_source": MICROSOFT_ENTRA, "staff_source_location": TENANT}
    store = Store()
    with serving(store) as c:
        response = appointing(c, body(answers={**EVERY_SCREEN, StepId.STAFF_SOURCE: chosen}))

    assert response.status_code == 200, response.json()
    [kept] = store.kept
    assert (kept[STAFF_SOURCE_SETTING], kept[STAFF_SOURCE_LOCATION_SETTING]) == (
        MICROSOFT_ENTRA,
        TENANT,
    )
    assert selected_source(env=kept).name == MICROSOFT_ENTRA
    draft, _ = answer(
        new_draft(),
        StepId.STAFF_SOURCE,
        chosen,
        an_enrolment(),
        SECRET,
        administrators=0,
        now=INSIDE,
    )
    assert settings_from(draft)[STAFF_SOURCE_SETTING] == MICROSOFT_ENTRA


def test_what_to_register_is_served_for_every_directory_the_wizard_offers() -> None:
    """The words the screen shows before anybody signs in. Every source the wizard offers is either
    a spreadsheet or has them, and the path the company registers is the one the sign-in checks.

    Delete this and a source can be offered on the screen with nothing telling the person what to
    register, which is a sign-in that cannot work and cannot say why."""
    with serving() as c:
        served = c.get(REGISTRATION_PATH).json()

    assert served["return_path"] == RETURN_PATH
    assert {one["source"] for one in served["sources"]} == set(STAFF_SOURCE_BROKERS) - {SPREADSHEET}
    assert all(one["where"] and one["grant"] and one["location"] for one in served["sources"])
    assert set(REGISTRATION) == {GOOGLE_WORKSPACE, MICROSOFT_ENTRA, LARK}


# ============================================================ sign in and pull
def test_a_spreadsheet_is_chosen_and_its_list_pulled_into_the_plan_a_first_run_would_make() -> None:
    """Choose and pull for the one source nobody signs in to. The file's rows are read by the
    spreadsheet adapter and the plan adds everybody still working there, removes nobody, and says
    why nothing is removed.

    Delete this and a spreadsheet install reaches the review screen with nobody ever having seen
    whether its file reads."""
    with serving() as c:
        response = c.post(
            TRIAL_PATH,
            json=trial_body(staff_source=SPREADSHEET, sheet=sheet_text(SPREADSHEET_EXPORT)),
        )

    assert response.status_code == 200
    trial = response.json()["trial"]
    assert trial["source"] == SPREADSHEET
    assert would_add(response) == ["ada@example.com", "grace@example.com", "katherine@example.com"]
    assert trial["plan"]["would_remove"] == []
    assert trial["plan"]["withheld"]


def test_a_directory_is_chosen_signed_in_to_and_its_list_pulled() -> None:
    """**The leaf, whole.** The sign-in route answers Microsoft's page for this tenant with the
    state and the challenge; the trial exchanges the returned code with the verifier and the
    secret at the tenant's token address; the directory is walked with the token that came back;
    and the plan names the people it would add, without the disabled account or the guest.

    Delete this and every half can pass on its own while the three never meet: a sign-in address
    nothing exchanges, an exchange whose token nothing walks, or a walk no route reaches."""
    directory = Directory()
    with serving(fetch=directory) as c:
        signing = c.post(
            SIGN_IN_PATH,
            json={
                "setup_code": SECRET,
                "staff_source": MICROSOFT_ENTRA,
                "location": TENANT,
                "client_id": CLIENT,
                "redirect_uri": RETURN,
                "state": STATE,
                "challenge": CHALLENGE,
            },
        )
        assert directory.sent == [], "the sign-in address contacted the directory"
        pulled = c.post(TRIAL_PATH, json=signed_in_trial())

    assert signing.status_code == 200
    address = signing.json()["address"]
    asked = {key: values[0] for key, values in parse_qs(urlsplit(address).query).items()}
    assert urlsplit(address).netloc == MICROSOFT_LOGIN_HOST
    assert urlsplit(address).path == f"/{TENANT}/oauth2/v2.0/authorize"
    assert (asked["state"], asked["code_challenge"]) == (STATE, CHALLENGE)

    assert pulled.status_code == 200, pulled.json()
    exchanged, *pages = directory.sent
    assert exchanged.url == f"https://{MICROSOFT_LOGIN_HOST}/{TENANT}/oauth2/v2.0/token"
    assert all(one.headers["Authorization"] == f"Bearer {TOKEN}" for one in pages)
    assert len(pages) == 2
    assert would_add(pulled) == ["ada@example.com", "katherine@example.com"]
    assert pulled.json()["trial"]["source"] == MICROSOFT_ENTRA


def test_a_sign_in_the_directory_refuses_is_told_in_its_words_and_nothing_is_walked() -> None:
    """The failing half of the leaf's test: a code the vendor will not exchange comes back as a
    refusal carrying the vendor's reason, with no plan, and no page is asked for.

    Delete this and an expired code can be drawn as a list with nobody in it."""
    directory = Directory()
    with serving(fetch=directory) as c:
        response = c.post(TRIAL_PATH, json={**signed_in_trial(), "code": "STALE"})

    trial = response.json()["trial"]
    assert trial["plan"] is None
    assert "AADSTS70008" in trial["refusals"][0]
    assert len(directory.sent) == 1


def test_a_client_secret_with_a_line_break_inside_is_refused_before_it_is_sent() -> None:
    """Judged by `brain.ops.credentials.problems_with`, in this screen's words. Delete this and a
    bad paste goes to the vendor and comes back as an authentication error nobody can read."""
    directory = Directory()
    with serving(fetch=directory) as c:
        response = c.post(TRIAL_PATH, json={**signed_in_trial(), "client_secret": "half\nsecret"})

    assert "client secret" in response.json()["trial"]["refusals"][0]
    assert directory.sent == []


def test_a_sign_in_address_for_an_unusable_location_is_a_problem_and_not_an_address() -> None:
    """Delete this and the route can answer an address built from a tenant with a path in it."""
    with serving() as c:
        response = c.post(
            SIGN_IN_PATH,
            json={
                "setup_code": SECRET,
                "staff_source": MICROSOFT_ENTRA,
                "location": "evil.example/x",
                "client_id": CLIENT,
                "redirect_uri": RETURN,
                "state": STATE,
                "challenge": CHALLENGE,
            },
        )

    assert response.status_code == 422
    assert response.json()["address"] == ""
    assert response.json()["problem"]


# ============================================================ the code comes first
@pytest.mark.parametrize("path", [SIGN_IN_PATH, TRIAL_PATH])
@pytest.mark.parametrize("code", [WRONG, ""])
def test_a_wrong_code_is_refused_as_nothing_here_before_anything_leaves_the_server(
    path: str, code: str
) -> None:
    """`NOTHING_LEAVES_THIS_SERVER_BEFORE_THE_CODE`. A wrong or blank code is the appointment's
    one 404, and the directory is never contacted.

    Delete this and whoever finds the address can make this server exchange a secret of their
    choosing with a vendor, from this server's address."""
    directory = Directory()
    sent = {**signed_in_trial(), "setup_code": code}
    if path == SIGN_IN_PATH:
        sent = {
            "setup_code": code,
            "staff_source": MICROSOFT_ENTRA,
            "location": TENANT,
            "client_id": CLIENT,
            "redirect_uri": RETURN,
            "state": STATE,
            "challenge": CHALLENGE,
        }
    with serving(fetch=directory) as c:
        refused = c.post(path, json=sent)
        finished = appointing(c, body(code=WRONG))

    assert refused.status_code == 404
    assert refused.json()["message"] == finished.json()["message"]
    assert directory.sent == []


def test_a_finished_install_refuses_the_right_code_and_contacts_nobody() -> None:
    """Delete this and the staff list screen outlives the wizard it belongs to, as a way to make a
    finished install contact a directory."""
    directory = Directory()
    with serving(Store(held=1), fetch=directory) as c:
        response = c.post(TRIAL_PATH, json=signed_in_trial())

    assert response.status_code == 404
    assert directory.sent == []


def test_no_answer_and_no_log_line_carries_the_client_secret_the_token_or_the_setup_code(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    """`A_CLIENT_CREDENTIAL_USED_FOR_ONE_READ_IS_NOT_KEPT` and
    `A_REFUSAL_REPEATS_THE_VENDOR_AND_NEVER_THE_REQUEST`, measured over a pull that worked, a
    refused exchange, a bad paste, and a body in the wrong shape carrying the secret.

    Delete this and a later edit can log the request that failed, or echo the body FastAPI
    refused, and the secret lands where the log is kept."""
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    seen: list[str] = []
    with serving(fetch=Directory()) as c:
        for sent in (
            signed_in_trial(),
            {**signed_in_trial(), "code": "STALE"},
            {**signed_in_trial(), "client_secret": f"{CLIENT_SECRET} x"},
            {**signed_in_trial(), "unexpected": CLIENT_SECRET},
        ):
            response = c.post(TRIAL_PATH, json=sent)
            seen.append(response.text)
            seen.extend(f"{name}: {value}" for name, value in response.headers.items())
    printed = capsys.readouterr()
    everything = "\n".join([*seen, printed.out, printed.err, caplog.text])

    assert CLIENT_SECRET not in everything
    assert TOKEN not in everything
    assert SECRET not in everything
    assert "staff list trial" in everything, "nothing was logged, so nothing was searched"
    assert GOOGLE_EXCHANGE_URL not in everything
