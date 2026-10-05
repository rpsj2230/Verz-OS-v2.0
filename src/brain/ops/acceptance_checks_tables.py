"""The install acceptance checks for classified tables: a price list uploaded, asked about, marked.

Each check drives the functions `brain.classification_routes` calls, in the order it calls them,
against the install's own database: `brain.knowledge.table_file` reads the file,
`brain.knowledge.classified_rows.next_upload` gives it its first classification,
`brain.ops.classification_store` writes it and `0116`'s trigger ledgers the write, all through the
harness's sessions as the application role and all rolled back. The three checks split where the
leaves split: the upload and the classification it arrives with (M7.5.1), what a reader is answered
out of it (M7.5.2), and a mark reviewed and applied (M7.5.3).

**Nothing signs in, so the routes' gate is restated over a reach the resolver loaded.** The
Classification routes take a signed-in caller and ask `_may_change` of it: both classification
grants, at the reach the request dependency admitted. A check makes no session and holds no token,
so it loads the administrator through the one resolver, narrows the reach with
`brain.gate.admission.admit` as the dependency does for a console session with a second factor, and
asks `may_change`, which `tests/unit/test_acceptance_tables.py` holds to the route's own function
over every combination of grants and sign-in. See
`THE_ROUTES_GATE_IS_RESTATED_AND_HELD_TO_THE_ROUTES_OWN`. Where the grants are held is not restated:
the routes ask `brain.classification_routes.table_within_reach` at every row a change governs, and
the check calls that function over the rows the store holds, as the routes do. Rejected: calling the
route functions with a caller whose verified claims the check wrote, which would put a signature
nobody checked where the product keeps only ones it did.

**Ask is asked on its own lane, with no model, over every table's questions.**
`brain.ops.classification_store.classified_lane_of` builds the lane from every live table as the
answer route does, and `brain.gate.answer.answer_lane` answers over its rules, its readers and its
policies, so the matcher, the projection, the redactor, the abstention and the frames a person
receives are the install's. The check uploads two price lists with the same columns and asks each
about its own services, which is the collision the owner's install showed on 2026-09-29: every
table with a sell price column is asked in the same words, and until then the lane answered nobody
about either. Until that day the check matched its own table's rules alone to dodge the collision,
which proved one price list worked on an install where two did not. See
`TWO_PRICE_LISTS_ARE_ASKED_IN_THE_SAME_WORDS_AND_EACH_ANSWERS`. A price list of the install's own
matches the same questions and is read at the check's readers' reach, which reaches none of it.

**What a reader is refused is looked for in three places, because it is withheld in three.** The
rows Ask reads for the reader, the redactor handed rows that do carry the cost, and the frames the
lane answers with. Each layer withholds on its own, so a check reading only the answer would stay
green with the projection gone, and one reading only the rows would stay green with the redactor
gone. A reader holding the margin grant and not the cost grant is asked as well, because withholding
the margin from them is the derivation and nothing else.

**Every name is the run's.** Tables are `acceptance_<run>_...`, every value and every service name
is a word nothing else holds, and every grant is scoped to a reserved department. Every table the
check uploads places its rows in acceptance_a through a department column, because a department
grant is judged against that column on every row: by the routes, for the administrator changing the
table, and by the row plane, for a reader asking about it once the administrator marks it open. The
one table placed in acceptance_b is uploaded by acceptance_b's own administrator, and is there to be
refused to acceptance_a's in the words a table that does not exist gets.

Task ids: M38.5.1, M7.5.1, M7.5.2, M7.5.3
"""

from __future__ import annotations

import base64
import io
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from xml.sax.saxutils import escape

from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check

# The department grants the other checks write, imported rather than copied, and imported first so
# the suite's own checks are registered ahead of these.
from brain.ops.acceptance_checks import _in
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from brain.classification_routes import ClassificationView, MarkApplied, ReviewView
    from brain.core.entitlement import EntitlementSet
    from brain.core.principal import Principal
    from brain.gate.answer import Answered
    from brain.knowledge.classified_rows import ClassifiedLane, StoredTable
    from brain.knowledge.columns import ColumnAccess
    from brain.ops.classification_store import ClassifiedTables

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 110

A: Final = RESERVED_DEPARTMENTS[0]
B: Final = RESERVED_DEPARTMENTS[1]

# ------------------------------------------------------------------ written-down reasons
#: Why the check asks the gate the routes ask, and how the two are kept one.
THE_ROUTES_GATE_IS_RESTATED_AND_HELD_TO_THE_ROUTES_OWN: Final = (
    "The Classification routes ask a signed-in request whether its reach holds both "
    "classification grants. A check signs nobody in, so it asks the same two grants of a reach "
    "the one resolver loaded and admit narrowed for a console session, and a test holds this "
    "function to the route's own over every combination of grants and sign-in, so the two cannot "
    "part without a red build."
)

