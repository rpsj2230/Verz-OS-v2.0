"""How every console list pages, searches, filters and sorts, and why each of the four happens after
the reach has been decided and never before.

`docs/admin-console.md` asks that long lists page, search, filter and sort. Before this module every
console list route loaded a bounded set, handed it to the module that decides what the reader may
see, and answered what survived with a flag saying the load came back full. None of them took a
cursor, a search, a filter or an order, and the pages that narrowed anything did it in the browser
over one answer, saying so. This is the one convention those routes now share, written once so that
a route cannot acquire a subtly different one by copying an older signature.

**The rows a listing narrows are the rows the reader would have been sent.** A route loads, decides
and projects exactly as it did, and hands the projected rows here. Search, filter, order and the
cursor are applied to those and to nothing else. Two consequences, and both are the point:

- A search or a filter cannot match a field the reader was not shown. Matching on the stored record
  instead would let somebody learn a withheld value one guess at a time, by asking whether a row
  comes back. See `A_SEARCH_READS_ONLY_WHAT_THE_ROW_SHOWS`.
- `next_cursor` is present exactly when at least one further row the reader may see matches. It is
  never computed over the load, so it cannot say that rows exist which the decision withheld.

**The load is never narrowed by the query.** `brain.estate_routes.
A_FILTER_ON_THE_SERVER_TURNS_A_TRUNCATION_FLAG_INTO_A_COUNT` is right, and it is why the library
refused a server-side filter: a load narrowed by a department the caller typed, answered with "the
load came back full", says that department holds at least a load of documents. This convention does
not narrow the load at all. The route loads to its own constant ceiling, and `truncated` stays a
fact about the install that is identical for every search, filter, order and cursor. Rejected: a
filter pushed into the SQL for speed. It is faster and it turns the flag back into the oracle.
See `THE_LOAD_IS_NEVER_NARROWED_BY_THE_QUERY`.

**A cursor is a position, never a permission.** It carries the order key and the row key of the last
row the reader was shown, and a digest binding it to that reader, that listing and that exact
question. Every page is decided again from the session's own reach before the cursor is read, so a
cursor forged by hand, or copied from another reader, can at most start a walk somewhere inside
the presenter's own rows. The binding is what makes a copied one refused rather than quietly
reinterpreted under a different order or a different reader: a cursor minted for one person and
presented by another is the 422 a malformed cursor gets, identically. Rejected: an HMAC. There is
no signing key on an install to sign with, a key minted per process would refuse every cursor
behind a second replica, and a signature would add nothing the re-decision does not already
guarantee. See `A_CURSOR_IS_A_POSITION_AND_NEVER_A_PERMISSION`.

**Offset was rejected for `brain.api`'s reason.** A page number re-reads and re-filters on every
page, so a row can appear twice or vanish when a grant changes mid-scroll, and "page 3" is the
shortest route back to a count.

**Each list declares what it may be ordered and narrowed by, and the declaration is the API
document.** `Listing.query` builds the route's dependency with a `sort` pattern and a `filter`
pattern naming exactly the listing's columns, so the generated document says which columns a
console may offer, and anything else is refused by the declaration before the route runs, the same
for every caller. A filter term is `brain.api_routes`' own grammar: `column:value`, an equality,
repeated, with two terms on one column meaning both.

**A filter offers only values the reader was shown.** That half lives in the console
(`console/src/components/listing.ts`): the choices are the values on rows already drawn, so no
dropdown can name a department, a person or a state the reader was never shown a row for.

**Several rows are acted on only as several single acts.** `each_of` runs one act per key, in the
order asked, and reports each one's own outcome. It exists so a route that takes a set of rows
cannot decide them together: every key goes through the check a single write makes and leaves the
audit entry a single write leaves, and a key the reader may not act on is reported exactly as a key
that does not exist. See `SEVERAL_ACTS_ARE_EACH_DECIDED_ALONE`.

Task ids: M27.8.6
"""

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Final

from fastapi import Query
from fastapi.exceptions import RequestValidationError
from pydantic import StringConstraints

from brain.api_routes import FILTER_PARAM, FILTER_SEPARATOR, MAX_FILTER_TERM_LENGTH

# ------------------------------------------------------------ written-down reasons

