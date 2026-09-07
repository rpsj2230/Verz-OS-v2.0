"""The gate that keeps this repository a template rather than one client's copy.

M41.1.1 asks for a sweep refusing any client name, domain, work address, company id or
storage path literal in `src`, `migrations`, the console and the compose files.

**The obvious implementation is a blocklist of the first client's names, and it is worthless.**
It goes green the day it is written, it stays green for the second client, and the second
client is the entire point: their name is not on the list, so their domain in a default and
their bucket in a compose file both pass. A blocklist tests whether you have finished
find-and-replace, and finding out later is exactly what M41 is written to prevent.

So this checks two properties that hold for a client nobody has met yet.

**One: no value-shaped literal.** An email address, a bare IPv4, or an absolute URL to a real
host is a client value whatever the client is called, and none of the three has any business
being a literal in a product. What is allowed is what documentation is made of: the reserved
example domains, loopback, and the service names the compose network resolves. That list is
short and every entry is defensible, which is the test of an allowlist.

**Two: one reader.** Every `INSTALL_` setting is read through `brain.install.value_of` and
nowhere else. A second reader has a second default, and the wrong one is the one nobody looked
at: unlike a literal it does not show up in a grep, and it agrees with the first reader on
every machine where both are set, which is every machine except the new client's.

**What this deliberately does not do.** It does not read prose. `core/projection.py` saying
"about 40 MB at Verz's scale" is a measurement with a place it was taken, and stripping the
place would make the sentence a claim about nothing. A comment cannot be deployed. The check
is about values the running system uses, so it reads string literals and assignments and
leaves docstrings and comments alone, which is also why it can be a hard gate rather than an
advisory one.

Task ids: M41.1.1, M41.3.2
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Final

from brain.install import INSTALL_PREFIX, INSTALLATION

#: Why the obvious implementation is the wrong one.
A_BLOCKLIST_OF_ONE_CLIENTS_NAMES_PASSES_FOR_EVERY_OTHER_CLIENT: Final = (
    "A sweep listing the first client's names is green the day it is written and green for "
    "the second client, whose name is not on it. It tests whether find-and-replace has been "
    "run, and finding that out at the second install is what this module exists to prevent."
)

#: Why a comment is not a finding.
A_COMMENT_CANNOT_BE_DEPLOYED: Final = (
    "A measurement is worth more with the place it was taken than without it, and prose "
    "naming the first deployment is a fact about where a number came from rather than a "
    "value the system uses. Reading literals and not comments is what lets this be a hard "
    "gate instead of an advisory one nobody can keep green."
)

#: Where a client value would actually land.
#:
#: `docs` is here and M41.1.1 does not name it, deliberately. Those pages are served by the
#: running application at `/build`, so they are as deployed as anything in `src`, and leaving
#: them out is how the first version of this sweep came back green while four pages fetched a
#: stylesheet from Google on every load from inside the client's network.
SEARCHED: Final[tuple[str, ...]] = ("src", "migrations", "console/src", "docs")

#: What is read inside those areas. HTML and JavaScript because the build pages are both,
#: and a link tag is exactly the shape of value this is looking for.
READ_SUFFIXES: Final[frozenset[str]] = frozenset({".py", ".ts", ".tsx", ".html", ".js"})

#: Compose is searched too, and separately, because it is YAML rather than Python.
COMPOSE_GLOB: Final = "docker-compose*.yml"

#: An email address in a literal.
ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")

#: A bare IPv4. Deliberately not matching version numbers: four octets, each 0-255.
IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)

#: A block comment in TypeScript or JavaScript. Prose, like a Python docstring.
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)

#: A comment in YAML, HTML or TypeScript, for the coarse line-based read of a non-Python file.
#:
#: **The `//` half must not match the one inside `https://`, and the first version did.** It
#: was `(#|//).*$`, so every URL in a compose file or an HTML page was truncated at the scheme
#: and the sweep could not have found one: the four Google Fonts links it did report were all
#: in a `.py` file, which takes the AST path instead. A mutation-driven test planting a host
#: in a real docs page is what showed it.
COMMENT = re.compile(r"(?<![:\w])//.*$|#.*$")

#: A bare hostname, for a constant holding one without a scheme.
BARE_HOST = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")

#: An absolute http(s) URL, captured by host.
URL_HOST = re.compile(r"https?://([A-Za-z0-9._-]+(?::\d+)?)")

#: Top-level domains documentation is made of. Reserved by RFC 2606 and RFC 6761 for exactly
#: this, so none of them can ever become a real client's.
#:
#: Matched as a suffix rather than as whole names, which is the difference between allowing
#: `acme.example` and having to list it. The corollary is worth knowing: `example.com.sg` is
#: **not** reserved, it is an ordinary domain somebody could register, and it was in this
#: repository as a fixture address until the sweep found it.
RESERVED_SUFFIXES: Final[tuple[str, ...]] = (
    ".example",
    ".invalid",
    ".test",
    ".localhost",
    "example.com",
    "example.org",
    "example.net",
    "example.edu",
)


def is_reserved(domain: str) -> bool:
    """True for a domain that is reserved for documentation and can never be a client's."""
    lowered = domain.lower()
    return lowered == "localhost" or lowered.endswith(RESERVED_SUFFIXES)


