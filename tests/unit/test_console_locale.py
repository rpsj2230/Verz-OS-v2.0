"""What the console is told about language, dates and figures, and that the browser agrees with it.

`brain.console_static.served_locale` sends each enabled language's rules and the console's
catalogue in the document the console reads before it draws. The console writes a date and a figure
with the same rules in TypeScript, so there are two implementations of `brain.locale.format_*`, and
the way to keep two honest is to make one of them write down what it produces. This writes the cases
into `console/tests/fixtures/console-locale.json`, `console/tests/locale.test.ts` reads them back
through the browser's functions, and this file fails when the committed cases are not the ones the
Python functions make today. Regenerate with `WRITE_CONSOLE_LOCALE=1`.

Task ids: M35.1.1.1, M35.1.1.2
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from brain.console_messages import CONSOLE_KEYS, CONSOLE_MESSAGES
from brain.console_static import runtime_config, served_locale
from brain.locale import (
    SHIPPED,
    SHIPPED_TAGS,
    DateOrder,
    Direction,
    LocaleRules,
    catalogue_gaps,
    format_date,
    format_money,
    format_number,
    format_timestamp,
)

FIXTURE = (
    Path(__file__).resolve().parents[2] / "console" / "tests" / "fixtures" / "console-locale.json"
)

#: A locale this product does not ship, so the order and the separators are shown to be read from
#: the rules and not written into the function (`brain.locale.format_date`'s own argument).
DAY_FIRST = LocaleRules(
    tag="xx",
    endonym="Testish",
    direction=Direction.LTR,
    date_order=DateOrder.DMY,
    date_marks=(".", ".", ""),
    decimal_point=",",
    group_separator=" ",
    group_size=3,
)
MONTH_FIRST = LocaleRules(
    tag="yy",
    endonym="Testish too",
    direction=Direction.LTR,
    date_order=DateOrder.MDY,
    date_marks=("/", "/", ""),
    decimal_point=".",
    group_separator=",",
    group_size=2,
)


def _rules(one: LocaleRules) -> dict[str, Any]:
    return {
        "tag": one.tag,
        "endonym": one.endonym,
        "direction": one.direction.value,
        "dateOrder": one.date_order.value,
        "dateMarks": list(one.date_marks),
        "decimalPoint": one.decimal_point,
        "groupSeparator": one.group_separator,
        "groupSize": one.group_size,
    }


def cases() -> list[dict[str, Any]]:
    """Every case both sides must agree on: a rule set, a function, an input and what it writes."""
    made: list[dict[str, Any]] = []
    for one in (*SHIPPED, DAY_FIRST, MONTH_FIRST):
        rules = _rules(one)
        for day in (date(2026, 9, 8), date(2019, 1, 2), date(999, 12, 31)):
            made.append(
                {
                    "kind": "date",
                    "rules": rules,
                    "input": {"year": day.year, "month": day.month, "day": day.day},
                    "expected": format_date(day, one),
                }
            )
        for iso, zone in (
            ("2026-09-08T06:30:00Z", "UTC"),
            ("2026-09-08T23:59:00Z", "Asia/Singapore"),
            ("2026-01-15T03:05:00Z", "America/New_York"),
            ("2026-07-15T03:05:00Z", "America/New_York"),
            ("2026-03-29T00:30:00Z", "Europe/London"),
        ):
            moment = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            made.append(
                {
                    "kind": "timestamp",
                    "rules": rules,
                    "input": {"iso": iso, "zone": zone},
                    "expected": format_timestamp(moment, one, ZoneInfo(zone)),
                }
            )
        for number in (
            "0",
            "12",
            "999",
            "1000",
            "1234",
            "1234567.89",
            "-1234.5",
            "1234567.890",
            "0.5",
        ):
            made.append(
                {
                    "kind": "number",
                    "rules": rules,
                    "input": {"value": number},
                    "expected": format_number(Decimal(number), one),
                }
            )
        for code in ("USD", "SGD", "XXX"):
            made.append(
                {
                    "kind": "money",
                    "rules": rules,
                    "input": {"value": "1234567.89", "code": code},
                    "expected": format_money(Decimal("1234567.89"), one, code),
                }
            )
    return made


def offered(served: dict[str, object]) -> list[dict[str, Any]]:
    """The languages in a served document, typed for the assertions below."""
    return cast(
        "list[dict[str, Any]]", served["locales"]
    )  # a library-boundary read of a JSON shape


def document() -> dict[str, Any]:
    """What the fixture holds: the cases, and the document the console reads at its defaults."""
    return {"cases": cases(), "served": served_locale({})}


def test_the_console_catalogue_has_every_language_for_every_key() -> None:
    """The console's sentences pass the same gap check the rest of the catalogue does: an entry in
    every shipped language, none blank, and the same placeholders in each. Delete this and a key
    added without its Chinese is a screen showing English under a Chinese switch, found by the one
    colleague who cannot read it."""
    assert catalogue_gaps(CONSOLE_MESSAGES) == ()
    assert all(set(entries) == set(SHIPPED_TAGS) for entries in CONSOLE_MESSAGES.values())
    assert len(CONSOLE_KEYS) == len(set(CONSOLE_KEYS)) > 0


def test_the_document_offers_every_enabled_language_with_all_of_the_console_s_words() -> None:
    """Two shipped languages, English first, each with the same keys and its own rules. Delete this
    and the switch is drawn with one language missing, or with a language that has some of the
    words."""
    served = served_locale({})

    assert served["default"] == "en"
    assert [one["tag"] for one in offered(served)] == ["en", "zh-Hans"]
    assert served["timeZone"] == "UTC" and served["currency"] == "XXX"
    for one in offered(served):
        assert set(one["messages"]) == set(CONSOLE_KEYS)
        assert all(text.strip() for text in one["messages"].values())
    chinese = offered(served)[1]
    assert chinese["endonym"] == "简体中文"
    assert chinese["dateMarks"] == ["年", "月", "日"]
    # Each language carries its own words and not the first language's.
    key = CONSOLE_KEYS[0]
    assert chinese["messages"][key] == CONSOLE_MESSAGES[key]["zh-Hans"]
    assert offered(served)[0]["messages"][key] == CONSOLE_MESSAGES[key]["en"]
    assert chinese["messages"][key] != CONSOLE_MESSAGES[key]["en"]


def test_the_first_enabled_language_is_the_default_and_the_install_s_zone_and_currency_travel() -> (
    None
):
    """`INSTALL_LOCALES` puts Chinese first, `INSTALL_TIME_ZONE` and `INSTALL_CURRENCY` are set.
    Delete this and the default is always English, or the console writes every figure in a currency
    nobody chose."""
    served = served_locale(
        {
            "INSTALL_LOCALES": "zh-Hans,en",
            "INSTALL_TIME_ZONE": "Asia/Singapore",
            "INSTALL_CURRENCY": "sgd",
        }
    )

    assert served["default"] == "zh-Hans"
    assert [one["tag"] for one in offered(served)] == ["zh-Hans", "en"]
    assert served["timeZone"] == "Asia/Singapore"
    assert served["currency"] == "SGD"


@pytest.mark.parametrize(
    "env",
    [
        {"INSTALL_LOCALES": "ar"},
        {"INSTALL_LOCALES": "fr"},
    ],
)
def test_a_setting_that_does_not_resolve_leaves_the_console_in_english_and_not_blank(
    env: dict[str, str],
) -> None:
    """A right-to-left language and one the product does not ship are each served as
    English only, and the Settings screen is where they are refused and named. Delete this and a
    mistyped language blanks the console of the person who needs it to mend the setting."""
    served = served_locale(env)

    assert served["default"] == "en"
    assert [one["tag"] for one in offered(served)] == ["en"]


def test_a_time_zone_that_does_not_resolve_is_served_as_utc_and_a_currency_as_unset() -> None:
    """Delete this and a misspelled zone raises while the document is served, which is a blank
    console, or an hour out on every timestamp for a year."""
    served = served_locale({"INSTALL_TIME_ZONE": "Not/AZone", "INSTALL_CURRENCY": "dollars"})

    assert served["timeZone"] == "UTC"
    assert served["currency"] == "XXX"


def test_the_served_document_carries_the_locale_beside_the_accent_and_the_brand() -> None:
    """The console reads one blocking document, so the locale has to be in it. Delete this and the
    rules are served nowhere the console looks."""
    text = runtime_config({})
    body = json.loads(text[text.index("(") + 1 : text.rindex(")")])

    assert {"accent", "brand", "locale"} <= set(body)
    assert body["locale"]["default"] == "en"


def test_the_cases_the_browser_is_held_to_are_the_ones_the_python_functions_make() -> None:
    """The committed fixture equals what `brain.locale.format_*` writes today. Delete this and the
    browser's formatters can be held to cases that no longer describe the product, and a date
    written two ways on one page is found by a reader. `WRITE_CONSOLE_LOCALE=1` rewrites it."""
    made = json.dumps(document(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if os.environ.get("WRITE_CONSOLE_LOCALE"):
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(made, encoding="utf-8", newline="\n")
    assert FIXTURE.read_text(encoding="utf-8") == made


def test_the_cases_cover_both_orders_a_zone_with_daylight_saving_and_an_unset_currency() -> None:
    """The cases are not a list of the happy path. Delete this and a fixture that holds only year
    first dates and UTC passes the browser's formatters for a bug in either."""
    made = cases()

    assert {one["rules"]["dateOrder"] for one in made if one["kind"] == "date"} == {
        "ymd",
        "dmy",
        "mdy",
    }
    zones = {one["input"]["zone"] for one in made if one["kind"] == "timestamp"}
    assert {"UTC", "Asia/Singapore", "America/New_York", "Europe/London"} <= zones
    assert {one["input"]["code"] for one in made if one["kind"] == "money"} >= {"USD", "XXX"}
    january, july = (
        one["expected"]
        for one in made
        if one["kind"] == "timestamp"
        and one["rules"]["tag"] == "en"
        and one["input"]["zone"] == "America/New_York"
    )
    assert january.endswith("22:05") and july.endswith("23:05")