#: Why search and filter run over the projected rows and not over what was loaded.
A_SEARCH_READS_ONLY_WHAT_THE_ROW_SHOWS: Final = (
    "A search or a filter is matched against the row the reader is sent, after the module that "
    "decides what they may see has projected it. Matching against the stored record would let a "
    "reader learn a withheld value by asking whether a row comes back when they search for it, "
    "one guess at a time, without ever being shown the value."
)

#: Why the load a route reads is bounded by a constant and never by what was asked.
THE_LOAD_IS_NEVER_NARROWED_BY_THE_QUERY: Final = (
    "A route loads to its own constant ceiling whatever the reader searched, filtered, ordered "
    "or paged by, and says whether that load came back full. Narrowing the load by the query "
    "would make that flag say how many rows match something the reader typed, including rows "
    "they may not see, which is a count arrived at by a boolean."
)

#: Why a cursor cannot widen what a reader is shown.
A_CURSOR_IS_A_POSITION_AND_NEVER_A_PERMISSION: Final = (
    "A cursor carries the order key and the row key of the last row the reader was shown and a "
    "digest of who asked and what. It carries no reach. Every page is decided again from the "
    "session's own grants before the cursor is read, so a forged or copied cursor can only start "
    "somewhere inside the presenter's own rows, and one minted for another reader or another "
    "question is refused as malformed."
)

#: Why a bulk act is a loop of single acts and not a set decided once.
SEVERAL_ACTS_ARE_EACH_DECIDED_ALONE: Final = (
    "An act on several rows runs the single act once per row, in the order asked, each through "
    "the same permission check and each leaving the audit entry a single act leaves. The answer "
    "reports every row's own outcome, so a partial failure is stated rather than hidden, and a "
    "row the reader may not act on is reported in the same words as one that does not exist."
)

# ------------------------------------------------------------------ the wire

#: The parameter names every listing takes. `filter` and its separator are `brain.api_routes`'.
LIMIT_PARAM: Final = "limit"
CURSOR_PARAM: Final = "cursor"
SEARCH_PARAM: Final = "q"
SORT_PARAM: Final = "sort"
LIST_FILTER_PARAM: Final = FILTER_PARAM
LIST_FILTER_SEPARATOR: Final = FILTER_SEPARATOR

#: What an order parameter puts before a column to walk it the other way.
DESCENDING: Final = "-"

#: The most rows one page carries, and what a caller gets when they do not say. A page, and not
#: the load: see `THE_LOAD_IS_NEVER_NARROWED_BY_THE_QUERY`.
MAX_PAGE_ROWS: Final = 200
DEFAULT_PAGE_ROWS: Final = 50

#: The longest search. A name, an identifier or a phrase, and far short of a document.
MAX_SEARCH_CHARS: Final = 120

#: How many filter terms one request may carry. More than any listing here has columns.
MAX_LIST_FILTERS: Final = 8

#: The longest cursor accepted. A key, a row key and a digest encode well inside it.
MAX_CURSOR_CHARS: Final = 1024

#: The most rows one bulk request may name. A resource bound, not a permission one.
MAX_SEVERAL: Final = 50

#: The grammar of a column name, which is `brain.core.scope.Clause.field`'s first character and
#: a subset of the rest, so a filter term that names one also matches `FILTER_TERM_PATTERN`.
COLUMN_PATTERN: Final = r"[a-z][a-z0-9_]{0,59}"

#: How long the reader binding inside a cursor is, in hex characters.
BINDING_CHARS: Final = 32

#: The cursor format's version. A cursor of any other version is malformed.
CURSOR_VERSION: Final = 1

#: What the fields of one row are joined with before a search reads them. A word never holds it,
#: so a search word cannot match across the end of one field and the start of the next.
SEPARATOR: Final = "\n"

#: What a cell may hold. A tuple of strings is a list column, such as a person's capabilities,
#: which a search and a filter read element by element and which is never an order.
Cell = str | int | float | bool | datetime | None
ListCell = tuple[str, ...]

#: The three kinds a sort key is tagged with, so keys of different kinds compare by tag rather
#: than raising: absent first, then numbers and instants, then text.
_ABSENT: Final = 0
_NUMBER: Final = 1
_TEXT: Final = 2

type SortKey = tuple[int, int | float | str]


class ListingError(ValueError):
    """A listing declared wrongly. Raised at import, never at request time."""