#: Why the check uploads two price lists and asks the whole lane about both.
TWO_PRICE_LISTS_ARE_ASKED_IN_THE_SAME_WORDS_AND_EACH_ANSWERS: Final = (
    "Every uploaded table with a sell price column is asked about in the same words, and until "
    "2026-09-29 a second one made the lane answer nobody about either, which the owner's install "
    "showed and this check, matching its own table's rules alone, did not. So it uploads two price "
    "lists with the same columns, asks the lane's every rule about each list's own service, and "
    "fails unless each is answered from its own list and withheld as one list withholds."
)

#: Why each write the check makes carries a trace of its own.
AN_APPLIED_MARK_IS_ATTRIBUTED_BY_ITS_OWN_REQUEST: Final = (
    "The three settings a trigger reads last for the transaction, and a check is one transaction, "
    "so an upload's attribution is still standing when a mark is applied after it. Each write "
    "the check makes therefore carries a trace of its own, as two requests would: an entry naming "
    "the mark's trace can only have come from the apply's own settings, and a store that set none "
    "would leave the upload's trace on the entry, which the check reads as a failure."
)

#: Why the check asks a table another department's administrator uploaded.
ANOTHER_DEPARTMENT_S_TABLE_IS_REFUSED_AS_A_MISSING_ONE: Final = (
    "Until 2026-09-29 the Classification routes asked whether both classification grants were "
    "held and never where, so a department's administrator could mark any department's price "
    "list, and this check, whose administrator changed only a table of its own, passed. So a "
    "table placed in acceptance_b, uploaded by acceptance_b's administrator, is asked for as "
    "acceptance_a's would change it, and must be refused exactly as a name no table has."
)

# ------------------------------------------------------------ the words a failure is said in
EACH_LIST_WAS_NOT_ANSWERED: Final = (
    "a reader holding two price lists asked in the same words was not answered each list's sell"
    " price from its own list"
)

ANOTHER_DEPARTMENT_S_TABLE_WAS_TOLD_APART: Final = (
    "an administrator of one department could read or change another department's price list, "
    "or was refused it in other words than a price list that does not exist"
)

A_PRICE_LIST_WAS_REFUSED: Final = (
    "a well-formed price list, uploaded as a CSV or an XLSX, was refused as the upload route "
    "refuses one"
)

# ------------------------------------------------------------------------ the figures
#: A price list's headings as somebody types them: the four the shipped price list classifies, the
#: department its rows are placed in, and a note it does not classify.
PRICE_LIST_HEADINGS: Final = ("Name", "Department", "Sell Price", "Cost", "Margin", "Notes")

#: The column each of those headings is held under, written out rather than derived, so the
#: product's parser is held to it by a test instead of agreeing with itself.
PRICE_LIST_COLUMNS: Final = ("name", "department", "sell_price", "cost", "margin", "notes")

#: A price list a reader asks about: the same columns, placed in a department.
ASKED_HEADINGS: Final = ("Name", "Department", "Sell Price", "Cost", "Margin")
ASKED_COLUMNS: Final = ("name", "department", "sell_price", "cost", "margin")

#: How a first upload of `PRICE_LIST_HEADINGS` classifies each column: its mark and its inputs, as
#: `brain.knowledge.columns.PRICE_LIST` ships them and default-deny leaves the rest.
FIRST_MARKS: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "name": ("open", ()),
    "department": ("restricted", ()),
    "sell_price": ("open", ()),
    "cost": ("derived", ("margin", "sell_price")),
    "margin": ("derived", ("cost", "sell_price")),
    "notes": ("restricted", ()),
}

#: The two price lists the Ask check uploads, asked about in the same words.
ASKED_LISTS: Final = ("prices", "rates")

#: The two columns a reader without the cost grant is never told, and the one they are.
WITHHELD: Final = ("cost", "margin")
SELL_PRICE: Final = "sell_price"

#: How many services each price list lists, so every question picks one row out of several.
SERVICES: Final = 2

#: What each write's trace ends in, after the run's own, so the ledger says which one it was.
UPLOAD_TRACE: Final = "-upload"
MARK_TRACE: Final = "-mark"
ASK_TRACE: Final = "-ask"

#: The two namespaces a workbook's parts are written in, and the package's own.
_MAIN: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_RELATIONSHIPS: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE: Final = "http://schemas.openxmlformats.org/package/2006/relationships"


