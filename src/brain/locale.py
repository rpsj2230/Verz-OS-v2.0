"""What the domain layer has to carry so a screen can be right for a reader it never met.

Localisation and accessibility look like two subjects and are one defect: **a domain layer
that has already decided how it will be read.** A date formatted `08/09/2026` in a function
that returns a string has decided the reader is British. A status returned as the word
"amber" has decided the reader can see colour. A stream of tokens with no completion event
has decided the reader is watching the text arrive. None of those decisions is visible at the
call site, none of them fails a test, and every one of them is unfixable in the renderer,
because by then the information needed to fix it is gone.

**This repository has no screens.** `brain.console.*` is the domain layer twelve screens read,
and `console/src` is a separate application. So nothing here draws anything, and a leaf that
genuinely needs a renderer is named as such in the report rather than claimed. What is here is
the half a renderer cannot supply for itself: which locales this install offers, what a locale
means, what a date and a figure look like in one, which language a document is in, when a
screen reader should be told something, and whether the colours a client chose can be read.

**The locale is configuration; what a locale means is a product fact.** That line is the whole
of M35's client independence, and it is not the obvious one. `INSTALL_LOCALES` differs between
companies and is therefore a setting read through `brain.install.value_of` like every other.
That `zh-Hans` groups digits in threes and writes the year first does not differ between
companies: it is a fact about a writing system, the same for every client this product will
ever have, and putting it in configuration would mean each install re-deciding what Chinese is.
So `SHIPPED` is a constant and `INSTALL_LOCALES` is a setting, and the test of which side a
value goes on is `brain.install`'s: would this line still be correct on a server belonging to a
company nobody here has met.

**Rejected: a fallback when a translation is missing.** The obvious kindness is for `text` to
return the English string when a language has no entry, so a half-translated build still runs.
It also means the catalogue is never finished, because nothing anywhere reports the gap: the
screen renders, the reader sees English under a Chinese label, and the only person who could
notice is the one who cannot read the other half. `catalogue_gaps` refuses instead, a test runs
it, and a missing translation is therefore a red build rather than a quiet one.

**Rejected: guessing the currency and the time zone.** Both have neutral defaults that are
visibly unset rather than plausibly wrong: `XXX` is the ISO 4217 code meaning no currency, and
UTC is nobody's local time. A figure rendered as `1,234.50 USD` on an install that never chose
a currency is a claim about money that somebody will act on; `1,234.50 XXX` is a support call
on the first afternoon. See `A_VISIBLY_UNSET_UNIT_BEATS_A_PLAUSIBLY_WRONG_ONE`.

**Rejected: announcing a token stream.** An `aria-live` region around text that arrives one
token at a time is announced on every mutation, so a screen reader reads the answer letter by
letter, restarting, for as long as it takes to generate. The fix is not a politeness setting;
it is that the domain layer emits a completion event and the tokens carry no announcement at
all. See `A_LIVE_REGION_ON_A_STREAM_READS_THE_ANSWER_LETTER_BY_LETTER`.

Task ids: M35.1.1.1, M35.1.1.2, M35.1.1.3, M35.1.2.2, M35.2.1.1, M35.2.1.2
Task ids: M35.2.2.3, M35.2.2.4, M35.3.2.2
"""

from __future__ import annotations

import enum
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

from brain.install import value_of

REPO: Final = Path(__file__).resolve().parents[2]

# ------------------------------------------------------------------ written-down reasons
#: Why the locale is a setting and what a locale means is not.
THE_LOCALE_IS_CONFIGURATION_AND_WHAT_A_LOCALE_MEANS_IS_A_PRODUCT_FACT: Final = (
    "Which languages an install offers differs between companies and is therefore a setting. "
    "That Simplified Chinese writes the year first does not differ between companies, and "
    "putting it in configuration would make every install re-decide what Chinese is, with the "
    "install that gets it wrong being the one nobody here can read."
)

#: Why an unambiguous date order is the one a shipped locale gets.
A_DATE_THAT_CAN_BE_READ_TWO_WAYS_WILL_BE: Final = (
    "08/09/2026 is the eighth of September in London and the ninth of August in Chicago, and "
    "nothing on the screen says which. A system whose answers cite dated documents cannot "
    "afford a rendering whose meaning depends on where the reader learnt to read, so an "
    "unqualified language tag gets the year-first order and only a region-qualified tag may "
    "state a different one."
)

#: Why `XXX` and `UTC` rather than a guess.
A_VISIBLY_UNSET_UNIT_BEATS_A_PLAUSIBLY_WRONG_ONE: Final = (
    "A figure rendered in a currency nobody chose is a claim about money somebody will act "
    "on, and a timestamp rendered in a zone nobody chose is wrong for part of every day. "
    "`XXX` is the ISO 4217 code meaning no currency and UTC is nobody's local time, so an "
    "install that has not been configured shows something obviously unset instead of "
    "something that reads correctly and is not."
)

#: Why a missing translation is a build failure rather than a fallback.
A_FALLBACK_TRANSLATION_IS_A_CATALOGUE_THAT_IS_NEVER_FINISHED: Final = (
    "Returning the English string for a missing entry means the screen renders, the gap is "
    "reported nowhere, and the only person who could notice is the one who cannot read the "
    "half that was left. `catalogue_gaps` refuses instead, so an untranslated key is a red "
    "build on the commit that adds it rather than a discovery made by a colleague."
)

#: Why the tokens carry no announcement.
A_LIVE_REGION_ON_A_STREAM_READS_THE_ANSWER_LETTER_BY_LETTER: Final = (
    "An aria-live region is announced on every mutation, and a token stream mutates tens of "
    "times a second, so a screen reader restarts the answer on each token and never finishes "
    "one. No politeness setting fixes that. The tokens carry no announcement at all and the "
    "completion carries exactly one, which is a decision the renderer cannot make for itself "
    "because only the domain layer knows the answer is finished."
)

#: Why silence needs one reassurance and not a progress bar.
SILENCE_IS_INDISTINGUISHABLE_FROM_A_BROKEN_PAGE: Final = (
    "A reader watching tokens arrive knows the system is working. A reader who cannot see "
    "them has nothing between the question and the answer, and after twenty seconds of "
    "nothing the reasonable conclusion is that the page is broken. One reassurance, once, is "
    "the smallest thing that says otherwise; a repeated one is the letter-by-letter problem "
    "wearing a longer interval."
)

#: Why a mixed document is indexed under every language in it.
A_MIXED_DOCUMENT_INDEXED_UNDER_ITS_MAJORITY_LOSES_THE_MINORITY: Final = (
    "A contract whose body is English and whose schedule is Chinese is eighty per cent "
    "English, and labelling it English is how the schedule stops being retrievable in the "
    "language it is written in. Nobody sees that happen: the document is indexed, it is "
    "found by English queries, and the Chinese queries that should have found it return "
    "nothing, which reads as the schedule not existing."
)

