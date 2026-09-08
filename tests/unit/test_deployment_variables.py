"""A per-install file carries values, names no product code, and never ships a credential.

The three properties M42.1 rests on, asserted separately because they fail separately: a
repository that has become a fork, a credential that two installs share, and a template that
shipped a value somebody then never changed.

**Every assertion about a refusal also checks what the refusal does not say.** The findings
here are read by whoever runs the check, which on a client's estate is a CI job with a log, so
a test that only proved the check fires would be satisfied by one that fires and quotes the
password.

Task ids: M42.1.1, M42.1.2, M42.3.2, M42.5.2
"""

from __future__ import annotations

import pytest

from brain.deployment.variables import (
    ENV_FILE_SUFFIX,
    PERMITTED_BESIDE,
    VariablesError,
    install_file,
    is_secret_name,
    parse_env,
    shared_secrets,
    template_for,
    unminted_secrets,
    variables_repository_gaps,
)
from brain.firstrun import MIN_SECRET_CHARS
from brain.install import INSTALLATION

# --- what counts as a credential -------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("POSTGRES_PASSWORD", True),
        ("APP_ROLE_PASSWORD", True),
        ("BRAIN_SETUP_SECRET", True),
        ("LANGFUSE_SECRET_KEY", True),
        # A path to a credential is not one: `brain.firstrun.A_PATH_TO_A_CREDENTIAL_IS_NOT_ONE`.
        ("KEYCLOAK_ADMIN_PASSWORD_FILE", False),
        # A public key is half of a pair and is meant to be copied.
        ("LANGFUSE_PUBLIC_KEY", False),
        ("INSTALL_TIME_ZONE", False),
        ("INSTALL_COMPANY_NAME", False),
    ],
)
def test_a_credential_is_recognised_by_shape_and_a_path_to_one_is_not(
    name: str, expected: bool
) -> None:
    """Every rule in this module keys off this answer: what is emitted blank, what is
    compared between installs, what the installer may not print. A name wrongly called a
    credential makes the template unable to describe a working install; a name wrongly called
    ordinary is a password in a file and in a log.

    Delete this and the three refusals below are all satisfied by a function returning False."""
    assert is_secret_name(name) is expected


# --- reading an install's file ---------------------------------------------------------


def test_a_quoted_value_and_a_bare_one_are_the_same_secret() -> None:
    """`shared_secrets` compares values between two installs. If the quotes survived the
    parse, `PASSWORD="abc"` on one install and `PASSWORD=abc` on the other would read as two
    different secrets, so the check would be green on exactly the case it exists for.

    Delete this and the shared-secret check passes for every pair of files written by two
    different people."""
    assert parse_env('A="one"\nB=one\n') == {"A": "one", "B": "one"}
    assert parse_env("C='one'") == {"C": "one"}
    # One quote is not a pair, and stripping it would change the value.
    assert parse_env('D="one') == {"D": '"one'}


def test_comments_blank_lines_and_lines_with_no_assignment_are_not_settings() -> None:
    """These files are edited by hand on a client's server. A comment read as a setting gives
    the audit a value that nothing set, and a stray word failing the parse fails a deploy.

    Delete this and a commented-out password counts as a live one."""
    parsed = parse_env("# POSTGRES_PASSWORD=old\n\nexport A=1\nnot an assignment\nB=2\n")
    assert parsed == {"A": "1", "B": "2"}


# --- the template ----------------------------------------------------------------------


def test_the_template_names_every_declared_setting_with_its_meaning() -> None:
    """Field by field is what M42.1.1 asks for, and the field list is
    `brain.install.INSTALLATION` rather than a copy: a hand-kept list is wrong the first time
    somebody adds a setting and it is wrong by omitting the new one.

    Delete this and a setting added to the declaration never reaches a client's file, so it
    quietly takes its default on their server."""
    rendered = template_for("acme")
    assignments = [
        line.partition("=")[0]
        for line in rendered.splitlines()
        if line and not line.startswith("#")
    ]
    for one in INSTALLATION:
        assert f"{one.name}=" in rendered, f"{one.name} is declared and not in the template"
        assert one.meaning in rendered, f"{one.name} is emitted with no explanation"
        # Once, under its own heading. A template that repeats a setting under every group is
        # a file that asks for the same value five times, where the last answer silently wins.
        assert assignments.count(one.name) == 1, f"{one.name} is emitted more than once"