# ------------------------------------------------------------------------ the files
def price_list_csv(headings: Sequence[str], rows: Sequence[Sequence[str]]) -> bytes:
    """A UTF-8 CSV as a spreadsheet saves one: a heading row, then a line per service."""
    lines = [",".join(headings), *(",".join(row) for row in rows)]
    return (chr(10).join(lines) + chr(10)).encode("utf-8")


def price_list_xlsx(headings: Sequence[str], rows: Sequence[Sequence[str]]) -> bytes:
    """A workbook of one sheet, every cell a shared string, as a spreadsheet saves one.

    The six parts a workbook opens with, including the two the product's reader never reads, so
    the file is one a spreadsheet would open as well as one the upload accepts.
    """
    strings: list[str] = []
    sheet_rows: list[str] = []
    for number, row in enumerate((headings, *rows), start=1):
        cells: list[str] = []
        for position, value in enumerate(row):
            strings.append(value)
            reference = f"{chr(ord('A') + position)}{number}"
            cells.append(f'<c r="{reference}" t="s"><v>{len(strings) - 1}</v></c>')
        sheet_rows.append(f'<row r="{number}">{"".join(cells)}</row>')
    prologue = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    parts = {
        "[Content_Types].xml": (
            f"{prologue}<Types "
            'xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/sharedStrings.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            f'{prologue}<Relationships xmlns="{_PACKAGE}"><Relationship Id="rId1" '
            f'Type="{_RELATIONSHIPS}/officeDocument" Target="xl/workbook.xml"/></Relationships>'
        ),
        "xl/workbook.xml": (
            f'{prologue}<workbook xmlns="{_MAIN}" xmlns:r="{_RELATIONSHIPS}"><sheets>'
            '<sheet name="Prices" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            f'{prologue}<Relationships xmlns="{_PACKAGE}">'
            f'<Relationship Id="rId1" Type="{_RELATIONSHIPS}/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="rId2" Type="{_RELATIONSHIPS}/sharedStrings" '
            'Target="sharedStrings.xml"/></Relationships>'
        ),
        "xl/sharedStrings.xml": (
            f'{prologue}<sst xmlns="{_MAIN}" count="{len(strings)}" '
            f'uniqueCount="{len(strings)}">'
            + "".join(f"<si><t>{escape(one)}</t></si>" for one in strings)
            + "</sst>"
        ),
        "xl/worksheets/sheet1.xml": (
            f'{prologue}<worksheet xmlns="{_MAIN}"><sheetData>'
            + "".join(sheet_rows)
            + "</sheetData></worksheet>"
        ),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as book:
        for name, content in parts.items():
            book.writestr(name, content)
    return out.getvalue()


@dataclass(frozen=True)
class _PriceList:
    """One price list a check uploads: a table name for the run, its headings, rows of words."""

    entity: str
    headings: tuple[str, ...]
    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...]

    def grid(self) -> list[list[str]]:
        return [[row[column] for column in self.columns] for row in self.rows]

    def csv(self) -> bytes:
        return price_list_csv(self.headings, self.grid())

    def xlsx(self) -> bytes:
        return price_list_xlsx(self.headings, self.grid())


def _price_list(
    h: Harness,
    what: str,
    headings: Sequence[str],
    columns: Sequence[str],
    *,
    department: str = A,
) -> _PriceList:
    """`SERVICES` services, every value a word nothing else holds, every row in `department`."""
    rows = []
    for _ in range(SERVICES):
        row = {column: h.word() for column in columns}
        if "department" in row:
            row["department"] = department
        rows.append(row)
    return _PriceList(
        entity=f"acceptance_{h.run}_{what}",
        headings=tuple(headings),
        columns=tuple(columns),
        rows=tuple(rows),
    )


# ------------------------------------------------------------------------ the helpers
class _Application:
    """What the Classification routes and Ask read off the application's state: its pool, which
    is the check's transaction here. See `brain.ops.classification_store.classified_tables_of`."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.db_sessions = sessions


def may_change(reach: EntitlementSet, now: datetime) -> bool:
    """`brain.classification_routes._may_change`, asked of a reach rather than a request. See
    `THE_ROUTES_GATE_IS_RESTATED_AND_HELD_TO_THE_ROUTES_OWN`."""
    from brain.classification_routes import CLASSIFICATION_READ, CLASSIFICATION_WRITE

    return reach.holds(CLASSIFICATION_READ, now) and reach.holds(CLASSIFICATION_WRITE, now)


async def _console(h: Harness, principal_id: str, *, second_factor: bool) -> EntitlementSet:
    """A reserved person's reach as `brain.api_routes.asking` admits it for a console session."""
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel

    assurance = Assurance.STRONG if second_factor else Assurance.AUTHENTICATED
    return admit(await h.reach(principal_id), Channel.CONSOLE, assurance)


