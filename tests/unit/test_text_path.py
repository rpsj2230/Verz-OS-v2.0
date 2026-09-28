"""The text path's scanner and parser, over real files built in memory.

`tests/fixtures/documents.py` builds each file, so a test names what is in it. Every parse runs
through `scan_for_parsing` and `parse_scanned`, the gates the route calls, rather than calling the
parser directly, because what M7.6.3 promises is the path and not the function.

Task ids: M7.6.3, M7.2.2, M7.2.5
"""

from __future__ import annotations

import pytest

from brain.knowledge import text_path
from brain.knowledge.chunking import Block, BlockKind
from brain.knowledge.ingest import (
    CAUSE_TEXT,
    IngestRefused,
    MediaType,
    ParseCause,
    ParseFailure,
    ScanVerdict,
    admit_upload,
)
from brain.knowledge.scanning import ParsedDocument, parse_scanned, scan_for_parsing
from brain.knowledge.text_path import (
    BLOCK_SEPARATOR,
    STRUCTURAL_CHECK,
    TABLES_ARE_VISIBLE,
    TEXT_PATH_TYPES,
    Drafted,
    StructuralCheck,
    TextPathParser,
    joined,
    laid_out,
    pipe_row,
)
from tests.fixtures.documents import (
    LINE,
    a_locked_pdf,
    a_pdf,
    a_word_document,
    a_zip,
    an_owner_locked_pdf,
    with_part,
)

DOCX = MediaType.DOCX.value


def verdict(content: bytes) -> ScanVerdict:
    report = StructuralCheck().scan(content)
    assert report.scanner == STRUCTURAL_CHECK
    return report.verdict


def read(
    content: bytes, media_type: MediaType, filename: str = "file"
) -> ParsedDocument | ParseFailure:
    """Admit, scan and parse, exactly as `brain.knowledge.uploads.read_for_text_path` does."""
    upload = admit_upload(filename=filename, declared_type=media_type.value, content=content)
    scanned = scan_for_parsing(upload, content, scanner=StructuralCheck())
    return parse_scanned(scanned, parser=TextPathParser())


def parsed(content: bytes, media_type: MediaType) -> tuple[Block, ...]:
    outcome = read(content, media_type)
    assert isinstance(outcome, ParsedDocument), outcome
    for block in outcome.blocks:
        assert joined(outcome.blocks)[block.start : block.end] == block.text
    return outcome.blocks


def failed(content: bytes, media_type: MediaType) -> ParseFailure:
    outcome = read(content, media_type, filename="the file.ext")
    assert isinstance(outcome, ParseFailure), outcome
    return outcome


# ------------------------------------------------------------------ the scanner
def test_a_word_document_a_pdf_and_utf8_text_are_cleared() -> None:
    """The positive case for every refusal below. Delete this and each of them is satisfied by a
    check that clears nothing, which on an install with no antivirus is every upload refused."""
    assert verdict(a_word_document(paragraphs=["Sign the list."])) is ScanVerdict.CLEAN
    assert verdict(a_pdf("Sign the list.")) is ScanVerdict.CLEAN
    assert verdict("Sign the list, café.".encode()) is ScanVerdict.CLEAN


def test_an_archive_part_that_expands_past_the_ratio_is_refused() -> None:
    """Delete this and a small zip whose one part inflates a thousandfold reaches python-docx,
    which holds the whole part in memory before it knows it is a bomb."""
    bomb = a_zip({"word/document.xml": bytes(4 * 1024 * 1024)})
    assert verdict(bomb) is ScanVerdict.INFECTED
    assert verdict(a_zip({"word/document.xml": b"<w:document/>"})) is ScanVerdict.CLEAN


def test_an_archive_whose_parts_add_up_past_the_ceiling_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and many parts each inside the ratio add up to more than any parse may hold.
    The ceiling is lowered for the test rather than a quarter of a gigabyte being built."""
    parts = {f"word/part{index}.bin": bytes(range(256)) * 4 for index in range(4)}
    assert verdict(a_zip(parts)) is ScanVerdict.CLEAN
    monkeypatch.setattr(text_path, "MAX_EXPANDED_BYTES", 3 * 1024)
    assert verdict(a_zip(parts)) is ScanVerdict.INFECTED


def test_an_archive_with_more_parts_than_a_document_has_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and an archive of thousands of parts is walked part by part before anything
    refuses it."""
    parts = {f"word/part{index}.xml": b"<x/>" for index in range(5)}
    assert verdict(a_zip(parts)) is ScanVerdict.CLEAN
    monkeypatch.setattr(text_path, "MAX_ARCHIVE_ENTRIES", 4)
    assert verdict(a_zip(parts)) is ScanVerdict.INFECTED


