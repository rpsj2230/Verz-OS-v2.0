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
`THE_ROUTES_GATE_IS_RESTATED_AND_HELD_TO_THE_ROUTES_OWN`. Rejected: calling the route functions with
a caller whose verified claims the check wrote, which would put a signature nobody checked where the
product keeps only ones it did.

**Ask is asked on its own lane, with no model, over the check's own table's questions.**
`brain.ops.classification_store.classified_lane_of` builds the lane from every live table as the
answer route does, and `brain.gate.answer.answer_lane` answers over its readers and its policies, so
the projection, the redactor, the abstention and the frames a person receives are the install's.
The one narrowing is which question shapes are matched, for
`THE_CHECK_MATCHES_ONLY_ITS_OWN_TABLE_S_QUESTIONS`. Rejected: columns renamed for the run, which
would dodge the collision and prove nothing about a price list, because only the product's own
column names are classified by `brain.knowledge.columns.first_classification`.

**What a reader is refused is looked for in three places, because it is withheld in three.** The
rows Ask reads for the reader, the redactor handed rows that do carry the cost, and the frames the
lane answers with. Each layer withholds on its own, so a check reading only the answer would stay
green with the projection gone, and one reading only the rows would stay green with the redactor
gone. A reader holding the margin grant and not the cost grant is asked as well, because withholding
the margin from them is the derivation and nothing else.

**Every name is the run's.** Tables are `acceptance_<run>_...`, every value and every service name
is a word nothing else holds, and every grant is scoped to acceptance_a. The classification grants
are held as `_may_change` asks for them, which is whether they are held at all, so their scope
narrows nothing about a table; the only table the administrator changes is the run's own. A table a
reader asks about places its rows in acceptance_a through a department column the administrator
marks open, because a department grant is judged against that column on every row.

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
    from brain.gate.fast_lane import FastPathRule
    from brain.knowledge.classified_rows import ClassifiedLane, StoredTable
    from brain.knowledge.columns import ColumnAccess
    from brain.ops.classification_store import ClassifiedTables

A: Final = RESERVED_DEPARTMENTS[0]

# ------------------------------------------------------------------ written-down reasons
#: Why the check asks the gate the routes ask, and how the two are kept one.
THE_ROUTES_GATE_IS_RESTATED_AND_HELD_TO_THE_ROUTES_OWN: Final = (
    "The Classification routes ask a signed-in request whether its reach holds both "
    "classification grants. A check signs nobody in, so it asks the same two grants of a reach "
    "the one resolver loaded and admit narrowed for a console session, and a test holds this "
    "function to the route's own over every combination of grants and sign-in, so the two cannot "
    "part without a red build."
)

#: Why the lane is asked with the check's own table's question shapes and no others.
THE_CHECK_MATCHES_ONLY_ITS_OWN_TABLE_S_QUESTIONS: Final = (
    "Every uploaded table with a sell price column is asked about in the same words, so on an "
    "install that holds a price list of its own, 'what is the sell price of' a service matches "
    "two rules and the lane answers nobody. The check matches the question against its own "
    "table's rules alone; the readers, the policies, the projection, the redactor and the frames "
    "are the lane's as the answer route builds it on this install."
)

#: Why each write the check makes carries a trace of its own.
AN_APPLIED_MARK_IS_ATTRIBUTED_BY_ITS_OWN_REQUEST: Final = (
    "The three settings a trigger reads last for the transaction, and a check is one transaction, "
    "so an upload's attribution is still standing when a mark is applied after it. Each write "
    "the check makes therefore carries a trace of its own, as two requests would: an entry naming "
    "the mark's trace can only have come from the apply's own settings, and a store that set none "
    "would leave the upload's trace on the entry, which the check reads as a failure."
)

# ------------------------------------------------------------ the words a failure is said in
A_PRICE_LIST_WAS_REFUSED: Final = (
    "a well-formed price list, uploaded as a CSV or an XLSX, was refused as the upload route "
    "refuses one"
)

# ------------------------------------------------------------------------ the figures
#: A price list's headings as somebody types them: the four the shipped price list classifies, and
#: one it does not.
PRICE_LIST_HEADINGS: Final = ("Name", "Sell Price", "Cost", "Margin", "Notes")

#: The column each of those headings is held under, written out rather than derived, so the
#: product's parser is held to it by a test instead of agreeing with itself.
PRICE_LIST_COLUMNS: Final = ("name", "sell_price", "cost", "margin", "notes")

#: A price list a reader asks about: the same columns, placed in a department.
ASKED_HEADINGS: Final = ("Name", "Department", "Sell Price", "Cost", "Margin")
ASKED_COLUMNS: Final = ("name", "department", "sell_price", "cost", "margin")

#: How a first upload of `PRICE_LIST_HEADINGS` classifies each column: its mark and its inputs, as
#: `brain.knowledge.columns.PRICE_LIST` ships them and default-deny leaves the rest.
FIRST_MARKS: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "name": ("open", ()),
    "sell_price": ("open", ()),
    "cost": ("derived", ("margin", "sell_price")),
    "margin": ("derived", ("cost", "sell_price")),
    "notes": ("restricted", ()),
}

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
    h: Harness, what: str, headings: Sequence[str], columns: Sequence[str]
) -> _PriceList:
    """`SERVICES` services, every value a word nothing else holds, any department acceptance_a."""
    rows = []
    for _ in range(SERVICES):
        row = {column: h.word() for column in columns}
        if "department" in row:
            row["department"] = A
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


