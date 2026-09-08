"""The install wizard: the first screens of the product and the only ones a stranger reads.

Every fixture date here is 2019, which is deliberate and is CLAUDE.md's rule: nothing in this
file is about the present, so a date near today would turn a passing suite into one that
reports a defect on a schedule nobody chose. The enrolment window is an hour and the three
instants below sit either side of it.

The setup code in this file is a string of the right length and nothing else. There is no
generator in `brain.setup_wizard` to exercise, which is the module's central claim and is
checked by `minting_gaps` rather than by producing a value here.
"""

from __future__ import annotations

import ast
import json
import os
import re
import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import pytest

from brain.deployment.installer import INSTALL_ENV_FILE, step_named
from brain.firstrun import (
    GRANTED_BY,
    MIN_SECRET_CHARS,
    Enrolment,
    digest_of,
    open_enrolment,
)
from brain.identity.roles import Role
from brain.identity.staff_adapters import ADAPTER_SOURCES
from brain.install import BY_NAME
from brain.install import missing as settings_missing
from brain.locale import MESSAGES, FieldError, FormField, catalogue_gaps
from brain.setup_wizard import (
    CALLBACK_PATH,
    DRAFT_FILE_NAME,
    DRAFT_MODE,
    ENTRY_POINTS,
    LOCAL_ONLY,
    MAX_ANSWER_CHARS,
    MAX_KEY_CHARS,
    MODEL_PROFILES,
    REVIEW_STATES,
    SECRET_ANSWERS,
    SETUP_CODE_CHARS,
    SNAPSHOT_VERSION,
    STAFF_SOURCE_BROKERS,
    WIZARD,
    Applied,
    Draft,
    Progress,
    Question,
    ReviewLine,
    Step,
    StepId,
    WizardClosedError,
    WizardError,
    WizardLockedError,
    answer,
    apply_install,
    discard_draft,
    draft_from,
    is_answered,
    minting_gaps,
    module_functions,
    new_draft,
    next_step,
    problems_with,
    progress_for,
    read_draft,
    reopening_gaps,
    review,
    settings_from,
    skip,
    snapshot,
    step_for,
    unlock,
    wizard_gaps,
    write_draft,
)

# ------------------------------------------------------------------ fixtures with no clock
ISSUED = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
INSIDE = ISSUED + timedelta(minutes=20)
AFTER = ISSUED + timedelta(hours=2)

#: A value of the length the installer prints, and nothing more. Never a real code.
SECRET = "setup-code-" + "0" * 53
WRONG = "wrong-code-" + "0" * 53

PERSON = "person-0001"

REPO = Path(__file__).resolve().parents[2]

COMPANY_ANSWERS = MappingProxyType(
    {
        "company_name": "A Company",
        "product_name": "Knowledge Desk",
        "web_address": "https://brain.internal",
        "logo_url": "https://brand.internal/mark.svg",
    }
)
ADMIN_ANSWERS = MappingProxyType(
    {"full_name": "A Person", "work_address": "a.person@company.internal"}
)
SOURCE_ANSWERS = MappingProxyType({"staff_source": "google_workspace"})
LOCAL_ANSWERS = MappingProxyType({"model_profile": "local"})
HOSTED_ANSWERS = MappingProxyType(
    {"model_profile": "hosted", "model_provider": "anthropic", "provider_key": "k" * 40}
)


def an_enrolment(*, spent: bool = False) -> Enrolment:
    """The one enrolment an install gets, opened from a digest the way the installer would."""
    opened = open_enrolment(digest=digest_of(SECRET), issued_at=ISSUED)
    return replace(opened, claimed_at=INSIDE) if spent else opened


def answered(*, hosted: bool = False, skip_connections: bool = True) -> Draft:
    """A draft with every screen finished, built through the wizard's own entry point."""
    draft = new_draft()
    for key, values in (
        (StepId.COMPANY, COMPANY_ANSWERS),
        (StepId.ADMINISTRATOR, ADMIN_ANSWERS),
        (StepId.STAFF_SOURCE, SOURCE_ANSWERS),
        (StepId.MODEL_PROVIDER, HOSTED_ANSWERS if hosted else LOCAL_ANSWERS),
    ):
        draft, problems = answer(
            draft,
            key,
            values,
            an_enrolment(),
            SECRET,
            administrators=0,
            now=INSIDE,
        )
        assert problems == (), (key, problems)
    if skip_connections:
        return skip(draft, StepId.CONNECTIONS, an_enrolment(), SECRET, administrators=0, now=INSIDE)
    draft, problems = answer(
        draft,
        StepId.CONNECTIONS,
        {"connections": "xero, hubspot"},
        an_enrolment(),
        SECRET,
        administrators=0,
        now=INSIDE,
    )
    assert problems == ()
    return draft


def a_field(name: str, *, errors: dict[str, str] | None = None) -> FormField:
    """A form field for a wizard built to fail, with whichever keys the test needs."""
    return FormField(
        name=name,
        label_key="setup.step.review.title",
        errors={"blank": "setup.error.blank", "too_long": "setup.error.too_long"}
        if errors is None
        else errors,
    )


# ------------------------------------------------------------------ M42.5.3, the setup code
def test_the_first_screen_asks_for_the_setup_code_and_for_nothing_else() -> None:
    """M42.5.3 says whoever loads the page first cannot claim the system, and the only thing
    that makes that true is that the code is asked before anything else. A wizard that asked
    at the end would already have let a stranger read the company's name, its staff source and
    its model configuration on the way there.

    Delete this and the setup code screen can be moved anywhere in the order, including after
    the screens whose contents it exists to protect."""
    first = WIZARD[0]
    assert first.key is StepId.SETUP_CODE
    assert [one.field.name for one in first.questions] == ["setup_code"]
    assert first.questions[0].secret is True


def test_a_wrong_code_an_expired_one_and_a_spent_one_refuse_in_the_same_words() -> None:
    """M42.5.3. Telling the three apart tells somebody whether the value they typed was ever
    right, which is `brain.firstrun.A_REFUSAL_THAT_SAYS_WHY_IS_AN_ORACLE` one step out.

    Delete this and one of the three can acquire its own message, which is the whole oracle:
    an attacker who can tell "expired" from "wrong" knows when they have guessed."""
    wrong = unlock(an_enrolment(), {"setup_code": WRONG}, administrators=0, now=INSIDE)
    expired = unlock(an_enrolment(), {"setup_code": SECRET}, administrators=0, now=AFTER)
    spent = unlock(an_enrolment(spent=True), {"setup_code": SECRET}, administrators=0, now=INSIDE)
    refused = (FieldError(field="setup_code", key="setup.error.refused"),)
    assert wrong == refused
    assert expired == refused
    assert spent == refused


def test_the_right_code_opens_the_first_screen_and_does_not_spend_it() -> None:
    """M42.5.3, and the sibling of the refusal test above: a gate tested only by its refusals
    is satisfied by a gate that refuses everything. The second half is the decision: `claim`
    spends on a correct presentation and `unlock` drops what it returns, so an install whose
    browser was closed after screen one still has its one way in.

    Delete this and `unlock` can start keeping the spent enrolment, which brings the install
    down to a single visit and gives the client no way back after a closed tab."""
    enrolment = an_enrolment()
    assert unlock(enrolment, {"setup_code": SECRET}, administrators=0, now=INSIDE) == ()
    assert enrolment.spent is False
    assert unlock(enrolment, {"setup_code": SECRET}, administrators=0, now=INSIDE) == ()
    finished = apply_install(
        answered(), enrolment, SECRET, principal_id=PERSON, administrators=0, now=INSIDE
    )
    assert finished.enrolment.spent is True


def test_wrong_codes_do_not_run_out_and_a_spent_one_cannot_be_replayed() -> None:
    """M42.5.3, and the two halves of `AN_ATTEMPT_LIMIT_IS_A_WAY_TO_DESTROY_THE_ONLY_WAY_IN`.
    A counter that sealed the enrolment after some number of wrong tries would hand anybody who
    can reach the page a reliable way to make the install unclaimable, so wrong presentations
    cost nothing and the right one still works after them. What does end is the claim itself:
    once it has bought an administrator the same value buys nothing again.

    Delete this and an attempt limit can be added here, which converts a guessing attack with
    no chance of success into a denial of service with a guaranteed one, and the replay half
    stops being checked at the only entry point that spends anything."""
    enrolment = an_enrolment()
    refused = (FieldError(field="setup_code", key="setup.error.refused"),)
    for _ in range(25):
        assert unlock(enrolment, {"setup_code": WRONG}, administrators=0, now=INSIDE) == refused
    assert unlock(enrolment, {"setup_code": SECRET}, administrators=0, now=INSIDE) == ()
    finished = apply_install(
        answered(), enrolment, SECRET, principal_id=PERSON, administrators=0, now=INSIDE
    )
    with pytest.raises(WizardLockedError):
        apply_install(
            answered(),
            finished.enrolment,
            SECRET,
            principal_id=PERSON,
            administrators=0,
            now=INSIDE,
        )


