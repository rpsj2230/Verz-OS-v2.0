"""The install acceptance checks for language: Chinese and mixed-language documents are found by a
question in either language and carry the language they were detected in, and the console is
served as an installable shell.

**The retrieval check uses the upload path the documents check uses, and asks as a person.** Three
Markdown documents are added to `acceptance_a` as a library person would add them, with no worker
(the same text path `brain.knowledge_routes` takes): one in English, one in Simplified Chinese and
one that is both. A member of the department then asks in Chinese and in English through the
document search tool, and the passage policy decides what they may read. What the install shows
is that the Han leg of the lexical search is built on the install's own database (`know.chunk.cjk`
and its configuration) and that the language recorded at ingest is read back from the column the
migration made. A mutation that drops the Han leg makes the Chinese question find nothing, which
is the silent worse retrieval the leaf exists to refuse. See
`A_CHINESE_QUESTION_THAT_FINDS_NOTHING_IS_THE_DEFECT`, which is why the check requires the
document.

**The shell is read the way the console serves it.** `brain.console_static` serves unhashed files
at the root of the built bundle, so the check asks the product's own fallback route, mounted on a
throwaway application, for `/manifest.webmanifest` and the icons it names. An image that carries
no built console says so and the check is not run; the install's own bundle is what is judged.
That the browser offers to install it is the person's half, and this check does not claim it.

Task ids: M35.1.1.3, M35.1.2.1, M35.1.2.2, M35.1.2.3, M35.3.2.1
"""

from __future__ import annotations

import json
from typing import Final

from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _found, _in, _upload
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2050

# ------------------------------------------------------------------ written-down reasons
#: Why the check asks a Chinese question and holds the answer to finding the document.
A_CHINESE_QUESTION_THAT_FINDS_NOTHING_IS_THE_DEFECT: Final = (
    "The default text search stems English and splits on spaces, so Chinese text is one long token "
    "that no question matches. The install builds a second index over Han segments and asks it "
    "whenever the question holds Han text; without it a Chinese question quietly retrieves "
    "nothing and the answer reads as though the company knows nothing. So the check asks in "
    "Chinese and requires the Chinese document."
)

#: Said when this image carries no built console to serve.
NO_CONSOLE_IS_BUILT_HERE: Final = (
    "this image carries no built console bundle, so there is no installable shell to ask for; the "
    "install's own image does"
)

# ------------------------------------------------------------------------ the figures
#: A Chinese document: a quotation procedure, long enough for its language to be told.
CHINESE_BODY: Final = (
    "# 报价流程\n\n客户必须在三十个自然日内确认报价。逾期报价自动失效。"
    "报价单由销售部门负责人审核。财务部门在确认后开具发票。所有变更须书面记录。\n"
)

#: A question about it. Every adjacent pair of its characters is in the document, because the Han
#: index asks for every pair and a question with one pair the text lacks finds nothing.
CHINESE_QUESTION: Final = "确认报价"

#: What the manifest of an installable shell is asked for.
MANIFEST_PATH: Final = "/manifest.webmanifest"


async def _languages_of(h: Harness, document_id: str) -> frozenset[str]:
    """The languages recorded on a document's passages, read from the column itself.

    A passage too short to tell records none, so a heading alone says nothing; the document is
    what its passages with a language say between them.
    """
    rows = (
        await h.execute(
            text("SELECT language FROM know.chunk WHERE document_id = :id").bindparams(
                id=document_id
            )
        )
    ).all()
    if not rows:
        raise CheckFailedError("an uploaded document was stored with no passages")
    return frozenset(str(one[0]).lower() for one in rows if one[0] is not None)