#: Why a status carries a name and never a colour.
A_STATUS_THAT_IS_A_COLOUR_HAS_DECIDED_THE_READER_CAN_SEE_IT: Final = (
    "Returning `amber` from the domain layer hands the renderer a colour and no meaning, so "
    "the only accessible rendering left is one that guesses back what amber was supposed to "
    "say. A status is a named value with a message key, the colour is the renderer's, and "
    "the reader who cannot see the colour still gets the word."
)


class LocaleError(Exception):
    """Raised when this install is asked for a locale it does not have."""


# ------------------------------------------------------------------ what a locale is
class Direction(enum.StrEnum):
    """Which way a script runs. Two members, and the second is deferred rather than absent.

    An enum with only `LTR` in it would be a model that cannot express a right-to-left
    locale, so adding one later would be a type change rippling through every caller. Both
    members exist, every locale states one, and no shipped locale is `RTL`. See `DEFERRALS`.
    """

    LTR = "ltr"
    RTL = "rtl"


class DateOrder(enum.StrEnum):
    """The order the three parts of a date are written in.

    `DMY` and `MDY` are both here and neither is shipped, deliberately: they are the two
    orders that render the first twelve days of a month identically, and having them named
    is what lets `ambiguous_orders` be a rule rather than a comment. See
    `A_DATE_THAT_CAN_BE_READ_TWO_WAYS_WILL_BE`.
    """

    YMD = "ymd"
    DMY = "dmy"
    MDY = "mdy"


#: The two orders that produce the same string for the first twelve days of every month.
AMBIGUOUS_ORDERS: Final[frozenset[DateOrder]] = frozenset({DateOrder.DMY, DateOrder.MDY})

#: Language subtags whose scripts run right to left, and the script subtags for the same.
#:
#: A fact about writing systems rather than about a client, so it is a constant here and not
#: a setting. Listed so that asking for one of them is recognised and refused with the
#: deferral's own words, rather than failing as an unknown tag with nothing to explain it.
RIGHT_TO_LEFT_LANGUAGES: Final[frozenset[str]] = frozenset({"ar", "he", "fa", "ur", "yi", "ps"})
RIGHT_TO_LEFT_SCRIPTS: Final[frozenset[str]] = frozenset({"arab", "hebr", "thaa", "nkoo"})

#: The shape of a language tag this module will look at: a language and optional subtags.
TAG_PATTERN: Final = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")

#: The shape of an ISO 4217 currency code.
CURRENCY_PATTERN: Final = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class LocaleRules:
    """Everything about one locale that the domain layer decides rather than the renderer.

    `endonym` is what speakers of the language call it, and it is required for the reason
    `brain.install.Setting.meaning` is: a language switcher listing "Chinese" in English is
    a switcher readable only by somebody who already found the language they wanted.

    `date_marks` is what follows each part of a date, in the order the parts are written.
    A separator field would have been one string and would not express `2026年09月08日`,
    where the marks differ from each other and the last one is not empty.
    """

    tag: str
    endonym: str
    direction: Direction
    date_order: DateOrder
    #: What follows the year, the month and the day, in the order they are written.
    date_marks: tuple[str, str, str]
    decimal_point: str
    group_separator: str
    group_size: int

    def __post_init__(self) -> None:
        if not TAG_PATTERN.match(self.tag):
            msg = f"{self.tag!r} is not a language tag"
            raise LocaleError(msg)
        if not self.endonym.strip():
            msg = f"{self.tag} has no endonym, so a switcher can only name it in another language"
            raise LocaleError(msg)
        # The two separators are checked differently and it is not an oversight. A space is a
        # real group separator, which is how French writes 1 234 567, so only an empty string
        # is refused there. No locale writes a decimal point as a space, so whitespace is
        # refused for that one: `1 5` and `15` are the same figure to a reader and the second
        # is what a blank separator produces.
        if not self.decimal_point.strip():
            msg = (
                f"{self.tag} writes its decimal point as whitespace, so 1234.5 renders as "
                "1234 5, which is a different figure rather than a different appearance"
            )
            raise LocaleError(msg)
        if not self.group_separator:
            msg = f"{self.tag} has no group separator, so 1234567 renders as one run of digits"
            raise LocaleError(msg)
        if self.decimal_point == self.group_separator:
            msg = (
                f"{self.tag} uses {self.decimal_point!r} for both the decimal point and the "
                "group separator, so 1,234 and 1.234 read alike and one of them is wrong"
            )
            raise LocaleError(msg)
        if self.group_size < 2:
            msg = f"{self.tag} groups digits in {self.group_size}s, which separates every digit"
            raise LocaleError(msg)
        # There is no length check on `date_marks`. The annotation is `tuple[str, str, str]`,
        # so mypy proves the length and a runtime guard for it is a branch no test can reach,
        # which is the shape `.scratch/guard_audit.py` exists to find. `format_date` zips it
        # with `strict=True` on the same guarantee.

    @property
    def language(self) -> str:
        """The primary subtag, lower-cased. `zh` for `zh-Hans`."""
        return self.tag.split("-")[0].lower()


#: The locales this product ships a complete catalogue for.
#:
#: Both are year-first, so neither can be misread, and the ambiguity
#: `A_DATE_THAT_CAN_BE_READ_TWO_WAYS_WILL_BE` describes never arises for a shipped locale.
#: A client wanting `en-GB`'s day-first order is asking for a region-qualified tag, which is
#: a locale added here with a complete catalogue rather than a setting they can invent.
SHIPPED: Final[tuple[LocaleRules, ...]] = (
    LocaleRules(
        tag="en",
        endonym="English",
        direction=Direction.LTR,
        date_order=DateOrder.YMD,
        date_marks=("-", "-", ""),
        decimal_point=".",
        group_separator=",",
        group_size=3,
    ),
    LocaleRules(
        tag="zh-Hans",
        endonym="简体中文",
        direction=Direction.LTR,
        date_order=DateOrder.YMD,
        date_marks=("年", "月", "日"),
        decimal_point=".",
        group_separator=",",
        group_size=3,
    ),
)

#: The shipped locales, indexed. Tags are compared case-insensitively because `zh-hans` out
#: of an environment file is the same request as `zh-Hans` and refusing it would be a
#: refusal about typing rather than about language.
BY_TAG: Final[Mapping[str, LocaleRules]] = {one.tag.lower(): one for one in SHIPPED}

#: The tags, spelled as they are shipped. This is what `INSTALL_LOCALES` defaults to, and a
#: test asserts the two agree so that shipping a third catalogue is not a translation nobody
#: is offered.
SHIPPED_TAGS: Final[tuple[str, ...]] = tuple(one.tag for one in SHIPPED)


def is_right_to_left(tag: str) -> bool:
    """Whether a tag names a right-to-left locale, whether or not it is shipped.

    Answered for unshipped tags on purpose: this is what makes asking for Arabic a refusal
    that can name the deferral rather than an unknown-tag error that explains nothing.
    """
    parts = [one.lower() for one in tag.split("-")]
    return parts[0] in RIGHT_TO_LEFT_LANGUAGES or any(
        one in RIGHT_TO_LEFT_SCRIPTS for one in parts[1:]
    )