def test_an_empty_setup_code_box_is_told_it_is_empty_and_not_that_it_is_wrong() -> None:
    """M42.5.3 and M42.5.13. The shape of the answer is judged before its value, so an empty
    box and a pasted document earn the message they would on any other screen. "That code was
    not accepted" in front of an empty box is a sentence about a value nobody typed, and it is
    also the one message on this screen that a person cannot act on.

    A mutation run is what found this: with the shape check removed, a blank code reached the
    comparison and came back refused, and nothing in the suite could tell the two apart.

    Delete this and the first screen has one message for every way of getting it wrong."""
    assert unlock(an_enrolment(), {}, administrators=0, now=INSIDE) == (
        FieldError(field="setup_code", key="setup.error.blank"),
    )
    assert unlock(an_enrolment(), {"setup_code": "   "}, administrators=0, now=INSIDE) == (
        FieldError(field="setup_code", key="setup.error.blank"),
    )
    pasted = {"setup_code": "0" * (MAX_ANSWER_CHARS + 1)}
    assert unlock(an_enrolment(), pasted, administrators=0, now=INSIDE) == (
        FieldError(field="setup_code", key="setup.error.too_long"),
    )


def test_a_rejected_screen_records_nothing_and_hands_back_what_is_wrong() -> None:
    """M42.5.13 and M42.5.10 at once. A screen that refused has to leave the draft exactly as
    it was, or the person who typed a bad address and pressed back has an install carrying it.
    Both halves matter and a mutation run showed why: dropping the refusal branch made `answer`
    record the bad values and report no problems, and every other test in this file stayed
    green because none of them answered a screen wrongly.

    Delete this and the wizard can accumulate answers it refused, which reach the review screen
    as though somebody had approved them."""
    before = answered()
    after, problems = answer(
        before,
        StepId.COMPANY,
        {**COMPANY_ANSWERS, "web_address": "brain.internal"},
        an_enrolment(),
        SECRET,
        administrators=0,
        now=INSIDE,
    )
    assert problems == (FieldError(field="web_address", key="setup.error.not_absolute"),)
    assert after is before
    assert after.values_for(StepId.COMPANY)["web_address"] == "https://brain.internal"


def test_the_setup_code_is_never_recorded_anywhere_a_resume_could_read_it() -> None:
    """M42.5.3 and M42.5.12 together. The code is secret, so its screen stores nothing, so it
    is not somewhere `next_step` can land and not something `snapshot` can write. There is no
    special case anywhere saying so: it falls out of the question being marked secret.

    Delete this and the setup code becomes an ordinary answer, which puts it in the draft file
    beside the company name and makes the install resumable by anybody who can read that
    file."""
    assert step_for(StepId.SETUP_CODE).stores is False
    assert "setup_code.setup_code" in SECRET_ANSWERS
    with pytest.raises(WizardError, match="stores nothing"):
        answer(
            new_draft(),
            StepId.SETUP_CODE,
            {"setup_code": SECRET},
            an_enrolment(),
            SECRET,
            administrators=0,
            now=INSIDE,
        )
    assert StepId.SETUP_CODE.value not in snapshot(answered())["answers"]


def test_the_first_screen_accepts_a_code_of_the_length_the_installer_prints() -> None:
    """M42.5.3 is one leaf across two modules and nothing else compares the ends. The
    installer's mint step is `openssl rand -hex N`, which prints 2N characters, and the first
    screen caps an answer at `MAX_ANSWER_CHARS`. A cap below that length would refuse the one
    value the installer guarantees, and the failure would appear on a client's server.

    The byte count is read out of the installer's own shell rather than repeated here, so
    changing either end fails this test. Delete it and the two halves of one leaf can drift
    apart with both files looking correct."""
    minting = step_named("mint this installation's secrets").run
    matched = re.search(r"BRAIN_SETUP_SECRET=%s.*?openssl rand -hex (\d+)", minting, re.S)
    assert matched is not None, minting
    assert 2 * int(matched.group(1)) == SETUP_CODE_CHARS
    assert MIN_SECRET_CHARS <= SETUP_CODE_CHARS <= MAX_ANSWER_CHARS < MAX_KEY_CHARS
    assert unlock(an_enrolment(), {"setup_code": SECRET}, administrators=0, now=INSIDE) == ()
    assert len(SECRET) == SETUP_CODE_CHARS


def test_nothing_in_this_module_mints_or_re_issues_a_credential() -> None:
    """M42.5.3, and the sentence the module is built around: the owner of this repository does
    not create a password on a client's behalf. A generator here would put a value in this
    file, and a call to `open_enrolment` here would make this module the one that decides when
    a client's window closes.

    Delete this and a helper that mints a code "for the tests" can be added to the module with
    nothing objecting, which is exactly how a repository comes to ship a credential."""
    assert minting_gaps() == ()


def test_a_module_that_minted_its_own_setup_code_would_be_reported() -> None:
    """M42.5.3. A check that has never reported anything is a check nobody knows works, and
    `minting_gaps` reads a syntax tree, so both call shapes have to be covered: a bare name
    and an attribute on a module. A name in a docstring must not be a finding, or the check is
    one people switch off.

    Delete this and `minting_gaps` can be narrowed to nothing and stay green on the real
    module, which is the only module it ever runs against."""
    minting = minting_gaps("import secrets\ndef mint():\n    return secrets.token_hex(32)\n")
    assert len(minting) == 1
    assert "token_hex" in minting[0]
    reissued = minting_gaps("def again(d, t):\n    return open_enrolment(digest=d, issued_at=t)\n")
    assert len(reissued) == 1
    assert "open_enrolment" in reissued[0]
    assert minting_gaps('"""A docstring mentioning token_hex and open_enrolment."""\n') == ()


def test_every_screen_behind_the_first_one_requires_the_setup_code() -> None:
    """M42.5.3. The draft of this module checked the code on the first screen and on the final
    write and nowhere between, so a stranger who never called `unlock` could walk every screen
    and read the review. A gate on the first screen is a gate only if nothing behind it can be
    reached without passing through it.

    Delete this and the check can go back to the two ends, which is the same as no check: a
    browser posting straight to the company screen never passes the first one."""
    draft = answered()
    with pytest.raises(WizardLockedError):
        answer(
            draft,
            StepId.COMPANY,
            COMPANY_ANSWERS,
            an_enrolment(),
            WRONG,
            administrators=0,
            now=INSIDE,
        )
    with pytest.raises(WizardLockedError):
        skip(draft, StepId.CONNECTIONS, an_enrolment(), WRONG, administrators=0, now=INSIDE)
    with pytest.raises(WizardLockedError):
        review(draft, an_enrolment(), WRONG, administrators=0, now=INSIDE)
    with pytest.raises(WizardLockedError):
        apply_install(
            draft, an_enrolment(), WRONG, principal_id=PERSON, administrators=0, now=INSIDE
        )


def test_a_screen_that_could_not_ask_for_the_setup_code_would_be_reported() -> None:
    """M42.5.3 and M42.5.11. `reopening_gaps` reads signatures, so an entry point that takes
    no enrolment cannot compare a code whatever its body says. Tested against a module built
    to fail, because a check that can only run against the real thing has no test for the case
    it exists to find.

    Delete this and the enrolment finding can be dropped from `reopening_gaps` while the real
    module keeps passing, and the next entry point added without a code is unguarded."""

    def open_screen(draft: Draft, *, administrators: int) -> None:
        return None

    found = reopening_gaps({"open_screen": open_screen}, ("open_screen",))
    assert len(found) == 1
    assert "does not take the enrolment" in found[0]


# ------------------------------------------------------------------ M42.5.4, counted screens
def test_every_screen_is_counted_against_the_length_of_the_wizard() -> None:
    """M42.5.4 asks for numbered steps with visible progress. `of` is `len(steps)` and never a
    constant, which is the failure `brain.deployment.installer.PLAN` still carries: its comment
    says ten steps and it has had twelve since somebody appended two.

    Delete this and a total can be typed into the module, where it stays right until the next
    screen is added and then tells every person installing how much is left, wrongly."""
    counted = [progress_for(one.key) for one in WIZARD]
    assert [one.number for one in counted] == list(range(1, len(WIZARD) + 1))
    assert {one.of for one in counted} == {len(WIZARD)}


def test_adding_a_screen_renumbers_the_total_on_every_other_screen() -> None:
    """M42.5.4. The arithmetic is tested against a wizard built for the test rather than only
    against the real one, so the property is about the function and not about today's eight
    screens.

    Delete this and `progress_for` can be pinned to the real wizard's length and pass."""
    three = (
        Step(key=StepId.SETUP_CODE, title_key="setup.step.setup_code.title"),
        Step(key=StepId.COMPANY, title_key="setup.step.company.title"),
        Step(key=StepId.FINISH, title_key="setup.step.finish.title"),
    )
    assert progress_for(StepId.COMPANY, three) == Progress(number=2, of=3, back=StepId.SETUP_CODE)
    assert progress_for(StepId.COMPANY).of == len(WIZARD)