@dataclass(frozen=True)
class _Administrator:
    """The person every change is made as, and their reach on a console with a second factor."""

    principal_id: str
    reach: EntitlementSet


async def _administrator(h: Harness, department: str = A) -> _Administrator:
    """A reserved person of `department` holding both classification grants there, let through
    the routes' gate. Every request the check makes as them is made at this one reach and one
    instant, so the gate asked once here is the answer each of those requests would be given."""
    from brain.classification_routes import CLASSIFICATION_READ, CLASSIFICATION_WRITE

    made = h.principal(department, "classifier")
    await h.person(
        made,
        department=department,
        grants=_in(department, CLASSIFICATION_READ.value, CLASSIFICATION_WRITE.value),
    )
    admin = _Administrator(made, await _console(h, made, second_factor=True))
    if not may_change(admin.reach, h.now):
        raise CheckFailedError(
            "an administrator holding both classification grants, signed in with a second "
            "factor, was refused a change to a classified table"
        )
    return admin


async def _only_an_administrator_may_change(h: Harness, admin: _Administrator) -> None:
    """The routes' refusals: a person holding the read grant alone, and the administrator on a
    session with no second factor, whose `admin` verb `admit` withholds."""
    from brain.classification_routes import CLASSIFICATION_READ

    reader = h.principal(A, "reader")
    await h.person(reader, department=A, grants=_in(A, CLASSIFICATION_READ.value))
    for reach in (
        await _console(h, reader, second_factor=True),
        await _console(h, admin.principal_id, second_factor=False),
    ):
        if may_change(reach, h.now):
            raise CheckFailedError(
                "a person without the write grant, or signed in without a second factor, may "
                "change a classified table"
            )


def _tables(h: Harness) -> ClassifiedTables:
    """Where the routes keep uploaded tables on this install, chosen by the routes' own wiring."""
    from brain.ops.classification_store import classified_tables_of

    tables = classified_tables_of(_Application(h.sessions))
    if tables is None:
        raise CheckFailedError("this install's application keeps uploaded tables nowhere")
    return tables


async def _upload(
    h: Harness, admin: _Administrator, prices: _PriceList, *, filename: str, content: bytes
) -> tuple[StoredTable, ClassificationView]:
    """`brain.classification_routes.upload_table`'s steps after its gate, in its order, for one
    file. The gate is `_administrator`'s; where it is held is the routes' own function, asked at
    the rows the file brings and the rows it replaces."""
    from brain.classification_routes import (
        TableUpload,
        _upload_refusal,
        table_within_reach,
        view_of,
    )
    from brain.knowledge.classified_rows import next_upload
    from brain.knowledge.columns import ColumnClassificationError, column_name_for
    from brain.knowledge.table_file import TableFileError, read_table_file
    from brain.ops.classification_store import ClassifiedTableStoreError, Writer

    tables = _tables(h)
    if _upload_refusal(prices.entity):
        raise CheckFailedError("a table name made for this run was refused as a table's name")
    body = TableUpload(
        title=f"Acceptance check {prices.entity}",
        filename=filename,
        content_base64=base64.b64encode(content).decode("ascii"),
        key_column=prices.headings[0],
    )
    try:
        parsed = read_table_file(
            body.filename, base64.b64decode(body.content_base64, validate=True)
        )
        key = column_name_for(body.key_column or "")
        # The route's own refusal, kept in its place. It is equivalent here and says so: a key the
        # file does not carry is refused again by `StoredTable` a line later, and the check tells
        # both in one sentence where the route tells them in two.
        if key not in parsed.columns:
            raise CheckFailedError(A_PRICE_LIST_WAS_REFUSED)
        existing = await tables.table(prices.entity)
        replaced = () if existing is None else await tables.rows_of(existing)
        if not table_within_reach(admin.reach, (*parsed.rows, *replaced), h.now):
            raise CheckFailedError(A_PRICE_LIST_WAS_REFUSED)
        table = next_upload(
            existing,
            entity=prices.entity,
            title=body.title.strip(),
            key_column=key,
            columns=parsed.columns,
        )
        stored = await tables.upload(
            table,
            parsed.rows,
            writer=Writer(
                actor_id=admin.principal_id,
                ent_hash=admin.reach.ent_hash(),
                trace_id=f"{h.trace_id}{UPLOAD_TRACE}",
            ),
        )
    except (TableFileError, ColumnClassificationError, ClassifiedTableStoreError):
        raise CheckFailedError(A_PRICE_LIST_WAS_REFUSED) from None
    return stored, view_of(stored.classification, editable=True, stored=stored)