def rules_for(tag: str) -> LocaleRules:
    """The rules for one shipped locale.

    Raises rather than falling back to the default locale. A fallback here is the same
    mistake `A_FALLBACK_TRANSLATION_IS_A_CATALOGUE_THAT_IS_NEVER_FINISHED` describes, one
    layer down: a screen asking for a locale that is not shipped would render in English and
    nothing would say so.
    """
    found = BY_TAG.get(tag.strip().lower())
    if found is None:
        if is_right_to_left(tag):
            msg = f"{tag!r} is a right-to-left locale. {RIGHT_TO_LEFT.reason}"
            raise LocaleError(msg)
        msg = f"{tag!r} is not a locale this product ships; the shipped ones are {SHIPPED_TAGS}"
        raise LocaleError(msg)
    return found


def enabled_locales(env: Mapping[str, str] | None = None) -> tuple[LocaleRules, ...]:
    """The locales this install offers, most preferred first.

    Read through `brain.install.value_of`, which is the one reader of an installation value
    in this repository: see `brain.ops.independence.second_readers`. An empty list is not a
    state this can return, because an install offering no language is one nobody can read.
    """
    raw = value_of("INSTALL_LOCALES", env)
    tags = [one.strip() for one in raw.split(",") if one.strip()]
    if not tags:
        msg = "INSTALL_LOCALES is set to nothing, and an install offering no language is unusable"
        raise LocaleError(msg)
    found = [rules_for(one) for one in tags]
    seen: set[str] = set()
    ordered: list[LocaleRules] = []
    for one in found:
        if one.tag not in seen:
            seen.add(one.tag)
            ordered.append(one)
    return tuple(ordered)


def default_locale(env: Mapping[str, str] | None = None) -> LocaleRules:
    """What somebody with no stated preference reads. The first entry, and never a constant.

    First rather than English, because the install that most needs a different default is
    the one where English is the second language, and a constant here would mean every
    person on it changes the same setting on their first morning.
    """
    return enabled_locales(env)[0]


def currency(env: Mapping[str, str] | None = None) -> str:
    """The ISO 4217 code figures are rendered in.

    See `A_VISIBLY_UNSET_UNIT_BEATS_A_PLAUSIBLY_WRONG_ONE` for why the neutral default is
    `XXX` and not the currency of wherever this product was written.
    """
    code = value_of("INSTALL_CURRENCY", env).strip().upper()
    if not CURRENCY_PATTERN.match(code):
        msg = f"{code!r} is not an ISO 4217 currency code, which is three upper-case letters"
        raise LocaleError(msg)
    return code


def time_zone(env: Mapping[str, str] | None = None) -> ZoneInfo:
    """The zone a timestamp with no reader attached is rendered in.

    Resolved through `zoneinfo` rather than trusted, so a misspelled zone fails at the point
    somebody set it rather than rendering every timestamp an hour out for a year.
    """
    name = value_of("INSTALL_TIME_ZONE", env).strip()
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError, OSError) as failure:
        # Three types for one mistake: `ZoneInfoNotFoundError` subclasses `KeyError`, a key
        # with a path separator in it raises `ValueError`, and a database that is present
        # but unreadable raises `OSError`. All three mean the same thing to whoever set it.
        msg = f"{name!r} is not a time zone this system can resolve: {failure}"
        raise LocaleError(msg) from failure


# ------------------------------------------------------------------ rendering a value
def format_date(when: date, rules: LocaleRules) -> str:
    """One date, in one locale.

    Takes the rules rather than a tag so a test can hand it a locale that is not shipped,
    which is the only way to prove the ordering is read from the table rather than written
    into the function. That is `brain.ops.starter.starter_gaps`'s argument about its own
    parameters, and the same mutation would have survived without it.
    """
    parts: Mapping[DateOrder, tuple[int, int, int]] = {
        DateOrder.YMD: (when.year, when.month, when.day),
        DateOrder.DMY: (when.day, when.month, when.year),
        DateOrder.MDY: (when.month, when.day, when.year),
    }
    widths: Mapping[DateOrder, tuple[int, int, int]] = {
        DateOrder.YMD: (4, 2, 2),
        DateOrder.DMY: (2, 2, 4),
        DateOrder.MDY: (2, 2, 4),
    }
    ordered = parts[rules.date_order]
    sizes = widths[rules.date_order]
    return "".join(
        f"{value:0{size}d}{mark}"
        for value, size, mark in zip(ordered, sizes, rules.date_marks, strict=True)
    )


def format_timestamp(moment: datetime, rules: LocaleRules, zone: ZoneInfo) -> str:
    """One moment, as a date and a time, in one zone.

    A naive datetime is refused rather than assumed to be UTC, for the reason
    `brain.firstrun.Enrolment` refuses one: a naive value compares and converts wrongly
    against an aware one, and the failure is a rendering that is out by hours on some days
    of the year and right on the rest.
    """
    if moment.tzinfo is None:
        msg = "a naive timestamp has no zone to convert from, and assuming one renders it wrong"
        raise LocaleError(msg)
    local = moment.astimezone(zone)
    return f"{format_date(local.date(), rules)} {local:%H:%M}"


def format_number(value: Decimal, rules: LocaleRules) -> str:
    """One figure, grouped and pointed as the locale writes it.

    The number of decimal places is whatever the `Decimal` carries. Rounding here would be
    this module inventing precision the source system did not state, and a figure that gains
    or loses a place on the way to a screen is a figure somebody will reconcile against and
    fail to.
    """
    sign = "-" if value < 0 else ""
    digits = format(abs(value), "f")
    whole, _, fraction = digits.partition(".")
    grouped: list[str] = []
    while len(whole) > rules.group_size:
        grouped.insert(0, whole[-rules.group_size :])
        whole = whole[: -rules.group_size]
    grouped.insert(0, whole)
    rendered = rules.group_separator.join(grouped)
    if fraction:
        rendered = f"{rendered}{rules.decimal_point}{fraction}"
    return f"{sign}{rendered}"


def format_money(amount: Decimal, rules: LocaleRules, code: str) -> str:
    """One figure and the currency it is in, as a code and never a symbol.

    A symbol is ambiguous across countries. `$` is at least ten currencies, and a figure
    carrying one has told the reader something they can act on and nothing they can check.
    The code is unambiguous everywhere and is the same three letters in every locale, which
    is also why it is not translated.
    """
    if not CURRENCY_PATTERN.match(code):
        msg = f"{code!r} is not an ISO 4217 currency code, which is three upper-case letters"
        raise LocaleError(msg)
    return f"{format_number(amount, rules)} {code}"