def test_an_encrypted_part_is_unscannable_rather_than_clean() -> None:
    """Delete this and a part nothing could look inside is cleared, which is the file crafted to
    defeat a scanner being the file that skips it."""
    assert verdict(a_zip({"word/document.xml": b"<w:document/>"}, encrypted=True)) is (
        ScanVerdict.UNSCANNABLE
    )


def test_a_word_document_carrying_macros_is_refused() -> None:
    """Delete this and a macro-enabled document renamed to .docx is accepted as a document."""
    document = a_word_document(paragraphs=["Sign the list."])
    assert verdict(with_part(document, "word/vbaProject.bin", b"macro")) is ScanVerdict.INFECTED


@pytest.mark.parametrize("part", ["word/document.xml", "word/_rels/document.xml.rels"])
def test_an_xml_part_declaring_entities_is_refused(part: str) -> None:
    """Delete this and a Word part or a relationships part declaring entities reaches the XML
    parser, which is the whole of the entity-expansion attack. Word never writes a DOCTYPE."""
    declared = b'<?xml version="1.0"?><!doctype x [<!ENTITY a "aaaa">]><x>&a;</x>'
    document = a_word_document(paragraphs=["Sign the list."])
    assert verdict(with_part(document, part, declared)) is ScanVerdict.INFECTED


def test_a_pdf_carrying_script_is_refused() -> None:
    """Delete this and a PDF whose opening action runs script is accepted as a document."""
    scripted = a_pdf("Sign the list.", extra="/OpenAction << /S /JavaScript /JS (go) >> ")
    assert verdict(scripted) is ScanVerdict.INFECTED


def test_text_that_is_not_utf8_past_its_head_is_unscannable() -> None:
    """The door sniffs the first sixteen bytes; this reads all of them. Delete this and a file
    that is text for sixteen bytes and binary after reaches the text reader."""
    assert verdict(b"Sixteen bytes ok" + bytes((0xFF, 0xFE, 0x00))) is ScanVerdict.UNSCANNABLE
    assert verdict(b"Sixteen bytes ok" + bytes(3)) is ScanVerdict.UNSCANNABLE


def test_a_container_this_path_does_not_read_is_unscannable() -> None:
    """Delete this and an image handed to this check is cleared by a check that never looked."""
    png = bytes((0x89,)) + b"PNG" + bytes((0x0D, 0x0A, 0x1A, 0x0A)) + bytes(16)
    assert verdict(png) is ScanVerdict.UNSCANNABLE


def test_a_refused_file_never_reaches_the_parser() -> None:
    """The gate, not the check alone: a macro file is refused by `scan_for_parsing`, by name."""
    document = with_part(a_word_document(paragraphs=["x"]), "word/vbaProject.bin", b"m")
    with pytest.raises(IngestRefused) as refused:
        read(document, MediaType.DOCX, filename="policy.docx")
    assert STRUCTURAL_CHECK in str(refused.value)


# ------------------------------------------------------------------ the parser
def test_markdown_is_cut_into_blocks_with_its_headings_as_sections_and_its_tables_whole() -> None:
    """Delete this and a Markdown table is cut across chunks, or a passage cites no section."""
    text = LINE.join(
        [
            "# Site handover",
            "",
            "Sign the TEALCHECK list before leaving.",
            "",
            "| Step | Who |",
            "| --- | --- |",
            "| Sign | Lead |",
            "",
            "## Afterwards",
            "",
            "File the list.",
        ]
    )
    blocks = parsed(text.encode(), MediaType.MARKDOWN)

    assert [block.kind for block in blocks] == [
        BlockKind.PROSE,
        BlockKind.PROSE,
        BlockKind.TABLE,
        BlockKind.PROSE,
        BlockKind.PROSE,
    ]
    assert [block.section for block in blocks] == [
        "Site handover",
        "Site handover",
        "Site handover",
        "Afterwards",
        "Afterwards",
    ]
    assert blocks[2].text.splitlines()[2] == "| Sign | Lead |"


def test_plain_text_has_no_headings_and_keeps_a_pipe_table() -> None:
    """Delete this and a line beginning with a hash in plain text is read as a heading."""
    blocks = parsed(
        LINE.join(["# not a heading", "", "| a | b |", "| c | d |"]).encode(), MediaType.PLAIN
    )
    assert [(block.kind, block.section) for block in blocks] == [
        (BlockKind.PROSE, ""),
        (BlockKind.TABLE, ""),
    ]


def test_a_pdf_is_read_page_by_page_with_its_page_numbers() -> None:
    """Delete this and a PDF passage cites no page, which is half of what a citation resolves to."""
    blocks = parsed(a_pdf("Sign the TEALCHECK list.", "File it afterwards."), MediaType.PDF)
    assert [(block.page, block.text) for block in blocks] == [
        (1, "Sign the TEALCHECK list."),
        (2, "File it afterwards."),
    ]
    assert not TABLES_ARE_VISIBLE[MediaType.PDF]


