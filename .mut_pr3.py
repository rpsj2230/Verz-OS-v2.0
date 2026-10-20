from pathlib import Path

from brain.ops.mutation import Mutation, verify

OCR = "src/inference_server/parts/ocr.py"
SUP = "src/inference_server/supervisor.py"
POCR = "src/brain/knowledge/parse_ocr.py"
TP = "src/brain/knowledge/text_path.py"
WK = "src/brain/ops/worker.py"
EMB = "src/inference_server/parts/embedding.py"
GW = "src/inference_server/gateway.py"
ST = "src/brain/ops/model_server_store.py"
SR = "src/brain/settings_routes.py"
CL = "src/brain/ops/model_server_client.py"
AC = "src/brain/ops/acceptance_checks_modelserver.py"

T_SRV = ("tests/unit/test_inference_server_documents.py",)
T_SUP = ("tests/unit/test_inference_server_documents.py", "tests/unit/test_inference_server.py")
T_PAR = (
    "tests/unit/test_model_server_parsers.py",
    "tests/unit/test_parse_ocr.py",
    "tests/unit/test_scanning.py",
)
T_IMG = (
    "tests/unit/test_model_server_parsers.py",
    "tests/unit/test_text_path.py",
    "tests/unit/test_scanners.py",
)
T_EMB = ("tests/unit/test_inference_server_embedding.py", "tests/unit/test_inference_server.py")
T_KEEP = ("tests/unit/test_peak_keeper.py",)
T_ROUTE = ("tests/unit/test_model_server_routes.py",)
T_ACC = ("tests/unit/test_acceptance_modelserver.py",)
T_CL = ("tests/unit/test_model_server_client.py",)

mutations = [
    Mutation(
        "a row the engine marks as not a word is a word",
        OCR,
        "if not word.text.strip() or word.confidence < 0:",
        "if not word.text.strip():",
        T_SRV,
    ),
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
        "a boolean figure is a confidence",
        POCR,
        "if isinstance(figure, bool) or not isinstance(figure, (int, float)):",
        "if not isinstance(figure, (int, float)):",
        T_PAR,
    ),
    Mutation(
        "a PNG with no header chunk is read for a size anyway",
        TP,
        'if len(content) < 24 or content[12:16] != b"IHDR":',
        "if len(content) < 24:",
        T_IMG,
    ),
    Mutation(
        "an install with no server and no revision is told about the door",
        WK,
        "if revision is None and not inference_is_switched_on(env, saved):",
        "if False:",
        ("tests/unit/test_acceptance_checks_knowledge_models.py",),
    ),
    Mutation(
        "a vector with no length is returned",
        EMB,
        "if not math.isfinite(norm) or norm == 0.0:",
        "if False:",
        T_EMB,
    ),
    Mutation(
        "a vector of the wrong width is stored",
        EMB,
        "if len(values) != self.dimensions:",
        "if False:",
        T_EMB,
    ),
    Mutation(
        "a chunk named twice is embedded twice",
        EMB,
        "or not chunk_id or chunk_id in seen:",
        "or not chunk_id:",
        T_EMB,
    ),
    Mutation(
        "a blank passage gets a vector",
        EMB,
        "if not isinstance(text, str) or not text.strip():",
        "if not isinstance(text, str):",
        T_EMB,
    ),
    Mutation(
        "a record of another length is believed",
        EMB,
        'held.get("bytes") == size and ',
        "",
        T_EMB,
    ),
    Mutation(
        "the revision is thirteen characters",
        EMB,
        "REVISION_CHARS: Final = 12",
        "REVISION_CHARS: Final = 13",
        T_EMB,
    ),
    Mutation(
        "the window is not the one the memory was sized for",
        EMB,
        "WINDOW_TOKENS: Final = 1024",
        "WINDOW_TOKENS: Final = 2048",
        T_EMB,
    ),
    Mutation(
        "the pooling is left to the library",
        EMB,
        "            pooling_type=llama_cpp.LLAMA_POOLING_TYPE_LAST,\n",
        "",
        T_EMB,
    ),
    Mutation(
        "a server without the embedding part states a revision",
        GW,
        'if "embedding" not in config.parts or not config.embedding_file:',
        "if not config.embedding_file:",
        T_EMB,
    ),
    Mutation(
        "the keeper grows without a bound",
        ST,
        "            del self._held[: -self.LARGEST_KEPT]\n",
        "",
        T_KEEP,
    ),
    Mutation(
        "the keeper's bound is not a ring for every part",
        ST,
        "LARGEST_KEPT: Final = 50 * len(Part)",
        "LARGEST_KEPT: Final = 50",
        T_KEEP,
    ),
    Mutation(
        "a peak is written outside its savepoint",
        ST,
        "session.begin(), session.begin_nested():",
        "session.begin():",
        T_KEEP,
    ),
    Mutation(
        "a row the table refuses fails the job",
        ST,
        "            except Exception as error:\n                log.warning(",
        "            except ZeroDivisionError as error:\n                log.warning(",
        T_KEEP,
    ),
    Mutation(
        "the embedding task does not write what it heard",
        WK,
        "            await peaks.flush(sessions, at=_utc_now())\n",
        "",
        T_KEEP,
    ),
    Mutation(
        "a server holding other weights is called the same",
        SR,
        "    if declared == held:",
        "    if True:",
        T_ROUTE,
    ),
    Mutation(
        "a declared revision with no held one is told to be set",
        SR,
        "    if declared is None:\n        return (",
        "    if False:\n        return (",
        T_ROUTE,
    ),
    Mutation(
        "a held revision that is not the declared one passes the check",
        AC,
        "if held != declared:",
        "if False:",
        T_ACC,
    ),
    Mutation(
        "a server stating no revision passes the check",
        AC,
        "    if held is None:\n        raise CheckFailedError(THE_SERVER_STATES_NO_REVISION)\n",
        "",
        T_ACC,
    ),
    Mutation(
        "a body that is not an object is a readiness answer",
        CL,
        "    if not isinstance(body, Mapping):\n        return None\n",
        "",
        T_CL,
    ),
]

report = verify(mutations, repo=Path("."))
print(report.table())
print("SURVIVORS:", [one.label for one in report.survivors])
