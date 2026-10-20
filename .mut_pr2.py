from pathlib import Path

from brain.ops.mutation import Mutation, verify

DOC = "src/inference_server/parts/documents.py"
LAY = "src/inference_server/parts/layout.py"
OCR = "src/inference_server/parts/ocr.py"
TIKA = "src/inference_server/parts/tika.py"
SUP = "src/inference_server/supervisor.py"
FETCH = "src/inference_server/fetch.py"
POCR = "src/brain/knowledge/parse_ocr.py"
ROUTE = "src/brain/knowledge/model_server_parsers.py"
UP = "src/brain/knowledge/uploads.py"
TP = "src/brain/knowledge/text_path.py"
SC = "src/brain/knowledge/scanning.py"
IQ = "src/brain/knowledge/ingest_queue.py"
DS = "src/brain/knowledge/document_services.py"
CL = "src/brain/ops/model_server_client.py"
WK = "src/brain/ops/worker.py"
AC = "src/brain/ops/acceptance_checks_modelserver.py"

T_SRV = ("tests/unit/test_inference_server_documents.py",)
T_SUP = ("tests/unit/test_inference_server_documents.py", "tests/unit/test_inference_server.py")
T_PAR = (
    "tests/unit/test_model_server_parsers.py",
    "tests/unit/test_parse_ocr.py",
    "tests/unit/test_scanning.py",
)
T_UP = ("tests/unit/test_model_server_parsers.py", "tests/unit/test_knowledge_upload.py")
T_IMG = (
    "tests/unit/test_model_server_parsers.py",
    "tests/unit/test_text_path.py",
    "tests/unit/test_scanners.py",
)