def test_only_the_first_and_the_last_screen_have_nothing_behind_them() -> None:
    """M42.5.4 asks for a back button on every screen, and two screens cannot have one. The
    first has nothing behind it. The last has the install behind it, and a back button there
    would offer to unwrite what has been written. The rule is positional so it holds for a
    wizard built for a test as well as for this one.

    Delete this and a back button appears on the finishing screen, which is either a lie or a
    second write path into an install that already has an administrator."""
    assert progress_for(WIZARD[0].key).back is None
    assert progress_for(WIZARD[-1].key).back is None
    middles = [one.key for one in WIZARD[1:-1]]
    assert all(progress_for(key).back is not None for key in middles)
    assert progress_for(StepId.REVIEW).back is StepId.CONNECTIONS


def test_a_position_outside_the_wizard_is_refused_rather_than_rendered() -> None:
    """M42.5.4. "Step 0 of 8" and "step 9 of 8" are both things a person can read, and both
    mean the counting is wrong somewhere the reader cannot see.

    Delete this and `Progress` will hold any pair of numbers, so a renumbering bug renders as
    a sentence instead of failing."""
    with pytest.raises(WizardError, match="counted from one"):
        Progress(number=0, of=3, back=None)
    with pytest.raises(WizardError, match="past the end"):
        Progress(number=4, of=3, back=None)
    with pytest.raises(WizardError, match="no position in it"):
        progress_for(StepId.REVIEW, WIZARD[:2])


# ------------------------------------------------------------------ M42.5.5, the company
def test_the_company_screen_asks_the_name_the_address_and_the_logo() -> None:
    """M42.5.5 names company name, logo and web address. All three are on one screen, because
    they are the three things one person answers from one page of their own brand guidelines.

    Delete this and a question can be dropped from the screen without anything noticing, which
    is a value the install then takes a neutral default for on a client's server."""
    names = [one.field.name for one in step_for(StepId.COMPANY).questions]
    assert names == ["company_name", "product_name", "web_address", "logo_url"]
    assert problems_with(step_for(StepId.COMPANY), COMPANY_ANSWERS) == ()


def test_the_logo_is_a_web_address_and_never_an_upload() -> None:
    """M42.5.5 says logo upload and this collects an address, which is the substitution the
    module states rather than leaves to be discovered. The setting it feeds is
    `INSTALL_LOGO_URL`, whose declared meaning is a URL served from somewhere the client
    controls, so collecting an address into it is the version that works.

    Delete this and the substitution stops being recorded anywhere a reader will find it, and
    the next person reads the leaf and assumes a file arrives."""
    logo = next(one for one in step_for(StepId.COMPANY).questions if one.field.name == "logo_url")
    assert logo.setting == "INSTALL_LOGO_URL"
    assert logo.required is False
    assert "URL" in BY_NAME["INSTALL_LOGO_URL"].meaning
    refused = problems_with(step_for(StepId.COMPANY), {**COMPANY_ANSWERS, "logo_url": "brand.png"})
    assert refused == (FieldError(field="logo_url", key="setup.error.not_absolute"),)


@pytest.mark.parametrize(
    "address",
    ["brain.internal", "ftp://brain.internal", "file://brain.internal/logo.svg", "https://", "/"],
)
def test_an_address_a_browser_cannot_be_sent_to_is_refused(address: str) -> None:
    """M42.5.5 and M42.5.13. Two separate mistakes and each needs its own case, which a
    mutation run is what proved: a value with no scheme is caught by the host rule as well, so
    a test using only `brain.internal` leaves the scheme rule unreachable and deletable. The
    discriminating case is a scheme with a host behind it. `ftp://` and `file://` both parse
    into a perfectly good host, and both end up in an image tag or in a redirect URI.

    `https` is not required and `http` is accepted, because an install on a private network
    behind its own terminator is a real deployment.

    Delete this and the address rule collapses to one of its two halves, and the wizard
    accepts either a bare host or a scheme no browser will follow."""
    for field_name in ("web_address", "logo_url"):
        assert problems_with(
            step_for(StepId.COMPANY), {**COMPANY_ANSWERS, field_name: address}
        ) == (FieldError(field=field_name, key="setup.error.not_absolute"),)
    for allowed in ("http://brain.internal", "https://brain.internal/base"):
        assert (
            problems_with(step_for(StepId.COMPANY), {**COMPANY_ANSWERS, "web_address": allowed})
            == ()
        )


def test_the_redirect_uri_is_derived_from_the_web_address_and_never_asked_for() -> None:
    """M42.5.5. A client typing a redirect URI is a client typing the one value whose being
    wrong is an open redirect, and it is the same string on every install, so it is arithmetic
    rather than a question.

    **The path is checked against the realm rather than against itself.** Comparing the
    derived value with an f-string containing `CALLBACK_PATH` moves both sides together, so
    the constant could hold any value and pass. What decides it is `ops/keycloak/realm-export.json`,
    which is where Keycloak learns which redirect URIs it will hand a code to, and a wizard
    registering a path that realm does not carry produces a sign-in that completes and then
    bounces to a page the client does not own.

    Delete this and somebody adds a redirect URI field to the company screen because the
    setting is required, and the wizard starts collecting the value it exists to compute."""
    assert not any(
        one.setting == "INSTALL_OIDC_REDIRECT_URIS" for step in WIZARD for one in step.questions
    )
    realm = json.loads((REPO / "ops" / "keycloak" / "realm-export.json").read_text("utf-8"))
    registered = [
        uri
        for client in realm["clients"]
        for uri in client.get("redirectUris", ())
        if not uri.endswith(".invalid")
    ]
    assert registered
    assert all(uri.endswith(CALLBACK_PATH) for uri in registered), registered
    settings = settings_from(answered())
    assert settings["INSTALL_OIDC_REDIRECT_URIS"] == "https://brain.internal/auth/callback"
    assert settings["INSTALL_COMPANY_NAME"] == "A Company"
    assert settings["INSTALL_LOGO_URL"] == "https://brand.internal/mark.svg"


def test_a_web_address_with_a_trailing_slash_makes_one_redirect_uri_not_two() -> None:
    """M42.5.5. `https://brain.internal/` and `https://brain.internal` are the same install and
    a realm that was told `//auth/callback` accepts nothing.

    Delete this and an install typed with a trailing slash registers a redirect URI the
    identity provider will never match, and sign-in fails after the wizard reported success."""
    draft, problems = answer(
        new_draft(),
        StepId.COMPANY,
        {**COMPANY_ANSWERS, "web_address": "https://brain.internal/"},
        an_enrolment(),
        SECRET,
        administrators=0,
        now=INSIDE,
    )
    assert problems == ()
    assert settings_from(draft)["INSTALL_OIDC_REDIRECT_URIS"] == (
        f"https://brain.internal{CALLBACK_PATH}"
    )


def test_the_wizard_leaves_exactly_one_required_setting_for_the_installer() -> None:
    """M42.5.5 and M42.5.6 produce settings, and a completed wizard that still cannot boot the
    install is the failure nobody notices from inside this module. `INSTALL_OIDC_ISSUER` is
    deliberately not asked for: an issuer guessed from the web address is a sign-in page
    pointing at somebody else's identity provider.

    Delete this and a required setting added to `brain.install` later is silently one the
    wizard does not collect, and the omission surfaces on a client's server as a refusal to
    start."""
    assert settings_missing(dict(settings_from(answered()))) == ("INSTALL_OIDC_ISSUER",)


# ------------------------------------------------------------ M42.5.6, the first administrator
def test_the_first_administrator_becomes_a_standing_super_admin() -> None:
    """M42.5.6. Standing rather than a deputy: `brain.identity.roles` keeps a floor of two
    standing Super Admins and a deputy does not count towards it, so a first administrator who
    was a deputy would leave the install permanently below its own floor.

    Delete this and the one grant that has no author to review it can be made at any role, on
    a screen nobody has authenticated to."""
    finished = apply_install(
        answered(), an_enrolment(), SECRET, principal_id=PERSON, administrators=0, now=INSIDE
    )
    assert finished.grant.role is Role.SUPER_ADMIN
    assert finished.grant.principal_id == PERSON
    assert finished.grant.granted_by == GRANTED_BY
    assert finished.grant.deputy_of is None
    assert finished.grant.granted_at == INSIDE