async def _administrator(h: Harness) -> _Administrator:
    """A reserved person of acceptance_a holding both classification grants, let through the
    routes' gate. Every request the check makes as them is made at this one reach and one instant,
    so the gate asked once here is the answer each of those requests would be given."""
    from brain.classification_routes import CLASSIFICATION_READ, CLASSIFICATION_WRITE

    made = h.principal(A, "classifier")
    await h.person(
        made,
        department=A,
        grants=_in(A, CLASSIFICATION_READ.value, CLASSIFICATION_WRITE.value),
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
    file. The gate is `_administrator`'s."""
    from brain.classification_routes import TableUpload, _upload_refusal, view_of
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
        table = next_upload(
            await tables.table(prices.entity),
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


async def _marked_table(h: Harness, entity: str) -> StoredTable:
    """The mark routes' opening after their gate: the uploaded table, or the one refusal."""
    stored = await _tables(h).table(entity)
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

    stored = await _marked_table(h, entity)
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

    stored = await _marked_table(h, entity)
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
    rules: Sequence[FastPathRule],
    person: Principal,
    reach: EntitlementSet,
    column: str,
    service: str,
) -> Answered:
    """One question in the first shape a table is asked in, answered on Ask's lane with no
    model, no cache and no recorder. See `THE_CHECK_MATCHES_ONLY_ITS_OWN_TABLE_S_QUESTIONS`."""
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
        rules=rules,
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
        "On Ask's own lane, with no model, a reader holding an uploaded price list without the "
        "cost grant is answered a service's sell price, and asking its cost or margin is answered "
        "as if the service did not exist; with the margin grant and not the cost grant, neither; "
        "with both, all three. The rows read and the redactor withhold the same two columns."
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
    prices = _price_list(h, "prices", ASKED_HEADINGS, ASKED_COLUMNS)
    await _upload(h, admin, prices, filename=f"{prices.entity}.csv", content=prices.csv())
    opened = await _apply(h, admin, prices.entity, "department", ColumnAccess.OPEN)
    if not opened.applied:
        raise CheckFailedError("an uploaded price list's department column could not be opened")

    table = table_capability(prices.entity).value
    cost, margin = (column_capability(prices.entity, one).value for one in WITHHELD)
    held = {"sales": (table,), "short": (table, margin), "finance": (table, cost, margin)}
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
    reader = lane.readers.get((TABLES_SOURCE, prices.entity))
    policy = lane.policies.get(prices.entity)
    rules = tuple(one for one in lane.rules if one.entity == prices.entity)
    if reader is None or policy is None or not rules:
        raise CheckFailedError("Ask's lane did not carry the price list uploaded a moment before")
    secret = {row[column] for row in prices.rows for column in WITHHELD}

    # The rows Ask reads for each reader, before anything redacts them.
    read = {role: await reader(RowRequest(), entitlement=reach[role], now=h.now) for role in held}
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
                    "the rows Ask read for a reader without the cost grant carried the cost or "
                    "the margin"
                )
    if any(not set(WITHHELD) <= set(one.model_dump()) for one in read["finance"].records):
        raise CheckFailedError("the rows Ask read for a reader holding both grants left one out")

    # The redactor, handed the rows that do carry the cost and the margin.
    for role in ("finance", *narrow):
        payload = redact(read["finance"], entitlement=reach[role], policy=policy, now=h.now).payload
        kept = [set(one) for one in payload.records]
        wanted = {SELL_PRICE, *WITHHELD} if role == "finance" else {SELL_PRICE}
        if len(kept) != SERVICES or any(one & {SELL_PRICE, *WITHHELD} != wanted for one in kept):
            raise CheckFailedError(
                "the redactor, handed rows holding the cost and the margin, did not narrow them to "
                "the sell price for a reader without the cost grant and leave them whole with it"
            )

    # What the lane answers each of them.
    service, nobody = prices.rows[0], h.word()
    for role in narrow:
        told = await _ask(h, lane, rules, people[role], reach[role], SELL_PRICE, service["name"])
        if told.text is None or service[SELL_PRICE] not in told.text:
            raise CheckFailedError("a reader holding the price list was not answered a sell price")
        for column in WITHHELD:
            withheld = await _ask(
                h, lane, rules, people[role], reach[role], column, service["name"]
            )
            absent = await _ask(h, lane, rules, people[role], reach[role], column, nobody)
            if withheld.text is not None or withheld.frames != absent.frames:
                raise CheckFailedError(
                    "a reader without the cost grant asking a service's cost or margin was not "
                    "answered as for a service that does not exist"
                )
    for column in (SELL_PRICE, *WITHHELD):
        told = await _ask(
            h, lane, rules, people["finance"], reach["finance"], column, service["name"]
        )
        if told.text is None or service[column] not in told.text:
            raise CheckFailedError(
                "a reader holding the cost and margin grants was not answered a service's sell "
                "price, cost and margin"
            )


# ---------------------------------------------------------- 3. a mark applied (M7.5.3)
@check(
    leaves=("M7.5.3",),
    sentence=(
        "On an uploaded price list an administrator with a second factor marks the margin "
        "restricted: the review names the cost as newly reachable and stores nothing; applied, the "
        "mark is stored, the policy epoch moves, and obs.audit_entry holds 0116's classified entry "
        "under the administrator's name, reach and request. A mark that would not load, and "
        "anybody without the write grant, change nothing."
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