# ------------------------------------------------------------------ the message catalogue
#: Every interface string the domain layer names, in every shipped language.
#:
#: Keyed by message and then by tag rather than the other way round, so a key with no Chinese
#: entry is one short row rather than an absence you would have to compare two dictionaries
#: to see. `catalogue_gaps` is what actually reports it; the shape is what makes the report
#: readable when it does.
#:
#: These are the strings the domain layer decides. A label a screen invents for itself is the
#: renderer's, and it is not this module's job to hold every word in the console: it is this
#: module's job to hold the ones a Python function would otherwise return as English prose.
MESSAGES: Final[Mapping[str, Mapping[str, str]]] = {
    "answer.complete": {"en": "Answer complete", "zh-Hans": "回答完成"},
    "answer.working": {"en": "Still working", "zh-Hans": "仍在处理"},
    "answer.failed": {"en": "That did not finish", "zh-Hans": "本次未能完成"},
    "answer.skip_to": {"en": "Skip to answer", "zh-Hans": "跳至回答"},
    "coverage.connected": {"en": "Connected", "zh-Hans": "已连接"},
    "coverage.not_connected": {"en": "Not connected", "zh-Hans": "未连接"},
    "coverage.connected_no_records": {
        "en": "Connected, no records yet",
        "zh-Hans": "已连接但尚无记录",
    },
    # The two kinds of work `brain.adoption.shopping_list` puts in front of a champion.
    "action.authorise_the_source": {
        "en": "Authorise this source so the department can ask about it",
        "zh-Hans": "授权此数据源 使该部门可以就其提问",
    },
    "action.find_out_why_it_is_empty": {
        "en": "Connected but empty: check the scope, or the records are elsewhere",
        "zh-Hans": "已连接但没有内容 请检查范围 或者记录在别处",
    },
    "field.department.label": {"en": "Department", "zh-Hans": "部门"},
    "field.department.required": {"en": "Choose a department", "zh-Hans": "请选择部门"},
    "field.review_date.label": {"en": "Review date", "zh-Hans": "复核日期"},
    "field.review_date.invalid": {
        "en": "Enter a date written like {example}",
        "zh-Hans": "请按 {example} 的写法输入日期",
    },
    # The starter questions `brain.adoption` builds. Templates rather than sentences,
    # because the entity is the client's word for their own records and is never translated.
    "starter.how_many": {"en": "How many {entity} are there?", "zh-Hans": "共有多少{entity}"},
    "starter.most_recent": {
        "en": "Which {entity} is the most recent?",
        "zh-Hans": "最近的{entity}是哪一个",
    },
    "starter.changed_this_week": {
        "en": "Which {entity} changed this week?",
        "zh-Hans": "本周有哪些{entity}发生了变化",
    },
    # The privacy posture `brain.adoption.privacy_posture` reads off the configuration.
    "posture.model_local": {
        "en": "Questions and answers stay on hardware your company runs",
        "zh-Hans": "提问与回答都留在贵公司自有的硬件上",
    },
    "posture.model_hosted": {
        "en": "Questions are sent to a model provider outside your network",
        "zh-Hans": "提问会发送到贵公司网络之外的模型服务商",
    },
    "posture.directory_own": {
        "en": "Sign-in passwords are held by this system's own sign-in server",
        "zh-Hans": "登录密码由本系统自己的登录服务器保管",
    },
    "posture.directory_brokered": {
        "en": "Sign-in goes through your existing directory and no password reaches this system",
        "zh-Hans": "登录通过贵公司现有的目录服务完成 本系统不会接触密码",
    },
    "posture.entitled": {
        "en": "You are shown only what your own permissions already allow",
        "zh-Hans": "只会向你显示你自身权限已允许的内容",
    },
    "visibility.can_reach": {
        "en": "You can ask about {departments}",
        "zh-Hans": "你可以询问 {departments} 的内容",
    },
    "visibility.rule": {
        "en": "Anything else is not listed anywhere, and finding nothing never means a refusal",
        "zh-Hans": "其余内容不会在任何地方列出 找不到结果并不代表被拒绝",
    },
}

#: What a placeholder looks like in a message. `{example}` and nothing cleverer: a format
#: specifier inside a translated string is a second grammar for a translator to get wrong.
PLACEHOLDER: Final = re.compile(r"\{([a-z_]+)\}")


def text(key: str, rules: LocaleRules) -> str:
    """One interface string, in one locale, or a refusal.

    No fallback. See `A_FALLBACK_TRANSLATION_IS_A_CATALOGUE_THAT_IS_NEVER_FINISHED`, and
    note that this can only be strict because `catalogue_gaps` runs in the suite: a missing
    entry is caught on the commit that adds the key, so the strictness never reaches a
    person.
    """
    entries = MESSAGES.get(key)
    if entries is None:
        msg = f"{key!r} is not a message this domain layer names"
        raise LocaleError(msg)
    found = entries.get(rules.tag)
    if found is None:
        msg = f"{key!r} has no {rules.tag} entry, which `catalogue_gaps` should have refused"
        raise LocaleError(msg)
    return found


def catalogue_gaps(
    messages: Mapping[str, Mapping[str, str]] = MESSAGES,
    tags: Sequence[str] = SHIPPED_TAGS,
) -> tuple[str, ...]:
    """Every way the catalogue would render wrongly for somebody.

    Three findings, and the third is the one a reviewer would miss. A missing entry and a
    blank one are both visible on inspection. A placeholder that differs between languages
    is not: `"Enter a date like {example}"` translated without the placeholder renders a
    sentence with the example silently dropped, and translated with `{sample}` instead
    raises `KeyError` inside the renderer at the moment somebody switches language.

    Takes its inputs so the refusals can be tested against a catalogue built to fail, which
    is `brain.ops.starter.starter_gaps`'s argument: a check that can only run against the
    real data has no test for the case it exists to find.
    """
    findings: list[str] = []
    for key in sorted(messages):
        entries = messages[key]
        expected: frozenset[str] | None = None
        for tag in tags:
            value = entries.get(tag)
            if value is None:
                findings.append(f"{key}: no {tag} entry, so a {tag} reader sees nothing or English")
                continue
            if not value.strip():
                findings.append(f"{key}: the {tag} entry is blank, which renders as an empty label")
                continue
            fields = frozenset(PLACEHOLDER.findall(value))
            if expected is None:
                expected = fields
            elif fields != expected:
                findings.append(
                    f"{key}: the {tag} entry has placeholders {sorted(fields)} rather than "
                    f"{sorted(expected)}, so the value is dropped or the renderer raises"
                )
    return tuple(findings)


# ------------------------------------------------------------------ what language a text is
class Script(enum.StrEnum):
    """The scripts this system distinguishes, which is as few as the decisions need.

    `HAN` rather than a member per language, because Simplified and Traditional Chinese,
    Japanese kanji and Korean hanja share the code points and telling them apart needs a
    model rather than a character class. What follows from the script is enough for both
    decisions here: which languages a document is indexed under, and whether the lexical
    index can segment it at all.
    """

    LATIN = "latin"
    HAN = "han"
    OTHER = "other"


def script_of(character: str) -> Script | None:
    """Which script one character belongs to, or None when it says nothing about language.

    Digits, punctuation and whitespace return None, because they are shared by every
    language and counting them would make a page of figures look like whichever script its
    handful of words happened to be in.
    """
    if not character.isalpha():
        return None
    try:
        name = unicodedata.name(character)
    except ValueError:
        return Script.OTHER
    if name.startswith("LATIN "):
        return Script.LATIN
    if name.startswith("CJK "):
        return Script.HAN
    return Script.OTHER