def test_the_template_emits_no_value_for_a_credential() -> None:
    """M42.5.2 asks that every secret is generated on the client's server, never defaulted and
    never shipped in the template, and a template is exactly where a default password lives:
    the file is copied, the value nobody changed connects, and nothing ever fails.

    Delete this and the first person who gives a credential a default ships it to every
    install that copies the file."""
    rendered = template_for("acme", also={"POSTGRES_PASSWORD": "the database superuser"})

    assert "POSTGRES_PASSWORD=\n" in rendered
    # The line that tells the person filling this in that the blank is deliberate. Without it
    # a blank credential reads as a value somebody forgot, and the next thing that happens is
    # somebody typing one in and copying the file to the next install.
    assert "Minted on this server by the installer" in rendered
    for line in rendered.splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        assert not (is_secret_name(name) and value), f"{line!r} ships a credential"


def test_a_credential_is_blanked_whatever_default_it_is_handed() -> None:
    """The emit rule stated on its own, because through `template_for` it cannot be reached:
    every variable a caller adds arrives with no default, so a credential emitted with its
    default and a credential emitted blank produce the same file today and would stop doing so
    the day somebody declares a credential-shaped setting with a value.

    `_emitted` is reached directly because that is the only way to the branch. The property is
    M42.5.2 exactly: never defaulted, never shipped in the template.

    Delete this and a declared credential ships its default to every install that copies the
    file, which is the failure `.env.example` already records about its own DATABASE_URL."""
    from brain.deployment.variables import _emitted

    lines = _emitted("SMTP_PASSWORD", "hunter2", required=False)

    assert "SMTP_PASSWORD=" in lines
    assert all("hunter2" not in one for one in lines)
    # And the ordinary case still carries its default, or the template describes nothing.
    assert _emitted("INSTALL_TIME_ZONE", "UTC", required=False) == ["INSTALL_TIME_ZONE=UTC"]


def test_the_template_refuses_to_emit_a_value_it_cannot_explain() -> None:
    """M42.3.2. A `Setting` cannot be built without a meaning, so the refusal that matters is
    about what a caller passes: a variable added to a compose file on a Friday and copied into
    the template on the Monday, which somebody then sets on a client's server by guessing.

    Both spellings of nothing, because `""` and `" "` are different values and only one of
    them is caught by a truthiness test.

    Delete this and the template grows variables nobody can explain, which is the state the
    whole declaration exists to prevent."""
    for empty in ("", " "):
        with pytest.raises(VariablesError, match="no meaning"):
            template_for("acme", also={"SMTP_RELAY": empty})


def test_the_template_refuses_a_second_meaning_for_a_declared_setting() -> None:
    """Two meanings for one variable is one meaning nobody read, and the one that reaches the
    person setting it is whichever the generator happened to print last.

    Delete this and `brain.install.INSTALLATION` stops being the single description of what a
    client supplies."""
    with pytest.raises(VariablesError, match="already declared"):
        template_for("acme", also={"INSTALL_TIME_ZONE": "the zone, again"})


def test_the_template_refuses_a_name_nothing_would_read() -> None:
    """A lower-case or hyphenated name is not an environment variable, so it is emitted,
    committed, set on a server and read by nothing.

    Delete this and a typo becomes a setting that silently takes its default for ever."""
    with pytest.raises(VariablesError, match="not an environment variable name"):
        template_for("acme", also={"smtp_relay": "where mail goes"})


def test_a_required_setting_is_emitted_blank_and_says_so() -> None:
    """A required setting with its default filled in could never refuse, and the refusal is
    the whole point: `brain.install` argues that a guessed identity provider is worse than a
    stopped one.

    Delete this and the file a client fills in gives no sign of which values stop the boot."""
    rendered = template_for("acme")
    required = [one for one in INSTALLATION if one.required]
    assert required, "the declaration has no required settings, so this proves nothing"
    for one in required:
        assert f"{one.name}=\n" in rendered
    assert "No default. The system refuses to start without it." in rendered