@check(
    leaves=("M35.1.2.1", "M35.1.2.2", "M35.1.2.3"),
    sentence=(
        "An English, a Chinese and a mixed English and Chinese document added to acceptance_a are "
        "each recorded with the language they were detected in; a member there asking in Chinese "
        "finds the Chinese and the mixed document, asking in English finds the English and the "
        "mixed one, and a member of acceptance_b finds neither."
    ),
)
async def chinese_and_mixed_documents_are_found_in_either_language(h: Harness) -> None:
    from brain.knowledge.ingest import MediaType, ParseFailure

    await h.found_departments()
    library, member, outsider = (
        h.principal(A, "library"),
        h.principal(A, "member"),
        h.principal(B, "member"),
    )
    await h.person(library, department=A, grants=_in(A, "admin:knowledge"))
    await h.person(member, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(outsider, department=B, grants=_in(B, *KNOWLEDGE_READS))

    word = h.word()
    english = (
        f"# Quotation process\n\nA customer must confirm a quotation within thirty days. {word}\n"
    )
    mixed = (
        f"# 报价流程 Quotation\n\n{CHINESE_BODY}\n"
        f"A customer must confirm within thirty days. {word}\n"
    )
    ids: dict[str, str] = {}
    for label, body in (("english", english), ("chinese", CHINESE_BODY), ("mixed", mixed)):
        read = await _upload(
            h,
            library,
            filename=f"Acceptance-{label}.md",
            declared=MediaType.MARKDOWN.value,
            body=body.encode("utf-8"),
        )
        if isinstance(read, ParseFailure):
            raise CheckFailedError("a document in this language was refused as unreadable")
        ids[label] = str(read.item.item_id)

    detected = {label: await _languages_of(h, one) for label, one in ids.items()}
    if not any(one.startswith("zh") for one in detected["chinese"]):
        raise CheckFailedError("a Chinese document was not recorded as Chinese")
    if not any(one.startswith("en") for one in detected["english"]):
        raise CheckFailedError("an English document was not recorded as English")

    async def found_by(reader: str, question: str) -> set[str]:
        _, kept = await _found(h, reader, question)
        return {str(one.get("document_id")) for one in kept}

    in_chinese = await found_by(member, CHINESE_QUESTION)
    if ids["chinese"] not in in_chinese:
        raise CheckFailedError("a question in Chinese did not find the Chinese document")
    if ids["mixed"] not in in_chinese:
        raise CheckFailedError("a question in Chinese did not find the mixed-language document")
    in_english = await found_by(member, word)
    if ids["english"] not in in_english or ids["mixed"] not in in_english:
        raise CheckFailedError("a question in English did not find the documents holding it")
    if ids["chinese"] in in_english:
        raise CheckFailedError("a question in English found a document that holds no English")
    if (await found_by(outsider, CHINESE_QUESTION)) & set(ids.values()):
        raise CheckFailedError("a member of another department found a Chinese document")


@check(
    leaves=("M35.3.2.1",),
    sentence=(
        "The install's console is served with a manifest naming the application, its start page, "
        "its scope, a display mode and icons, and every icon the manifest names is served."
    ),
)
async def the_console_is_served_as_an_installable_shell(h: Harness) -> None:
    del h
    import httpx
    from fastapi import FastAPI

    from brain.console_static import bundle_entry, mount_console_fallback

    if bundle_entry() is None:
        raise CheckNotRunError(NO_CONSOLE_IS_BUILT_HERE)
    app = FastAPI()
    mount_console_fallback(app)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://acceptance.invalid") as c:
        answered = await c.get(MANIFEST_PATH)
        if answered.status_code != 200:
            raise CheckFailedError("the console served no manifest")
        try:
            manifest = json.loads(answered.text)
        except ValueError:
            raise CheckFailedError("the console's manifest is not JSON") from None
        for field in ("name", "start_url", "scope", "display"):
            if not manifest.get(field):
                raise CheckFailedError("the console's manifest is missing a field a shell needs")
        icons = manifest.get("icons") or []
        if not icons:
            raise CheckFailedError("the console's manifest names no icon")
        for icon in icons:
            served = await c.get(str(icon.get("src", "")))
            # The console answers every unknown address with its own page, so a missing icon is
            # a 200 of HTML: an icon is judged by being an image.
            if served.status_code != 200 or not served.headers.get("content-type", "").startswith(
                "image/"
            ):
                raise CheckFailedError("an icon the console's manifest names is not served")


@check(
    leaves=("M35.1.1.3",),
    sentence=(
        "Asking for a right-to-left language in the install's settings is refused with the "
        "deferral's own sentence, which says what would make it due, while the shipped languages "
        "are accepted and a language that is merely not shipped is refused in other words."
    ),
)
async def a_right_to_left_language_is_refused_by_name(
    h: Harness,
) -> None:
    del h
    from brain.console.configuration import setting_problem
    from brain.locale import RIGHT_TO_LEFT, SHIPPED_TAGS, Trigger

    if setting_problem("INSTALL_LOCALES", ",".join(SHIPPED_TAGS)) != "":
        raise CheckFailedError("the languages this product ships were refused")
    said = setting_problem("INSTALL_LOCALES", f"{SHIPPED_TAGS[0]}, ar")
    if RIGHT_TO_LEFT.reason not in said:
        raise CheckFailedError("a right-to-left language was not refused with the deferral's words")
    other = setting_problem("INSTALL_LOCALES", "fr")
    if not other or RIGHT_TO_LEFT.reason in other:
        raise CheckFailedError("a language that is only not shipped was refused as a deferral")
    if RIGHT_TO_LEFT.trigger is not Trigger.A_RIGHT_TO_LEFT_LOCALE_IS_ASKED_FOR:
        raise CheckFailedError("the right-to-left deferral does not state its trigger")