mutations = [
    Mutation(
        "a block is laid out one character from where the separator puts it",
        DOC,
        "start += len(text) + len(BLOCK_SEPARATOR)",
        "start += len(text) + 1",
        T_SRV,
    ),
    Mutation("a NUL is kept in a block", DOC, r'replace("\x00", "")', r'replace("\x01", "")', T_SRV),
    Mutation(
        "a fifth cause at a valid stage may be declared",
        DOC,
        "if cause not in CAUSES or stage not in STAGES:",
        "if cause not in CAUSES and stage not in STAGES:",
        T_SRV,
    ),
    Mutation(
        "a password exception is not told as encrypted",
        DOC,
        'if "password" in name or "encrypt" in name:',
        'if "encrypt" in name:',
        T_SRV,
    ),
    Mutation(
        "every library failure is told as corrupt",
        DOC,
        'if "corrupt" in name:',
        "if True:",
        T_SRV,
    ),
    Mutation(
        "page furniture is indexed",
        LAY,
        "if item.label in LEFT_OUT_LABELS:",
        "if False:",
        T_SRV,
    ),
    Mutation(
        "a heading does not open a section",
        LAY,
        "if item.label in HEADING_LABELS:",
        "if False:",
        T_SRV,
    ),
    Mutation(
        "a table is read as prose",
        LAY,
        'kind = "table" if item.label in TABLE_LABELS else "prose"',
        'kind = "prose"',
        T_SRV,
    ),
    Mutation(
        "our own mistake is read as a fact about the document",
        LAY,
        "except OUR_OWN_MISTAKES:",
        "except ZeroDivisionError:",
        T_SRV,
    ),
    Mutation(
        "a word with no confidence figure counts as sure",
        OCR,
        "word.text.strip() and word.confidence >= 0]",
        "word.text.strip()]",
        T_SRV,
    ),
    Mutation(
        "a row the engine marks as not a word is a word",
        OCR,
        "if not word.text.strip() or word.confidence < 0:",
        "if not word.text.strip():",
        T_SRV,
    ),
    Mutation(
        "the page cap is one page over",
        OCR,
        "if len(pages) >= MAX_PAGES:",
        "if len(pages) > MAX_PAGES:",
        T_SRV,
    ),
    Mutation(
        "a locked PDF is any pdfium error",
        OCR,
        'if getattr(error, "err_code", None) == 4:',
        "if True:",
        T_SRV,
    ),
    Mutation(
        "a 422 from the general reader is an outage",
        TIKA,
        "UNSUPPORTED_STATUSES: Final = frozenset({415, 422})",
        "UNSUPPORTED_STATUSES: Final = frozenset({415})",
        T_SRV,
    ),
    Mutation("a server error is read as text", TIKA, "if status != 200:", "if False:", T_SRV),
    Mutation(
        "a dead JVM is not noticed before the request",
        TIKA,
        "        if not self._alive():\n            raise SystemExit(JVM_GONE)\n        try:",
        "        try:",
        T_SRV,
    ),
    Mutation("the JVM heap is not the budgeted one", TIKA, "HEAP_MIB: Final = 384", "HEAP_MIB: Final = 385", T_SRV),
    Mutation(
        "ending a part leaves what it started running",
        SUP,
        "        # Whatever the part started and did not wait for: a part that ended by itself leaves its\n"
        "        # children in the group, and they are the memory this call exists to give back.\n"
        "        self._signal_group(process, signal.SIGKILL)\n",
        "",
        T_SUP,
    ),
    Mutation(
        "a part shares its parent's process group",
        SUP,
        "            start_new_session=True,\n",
        "",
        T_SUP,
    ),
    Mutation(
        "a floor at exactly the figure drops the page",
        POCR,
        "figure.get(block.page, 0.0) >= OCR_FLOOR_CONFIDENCE",
        "figure.get(block.page, 0.0) > OCR_FLOOR_CONFIDENCE",
        T_PAR,
    ),
    Mutation(
        "a blank page is named as left out",
        POCR,
        "had_text = {block.page for block in blocks if block.page is not None}",
        "had_text = {one.page for one in pages}",
        T_PAR,
    ),
    Mutation(
        "the kept blocks keep the offsets they had",
        POCR,
        "return OcrReading(blocks=relaid, confidence=confidence, left_out_pages=left_out)",
        "return OcrReading(blocks=tuple(kept), confidence=confidence, left_out_pages=left_out)",
        T_PAR,
    ),
    Mutation(
        "a page named twice is believed",
        POCR,
        "if isinstance(page, bool) or not isinstance(page, int) or page in seen:",
        "if isinstance(page, bool) or not isinstance(page, int):",
        T_PAR,
    ),
    Mutation(
        "a boolean figure is a confidence",
        POCR,
        "if isinstance(figure, bool) or not isinstance(figure, (int, float)):",
        "if not isinstance(figure, (int, float)):",
        T_PAR,
    ),
    Mutation(
        "page runs are not joined",
        POCR,
        "if runs and page == runs[-1][-1] + 1:",
        "if runs and page == runs[-1][-1] + 2:",
        T_PAR,
    ),
    Mutation(
        "a parser that leaves pages out says nothing of them",
        POCR,
        "        if outcome.left_out_pages:\n",
        "        if False:\n",
        T_PAR,
    ),
    Mutation(
        "the gate drops the pages a parser left out",
        SC,
        "left_out = outcome.left_out_pages if isinstance(outcome, ReadWithGaps) else ()",
        "left_out = ()",
        T_PAR,
    ),
    Mutation(
        "a route is built for an install with no reader",
        ROUTE,
        "    if not services.any:\n        return ()\n",
        "",
        T_PAR,
    ),
    Mutation(
        "a PDF is read by the scanned-page reader first",
        ROUTE,
        "route = [*layout, *text, *ocr]",
        "route = [*ocr, *text, *layout]",
        T_PAR,
    ),
    Mutation(
        "a block on a page nobody scored is believed",
        ROUTE,
        "if pages is None or any(block.page not in figured for block in decoded):",
        "if pages is None:",
        T_PAR,
    ),
    Mutation(
        "a layout read is judged as blind as a text layer",
        UP,
        "sees_tables = provenance.path is ParsePath.LAYOUT or tables_visible.get(media_type, False)",
        "sees_tables = tables_visible.get(media_type, False)",
        T_UP,
    ),
    Mutation(
        "a header at exactly the pixel bound is refused",
        TP,
        "if size[0] * size[1] > MAX_IMAGE_PIXELS:",
        "if size[0] * size[1] >= MAX_IMAGE_PIXELS:",
        T_IMG,
    ),
    Mutation(
        "a header claiming no pixels is cleared",
        TP,
        "if size is None or size[0] < 1 or size[1] < 1:",
        "if size is None:",
        T_IMG,
    ),
    Mutation(
        "a PNG with no header chunk is read for a size anyway",
        TP,
        'if len(content) < 24 or content[12:16] != b"IHDR":',
        "if len(content) < 24:",
        T_IMG,
    ),
    Mutation(
        "an outage ends a document instead of waiting",
        IQ,
        "        if read.is_retryable:\n",
        "        if False:\n",
        ("tests/unit/test_ingest_queue.py",),
    ),
    Mutation(
        "a process with no database sends documents to the server",
        DS,
        "if sessions is None or not is_switched_on(env):",
        "if not is_switched_on(env):",
        ("tests/unit/test_document_services.py",),
    ),
    Mutation(
        "the feature switch is not asked",
        DS,
        "    if not await model_server_is_on(sessions):\n        return frozenset()\n",
        "",
        ("tests/unit/test_document_services.py",),
    ),
    Mutation(
        "the embedding part is a reader of documents",
        DS,
        "if part in DOCUMENT_PARTS",
        "if True",
        ("tests/unit/test_document_services.py",),
    ),
    Mutation(
        "an open breaker still sends",
        CL,
        "        if not admitted:\n",
        "        if False:\n",
        ("tests/unit/test_model_server_client.py",),
    ),
    Mutation(
        "an answer that is not an object is read as empty",
        CL,
        "        if not isinstance(payload, Mapping):\n            return Reply(CallOutcome.REJECTED)\n",
        "",
        ("tests/unit/test_model_server_client.py",),
    ),
    Mutation(
        "a failing observer costs the answer",
        CL,
        "        except Exception as error:\n            log.warning(\"the model server's peak was not kept\", error=type(error).__name__)",
        "        except ZeroDivisionError as error:\n            log.warning(\"the model server's peak was not kept\", error=type(error).__name__)",
        ("tests/unit/test_model_server_client.py",),
    ),
    Mutation(
        "a server that reads no document is told about the door",
        WK,
        "    if not config.reads_documents:\n        return ()\n",
        "",
        ("tests/unit/test_acceptance_checks_knowledge_models.py",),
    ),
    Mutation(
        "an install with no server and no revision is told about the door",
        WK,
        "if revision is None and not inference_is_switched_on(env, saved):",
        "if False:",
        ("tests/unit/test_acceptance_checks_knowledge_models.py",),
    ),
    Mutation(
        "a part that reads another page's words passes the check",
        AC,
        'if PROBE_WORD not in " ".join(block.text for block in blocks).casefold():',
        "if False:",
        ("tests/unit/test_acceptance_modelserver_documents.py",),
    ),
    Mutation(
        "a peak one over the limit passes the check",
        AC,
        "if summary.largest_anon_mib > limit:",
        "if summary.largest_anon_mib > limit + 1:",
        ("tests/unit/test_acceptance_modelserver_documents.py",),
    ),
    Mutation(
        "a nested weight file is written without its directory",
        FETCH,
        "    target.parent.mkdir(parents=True, exist_ok=True)\n",
        "",
        T_SUP,
    ),
]

report = verify(mutations, repo=Path("."))
print(report.table())
print("SURVIVORS:", [one.label for one in report.survivors])