def test_a_pdf_with_a_password_to_open_is_refused_naming_the_cause() -> None:
    """M7.2.5. Delete this and a locked PDF is reported as corrupt, which tells the uploader to
    re-export a file whose only problem is its password."""
    failure = failed(a_locked_pdf("Sign the list."), MediaType.PDF)
    assert failure.cause is ParseCause.ENCRYPTED
    assert CAUSE_TEXT[ParseCause.ENCRYPTED] in failure.message()


def test_a_pdf_with_restrictions_and_no_password_to_open_is_read() -> None:
    """Delete this and most "protected" PDFs, which need no password to open, are refused."""
    blocks = parsed(an_owner_locked_pdf("Sign the TEALCHECK list."), MediaType.PDF)
    assert [block.text for block in blocks] == ["Sign the TEALCHECK list."]


def test_a_pdf_with_no_text_layer_names_that_cause() -> None:
    """Delete this and a scanned PDF becomes an item that answers nothing while looking indexed."""
    assert failed(a_pdf(""), MediaType.PDF).cause is ParseCause.NO_TEXT_LAYER


def test_a_damaged_pdf_names_that_cause() -> None:
    """Delete this and a truncated PDF raises out of the parser, which the route answers as a
    fault rather than telling the uploader to re-export it."""
    assert failed(b"%PDF-1.4" + bytes(40), MediaType.PDF).cause is ParseCause.CORRUPT


def test_a_word_document_keeps_its_heading_as_a_section_and_its_table_whole_in_order() -> None:
    """M7.2.2 for Word. Delete this and a Word table becomes scrambled prose, or is read out of
    reading order, and a citation to it points at the paragraph beside it."""
    document = a_word_document(
        heading="Price list notes",
        paragraphs=["Prices move each quarter."],
        table=[["Service", "Price"], ["Audit | full", "1,200"]],
        after=["Ask finance first."],
    )
    blocks = parsed(document, MediaType.DOCX)

    assert [block.kind for block in blocks] == [BlockKind.PROSE, BlockKind.TABLE, BlockKind.PROSE]
    assert blocks[0].text == LINE.join(["Price list notes", "Prices move each quarter."])
    assert blocks[1].text == LINE.join(["| Service | Price |", "| Audit / full | 1,200 |"])
    assert {block.section for block in blocks} == {"Price list notes"}
    assert TABLES_ARE_VISIBLE[MediaType.DOCX]


def test_a_zip_that_is_not_a_word_document_is_unsupported() -> None:
    """The question the door leaves for the parser. Delete this and an ordinary zip declared as
    Word is reported as damaged rather than as the wrong kind of file."""
    assert failed(a_zip({"notes.xml": b"<n/>"}), MediaType.DOCX).cause is ParseCause.UNSUPPORTED


def test_a_type_outside_the_text_path_is_unsupported_by_the_parser() -> None:
    """Delete this and a CSV handed to this parser is read as something."""
    assert MediaType.CSV not in TEXT_PATH_TYPES
    assert failed(b"a,b" + LINE.encode() + b"1,2", MediaType.CSV).cause is ParseCause.UNSUPPORTED


# ------------------------------------------------------------------ laying out
def test_blocks_are_laid_out_one_blank_line_apart_at_the_offsets_they_sit_at() -> None:
    """Delete this and a block's offset can drift from where its words are, and every citation
    to it points a few characters off."""
    blocks = laid_out([Drafted(text="  first  "), Drafted(text=""), Drafted(text="second", page=2)])
    assert [(block.start, block.text, block.page) for block in blocks] == [
        (0, "first", None),
        (len("first") + len(BLOCK_SEPARATOR), "second", 2),
    ]
    assert joined(blocks) == "first" + BLOCK_SEPARATOR + "second"


def test_a_block_that_is_not_where_its_words_are_is_refused() -> None:
    """The refusal `joined` makes, reached. Delete this and a layout whose offsets disagree with
    its content is written, and its citations point at other words."""
    wrong = (
        Block(kind=BlockKind.PROSE, text="first", start=0),
        Block(kind=BlockKind.PROSE, text="second", start=5),
    )
    with pytest.raises(IngestRefused):
        joined(wrong)


def test_a_pipe_inside_a_cell_cannot_open_a_new_column() -> None:
    """Delete this and a cell holding a pipe renders as two cells, shifting every column after
    it under the wrong heading."""
    assert pipe_row(["a | b", " c  d "]) == "| a / b | c d |"