async def _changeable(
    h: Harness, admin: _Administrator, entity: str, *, reading: bool = False
) -> StoredTable | None:
    """`brain.classification_routes._changeable_or_absent`'s answer: the uploaded table when it
    exists and every row of it is within the administrator's grants, and None, the routes' one
    refusal, both when it does not exist and when it is out of reach. `reading` asks what
    `brain.classification_routes.classification` asks before it answers a table's rules: the read
    grant alone, at every row."""
    from brain.classification_routes import TO_CHANGE, TO_READ, table_within_reach

    tables = _tables(h)
    stored = await tables.table(entity)
    if stored is None:
        return None
    rows = await tables.rows_of(stored)
    needing = TO_READ if reading else TO_CHANGE
    return stored if table_within_reach(admin.reach, rows, h.now, needing) else None


async def _marked_table(h: Harness, admin: _Administrator, entity: str) -> StoredTable:
    """The mark routes' opening after their gate: the uploaded table, or the one refusal."""
    stored = await _changeable(h, admin, entity)
    if stored is None:
        raise CheckFailedError("a table uploaded a moment before was not there to be marked")
    return stored


async def _review(
    h: Harness,
    admin: _Administrator,
    entity: str,
    column: str,
    access: ColumnAccess,
    derived_from: Sequence[str] = (),
) -> ReviewView:
    """`brain.classification_routes.review_mark`'s steps: nothing is written."""
    from brain.classification_routes import ColumnMark, _mark_review

    stored = await _marked_table(h, admin, entity)
    return _mark_review(stored, column, ColumnMark(access=access, derived_from=list(derived_from)))


async def _apply(
    h: Harness,
    admin: _Administrator,
    entity: str,
    column: str,
    access: ColumnAccess,
    derived_from: Sequence[str] = (),
) -> MarkApplied:
    """`brain.classification_routes.apply_mark`'s steps, in its order, answered as it answers."""
    from brain.classification_routes import (
        ColumnMark,
        MarkApplied,
        _in_place,
        _mark_review,
        view_of,
    )
    from brain.knowledge.columns import marked
    from brain.ops.classification_store import Writer

    stored = await _marked_table(h, admin, entity)
    mark = ColumnMark(access=access, derived_from=list(derived_from))
    verdict = _mark_review(stored, column, mark)
    if verdict.would_not_load:
        return MarkApplied(
            applied=False,
            review=verdict,
            classification=view_of(stored.classification, editable=True, stored=stored),
        )
    after = _in_place(stored.classification, marked(entity, column, mark.access, mark.derived_from))
    written = await _tables(h).classify(
        entity,
        after,
        writer=Writer(
            actor_id=admin.principal_id,
            ent_hash=admin.reach.ent_hash(),
            trace_id=f"{h.trace_id}{MARK_TRACE}",
        ),
    )
    if written is None:
        raise CheckFailedError("a table uploaded a moment before was not there to be marked")
    return MarkApplied(
        applied=True,
        review=verdict,
        classification=view_of(written.classification, editable=True, stored=written),
    )


async def _held_rows(h: Harness, entity: str, version: int) -> list[dict[str, str]]:
    """The rows `know.classified_row` holds for one upload, in the file's order."""
    rows = (
        await h.execute(
            text(
                "SELECT fields FROM know.classified_row"
                " WHERE entity = :entity AND version = :version ORDER BY position"
            ).bindparams(entity=entity, version=version)
        )
    ).scalars()
    # A JSONB value arrives decoded: psycopg, the application's driver, loads it.
    return [{str(k): str(v) for k, v in dict(one).items()} for one in rows]


@dataclass(frozen=True)
class _Entry:
    """One ledger entry about a table, read as an auditor reads it."""

    actor: str
    action: str
    ent_hash: str
    trace: str
    change: str
    source: str
    inferred: bool


async def _entries(h: Harness, entity: str) -> list[_Entry]:
    """Every entry `0116`'s trigger wrote about this table in the check's transaction."""
    rows = (
        await h.execute(
            text(
                "SELECT actor_id, action, ent_hash, trace_id, details FROM obs.audit_entry"
                " WHERE subject = :subject ORDER BY seq"
            ).bindparams(subject=f"setting:classified_table.{entity}")
        )
    ).all()
    entries = []
    for actor, action, ent_hash, trace, details in rows:
        said = dict(details)
        entries.append(
            _Entry(
                actor=str(actor),
                action=str(action),
                ent_hash=str(ent_hash),
                trace=str(trace),
                change=str(said.get("change", "")),
                source=str(said.get("source", "")),
                inferred="actor" in said,
            )
        )
    return entries