def vendor_hosts(repo: Path) -> frozenset[str]:
    """Every host a connector declares as a module-level constant.

    **Derived rather than listed, and that is the point.** A vendor's API host belongs to the
    product: `api.xero.com` is where Xero is, for every client this system will ever have, and
    a hand-written allowlist of them would need editing on the day somebody adds a connector,
    which is the day nobody is thinking about client independence.

    Only module-level constants count, and only ones named for the job. A URL buried inside a
    function is exactly what should be refused, so the rule doubles as one worth having on its
    own: a connector declares where its vendor is, at the top of the file, once.
    """
    found: set[str] = set()
    roots = [repo / "src" / "brain" / one for one in DECLARING_AREAS]
    for path in sorted(one for root in roots if root.is_dir() for one in root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            named = any(
                isinstance(one, ast.Name) and one.id.endswith(VENDOR_CONSTANT_SUFFIXES)
                for one in targets
            )
            value = getattr(node, "value", None)
            if named and isinstance(value, ast.Constant) and isinstance(value.value, str):
                for match in URL_HOST.finditer(value.value):
                    found.add(match.group(1).split(":")[0].lower())
                # A bare hostname, when the constant holds one rather than a whole URL. The
                # first version tested `"." in value`, which swept in a named reason constant
                # whose name happened to end in `_URL` and whose value was a paragraph of
                # prose. A hostname shape is the check; a sentence is not a host.
                if "://" not in value.value and BARE_HOST.fullmatch(value.value.strip()):
                    found.add(value.value.strip().lower())
    return frozenset(found)


#: Hosts that are this deployment's own shape rather than any client's: loopback, the compose
#: network's service names, and the registries an image comes from. Each is defensible on its
#: own, which is the test an allowlist has to pass.
ALLOWED_HOSTS: Final[frozenset[str]] = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",  # noqa: S104  a host in an allowlist, not an address to bind
        "::1",
        # Service names are not listed here. See `compose_services`: they are read from the
        # compose files, so adding a service does not mean editing this module.
        # Standards bodies and registries. A URL to one of these is a citation, not a client.
        "www.w3.org",
        "schema.org",
        "ghcr.io",
        "quay.io",
        "docs.pydantic.dev",
        "mypy.readthedocs.io",
        "www.postgresql.org",
        "peps.python.org",
    }
)