def test_the_administrator_screen_asks_for_the_address_they_sign_in_with() -> None:
    """M42.5.6 and M42.5.13. What a work address is has one answer in this repository, on
    `StaffRecord`, and this delegates to it rather than carrying a second rule that would
    accept an address the roster later rejects.

    Delete this and the wizard grows its own idea of an address, so the first administrator
    can be created against a value no staff source will ever match."""
    step = step_for(StepId.ADMINISTRATOR)
    assert [one.field.name for one in step.questions] == ["full_name", "work_address"]
    assert problems_with(step, ADMIN_ANSWERS) == ()
    assert problems_with(step, {**ADMIN_ANSWERS, "work_address": "a person"}) == (
        FieldError(field="work_address", key="setup.error.not_an_address"),
    )


# ------------------------------------------------------------------ M42.5.8, the AI provider
def test_a_hosted_profile_with_no_key_and_no_provider_says_both() -> None:
    """M42.5.8. A hosted profile with no key is an install that cannot answer a question and
    says so on the first afternoon. Both findings are reported at once because fixing one
    leaves a screen that still refuses.

    Delete this and the model screen can advance with half an answer, which produces an
    install that looks configured and cannot reach a model."""
    refused = problems_with(step_for(StepId.MODEL_PROVIDER), {"model_profile": "hosted"})
    assert refused == (
        FieldError(field="model_provider", key="setup.error.provider_needed"),
        FieldError(field="provider_key", key="setup.error.key_needed"),
    )


def test_a_local_profile_carrying_a_key_cannot_advance() -> None:
    """M42.5.8, and the direction that would otherwise be silent. A local profile with a key is
    an install where somebody supplied a credential the routing will never reach and believes
    their questions are going to that provider. Nothing fails, and the belief is wrong for as
    long as it lasts.

    Delete this and a client can leave the wizard convinced their questions go to a provider
    they pasted a key for, when every question is answered on their own hardware."""
    refused = problems_with(
        step_for(StepId.MODEL_PROVIDER), {"model_profile": "local", "provider_key": "k" * 40}
    )
    assert refused == (FieldError(field="provider_key", key="setup.error.key_not_wanted"),)


def test_a_local_only_profile_is_a_complete_answer_on_its_own() -> None:
    """M42.5.8 asks for either their own key or a local-only profile with no external provider.
    A rule tested only by its refusals is satisfied by a rule that refuses everything.

    Delete this and the model screen can start requiring a provider, which makes the
    local-only install the one that cannot be completed."""
    assert problems_with(step_for(StepId.MODEL_PROVIDER), LOCAL_ANSWERS) == ()
    assert problems_with(step_for(StepId.MODEL_PROVIDER), HOSTED_ANSWERS) == ()
    assert LOCAL_ONLY in MODEL_PROFILES
    assert settings_from(answered())["INSTALL_MODEL_PROFILE"] == LOCAL_ONLY


def test_a_profile_that_is_neither_says_only_that() -> None:
    """M42.5.8 and M42.5.13. Adding two more messages to a screen whose first field is wrong
    buries the one the person can act on, so the cross-field rule stays silent until the
    profile is one of the two.

    Delete this and a typo in the profile produces three messages, two of which are about
    fields the person has not reached yet."""
    refused = problems_with(step_for(StepId.MODEL_PROVIDER), {"model_profile": "cloudy"})
    assert refused == (FieldError(field="model_profile", key="setup.error.unknown_choice"),)


def test_the_provider_key_leaves_on_the_result_and_never_in_the_settings() -> None:
    """M42.5.8. `brain.ops.provider_keys` is where a provider key lives and an environment file
    is not it, so the key travels on the result to the vault while every other answer travels
    in the settings map.

    Delete this and the key can acquire a setting name, which puts a standing credential on a
    line of a file nobody rotates and in every process that reads the environment."""
    finished = apply_install(
        answered(hosted=True),
        an_enrolment(),
        SECRET,
        principal_id=PERSON,
        administrators=0,
        now=INSIDE,
    )
    assert finished.provider == "anthropic"
    assert finished.provider_key == "k" * 40
    assert not any(value == "k" * 40 for value in finished.settings.values())
    assert not any(one.secret and one.setting for step in WIZARD for one in step.questions)


def test_the_provider_key_is_not_in_the_repr_of_what_the_wizard_returns() -> None:
    """M42.5.8. An exception raised anywhere holding this object renders every field into the
    traceback, and a traceback is written to a log by whatever catches it. `brain.firstrun.Claim`
    solves the same problem by having no such field; that is not available here, because
    somebody has to carry the key from the screen to the vault.

    Delete this and the first unhandled error on the install path puts a standing provider
    credential into the log the client keeps forever."""
    finished = apply_install(
        answered(hosted=True),
        an_enrolment(),
        SECRET,
        principal_id=PERSON,
        administrators=0,
        now=INSIDE,
    )
    assert "k" * 40 not in repr(finished)
    assert "anthropic" in repr(finished)


def test_a_result_that_says_local_and_carries_a_key_is_refused() -> None:
    """M42.5.8, said at the type rather than only at the screen. The model screen refuses this
    combination, and a result built by anything other than a reviewed draft would not have
    been past that screen.

    Delete this and the guard exists only where a person types, so any other caller can
    produce an install that keeps a credential nothing will ever reach."""
    finished = apply_install(
        answered(), an_enrolment(), SECRET, principal_id=PERSON, administrators=0, now=INSIDE
    )
    with pytest.raises(WizardError, match="own hardware"):
        replace(finished, provider="anthropic", provider_key="k" * 40)


def test_a_provider_named_without_a_key_is_half_an_answer() -> None:
    """M42.5.8. A provider with no key and a key with no provider are both halves that nothing
    downstream can act on: `brain.ops.provider_keys` needs a slot and a value together.

    Delete this and a half-filled result reaches the vault write, where the failure is a
    missing slot on a client's server rather than a refusal here."""
    finished = apply_install(
        answered(hosted=True),
        an_enrolment(),
        SECRET,
        principal_id=PERSON,
        administrators=0,
        now=INSIDE,
    )
    with pytest.raises(WizardError, match="half an answer"):
        replace(finished, provider_key="")
    with pytest.raises(WizardError, match="half an answer"):
        replace(finished, provider="")


# ------------------------------------------------------------------ M42.5.10, review then write
def test_the_review_lists_every_question_on_every_storing_screen() -> None:
    """M42.5.10. Listing only what was answered would make an omission invisible on the one
    screen whose whole job is to show what is about to happen: an unset logo and a logo nobody
    was asked about read identically once the install is finished.

    Delete this and the review quietly stops showing the fields nobody filled in, which is the
    half of the screen that catches a mistake."""
    lines = review(answered(), an_enrolment(), SECRET, administrators=0, now=INSIDE)
    expected = [
        (step.key, one.field.name) for step in WIZARD if step.stores for one in step.questions
    ]
    assert [(one.step, one.field) for one in lines] == expected
    assert all(one.label_key in MESSAGES for one in lines)


def test_a_secret_answer_reads_as_supplied_and_never_as_itself() -> None:
    """M42.5.10. Showing the first four characters of a key is showing four characters of a
    key, on a screen nobody has authenticated to, so a supplied secret is a state and not a
    masked value.

    Delete this and the review screen can start rendering the provider key, on the one page
    that is reachable without a sign-in."""
    lines = review(answered(hosted=True), an_enrolment(), SECRET, administrators=0, now=INSIDE)
    key_row = next(one for one in lines if one.field == "provider_key")
    assert key_row.state_key == REVIEW_STATES["supplied"]
    assert key_row.shown == ""
    assert all(one.shown != "k" * 40 for one in lines)


def test_a_skipped_screen_and_an_unanswered_field_read_differently() -> None:
    """M42.5.10. A skipped screen is a decision and a blank optional field is an omission, and
    a review that showed them alike would hide which of the two happened.

    Delete this and the review can collapse the two, so a person cannot tell whether they
    decided against the connections screen or never reached it."""
    lines = review(answered(), an_enrolment(), SECRET, administrators=0, now=INSIDE)
    connections = next(one for one in lines if one.field == "connections")
    assert connections.state_key == REVIEW_STATES["skipped"]
    hosted = review(answered(hosted=True), an_enrolment(), SECRET, administrators=0, now=INSIDE)
    provider = next(one for one in hosted if one.field == "connections")
    assert provider.state_key == REVIEW_STATES["skipped"]
    blank = review(
        answer(
            new_draft(),
            StepId.COMPANY,
            {"company_name": "A Company", "web_address": "https://brain.internal"},
            an_enrolment(),
            SECRET,
            administrators=0,
            now=INSIDE,
        )[0],
        an_enrolment(),
        SECRET,
        administrators=0,
        now=INSIDE,
    )
    logo = next(one for one in blank if one.field == "logo_url")
    assert logo.state_key == REVIEW_STATES["not_given"]