# ------------------------------------------------------------- 1. an upload (M7.5.1)
@check(
    leaves=("M7.5.1",),
    sentence=(
        "A price list uploaded as a CSV and again as an XLSX, by the Classification screen's steps "
        "as an administrator with a second factor, is held as rows with every column classified: "
        "name and sell price open, cost and margin derived, a column no price list names "
        "restricted. A PDF, the shipped price list's name, and anybody without the write grant or "
        "the second factor are refused."
    ),
)
async def a_price_list_upload_classifies_every_column(h: Harness) -> None:
    from brain.classification_routes import A_NAME_THE_PRODUCT_CLASSIFIES, _upload_refusal
    from brain.knowledge.columns import PRICE_LIST
    from brain.knowledge.table_file import TableFileError, read_table_file

    await h.found_departments()
    admin = await _administrator(h)
    await _only_an_administrator_may_change(h, admin)
    if _upload_refusal(PRICE_LIST.entity) != A_NAME_THE_PRODUCT_CLASSIFIES:
        raise CheckFailedError("a table named as the price list the product ships with was taken")
    as_csv = _price_list(h, "csv", PRICE_LIST_HEADINGS, PRICE_LIST_COLUMNS)
    as_xlsx = _price_list(h, "xlsx", PRICE_LIST_HEADINGS, PRICE_LIST_COLUMNS)
    try:
        read_table_file(f"{as_csv.entity}.pdf", as_csv.csv())
    except TableFileError:
        pass
    else:
        raise CheckFailedError("a file that is neither a CSV nor an XLSX was read as a table")

    tables = _tables(h)
    for prices, suffix, content in (
        (as_csv, ".csv", as_csv.csv()),
        (as_xlsx, ".xlsx", as_xlsx.xlsx()),
    ):
        stored, view = await _upload(
            h, admin, prices, filename=f"{prices.entity}{suffix}", content=content
        )
        shown = {one.column: (one.access, tuple(one.derived_from)) for one in view.columns}
        again = await tables.table(prices.entity)
        if shown != FIRST_MARKS or again != stored or stored.key_column != PRICE_LIST_COLUMNS[0]:
            raise CheckFailedError(
                "an uploaded price list's columns were not each held as open, restricted or "
                "derived as the shipped price list marks them"
            )
        if await _held_rows(h, prices.entity, stored.version) != list(prices.rows):
            raise CheckFailedError(
                "an uploaded price list's rows were not held as the file had them"
            )


# ------------------------------------------------------------ 2. what Ask says (M7.5.2)
async def _ask(
    h: Harness,
    lane: ClassifiedLane,
    person: Principal,
    reach: EntitlementSet,
    column: str,
    service: str,
) -> Answered:
    """One question in the first shape a table is asked in, answered on Ask's lane over every rule
    it holds, with no model, no cache and no recorder. See
    `TWO_PRICE_LISTS_ARE_ASKED_IN_THE_SAME_WORDS_AND_EACH_ANSWERS`."""
    from brain.gate.answer import answer_lane
    from brain.gate.context import Channel
    from brain.gate.finish import Origin
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of
    from brain.ops.trace_sink import CountingTraceSink

    now = h.now
    return await answer_lane(
        QUESTION_SHAPES[0].format(label=label_of(column), slot=service),
        origin=Origin(
            trace_id=f"{h.trace_id}{ASK_TRACE}", principal=person, channel=Channel.CONSOLE
        ),
        recorders=(),
        rules=lane.rules,
        readers=lane.readers,
        entitlement=reach,
        policies=lane.policies,
        # What `brain.api_routes.sources_at` gives a reach holding no registry entity's grant.
        reachable_sources=(),
        sink=CountingTraceSink(),
        now=now,
        clock=lambda: now,
    )


