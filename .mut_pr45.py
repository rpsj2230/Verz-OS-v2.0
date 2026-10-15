from pathlib import Path

from brain.ops.mutation import Mutation, verify

MSP = "src/brain/knowledge/model_server_parsers.py"
UP = "src/brain/knowledge/uploads.py"
TP = "src/brain/knowledge/text_path.py"
IS = "src/brain/knowledge/item_store.py"
IQ = "src/brain/knowledge/ingest_queue.py"
CH = "src/brain/knowledge/chunking.py"
CS = "src/brain/knowledge/chunk_store.py"
DOC = "src/inference_server/parts/documents.py"
OCR = "src/inference_server/parts/ocr.py"
ENT = "src/inference_server/parts/entities.py"
EG = "src/brain/ops/egress.py"
CL = "src/brain/ops/model_server_client.py"

T_PASS = ("tests/unit/test_how_a_passage_was_read.py",)
T_QUEUE = ("tests/unit/test_ingest_queue.py",)
T_SRV = ("tests/unit/test_inference_server_documents.py",)
T_ENT = ("tests/unit/test_inference_server_entities.py",)
T_CHUNK = (
    "tests/unit/test_how_a_passage_was_read.py",
    "tests/unit/test_parse_layout.py",
    "tests/unit/test_knowledge_chunking.py",
)

mutations = [
    Mutation(
        "a block that already says how it was read is overwritten",
        MSP,
        "block if block.path else replace(block, path=path, engine=engine) for block in blocks",
        "replace(block, path=path, engine=engine) for block in blocks",
        T_PASS,
    ),
    Mutation(
        "a document that is not a PDF is filled in",
        MSP,
        "if media is not MediaType.PDF or not isinstance(reader, ServerOcr):",
        "if not isinstance(reader, ServerOcr):",
        T_PASS,
    ),
    Mutation(
        "a page the layout read is read again",
        MSP,
        "if page not in had)",
        "if True)",
        T_PASS,
    ),
    Mutation(
        "a reader that is down leaves the pages out for good",
        MSP,
        "if outcome.cause in (ParseCause.PARSER_UNAVAILABLE, ParseCause.TIMED_OUT):",
        "if False:",
        T_PASS,
    ),
    Mutation(
        "a refused fill-in names no page",
        MSP,
        "return FilledIn(tuple(read), blank)",
        "return FilledIn(tuple(read))",
        T_PASS,
    ),
    Mutation(
        "filled-in pages are not laid in by page",
        MSP,
        "key=lambda pair: (pair[1].page or 0, pair[0])",
        "key=lambda pair: pair[0]",
        T_PASS,
    ),
    Mutation(
        "a layout read is not filled in",
        UP,
        "if services is not None and provenance.path is ParsePath.LAYOUT:",
        "if False:",
        T_PASS,
    ),
    Mutation(
        "the pages the reader left out are not joined to the fill-in's",
        UP,
        "left_out = tuple(sorted({*left_out, *filled.left_out_pages}))",
        "left_out = filled.left_out_pages",
        T_PASS,
    ),
    Mutation(
        "the item carries no notice",
        UP,
        "parse_notice=left_out_notice(left_out),",
        'parse_notice="",',
        T_PASS,
    ),
    Mutation(
        "every page is a page without text",
        TP,
        "if not page.extract_text().strip()",
        "if True",
        T_PASS,
    ),
    Mutation(
        "an empty notice is stored as a sentence",
        IS,
        '"parse_notice": item.parse_notice or None,',
        '"parse_notice": item.parse_notice,',
        T_PASS,
    ),
    Mutation(
        "the ticket says nothing of the pages left out",
        IQ,
        "reason=read.item.parse_notice,",
        'reason="",',
        T_QUEUE,
    ),
    Mutation(
        "the sentence leaves the notice out",
        IQ,
        "        case TicketState.ADDED if ticket.reason:\n",
        "        case TicketState.ADDED if False:\n",
        T_QUEUE,
    ),
    Mutation(
        "a page numbered zero is a page",
        DOC,
        "isinstance(one, int) and not isinstance(one, bool) and one >= 1 for one in named",
        "isinstance(one, int) and not isinstance(one, bool) and one >= 0 for one in named",
        T_SRV,
    ),
    Mutation(
        "a boolean is a page",
        DOC,
        "isinstance(one, int) and not isinstance(one, bool) and one >= 1 for one in named",
        "isinstance(one, int) and one >= 1 for one in named",
        T_SRV,
    ),
    Mutation(
        "every page is recognised though some were named",
        OCR,
        "                if only is not None and number + 1 not in only:\n                    continue\n",
        "",
        T_SRV,
    ),
    Mutation(
        "the windows do not overlap",
        ENT,
        "    step = size - overlap\n",
        "    step = size\n",
        T_ENT,
    ),
    Mutation(
        "the tail of a long text is not read",
        ENT,
        "    if starts[-1] + size < len(text):\n",
        "    if False:\n",
        T_ENT,
    ),
    Mutation(
        "a label nobody asked for is kept",
        ENT,
        "                moved.label in asked\n                and ",
        "                True\n                and ",
        T_ENT,
    ),
    Mutation(
        "a span under the floor is kept",
        ENT,
        "and FLOOR_SCORE <= moved.score <= 1.0",
        "and moved.score <= 1.0",
        T_ENT,
    ),
    Mutation(
        "a name found twice keeps the lower score",
        ENT,
        "if key not in best or moved.score > best[key].score:",
        "if key not in best or moved.score < best[key].score:",
        T_ENT,
    ),
    Mutation(
        "an entity part that is unwell is read as an answer",
        EG,
        "        if response.status_code != ANALYSED:\n            raise AnalyserUnavailableError\n        try:\n            payload = response.json()\n        except ValueError:\n            raise AnalyserUnavailableError from None\n        if not isinstance(payload, Mapping):",
        "        try:\n            payload = response.json()\n        except ValueError:\n            raise AnalyserUnavailableError from None\n        if not isinstance(payload, Mapping):",
        T_ENT,
    ),
    Mutation(
        "a second leg is asked with no time left",
        EG,
        "            if remaining <= 0:\n                break\n",
        "",
        T_ENT,
    ),
    Mutation(
        "every leg being down is an answer",
        EG,
        "        if not answered:\n            raise AnalyserUnavailableError\n",
        "",
        T_ENT,
    ),
    Mutation(
        "the entity model gets the analyser's budget",
        EG,
        'getattr(detector, "budget_seconds", ANALYSER_BUDGET_SECONDS)',
        "ANALYSER_BUDGET_SECONDS",
        T_ENT,
    ),
    Mutation(
        "the analyser alone is wrapped",
        EG,
        "    if entity_detector is None:\n        return analyser_detector\n",
        "",
        T_ENT,
    ),
    Mutation(
        "an install that does not run the server has an entity model",
        CL,
        "    if not is_switched_on(env, saved):\n        return None\n",
        "",
        T_ENT,
    ),
    Mutation(
        "an install that did not choose the part has an entity model",
        CL,
        "        if Part.ENTITIES not in read_config(env, saved).parts:\n            return None\n",
        "",
        T_ENT,
    ),
]

report = verify(mutations, repo=Path("."))
print(report.table())
print("SURVIVORS:", [one.label for one in report.survivors])