def compose_services(repo: Path) -> frozenset[str]:
    """Every service name the compose files declare.

    **Derived for the same reason vendor hosts are.** `langfuse-clickhouse:8123` and
    `automation-egress:3128` are addresses on this system's own network, and hand-listing them
    means editing this module on the day somebody adds a service, which is the day nobody is
    thinking about client independence. Reading them from the compose files makes the rule
    "a host is allowed if this deployment declares it", which is a rule rather than a list.

    Parsed rather than pattern-matched, so a service named in a comment does not count.
    """
    import yaml

    found: set[str] = set()
    for path in sorted(repo.glob(COMPOSE_GLOB)):
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(parsed, dict):
            services = parsed.get("services")
            if isinstance(services, dict):
                found.update(str(one).lower() for one in services)
    return frozenset(found)


#: Loopback and this-network addresses, which name no client.
ALLOWED_IPS: Final[frozenset[str]] = frozenset(
    {"127.0.0.1", "0.0.0.0", "255.255.255.255"}  # noqa: S104  an allowlist, not a bind
)

#: Where a vendor endpoint may be declared. `channels` as well as `connectors`, because a
#: channel adapter reaches a vendor for the same reason a connector does: `BOT_FRAMEWORK_ISSUER`
#: in `channels/teams.py` is where Microsoft is, for every client this system will ever have.
DECLARING_AREAS: Final[tuple[str, ...]] = ("connectors", "channels")

#: What a constant naming a vendor endpoint is called. A rule rather than a list of hosts: the
#: sweep is satisfied by declaring where the vendor is, at the top of the file, once. A URL
#: buried in a function body is still refused, which is the half worth keeping.
VENDOR_CONSTANT_SUFFIXES: Final[tuple[str, ...]] = (
    "BASE_URL",
    "_HOST",
    "HOST",
    "_ISSUER",
    "_ENDPOINT",
    "_URL",
)

#: The one module allowed to read an installation setting. See the header.
THE_READER: Final = "src/brain/install.py"


def _searched_files(repo: Path) -> Iterator[Path]:
    for area in SEARCHED:
        root = repo / area
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix in READ_SUFFIXES and "__pycache__" not in path.parts:
                yield path
    yield from sorted(repo.glob(COMPOSE_GLOB))