def script_counts(body: str) -> Mapping[Script, int]:
    """How many characters of each script a text holds. Absent scripts are absent, not zero."""
    counts: dict[Script, int] = {}
    for character in body:
        script = script_of(character)
        if script is not None:
            counts[script] = counts.get(script, 0) + 1
    return counts


#: The language each script implies, for the two this product ships catalogues for.
SCRIPT_LANGUAGE: Final[Mapping[Script, str]] = {Script.LATIN: "en", Script.HAN: "zh-Hans"}

#: The share of a document a language needs before the document is indexed under it.
#:
#: A tenth, and the figure is the point rather than the precision. A single Chinese product
#: name in an English page is noise and would make every document bilingual; a schedule, an
#: appendix or a signature block is a section somebody will search for in its own language
#: and is comfortably above a tenth of the page. See
#: `A_MIXED_DOCUMENT_INDEXED_UNDER_ITS_MAJORITY_LOSES_THE_MINORITY`.
SECTION_SHARE: Final = Decimal("0.10")

#: Below this many classifiable characters, a text is not evidence of any language.
#:
#: Twenty, because "OK" and an invoice number are Latin characters that say nothing about
#: what language the document is in, and recording `en` for them would put a wrong fact in
#: the metadata rather than an honest absence. A record saying "unknown" can be improved
#: later; one saying "English" will not be looked at again.
DETECTION_FLOOR: Final = 20


@dataclass(frozen=True)
class DetectedLanguage:
    """What ingest records about the language of one document.

    **`tag` is optional and that is the load-bearing field.** A detector that always returns
    a language turns "we could not tell" into "English", which is a claim nothing later can
    distinguish from a measurement. `None` is what a two-word document gets, and it is a
    state the row can hold.

    `languages` is every language the document is indexed under and is never empty when
    `tag` is set, so a consumer that only wants the dominant one and a consumer that wants
    all of them read two fields rather than re-deriving one from the other.
    """

    #: The dominant language, or None when there was not enough text to say.
    tag: str | None
    #: Every language present above `SECTION_SHARE`, dominant first.
    languages: tuple[str, ...]
    #: How many characters of each script were counted, for anybody re-deriving this later.
    counts: Mapping[Script, int]

    def __post_init__(self) -> None:
        if self.tag is None and self.languages:
            msg = "a document with no detected language cannot be indexed under one"
            raise LocaleError(msg)
        if self.tag is not None and not self.languages:
            msg = f"{self.tag} was detected and the document is indexed under nothing"
            raise LocaleError(msg)
        if self.tag is not None and self.languages[0] != self.tag:
            msg = f"{self.tag} is the dominant language and is not first in {self.languages}"
            raise LocaleError(msg)

    @property
    def mixed(self) -> bool:
        """Whether the document holds a section in a second language."""
        return len(self.languages) > 1


def detect(body: str) -> DetectedLanguage:
    """The language metadata one document is ingested with (M35.1.2.2, M35.1.2.3).

    By script rather than by a model, and the limit is stated rather than hidden: this tells
    Chinese from English and would tell neither from Japanese, because Han characters are
    shared. That is honest for the two languages this product ships catalogues for, and the
    day a third arrives the replacement is a better `detect` behind the same record rather
    than a new field on every row.

    Mixed documents are indexed under every language above `SECTION_SHARE`, not under the
    majority. See `A_MIXED_DOCUMENT_INDEXED_UNDER_ITS_MAJORITY_LOSES_THE_MINORITY`.
    """
    counts = script_counts(body)
    countable = sum(counts.values())
    if countable < DETECTION_FLOOR:
        return DetectedLanguage(tag=None, languages=(), counts=counts)
    ranked = sorted(
        ((script, number) for script, number in counts.items() if script in SCRIPT_LANGUAGE),
        key=lambda pair: (-pair[1], pair[0].value),
    )
    # There is no `if not ranked` short cut here, and the guard audit is why: with nothing
    # ranked the comprehension below yields nothing, `if not present` returns the identical
    # record, and the earlier return was a branch no test could ever tell apart from the
    # later one. A guard whose removal changes nothing is one a reader has to reason about
    # for no return.
    present = tuple(
        SCRIPT_LANGUAGE[script]
        for script, number in ranked
        if Decimal(number) / Decimal(countable) >= SECTION_SHARE
    )
    if not present:
        return DetectedLanguage(tag=None, languages=(), counts=counts)
    return DetectedLanguage(tag=present[0], languages=present, counts=counts)


def lexical_tokens(body: str) -> tuple[str, ...]:
    """The tokens a lexical index has to hold for this text to be findable in it.

    **Han runs are split into overlapping character bigrams and Latin runs are left alone.**
    PostgreSQL's default parser has no Chinese dictionary: a run of Han characters is one
    token, so a query for a two-character term inside a longer phrase matches nothing, and
    the symptom is a Chinese query that returns fewer rows rather than an error. Overlapping
    bigrams are the segmentation that needs no extension: every adjacent pair is a token, so
    any term of two characters or more shares a token with the text that contains it.

    Applied at index time and at query time or not at all. The two must agree for the same
    reason `brain.knowledge.search.SEARCH_CONFIG` is one constant: an index built one way
    and queried another is not used, and the symptom is a slow correct answer that nothing
    fails on.
    """
    tokens: list[str] = []
    han: list[str] = []
    word: list[str] = []

    def flush_han() -> None:
        # No empty-run short cut, for the reason `detect` has none: with `han` empty the
        # length test is false and `range(-1)` is empty, so the early return was a branch
        # with no observable effect. `han.clear()` on an empty list is free.
        if len(han) == 1:
            tokens.append(han[0])
        else:
            tokens.extend(han[index] + han[index + 1] for index in range(len(han) - 1))
        han.clear()

    def flush_word() -> None:
        if word:
            tokens.append("".join(word))
            word.clear()

    for character in body:
        if script_of(character) is Script.HAN:
            flush_word()
            han.append(character)
            continue
        flush_han()
        if character.isalnum():
            word.append(character.lower())
        else:
            flush_word()
    flush_han()
    flush_word()
    return tuple(tokens)


def lexical_blind_to(body: str) -> bool:
    """Whether the configured lexical index cannot segment this text at all.

    True for any text with more than one adjacent Han character, because that is exactly the
    case the default parser turns into a single token. It exists so that a caller combining
    lexical and vector results knows the lexical half contributed nothing, rather than
    reading an empty lexical result as evidence that nothing matched.
    """
    previous = False
    for character in body:
        this = script_of(character) is Script.HAN
        if this and previous:
            return True
        previous = this
    return False


# ------------------------------------------------------------------ what is deferred
class Trigger(enum.StrEnum):
    """The observable that turns a deferred piece of work into due work.

    Members rather than sentences, because "when clients ask for it" is a trigger nobody can
    evaluate and a deferral with one is an abandonment with better manners. Each member names
    something this system can be asked about.
    """

    #: Somebody set `INSTALL_LOCALES` to a locale that runs right to left.
    A_RIGHT_TO_LEFT_LOCALE_IS_ASKED_FOR = "a_right_to_left_locale_is_asked_for"
    #: Approvals sit long enough that the people approving are not looking at the console.
    APPROVALS_WAIT_LONGER_THAN_THE_STATED_HOURS = "approvals_wait_longer_than_the_stated_hours"