def test_a_review_row_carries_an_answer_or_a_state_and_never_both_or_neither() -> None:
    """M42.5.10 and M42.5.13. A row that is both is one a screen renders twice or picks
    between; a row that is neither renders as an empty cell beside a real one and reads as an
    answered blank.

    Delete this and the review screen can show a company literally named "Skipped" as a
    skipped screen, or show nothing at all where an answer should be."""
    with pytest.raises(WizardError, match="both an answer and a state"):
        ReviewLine(
            step=StepId.COMPANY,
            field="company_name",
            label_key="field.company_name.label",
            shown="A Company",
            state_key=REVIEW_STATES["skipped"],
        )
    with pytest.raises(WizardError, match="neither an answer nor a state"):
        ReviewLine(step=StepId.COMPANY, field="company_name", label_key="field.company_name.label")


def test_answering_a_screen_writes_nothing_and_leaves_the_draft_it_was_given() -> None:
    """M42.5.10. Until somebody presses the last button the install is exactly as it was before
    the wizard was opened, and the draft is a value rather than an object with a history.

    Delete this and `answer` can start mutating what it was handed, which makes "what was
    answered" unanswerable after the browser was closed and takes M42.5.12 with it."""
    before = new_draft()
    after, problems = answer(
        before,
        StepId.COMPANY,
        COMPANY_ANSWERS,
        an_enrolment(),
        SECRET,
        administrators=0,
        now=INSIDE,
    )
    assert problems == ()
    assert before.answers == {}
    assert after.values_for(StepId.COMPANY)["company_name"] == "A Company"


def test_a_field_the_screen_never_asked_for_is_not_kept() -> None:
    """M42.5.10 read strictly: everything written is reviewed, so nothing unreviewed is
    written. The draft of this module kept whatever a browser posted, which put unvalidated
    values into a file the review screen does not show.

    Delete this and a form can add fields that reach the install directory without appearing
    on the screen whose job is to show what is about to happen."""
    draft, problems = answer(
        new_draft(),
        StepId.COMPANY,
        {**COMPANY_ANSWERS, "smuggled": "a value nobody reviewed"},
        an_enrolment(),
        SECRET,
        administrators=0,
        now=INSIDE,
    )
    assert problems == ()
    assert "smuggled" not in draft.values_for(StepId.COMPANY)
    assert "smuggled" not in json.dumps(snapshot(draft))


def test_an_install_missing_screens_names_every_one_of_them_and_writes_nothing() -> None:
    """M42.5.10. An install missing two screens has two problems, and fixing one leaves a
    wizard that still refuses, so all of them are named at once.

    Delete this and the final write can report one missing screen at a time, which turns the
    last step of an install into a sequence of refusals."""
    with pytest.raises(WizardError, match="not finished and nothing has been written") as raised:
        apply_install(
            new_draft(),
            an_enrolment(),
            SECRET,
            principal_id=PERSON,
            administrators=0,
            now=INSIDE,
        )
    for name in ("company", "administrator", "staff_source", "model_provider", "connections"):
        assert name in str(raised.value)


def test_a_screen_that_cannot_be_skipped_refuses_a_skip() -> None:
    """M42.5.10. A skip that silently became an empty answer would move the refusal to the
    review screen, where the person can no longer see which screen it was about.

    Delete this and the company screen can be skipped, which produces a draft that refuses at
    the last step for a reason that happened five screens earlier."""
    with pytest.raises(WizardError, match="cannot be skipped"):
        skip(new_draft(), StepId.COMPANY, an_enrolment(), SECRET, administrators=0, now=INSIDE)
    assert step_for(StepId.CONNECTIONS).skippable is True


def test_a_skip_replaces_an_answer_and_an_answer_replaces_a_skip() -> None:
    """M42.5.10. A screen cannot be in two states, and a person who answers the connections
    screen and then goes back and skips it has decided the second thing.

    Delete this and a draft can hold a screen as both answered and skipped, so which one the
    review shows depends on the order the two records are read in."""
    answered_first = answered(skip_connections=False)
    assert "connections" in answered_first.answers
    skipped = skip(
        answered_first, StepId.CONNECTIONS, an_enrolment(), SECRET, administrators=0, now=INSIDE
    )
    assert "connections" not in skipped.answers
    assert "connections" in skipped.skipped
    again, problems = answer(
        skipped,
        StepId.CONNECTIONS,
        {"connections": "xero"},
        an_enrolment(),
        SECRET,
        administrators=0,
        now=INSIDE,
    )
    assert problems == ()
    assert "connections" not in again.skipped


def test_skipping_the_connections_screen_and_answering_it_produce_the_same_install() -> None:
    """The connections screen sets no installation value, which is what makes skipping it free:
    a skipped install and an answered one are the same install, and the console does the
    connecting either way.

    Delete this and the connections screen can quietly acquire a setting, at which point
    skipping it changes the install and the screen stops being optional in fact."""
    assert settings_from(answered()) == settings_from(answered(skip_connections=False))


# ------------------------------------------------------------------ M42.5.11, the closed door
@pytest.mark.parametrize("administrators", [1, 2, 40])
def test_every_entry_point_refuses_once_an_administrator_exists(administrators: int) -> None:
    """M42.5.11 asks for unreachable rather than hidden. A hidden install path is an
    unauthenticated route to the widest role in the system, guarded by a value printed once to
    a terminal that has since been closed.

    Delete this and one entry point can lose its check, which is enough: a browser posting to
    that one reaches the install path on a server that already has an administrator."""
    draft = answered()
    with pytest.raises(WizardClosedError):
        unlock(an_enrolment(), {"setup_code": SECRET}, administrators=administrators, now=INSIDE)
    with pytest.raises(WizardClosedError):
        answer(
            draft,
            StepId.COMPANY,
            COMPANY_ANSWERS,
            an_enrolment(),
            SECRET,
            administrators=administrators,
            now=INSIDE,
        )
    with pytest.raises(WizardClosedError):
        skip(
            draft,
            StepId.CONNECTIONS,
            an_enrolment(),
            SECRET,
            administrators=administrators,
            now=INSIDE,
        )
    with pytest.raises(WizardClosedError):
        review(draft, an_enrolment(), SECRET, administrators=administrators, now=INSIDE)
    with pytest.raises(WizardClosedError):
        apply_install(
            draft,
            an_enrolment(),
            SECRET,
            principal_id=PERSON,
            administrators=administrators,
            now=INSIDE,
        )


def test_a_closed_wizard_is_a_type_a_route_can_refuse_without_reading_any_text() -> None:
    """M42.5.11. Closed and locked are different outcomes and a route does different things
    with them: a closed wizard renders nothing at all, a locked one renders the first screen
    again so somebody who mistyped the code can carry on.

    Delete this and the two collapse into one message, and a route either shows the install
    path to a server that has an administrator or refuses everybody who typed badly."""
    assert issubclass(WizardClosedError, WizardError)
    assert issubclass(WizardLockedError, WizardError)
    assert not issubclass(WizardClosedError, WizardLockedError)
    assert not issubclass(WizardLockedError, WizardClosedError)


def test_nothing_here_takes_a_parameter_that_would_reopen_the_install_path() -> None:
    """M42.5.11. The way this rule dies is one keyword added at three in the morning to get an
    install past a check, and never taken out, so the signatures are read rather than trusted.

    Delete this and `force=True` can be added to `apply_install` and the module still reads as
    though the door is closed."""
    assert reopening_gaps() == ()
    assert set(ENTRY_POINTS) <= set(module_functions())


def test_a_parameter_meaning_do_it_anyway_would_be_reported() -> None:
    """M42.5.11. A check that has never reported anything is a check nobody knows works, and
    this one can only be exercised against a module built to fail.

    Delete this and `REOPENING_NAMES` can be emptied, or the scan narrowed to nothing, and the
    real module keeps passing."""

    def apply_install(
        draft: Draft, enrolment: Enrolment, *, administrators: int, force: bool
    ) -> None:
        return None

    found = reopening_gaps({"apply_install": apply_install}, ("apply_install",))
    assert len(found) == 1
    assert "'force'" in found[0]


def test_an_entry_point_that_cannot_count_administrators_or_does_not_exist_is_reported() -> None:
    """M42.5.11. Two more ways the closed door goes missing: a screen that cannot ask how many
    administrators there are, and a name in `ENTRY_POINTS` that this module does not define,
    which is the state a rename leaves behind and which would silently cover one fewer
    function.

    Delete this and `ENTRY_POINTS` can name a function that no longer exists, so the check
    runs against four entry points and reports nothing about the fifth."""

    def review(draft: Draft, enrolment: Enrolment) -> None:
        return None

    found = reopening_gaps({"review": review}, ("review", "gone"))
    assert len(found) == 2
    assert "number of administrators" in found[0]
    assert "no such name" in found[1]


