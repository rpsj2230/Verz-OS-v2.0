"""The per-install environment file, and why the repository holding it is not a fork.

M42.1.1 asks for per-client variables in a separate private repository, one file per install,
documented field by field. Read quickly that says "a repository per client", which is the
exact thing `brain.ops.independence.duplication_gaps` refuses and would be right to.

**The difference is what is inside, and it is the whole of M41 restated from the other side.**
A repository holding one environment file per install is configuration under version control:
there is still one copy of the product, every fix reaches every client through the same image,
and what differs between two installs is a list of values with no code in it. A repository
holding a copy of the product beside those values is a second product, and the failure is the
silent one: both copies pass their own tests, both deploy, and the client on the older one
meets the defect that was fixed elsewhere a month ago. So the rule here is an allowlist rather
than a blocklist, which is the one direction that survives a file nobody has thought of yet:
an install file, a readme and an ignore list, and anything else is refused by name.

**Every refusal in this module reports a setting and never a value.** A check that prints the
shared password into a build log has moved that password from a private repository into a log
that is not private, which is the leak it was written to find. `shared_secrets` names the two
installs and the two settings and stops there, and that costs a reader nothing: the action is
the same either way, which is to mint a new one.

**A secret is emitted blank whatever the declaration says.** M42.5.2 asks that every password
and key is generated on the client's server, never defaulted and never shipped in the
template, and a template is exactly where a default password survives: the file is copied, the
value nobody changed connects, nothing fails, and the install runs on the value that came with
it. `.env.example` records the same lesson about its own `DATABASE_URL`. So the emit rule is
positional rather than a judgement per setting: a credential-shaped name gets an empty value
and a line saying where the real one comes from.

**The credential-shaped test is imported, not written again.** `brain.firstrun` already owns
what a credential name looks like and, more usefully, the distinction that a name ending in
`_URL` or `_PATH` says *where* a credential is rather than holding one. A second regular
expression here would be a second answer to one question, and the wrong copy is the one that
decides a password is not a password.

Rejected: reading the private repository over the network to check it. Nothing here takes a
URL or a token, because a check that authenticates to a client's private repository is a check
that holds a credential for every client at once, which is a worse object than the thing it
audits. It takes the names of what is in there, which is what a person or a CI job in that
repository can pass it.

Rejected: declaring these operational variables as `brain.install.Setting`s. `POSTGRES_PASSWORD`
is not client-specific in the sense M41 means: every install has one and it says nothing about
who the client is. Adding it to `INSTALLATION` would put it on the console's installation
screen beside the company name and the logo, and widen the one declaration that exists to draw
exactly that line.

Task ids: M42.1.1, M42.1.2, M42.3.2, M42.5.2, M30.1.4, M30.1.5
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Final

from brain.deployment.app_environment import VAULT_SETTINGS, WORKER_VAULT_CHOICE
from brain.firstrun import _CREDENTIAL_NAME, _NAMES_A_PLACE, MIN_SECRET_CHARS
from brain.install import INSTALLATION, Belongs

#: Why a repository of environment files is not the second copy M41 refuses.
A_VARIABLES_REPOSITORY_HOLDS_VALUES_AND_A_FORK_HOLDS_CODE: Final = (
    "One environment file per install is configuration under version control: there is still "
    "one image, every fix reaches every client through it, and what differs between two "
    "installs is a list of values with no code in it. A repository holding the product beside "
    "those values is a second product that every fix has to reach twice, and nothing reports "
    "when one of them is missed. The two look identical in a directory listing and differ in "
    "the only thing that matters, which is why this is checked by name rather than by habit."
)

#: Why a check that finds a shared secret must not print it.
A_CHECK_THAT_PRINTS_THE_VALUE_IS_THE_LEAK_IT_LOOKS_FOR: Final = (
    "Reporting that two installs share a password, and quoting it, has moved that password "
    "out of two private repositories and into whatever read the report: a CI log, a terminal "
    "scrollback, a paste in a chat. The reader loses nothing, because the action is the same "
    "either way and it is to mint a new one. So a finding names the installs and the settings "
    "and never the value, and that is the same rule the platform applies to a refusal message."
)

#: Why a template ships no secret, not even one that is declared.
A_VALUE_THAT_ARRIVED_WITH_THE_TEMPLATE_WAS_NEVER_MINTED: Final = (
    "A default password in a file people copy is the password the install runs with. The copy "
    "connects, nothing fails, and there is no moment at which anybody is told to change it. "
    "It is also the same value on every install that copied the same file, so one client's "
    "leak is every client's. A blank with a sentence saying where the real value comes from "
    "fails at the first connection instead, which is the failure you want."
)

#: What an install may be called. Lower case, digits and hyphens, because the name is a file
#: name in a repository and a directory on a server, and a name that differs only by case is
#: two installs on Linux and one on the machine somebody clones it to.
INSTALL_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")

#: An environment variable name, spelled as it is set.
VARIABLE_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")

#: What one install's file is called in the variables repository.
ENV_FILE_SUFFIX: Final = ".env"

#: What may sit in a variables repository beside the install files.
#:
#: An allowlist rather than a list of things to refuse, and that is the direction that
#: survives: a blocklist of `src`, `Dockerfile` and `pyproject.toml` is green for the fourth
#: shape a fork arrives in, and a fork arriving in a shape nobody listed is the whole failure.
PERMITTED_BESIDE: Final[frozenset[str]] = frozenset({"README.md", ".gitignore", ".gitattributes"})

#: The variables that hold a token the vault issued, and not one the installer generated: the
#: application's and the worker's. Derived from the two names `brain.deployment.app_environment`
#: already owns, and held equal to the tokens the installer asks the vault to mint by a test.
#:
#: Their length is the vault's. OpenBao service tokens are about twenty-six characters, which is
#: shorter than `MIN_SECRET_CHARS` and correct, so `unminted_secrets` does not apply the length
#: test to them. Empty and shared are still faults, so it still applies those two.
ISSUED_BY_THE_VAULT: Final[frozenset[str]] = frozenset({VAULT_SETTINGS[1], WORKER_VAULT_CHOICE})

#: Why a vault-issued token is exempt from the length test and from nothing else.
THE_LENGTH_OF_WHAT_THE_VAULT_ISSUED_IS_THE_VAULT_S_AND_NOT_THE_INSTALLER_S: Final = (
    "The installer asks the vault to mint the application's and the worker's tokens and writes "
    "what it is handed, so their length is the vault's choice: an OpenBao service token is about "
    "twenty-six characters. Holding it to the length the installer chooses for the secrets it "
    "generates fails every correct install, with no way to make it pass short of a token the "
    "vault did not mint. The length test is the only one that does not carry over. A blank "
    "token is still a vault nobody can reach, and one token doing for two settings is still the "
    "application's and the worker's policies being one."
)

#: Names whose value is public even though the name reads like a credential. A public key is
#: half of a pair and is meant to be copied, so refusing to emit one would make the template
#: unable to describe a working install.
NOT_A_SECRET: Final[frozenset[str]] = frozenset({"PUBLIC"})


class VariablesError(Exception):
    """Raised when a per-install file would carry something it must not."""


def is_secret_name(name: str) -> bool:
    """Whether this variable holds a credential, rather than saying where one is.

    Delegated to `brain.firstrun`, which owns the question and owns the harder half of it:
    `KEYCLOAK_ADMIN_PASSWORD_FILE` names a path and holds nothing, and a check that read the
    word PASSWORD and stopped would refuse to emit the one line that makes the file work.
    """
    if any(part in NOT_A_SECRET for part in name.upper().split("_")):
        return False
    if _NAMES_A_PLACE.search(name):
        return False
    return bool(_CREDENTIAL_NAME.search(name))


def parse_env(text: str) -> dict[str, str]:
    """An environment file as a mapping, with quotes removed and comments dropped.

    **The quote stripping is not cosmetic.** `shared_secrets` compares values between two
    installs, and `PASSWORD="abc"` against `PASSWORD=abc` is the same secret written twice.
    A comparison that read the quotes would report the pair as different, which is a check
    that is green on exactly the case it exists for.

    A line with no `=` is not a setting and is skipped rather than refused, because these
    files are edited by hand and a stray word is not worth failing a client's deploy over.
    """
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        stripped = stripped.removeprefix("export ").strip()
        name, separator, value = stripped.partition("=")
        if not separator:
            continue
        values[name.strip()] = _unquoted(value.strip())
    return values


def _unquoted(value: str) -> str:
    """A value with one matched pair of surrounding quotes removed."""
    for quote in ('"', "'"):
        if len(value) > 1 and value.startswith(quote) and value.endswith(quote):
            return value[1:-1]
    return value


def install_file(install: str) -> str:
    """The name of one install's file in the variables repository."""
    assert_install_name(install)
    return f"{install}{ENV_FILE_SUFFIX}"


