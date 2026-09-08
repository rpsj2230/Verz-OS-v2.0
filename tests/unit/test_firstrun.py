"""First run: one administrator, one chance, and no password anywhere.

**No value in this file is a credential.** Every "secret" here is a visibly inert string
built out of the words "not a secret" and a run of zeroes, long enough to satisfy the length
floor and useless anywhere. A test suite that contained a real token would be a repository
that contained one, which is the thing the module under test exists to prevent.

Task ids: M41.2.4
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain.firstrun import (
    DEFAULT_WINDOW,
    DIGEST,
    MAX_WINDOW,
    MIN_SECRET_CHARS,
    Claim,
    Enrolment,
    FirstRunError,
    Refusal,
    claim,
    credential_default_gaps,
    credential_field_gaps,
    derived_enrolment,
    digest_of,
    first_administrator,
    first_run_gaps,
    is_open,
    open_enrolment,
    sealed_setup_secret,
)
from brain.identity.roles import Role, standing_super_admins
from brain.ops.leases import SEALED_RENDERING, SealedSecret

NOW = datetime(2026, 1, 6, 9, 0, tzinfo=UTC)
NL = "\n"

#: Not a credential and not pretending to be one. It exists to be long enough to pass the
#: length floor so the rules above it can be exercised at all.
INERT = "not-a-secret-" + "0" * MIN_SECRET_CHARS
OTHER = "not-a-secret-either-" + "1" * MIN_SECRET_CHARS


def _enrolment(**over: object) -> Enrolment:
    base: dict[str, object] = {"digest": digest_of(INERT), "issued_at": NOW}
    base.update(over)
    return open_enrolment(**base)  # type: ignore[arg-type]


# ------------------------------------------------------------------ presenting it
def test_the_right_secret_presented_inside_the_window_is_accepted() -> None:
    """The positive half, and it is not decoration. Every other test here is a refusal, and a
    guard tested only by its refusals is satisfied by one that refuses everything, which on an
    install means nobody can ever become the administrator.

    Deleting this leaves the whole module provable by a function that returns a refusal.
    """
    result = claim(_enrolment(), presented=INERT, now=NOW + timedelta(minutes=5))
    assert result.accepted
    assert result.reason is None
    assert result.enrolment.spent


def test_an_enrolment_presented_once_cannot_be_presented_again() -> None:
    """What makes this an enrolment rather than a password. The copy left in a terminal
    history, a chat message or an install ticket has to be worth nothing, and the only way it
    is worth nothing is if presenting it consumes it.

    Deleting this lets the spend be dropped, and what is left is a password with an hour on
    it, which is still a password.
    """
    first = claim(_enrolment(), presented=INERT, now=NOW + timedelta(minutes=1))
    assert first.accepted
    again = claim(first.enrolment, presented=INERT, now=NOW + timedelta(minutes=2))
    assert not again.accepted
    assert again.reason is Refusal.SPENT


def test_an_enrolment_presented_after_its_window_is_refused() -> None:
    """The second bound. Deleting this leaves an unspent enrolment valid forever, which is the
    state an install that nobody finished sits in."""
    late = claim(_enrolment(), presented=INERT, now=NOW + DEFAULT_WINDOW)
    assert not late.accepted
    assert late.reason is Refusal.EXPIRED


def test_a_wrong_guess_does_not_spend_the_enrolment() -> None:
    """A guessing attack must not become a denial of service. If a wrong presentation spent
    the enrolment, anybody who could reach the endpoint could destroy the install's only way
    in, with a guaranteed hit rate and no credential at all.

    Deleting this makes "spend on every attempt" look like a tightening rather than like
    handing every passer-by a one-shot kill switch.
    """
    enrolment = _enrolment()
    wrong = claim(enrolment, presented=OTHER, now=NOW + timedelta(minutes=1))
    assert not wrong.accepted
    assert wrong.reason is Refusal.WRONG
    assert not wrong.enrolment.spent
    right = claim(wrong.enrolment, presented=INERT, now=NOW + timedelta(minutes=2))
    assert right.accepted


@pytest.mark.parametrize(
    ("presented", "at"),
    [
        (OTHER, NOW + timedelta(minutes=1)),
        (INERT, NOW + DEFAULT_WINDOW),
        ("short", NOW + timedelta(minutes=1)),
    ],
)
def test_every_refusal_looks_the_same_to_whoever_presented_it(presented: str, at: datetime) -> None:
    """Expired, wrong and too short are three facts, and telling them apart tells somebody
    whether what they presented was ever right. The reason is on the result for the ledger,
    and the result carries no message and no field a caller could render.

    Deleting this lets a helpful error message in, and a distinguishable refusal is an oracle
    against the widest account in the system.
    """
    refused = claim(_enrolment(), presented=presented, now=at)
    assert refused.accepted is False
    assert not hasattr(refused, "message")
    assert not hasattr(refused, "detail")


def test_a_secret_short_enough_to_be_guessed_inside_its_own_window_is_refused() -> None:
    """The floor is not a password policy. It is the length below which a one-time value can
    be guessed inside the hour it is valid for.

    Deleting this lets an installer mint four characters and call it an enrolment.
    """
    with pytest.raises(FirstRunError, match="guessed inside its own window"):
        digest_of("x" * (MIN_SECRET_CHARS - 1))


def test_a_digest_that_is_not_a_digest_is_refused_when_the_enrolment_is_opened() -> None:
    """A truncated or differently derived value would be stored, compared, and never match,
    which reads as an installer typing the token wrongly rather than as a broken install.

    Deleting this turns a construction error into an enrolment nobody can ever spend.
    """
    with pytest.raises(FirstRunError, match="64 lower-case hex"):
        open_enrolment(digest="abc", issued_at=NOW)


def test_an_enrolment_window_longer_than_the_ceiling_is_refused() -> None:
    """A ceiling an operator can raise is one that gets raised during the install that made
    it inconvenient, which is the argument `brain.identity.roles` makes about break-glass.

    Deleting this lets a window be passed in days, and a credential is what that is.
    """
    with pytest.raises(FirstRunError, match="longer than"):
        open_enrolment(digest=digest_of(INERT), issued_at=NOW, window=MAX_WINDOW * 2)


# ------------------------------------------------------------------ what it buys
def test_a_spent_enrolment_buys_exactly_one_standing_super_admin() -> None:
    """The appointment is standing rather than a deputy one, and the difference is load
    bearing: `brain.identity.roles` keeps a floor of two standing Super Admins and a deputy
    does not count towards it, so a deputy first administrator leaves the install permanently
    below its own floor on the day it is created.

    Deleting this lets the grant become time-boxed, which looks safer and is not.
    """
    accepted = claim(_enrolment(), presented=INERT, now=NOW + timedelta(minutes=1))
    grant = first_administrator(
        accepted, principal_id="u_first", administrators=0, now=NOW + timedelta(minutes=1)
    )
    assert grant.role is Role.SUPER_ADMIN
    assert not grant.is_deputy
    assert standing_super_admins([grant], NOW + timedelta(minutes=2)) == (grant,)


def test_a_refused_claim_appoints_nobody() -> None:
    """A caller that ignored `accepted` and passed the object on must not be able to proceed.
    Deleting this makes the acceptance flag advisory, and an advisory flag on the widest role
    in the system is not a check."""
    refused = claim(_enrolment(), presented=OTHER, now=NOW + timedelta(minutes=1))
    with pytest.raises(FirstRunError, match="appoints nobody"):
        first_administrator(refused, principal_id="u_first", administrators=0, now=NOW)


def test_an_install_that_already_has_an_administrator_is_past_first_run() -> None:
    """First run exists because there is nobody to authorise an appointment. The moment there
    is, every later appointment goes through the review `brain.identity.roles` performs.

    Deleting this leaves a permanent unauthenticated route to Super Admin, guarded by a value
    somebody printed once and probably still has.
    """
    accepted = claim(_enrolment(), presented=INERT, now=NOW + timedelta(minutes=1))
    with pytest.raises(FirstRunError, match="already has an administrator"):
        first_administrator(accepted, principal_id="u_second", administrators=1, now=NOW)


def test_a_hand_built_claim_whose_enrolment_was_never_spent_appoints_nobody() -> None:
    """The replay written by accident: a caller constructs a `Claim` with `accepted=True`
    rather than obtaining one from `claim`, and the enrolment behind it is still unspent.

    Deleting this leaves the single-use property enforced only by the code path callers are
    expected to use, which is the path an incident does not use.
    """
    forged = Claim(accepted=True, enrolment=_enrolment())
    with pytest.raises(FirstRunError, match="not marked spent"):
        first_administrator(forged, principal_id="u_first", administrators=0, now=NOW)


def test_first_run_is_a_question_about_a_count_and_not_a_flag() -> None:
    """`is_open` takes the number of administrators. A boolean is a value somebody sets; a
    count is a fact about the system, and there is no `force` beside it.

    Deleting this lets the signature grow an override, which is the one edit that reopens the
    door permanently.
    """
    assert is_open(administrators=0)
    assert not is_open(administrators=1)
    with pytest.raises(FirstRunError):
        is_open(administrators=-1)


# ------------------------------------------------------------------ nowhere to put a secret
def test_no_model_here_has_a_field_a_secret_could_live_in() -> None:
    """A structure with somewhere to put the secret is a structure that will have it put
    there, by a debug branch or by a serialiser, and from there it reaches a log.

    Deleting this lets a `presented` field be added during an investigation into why a token
    was not matching, which is exactly when it would be.
    """
    assert credential_field_gaps() == ()


def test_a_model_with_somewhere_to_put_the_secret_is_reported() -> None:
    """The check driven rather than described. A scan tested only against models that pass is
    satisfied by a function returning an empty tuple.

    Deleting this leaves the field rule asserted by nothing at all.
    """

    @dataclass(frozen=True)
    class Careless:
        digest: str
        presented: str

    findings = credential_field_gaps((Careless,))
    assert any("presented" in one for one in findings), findings


# ------------------------------------------------------------------ no default anywhere
def _config(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return tmp_path


def test_this_repository_deploys_no_default_credential() -> None:
    """The leaf itself, over the real tree. It was red until 2026-09-07: `.env.example`
    carried `postgresql://brain:change-me@localhost:5432/brain`, and a file people copy is
    exactly where a default password lives.

    Deleting this lets the next one land, and a default credential is invisible in review
    because it is always accompanied by a comment saying to change it.
    """
    assert first_run_gaps() == ()


def test_a_credential_with_a_literal_value_is_reported(tmp_path: Path) -> None:
    """The plain case. Deleting it lets a value be typed straight into a compose file, which
    is how every install ends up sharing one."""
    repo = _config(tmp_path, "docker-compose.yml", "    KEYCLOAK_ADMIN_PASSWORD: letmein" + NL)
    findings = credential_default_gaps(repo)
    assert any("literal value" in one for one in findings), findings


def test_a_credential_with_a_shell_default_is_reported(tmp_path: Path) -> None:
    """`${VAR:-value}` is the version that gets past review, because it looks like
    configuration. It is a default password with a variable in front of it, and on this
    deployment it is worse than a literal: Coolify resolves the fallback when the compose is
    saved, so the default beats what the image sets.

    Deleting this leaves only the literal form caught, and the literal form is the one nobody
    writes.
    """
    repo = _config(
        tmp_path, "docker-compose.yml", "    ADMIN_PASSWORD: ${ADMIN_PASSWORD:-letmein}" + NL
    )
    findings = credential_default_gaps(repo)
    assert any("defaults to" in one for one in findings), findings


def test_a_credential_that_refuses_to_start_without_a_value_passes(tmp_path: Path) -> None:
    """The positive half, and it is the shape `docker-compose.keycloak.yml` already uses.
    A rule that also refused `:?` would refuse the correct answer, and the first thing anybody
    does with a check that fires on the right answer is switch it off.

    Deleting this leaves the rule provable only by its refusals.
    """
    repo = _config(
        tmp_path,
        "docker-compose.yml",
        "    ADMIN_PASSWORD: ${ADMIN_PASSWORD:?set ADMIN_PASSWORD}"
        + NL
        + "    OTHER_SECRET: ${OTHER_SECRET}"
        + NL
        + "    THIRD_TOKEN:"
        + NL,
    )
    assert credential_default_gaps(repo) == ()


def test_a_path_to_a_credential_is_not_a_credential(tmp_path: Path) -> None:
    """`TOKEN_FILE=/root/.coolify-deploy-token` names where a credential lives, which is the
    whole point of keeping one in a file. The first run of this sweep reported it.

    Deleting this lets the carve-out be removed, and the sweep then fires on the pattern it
    exists to encourage.
    """
    repo = _config(tmp_path, "ops/deploy/thing.sh", "TOKEN_FILE=/root/.deploy-token" + NL)
    assert credential_default_gaps(repo) == ()


def test_a_password_hidden_in_a_url_is_reported(tmp_path: Path) -> None:
    """A check that reads variable names alone never sees this one: the name is
    `DATABASE_URL` and the credential is in the middle of the value.

    Deleting this restores the exact finding this sweep was written by: a copied
    `.env.example` connecting with the password nobody changed.
    """
    repo = _config(
        tmp_path, ".env.example", "DATABASE_URL=postgresql://brain:change-me@localhost/brain" + NL
    )
    findings = credential_default_gaps(repo)
    assert any("inside a URL" in one for one in findings), findings


def test_a_url_whose_password_comes_from_a_variable_passes(tmp_path: Path) -> None:
    """Every compose file here writes `postgresql+psycopg://brain:${POSTGRES_PASSWORD}@...`,
    which is the correct form. Reporting it would make this sweep unable to run on the
    repository it is written for.

    Deleting this leaves the URL rule provable only by breaking things, and the shape it must
    not break is the shape thirty lines in this repository already use.
    """
    repo = _config(
        tmp_path,
        "docker-compose.yml",
        "      DATABASE_URL: postgresql+psycopg://brain:${POSTGRES_PASSWORD}@pgbouncer/brain" + NL,
    )
    assert credential_default_gaps(repo) == ()


def test_a_comment_is_not_a_credential(tmp_path: Path) -> None:
    """The compose files argue at length about why their credentials are required rather than
    defaulted, and the argument contains every word this sweep matches on.

    Deleting this makes the sweep fire on the documentation that keeps the rule.
    """
    repo = _config(
        tmp_path, "docker-compose.yml", "    # ADMIN_PASSWORD: letmein would be a default" + NL
    )
    assert credential_default_gaps(repo) == ()


# --- the four the mutation table found missing -------------------------------------------------
#
# Written after the fact. The agent that built this module ran out of session before it reached
# mutation testing, and the table run afterwards had four survivors, every one of them on the
# credential path. Two are the constant-compared-against-itself shape CLAUDE.md records.


def test_a_secret_of_thirty_one_characters_is_refused_and_thirty_two_is_accepted() -> None:
    """**`MIN_SECRET_CHARS` was compared against itself.** `INERT` above is built as
    `"not-a-secret-" + "0" * MIN_SECRET_CHARS` and the refusal test used
    `"x" * (MIN_SECRET_CHARS - 1)`, so cutting the constant from 32 to 4 moved both sides
    together and the whole file stayed green. A four-character one-time secret would have been
    accepted, and it is guessable inside its own window by hand.

    So the boundary is written out as literals. Thirty-one characters is refused and
    thirty-two is accepted, whatever the constant says, which is the only form of this test
    that has an opinion about the number.

    Delete this and the length below which a one-time value can be guessed becomes a figure
    nothing checks."""
    with pytest.raises(FirstRunError, match="can be guessed inside its own window"):
        digest_of("a" * 31)

    assert DIGEST.match(digest_of("a" * 32))


def test_the_enrolment_window_is_never_longer_than_a_break_glass_session() -> None:
    """**`MAX_WINDOW` was also compared against itself**: every test that used it derived its
    dates from it, so 24 hours could become 7 days with nothing failing. A week-long enrolment
    is a password with an end date, which is the thing this module exists not to be.

    Anchored outside itself, to `identity.roles.BREAK_GLASS_MAX`. That is the comparison the
    constant's own docstring already makes in prose, and it is the right one: both are
    time-boxed grants of the highest access in the system to somebody the system cannot yet
    authenticate, and the enrolment is the weaker of the two because nobody has approved it.

    Delete this and the ceiling drifts, and the argument for why it is a ceiling survives only
    as a comment."""
    from brain.identity.roles import BREAK_GLASS_MAX

    assert MAX_WINDOW >= DEFAULT_WINDOW
    assert timedelta(hours=24) >= MAX_WINDOW
    assert BREAK_GLASS_MAX <= MAX_WINDOW, (
        "a break-glass session may now outlast the enrolment ceiling, so the weaker grant is "
        "the longer one"
    )


def test_an_enrolment_that_closes_before_it_opens_cannot_be_created() -> None:
    """A window of zero, or a negative one, produces an enrolment that has already expired at
    the instant it is issued. That is not a safe failure: the installer is handed a value, the
    claim is refused, and nothing anywhere says the window was the problem rather than the
    secret.

    Both shapes, because a check written for zero misses a negative timedelta and the
    subtraction that produces one is the ordinary way this happens.

    Delete this and `open_enrolment(window=timedelta(0))` returns an enrolment nobody can
    ever use."""
    for window in (timedelta(0), timedelta(seconds=-1)):
        with pytest.raises(FirstRunError, match="closes before it opens"):
            open_enrolment(digest=digest_of("a" * 40), issued_at=NOW, window=window)

    assert open_enrolment(digest=digest_of("a" * 40), issued_at=NOW, window=DEFAULT_WINDOW)


def test_a_claim_is_accepted_with_no_reason_or_refused_with_one_and_never_both() -> None:
    """The ledger reads `reason` to record why an enrolment was refused, and an accepted claim
    carrying one would put a refusal in the record of a successful first sign-in. The mirror
    case is worse: a refusal with no reason is one the ledger cannot record at all, so the one
    event anybody would audit leaves no trace.

    Both directions, because the guard is two clauses and a test for either alone is satisfied
    by deleting the other.

    Delete this and the first administrator can be created with the audit trail saying nothing,
    or saying they were refused."""
    enrolment = open_enrolment(digest=digest_of("a" * 40), issued_at=NOW)

    with pytest.raises(FirstRunError, match="one of the two is wrong"):
        Claim(accepted=True, enrolment=enrolment, reason=Refusal.SPENT)

    with pytest.raises(FirstRunError, match="cannot record"):
        Claim(accepted=False, enrolment=enrolment, reason=None)

    assert Claim(accepted=True, enrolment=enrolment).reason is None
    assert Claim(accepted=False, enrolment=enrolment, reason=Refusal.SPENT).reason is Refusal.SPENT


# --- the join with the installer ---------------------------------------------------------------
#
# `open_enrolment` had no caller in `src` until 2026-09-09. The installer wrote
# BRAIN_SETUP_SECRET and the wizard required it, and nothing turned the one into the other, so
# every test above proved a rule that no install could reach.


def test_two_processes_reading_one_environment_file_derive_one_window() -> None:
    """The property the whole design rests on, and the reason the enrolment is derived rather
    than constructed at startup. A fresh enrolment per process is a window that reopens on
    every restart, which makes it a formality: the period it closes is the one in which a
    stranger could claim the system, and a period that reopens never closes.

    Two derivations from the same two values, asserted equal as whole objects rather than by
    their expiries, because a restart that moved the digest or the issue instant would be the
    same defect wearing different clothes.

    Delete this and the expiry becomes whatever the last process to start decided."""
    first = derived_enrolment(SealedSecret(INERT), issued_at=NOW)
    second = derived_enrolment(SealedSecret(INERT), issued_at=NOW)

    assert first == second
    assert first == open_enrolment(digest=digest_of(INERT), issued_at=NOW)
    assert first is not None
    assert first.expires_at == NOW + DEFAULT_WINDOW


def test_a_derived_enrolment_is_the_one_the_installers_own_secret_opens() -> None:
    """The positive half of the join, without which every test here is satisfied by a
    derivation that produces an enrolment nothing can ever present a secret to.

    The wrong secret is the sibling: a derivation that ignored what it was handed and hashed
    something constant would accept everybody, and the equality above would still hold.

    Delete this and the digest can be derived from something other than the installer's
    value with the whole file green."""
    enrolment = derived_enrolment(SealedSecret(INERT), issued_at=NOW)
    assert enrolment is not None

    accepted = claim(enrolment, presented=INERT, now=NOW + timedelta(minutes=5))
    assert accepted.accepted
    assert accepted.enrolment.spent

    refused = claim(enrolment, presented=OTHER, now=NOW + timedelta(minutes=5))
    assert not refused.accepted
    assert refused.reason is Refusal.WRONG


def test_a_derived_enrolment_expires_from_the_mint_and_not_from_the_visit() -> None:
    """What a restart cannot do, observed through `claim` rather than through a field. The
    installer writes the instant it minted the code, so the window has already been running
    while the images pulled and the database came up; a process that started an hour later
    derives an enrolment that is already expired rather than a fresh one.

    Delete this and a derivation could quietly take its issue instant from the clock, which
    would pass the equality test above inside any single process.

    Deliberately not spent. A derived enrolment never is, because nothing stores the spend
    `claim` returns, and the expiry is what closes the window instead. See
    `SPENTNESS_WOULD_ONLY_BIND_AN_INSTALL_THAT_APPOINTED_NOBODY`."""
    enrolment = derived_enrolment(SealedSecret(INERT), issued_at=NOW)
    assert enrolment is not None
    assert not enrolment.spent

    late = claim(enrolment, presented=INERT, now=NOW + DEFAULT_WINDOW)
    assert not late.accepted
    assert late.reason is Refusal.EXPIRED


def test_an_install_that_minted_neither_half_has_no_enrolment_rather_than_an_open_one() -> None:
    """A development machine, and an install from before the installer wrote the instant, have
    no setup code at all. The answer is None, which a route has to read as "there is no wizard
    here", and the alternative shapes are both worse: an exception makes an ordinary
    configuration a crash, and an enrolment built from nothing is a window nobody minted.

    Delete this and the empty case can start raising, which would take the whole application
    down on every machine that never ran the installer."""
    assert derived_enrolment(None, issued_at=None) is None


def test_half_a_setup_pair_refuses_rather_than_deriving_the_missing_half_from_a_clock() -> None:
    """One step of the installer writes both values, into one file, in one redirected group
    under one guard, so a file carrying one of them was edited by hand. Supplying the other
    from the current time would be exactly the restart this design refuses: an hour that
    nobody minted, opened by whoever edited the file.

    Both directions, because a check written for the missing instant leaves the missing secret
    reaching `open_enrolment` with nothing to hash.

    Delete this and an install with a hand-edited environment file gets a fresh window."""
    with pytest.raises(FirstRunError, match="one half of its setup pair"):
        derived_enrolment(SealedSecret(INERT), issued_at=None)

    with pytest.raises(FirstRunError, match="one half of its setup pair"):
        derived_enrolment(None, issued_at=NOW)


def test_a_setup_code_shorter_than_the_installers_is_refused_at_the_derivation() -> None:
    """The length floor reaches the configured value as well as the presented one. A file
    hand-edited to a four-character code would otherwise produce a perfectly valid enrolment
    whose secret can be guessed inside its own window, and nothing would say so.

    Delete this and the floor applies only to what a visitor types."""
    with pytest.raises(FirstRunError, match="can be guessed inside its own window"):
        derived_enrolment(SealedSecret("a" * 31), issued_at=NOW)

    assert derived_enrolment(SealedSecret("a" * 32), issued_at=NOW) is not None


def test_the_setup_code_is_sealed_before_anything_can_render_it() -> None:
    """The code arrives on a settings object that is rendered whole into the startup log line
    and into any traceback that carries it, so the value has to be one with no rendering
    before it is stored anywhere. `brain.ops.leases.SealedSecret` is that value and is reused
    rather than reimplemented; a second sealed type would be a second answer to one question.

    Four cases, and the last two are the ones that decide whether a settings object can be
    constructed at all: `SealedSecret` refuses an empty value, so unset has to become None
    here rather than a sealed blank, and whitespace is unset.

    Delete this and an install with no setup code cannot start, or one with a setup code
    prints it."""
    sealed = sealed_setup_secret(INERT)
    assert sealed is not None
    assert sealed.reveal() == INERT
    assert INERT not in f"{sealed!r} {sealed} {sealed:>40}"
    assert repr(sealed) == SEALED_RENDERING

    already = SealedSecret(INERT)
    assert sealed_setup_secret(already) is already

    assert sealed_setup_secret(None) is None
    assert sealed_setup_secret("") is None
    assert sealed_setup_secret("   ") is None


def test_the_enrolment_window_outlasts_the_installers_own_wait_for_readiness() -> None:
    """**`DEFAULT_WINDOW` had nothing outside itself to compare against.** Every test in this
    file derives its dates from the constant, so an hour could become a minute, or a week,
    with the whole file green. That mattered less while nothing read the value; it matters now
    that the window runs from the mint, because the installer keeps working afterwards.

    The floor is the installer's own readiness loop, read out of its shell rather than
    restated here: a window shorter than the time the install spends waiting for the
    application to answer would expire before the console could be opened, on a code the
    installer had already printed. The ceiling is a literal, because the argument for it is
    that somebody is still standing there, and two hours is generous for that.

    Delete this and the one number in this module that decides how long a stranger has is a
    number nothing has an opinion about."""
    from brain.deployment.installer import step_named

    waiting = step_named("wait for the application to report ready").run
    attempts = re.search(r"seq 1 (\d+)", waiting)
    pause = re.search(r"sleep (\d+)", waiting)
    assert attempts and pause, f"the readiness step no longer waits in a loop: {waiting}"

    budget = timedelta(seconds=int(attempts.group(1)) * int(pause.group(1)))
    assert budget < DEFAULT_WINDOW, (
        "the setup code can expire while the installer is still waiting for the application "
        "to report ready, on a value it has already printed"
    )
    assert timedelta(hours=2) >= DEFAULT_WINDOW


# --- the five guards a mutation audit found nothing watching ------------------------------------
#
# `.scratch/guard_audit.py` mutates every `if` in this module. Five of them could be deleted with
# the file green, and all five are about a time that is not what it claims to be. They are worth
# more now than they were: `Settings.setup_issued_at` is parsed out of an environment file, so a
# naive or backwards instant is a thing an install can actually have rather than a thing a caller
# could write.


def test_a_naive_now_is_refused_rather_than_compared_against_an_aware_expiry() -> None:
    """`claim` takes the instant from its caller, and a caller reading a clock without a zone
    is the ordinary mistake. Comparing naive against aware raises a `TypeError` from deep
    inside a comparison, which reaches a browser as a failure with no explanation on the one
    screen that has no other way in.

    Delete this and the refusal can be removed with nothing failing, because every other test
    in this file passes an aware instant.

    The positive sibling is every accepted claim above."""
    with pytest.raises(FirstRunError, match="naive now"):
        claim(_enrolment(), presented=INERT, now=datetime(2026, 1, 6, 9, 0))


def test_an_enrolment_that_expires_before_it_was_issued_cannot_be_constructed() -> None:
    """`test_an_enrolment_that_closes_before_it_opens_cannot_be_created` proves `open_enrolment`
    refuses a window of zero, and it never reaches this guard: the window check answers first.
    So the same rule stated on the model itself had nothing watching it, and `Enrolment` is a
    public type that `brain.setup_wizard` imports and a caller can build.

    Both shapes, because equal and backwards are different values and a test for one leaves
    the other reachable.

    Delete this and an enrolment can exist that is expired at the instant it is issued, which
    refuses every correct code with `EXPIRED` and says nothing about the window."""
    for expires in (NOW, NOW - timedelta(seconds=1)):
        with pytest.raises(FirstRunError, match="can never be presented"):
            Enrolment(digest=digest_of(INERT), issued_at=NOW, expires_at=expires)

    assert Enrolment(digest=digest_of(INERT), issued_at=NOW, expires_at=NOW + timedelta(seconds=1))


def test_an_enrolment_carrying_a_time_with_no_zone_is_refused_at_construction() -> None:
    """All three times on the model, and this is the guard the environment file walks into.
    `BRAIN_SETUP_ISSUED_AT=2026-01-06T09:00:00` without the `Z` parses to a naive datetime, so
    an install whose instant was typed by hand rather than written by `date -u` reaches here.
    Refusing is right: a naive instant is judged in whatever zone the comparison happens to
    pick, and the window it describes is then hours wide or hours gone.

    `claimed_at` is the third because it is the one a future caller sets, and a spend recorded
    without a zone is a spend that compares wrongly against the next expiry.

    Delete this and a hand-edited instant produces a window judged in the wrong zone, silently
    and only on installs whose server is not in UTC."""
    naive = datetime(2026, 1, 6, 9, 0)

    with pytest.raises(FirstRunError, match="issued_at is naive"):
        open_enrolment(digest=digest_of(INERT), issued_at=naive)

    with pytest.raises(FirstRunError, match="expires_at is naive"):
        Enrolment(digest=digest_of(INERT), issued_at=NOW, expires_at=naive)

    with pytest.raises(FirstRunError, match="claimed_at is naive"):
        Enrolment(
            digest=digest_of(INERT),
            issued_at=NOW,
            expires_at=NOW + DEFAULT_WINDOW,
            claimed_at=naive,
        )

    with pytest.raises(FirstRunError, match="issued_at is naive"):
        derived_enrolment(SealedSecret(INERT), issued_at=naive)


def test_a_directory_matching_a_configuration_pattern_is_not_read_as_a_file(
    tmp_path: Path,
) -> None:
    """`CONFIGURATION` globs `ops/deploy/*` and `ops/vps/*`, and a glob matches directories.
    Reading one raises an operating-system error rather than reporting a finding, which turns
    the sweep that proves this repository ships no default credential into a sweep that
    crashes, and a crashed sweep is read as an infrastructure problem rather than as a result.

    The file beside it is the positive half: skipping directories must not become skipping
    everything, which is the mutation that would otherwise pass this test on its own.

    Delete this and the next directory added under `ops/deploy` stops the credential sweep."""
    repo = _config(tmp_path, "ops/deploy/deploy.sh", "ADMIN_PASSWORD=letmein" + NL)
    (repo / "ops" / "deploy" / "keys").mkdir()

    findings = credential_default_gaps(repo)
    assert len(findings) == 1
    assert "ADMIN_PASSWORD" in findings[0]