def test_an_install_name_that_is_not_a_file_name_is_refused() -> None:
    """The name is a file in the variables repository and a directory on a server. Two names
    differing only by case are two files on Linux and one on the machine somebody clones the
    repository to, which is how one client's values overwrite another's.

    Delete this and the repository accepts `Acme.env` and `acme.env` as separate installs."""
    for bad in ("Acme", "acme/two", "", "-acme", "acme_two"):
        with pytest.raises(VariablesError, match="not an install name"):
            template_for(bad)
    assert install_file("acme-two") == f"acme-two{ENV_FILE_SUFFIX}"


# --- the repository the files live in --------------------------------------------------


def test_a_variables_repository_holding_product_code_is_reported_as_a_fork() -> None:
    """This is the leaf's trap. "A repository per client" read quickly is the fork
    `brain.ops.independence.duplication_gaps` refuses, and the difference between the two is
    entirely what is inside: values, or values plus a copy of the product that every fix then
    has to reach twice with nothing reporting when one is missed.

    Delete this and the private repository grows a `docker-compose.yml` somebody edited for
    one client, which is a second product wearing a configuration repository's name."""
    findings = variables_repository_gaps(
        [
            "acme.env",
            "beta.env",
            "README.md",
            "docker-compose.yml",
            "src/brain/app.py",
            # An install file in a directory, which is the case that needs the path rule of
            # its own: it ends in `.env` and its stem is a valid install name, so every other
            # check here passes it, and a repository with a directory layout is a repository
            # that has started holding something other than one file per install.
            "clients/acme/acme.env",
        ]
    )

    assert len(findings) == 3
    assert any("docker-compose.yml" in one and "fork" in one for one in findings)
    assert any("src/brain/app.py" in one and "flat" in one for one in findings)
    assert any("clients/acme/acme.env" in one and "flat" in one for one in findings)


def test_a_repository_of_install_files_alone_is_reported_as_clean() -> None:
    """The positive case. A refusal tested only by what it refuses is satisfied by a check
    that refuses everything, and a check that refuses a correct variables repository is one
    nobody runs a second time.

    Delete this and the allowlist can be emptied without a test noticing."""
    assert variables_repository_gaps(["acme.env", "beta-corp.env", *sorted(PERMITTED_BESIDE)]) == ()


def test_a_file_whose_name_is_not_an_install_name_is_reported() -> None:
    """`Acme.env` and `acme.env` are one file on some machines, so a repository holding both
    has one client's values overwriting another's on the next clone.

    Delete this and nothing can say which installation a file belongs to."""
    findings = variables_repository_gaps(["Acme.env"])
    assert len(findings) == 1
    assert "not an install name" in findings[0]


# --- secrets between installs ----------------------------------------------------------


def test_one_value_used_on_two_installs_is_reported_without_being_printed() -> None:
    """M42.1.2, and the second half of the assertion is the one that matters. A finding that
    quotes the shared password has moved it out of two private repositories and into whatever
    read the report, which is the leak the check was written to find. The reader loses
    nothing: the action either way is to mint a new one.

    Delete this and the check that enforces "never copied between clients" becomes the widest
    copy of them all."""
    shared = "e" * MIN_SECRET_CHARS
    findings = shared_secrets(
        {
            "acme": {"POSTGRES_PASSWORD": shared, "INSTALL_TIME_ZONE": "UTC"},
            "beta": {"APP_ROLE_PASSWORD": shared},
        }
    )

    assert len(findings) == 1
    assert "POSTGRES_PASSWORD on acme" in findings[0]
    assert "APP_ROLE_PASSWORD on beta" in findings[0]
    assert shared not in findings[0], "the finding printed the value it was reporting"


def test_two_installs_sharing_an_ordinary_setting_are_not_reported() -> None:
    """Every install sets `INSTALL_TIME_ZONE=UTC` and most set the same model endpoint. A
    check that reported those would be a check reporting the correct configuration, which is
    the fastest way to have it switched off.

    Delete this and the shared-secret report is mostly noise and gets ignored, including the
    line that matters."""
    assert (
        shared_secrets(
            {
                "acme": {"INSTALL_TIME_ZONE": "UTC", "INSTALL_VECTOR_STORE": "postgres"},
                "beta": {"INSTALL_TIME_ZONE": "UTC", "INSTALL_VECTOR_STORE": "postgres"},
            }
        )
        == ()
    )


