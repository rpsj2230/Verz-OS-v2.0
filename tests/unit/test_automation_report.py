"""What the host says of the running canvas, parsed, kept for the release and judged.

The step (`ops/deploy/overlays/automation.observe.sh`, run against a stub in
`tests/unit/test_automation_observe.py`) writes `kind|value` lines; `brain.ops.automation_report`
reads them, and `gaps` says which way the running canvas breaks the boundary. Every gap is tested by
breaking one fact of a canvas that has none, and the policy is held against the compose file it
judges, so a rule that would fail the real canvas, or pass a changed one, is found here.

Task ids: M32.6.1.2
"""

from __future__ import annotations

import io
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.ops import automation, automation_report
from brain.ops.automation import EGRESS_ALLOWLIST
from brain.ops.automation_report import (
    CANVAS_OWN_SECRETS,
    REFUSED_STATUS,
    CanvasFacts,
    FactsError,
    Gap,
    facts_from,
    facts_in,
    foreign_credential_names,
    gaps,
    observation,
)

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.automation.yml"
SCRIPT = REPO / "ops" / "deploy" / "overlays" / "automation.observe.sh"

#: Far outside any plausible wall clock, because nothing here is about the present.
RELEASE = "a-release-far-from-any-clock"


def canvas_environment() -> dict[str, str]:
    """The canvas's own environment as its compose file declares it."""
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    declared: dict[str, str] = loaded["services"]["activepieces"]["environment"]
    return declared


def sound() -> CanvasFacts:
    """A canvas that keeps the boundary: its own networks, the compose file's own variables, no
    default route, the product's allowlist and a refusal for a host on no list."""
    return CanvasFacts(
        networks=("u-overlays_automation", "brain-tool-api"),
        proxy_networks=("u-overlays_automation", "u-overlays_egress"),
        env_names=tuple(sorted({*canvas_environment(), "NODE_VERSION", "PATH", "HOSTNAME"})),
        connection_strings=0,
        default_routes=0,
        allowlist=tuple(sorted(EGRESS_ALLOWLIST)),
        probe=f"HTTP/1.1 {REFUSED_STATUS} Forbidden",
    )


def test_a_canvas_that_keeps_the_boundary_has_no_gap() -> None:
    """The positive case, over the compose file's own variable names. Delete this and a `gaps` that
    reports something for every canvas passes every refusal below, and a rule that would fail the
    real canvas is found on an owner's server."""
    assert gaps(sound()) == ()


def test_the_three_secrets_the_canvas_is_given_are_the_compose_file_s_own() -> None:
    """The names exempted from the credential rule against the variables the file fills from the
    canvas's own `AUTOMATION_` values. Delete this and a fourth secret can be added to the file and
    pass unseen, or an exemption outlive the variable it was for."""
    own = {
        name
        for name, value in canvas_environment().items()
        if isinstance(value, str)
        and value.startswith("${AUTOMATION_")
        and automation.is_credential_name(name)
    }
    assert own == CANVAS_OWN_SECRETS


def test_the_compose_file_s_application_wide_secret_is_not_among_the_canvas_s_variables() -> None:
    """Delete this and the rule 'no variable the application holds' is never held against the file
    it is written for."""
    names = set(canvas_environment())
    assert not {
        name for name in names if name.startswith(automation_report.APPLICATION_NAME_PREFIXES)
    }
    assert "POSTGRES_PASSWORD" not in names
    assert not {name for name in names if "DATABASE_URL" in name}


