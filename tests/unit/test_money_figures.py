"""Every money figure the API returns carries the install's currency, read off the API's own
document rather than off a list of routes somebody remembered.

The rule is `brain.report_routes.A_FIGURE_SAYS_ITS_CURRENCY_AND_ITS_CLOCK`: a cost with no
currency is read in whichever currency the reader assumes. It was kept by the reports and the
Overview and missed by four answers, measured on 2026-10-06 by walking every 2xx response schema
in the application's OpenAPI document: an agent's budget as it is set, an agent's headline spend,
a person's own allowances on My workspace and a provider's figures. Each carried minor units with
nothing saying which currency they were in. A list of the routes that carry money would have been
the fifth place to forget one, so the test walks the document the application serves.

**A money figure is a field whose name ends in `_minor` or holds `_minor_`**, which is how every
amount in this API is named: minor units of the install's currency, never a float. **Its currency
may be on the same object or on any object above it**, because a report's lines share the
report's one currency and repeating it per line would let two lines disagree.

Task ids: M27.15.33
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from brain.locale import NO_CURRENCY_CODE, currency_or_unset


def _refs(node: Any) -> Iterator[str]:
    """Every schema name a fragment of the document refers to."""
    if isinstance(node, dict):
        if "$ref" in node:
            yield str(node["$ref"]).rsplit("/", 1)[-1]
        for value in node.values():
            yield from _refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _refs(value)


def _is_money(name: str) -> bool:
    return name.endswith("_minor") or "_minor_" in name


def money_without_currency(spec: Mapping[str, Any]) -> dict[str, list[str]]:
    """Each response schema with a money figure and no `currency` on it or above it, by name."""
    schemas: Mapping[str, Any] = spec.get("components", {}).get("schemas", {})
    found: dict[str, list[str]] = {}
    seen: set[tuple[str, bool]] = set()

    def walk(name: str, carried: bool) -> None:
        if (name, carried) in seen:
            return
        seen.add((name, carried))
        properties: Mapping[str, Any] = schemas[name].get("properties", {})
        here = carried or "currency" in properties
        money = sorted(one for one in properties if _is_money(one))
        if money and not here:
            found[name] = money
        for value in properties.values():
            for inner in _refs(value):
                walk(inner, here)

    for operations in spec.get("paths", {}).values():
        for operation in operations.values():
            for status, response in operation.get("responses", {}).items():
                if str(status).startswith("2"):
                    for name in _refs(response):
                        walk(name, carried=False)
    return found


def _spec(view: Mapping[str, Any], line: Mapping[str, Any]) -> dict[str, Any]:
    """A document with one route answering `view`, whose `lines` are `line` objects."""
    return {
        "paths": {
            "/x": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/View"}
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "View": {
                    "properties": {
                        **view,
                        "lines": {"type": "array", "items": {"$ref": "#/components/schemas/Line"}},
                    }
                },
                "Line": {"properties": dict(line)},
            }
        },
    }


def test_every_money_figure_the_api_returns_carries_the_install_currency() -> None:
    """**The property, over the document the application serves.** Delete this and a route can
    answer a ceiling or a spend in minor units of nothing, which a reader in one country reads in
    their own currency; four did until 2026-10-06."""
    from brain.app import create_app

    assert money_without_currency(create_app().openapi()) == {}


def test_a_money_figure_with_no_currency_on_it_or_above_it_is_found() -> None:
    """The walk finds a figure with no currency anywhere above it, and finds a currency carried
    by the object above. Delete this and a walk that never descends, or never finds anything,
    passes the property test above on every document."""
    integer = {"type": "integer"}
    assert money_without_currency(_spec({}, {"cost_minor": integer})) == {"Line": ["cost_minor"]}
    assert money_without_currency(_spec({"total_minor": integer}, {})) == {"View": ["total_minor"]}
    carried = _spec(
        {"currency": {"type": "string"}, "total_minor": integer}, {"cost_minor": integer}
    )
    assert money_without_currency(carried) == {}
    beside = _spec({}, {"currency": {"type": "string"}, "input_minor_per_million": integer})
    assert money_without_currency(beside) == {}


@pytest.mark.parametrize(
    ("setting", "sent"),
    [("SGD", "SGD"), ("eur", "EUR"), ("", NO_CURRENCY_CODE), ("dollars", NO_CURRENCY_CODE)],
)
def test_a_figure_is_sent_in_the_installs_currency_or_visibly_in_none(
    setting: str, sent: str
) -> None:
    """The currency a figure carries is the install's, and a setting that does not resolve is
    sent as `XXX` rather than refusing the reader or guessing. Delete this and a misspelled
    setting either fails every budget screen or labels every figure with a currency nobody
    chose."""
    assert currency_or_unset({"INSTALL_CURRENCY": setting}) == sent


def test_the_unset_code_is_the_one_the_reports_already_send() -> None:
    """The four answers that gained a currency send the same unset code the reports send. Delete
    this and an install with no currency shows `XXX` on Spend and something else on My
    workspace."""
    from brain.models.pricing import NO_CURRENCY
    from brain.report_routes import UNSET_CURRENCY

    assert NO_CURRENCY_CODE == UNSET_CURRENCY == NO_CURRENCY


def test_a_providers_figures_carry_the_currency_their_cost_would_be_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Models screen's provider figures carry the install's currency beside a cost they name
    as not recorded. Delete this and the field can be filled with anything by the one builder that
    fills it, with the property test still green, because the schema keeps the field."""
    from brain.provider_routes import stats_view

    monkeypatch.setenv("INSTALL_CURRENCY", "SGD")
    shown = stats_view("anthropic", answered=3, cost_recorded=True)
    assert shown.currency == "SGD"
    assert shown.cost_minor is None