def test_one_install_reusing_a_value_twice_is_not_reported_as_sharing_it_with_anybody() -> None:
    """`shared_secrets` answers "never copied between clients", and one install holding one
    value under two names is a different fault with a different fix, reported by
    `unminted_secrets`. A finding that said this credential is shared between installs would
    send somebody looking for the other install.

    Delete this and the check reports a single install as sharing a secret with itself, which
    is the shape of finding that gets the whole report dismissed."""
    reused = "g" * MIN_SECRET_CHARS
    assert (
        shared_secrets({"acme": {"POSTGRES_PASSWORD": reused, "APP_ROLE_PASSWORD": reused}}) == ()
    )


def test_a_blank_credential_is_not_counted_as_shared_between_installs() -> None:
    """Two installs that have not minted anything yet both hold the empty string, and
    reporting that as a shared secret would put a finding in front of somebody on the one day
    it is certainly wrong: before either install has run.

    Delete this and every pair of fresh installs reports a shared credential."""
    fresh = {
        "acme": {"POSTGRES_PASSWORD": ""},
        "beta": {"POSTGRES_PASSWORD": ""},
    }
    assert shared_secrets(fresh) == ()


# --- secrets on one install ------------------------------------------------------------


def test_a_credential_that_is_blank_or_short_or_reused_is_reported_as_unminted() -> None:
    """M42.5.2 asks that these are generated on the client's server. All three shapes here are
    a credential the installer did not generate, and the third is the one this repository
    already asks for in words: `.env.example` says `APP_ROLE_PASSWORD` is "never the same as
    the postgres superuser" and nothing anywhere checked it.

    Delete this and an install runs with the application role holding the superuser's
    password, so the pooler's ceiling and the connections it reserves are one value away from
    being nobody's ceiling at all."""
    reused = "f" * MIN_SECRET_CHARS
    findings = unminted_secrets(
        {
            "POSTGRES_PASSWORD": reused,
            "APP_ROLE_PASSWORD": reused,
            "LANGFUSE_SECRET_KEY": "short",
            "BRAIN_SETUP_SECRET": "",
            "INSTALL_TIME_ZONE": "UTC",
        }
    )

    assert len(findings) == 3
    assert any("BRAIN_SETUP_SECRET is empty" in one for one in findings)
    assert any("LANGFUSE_SECRET_KEY is shorter" in one for one in findings)
    assert any("APP_ROLE_PASSWORD and POSTGRES_PASSWORD hold one value" in one for one in findings)
    assert all(reused not in one for one in findings)


def test_a_properly_minted_set_of_credentials_is_reported_as_clean() -> None:
    """The positive case, and the one that decides whether the check is usable: a report that
    fires on a correct install is a report nobody reads on an incorrect one.

    Delete this and `unminted_secrets` can be made to refuse everything without failing."""
    assert (
        unminted_secrets(
            {
                "POSTGRES_PASSWORD": "a" * MIN_SECRET_CHARS,
                "APP_ROLE_PASSWORD": "b" * MIN_SECRET_CHARS,
                "INSTALL_COMPANY_NAME": "Acme",
            }
        )
        == ()
    )


def test_the_minimum_length_is_the_one_first_run_already_decided() -> None:
    """A second opinion about how long a generated secret has to be is a second opinion that
    is lower on the day somebody is in a hurry. `brain.firstrun` sets the length below which a
    one-time value can be guessed inside its own window, and this has to be that number rather
    than one chosen here.

    Delete this and the two can drift, with the looser one deciding on a client's server."""
    just_short = "a" * (MIN_SECRET_CHARS - 1)
    assert unminted_secrets({"POSTGRES_PASSWORD": just_short})
    assert unminted_secrets({"POSTGRES_PASSWORD": "a" * MIN_SECRET_CHARS}) == ()
