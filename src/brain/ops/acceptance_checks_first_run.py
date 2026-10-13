"""The install acceptance checks for the first-run wizard, through the wizard's own functions.

**Once an administrator exists the wizard cannot be posted to**, so a check on an install that has
been finished cannot walk the screens, and the people who wrote these leaves said so: prove them
through the wizard's own validators, or on a fresh-install walk. These are the first. Each check
makes its own one-time setup code (a value of the run's, held only as the digest an installer would
hand over), opens an enrolment from it, and calls `brain.setup_wizard` as the routes call it. They
therefore prove the install's code behaves, and say nothing about what a real person typed on a real
server, which is why the leaves that rest on them are held in `docs/proof-sweep-holds.json` until
the walk is recorded.

**The closed wizard is the exception, and it is real.** A reserved person is given every grant a
first administrator holds, in the check's rolled-back transaction, so the install's own count of
administrators is one; the appointment route's function is then asked, with a correct code and a
live enrolment, and answers exactly as it does for a visitor with no enrolment at all. A wizard that
answered a closed install differently from an unknown path would tell whoever probes it that this
product is here.

Rejected: posting to the running application. The check runs in the worker, which serves nothing,
and an HTTP client from a worker to its own application is a second thing to be down.

Task ids: M42.5.3, M42.5.4, M42.5.10, M42.5.11, M42.5.13, M42.5.8, M42.6.2, M42.5.12
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1830

A, _B = RESERVED_DEPARTMENTS

#: A key a provider would hand out, made up for the check, to show the review does not print it.
SECRET_ANSWER: Final = "acceptance-key-"  # noqa: S105


def _enrolment(now: datetime) -> tuple[Any, str]:
    """An enrolment opened from a code made for this check, and the code."""
    from brain.firstrun import digest_of, open_enrolment

    code = secrets.token_urlsafe(32)
    return open_enrolment(digest=digest_of(code), issued_at=now), code


@check(
    leaves=("M42.5.3", "M42.5.13"),
    sentence=(
        "The first screen refuses a wrong setup code with the one refusal and admits the right "
        "one without spending it; every other screen refuses a wrong code; and each answer that "
        "cannot be kept is refused beside its own field in a sentence the catalogue holds."
    ),
)
async def the_wizard_wants_the_setup_code_and_says_what_is_wrong_in_words(h: Harness) -> None:
    from brain.locale import MESSAGES
    from brain.setup_wizard import (
        StepId,
        WizardLockedError,
        answer,
        new_draft,
        unlock,
        wizard_gaps,
    )

    enrolment, code = _enrolment(h.now)
    wrong = secrets.token_urlsafe(32)
    refused = unlock(enrolment, {"setup_code": wrong}, administrators=0, now=h.now)
    if [one.key for one in refused] != ["setup.error.refused"]:
        raise CheckFailedError("a wrong setup code was not refused with the one refusal")
    if unlock(enrolment, {"setup_code": code}, administrators=0, now=h.now):
        raise CheckFailedError("the right setup code was refused on the first screen")
    if unlock(enrolment, {"setup_code": code}, administrators=0, now=h.now):
        raise CheckFailedError("asking the first screen spent the setup code")
    if [one.key for one in unlock(enrolment, {"setup_code": ""}, administrators=0, now=h.now)] != [
        "setup.error.blank"
    ]:
        raise CheckFailedError("a blank setup code was not told it was blank")

    try:
        answer(
            new_draft(),
            StepId.COMPANY,
            {"company_name": "A company", "web_address": "https://company.example.invalid"},
            enrolment,
            wrong,
            administrators=0,
            now=h.now,
        )
    except WizardLockedError:
        pass
    else:
        raise CheckFailedError("a screen behind the first accepted a wrong setup code")

    draft, problems = answer(
        new_draft(),
        StepId.COMPANY,
        {"company_name": "  ", "web_address": "not an address"},
        enrolment,
        code,
        administrators=0,
        now=h.now,
    )
    fields = {one.field for one in problems}
    if fields != {"company_name", "web_address"} or draft != new_draft():
        raise CheckFailedError("answers that cannot be kept were not each refused beside a field")
    if any(not MESSAGES.get(one.key, {}).get("en", "").strip() for one in problems):
        raise CheckFailedError("a refusal names a sentence the catalogue does not hold")
    kept, none = answer(
        new_draft(),
        StepId.COMPANY,
        {"company_name": "A company", "web_address": "https://company.example.invalid"},
        enrolment,
        code,
        administrators=0,
        now=h.now,
    )
    if none or kept == new_draft():
        raise CheckFailedError("a screen answered correctly was refused or not kept")
    if wizard_gaps():
        raise CheckFailedError("a screen of the wizard cannot say what is wrong in words")


@check(
    leaves=("M42.5.4", "M42.5.10"),
    sentence=(
        "Every screen of the wizard is counted as step n of the total with a way back except the "
        "first and the last; the review lists every question including the unanswered, shows an "
        "answer in the person's own words and a secret as supplied only; and recording a screen "
        "writes nothing."
    ),
)
async def the_wizard_counts_steps_and_reviews_everything_before_writing(h: Harness) -> None:
    from brain.setup_wizard import (
        WIZARD,
        StepId,
        answer,
        new_draft,
        progress_for,
        review,
    )

    order = [one.key for one in WIZARD]
    for at, key in enumerate(order):
        seen = progress_for(key)
        first, last = at == 0, at == len(order) - 1
        if (seen.number, seen.of) != (at + 1, len(order)):
            raise CheckFailedError("a screen is not counted as its place of the total")
        if (seen.back is None) != (first or last) or (
            not first and not last and seen.back != order[at - 1]
        ):
            raise CheckFailedError("a screen's way back is not the screen before it")

    enrolment, code = _enrolment(h.now)
    draft = new_draft()
    asks = {
        StepId.COMPANY: {
            "company_name": "A company",
            "web_address": "https://company.example.invalid",
        },
        StepId.MODEL_PROVIDER: {
            "model_profile": "hosted",
            "model_provider": "anthropic",
            "provider_key": f"{SECRET_ANSWER}{secrets.token_hex(8)}",
        },
    }
    for key, values in asks.items():
        draft, problems = answer(draft, key, values, enrolment, code, administrators=0, now=h.now)
        if problems:
            raise CheckFailedError("a correct answer to a screen was refused")
    lines = review(draft, enrolment, code, administrators=0, now=h.now)
    stored = [one for step in WIZARD if step.stores for one in step.questions]
    if len(lines) != len(stored):
        raise CheckFailedError("the review does not list every question the wizard asked")
    by_field = {one.field: one for one in lines}
    if by_field["company_name"].shown != "A company":
        raise CheckFailedError("the review does not show an answer in the person's own words")
    if not by_field["full_name"].state_key:
        raise CheckFailedError("the review shows an unanswered question as if it were answered")
    secret = by_field["provider_key"]
    if secret.shown or not secret.state_key:
        raise CheckFailedError(
            "the review shows a secret answer rather than saying it was supplied"
        )
    if any(SECRET_ANSWER in one.shown for one in lines):
        raise CheckFailedError("the review printed a secret")
    if (
        answer(
            draft,
            StepId.COMPANY,
            asks[StepId.COMPANY],
            enrolment,
            code,
            administrators=0,
            now=h.now,
        )[0]
        != draft
    ):
        raise CheckFailedError("recording the same screen twice changed the draft")


class _NobodyYet:
    """An install with no administrator, for the sibling that shows an open wizard answers."""

    async def administrators(self, now: datetime) -> int:
        del now
        return 0

    async def appoint(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("an appointment with no answers must not be written")


@check(
    leaves=("M42.5.11",),
    sentence=(
        "With an administrator on the install, the appointment is refused with a correct code and "
        "a live enrolment exactly as it is for a visitor with no enrolment, and writes nobody; "
        "with none, the same call says what is wrong with its answers instead."
    ),
)
async def a_closed_wizard_answers_as_a_path_that_does_not_exist(h: Harness) -> None:
    from brain.core.errors import Absent, to_public
    from brain.identity.first_administrator import FirstAdministrators
    from brain.ops.acceptance_people_signed_in import administrator, everywhere
    from brain.setup_routes import AppointmentAsked, appoint_first_administrator

    await h.found_departments()
    keeper = h.principal(A, "first")
    await h.person(keeper, department=A, grants=everywhere(*administrator()))
    enrolment, code = _enrolment(h.now)
    asked = AppointmentAsked(setup_code=code)
    store = FirstAdministrators(h.sessions)
    if await store.administrators(h.now) < 1:
        raise CheckFailedError("a person holding the first administrator's grants was not counted")

    async def appointed(held: Any, *, with_enrolment: bool) -> Any:
        return await appoint_first_administrator(
            held,
            asked,
            enrolment=enrolment if with_enrolment else None,
            principal_id=h.principal(A, "appointed"),
            trace_id=h.trace_id,
            now=h.now,
        )

    told: list[str] = []
    for with_enrolment in (True, False):
        try:
            await appointed(store, with_enrolment=with_enrolment)
        except Absent as nothing:
            told.append(to_public(nothing))
        else:
            raise CheckFailedError("a closed wizard answered an appointment")
    if told[0] != told[1]:
        raise CheckFailedError("a closed wizard answered unlike a visitor with no enrolment")
    opened = await appointed(_NobodyYet(), with_enrolment=True)
    if not opened.problems or opened.principal_id:
        raise CheckFailedError("an open wizard did not say what was wrong with an empty answer")


# ------------------------------------------------------ what the wizard left on this install
#: Said when this install holds no value the wizard collects.
NO_WIZARD_VALUES_HERE: Final = (
    "this install holds none of the values the setup wizard collects in its settings, so it was "
    "not set up through the wizard and what the wizard writes cannot be read back"
)

#: Said when no secrets vault is named.
NO_VAULT_NAMED: Final = (
    "this install names no secrets vault address or token, so no provider key can be held in one"
)

#: Said when the vault cannot be read as open.
THE_VAULT_IS_NOT_OPEN_HERE: Final = (
    "the secrets vault is not open to this process, so which provider keys it holds is unknown"
)

#: Said when no provider key is held, which a hosted install cannot answer without.
NO_PROVIDER_KEY_HELD: Final = (
    "no model provider key is held in the vault yet, which the hosted profile needs before it can "
    "answer; enter one in the setup wizard or on the models screen"
)


@check(
    leaves=("M42.6.2",),
    sentence=(
        "Every required value the setup wizard collects is held in this install's own settings "
        "table and not only in its environment, so a first install needs no hand-edited "
        "environment file for what the wizard asks."
    ),
)
async def the_wizard_s_values_are_held_in_the_install_s_settings(h: Harness) -> None:
    from brain.ops.install_settings import load
    from brain.setup_wizard import WIZARD

    asked = {one.setting for step in WIZARD for one in step.questions if one.setting}
    required = {
        one.setting for step in WIZARD for one in step.questions if one.setting and one.required
    }
    async with h.sessions() as session:
        held = {name for name, value in (await load(session)).items() if value and name in asked}
    if not held:
        from brain.ops.acceptance import CheckNotRunError

        raise CheckNotRunError(NO_WIZARD_VALUES_HERE)
    if required - held:
        raise CheckFailedError(
            "a value the setup wizard requires is not held in this install's settings"
        )


@check(
    leaves=("M42.5.8",),
    sentence=(
        "The install's secrets vault is open and holds at least one model provider's key in a "
        "slot of its own, which is where the setup wizard keeps the key it is given and not "
        "somewhere set beside the server first. The key is never read."
    ),
)
async def a_provider_key_the_wizard_was_given_is_held_in_the_vault(h: Harness) -> None:
    import asyncio

    from brain.ops.acceptance import CheckNotRunError
    from brain.ops.openbao import OpenBaoVault
    from brain.ops.vault_status import Seal, SlotState, report

    address, token = h.settings.vault_address, h.settings.vault_token
    if not (address and token):
        raise CheckNotRunError(NO_VAULT_NAMED)
    vault = await asyncio.to_thread(lambda: report(OpenBaoVault(address, token)))
    if vault.seal is not Seal.OPEN:
        raise CheckNotRunError(THE_VAULT_IS_NOT_OPEN_HERE)
    if not any(one.state is SlotState.HELD for one in vault.providers):
        raise CheckNotRunError(NO_PROVIDER_KEY_HELD)


@check(
    leaves=("M42.5.12",),
    sentence=(
        "Behind the setup code, the answers given so far are kept and read back with the next "
        "screen named, a provider key is not in what is kept, and a wrong code is refused as an "
        "install with an administrator is: with the one refusal, and nothing written."
    ),
)
async def a_half_finished_setup_is_kept_behind_the_code_and_read_back(h: Harness) -> None:
    import tempfile
    from pathlib import Path

    from brain.core.errors import Absent, to_public
    from brain.identity.first_administrator import FirstAdministrators
    from brain.ops.acceptance_people_signed_in import administrator, everywhere
    from brain.setup_routes import AppointmentAsked, keep_draft, read_kept_draft
    from brain.setup_wizard import StepId

    enrolment, code = _enrolment(h.now)
    secret = f"{SECRET_ANSWER}{secrets.token_hex(8)}"
    answers = {
        StepId.COMPANY: {
            "company_name": "A company",
            "web_address": "https://company.example.invalid",
        },
        StepId.MODEL_PROVIDER: {
            "model_profile": "hosted",
            "model_provider": "anthropic",
            "provider_key": secret,
        },
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "draft.json"
        open_store = _NobodyYet()
        asked = AppointmentAsked(setup_code=code, answers=answers)
        kept = await keep_draft(open_store, asked, enrolment=enrolment, path=path, now=h.now)
        if set(kept) != {StepId.COMPANY, StepId.MODEL_PROVIDER}:
            raise CheckFailedError("the screens answered so far were not all kept")
        if secret in path.read_text(encoding="utf-8"):
            raise CheckFailedError("a provider key was written into the draft")
        told = await read_kept_draft(open_store, code, enrolment=enrolment, path=path, now=h.now)
        if told.answers.get(StepId.COMPANY, {}).get("company_name") != "A company":
            raise CheckFailedError("what was kept was not read back")
        if "provider_key" in told.answers.get(StepId.MODEL_PROVIDER, {}):
            raise CheckFailedError("a provider key was read back")
        if told.next_step is None:
            raise CheckFailedError("the draft did not say which screen comes next")
        try:
            await read_kept_draft(
                open_store, secrets.token_urlsafe(32), enrolment=enrolment, path=path, now=h.now
            )
        except Absent as refused:
            wrong = to_public(refused)
        else:
            raise CheckFailedError("a wrong setup code was answered with a draft")

        await h.found_departments()
        keeper = h.principal(A, "draftkeeper")
        await h.person(keeper, department=A, grants=everywhere(*administrator()))
        shut = FirstAdministrators(h.sessions)
        later = Path(directory) / "closed.json"
        try:
            await keep_draft(shut, asked, enrolment=enrolment, path=later, now=h.now)
        except Absent as refused:
            closed = to_public(refused)
        else:
            raise CheckFailedError("a draft was kept on an install that has an administrator")
        if later.exists() or closed != wrong:
            raise CheckFailedError("a closed wizard wrote a draft or answered unlike a wrong code")