@dataclass(frozen=True)
class Column[R]:
    """One field of a projected row a listing may search, filter or order by.

    `read` is handed the row the reader is sent and nothing else. There is no parameter through
    which a stored record could reach it, which is `A_SEARCH_READS_ONLY_WHAT_THE_ROW_SHOWS` as a
    signature rather than as a habit.
    """

    name: str
    read: Callable[[R], Cell | ListCell]
    search: bool = False
    filter: bool = False
    sort: bool = False


@dataclass(frozen=True)
class ListAsked:
    """What one request asked of a listing, already through the declared grammar."""

    limit: int = DEFAULT_PAGE_ROWS
    cursor: str | None = None
    search: str = ""
    filters: tuple[str, ...] = ()
    sort: str | None = None


@dataclass(frozen=True)
class Paged[R]:
    """One page: the rows, and a cursor exactly when a further row matches. Never a count."""

    items: tuple[R, ...]
    next_cursor: str | None


def refused(parameter: str, message: str) -> RequestValidationError:
    """A parameter the listing refuses, as the 422 every other malformed parameter gets.

    `brain.audit_routes._refused_input`'s shape. Every refusal made here is a pure function of the
    parameters and the reader, so it is answered identically whatever the rows hold.
    """
    return RequestValidationError(
        [{"type": "value_error", "loc": ("query", parameter), "msg": message, "input": None}]
    )


def search_words(text: str) -> tuple[str, ...]:
    """A search as the words every matching row must say, casefolded."""
    return tuple(text.casefold().split())


_words = search_words


def says_every_word(texts: Iterable[str], words: Sequence[str]) -> bool:
    """Whether every word sits inside one of these texts, without regard to case.

    The texts are joined with `SEPARATOR`, which no word holds, so a word cannot match across the
    end of one field and the start of the next. The one definition of a search match, used by every
    listing here and by the audit ledger's search, so the two cannot mean different things.
    """
    said = SEPARATOR.join(text.casefold() for text in texts)
    return all(word in said for word in words)


def _texts(value: Cell | ListCell) -> tuple[str, ...]:
    """What a cell says, as the text a search or a filter compares against."""
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, bool):
        return ("true" if value else "false",)
    if isinstance(value, datetime):
        return (value.isoformat(),)
    return (str(value),)


def sort_key(value: Cell | ListCell) -> SortKey:
    """A cell as an order key: tagged, so no two keys can fail to compare.

    Text is compared casefolded, because an order in which "zoe" follows "Zachary" reads as broken.
    An instant is its timestamp. A list column is refused where the listing is declared.
    """
    if value is None:
        return (_ABSENT, 0)
    if isinstance(value, bool):
        return (_NUMBER, int(value))
    if isinstance(value, int | float):
        return (_NUMBER, value)
    if isinstance(value, datetime):
        return (_NUMBER, value.timestamp())
    if isinstance(value, str):
        return (_TEXT, value.casefold())
    msg = "a list column has no order"
    raise ListingError(msg)


