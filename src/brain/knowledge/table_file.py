"""Reading a price list out of a CSV or an XLSX file, and nothing else out of either.

A price list arrives as a spreadsheet, and what the classification needs from it is a heading
row and the cells under it. So this reads exactly that: the first sheet of a workbook or the
whole of a CSV, as text, into `ParsedTable`. No formula is evaluated, no style is read, no
second sheet is looked at, and the file itself is kept nowhere: once the cells are read the
bytes are dropped, so there is no original for anything to serve, scan later or leak.

**XLSX is read with the standard library, and no spreadsheet dependency was added.** The brief
allowed `openpyxl` through the licence and dependency sweeps if XLSX needed it. It does not: a
workbook is a zip of XML parts, and the four parts a first sheet's values live in
(`workbook.xml`, its relationships, `sharedStrings.xml` and the sheet) are read here with
`zipfile` and `xml.etree`. A library that understands charts, styles and pivot tables is a
larger surface parsing untrusted bytes than a reader that understands four elements. What that
costs is stated: a cell holding a formula is read as the value Excel last cached for it, and a
workbook saved by a tool that caches none reads that cell as empty.

**Every bound is enforced before the thing it bounds is built.** The declared size of each zip
member is checked before it is inflated, and it is a claim the file makes about itself, so the
inflation is also cut off at the same bound while it runs; a document type declaration is
refused before any XML is parsed, which closes entity expansion whatever the parser's own
defaults are; rows, columns and cell lengths are counted as they arrive. An upload is a small
file, and a bound that only applies after the whole of something is in memory has already
cost what admitting it would have.

**A refusal says what is wrong with the file, in a sentence the uploader can act on.** They
are an administrator holding the file, so naming the heading that is missing or the row that
is too long discloses nothing to them.

Rejected: guessing an encoding for a CSV that is not UTF-8. Every byte string decodes as
cp1252, so a guess never fails, and a price list read in the wrong encoding stores a product
name nobody can ask for by its real spelling. The file is refused and the sentence says how to
save it as UTF-8.

Task ids: M7.5.1, M7.7.3
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final
from xml.etree import ElementTree

from brain.knowledge.columns import ColumnClassificationError, column_name_for

#: The largest file accepted, after base64 decoding. A price list of a few thousand rows is
#: tens of kilobytes; two mebibytes is far past that and small enough to hold in memory.
MAX_TABLE_FILE_BYTES: Final = 2 * 1024 * 1024

#: The largest any one part of a workbook may inflate to. Checked against the declared size
#: and again while inflating, because the declared size is the file's own claim.
MAX_PART_BYTES: Final = 16 * 1024 * 1024

#: How many rows, columns and characters per cell a table may carry.
MAX_TABLE_ROWS: Final = 10_000
MAX_TABLE_COLUMNS: Final = 40
MAX_CELL_CHARS: Final = 1_000

#: How far along a sheet row a cell may sit before the row is refused unread. Wider than
#: `MAX_TABLE_COLUMNS`, so a stray value past the headings is refused in the heading check's
#: own words ("a value under no heading") rather than in this one's.
MAX_SHEET_COLUMNS: Final = 256

#: The two formats read, by extension. A file is read by what it says it is and then held to
#: it: a `.xlsx` that is not a zip is refused rather than retried as a CSV.
CSV_SUFFIX: Final = ".csv"
XLSX_SUFFIX: Final = ".xlsx"
TABLE_SUFFIXES: Final = frozenset({CSV_SUFFIX, XLSX_SUFFIX})

#: The spreadsheet namespace every element below is in, and the relationships one.
_MAIN: Final = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_ID: Final = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_PACKAGE_REL: Final = "{http://schemas.openxmlformats.org/package/2006/relationships}"

#: A cell reference, `AB12`, of which only the letters are read.
_CELL_REF: Final = re.compile(r"^([A-Z]{1,3})[0-9]+$")

#: What a document type declaration begins with. Refused in any part before parsing, so
#: entity expansion is closed by this module rather than by whichever expat is linked.
_DOCTYPE: Final = b"<!DOCTYPE"


class TableFileError(Exception):
    """A file that is not a table this module can read, with the reason in the uploader's words."""


@dataclass(frozen=True)
class ParsedTable:
    """The heading row as written, the column names it became, and every row under it.

    `rows` maps a column name to the cell's text; an empty cell is absent rather than an empty
    string, so a blank cost reads as no cost rather than as a cost of nothing.
    """

    headings: tuple[str, ...]
    columns: tuple[str, ...]
    rows: tuple[Mapping[str, str], ...]