def assert_install_name(install: str) -> None:
    """Refuse a name that is not usable as a file name and a directory on a server."""
    if not INSTALL_NAME.match(install):
        msg = (
            f"{install!r} is not an install name; lower case letters, digits and hyphens, "
            "because the name is a file in the variables repository and a directory on a "
            "server, and two names differing only by case are one file on some machines"
        )
        raise VariablesError(msg)


def template_for(install: str, *, also: Mapping[str, str] | None = None) -> str:
    """The blank environment file for one install, documented field by field.

    `also` carries the variables an install needs that are not `INSTALL_` settings, as a name
    against its meaning: the database password, the image tag, the deployment environment.
    They are a mapping rather than a declaration because they belong to the deployment rather
    than to the product's idea of a client, and `brain.install.INSTALLATION` is deliberately
    the narrower list.

    **Refuses to emit a value it cannot explain (M42.3.2), and that is a rule about `also`
    rather than about the declaration.** A `Setting` cannot be constructed without a meaning,
    so a refusal aimed at the declared list would be unreachable code claiming to be a guard.
    What can arrive unexplained is exactly what a caller passes here, which is also the half
    nobody reviews: a variable added to a compose file on a Friday, copied into the template
    on the Monday, and set on a client's server by somebody who has no idea what it does.
    """
    lines = [
        f"# {install}: every value this installation supplies, and what each one is for.",
        "# One file per install. The repository holding it carries these files and no",
        "# product code: see variables.A_VARIABLES_REPOSITORY_HOLDS_VALUES_AND_A_FORK_HOLDS_CODE.",
        "",
    ]
    assert_install_name(install)
    declared = {one.name for one in INSTALLATION}
    for name, meaning in sorted((also or {}).items()):
        if not VARIABLE_NAME.match(name):
            msg = f"{name!r} is not an environment variable name, so nothing would read it"
            raise VariablesError(msg)
        if not meaning.strip():
            msg = (
                f"{name} has no meaning written down, and this generator will not emit a "
                "value it cannot explain: somebody sets it on a client's server by guessing"
            )
            raise VariablesError(msg)
        if name in declared:
            msg = (
                f"{name} is already declared in brain.install.INSTALLATION with its own "
                "meaning, and two meanings for one variable is one meaning nobody read"
            )
            raise VariablesError(msg)

    for group in Belongs:
        lines.append(f"# --- {group.value}")
        for one in INSTALLATION:
            if one.belongs is not group:
                continue
            lines.append(f"# {one.meaning}")
            lines.extend(_emitted(one.name, one.default, required=one.required))
        lines.append("")

    if also:
        lines.append("# --- this deployment")
        for name, meaning in sorted(also.items()):
            lines.append(f"# {meaning}")
            lines.extend(_emitted(name, "", required=False))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _emitted(name: str, default: str, *, required: bool) -> list[str]:
    """One variable's lines: the note that applies to it, then the assignment.

    See `A_VALUE_THAT_ARRIVED_WITH_THE_TEMPLATE_WAS_NEVER_MINTED` for why a credential is
    blank here whatever it was declared with.
    """
    if is_secret_name(name):
        return [
            "# Minted on this server by the installer. Never copied from another install.",
            f"{name}=",
        ]
    if required:
        return ["# No default. The system refuses to start without it.", f"{name}="]
    return [f"{name}={default}"]