@check(
    leaves=("M7.5.2",),
    sentence=(
        "On Ask's own lane, with no model, two price lists with the same columns each answer for "
        "their own services: without the cost grant a reader of both is told a service's sell "
        "price, and its cost or margin as if the service did not exist; with the margin grant "
        "alone, neither; with both, all three. The rows read and the redactor withhold the same "
        "two columns."
    ),
)
async def a_reader_without_the_cost_grant_is_told_the_sell_price_alone(h: Harness) -> None:
    from brain.core.redaction import redact
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge.classified_rows import TABLES_SOURCE
    from brain.knowledge.columns import ColumnAccess, column_capability, table_capability
    from brain.knowledge.rows import RowRequest
    from brain.ops.classification_store import classified_lane_of

    await h.found_departments()
    admin = await _administrator(h)
    # See TWO_PRICE_LISTS_ARE_ASKED_IN_THE_SAME_WORDS_AND_EACH_ANSWERS.
    lists = tuple(_price_list(h, what, ASKED_HEADINGS, ASKED_COLUMNS) for what in ASKED_LISTS)
    for prices in lists:
        await _upload(h, admin, prices, filename=f"{prices.entity}.csv", content=prices.csv())
        opened = await _apply(h, admin, prices.entity, "department", ColumnAccess.OPEN)
        if not opened.applied:
            raise CheckFailedError("an uploaded price list's department column could not be opened")

    tables = tuple(table_capability(one.entity).value for one in lists)
    costs, margins = (
        tuple(column_capability(one.entity, column).value for one in lists) for column in WITHHELD
    )
    held = {
        "sales": tables,
        "short": (*tables, *margins),
        "finance": (*tables, *costs, *margins),
    }
    people: dict[str, Principal] = {}
    reach: dict[str, EntitlementSet] = {}
    for role, capabilities in held.items():
        made = h.principal(A, role)
        await h.person(made, department=A, grants=_in(A, *capabilities))
        person = await StoredPrincipals(h.sessions).live_principal(made)
        if person is None:
            raise CheckFailedError("a reserved person was not live in the directory")
        people[role], reach[role] = person, await _console(h, made, second_factor=False)
    narrow = ("sales", "short")

    lane = await classified_lane_of(_Application(h.sessions))
    for prices in lists:
        reader = lane.readers.get((TABLES_SOURCE, prices.entity))
        policy = lane.policies.get(prices.entity)
        if reader is None or policy is None or all(r.entity != prices.entity for r in lane.rules):
            raise CheckFailedError(
                "Ask's lane did not carry the price list uploaded a moment before"
            )
        secret = {row[column] for row in prices.rows for column in WITHHELD}

        # The rows Ask reads for each reader, before anything redacts them.
        read = {
            role: await reader(RowRequest(), entitlement=reach[role], now=h.now) for role in held
        }
        if {len(one.records) for one in read.values()} != {SERVICES}:
            raise CheckFailedError(
                "readers of one price list were read different numbers of its rows, which counts "
                "what one of them was refused"
            )
        for role in narrow:
            for record in read[role].records:
                seen = record.model_dump()
                if set(WITHHELD) & set(seen) or secret & {str(value) for value in seen.values()}:
                    raise CheckFailedError(
                        "the rows Ask read for a reader without the cost grant carried the cost "
                        "or the margin"
                    )
        if any(not set(WITHHELD) <= set(one.model_dump()) for one in read["finance"].records):
            raise CheckFailedError(
                "the rows Ask read for a reader holding both grants left one out"
            )

        # The redactor, handed the rows that do carry the cost and the margin.
        for role in ("finance", *narrow):
            payload = redact(
                read["finance"], entitlement=reach[role], policy=policy, now=h.now
            ).payload
            kept = [set(one) for one in payload.records]
            wanted = {SELL_PRICE, *WITHHELD} if role == "finance" else {SELL_PRICE}
            if len(kept) != SERVICES or any(
                one & {SELL_PRICE, *WITHHELD} != wanted for one in kept
            ):
                raise CheckFailedError(
                    "the redactor, handed rows holding the cost and the margin, did not narrow "
                    "them to the sell price for a reader without the cost grant and leave them "
                    "whole with it"
                )

    # What the lane answers each of them, about each list's own service, over every rule it holds.
    nobody = h.word()
    for prices in lists:
        service = prices.rows[0]
        for role in narrow:
            told = await _ask(h, lane, people[role], reach[role], SELL_PRICE, service["name"])
            if told.text is None or service[SELL_PRICE] not in told.text:
                raise CheckFailedError(EACH_LIST_WAS_NOT_ANSWERED)
            for column in WITHHELD:
                withheld = await _ask(h, lane, people[role], reach[role], column, service["name"])
                absent = await _ask(h, lane, people[role], reach[role], column, nobody)
                if withheld.text is not None or withheld.frames != absent.frames:
                    raise CheckFailedError(
                        "a reader without the cost grant asking a service's cost or margin was "
                        "not answered as for a service that does not exist"
                    )
        for column in (SELL_PRICE, *WITHHELD):
            told = await _ask(h, lane, people["finance"], reach["finance"], column, service["name"])
            if told.text is None or service[column] not in told.text:
                raise CheckFailedError(
                    "a reader holding the cost and margin grants was not answered a service's "
                    "sell price, cost and margin"
                )


