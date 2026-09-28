"""Every console write's ledger entry carries the writer's reach digest and the request's trace.

The ledger's entries are written by triggers on the rows the console writes (`0003`, `0054`,
`0059` and every migration since), and a trigger cannot know who is writing: it reads
`brain.actor_id`, `brain.ent_hash` and `brain.trace_id` from the transaction, set by
`brain.tables.audit.attributed_to`, and when nothing set them it writes `0003`'s placeholders,
thirty-two zeros for the reach and `tx.<xid>` for the trace. **A placeholder is not an error the
database can see**: the entry verifies, the chain holds, and the one question the ledger exists to
answer, "at what reach, in which request", has no answer. On 2026-09-21 a first run of this sweep
found the People screen's grants, legal holds and retention releases, the notices and relay
settings and the provider switch all writing that placeholder on every press.

**So the sweep follows each write back to where a request could set the attribution.** It reads
three things from source and nothing from a database. The tables whose write triggers read the
attribution, from `brain.ops.application_privileges.migrations_catalogue`, which renders every
migration in order. Every write to one of them in a module the application's sessions reach,
from `application_privileges.uses`. And, for a write in a module that does not set the
attribution itself, the functions that call the writing function, followed outwards until a
module that sets it, an explained caller, or a function nothing calls. A route handler reached
that way with no attribution on the path is a finding, and so is a writing function nobody calls,
because the day somebody calls it is the day the placeholder ships.

**"Sets the attribution" is read at the module, which is wider than the truth, and that is the
direction this errs in.** A module that calls `attributed_to` once is taken to call it before
every write it makes, which a module setting it for one route and not another would pass. The
alternative, proving an order of statements within a transaction from the syntax tree, is a
second interpreter of Python, and `application_privileges` makes the same choice for the settings
its policies read, for the same reason.

**What is not a console write is written down, with its reason, and a stale excuse fails.** The
first administrator's appointment writes the first reach there is, so no writer's reach exists to
carry; reconciliation runs when the process starts, with no request; the vault's log is shipped
by the worker, whose actor is the vault; the staff sync rewrites heads' audit grants at night with
nobody signed in. Each is in `NOT_A_REQUEST_WITH_A_REACH`, and an entry
that stops matching a path the sweep takes is itself a finding.

Task ids: M24.3.1
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Final

from brain.ops.application_privileges import (
    SRC,
    Catalogue,
    Use,
    migrations_catalogue,
    module_name,
    uses,
)
from brain.ops.controls import call_sites

#: The writes a trigger could need attributing.
WRITES: Final[tuple[str, ...]] = ("INSERT", "UPDATE", "DELETE")

#: What a trigger body reads when it takes the writer's reach from the transaction.
READS_THE_REACH: Final = "current_setting('brain.ent_hash'"

#: What in a module's source says it sets the attribution before it writes.
SETS_THE_ATTRIBUTION: Final[tuple[str, ...]] = (
    "attributed_to(",
    "from brain.attribution import",
    "ENT_HASH_SETTING",
    "brain.ent_hash",
)

#: The router methods that register a route handler.
HTTP_VERBS: Final = frozenset({"get", "post", "put", "patch", "delete"})

#: How far a write is followed outwards before the sweep gives up and reports it.
MAX_DEPTH: Final = 6

#: Why a placeholder in the ledger is a defect and not a default.
A_PLACEHOLDER_IN_THE_LEDGER_ANSWERS_NOTHING: Final = (
    "The ledger is read to answer who did this, at what reach, in which request. An entry whose "
    "reach is thirty-two zeros and whose trace is a transaction number answers the first and "
    "neither of the others, verifies perfectly and looks exactly like an entry that does, so "
    "nothing downstream can tell it was missing until somebody needs it."
)

#: Paths through which a write reaches the ledger with no request and no reach, and why. Keyed by
#: `module:function`, the writing function or the caller the path ends at.
NOT_A_REQUEST_WITH_A_REACH: Final[Mapping[str, str]] = MappingProxyType(
    {
        "brain.identity.first_administrator:FirstAdministrators.appoint": (
            "The first administrator's appointment writes the first grants the install has, from "
            "the setup code, before any principal holds a reach, so there is no writer's reach to "
            "carry and the entry records the unsupplied digest, which is the truth."
        ),
        "brain.identity.administration_reconciliation:reconcile_super_admin_roles": (
            "Runs when the process starts, recording a first administrator appointed before role "
            "grants existed as Super Admin, once: no request and no person pressing anything, so "
            "no reach and no trace, and the actor is first run, as at the appointment."
        ),
        "brain.identity.administration_reconciliation:reconcile_first_administrators": (
            "Runs when the process starts, granting an administrator what was added to the "
            "administration set since they were appointed: no request, no person pressing "
            "anything, and so no reach and no trace."
        ),
        "brain.ops.staff_sync_run:_rewrite_heads": (
            "The scheduled staff sync rewrites each department head's audit grants from the "
            "staff list at night with nobody signed in: the grants name the roster as their "
            "granter, which the trigger records as the actor, and there is no request and no "
            "person's reach."
        ),
        "brain.ops.staff_sync_store:stop_leavers_agents": (
            "The staff sync stops a leaver's agents in the run that marks them, at night in the "
            "worker with nobody signed in. It sets disabled_at and never owner_id, and 0105's "
            "trigger on agent.agent records an owner change only, so the statement appends no "
            "entry for a placeholder to reach; the owner change it waits for is attributed by "
            "the route that makes it."
        ),
        "brain.ops.vault_audit_ship:StoredVaultAccess.ship": (
            "The worker copies the vault's own audit log into the ledger; the actor is the vault, "
            "and no person's request or reach is involved."
        ),
    }
)


@dataclass(frozen=True)
class Finding:
    """One path along which a write can reach the ledger carrying a placeholder."""

    table: str
    write: str
    path: tuple[str, ...]
    why: str

    def __str__(self) -> str:
        return f"{self.write} {self.table} via {' <- '.join(self.path)}: {self.why}"


def attributed_writes(catalogue: Catalogue) -> frozenset[tuple[str, str]]:
    """Every (table, write) whose firing triggers read the writer's reach from the transaction."""
    return frozenset(
        (table, write)
        for table in catalogue.tables
        for write in WRITES
        if any(READS_THE_REACH in body for body in catalogue.fired_by(table, write))
    )