# ------------------------------------------------------------------ M42.5.12, resuming
def test_a_resumed_install_continues_at_the_screen_it_stopped_on(tmp_path: Path) -> None:
    """M42.5.12 asks that closing the browser halfway continues where it stopped. The draft is
    a file in the install directory rather than a table, because the wizard is reachable while
    the first migration is still running and a resume that needs a schema cannot resume the
    install that failed while building one.

    Delete this and the round trip through the file can lose an answer without anything
    noticing, which sends a person back to a screen they have already filled in."""
    draft = new_draft()
    draft, problems = answer(
        draft,
        StepId.COMPANY,
        COMPANY_ANSWERS,
        an_enrolment(),
        SECRET,
        administrators=0,
        now=INSIDE,
    )
    assert problems == ()
    path = tmp_path / DRAFT_FILE_NAME
    write_draft(path, draft)
    resumed = read_draft(path)
    assert resumed is not None
    assert resumed == draft
    assert next_step(resumed) is StepId.ADMINISTRATOR
    assert next_step(answered()) is StepId.REVIEW


def test_an_install_nobody_has_started_is_told_apart_from_one_with_no_answers(
    tmp_path: Path,
) -> None:
    """M42.5.12. None and an empty draft are the same set of answers and different facts: only
    one of them means somebody has been here, and a caller greeting a returning person needs
    to know which.

    Delete this and `read_draft` can invent an empty draft for an install nobody has opened,
    so a first visit renders as a resume."""
    path = tmp_path / DRAFT_FILE_NAME
    assert read_draft(path) is None
    write_draft(path, new_draft())
    assert read_draft(path) == new_draft()


def test_the_draft_on_disk_never_carries_the_provider_key(tmp_path: Path) -> None:
    """M42.5.12 and M42.5.8. The provider key is a standing credential no engine reissues, and
    a copy left in an install directory outlives the install that made it and appears in no
    inventory. It is dropped rather than masked, because a masked value is still a value in the
    file one substitution away from being the real one.

    Delete this and a resume becomes smoother by keeping the key, which is the change somebody
    makes on purpose and nobody reviews."""
    path = tmp_path / DRAFT_FILE_NAME
    write_draft(path, answered(hosted=True))
    written = path.read_text(encoding="utf-8")
    assert "k" * 40 not in written
    assert "provider_key" not in written
    assert "anthropic" in written
    assert json.loads(written)["answers"]["model_provider"] == {
        "model_profile": "hosted",
        "model_provider": "anthropic",
    }


def test_a_resumed_install_asks_for_the_provider_key_again(tmp_path: Path) -> None:
    """M42.5.12. Dropping the key is only safe if the resume notices, and it notices through
    the model screen's own cross-field rule rather than through a special case: a hosted
    profile with no key is not a finished screen.

    Delete this and a resumed install reaches the review screen with no key at all, and the
    person presses the last button on an install that cannot reach a model."""
    path = tmp_path / DRAFT_FILE_NAME
    write_draft(path, answered(hosted=True))
    resumed = read_draft(path)
    assert resumed is not None
    assert is_answered(step_for(StepId.MODEL_PROVIDER), resumed) is False
    assert next_step(resumed) is StepId.MODEL_PROVIDER


def test_a_draft_that_carries_a_credential_is_refused_rather_than_read() -> None:
    """M42.5.12. `snapshot` drops the secrets, so a document holding one was written by
    something else, and reading it would put the credential back into memory and, on the next
    write, back into the file.

    Delete this and a store that has started keeping keys is accepted silently, which is worse
    than the store being wrong: nothing anywhere reports it."""
    with pytest.raises(WizardError, match="which is a credential"):
        draft_from(
            {
                "version": SNAPSHOT_VERSION,
                "answers": {"model_provider": {"provider_key": "k" * 40}},
                "skipped": [],
            }
        )


def test_a_draft_from_another_release_or_another_shape_is_refused() -> None:
    """M42.5.12. A version rather than a date, so a document written by an older release
    refuses with a sentence about the version rather than being read as though its fields
    meant what they mean today. The shape checks are the same argument for a hand-edited file.

    Delete this and an older draft is read field by field into a `Draft` whose meaning has
    changed, and the install continues from answers that mean something else."""
    with pytest.raises(WizardError, match="version"):
        draft_from({"version": SNAPSHOT_VERSION + 1, "answers": {}, "skipped": []})
    with pytest.raises(WizardError, match="not a mapping"):
        draft_from({"version": SNAPSHOT_VERSION, "answers": ["company"], "skipped": []})
    with pytest.raises(WizardError, match="not a mapping of field to value"):
        draft_from({"version": SNAPSHOT_VERSION, "answers": {"company": "A Company"}})
    with pytest.raises(WizardError, match="not a screen in this wizard"):
        draft_from({"version": SNAPSHOT_VERSION, "answers": {"invoicing": {}}})


def test_a_screen_answered_entirely_in_secrets_survives_as_an_empty_record() -> None:
    """M42.5.12. A screen whose answers were all secret has to come back as an empty mapping
    rather than disappearing, so the resume knows it was visited and reopens it. Disappearing
    would make it an unvisited screen, which is the same place a person lands but with the
    earlier screens' answers still there and no explanation.

    Delete this and `snapshot` can drop the whole screen, and a resume cannot tell a screen
    somebody filled in entirely with a credential from one they never reached."""
    written = snapshot(Draft(answers={"model_provider": {"provider_key": "k" * 40}}))
    assert written["answers"] == {"model_provider": {}}
    assert "k" * 40 not in json.dumps(written)


def test_the_draft_is_created_readable_only_by_its_owner(tmp_path: Path) -> None:
    """M42.5.12. The mode is a ceiling a umask can only take bits from, and the file is removed
    and recreated rather than truncated, because a mode is applied when a file is created and
    not when it is opened: writing into a file somebody had already made world-readable would
    leave it world-readable.

    The mode is asserted as the two permissions the file actually needs rather than as the
    number itself, which a mutation run is what forced: `& 0o077 == 0` is satisfied by 0o700
    as well, so the octal could gain an execute bit nothing needs with the suite green, and
    comparing it against `DRAFT_MODE` moves both sides together.

    Delete this and the draft can be opened in place, so an install directory with a loose
    umask keeps the company's answers world-readable with the code still saying 0600."""
    assert DRAFT_MODE & 0o077 == 0
    assert DRAFT_MODE == stat.S_IRUSR | stat.S_IWUSR
    path = tmp_path / DRAFT_FILE_NAME
    path.write_text("{}", encoding="utf-8", newline="\n")
    if os.name == "posix":
        path.chmod(0o666)
    write_draft(path, answered())
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == DRAFT_MODE
    assert read_draft(path) == answered()


def test_a_draft_written_twice_replaces_the_first_rather_than_joining_it(
    tmp_path: Path,
) -> None:
    """M42.5.12. Every visit writes the whole draft, so a screen whose answer was removed has
    to be gone from the file rather than left behind by a partial write.

    Delete this and an answer a person went back and cleared stays in the install directory
    and comes back on the next resume."""
    path = tmp_path / DRAFT_FILE_NAME
    write_draft(path, answered(skip_connections=False))
    assert "xero" in path.read_text(encoding="utf-8")
    write_draft(path, answered())
    assert "xero" not in path.read_text(encoding="utf-8")


def test_finishing_an_install_removes_the_draft_and_removing_it_twice_is_safe(
    tmp_path: Path,
) -> None:
    """M42.5.12. Discarding is called after the write rather than before, so a failure between
    the two leaves a draft that can be resumed rather than an install with nothing to resume
    from, and a second call has to be harmless or that ordering is unusable.

    Delete this and the draft survives a finished install, which leaves the company's answers
    in a file on a server whose wizard is now unreachable."""
    path = tmp_path / DRAFT_FILE_NAME
    write_draft(path, answered())
    discard_draft(path)
    assert not path.exists()
    discard_draft(path)
    assert read_draft(path) is None


def test_the_draft_on_disk_says_which_release_wrote_it_and_is_not_the_environment_file(
    tmp_path: Path,
) -> None:
    """M42.5.12, and the two constants a test comparing them with themselves would never pin.
    The version is compared with the literal 1 rather than with `SNAPSHOT_VERSION`, because the
    format on disk is a fact about what has shipped: a release that renumbers it silently makes
    every draft written by the previous one unreadable, and the round trip in this file would
    stay green because both ends moved together. The file name is checked against the
    installer's own environment file, which is the one name it must never be: they live in the
    same directory, and a draft written over `.env` destroys the install it is resuming.

    Delete this and the on-disk format can be renumbered with no test noticing, and the draft
    can be pointed at the file holding every credential the installer minted."""
    path = tmp_path / DRAFT_FILE_NAME
    write_draft(path, answered())
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1
    assert DRAFT_FILE_NAME not in {INSTALL_ENV_FILE, f"{INSTALL_ENV_FILE}.example"}
    assert not DRAFT_FILE_NAME.startswith(".")
    with pytest.raises(WizardError, match="version"):
        draft_from({"version": 0, "answers": {}, "skipped": []})


def test_a_draft_cannot_hold_a_screen_as_answered_and_skipped_at_once() -> None:
    """M42.5.12. A screen cannot be in two states, and a document that says it is has been
    edited by hand or written by a release that meant something else by one of the two words.

    Delete this and which state wins depends on which of the two the reader looks at first,
    which is a different install depending on the code path."""
    with pytest.raises(WizardError, match="cannot be in two states"):
        Draft(answers={"connections": {}}, skipped=frozenset({"connections"}))