@dataclass(frozen=True)
class Listing[R]:
    """One list route's columns, its row key and its default order.

    `key` is the row's own identifier as the row carries it, which is what breaks a tie in the
    order and what a cursor names. It has to be on the row: a key the reader was not sent would be
    a value a cursor carried back and forth that they were never shown.
    """

    name: str
    columns: tuple[Column[R], ...]
    key: Callable[[R], str]
    #: The order when none is asked for, as a `sort` parameter spells it.
    order: str
    _by_name: dict[str, Column[R]] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        names = [one.name for one in self.columns]
        if len(set(names)) != len(names):
            msg = f"listing {self.name} names a column twice"
            raise ListingError(msg)
        for one in names:
            if re.fullmatch(COLUMN_PATTERN, one) is None:
                msg = f"listing {self.name} has a column name the filter grammar refuses: {one}"
                raise ListingError(msg)
        object.__setattr__(self, "_by_name", {one.name: one for one in self.columns})
        if self._sorted(self.order) is None:
            msg = f"listing {self.name} orders by default by a column it does not sort by"
            raise ListingError(msg)

    # ------------------------------------------------------------ the declaration

    def sorts(self) -> tuple[str, ...]:
        return tuple(one.name for one in self.columns if one.sort)

    def filters(self) -> tuple[str, ...]:
        return tuple(one.name for one in self.columns if one.filter)

    def searches(self) -> tuple[str, ...]:
        return tuple(one.name for one in self.columns if one.search)

    def sort_pattern(self) -> str:
        """The `sort` grammar: one declared column, optionally walked the other way."""
        return rf"^-?(?:{'|'.join(re.escape(one) for one in self.sorts())})$"

    def filter_pattern(self) -> str:
        """The `filter` grammar: `brain.api_routes`' term, narrowed to the declared columns.

        A listing that filters by nothing declares a pattern nothing matches, so a term is refused
        by the declaration rather than accepted and ignored.
        """
        declared = self.filters()
        if not declared:
            # An empty character class, because the validator is Rust's regex engine, which has no
            # lookahead: `(?!)` refuses to build and takes the route down at import.
            return r"^[^\s\S]$"
        names = "|".join(re.escape(one) for one in declared)
        return rf"^(?:{names}){re.escape(FILTER_SEPARATOR)}[^\r\n]+$"

    def query(self) -> Callable[..., ListAsked]:
        """The route dependency: the five parameters, each declared with this listing's grammar.

        Built per listing so the API document carries the columns each route sorts and filters by,
        which is what a console reads to decide what it may offer.
        """
        sort_pattern = self.sort_pattern()
        filter_pattern = self.filter_pattern()

        def asked(
            limit: Annotated[int, Query(ge=1, le=MAX_PAGE_ROWS)] = DEFAULT_PAGE_ROWS,
            cursor: Annotated[str | None, Query(max_length=MAX_CURSOR_CHARS)] = None,
            q: Annotated[str, Query(max_length=MAX_SEARCH_CHARS)] = "",
            filters: Annotated[
                tuple[
                    Annotated[
                        str,
                        StringConstraints(
                            pattern=filter_pattern, max_length=MAX_FILTER_TERM_LENGTH
                        ),
                    ],
                    ...,
                ],
                Query(alias=FILTER_PARAM, max_length=MAX_LIST_FILTERS),
            ] = (),
            sort: Annotated[str | None, Query(pattern=sort_pattern)] = None,
        ) -> ListAsked:
            return ListAsked(limit=limit, cursor=cursor, search=q, filters=filters, sort=sort)

        return asked

    # ------------------------------------------------------------------ a page

    def _sorted(self, spelled: str) -> tuple[Column[R], bool] | None:
        descending = spelled.startswith(DESCENDING)
        found = self._by_name.get(spelled.removeprefix(DESCENDING))
        if found is None or not found.sort:
            return None
        return found, descending

    def binding(self, asked: ListAsked, reader: str) -> str:
        """The digest a cursor carries: this listing, this reader and this exact question."""
        material = json.dumps(
            [
                self.name,
                reader,
                asked.sort or self.order,
                list(_words(asked.search)),
                sorted(asked.filters),
            ],
            separators=(",", ":"),
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:BINDING_CHARS]

    def plan(self, asked: ListAsked, *, reader: str) -> "Plan[R]":
        """What one request asks of this listing, checked, before anything is loaded.

        Every refusal is decided here, from the parameters and the reader alone, so a route calls
        this before it reads a row and a malformed question is answered identically on an install
        with rows, with none, and with no database at all.
        """
        chosen = self._sorted(asked.sort or self.order)
        if chosen is None:
            raise refused(SORT_PARAM, "this list is not ordered by that")
        narrowing: list[tuple[Column[R], str]] = []
        for term in asked.filters:
            name, _, value = term.partition(FILTER_SEPARATOR)
            by = self._by_name.get(name)
            if by is None or not by.filter:
                raise refused(LIST_FILTER_PARAM, "this list is not filtered by that")
            narrowing.append((by, value))
        binding = self.binding(asked, reader)
        after = None if asked.cursor is None else decode_position(asked.cursor, binding)
        return Plan(
            listing=self,
            column=chosen[0],
            descending=chosen[1],
            narrowing=tuple(narrowing),
            words=_words(asked.search),
            limit=asked.limit,
            binding=binding,
            after=after,
        )

    def page(self, rows: Sequence[R], asked: ListAsked, *, reader: str) -> Paged[R]:
        """`plan` and then `Plan.page`, for a caller with the rows already in hand."""
        return self.plan(asked, reader=reader).page(rows)


