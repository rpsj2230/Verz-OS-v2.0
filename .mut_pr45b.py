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
        "a document that is not a PDF is filled in",
        MSP,
        "if media is not MediaType.PDF or not isinstance(reader, ServerOcr):",
        "if not isinstance(reader, ServerOcr):",
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
        "every page is recognised though some were named",
        OCR,
        "                if only is not None and number + 1 not in only:\n                    continue\n",
        "",
        T_SRV,
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
]

report = verify(mutations, repo=Path('.'))
print(report.table())
print('SURVIVORS:', [one.label for one in report.survivors])