@cache
def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@cache
def _tree(path: Path) -> ast.Module:
    return ast.parse(_source(path))


def _files(src: Path) -> Mapping[str, Path]:
    return {module_name(path, src): path for path in sorted(src.rglob("*.py"))}


def sets_attribution(path: Path) -> bool:
    """Whether this module names the attribution anywhere. See the module docstring."""
    text = _source(path)
    return any(marker in text for marker in SETS_THE_ATTRIBUTION)


def enclosing(path: Path, line: int) -> str:
    """The top-level function a line sits in, `Class.method` for a method, or empty."""
    best = ""
    for node in _tree(path).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.lineno <= line <= (node.end_lineno or node.lineno):
                best = node.name
        elif isinstance(node, ast.ClassDef):
            for inner in node.body:
                if isinstance(inner, ast.FunctionDef | ast.AsyncFunctionDef) and (
                    inner.lineno <= line <= (inner.end_lineno or inner.lineno)
                ):
                    best = f"{node.name}.{inner.name}"
    return best


def is_route(path: Path, function: str) -> bool:
    """Whether this function is registered as the handler for an HTTP path."""
    for node in _tree(path).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function:
            # `@router.post(PATH, ...)`: the verb is the signal, because the path is as often a
            # constant as a literal, and a literal-only reading missed every route written so.
            return any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in HTTP_VERBS
                for decorator in node.decorator_list
            )
    return False