@dataclass(frozen=True)
class Deferral:
    """One thing deliberately not built, the observable that makes it due, and why.

    All three are required and all three are checked for being blank, because a deferral
    with an empty trigger is the sentence "later" in a dataclass.
    """

    what: str
    trigger: Trigger
    reason: str

    def __post_init__(self) -> None:
        if not self.what.strip():
            msg = "a deferral has to say what is deferred"
            raise LocaleError(msg)
        if not self.reason.strip():
            msg = f"{self.what} is deferred with no reason, which is an omission with a record"
            raise LocaleError(msg)


#: Right-to-left support, deferred (M35.1.1.3).
RIGHT_TO_LEFT: Final = Deferral(
    what="right-to-left layout",
    trigger=Trigger.A_RIGHT_TO_LEFT_LOCALE_IS_ASKED_FOR,
    reason=(
        "Every locale carries a direction and no shipped locale is right to left, so the "
        "model expresses one and the layout has never rendered one. Building it now would "
        "mean mirroring a console against no Arabic or Hebrew catalogue to check it with, "
        "which is a rendering nobody in this repository could read to find out it was wrong. "
        "Asking for such a locale is refused by name, so the trigger fires as a refusal "
        "somebody reads rather than as a screen that silently runs the wrong way."
    ),
)

#: How long an approval may sit before a push notification is what is missing.
#:
#: Half a working day. An approval is a person waiting, and a queue whose typical wait is
#: four hours means the people approving are not in the console, which is the only thing a
#: push notification changes. Shorter would fire on a busy afternoon; a day would be the
#: threshold that never fires because by then somebody has already complained.
PUSH_IS_DUE_ABOVE_HOURS: Final = 4

#: Push notifications for approvals, deferred (M35.3.2.2).
PUSH_FOR_APPROVALS: Final = Deferral(
    what="push notifications for approvals",
    trigger=Trigger.APPROVALS_WAIT_LONGER_THAN_THE_STATED_HOURS,
    reason=(
        f"Push needs a subscription store, a signing key pair and a delivery path that is "
        f"outside this system's network, which is three new pieces of client infrastructure "
        f"bought to shorten a wait nobody has measured yet. The measurement exists: an "
        f"install whose typical approval wait passes {PUSH_IS_DUE_ABOVE_HOURS} hours has the "
        f"problem push solves, and one that does not has an email that already works."
    ),
)

#: Everything deferred here, so a caller asking what is outstanding reads one list.
DEFERRALS: Final[tuple[Deferral, ...]] = (RIGHT_TO_LEFT, PUSH_FOR_APPROVALS)


def locale_facts(env: Mapping[str, str] | None = None) -> Mapping[Trigger, bool]:
    """The trigger facts this module can answer for itself.

    Only one of the two: whether a right-to-left locale has been asked for is a question
    about configuration and is answerable here. How long approvals wait is a measurement
    somebody else takes, and inventing a value for it would make `triggered` report on a
    figure nothing measured.
    """
    raw = value_of("INSTALL_LOCALES", env)
    asked = [one.strip() for one in raw.split(",") if one.strip()]
    return {
        Trigger.A_RIGHT_TO_LEFT_LOCALE_IS_ASKED_FOR: any(is_right_to_left(one) for one in asked)
    }


def triggered(
    facts: Mapping[Trigger, bool], deferrals: Sequence[Deferral] = DEFERRALS
) -> tuple[Deferral, ...]:
    """The deferred work whose trigger has fired, given what is known.

    A trigger nobody supplied a fact for is not fired and is not an error: the two facts
    come from different places and a caller holding one of them should still get an answer
    about that one, rather than being made to invent the other.
    """
    return tuple(one for one in deferrals if facts.get(one.trigger, False))


# ------------------------------------------------------------------ announcing an answer
class Piece(enum.StrEnum):
    """What arrives on the wire while an answer is being made, from a reader's point of view.

    Deliberately not `brain.gate.streaming.Event`. That enum is the transport's vocabulary
    and this one is the reader's: `FRAGMENT` and `STEP` are different events there and the same
    non-announcement here, and coupling the two would mean a transport change silently
    changing what a screen reader says.
    """

    FRAGMENT = "fragment"
    STEP = "step"
    CITATION = "citation"
    DONE = "done"
    ERROR = "error"


class Politeness(enum.StrEnum):
    """How urgently a live region interrupts. Two values, matching what `aria-live` accepts."""

    POLITE = "polite"
    ASSERTIVE = "assertive"


@dataclass(frozen=True)
class Announcement:
    """One thing a screen reader should say, and how urgently.

    `key` rather than a sentence, so every announcement goes through the catalogue and is
    therefore translated. An announcement built as English prose in the domain layer is a
    string that never reaches `catalogue_gaps` and is read to a Chinese-speaking colleague
    in English.
    """

    key: str
    politeness: Politeness

    def __post_init__(self) -> None:
        if self.key not in MESSAGES:
            msg = f"{self.key!r} is announced and is not in the catalogue, so it is untranslated"
            raise LocaleError(msg)


#: How long a reader may hear nothing before being told the system is still working.
#:
#: Twenty seconds, and it is two of `brain.gate.streaming.HEARTBEAT_SECONDS` rather than a
#: figure of its own: the transport already decided that ten seconds of silence needs a
#: keep-alive, and a reassurance that fired more often than the transport's own idea of
#: silence would be announcing that the connection is open. A test asserts the relation
#: rather than the number, so the two cannot drift.
REASSURANCE_AFTER_SECONDS: Final = 20


def announcements(
    pieces: Sequence[tuple[Piece, float]], *, quiet_after: int = REASSURANCE_AFTER_SECONDS
) -> tuple[Announcement, ...]:
    """What a screen reader should be told, given the stream and when each part arrived.

    Each entry is a piece and the seconds since the question was asked. Three rules, and
    every one of them is a thing a renderer cannot decide alone:

    **No token and no step is ever announced** (M35.2.1.1). See
    `A_LIVE_REGION_ON_A_STREAM_READS_THE_ANSWER_LETTER_BY_LETTER`. A step is excluded
    for a second reason as well: `brain.gate.streaming` argues that a progress label is a
    permission surface, and reading the six labels aloud would make the one reader who
    cannot skim them hear every one.

    **Completion is announced exactly once** (M35.2.1.2), politely, because the reader asked
    for this and is waiting for it: an assertive interruption for an expected event trains
    somebody to switch the region off.

    **Silence gets one reassurance and no more.** See
    `SILENCE_IS_INDISTINGUISHABLE_FROM_A_BROKEN_PAGE`. It is suppressed when the answer
    finished before the threshold, so a fast answer says one thing rather than two.

    A failure is assertive, because it is the one event the reader is not waiting for and
    the one where continuing to wait is wrong.
    """
    if quiet_after <= 0:
        msg = "a reassurance threshold of zero announces silence before there is any"
        raise LocaleError(msg)
    out: list[Announcement] = []
    finished = False
    for piece, at in pieces:
        if finished:
            break
        if piece is Piece.DONE:
            if at >= quiet_after:
                out.append(Announcement(key="answer.working", politeness=Politeness.POLITE))
            out.append(Announcement(key="answer.complete", politeness=Politeness.POLITE))
            finished = True
            continue
        if piece is Piece.ERROR:
            if at >= quiet_after:
                out.append(Announcement(key="answer.working", politeness=Politeness.POLITE))
            out.append(Announcement(key="answer.failed", politeness=Politeness.ASSERTIVE))
            finished = True
    return tuple(out)