def is_a_table_file(filename: str) -> bool:
    """Whether a file is one this module reads, by its extension.

    The question a document upload asks first (M7.7.3): a price list uploaded as a document is
    offered for conversion to classified rows rather than indexed as text, and the offer is
    made for exactly the files this module could convert.
    """
    return PurePosixPath(filename.casefold()).suffix in TABLE_SUFFIXES


def read_table_file(filename: str, content: bytes) -> ParsedTable:
    """The table in a CSV or an XLSX file, or a `TableFileError` saying why there is none."""
    if len(content) > MAX_TABLE_FILE_BYTES:
        msg = f"the file is larger than {MAX_TABLE_FILE_BYTES // (1024 * 1024)} MiB"
        raise TableFileError(msg)
    suffix = PurePosixPath(filename.casefold()).suffix
    if suffix == CSV_SUFFIX:
        grid = _csv_grid(content)
    elif suffix == XLSX_SUFFIX:
        grid = _xlsx_grid(content)
    else:
        msg = "only a .csv or an .xlsx file can be read as a table"
        raise TableFileError(msg)
    return _table(grid)


def _table(grid: Iterator[list[str]]) -> ParsedTable:
    """The first non-empty row as headings, and every non-empty row after it as a record."""
    headings: list[str] | None = None
    columns: list[str] = []
    rows: list[dict[str, str]] = []
    for line, cells in enumerate(grid, start=1):
        if not any(cell.strip() for cell in cells):
            continue
        if any(len(cell) > MAX_CELL_CHARS for cell in cells):
            msg = f"row {line} has a cell longer than {MAX_CELL_CHARS} characters"
            raise TableFileError(msg)
        if headings is None:
            headings, columns = _headings(cells)
            continue
        if len([c for c in cells[len(headings) :] if c.strip()]) > 0:
            msg = f"row {line} has a value under no heading"
            raise TableFileError(msg)
        if len(rows) >= MAX_TABLE_ROWS:
            msg = f"the table has more than {MAX_TABLE_ROWS} rows"
            raise TableFileError(msg)
        rows.append(
            {
                column: cell.strip()
                for column, cell in zip(columns, cells, strict=False)
                if cell.strip()
            }
        )
    if headings is None:
        msg = "the file has no heading row"
        raise TableFileError(msg)
    if not rows:
        msg = "the file has a heading row and no rows under it"
        raise TableFileError(msg)
    return ParsedTable(headings=tuple(headings), columns=tuple(columns), rows=tuple(rows))


def _headings(cells: Sequence[str]) -> tuple[list[str], list[str]]:
    """The heading row, trailing blanks dropped, and the column name each heading becomes."""
    headings = [cell.strip() for cell in cells]
    while headings and not headings[-1]:
        headings.pop()
    if len(headings) > MAX_TABLE_COLUMNS:
        msg = f"the table has more than {MAX_TABLE_COLUMNS} columns"
        raise TableFileError(msg)
    columns: list[str] = []
    for position, heading in enumerate(headings, start=1):
        if not heading:
            msg = f"column {position} has no heading"
            raise TableFileError(msg)
        try:
            name = column_name_for(heading)
        except ColumnClassificationError as exc:
            raise TableFileError(str(exc)) from exc
        if name in columns:
            msg = f"two headings both become the column {name!r}; rename one of them"
            raise TableFileError(msg)
        columns.append(name)
    return headings, columns


# ---------------------------------------------------------------------------- CSV


def _csv_grid(content: bytes) -> Iterator[list[str]]:
    """Every row of a UTF-8 CSV, a byte order mark allowed, the delimiter sniffed from three."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        msg = 'the CSV is not UTF-8; save it as "CSV UTF-8" and upload it again'
        raise TableFileError(msg) from exc
    sample = text[:4096]
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    try:
        yield from csv.reader(io.StringIO(text, newline=""), dialect)
    except csv.Error as exc:
        msg = f"the CSV could not be read: {exc}"
        raise TableFileError(msg) from exc


# --------------------------------------------------------------------------- XLSX


def _xlsx_grid(content: bytes) -> Iterator[list[str]]:
    """Every row of a workbook's first sheet, as text."""
    try:
        book = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        msg = "the .xlsx file is not a workbook"
        raise TableFileError(msg) from exc
    with book:
        sheet = _first_sheet(book)
        shared = _shared_strings(book)
        root = _xml(book, sheet)
    data = root.find(f"{_MAIN}sheetData")
    if data is None:
        return
    for row in data.iter(f"{_MAIN}row"):
        yield _row_cells(row, shared)