@pytest.mark.parametrize(
    ("broken", "gap"),
    [
        ({"env_names": ("AP_JWT_SECRET", "OPENAI_API_KEY")}, Gap.FOREIGN_CREDENTIAL),
        ({"env_names": ("POSTGRES_PASSWORD",)}, Gap.FOREIGN_CREDENTIAL),
        ({"connection_strings": 1}, Gap.CONNECTION_STRING),
        ({"connection_strings": None}, Gap.CONNECTION_STRING),
        ({"env_names": ("BRAIN_ANYTHING",)}, Gap.APPLICATION_VARIABLE),
        ({"env_names": ("DATABASE_HOST",)}, Gap.APPLICATION_VARIABLE),
        ({"networks": ("u-overlays_automation", "u_default")}, Gap.CANVAS_NETWORKS),
        ({"networks": ("brain-tool-api",)}, Gap.CANVAS_NETWORKS),
        ({"networks": ()}, Gap.CANVAS_NETWORKS),
        ({"proxy_networks": ("u-overlays_automation", "u_default")}, Gap.PROXY_NETWORKS),
        ({"proxy_networks": ()}, Gap.PROXY_NETWORKS),
        ({"default_routes": 1}, Gap.DEFAULT_ROUTE),
        ({"default_routes": None}, Gap.ROUTES_UNKNOWN),
        ({"allowlist": (*sorted(EGRESS_ALLOWLIST), "extra.example")}, Gap.ALLOWLIST),
        ({"allowlist": tuple(sorted(EGRESS_ALLOWLIST))[1:]}, Gap.ALLOWLIST),
        ({"allowlist": ()}, Gap.ALLOWLIST),
        ({"probe": "HTTP/1.1 200 Connection established"}, Gap.NOT_REFUSED),
        ({"probe": ""}, Gap.NOT_REFUSED),
        ({"probe": "garbage"}, Gap.NOT_REFUSED),
    ],
)
def test_each_way_the_canvas_breaks_the_boundary_is_its_own_gap(
    broken: dict[str, Any], gap: Gap
) -> None:
    """Twenty single breaks of a sound canvas, each reported as exactly the gap it is, including
    the facts the step could not read. Delete this and a canvas holding the vault's token, one on
    the application's network or one with a default route reads as sound."""
    found = gaps(replace(sound(), **broken))
    assert gap in found
    assert len(found) == 1, found


def test_the_vault_s_token_is_both_a_credential_and_a_variable_of_the_application_s() -> None:
    """The most dangerous variable of all, which both rules catch. Delete this and one of the two
    rules can be removed with every other test still green, because each is also caught by
    something else for the other names."""
    found = gaps(replace(sound(), env_names=("AP_JWT_SECRET", "VAULT_TOKEN")))
    assert set(found) == {Gap.FOREIGN_CREDENTIAL, Gap.APPLICATION_VARIABLE}


def test_a_name_that_would_be_the_application_s_is_named_for_the_log_and_a_sound_one_is_not() -> (
    None
):
    """Delete this and the worker's log cannot say which variable to remove, so a failing row is a
    sentence the owner cannot act on."""
    assert foreign_credential_names(sound()) == ()
    broken = replace(sound(), env_names=("AP_JWT_SECRET", "BRAIN_X", "OPENAI_API_KEY", "PATH"))
    assert foreign_credential_names(broken) == ("BRAIN_X", "OPENAI_API_KEY")


def test_an_allowlist_is_judged_as_a_set_and_not_by_its_order() -> None:
    """The same hosts the other way round. Delete this and a proxy that lists them in another order
    fails for a reason that is not a difference."""
    shuffled = replace(sound(), allowlist=tuple(sorted(EGRESS_ALLOWLIST, reverse=True)))
    assert gaps(shuffled) == ()


# ------------------------------------------------------------------------- the lines
GOOD_LINES = (
    "net|u-overlays_automation",
    "net|brain-tool-api",
    "proxynet|u-overlays_automation",
    "proxynet|u-overlays_egress",
    "env|AP_JWT_SECRET",
    "env|PATH",
    "connstr|0",
    "routes|0",
    *(f"allow|{one}" for one in sorted(EGRESS_ALLOWLIST)),
    "probe|HTTP/1.1 403 Forbidden",
)


def test_the_step_s_lines_are_read_as_the_facts_they_say() -> None:
    """Delete this and the parser and the step disagree on a kind, and every canvas is reported
    with a fact it never had."""
    got = facts_from(GOOD_LINES)
    assert got.networks == ("brain-tool-api", "u-overlays_automation")
    assert got.proxy_networks == ("u-overlays_automation", "u-overlays_egress")
    assert got.env_names == ("AP_JWT_SECRET", "PATH")
    assert (got.connection_strings, got.default_routes) == (0, 0)
    assert got.allowlist == tuple(sorted(EGRESS_ALLOWLIST))
    assert got.probe == "HTTP/1.1 403 Forbidden"


def test_a_fact_the_step_could_not_read_is_none_and_never_zero() -> None:
    """`routes|unknown` and a missing line. Delete this and an unread routing table reads as zero
    default routes, which is the answer the check hopes for."""
    unread = facts_from(["routes|unknown", "connstr|unknown", "net|x_automation"])
    assert unread.default_routes is None
    assert unread.connection_strings is None
    assert facts_from([]).default_routes is None
    assert Gap.ROUTES_UNKNOWN in gaps(unread)