def variables_repository_gaps(names: Iterable[str]) -> tuple[str, ...]:
    """Everything in the variables repository that is not one install's environment file.

    `names` is what the repository holds, as paths relative to its root. Taken rather than
    read, because this has to be answerable about a repository that is not on this machine and
    that nothing here should ever hold a credential for.

    See `A_VARIABLES_REPOSITORY_HOLDS_VALUES_AND_A_FORK_HOLDS_CODE`.
    """
    found: list[str] = []
    for name in sorted(names):
        if name in PERMITTED_BESIDE:
            continue
        if "/" in name or chr(92) in name:
            found.append(
                f"{name}: a variables repository is flat, one file per install, so a "
                "directory here is either a second install layout or a copy of the product"
            )
            continue
        if not name.endswith(ENV_FILE_SUFFIX):
            found.append(
                f"{name}: not an install file and not one of {sorted(PERMITTED_BESIDE)}, so "
                "this repository holds something other than values, which is a fork"
            )
            continue
        if not INSTALL_NAME.match(name[: -len(ENV_FILE_SUFFIX)]):
            found.append(
                f"{name}: the part before {ENV_FILE_SUFFIX} is not an install name, so "
                "nothing can say which installation this file belongs to"
            )
    return tuple(found)


def shared_secrets(installs: Mapping[str, Mapping[str, str]]) -> tuple[str, ...]:
    """Every credential one value of which is set on more than one install.

    **Grouped by value rather than by name, which is the half a per-setting check misses.**
    One client's `POSTGRES_PASSWORD` copied into another client's `APP_ROLE_PASSWORD` is the
    same failure as copying it under the same name, and it is the likelier one: a person
    reusing a password reuses it wherever it is asked for.

    The finding names the installs and the settings. See
    `A_CHECK_THAT_PRINTS_THE_VALUE_IS_THE_LEAK_IT_LOOKS_FOR`.
    """
    holders: dict[str, list[tuple[str, str]]] = {}
    for install in sorted(installs):
        for name, value in sorted(installs[install].items()):
            if not value.strip() or not is_secret_name(name):
                continue
            holders.setdefault(value, []).append((install, name))
    found: list[str] = []
    for held in holders.values():
        if len({install for install, _ in held}) < 2:
            continue
        where = " and ".join(f"{name} on {install}" for install, name in held)
        found.append(
            f"one credential is set to the same value on more than one install: {where}. "
            "Mint a new one for each; a value shared between two clients makes one client's "
            "leak the other client's incident"
        )
    return tuple(found)