def _part(book: zipfile.ZipFile, name: str) -> bytes:
    """One part of the workbook, inflated no further than `MAX_PART_BYTES`."""
    try:
        info = book.getinfo(name)
    except KeyError as exc:
        msg = f"the workbook has no {name}"
        raise TableFileError(msg) from exc
    if info.file_size > MAX_PART_BYTES:
        msg = "the workbook is larger than this reader accepts once unpacked"
        raise TableFileError(msg)
    with book.open(info) as stream:
        data = stream.read(MAX_PART_BYTES + 1)
    if len(data) > MAX_PART_BYTES:
        msg = "the workbook is larger than this reader accepts once unpacked"
        raise TableFileError(msg)
    return data


def _xml(book: zipfile.ZipFile, name: str) -> ElementTree.Element:
    """One part parsed, a document type declaration refused before parsing starts."""
    data = _part(book, name)
    if _DOCTYPE in data.upper():
        msg = "the workbook declares a document type, which a spreadsheet never needs"
        raise TableFileError(msg)
    try:
        # The refusal above is what defusedxml refuses by default: every entity attack needs a
        # document type declaration, and the standard parser resolves no external entity.
        return ElementTree.fromstring(data)  # noqa: S314 - declaration refused above
    except ElementTree.ParseError as exc:
        msg = f"the workbook's {name} is not readable XML"
        raise TableFileError(msg) from exc


def _first_sheet(book: zipfile.ZipFile) -> str:
    """The part holding the first sheet in the workbook's own order."""
    workbook = _xml(book, "xl/workbook.xml")
    sheets = workbook.find(f"{_MAIN}sheets")
    first = None if sheets is None else sheets.find(f"{_MAIN}sheet")
    if first is None:
        msg = "the workbook has no sheet"
        raise TableFileError(msg)
    wanted = first.get(_REL_ID, "")
    relations = _xml(book, "xl/_rels/workbook.xml.rels")
    for relation in relations.iter(f"{_PACKAGE_REL}Relationship"):
        if relation.get("Id") == wanted:
            target = relation.get("Target", "")
            # Targets are relative to `xl/`, or absolute from the package root.
            return target.lstrip("/") if target.startswith("/") else f"xl/{target}"
    msg = "the workbook's first sheet points at no part"
    raise TableFileError(msg)


def _shared_strings(book: zipfile.ZipFile) -> list[str]:
    """The workbook's string table, rich text flattened. Absent in a workbook with no text."""
    if "xl/sharedStrings.xml" not in book.namelist():
        return []
    table = _xml(book, "xl/sharedStrings.xml")
    return ["".join(t.text or "" for t in item.iter(f"{_MAIN}t")) for item in table]


def _column_index(reference: str | None, fallback: int) -> int:
    """The zero-based column of `AB12`, or the next position when a cell carries no reference."""
    found = _CELL_REF.match(reference or "")
    if found is None:
        return fallback
    index = 0
    for letter in found.group(1):
        index = index * 26 + (ord(letter) - ord("A") + 1)
    return index - 1


def _row_cells(row: ElementTree.Element, shared: Sequence[str]) -> list[str]:
    """One sheet row as a list of text, gaps where the sheet left cells out."""
    cells: list[str] = []
    for cell in row.iter(f"{_MAIN}c"):
        index = _column_index(cell.get("r"), len(cells))
        if index >= MAX_SHEET_COLUMNS:
            # A bound on the list built here, before the heading check can run: a cell at
            # column XFD would otherwise be a sixteen-thousand-entry row for one value.
            msg = f"the sheet has a value past column {MAX_SHEET_COLUMNS}"
            raise TableFileError(msg)
        while len(cells) <= index:
            cells.append("")
        cells[index] = _cell_text(cell, shared)
    return cells


def _cell_text(cell: ElementTree.Element, shared: Sequence[str]) -> str:
    """A cell's value as text: a shared string, an inline string, or the cached value."""
    kind = cell.get("t", "n")
    if kind == "inlineStr":
        inline = cell.find(f"{_MAIN}is")
        return "" if inline is None else "".join(t.text or "" for t in inline.iter(f"{_MAIN}t"))
    value = cell.find(f"{_MAIN}v")
    raw = "" if value is None or value.text is None else value.text
    if kind == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError) as exc:
            msg = "the workbook names a string its string table does not hold"
            raise TableFileError(msg) from exc
    if kind == "b":
        return "TRUE" if raw == "1" else "FALSE"
    return raw