# ------------------------------------------------------------------ M42.5.13, saying what is wrong
def test_every_message_this_wizard_names_exists_in_every_shipped_language() -> None:
    """M42.5.13 says every step says what is wrong in words the person can act on, and this is
    the screen read by somebody who has never seen the software. A message key with no entry
    renders as nothing, and `brain.locale.text` refuses rather than falling back, so a missing
    key is an exception on the install path.

    Delete this and the first screens of the product can ship naming messages that exist in no
    language, which is exactly the state this module was found in."""
    assert wizard_gaps() == ()
    assert catalogue_gaps() == ()


def test_a_wizard_naming_a_message_nobody_wrote_would_be_reported() -> None:
    """M42.5.13. Five findings, and each has to be exercised against a wizard built to fail: a
    check that can only run against the real thing has no test for the case it exists to find.

    Delete this and `wizard_gaps` can be narrowed to the title check alone and stay green on
    the real wizard, and the next question added with no `too_long` message refuses a paste
    with a traceback."""
    unheaded = Step(key=StepId.COMPANY, title_key="setup.step.nowhere.title")
    assert any("is not in the catalogue" in one for one in wizard_gaps((unheaded,)))

    unlabelled = Step(
        key=StepId.COMPANY,
        title_key="setup.step.company.title",
        questions=(
            Question(
                field=FormField(
                    name="company_name",
                    label_key="field.nowhere.label",
                    errors={"blank": "setup.error.blank", "too_long": "setup.error.too_long"},
                ),
                check=lambda value: "",
            ),
        ),
    )
    assert any("field.nowhere.label" in one for one in wizard_gaps((unlabelled,)))

    speechless = Step(
        key=StepId.COMPANY,
        title_key="setup.step.company.title",
        questions=(Question(field=a_field("company_name", errors={}), check=lambda value: ""),),
    )
    findings = wizard_gaps((speechless,))
    assert any("no error keys" in one for one in findings)
    assert any("required with no blank message" in one for one in findings)
    assert any("no too_long message" in one for one in findings)


def test_a_review_state_with_no_message_would_be_reported() -> None:
    """M42.5.13. The three review states are the only strings on the review screen that are not
    somebody's own words, so an absent one renders as a blank cell beside a real answer, which
    reads as an answered blank rather than as a missing translation.

    The three keys are checked against the catalogue's own words rather than against each
    other, because a map compared with itself is green for every value it could hold: pointing
    "skipped" at the "not given" message would keep every equality in this file true while the
    review screen stopped distinguishing a decision from an omission.

    Delete this and the review states are the one part of that screen nothing checks, on the
    last page before an install is written."""
    assert set(REVIEW_STATES) == {"supplied", "not_given", "skipped"}
    assert len(set(REVIEW_STATES.values())) == 3
    assert all(key in MESSAGES for key in REVIEW_STATES.values())
    assert all(set(MESSAGES[key]) >= {"en", "zh-Hans"} for key in REVIEW_STATES.values())
    assert MESSAGES[REVIEW_STATES["skipped"]]["en"] == "Skipped"
    assert MESSAGES[REVIEW_STATES["not_given"]]["en"] == "Not given"
    assert MESSAGES[REVIEW_STATES["supplied"]]["en"] == "Supplied"
    absent = wizard_gaps((), {"skipped": "setup.review.nowhere"})
    assert len(absent) == 1
    assert "setup.review.nowhere" in absent[0]


def test_an_answer_of_one_space_is_blank_rather_than_a_company_name() -> None:
    """M42.5.13. A company name of one space passes every non-empty test and renders as an
    unnamed install, so the value is stripped before it is judged and again before it is kept.

    Delete this and an install can be created whose name is whitespace, on every screen and in
    every message it sends."""
    assert problems_with(step_for(StepId.COMPANY), {**COMPANY_ANSWERS, "company_name": " "}) == (
        FieldError(field="company_name", key="setup.error.blank"),
    )
    assert problems_with(step_for(StepId.COMPANY), {**COMPANY_ANSWERS, "company_name": ""}) == (
        FieldError(field="company_name", key="setup.error.blank"),
    )
    draft, problems = answer(
        new_draft(),
        StepId.COMPANY,
        {**COMPANY_ANSWERS, "company_name": "  A Company  "},
        an_enrolment(),
        SECRET,
        administrators=0,
        now=INSIDE,
    )
    assert problems == ()
    assert draft.values_for(StepId.COMPANY)["company_name"] == "A Company"


def test_a_pasted_document_is_told_about_its_length_and_not_about_its_shape() -> None:
    """M42.5.13. Length is checked before the field's own rule, so a pasted document earns one
    message about its length rather than a message about its shape, which is the one the
    person can act on.

    Delete this and somebody who pastes a page into the web address field is told it is not an
    absolute URL, which is true and useless."""
    long_answer = "https://brain.internal/" + "a" * MAX_ANSWER_CHARS
    pasted = {**COMPANY_ANSWERS, "web_address": long_answer}
    assert problems_with(step_for(StepId.COMPANY), pasted) == (
        FieldError(field="web_address", key="setup.error.too_long"),
    )
    not_a_url = {**COMPANY_ANSWERS, "web_address": "brain.internal"}
    assert problems_with(step_for(StepId.COMPANY), not_a_url) == (
        FieldError(field="web_address", key="setup.error.not_absolute"),
    )


def test_a_provider_key_may_be_longer_than_an_ordinary_answer() -> None:
    """M42.5.13 and M42.5.8. The ordinary cap exists because an answer becomes a page title or
    a line of an environment file. A provider key becomes neither: it is issued by somebody
    else in a format that is not ours to bound and it goes to the vault.

    Delete this and one cap covers both, which has to be the larger of the two, and a company
    name of a thousand characters reaches a page title."""
    key = "k" * (MAX_ANSWER_CHARS + 100)
    assert (
        problems_with(
            step_for(StepId.MODEL_PROVIDER),
            {"model_profile": "hosted", "model_provider": "anthropic", "provider_key": key},
        )
        == ()
    )
    assert problems_with(
        step_for(StepId.COMPANY), {**COMPANY_ANSWERS, "company_name": "A" * (MAX_ANSWER_CHARS + 1)}
    ) == (FieldError(field="company_name", key="setup.error.too_long"),)


def test_a_screen_with_two_problems_says_both_of_them() -> None:
    """M42.5.13. Fixing one leaves a screen that still refuses, and a person who is told one
    thing at a time reads the wizard as broken rather than as strict.

    Delete this and the per-field rules can start returning at the first failure, which turns
    one screen into three visits."""
    refused = problems_with(
        step_for(StepId.MODEL_PROVIDER), {"model_profile": "hosted", "model_provider": "nobody"}
    )
    assert [one.field for one in refused] == ["model_provider", "provider_key"]
    assert refused[0].key == "setup.error.unknown_choice"
    assert refused[1].key == "setup.error.key_needed"


def test_every_refusal_names_a_field_that_is_on_the_screen_it_came_from() -> None:
    """M42.5.13. An error that arrived without a field is one a screen can only put at the top
    of the page, where a screen reader announces it with nothing saying which input to go back
    to. That is `brain.locale.FieldError`'s whole argument and this is the wizard obeying it.

    Delete this and a cross-field rule can name a field the screen does not have, which puts
    the message nowhere a person can act on."""
    for step in WIZARD:
        names = {one.field.name for one in step.questions}
        for values in ({}, {"model_profile": "hosted"}, {"company_name": " "}):
            for problem in problems_with(step, values):
                assert problem.field in names, (step.key, problem)
                assert problem.key in MESSAGES


def test_a_source_name_that_is_not_shaped_like_one_says_so_in_its_own_words() -> None:
    """M42.5.13. There is no closed list of connectable sources anywhere in this repository, so
    "choose one of the options shown" is the wrong sentence for a screen with no options to
    show, and the connections field carries its own message instead.

    Delete this and the connections screen refuses a typo with a message about a list that does
    not exist."""
    assert problems_with(step_for(StepId.CONNECTIONS), {"connections": "Xero, hubspot"}) == (
        FieldError(field="connections", key="setup.error.not_a_source_name"),
    )
    assert problems_with(step_for(StepId.CONNECTIONS), {"connections": "xero, hubspot"}) == ()
    assert problems_with(step_for(StepId.CONNECTIONS), {}) == ()