def unminted_secrets(values: Mapping[str, str]) -> tuple[str, ...]:
    """Every credential on one install that the installer did not generate for it.

    Three shapes and each is a real install file. Blank, so the container refuses to start and
    the next thing that happens is somebody typing enough characters to get past it. Short
    enough to be guessed rather than generated. And one value doing for two credentials, which
    `.env.example` already asks for in words about `APP_ROLE_PASSWORD` ("never the same as the
    postgres superuser") with nothing anywhere checking it: the application role then has the
    superuser's password, so the pooler's ceiling and the reserved connections it protects are
    one leaked value away from being nobody's ceiling at all.

    The length is `brain.firstrun.MIN_SECRET_CHARS` rather than a number chosen here, because
    a second opinion about how long a generated secret has to be is a second opinion that is
    lower on the day somebody is in a hurry. **It is applied to what the installer generates and
    not to a token the vault issued** (`ISSUED_BY_THE_VAULT`): see
    `THE_LENGTH_OF_WHAT_THE_VAULT_ISSUED_IS_THE_VAULT_S_AND_NOT_THE_INSTALLER_S`. Those are still
    refused when empty and when two settings hold one value.

    Names, never values. See `A_CHECK_THAT_PRINTS_THE_VALUE_IS_THE_LEAK_IT_LOOKS_FOR`.
    """
    found: list[str] = []
    holders: dict[str, list[str]] = {}
    for name in sorted(values):
        if not is_secret_name(name):
            continue
        value = values[name].strip()
        if not value:
            found.append(f"{name} is empty, so nothing was minted for it on this server")
            continue
        if len(value) < MIN_SECRET_CHARS and name not in ISSUED_BY_THE_VAULT:
            found.append(
                f"{name} is shorter than {MIN_SECRET_CHARS} characters, which is short "
                "enough to be guessed rather than generated"
            )
        holders.setdefault(value, []).append(name)
    for names in holders.values():
        if len(names) < 2:
            continue
        found.append(
            f"{' and '.join(names)} hold one value between them, so whatever that value "
            "reaches, it reaches everywhere it is accepted"
        )
    return tuple(found)