def callers_of(symbol: str, files: Mapping[str, Path], src: Path) -> list[str]:
    """Every `module:function` whose body calls this `module:function`, found through imports."""
    module, _, name = symbol.partition(":")
    found: list[str] = []
    # The module's own callers as well: `call_sites` leaves them out, and a route that calls a
    # helper beside it is the commonest shape a write takes here.
    for caller in (*call_sites(symbol, src), module):
        path = files.get(caller)
        if path is None:
            continue
        tree = _tree(path)
        bound = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == module
            for alias in node.names
            if alias.name == name
        } | ({name} if caller == module else set())
        for node in tree.body:
            owners: list[tuple[str, ast.AST]] = []
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                owners.append((node.name, node))
            elif isinstance(node, ast.ClassDef):
                owners.extend(
                    (f"{node.name}.{inner.name}", inner)
                    for inner in node.body
                    if isinstance(inner, ast.FunctionDef | ast.AsyncFunctionDef)
                )
            for owner, body in owners:
                if caller == module and owner == name:
                    continue
                calls = (
                    one
                    for one in ast.walk(body)
                    if isinstance(one, ast.Call)
                    and (
                        (isinstance(one.func, ast.Name) and one.func.id in bound)
                        or (isinstance(one.func, ast.Attribute) and one.func.attr == name)
                    )
                )
                if next(calls, None) is not None:
                    found.append(f"{caller}:{owner}")
    return sorted(set(found))


def _follow(
    symbol: str,
    files: Mapping[str, Path],
    src: Path,
    explained: Mapping[str, str],
    trail: tuple[str, ...],
    used: set[str],
) -> list[tuple[tuple[str, ...], str]]:
    """Every path outwards from this function that reaches no attribution, with why."""
    if symbol in explained:
        used.add(symbol)
        return []
    module, _, function = symbol.partition(":")
    path = files[module]
    here = (*trail, symbol)
    if sets_attribution(path):
        return []
    if "." not in function and is_route(path, function):
        return [(here, "a route handler writes with nothing setting the attribution")]
    if len(here) > MAX_DEPTH:
        return [(here, f"followed {MAX_DEPTH} calls outwards without finding the attribution")]
    if "." in function:
        return [(here, "a method is not followed; set the attribution in its module")]
    callers = [one for one in callers_of(symbol, files, src) if one not in here]
    if not callers:
        return [(here, "nothing calls it, so whoever does first will write the placeholder")]
    return [
        found for caller in callers for found in _follow(caller, files, src, explained, here, used)
    ]


def findings(
    catalogue: Catalogue | None = None,
    found: Iterable[Use] | None = None,
    *,
    src: Path = SRC,
    explained: Mapping[str, str] = NOT_A_REQUEST_WITH_A_REACH,
) -> list[str]:
    """Every write path that can leave the reach digest or the trace as a placeholder, and every
    stale excuse. Empty is the answer the build requires."""
    known = catalogue if catalogue is not None else migrations_catalogue()
    targets = attributed_writes(known)
    every = list(found) if found is not None else uses(src, known=known.tables)
    files = _files(src)
    used: set[str] = set()
    out: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for use in every:
        if (use.table, use.privilege) not in targets:
            continue
        function = enclosing(files[use.module], use.line)
        key = (use.table, use.privilege, f"{use.module}:{function}")
        if key in seen:
            continue
        seen.add(key)
        symbol = f"{use.module}:{function}" if function else f"{use.module}:<module>"
        for path, why in _follow(symbol, files, src, explained, (), used):
            out.append(str(Finding(use.table, use.privilege, path, why)))
    out.extend(
        f"{stale}: excused in NOT_A_REQUEST_WITH_A_REACH and no write path reaches it any more"
        for stale in sorted(set(explained) - used)
    )
    return out


def describe(found: Sequence[str]) -> str:
    return "\n".join(found) if found else "ok: every console write sets its attribution"