def test_a_refusal_this_screen_has_no_words_for_is_raised_rather_than_invented() -> None:
    """M42.5.13. A fallback means the catalogue is never finished and the person who cannot
    read the fallback is the only one who could notice, so a code with no message raises here
    and `wizard_gaps` runs in the suite to keep that unreachable in the shipped wizard.

    Delete this and a validator can return a code nobody wrote a sentence for, and the screen
    shows an empty message beside the field."""
    speechless = Step(
        key=StepId.COMPANY,
        title_key="setup.step.company.title",
        questions=(
            Question(
                field=a_field("company_name", errors={"blank": "setup.error.blank"}),
                check=lambda value: "not_absolute",
            ),
        ),
    )
    with pytest.raises(WizardError, match="has no message for it"):
        problems_with(speechless, {"company_name": "A Company"})


# ------------------------------------------------------------------ the wizard's own shape
def test_a_question_cannot_name_a_setting_nothing_reads() -> None:
    """A wizard that set something nothing reads is refused at import rather than on a client's
    server, because `brain.install.value_of` refuses an undeclared name and the failure would
    be at the moment the install is written.

    Delete this and a typo in a setting name is discovered by the client, after the wizard has
    reported success."""
    with pytest.raises(WizardError, match="not a declared"):
        Question(field=a_field("company_name"), check=lambda value: "", setting="INSTALL_NOWHERE")
    assert all(one.setting in BY_NAME for step in WIZARD for one in step.questions if one.setting)


def test_a_secret_answer_cannot_also_name_a_setting() -> None:
    """A secret with a setting name is a credential on a line of an environment file, which is
    the one place `brain.ops.provider_keys` argues a provider key must not be.

    Delete this and marking an answer secret stops meaning anything: it would be dropped from
    the draft and written into the environment in the same commit."""
    with pytest.raises(WizardError, match="is a secret and also names"):
        Question(
            field=a_field("provider_key"),
            check=lambda value: "",
            secret=True,
            setting="INSTALL_MODEL_PROFILE",
        )


def test_a_question_that_accepts_no_characters_can_never_be_answered() -> None:
    """A per-question cap is a number somebody types, and zero is the value that turns a
    question into one that refuses every answer with a message about length.

    Delete this and a cap of zero ships, and the screen refuses the person who typed the
    correct thing."""
    with pytest.raises(WizardError, match="can never be answered"):
        Question(field=a_field("company_name"), check=lambda value: "", max_chars=0)


def test_a_step_that_could_not_be_headed_counted_or_answered_is_refused() -> None:
    """Three ways a screen is unusable and each is refused where it is built. A screen with no
    title cannot be headed. A repeated question means one answer wins and the other is lost. A
    skippable screen with a required question obeys whichever rule it is asked first.

    Delete this and the wizard can be assembled into a shape whose behaviour depends on which
    of two rules a caller happens to reach."""
    with pytest.raises(WizardError, match="no title key"):
        Step(key=StepId.COMPANY, title_key="   ")
    twice = (
        Question(field=a_field("company_name"), check=lambda value: ""),
        Question(field=a_field("company_name"), check=lambda value: ""),
    )
    with pytest.raises(WizardError, match="with a repeat"):
        Step(key=StepId.COMPANY, title_key="setup.step.company.title", questions=twice)
    with pytest.raises(WizardError, match="skippable and has a required question"):
        Step(
            key=StepId.CONNECTIONS,
            title_key="setup.step.connections.title",
            questions=(Question(field=a_field("connections"), check=lambda value: ""),),
            skippable=True,
        )


def test_a_screen_that_is_not_in_this_wizard_is_refused_rather_than_answered_none() -> None:
    """A caller handed None writes `if step is None: return` and the screen silently stops
    being part of the wizard, which is `brain.deployment.installer.step_named`'s argument for
    refusing the same way. The case it exists for is a member added to `StepId` and not to
    `WIZARD`, which is why the value here is cast rather than being a real member: every real
    member is in the wizard today, and the guard is for the day one is not.

    Delete this and an unknown screen resolves to nothing, and the wizard skips it without
    saying so."""
    with pytest.raises(WizardError, match="is not a step in this wizard"):
        step_for(cast(StepId, "nowhere"))


def test_every_staff_source_the_wizard_offers_is_one_the_adapters_can_read() -> None:
    """The wizard offers four of the six sources `brain.identity.staff_adapters` can parse, and
    a fifth added here that the adapters do not know would be an install that collects a choice
    nothing can act on.

    Delete this and a source name can be misspelled on this screen and the mismatch is
    discovered when the first sync runs on a client's server."""
    assert set(STAFF_SOURCE_BROKERS) <= set(ADAPTER_SOURCES)
    assert len(STAFF_SOURCE_BROKERS) == 4


def test_every_broker_the_wizard_can_choose_is_named_by_the_setting_that_holds_it() -> None:
    """Choosing where the staff list comes from is also choosing what signs people in, so the
    map is checked against `INSTALL_BROKERED_DIRECTORY`'s own declared meaning rather than
    against itself. A constant compared with a constant imported from the same module is a
    comparison that moves when either side does.

    Delete this and the wizard can write a brokered directory Keycloak has never heard of, and
    sign-in fails after the install reported success."""
    meaning = BY_NAME["INSTALL_BROKERED_DIRECTORY"].meaning
    for broker in STAFF_SOURCE_BROKERS.values():
        assert broker in meaning, broker
    assert STAFF_SOURCE_BROKERS["spreadsheet"] == "none"
    assert settings_from(answered())["INSTALL_BROKERED_DIRECTORY"] == "google"


def test_the_screens_that_store_nothing_are_the_ones_a_resume_cannot_land_on() -> None:
    """`stores` is derived from the questions rather than declared, so the setup code screen,
    the review and the finish are outside the resume walk with no special case naming them.

    Delete this and `next_step` can be given a list of screens to skip, which is a second place
    the rule lives and the one that will disagree."""
    stores = {one.key for one in WIZARD if one.stores}
    assert stores == {
        StepId.COMPANY,
        StepId.ADMINISTRATOR,
        StepId.STAFF_SOURCE,
        StepId.MODEL_PROVIDER,
        StepId.CONNECTIONS,
    }
    assert next_step(new_draft()) is StepId.COMPANY


def test_an_optional_screen_nobody_has_visited_is_not_finished() -> None:
    """A screen whose questions are all optional has no problems with no answers at all, so
    asking `problems_with` alone would report it as done before anybody had seen it.

    Delete this and the connections screen is skipped over silently, and the person never gets
    the chance to decide about it."""
    assert is_answered(step_for(StepId.CONNECTIONS), new_draft()) is False
    skipped = skip(
        new_draft(), StepId.CONNECTIONS, an_enrolment(), SECRET, administrators=0, now=INSIDE
    )
    assert is_answered(step_for(StepId.CONNECTIONS), skipped) is True


def test_this_module_reads_its_own_source_and_finds_the_module_it_is_in() -> None:
    """`minting_gaps` and `reopening_gaps` both read this module rather than trusting it, and
    both would report nothing if they were reading the wrong thing. A scan over an empty string
    is a scan that passes.

    Delete this and either check can silently start reading nothing, which is the failure
    `brain.ops.sweeps.sweep_traceability` had for its whole life: green, and checking nothing."""
    source = Path(module_functions()["minting_gaps"].__code__.co_filename).read_text(
        encoding="utf-8"
    )
    assert "def apply_install(" in source
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "unlock"
        for node in ast.walk(ast.parse(source))
    )
    assert set(ENTRY_POINTS) == {"unlock", "answer", "skip", "review", "apply_install"}


def test_nothing_the_wizard_returns_carries_a_value_a_reader_should_not_have() -> None:
    """The review screen and the settings map are the two things a caller renders, and neither
    may carry the setup code or the provider key. Asserted over the whole of both rather than
    field by field, because the way this breaks is a field added later.

    Delete this and a new field on `ReviewLine` or a new derived setting can carry a credential
    onto a page nobody has authenticated to."""
    lines = review(answered(hosted=True), an_enrolment(), SECRET, administrators=0, now=INSIDE)
    rendered = json.dumps([[one.shown, one.state_key, one.label_key] for one in lines])
    assert SECRET not in rendered
    assert "k" * 40 not in rendered
    settings: dict[str, Any] = dict(settings_from(answered(hosted=True)))
    assert SECRET not in json.dumps(settings)
    assert "k" * 40 not in json.dumps(settings)


def test_a_finished_install_is_the_one_act_and_the_enrolment_comes_back_spent() -> None:
    """M42.5.10 and M42.5.6. An enrolment spent and not stored is one that works a second time,
    so the spent value comes back on the result for the caller to keep, rather than being
    marked in place on an object nothing persists.

    Delete this and the caller stores the enrolment it started with, which leaves the install
    path open to a second claim by anybody holding the code."""
    enrolment = an_enrolment()
    finished = apply_install(
        answered(), enrolment, SECRET, principal_id=PERSON, administrators=0, now=INSIDE
    )
    assert enrolment.spent is False
    assert finished.enrolment.spent is True
    assert finished.enrolment.claimed_at == INSIDE
    assert finished.enrolment.digest == enrolment.digest
    assert isinstance(finished, Applied)
