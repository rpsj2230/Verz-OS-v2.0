"""Every log call under `src/brain` names its event where the Logs screen's capture can read it.

`brain.ops.log_capture.literals_in` keeps an event's name only when the module passes it to a
`log.<method>(...)` call as a string literal, which is how a question typed in lower case is kept
off the Logs screen. A call made through a name bound to a log method, `emit = log.error if ...`,
is not an attribute call, so its literal is never seen and the row is kept as "Name not kept".

Found on the owner's install on 2026-09-29: the Logs screen's only errors were three rows reading
"Error / Name not kept" from `brain.ops.provider_health_store`, which were critical chain-depth
alerts (a tier answering on its third rung). The one alert an operator most needs to recognise was
the one row nobody could name.

Task ids: M27.8.14
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from brain.models.health import AlertLevel, DepthAlert
from brain.models.routing import Tier
from brain.ops.log_capture import LOG_METHODS, LogCapture, LogLevel, install
from brain.ops.provider_health_store import SessionDepthAlerts

#: Pinned far from any wall clock: nothing here is about the present.
AT = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)

SOURCE = Path(__file__).resolve().parents[2] / "src" / "brain"

#: The names a module binds its structlog logger to.
LOGGER_NAMES = frozenset({"log", "logger", "_log"})


@dataclass
class Printed:
    events: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, _logger: Any, _name: str, event_dict: MutableMapping[str, Any]) -> str:
        self.events.append(dict(event_dict))
        return ""


@contextmanager
def capturing() -> Iterator[LogCapture]:
    """The capture in front of a renderer that prints nothing, as the application installs it."""
    original = structlog.get_config()["processors"]
    structlog.configure(
        processors=[structlog.processors.add_log_level, Printed()],
    )
    capture = LogCapture(clock=lambda: AT)
    uninstall = install(capture)
    try:
        yield capture
    finally:
        uninstall()
        structlog.configure(processors=original)


def alert(level: AlertLevel) -> DepthAlert:
    return DepthAlert(
        level=level,
        tier=Tier.MAIN,
        depth=3,
        served_by="a-deployment",
        reason="tier main answered on rung 3 rather than its primary",
    )


def test_a_critical_chain_depth_alert_keeps_its_event_name_on_the_logs_screen() -> None:
    """The row the owner's install showed as "Error / Name not kept" is named.

    Delete this and the alert goes back to being logged through an alias the capture cannot read,
    which is the state the install was found in: the error was on the Logs screen and nothing on
    the row said what it was."""
    with capturing() as capture:
        asyncio.run(
            SessionDepthAlerts(None).raised(alert(AlertLevel.CRITICAL), trace_id="t", at=AT)
        )
        rows = capture.drain()

    assert [(row.level, row.event) for row in rows] == [(LogLevel.ERROR, "models.chain_depth")]


def test_a_warning_chain_depth_alert_keeps_its_event_name_too() -> None:
    """The sibling: the warning half is named as well, at its own level.

    Delete this and a fix that named only the critical branch would pass, leaving the warning,
    which arrives first and more often, unnamed."""
    with capturing() as capture:
        asyncio.run(SessionDepthAlerts(None).raised(alert(AlertLevel.WARNING), trace_id="t", at=AT))
        rows = capture.drain()

    assert [(row.level, row.event) for row in rows] == [(LogLevel.WARNING, "models.chain_depth")]


def aliased_log_methods(tree: ast.AST) -> list[int]:
    """Lines binding a name to a logger's method, which the capture cannot read a call through."""

    def is_log_method(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr in LOG_METHODS
            and isinstance(node.value, ast.Name)
            and node.value.id in LOGGER_NAMES
        )

    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        if any(is_log_method(one) for one in ast.walk(node.value)):
            found.append(node.lineno)
    return found


def test_no_module_calls_a_log_method_through_a_name_the_capture_cannot_read() -> None:
    """The class of the defect, not the one call: nothing under `src/brain` aliases a log method.

    Delete this and the next `emit = log.error if ... else log.warning` ships a row the Logs screen
    cannot name, with every test of the module that wrote it green."""
    offenders = [
        f"{path.relative_to(SOURCE.parent)}:{line}"
        for path in sorted(SOURCE.rglob("*.py"))
        for line in aliased_log_methods(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert offenders == []


def test_the_alias_check_finds_an_alias_and_passes_a_literal_call() -> None:
    """The check's positive and negative case on source written here, so an empty result above is
    a finding about the code and not a check that finds nothing.

    Delete this and a check that never matched would report every module clean."""
    aliased = ast.parse("emit = log.error if critical else log.warning\nemit('x')\n")
    literal = ast.parse("if critical:\n    log.error('x')\nelse:\n    log.warning('x')\n")
    assert aliased_log_methods(aliased) == [1]
    assert aliased_log_methods(literal) == []
