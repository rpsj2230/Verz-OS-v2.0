"""A credential appears at the tool-execution boundary, on its own origin, and nowhere else.

The structural half, that no type outside the credentials module has a field a value could
sit in, is in `test_browsing_shape.py`. This is the behavioural half.

Task ids: M19.4.1, M19.4.2, M19.4.3, M19.4.4
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import pytest

from brain.browsing.credentials import (
    MIN_SCRUBBABLE,
    SCRUBBED,
    TOTP_DIGITS,
    TOTP_STEP,
    Binding,
    Bindings,
    CredentialError,
    SecretKind,
    binding_gaps,
    placeholder_name,
    resolve,
    scrub_history,
    scrub_outbound,
    totp,
    unresolvable,
)
from brain.ops.secrets import Lease, SecretRef, SecretsUnavailableError, VaultRole

ORIGIN = "https://books.example"
OTHER = "https://books.example.evil.test"
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)

#: The seed from RFC 6238 appendix B, base32 encoded. Twenty ASCII bytes, "12345678901234567890".
RFC_SEED = base64.b32encode(b"12345678901234567890").decode("ascii")


class StubVault:
    """A vault that issues one known value and records every revocation.

    Written here rather than reused from the connector tests because what is being checked is
    this package's use of `borrow`, and a shared fake would make a change in either place
    look like a failure in the other.
    """

    def __init__(self, value: str, *, already_expired: bool = False) -> None:
        self.value = value
        self.already_expired = already_expired
        self.issued: list[str] = []
        self.revoked: list[str] = []

    def issue(self, ref: SecretRef, ttl: timedelta) -> Lease:
        """Hand back a lease. `already_expired` models the case that matters.

        A vault can return a lease whose window has passed: a clock differing between the
        vault and this process, or a lease read back from a cache. The point of `reveal`
        checking the clock is that the source might accept such a credential anyway.
        """
        self.issued.append(ref.path)
        start = NOW - ttl - timedelta(minutes=1) if self.already_expired else NOW
        return Lease(
            lease_id=f"lease-{len(self.issued)}",
            ref=ref,
            secret=self.value,
            issued_at=start,
            expires_at=start + ttl,
        )

    def revoke(self, lease_id: str) -> None:
        self.revoked.append(lease_id)


def ref(path: str = "browser/books/password") -> SecretRef:
    return SecretRef(path=path, role=VaultRole.BROWSER_RUNNER)


def bindings(**changes: object) -> Bindings:
    fields: dict[str, object] = {
        "placeholder": "{{secret:books_password}}",
        "ref": ref(),
        "origin": ORIGIN,
        "kind": SecretKind.PASSWORD,
    }
    fields.update(changes)
    return Bindings(bindings=(Binding(**fields),))  # type: ignore[arg-type]


# --------------------------------------------------------------------- the placeholder


def test_a_placeholder_is_recognised_and_anything_else_is_not() -> None:
    """The grammar, in both directions. A binding on a string that is not a placeholder would
    substitute nowhere and look like a vault problem.

    Delete this and the pattern can be loosened to match any `{{...}}`, which turns every
    templated value in a plan into a credential lookup.
    """
    assert placeholder_name("{{secret:books_password}}") == "books_password"
    assert placeholder_name("{{secret:Books}}") == ""
    assert placeholder_name("books_password") == ""
    assert placeholder_name("{{books_password}}") == ""


def test_a_binding_on_something_that_is_not_a_placeholder_is_refused() -> None:
    """Delete this and a typo in a binding row produces a credential that resolves for
    nothing, discovered halfway through a run that has already logged in."""
    with pytest.raises(CredentialError, match="not a placeholder"):
        Binding(placeholder="books_password", ref=ref(), origin=ORIGIN)


def test_a_binding_on_an_origin_that_is_not_normalised_is_refused() -> None:
    """Comparing a normalised action origin against a raw declaration refuses every
    substitution, and the failure presents as the vault being wrong.

    Delete this and a trailing slash in a binding row makes a login impossible with nothing
    saying why.
    """
    with pytest.raises(CredentialError, match="normalised"):
        Binding(placeholder="{{secret:books_password}}", ref=ref(), origin=f"{ORIGIN}/")


def test_two_bindings_sharing_a_placeholder_are_refused() -> None:
    """Which credential is substituted would otherwise be decided by list order.

    Delete this and a duplicated row silently repoints a placeholder at another system's
    password, which is then typed into this system's form.
    """
    with pytest.raises(CredentialError, match="share a placeholder"):
        Bindings(
            bindings=(
                Binding(placeholder="{{secret:one}}", ref=ref(), origin=ORIGIN),
                Binding(placeholder="{{secret:one}}", ref=ref("other"), origin=ORIGIN),
            )
        )


# --------------------------------------------------------------------- resolution


def test_a_credential_is_produced_at_the_boundary_and_the_lease_is_given_back() -> None:
    """M19.4.1, the positive case. `resolve` is the only thing in the package that produces a
    value, and it does so inside `borrow`, so the lease is revoked on the way out.

    Delete this and `resolve` can stop using the context manager, which leaks a live lease per
    action and is invisible until somebody counts them.
    """
    vault = StubVault("correct-horse-battery")

    value = resolve("{{secret:books_password}}", bindings(), vault=vault, origin=ORIGIN, now=NOW)

    assert value == "correct-horse-battery"
    assert vault.revoked == ["lease-1"]


def test_a_credential_does_not_substitute_on_a_look_alike_origin() -> None:
    """M19.4.2. An exact comparison, never a suffix.

    `books.example.evil.test` ends with nothing that should match, and a registrable-domain
    comparison would admit it. This is the last check before a value is typed into a form.

    Delete this and the origin test can be loosened to something that reads as more
    forgiving, and it forgives the one host it must not.
    """
    vault = StubVault("correct-horse-battery")

    with pytest.raises(CredentialError, match="bound to one origin"):
        resolve("{{secret:books_password}}", bindings(), vault=vault, origin=OTHER, now=NOW)

    assert vault.issued == []


def test_the_vault_is_not_asked_for_a_placeholder_nothing_binds() -> None:
    """Fetching first would tell the vault which credentials a run guessed at.

    Delete this and an unbound placeholder becomes a probe against the vault, and the refusal
    arrives after a lease has been issued for something.
    """
    vault = StubVault("correct-horse-battery")

    with pytest.raises(CredentialError, match="nothing binds"):
        resolve("{{secret:missing}}", bindings(), vault=vault, origin=ORIGIN, now=NOW)

    assert vault.issued == []


def test_an_expired_lease_refuses_to_be_read() -> None:
    """`brain.ops.secrets` makes this refusal and this is the test that this package inherits
    it rather than working around it.

    Delete this and a `reveal` that ignored the clock would be invisible from here, and a
    credential working after we believed it withdrawn is what that module exists to prevent.
    """
    vault = StubVault("correct-horse-battery", already_expired=True)

    with pytest.raises(SecretsUnavailableError, match="expired"):
        resolve("{{secret:books_password}}", bindings(), vault=vault, origin=ORIGIN, now=NOW)

    assert vault.revoked == ["lease-1"]


def test_placeholders_a_plan_uses_that_nothing_binds_are_found_before_the_run() -> None:
    """A run that discovers this halfway through has already taken a browser slot and possibly
    logged in.

    Delete this and the check moves to the moment the credential is needed, which is the least
    recoverable point in a run.
    """
    assert unresolvable(["{{secret:books_password}}", "{{secret:missing}}"], bindings()) == (
        "{{secret:missing}}",
    )
    assert unresolvable(["{{secret:books_password}}"], bindings()) == ()


# --------------------------------------------------------------------- one-time codes


def test_the_code_matches_the_published_vectors() -> None:
    """M19.4.3, asserted against RFC 6238 appendix B rather than against itself.

    A test comparing `totp(...)` with a constant this module also defines is green for every
    value the implementation could produce, which is the trap CLAUDE.md records from
    `throttle.RETRY_AFTER_WHEN_UNSTATED`. The published vectors are the one assertion about
    this function that lives outside it.

    Delete this and the arithmetic can drift, and every code we generate is wrong in a way no
    test in this repository could see.
    """
    vectors = {
        59: "94287082",
        1111111109: "07081804",
        1111111111: "14050471",
        1234567890: "89005924",
        2000000000: "69279037",
        20000000000: "65353130",
    }

    for seconds, expected in vectors.items():
        at = datetime.fromtimestamp(seconds, tz=UTC)
        assert totp(RFC_SEED, at, digits=8) == expected


def test_the_default_shape_is_the_one_every_authenticator_uses() -> None:
    """Six digits and a thirty-second step, pinned against the vectors rather than restated.

    The last six digits of the eight-digit vector are what a six-digit authenticator shows, so
    this asserts the default against the same external source as the test above.

    Delete this and the defaults can be changed to something that is correct arithmetic and
    wrong everywhere a person has already enrolled.
    """
    at = datetime.fromtimestamp(59, tz=UTC)

    assert totp(RFC_SEED, at) == "287082"
    assert len(totp(RFC_SEED, at)) == 6
    assert TOTP_DIGITS == 6
    assert TOTP_STEP == 30
    assert totp(RFC_SEED, at) == totp(
        RFC_SEED, datetime.fromtimestamp(89, tz=UTC) - timedelta(seconds=31)
    )


def test_a_seed_that_is_not_base32_is_refused() -> None:
    """A seed nobody can decode produces no code, and the honest failure is at the binding.

    Delete this and a malformed seed becomes an exception from inside `base64` at the moment a
    login is being attempted, carrying the seed in its message.
    """
    with pytest.raises(CredentialError, match="must be base32"):
        totp("not base32 at all!!", NOW)


def test_a_totp_binding_returns_a_code_and_never_the_seed() -> None:
    """The seed is a permanent credential and the code is worth thirty seconds.

    Delete this and `resolve` can return whatever the vault held for a TOTP binding, which
    hands the container the seed and every future code with it.
    """
    vault = StubVault(RFC_SEED)

    value = resolve(
        "{{secret:books_totp}}",
        bindings(placeholder="{{secret:books_totp}}", kind=SecretKind.TOTP_SEED),
        vault=vault,
        origin=ORIGIN,
        now=datetime.fromtimestamp(59, tz=UTC),
    )

    assert value == "287082"
    assert value != RFC_SEED


# --------------------------------------------------------------------- scrubbing


def test_a_credential_value_is_removed_from_text_and_the_removal_is_reported() -> None:
    """M19.4.4. A non-empty finding means something upstream already failed.

    Delete this and the scrubber can report success while removing nothing, which is the worst
    possible state for a last line.
    """
    text, found = scrub_outbound(
        "I typed correct-horse-battery into the form", ["correct-horse-battery"]
    )

    assert SCRUBBED in text
    assert "correct-horse-battery" not in text
    assert found == (SCRUBBED,)


def test_what_was_removed_is_reported_without_reporting_the_value() -> None:
    """A scrubber that says what it caught has written the credential into the log line that
    was supposed to record the scrub.

    Delete this and the obvious change, returning the secrets that were found, puts the value
    in exactly the place somebody looks after an incident.
    """
    _, found = scrub_outbound("password correct-horse-battery", ["correct-horse-battery"])

    assert found == (SCRUBBED,)
    assert all("correct-horse-battery" not in one for one in found)


def test_text_with_no_credential_in_it_is_returned_unchanged() -> None:
    """The positive sibling. A scrubber that mangled every message would be switched off.

    Delete this and the replacement can be made unconditional, which destroys the history it
    was meant to clean.
    """
    text, found = scrub_outbound("nothing sensitive here", ["correct-horse-battery"])

    assert text == "nothing sensitive here"
    assert found == ()


def test_a_credential_too_short_to_remove_safely_is_not_searched_for() -> None:
    """Replacing every occurrence of a four-character string produces a history that reads as
    though it had been redacted at random.

    Delete this and a short secret turns ordinary prose into holes, and the reader cannot tell
    a redaction from a coincidence.
    """
    text, found = scrub_outbound("the total was 1234 and the code was 1234", ["1234"])

    assert text == "the total was 1234 and the code was 1234"
    assert found == ()
    assert len("1234") < MIN_SCRUBBABLE


def test_the_history_reports_which_messages_carried_a_credential() -> None:
    """The indices are the finding: a credential in the history was substituted somewhere it
    should not have been.

    Delete this and a caller has to diff two lists to notice an incident, which is a thing
    nobody does.
    """
    cleaned, leaked = scrub_history(
        ["hello", "I typed correct-horse-battery", "goodbye"],
        ["correct-horse-battery"],
    )

    assert leaked == (1,)
    assert cleaned[1] == f"I typed {SCRUBBED}"
    assert cleaned[0] == "hello"


def test_a_clean_history_reports_nothing() -> None:
    """The positive sibling for the same reason: an incident signal that always fires is not
    one.

    Delete this and `scrub_history` can report every message as leaked and every refusal test
    above still passes.
    """
    cleaned, leaked = scrub_history(["hello", "goodbye"], ["correct-horse-battery"])

    assert leaked == ()
    assert cleaned == ("hello", "goodbye")


def test_a_credential_too_short_to_scrub_is_reported_when_the_bindings_are_reviewed() -> None:
    """The check that catches it while somebody can still change it.

    Delete this and a four-character credential is accepted at setup and silently skipped by
    the scrubber, which reports success on a message that still contains it.
    """
    gaps = binding_gaps(bindings(), values=["1234"])

    assert any("below the" in one for one in gaps)
    assert binding_gaps(bindings(), values=["correct-horse-battery"]) == ()


def test_a_binding_with_no_origin_is_refused() -> None:
    """Found by mutation, and it was a hole rather than a missing test.

    `normalise_origin` returns the empty string for everything it cannot parse, so an empty
    declared origin satisfied "is this normalised" by comparing "" with "", and
    `substitutes_on` then returned True for `null`, for `not-a-url` and for every other
    unparseable origin an action could name. A binding with no origin handed the credential to
    whichever page asked first.

    Delete this and the whitespace-and-empty case comes back, which is the case CLAUDE.md
    records as the survivor a dataclass validator almost always has.
    """
    with pytest.raises(CredentialError, match="names no origin"):
        Binding(placeholder="{{secret:books_password}}", ref=ref(), origin="")


def test_a_credential_never_substitutes_on_an_origin_that_did_not_parse() -> None:
    """The second half of the same hole, stated on the method rather than the constructor.

    `null` is what a sandboxed iframe and a `file://` document send, and it is the absence of
    an origin rather than a value for one.

    Delete this and `substitutes_on` can go back to a bare equality, which is correct for every
    origin that parses and wrong for every one that does not.
    """
    one = bindings().bindings[0]

    assert one.substitutes_on(ORIGIN)
    assert not one.substitutes_on("null")
    assert not one.substitutes_on("not-a-url")
    assert not one.substitutes_on("")
    # The suffix attack that a lenient comparison actually admits. `books.example.evil.test`
    # is the obvious try and `endswith` refuses it; `evilbooks.example` is the one that gets
    # through, and a mutation replacing the equality with a suffix test passed until this line.
    assert not one.substitutes_on("https://evilbooks.example")


def test_a_seed_that_decodes_to_no_bytes_is_refused() -> None:
    """An empty base32 string decodes cleanly to zero bytes, so it reaches the HMAC.

    Every account with an empty seed would then produce the same code as every other, which is
    a working login flow that authenticates nobody in particular.

    Delete this and the guard is unreachable by any test, which is exactly how it was found:
    mutating it to `if False:` changed nothing anybody was watching.
    """
    with pytest.raises(CredentialError, match="no bytes"):
        totp("", NOW)

    with pytest.raises(CredentialError, match="no bytes"):
        totp("   ", NOW)


def test_a_scrubbed_value_leaves_a_mark_rather_than_a_hole() -> None:
    """Replaced, never removed, which is the argument `brain.ops.pii.scrub` makes for itself.

    A removed span joins two sentences into one that says something neither of them said, and
    nothing downstream can tell that anything was there. Asserted against the shape of the
    result rather than against `SCRUBBED` itself, because comparing the marker with the marker
    is green for every value it could hold, the empty string included.

    Delete this and the marker can be emptied, and every scrub silently becomes a deletion
    that reads as text nobody redacted.
    """
    text, found = scrub_outbound("before COMPLICATEDVALUE after", ["COMPLICATEDVALUE"])

    assert "COMPLICATEDVALUE" not in text
    assert text != "before  after"
    assert len(text) > len("before  after")
    assert found