# ------------------------------------------------------------------ a form a screen renders
@dataclass(frozen=True)
class FormField:
    """One field a screen collects, with the keys its label and its errors are written under.

    **The label is a message key and never a string**, which is what makes a labelled field
    and a translated field the same piece of work. A renderer given a key has no way to draw
    the field without a label, and `catalogue_gaps` has already proved the key exists in
    every language.

    `errors` maps a machine-readable code to a message key, so an error a validator raises
    is associated with this field by construction rather than by a screen matching text.
    """

    name: str
    label_key: str
    errors: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "a form field with no name cannot be associated with an error"
            raise LocaleError(msg)
        if not self.label_key.strip():
            msg = f"{self.name} has no label key, and an unlabelled input is unusable by name"
            raise LocaleError(msg)


@dataclass(frozen=True)
class FieldError:
    """One validation failure, naming the field it belongs to.

    Two fields and no message text. A screen associates this with its input by `field` and
    renders `key` through the catalogue, which is the whole of "error association": an error
    that arrived as a sentence would be one a screen could only put at the top of the page,
    where a screen reader announces it with nothing saying which input to go back to.
    """

    field: str
    key: str


def form_gaps(fields: Sequence[FormField], errors: Sequence[FieldError] = ()) -> tuple[str, ...]:
    """Every way this form would be unusable to somebody navigating it by name (M35.2.2.4).

    Four findings: a label key that is not in the catalogue, an error key that is not, an
    error naming a field the form does not have, and a field with no error keys at all,
    which is a field that can fail with nothing to say.
    """
    findings: list[str] = []
    known = {one.name for one in fields}
    for one in fields:
        if one.label_key not in MESSAGES:
            findings.append(f"{one.name}: label {one.label_key!r} is not in the catalogue")
        if not one.errors:
            findings.append(
                f"{one.name}: no error keys, so a rejected value has no sentence to show"
            )
        for code, key in sorted(one.errors.items()):
            if key not in MESSAGES:
                findings.append(f"{one.name}.{code}: message {key!r} is not in the catalogue")
    for problem in errors:
        if problem.field not in known:
            findings.append(
                f"{problem.field!r} is not a field on this form, so the error has no input "
                "to be associated with and can only be read out at the top of the page"
            )
        if problem.key not in MESSAGES:
            findings.append(f"{problem.field}: message {problem.key!r} is not in the catalogue")
    return tuple(findings)


# ------------------------------------------------------------------ contrast, in both themes
class Theme(enum.StrEnum):
    """The two grounds the console renders on. Both, always: see `contrast_gaps`."""

    LIGHT = "light"
    DARK = "dark"


#: The smallest contrast ratio body text may have against its ground.
#:
#: 4.5 to 1, which is WCAG 2.2 AA for text below 24px. Taken as the floor for every pair
#: rather than the 3.0 that large text is allowed, because the domain layer does not know
#: what size a renderer will draw a token at, and a floor chosen from the most forgiving
#: case is a floor that passes for text nobody can read.
MINIMUM_CONTRAST: Final = Decimal("4.5")

#: The pairs a reader has to be able to read, as (foreground token, background token).
#:
#: Named pairs rather than every combination, because most combinations are never drawn and
#: a check reporting them would be a check somebody switches off. Each of these is a
#: rendering the console actually performs.
READ_PAIRS: Final[tuple[tuple[str, str], ...]] = (
    ("text", "bg"),
    ("text", "surface"),
    ("text-muted", "bg"),
    ("text-muted", "surface"),
    ("accent", "surface"),
    ("lock-fg", "lock-bg"),
    ("tone-neutral-fg", "tone-neutral-bg"),
    ("tone-positive-fg", "tone-positive-bg"),
    ("tone-caution-fg", "tone-caution-bg"),
    ("tone-critical-fg", "tone-critical-bg"),
)

#: A CSS custom property holding a hex colour.
_DECLARATION = re.compile(r"--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;")

#: A CSS block comment, which is prose and is not a selector. See `theme_palettes`.
_COMMENT = re.compile(r"/\*.*?\*/", re.S)

#: The console's theme tokens, relative to the repository root.
TOKENS_CSS: Final = Path("console") / "src" / "theme" / "tokens.css"


def _luminance(colour: str) -> Decimal:
    """WCAG 2 relative luminance of a hex colour, 0 for black and 1 for white."""
    digits = colour.lstrip("#")
    if len(digits) == 3:
        digits = "".join(one * 2 for one in digits)
    if len(digits) not in {6, 8}:
        msg = f"{colour!r} is not a hex colour this can read"
        raise LocaleError(msg)
    weights = (Decimal("0.2126"), Decimal("0.7152"), Decimal("0.0722"))
    total = Decimal(0)
    for index, weight in enumerate(weights):
        raw = Decimal(int(digits[index * 2 : index * 2 + 2], 16)) / Decimal(255)
        linear = (
            raw / Decimal("12.92")
            if raw <= Decimal("0.03928")
            else ((raw + Decimal("0.055")) / Decimal("1.055")) ** Decimal("2.4")
        )
        total += weight * linear
    return total


def contrast_ratio(foreground: str, background: str) -> Decimal:
    """The WCAG 2 contrast ratio between two hex colours, from 1 to 21.

    Symmetric by construction: the lighter of the two goes on top whichever way round the
    arguments arrive, because a pair that passed one way round and failed the other would
    be a check whose result depended on which token somebody wrote first.
    """
    first, second = _luminance(foreground), _luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + Decimal("0.05")) / (darker + Decimal("0.05"))


def theme_palettes(path: Path) -> Mapping[Theme, Mapping[str, str]]:
    """The light and dark colour tokens, read out of the console's stylesheet.

    Read rather than restated. A copy of the palette in Python would be a second source that
    agrees with the stylesheet on the day it is written and never again, and the failure is
    silent: the check keeps passing about colours nobody renders.

    A declaration belongs to the dark palette when any selector it is nested inside mentions
    dark, which covers both of the file's two dark blocks: the `prefers-color-scheme` media
    query and the explicit `data-theme` selector. That the file has two is deliberate and
    its own comment says they must stay identical, which `contrast_gaps` gets for free by
    reading both into one map.

    **Comments are stripped before anything else, and the first version did not.** The
    stylesheet opens with a paragraph explaining why the dark values are written twice, so
    the word "dark" sat in the text preceding the light `:root`, every light declaration was
    filed under dark, and the light palette came back empty. An empty palette is not a
    failure that announces itself: `contrast_gaps` reported ten missing tokens rather than a
    parse that had gone wrong, which is a finding about the pair list and not about the
    parser.
    """
    text = _COMMENT.sub(" ", path.read_text(encoding="utf-8"))
    palettes: dict[Theme, dict[str, str]] = {Theme.LIGHT: {}, Theme.DARK: {}}
    selectors: list[str] = []
    buffer: list[str] = []
    for character in text:
        if character == "{":
            selectors.append("".join(buffer))
            buffer = []
            continue
        if character == "}":
            if selectors:
                selectors.pop()
            buffer = []
            continue
        buffer.append(character)
        if character != ";":
            continue
        found = _DECLARATION.search("".join(buffer))
        buffer = []
        if found is None:
            continue
        theme = Theme.DARK if any("dark" in one for one in selectors) else Theme.LIGHT
        palettes[theme][found.group(1)] = found.group(2)
    return palettes