# ------------------------------------------------------------------------- the command line
#: What the command prints when it is called wrongly.
USAGE: Final = (
    "usage: python -m brain.deployment.variables template <install> [NAME=meaning ...]\n"
    "       python -m brain.deployment.variables check <directory>"
)

#: The exit statuses a wrapper acts on.
EXIT_CLEAN: Final = 0
EXIT_FOUND: Final = 1
EXIT_USAGE: Final = 2

#: What `check` leaves out of a variables directory, because it is the repository's own.
NOT_THE_REPOSITORY_S_CONTENT: Final = frozenset({".git"})


def check_directory(directory: Path) -> tuple[str, ...]:
    """Everything wrong with a variables repository checked out at `directory`.

    The repository is read from a directory somebody checked out, never over the network, for the
    reason in the module docstring. It is the three checks written for it and nothing new: what
    the repository holds besides install files (`variables_repository_gaps`), a credential set
    to one value on two installs (`shared_secrets`), and a credential that is set and too short
    to have been generated (`unminted_secrets`, with the blank ones left out, because a blank
    credential is what the template emits and the installer mints on the server). Findings name
    an install and a setting and never a value.
    """
    names = sorted(
        one.name for one in directory.iterdir() if one.name not in NOT_THE_REPOSITORY_S_CONTENT
    )
    found = list(variables_repository_gaps(names))
    installs: dict[str, dict[str, str]] = {}
    for name in names:
        if name.endswith(ENV_FILE_SUFFIX) and (directory / name).is_file():
            installs[name[: -len(ENV_FILE_SUFFIX)]] = parse_env(
                (directory / name).read_text(encoding="utf-8")
            )
    found.extend(shared_secrets(installs))
    for install, values in sorted(installs.items()):
        set_only = {name: value for name, value in values.items() if value.strip()}
        found.extend(f"{install}: {one}" for one in unminted_secrets(set_only))
    return tuple(found)


def main(argv: Sequence[str] | None = None) -> int:
    """Print an install's blank template, or check a variables repository, and say which.

    The two things the module's functions were written to be asked and nothing asked: a person
    setting up the variables repository for an install runs `template`, and the repository's own
    job runs `check` on every push. Neither reads the network or the environment.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) >= 2 and args[0] == "template":
        meanings: dict[str, str] = {}
        for one in args[2:]:
            name, _, meaning = one.partition("=")
            meanings[name] = meaning
        try:
            print(template_for(args[1], also=meanings), end="")
        except VariablesError as refused:
            print(str(refused), file=sys.stderr)
            return EXIT_USAGE
        return EXIT_CLEAN
    if len(args) == 2 and args[0] == "check":
        where = Path(args[1])
        if not where.is_dir():
            print(f"{args[1]} is not a directory", file=sys.stderr)
            return EXIT_USAGE
        findings = check_directory(where)
        for one in findings:
            print(one)
        if findings:
            return EXIT_FOUND
        print("the variables repository holds install files only, and no credential repeats")
        return EXIT_CLEAN
    print(USAGE, file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