# ---------------------------------------------------------- 3. a mark applied (M7.5.3)
@check(
    leaves=("M7.5.3",),
    sentence=(
        "An administrator with a second factor marks a price list's margin restricted: the review "
        "names the cost as newly reachable and stores nothing; applied, the mark is stored, the "
        "epoch moves and 0116 ledgers it under their name, reach and request. A mark that would "
        "not load and a person without the write grant change nothing; to another department's "
        "administrator the list is missing, read or changed."
    ),
)
async def an_applied_mark_is_in_the_ledger_under_the_administrator(h: Harness) -> None:
    from brain.knowledge.columns import ColumnAccess, access_of

    await h.found_departments()
    admin = await _administrator(h)
    await _only_an_administrator_may_change(h, admin)
    prices = _price_list(h, "marked", PRICE_LIST_HEADINGS, PRICE_LIST_COLUMNS)
    await _upload(h, admin, prices, filename=f"{prices.entity}.csv", content=prices.csv())
    tables = _tables(h)

    proposed = await _review(h, admin, prices.entity, "margin", ColumnAccess.RESTRICTED)
    if (
        proposed.would_not_load
        or not proposed.widens
        or "cost" not in proposed.exposed
        or proposed.epoch_now == proposed.epoch_after
    ):
        raise CheckFailedError(
            "the review of a mark dropping the margin's derivation did not name the cost as newly "
            "reachable"
        )
    # Neither the review nor a refused mark can write: each is the route's own sequence, which
    # stops before the store. That they did not is read off the ledger at the end, which holds
    # the upload's entry and the apply's and nothing else.
    for column, access in ((h.word().lower(), ColumnAccess.OPEN), ("margin", ColumnAccess.DERIVED)):
        refused = await _apply(h, admin, prices.entity, column, access)
        if refused.applied or not refused.review.would_not_load:
            raise CheckFailedError(
                "a mark on a column the table does not carry, or a derived mark naming no input, "
                "was applied"
            )

    applied = await _apply(h, admin, prices.entity, "margin", ColumnAccess.RESTRICTED)
    kept = await tables.table(prices.entity)
    rule = None if kept is None else kept.classification.rule_for("margin")
    if (
        not applied.applied
        or applied.review != proposed
        or kept is None
        or rule is None
        or access_of(prices.entity, rule) is not ColumnAccess.RESTRICTED
        or kept.classification.policy().epoch() != proposed.epoch_after
        or applied.classification.epoch != proposed.epoch_after
    ):
        raise CheckFailedError(
            "an applied mark was not stored as the uploaded table's classification"
        )
    # See AN_APPLIED_MARK_IS_ATTRIBUTED_BY_ITS_OWN_REQUEST.
    reach = admin.reach.ent_hash()
    expected = [
        _Entry(
            admin.principal_id,
            "setting",
            reach,
            f"{h.trace_id}{trace}",
            change,
            "classified_table",
            False,
        )
        for trace, change in ((UPLOAD_TRACE, "uploaded"), (MARK_TRACE, "classified"))
    ]
    if await _entries(h, prices.entity) != expected:
        raise CheckFailedError(
            "the upload and the applied mark did not reach the ledger once each, as 0116's entries "
            "under the administrator's name, reach and request"
        )

    # Last, so every guard above is reached first. See
    # ANOTHER_DEPARTMENT_S_TABLE_IS_REFUSED_AS_A_MISSING_ONE.
    elsewhere = await _administrator(h, B)
    theirs = _price_list(h, "theirs", PRICE_LIST_HEADINGS, PRICE_LIST_COLUMNS, department=B)
    await _upload(h, elsewhere, theirs, filename=f"{theirs.entity}.csv", content=theirs.csv())
    if (
        await _changeable(h, admin, theirs.entity) is not None
        or await _changeable(h, admin, f"{theirs.entity}_nowhere") is not None
        or await _changeable(h, admin, prices.entity) is None
        or await _changeable(h, elsewhere, theirs.entity) is None
        or await _changeable(h, admin, theirs.entity, reading=True) is not None
        or await _changeable(h, admin, f"{theirs.entity}_nowhere", reading=True) is not None
        or await _changeable(h, admin, prices.entity, reading=True) is None
    ):
        raise CheckFailedError(ANOTHER_DEPARTMENT_S_TABLE_WAS_TOLD_APART)