def contrast_gaps(
    palettes: Mapping[Theme, Mapping[str, str]],
    pairs: Sequence[tuple[str, str]] = READ_PAIRS,
    minimum: Decimal = MINIMUM_CONTRAST,
) -> tuple[str, ...]:
    """Every pair that is too faint to read, in either theme (M35.2.2.3).

    **Both themes, always, and that is the finding this exists for.** A palette is designed
    in one of them, usually the light one, and the dark values are derived by somebody
    checking that it looks right rather than measuring it. The pair that fails is almost
    always a muted grey on a dark surface, and it fails for the reader who most needs it to
    pass.

    A missing token is reported rather than skipped. A pair naming a token the stylesheet
    does not define is a renaming that left this list behind, and skipping it silently is
    how a check goes green by measuring nothing.
    """
    findings: list[str] = []
    for theme in Theme:
        palette = palettes.get(theme, {})
        for foreground, background in pairs:
            first, second = palette.get(foreground), palette.get(background)
            if first is None or second is None:
                missing = foreground if first is None else background
                findings.append(f"{theme.value}: no token named {missing!r} to measure")
                continue
            ratio = contrast_ratio(first, second)
            if ratio < minimum:
                findings.append(
                    f"{theme.value}: {foreground} on {background} is {ratio:.2f} to 1, "
                    f"below {minimum} to 1"
                )
    return tuple(findings)


#: Why one client colour is held to 3 to 1 and not to 4.5.
#:
#: Not a relaxation, an arithmetic result. `accent_window` computes the band of relative
#: luminance a colour must sit in to clear a ratio against every ground, and at 4.5 to 1 the
#: band for the light ground ends below where the band for the dark ground begins: no colour
#: exists that passes on both. WCAG 2.2's 3 to 1 for non-text contrast is the right floor
#: because the accent is a boundary and a fill rather than body text, the console keeps
#: `--accent-contrast` for text drawn on top of it, and its own `--accent` is two different
#: colours in the two themes for exactly this reason. A test measures both bands rather than
#: quoting this paragraph.
ONE_COLOUR_CANNOT_CLEAR_TEXT_CONTRAST_ON_A_LIGHT_AND_A_DARK_GROUND: Final = (
    "A single client accent has to sit light enough to be seen on the dark ground and dark "
    "enough to be seen on the light one, and at 4.5 to 1 those two requirements do not "
    "overlap. Holding a configured brand colour to a floor no colour can meet would make "
    "the check fail on every install, which is a check somebody switches off in week one."
)

#: The floor a non-text colour is held to. WCAG 2.2 SC 1.4.11.
MINIMUM_NON_TEXT_CONTRAST: Final = Decimal("3")


def accent_window(
    palettes: Mapping[Theme, Mapping[str, str]], minimum: Decimal
) -> tuple[Decimal, Decimal]:
    """The band of relative luminance a single accent must sit in to clear `minimum` on both.

    Returned as a pair rather than a boolean so the caller can see how far apart the two
    requirements are. A band whose floor is above its ceiling is empty, and an empty band is
    the measured statement that no colour can satisfy the ratio against both grounds. See
    `ONE_COLOUR_CANNOT_CLEAR_TEXT_CONTRAST_ON_A_LIGHT_AND_A_DARK_GROUND`.

    A colour clears a ratio against one ground by being lighter than it or by being darker
    than it, so each ground allows two bands rather than one. What makes a single band the
    right answer here is that a real ground rules one of them out: nothing is dark enough to
    stand off `#0f1216`, and nothing is light enough to stand off `#f6f7f9`. A ground where
    both directions remain open is refused rather than approximated, because narrowing to
    one of two bands would return a window that is tighter than the truth and would report
    perfectly usable colours as failures.
    """
    offset = Decimal("0.05")
    floor = Decimal(0)
    ceiling = Decimal(1)
    for theme in Theme:
        ground = palettes.get(theme, {}).get("bg")
        if ground is None:
            continue
        light = _luminance(ground)
        lighter_than = minimum * (light + offset) - offset
        darker_than = (light + offset) / minimum - offset
        if darker_than < 0:
            floor = max(floor, lighter_than)
        elif lighter_than > 1:
            ceiling = min(ceiling, darker_than)
        else:
            msg = (
                f"the {theme.value} ground {ground} admits both a lighter and a darker "
                f"accent at {minimum} to 1, so the answer is two bands and this returns one"
            )
            raise LocaleError(msg)
    return floor, ceiling


def accent_gaps(
    accent: str,
    palettes: Mapping[Theme, Mapping[str, str]],
    minimum: Decimal = MINIMUM_NON_TEXT_CONTRAST,
) -> tuple[str, ...]:
    """Whether the colour this client chose is visible on both grounds (M35.2.2.3).

    `INSTALL_ACCENT_COLOUR` is configuration, so it is a value chosen by somebody holding a
    brand guideline and no contrast meter, on a light screen, for a console that also has a
    dark theme. This is the one contrast check that cannot be settled in the repository,
    because the colour arrives on install day, and it is the one most likely to fail.
    """
    findings: list[str] = []
    for theme in Theme:
        ground = palettes.get(theme, {}).get("bg")
        if ground is None:
            findings.append(f"{theme.value}: no ground colour to measure the accent against")
            continue
        ratio = contrast_ratio(accent, ground)
        if ratio < minimum:
            findings.append(
                f"{theme.value}: the accent {accent} on {ground} is {ratio:.2f} to 1, below "
                f"{minimum} to 1, so a client's brand colour disappears into this theme"
            )
    return tuple(findings)


def presentation_gaps(repo: Path = REPO, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Everything about how this install would be read that is wrong before anybody opens it.

    The catalogue, both themes and the configured accent, in one call, so a sweep or a
    console screen asks one question. Kept out of any hard gate on arrival for the reason
    `brain.ops.connections` keeps `ceiling_costs` out of its breaches: a check that is red
    the day it lands is a check somebody switches off.
    """
    palettes = theme_palettes(repo / TOKENS_CSS)
    return (
        *catalogue_gaps(),
        *contrast_gaps(palettes),
        *accent_gaps(value_of("INSTALL_ACCENT_COLOUR", env), palettes),
    )