def _literals(path: Path) -> Iterator[tuple[int, str]]:
    """Every string a running system could use, and no comments or docstrings.

    Python is parsed rather than scanned, so a docstring is a docstring and not a string
    constant that happens to sit at the top of a module. Everything else is read line by line
    with `#` and `//` comments stripped, which is coarse and is the right coarseness: YAML and
    TypeScript both put real values on the left of a comment and never on the right.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        tree = ast.parse(text, filename=str(path))
        documented = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in documented
            ):
                yield node.lineno, node.value
        return
    # Block comments first, and they are why `console/src/config.ts` was reported: it explains
    # an issuer-prefix attack using `https://idp.example.com.attacker.net/`, inside a JSDoc
    # block. That is prose about a threat and is exactly what a Python docstring would be, so
    # it is removed the same way. Replaced with newlines rather than deleted, so every line
    # after it keeps its number and a finding still points at the right place.
    text = BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    for number, line in enumerate(text.splitlines(), 1):
        stripped = COMMENT.sub("", line)
        if stripped.strip():
            yield number, stripped


def value_shaped_literals(repo: Path) -> tuple[str, ...]:
    """Every literal that looks like one client's value rather than the product's.

    Addresses, bare IPv4s and absolute URLs to real hosts. See
    `A_BLOCKLIST_OF_ONE_CLIENTS_NAMES_PASSES_FOR_EVERY_OTHER_CLIENT` for why it is shapes and
    not names.
    """
    vendors = vendor_hosts(repo) | compose_services(repo)
    found: list[str] = []
    for path in _searched_files(repo):
        where = path.relative_to(repo).as_posix()
        for number, literal in _literals(path):
            for match in ADDRESS.finditer(literal):
                if not is_reserved(match.group(1)):
                    found.append(f"{where}:{number}: a work address, {match.group(0)!r}")
            for match in URL_HOST.finditer(literal):
                host = match.group(1).split(":")[0].lower()
                if host not in ALLOWED_HOSTS and host not in vendors and not is_reserved(host):
                    found.append(f"{where}:{number}: a client host, {match.group(1)!r}")
            for match in IPV4.finditer(literal):
                if match.group(0) not in ALLOWED_IPS:
                    found.append(f"{where}:{number}: an address, {match.group(0)!r}")
    return tuple(found)


def environment_reads(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """Every `INSTALL_` name this module reads out of the environment itself.

    **Shape rather than mention, and the first version got this wrong.** It flagged any
    literal beginning `INSTALL_`, which made `value_of("INSTALL_ACCENT_COLOUR")` a violation:
    the one correct way to read a setting was reported as the second reader. A check that
    fires on the right usage is worse than none, because the first thing anybody does is
    switch it off.

    So this looks for the three real shapes: `os.environ["X"]`, `os.environ.get("X")` and
    `os.getenv("X")`, plus the same on anything named `env` or `environ`, which is how the
    parameter is spelled throughout this repository.
    """

    def named(node: ast.expr) -> bool:
        if isinstance(node, ast.Attribute):
            return node.attr in {"environ", "env"}
        return isinstance(node, ast.Name) and node.id in {"environ", "env"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and named(node.value):
            key = node.slice
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value.startswith(INSTALL_PREFIX)
            ):
                yield node.lineno, key.value
        if not isinstance(node, ast.Call) or not node.args:
            continue
        first = node.args[0]
        if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
            continue
        if not first.value.startswith(INSTALL_PREFIX):
            continue
        callee = node.func
        # `getenv` needs no receiver check: it means one thing wherever it is called from, and
        # requiring `os` would miss `from os import getenv`. `.get` does need one, because
        # `.get` on a dictionary is the most ordinary call in the language.
        bare = isinstance(callee, ast.Name) and callee.id == "getenv"
        through = isinstance(callee, ast.Attribute) and (
            callee.attr == "getenv" or (callee.attr == "get" and named(callee.value))
        )
        if bare or through:
            yield node.lineno, first.value


def second_readers(repo: Path) -> tuple[str, ...]:
    """Every module other than `brain.install` that reads an installation setting itself.

    Matched on the `INSTALL_` prefix rather than on the declared names, so a setting somebody
    reads before declaring it is caught as well: an undeclared read is the worse of the two,
    because it has a default nothing has written down.
    """
    declared = {one.name for one in INSTALLATION}
    found: list[str] = []
    for path in _searched_files(repo):
        where = path.relative_to(repo).as_posix()
        if where == THE_READER or path.suffix != ".py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        for number, name in environment_reads(tree):
            known = "" if name in declared else ", and it is not even declared"
            found.append(
                f"{where}:{number}: reads {name} from the environment rather than through "
                f"brain.install.value_of{known}"
            )
    return tuple(found)


def independence_gaps(repo: Path, *, extra_allowed: Iterable[str] = ()) -> tuple[str, ...]:
    """Everything about this tree that would arrive at the next client's install.

    `extra_allowed` exists for a test to prove the allowlist is consulted rather than for a
    caller to widen the gate: a caller who needs a host allowed should say why in
    `ALLOWED_HOSTS`, where the reason is reviewed with the rest of the list.
    """
    allowed = {one.lower() for one in extra_allowed}
    return tuple(
        one
        for one in (*value_shaped_literals(repo), *second_readers(repo))
        if not any(f"'{name}'" in one.lower() for name in allowed)
    )


#: Why a second copy of this repository is the failure that reports nothing.
#:
#: A fork, a vendored checkout and a submodule are three shapes of one thing: a version of
#: this product that a fix has to be applied to twice. Nothing anywhere notices when it is
#: applied once. Both copies keep passing their own tests, both deploy, and the client on the
#: older one meets the bug that was fixed a month ago on the other. There is no error to read
#: and no place the divergence appears, which is what separates this from an ordinary
#: maintenance cost: the cost is not the second copy, it is that the second copy is silent.
A_SECOND_COPY_IS_SILENT_UNTIL_A_CLIENT_MEETS_THE_BUG_THAT_WAS_FIXED: Final = (
    "A per-client fork, a vendored checkout or a submodule is a version of this product that "
    "every fix has to reach twice, and nothing reports when one of them is missed. Both "
    "copies pass their own tests and both deploy. The client on the older one finds the "
    "defect that was fixed elsewhere a month ago, and there is no error anywhere that would "
    "have said so. An install is a release tag plus one environment file precisely so that "
    "there is only ever one copy to fix."
)

#: What fetching a second repository looks like in a build input. A pattern rather than a
#: list of tools, because the shape is stable and the tools are not: what matters is that the
#: build reaches a repository other than the one it was started from.
FETCHES_A_REPOSITORY: Final = re.compile(
    r"\bgit\s+clone\b|\bgit\s+submodule\b|\bgit\+https?://|\bgh\s+repo\s+clone\b"
)

#: The files that decide what ends up in a running install. A second repository entering
#: through any of them is in production, whatever the source tree looks like.
BUILD_INPUTS: Final[tuple[str, ...]] = (
    "Dockerfile",
    "Makefile",
    "pyproject.toml",
    "docker-compose*.yml",
    ".github/workflows/*.yml",
    "ops/**/*.sh",
)


def build_inputs(repo: Path) -> tuple[Path, ...]:
    """Every file whose contents decide what a built image contains, in declaration order.

    Globbed rather than listed one by one so a ninth compose file or a second workflow is
    covered on the day it is written. A pattern that matches nothing is not an error: this
    repository has no `ops/**/*.sh` today and may never, and a check that refused a tree for
    the absence of a shell script would be describing this checkout rather than the product.
    """
    found: list[Path] = []
    for pattern in BUILD_INPUTS:
        found.extend(sorted(one for one in repo.glob(pattern) if one.is_file()))
    return tuple(found)


def duplication_gaps(repo: Path) -> tuple[str, ...]:
    """Every way a second copy of this repository has got into this one.

    Three shapes, and they are found rather than declared. A nested `.git` is a checkout
    somebody put inside the tree; a `.gitmodules` is a second repository whose version this
    one pins; a build input that clones is a second repository that never appears in the
    source tree at all and is in the image anyway. The third is the one a reader of the
    directory listing would miss.

    **What this cannot see is the fork on somebody else's account**, and saying so matters
    because the leaf's words are "no duplicated repository anywhere". A copy of this
    repository is by definition not in this repository. What is checkable here is that
    nothing in the product creates one, which is the half that can be kept honest by a
    machine; the other half is kept by `install.py` making a fork pointless, and that is
    what M41.1 and M41.3.1 are.

    The scan skips `.git` itself, because every path under it contains the string and the
    repository's own object store is not a vendored checkout.

    See `A_SECOND_COPY_IS_SILENT_UNTIL_A_CLIENT_MEETS_THE_BUG_THAT_WAS_FIXED`.
    """
    found: list[str] = []

    for path in sorted(repo.rglob(".git")):
        if path.parent == repo:
            continue
        where = str(path.parent.relative_to(repo)).replace(chr(92), "/")
        found.append(f"{where}: a second checkout is vendored inside this repository")

    if (repo / ".gitmodules").is_file():
        found.append(".gitmodules: a submodule is a second repository this one pins a version of")

    for path in build_inputs(repo):
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            # Comments stripped first, following `A_COMMENT_CANNOT_BE_DEPLOYED`, which this
            # module already argues for the other direction. A commented-out clone does not
            # fetch anything, and a comment explaining that the build deliberately does not
            # clone would otherwise be reported for containing the words it is about.
            if FETCHES_A_REPOSITORY.search(COMMENT.sub("", line)):
                where = str(path.relative_to(repo)).replace(chr(92), "/")
                found.append(f"{where}:{number}: the build fetches a second repository")

    return tuple(found)
