"""Which readers of the model server an install has, asked in one place.

The answer is no readers unless three things hold together: the server is one of the services the
install runs, the feature that lets the product send it work is on, and a part that reads a
document is chosen. Each is tested alone, with the other two satisfied, so that a missing one is
what is seen to matter.

Task ids: M7.2.1, M7.2.3, M7.2.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest

from brain.knowledge import document_services as under_test
from brain.knowledge.document_services import document_parts, door_services
from brain.knowledge.document_services import document_services as build_services
from brain.ops.model_server import Part
from brain.ops.model_server_client import Reply

ON: Mapping[str, str] = {"INSTALL_SERVICES": "modelserver", "INSTALL_MODEL_PARTS": "embedding,ocr"}


def _feature(monkeypatch: pytest.MonkeyPatch, on: bool) -> None:
    async def answer(sessions: Any) -> bool:
        return on

    monkeypatch.setattr(under_test, "model_server_is_on", answer)


#: Stands for the application's sessions, which the feature question is answered over. It is
#: never opened: `model_server_is_on` is replaced in every test that gets past the switch.
SESSIONS: Any = object()


def _parts(env: Mapping[str, str]) -> frozenset[Part]:
    return asyncio.run(document_parts(SESSIONS, env))


def test_a_process_with_no_database_has_no_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without sessions the feature cannot be asked, and the answer is that it is off.

    Delete this and a process built without a database raises where it should read as off."""
    _feature(monkeypatch, True)

    assert asyncio.run(document_parts(None, ON)) == frozenset()


def test_a_chosen_document_part_is_a_reader_when_the_server_runs_and_the_feature_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive case, and the embedding part is not a reader of documents.

    Delete this and every refusal below is satisfied by a function that answers no readers."""
    _feature(monkeypatch, True)

    assert _parts(ON) == frozenset({Part.OCR})


def test_without_the_server_among_the_services_there_is_no_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parts are chosen and the feature is on, and the server is not run.

    Delete this and an install that never started the server sends documents to an address
    nothing answers."""
    _feature(monkeypatch, True)

    assert _parts({**ON, "INSTALL_SERVICES": "none"}) == frozenset()
    assert _parts({**ON, "INSTALL_SERVICES": "presidio"}) == frozenset()


def test_with_the_feature_off_there_is_no_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """The server is run and the parts are chosen, and the product is not switched to use them.

    Delete this and a new capability reaches every install that merely runs the service."""
    _feature(monkeypatch, False)

    assert _parts(ON) == frozenset()


def test_a_choice_of_no_document_part_is_no_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the embedding part is chosen, so no document is sent anywhere.

    Delete this and an embedding-only install is routed as though it had a layout reader."""
    _feature(monkeypatch, True)

    assert _parts({**ON, "INSTALL_MODEL_PARTS": "embedding"}) == frozenset()


def test_a_setting_that_cannot_be_read_is_no_reader_and_not_a_stopped_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A part named wrongly is refused where it is saved; here it reads as nothing chosen, so a
    worker whose setting was edited by hand keeps draining the queue.

    Delete this and the queue stops over a typo."""
    _feature(monkeypatch, True)

    assert _parts({**ON, "INSTALL_MODEL_PARTS": "ocr,telepathy"}) == frozenset()
    assert _parts({**ON, "INSTALL_SERVICES": "no such service"}) == frozenset()


def test_the_client_is_built_only_when_there_is_a_reader_to_send_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With readers the factory is called once and the services are over what it gave; with none
    it is never called.

    Delete this and an install that runs no document part builds a client, and its breaker, for
    nothing."""

    class Server:
        def ask(self, part: Part, request: object) -> Reply:
            raise AssertionError("nothing is sent in this test")

    built: list[Server] = []

    def make() -> Server:
        built.append(Server())
        return built[0]

    _feature(monkeypatch, True)
    some = asyncio.run(build_services(SESSIONS, make, ON))
    embedding_only = {**ON, "INSTALL_MODEL_PARTS": "embedding"}
    none = asyncio.run(build_services(SESSIONS, make, embedding_only))

    assert some is not None and some.ocr is not None and some.layout is None
    assert none is None
    assert len(built) == 1


def test_a_door_decides_with_the_parts_and_sends_nothing() -> None:
    """The door's services name which types are readable and can reach no server.

    Delete this and a door builds a client to answer a question about a file's type."""
    assert door_services(frozenset()) is None
    services = door_services(frozenset({Part.OCR}))

    assert services is not None and services.ocr is not None
    with pytest.raises(RuntimeError, match="sends no document"):
        services.ocr.server.ask(Part.OCR, {})  # type: ignore[attr-defined]