@pytest.mark.parametrize(
    "line",
    ["env|AP_JWT_SECRET=hunter2", "env|", "env|has space", "no separator", "mystery|x", "env|a|b"],
)
def test_a_line_that_could_carry_a_value_or_that_nothing_reads_is_refused(line: str) -> None:
    """Delete this and a report that somehow carried `NAME=value` is kept in a row anybody who can
    read settings can read."""
    with pytest.raises(FactsError):
        facts_from([line])


def test_a_stored_row_is_read_back_only_for_the_release_that_wrote_it_and_in_its_own_shape() -> (
    None
):
    """The round trip, another release, and values of the wrong shape (including a boolean where a
    count belongs). Delete this and a canvas is judged on what an older release saw, or on a row
    somebody wrote by hand."""
    facts = sound()
    value = observation(facts, commit=RELEASE)
    assert facts_in(value, commit=RELEASE) == facts
    assert facts_in(value, commit="another") is None
    for bad in (None, "text", [], {}, {**value, "networks": "not a list"}, {**value, "probe": 3}):
        assert facts_in(bad, commit=RELEASE) is None
    assert facts_in({**value, "default_routes": True}, commit=RELEASE) == replace(
        facts, default_routes=None
    )


# --------------------------------------------------------------- held against the files
def test_the_step_counts_the_connection_strings_the_policy_names() -> None:
    """The schemes the script's pattern counts, parsed out of it, against the product's own list.
    Delete this and a scheme added to `credential_leaks` is one the host never counts."""
    script = SCRIPT.read_text(encoding="utf-8")
    pattern = re.search(r"grep -ciE '[^=]*=\(([^)]*)\)://'", script)
    assert pattern is not None
    counted = {one.replace("\\+", "+") for one in pattern.group(1).split("|")}
    declared = {one.removesuffix("://") for one in automation._CONNECTION_SCHEMES}
    assert counted == declared


def test_the_allowlist_the_report_expects_is_the_one_the_proxy_file_declares() -> None:
    """Hosts read out of `ops/automation/egress.conf` the way the step reads them out of the
    running proxy. Delete this and the check compares the running proxy with a list the file does
    not hold."""
    conf = (REPO / "ops" / "automation" / "egress.conf").read_text(encoding="utf-8")
    from_the_file = re.findall(r"^acl allowed_sources dstdomain (\S+)$", conf, re.MULTILINE)
    assert sorted(from_the_file) == sorted(EGRESS_ALLOWLIST)


def test_the_probe_names_a_host_that_can_never_resolve_and_is_on_no_list() -> None:
    """Delete this and the probe is changed to a real name, and every deploy opens a connection to
    somebody's server to prove a refusal."""
    script = SCRIPT.read_text(encoding="utf-8")
    host = re.search(r"CONNECT (\S+):443", script)
    assert host is not None
    assert host.group(1).endswith(".invalid")
    assert host.group(1) not in EGRESS_ALLOWLIST


# --------------------------------------------------------------------------- the hand
def keeping(monkeypatch: pytest.MonkeyPatch, lines: str) -> list[dict[str, object]]:
    kept: list[dict[str, object]] = []
    monkeypatch.setattr(automation_report, "_keep", kept.append)
    monkeypatch.setattr("sys.stdin", io.StringIO(lines))
    return kept


def test_the_hand_keeps_what_it_is_given_for_this_release_and_says_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command as the deploy step runs it. Delete this and a report is parsed and never kept,
    so the checks say nothing was reported on a canvas that is running."""
    kept = keeping(monkeypatch, "\n".join(GOOD_LINES) + "\n")
    assert automation_report.main(["keep"]) == 0
    assert len(kept) == 1
    assert kept[0]["probe"] == "HTTP/1.1 403 Forbidden"
    assert capsys.readouterr().out.startswith("SAY the canvas's facts are kept")


def test_a_report_that_cannot_be_read_or_kept_is_said_and_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A line carrying a value, and a database that refuses. Delete this and a failed report exits
    zero, so the step believes the checks have something to read, and a value that reached the
    command is printed back."""
    kept = keeping(monkeypatch, "env|AP_JWT_SECRET=hunter2\n")
    assert automation_report.main(["keep"]) == 1
    assert kept == []
    said = capsys.readouterr()
    assert "hunter2" not in said.out + said.err

    def refuse(value: dict[str, object]) -> None:
        raise OSError("no database")

    monkeypatch.setattr(automation_report, "_keep", refuse)
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(GOOD_LINES) + "\n"))
    assert automation_report.main(["keep"]) == 1
    assert "not kept" in capsys.readouterr().out
    assert automation_report.main(["something else"]) == 64