@dataclass(frozen=True)
class Plan[R]:
    """A checked question about one listing, ready to be put to the rows the reader is sent."""

    listing: Listing[R]
    column: Column[R]
    descending: bool
    narrowing: tuple[tuple[Column[R], str], ...]
    words: tuple[str, ...]
    limit: int
    binding: str
    after: tuple[SortKey, str] | None

    def matches(self, row: R) -> bool:
        """Whether a projected row answers the search and every filter term."""
        if self.words:
            texts = (
                text for one in self.listing.columns if one.search for text in _texts(one.read(row))
            )
            if not says_every_word(texts, self.words):
                return False
        return all(value in _texts(by.read(row)) for by, value in self.narrowing)

    def position(self, row: R) -> tuple[SortKey, str]:
        """Where a row sits in the order asked: its order key, then its row key."""
        return sort_key(self.column.read(row)), self.listing.key(row)

    def matching(self, rows: Sequence[R]) -> list[R]:
        """Every row that matches, in the order asked, unpaged. For a list answered whole."""
        return sorted(
            (one for one in rows if self.matches(one)),
            key=self.position,
            reverse=self.descending,
        )

    def page(self, rows: Sequence[R]) -> Paged[R]:
        """One page of the projected rows this reader is sent, narrowed, ordered and positioned.

        `next_cursor` is computed over the rows that match and follow the page, which are rows the
        reader may see, and never over what the route loaded.
        """
        kept = self.matching(rows)
        after = self.after
        if after is not None:
            kept = [
                one
                for one in kept
                if (self.position(one) < after if self.descending else self.position(one) > after)
            ]
        shown = tuple(kept[: self.limit])
        if len(kept) <= self.limit or not shown:
            return Paged(items=shown, next_cursor=None)
        cursor = encode_position(self.position(shown[-1]), self.binding)
        return Paged(items=shown, next_cursor=cursor)


# ------------------------------------------------------------------ the cursor


def encode_position(position: tuple[SortKey, str], binding: str) -> str:
    """A cursor: a version, the binding, the order key and the row key, as URL-safe text."""
    (tag, value), key = position
    payload = {"v": CURSOR_VERSION, "b": binding, "k": [tag, value], "r": key}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _key_of(found: Any) -> SortKey | None:
    """An order key read back from a cursor, or None when its tag and value do not agree.

    The agreement is what keeps a forged cursor from raising in the comparison: a key whose tag
    says text holds text, so it compares with every other text key and, by its tag, with the rest.
    """
    if not isinstance(found, list) or len(found) != 2:
        return None
    tag, value = found
    if tag == _ABSENT and value == 0 and not isinstance(value, bool):
        return (_ABSENT, 0)
    if tag == _NUMBER and isinstance(value, int | float) and not isinstance(value, bool):
        return (_NUMBER, value)
    if tag == _TEXT and isinstance(value, str):
        return (_TEXT, value)
    return None


def decode_position(cursor: str, binding: str) -> tuple[SortKey, str]:
    """The position a cursor names, or the 422 a malformed cursor gets.

    A cursor bound to another reader, another listing or another question is malformed here, in the
    same words as one that is not base64 at all.
    See `A_CURSOR_IS_A_POSITION_AND_NEVER_A_PERMISSION`.
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
    except (binascii.Error, UnicodeError, ValueError):
        raise refused(CURSOR_PARAM, "malformed cursor") from None
    if not isinstance(payload, dict) or payload.get("v") != CURSOR_VERSION:
        raise refused(CURSOR_PARAM, "malformed cursor")
    found = payload.get("b")
    key = _key_of(payload.get("k"))
    row = payload.get("r")
    if not isinstance(found, str) or found != binding or key is None or not isinstance(row, str):
        raise refused(CURSOR_PARAM, "malformed cursor")
    return key, row


# ------------------------------------------------------------------ several


async def each_of[K, T](keys: Sequence[K], act: Callable[[K], Awaitable[T]]) -> list[tuple[K, T]]:
    """Run one act per key, in the order asked, and pair each key with its own outcome.

    Sequential rather than gathered: each act takes its own lock and writes its own ledger entry,
    and two acts racing on one row would each be refused for the other's reason. A duplicate key
    is acted on once. See `SEVERAL_ACTS_ARE_EACH_DECIDED_ALONE`.
    """
    seen: set[K] = set()
    outcomes: list[tuple[K, T]] = []
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        outcomes.append((key, await act(key)))
    return outcomes
