"""What each part needs on disk and in the image before it can be asked anything.

**Readiness is a list of absences, and it never loads a model.** The container's health check asks
this, and loading a part to prove it works would hold the memory the supervisor exists to give back
and would make the check as slow as a model load. So it asks four cheaper questions, in the order a
person fixing it would meet them: is the part's own module in this image, are the libraries it
imports installed, are the programs it runs on the path, and are its weights where the volume says
they are. A part whose answer to any is no is named with what is missing, and the container is not
ready while any chosen part is in that state: a server that is up and cannot serve a part an install
chose is the "presents a listening socket and refuses what it is asked" failure
`brain.ops.wiring` records readiness as being written to prevent.

**A part this image does not carry is a gap, not a crash.** Backends arrive one at a time with the
work that needs them, so an image built before a part existed reports it as not in the image, and an
install that chose it is told so by the health check rather than by a document that never reads.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

import importlib.util
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from inference_server.config import ServerConfig


@dataclass(frozen=True)
class PartNeeds:
    """What one part needs, as four lists."""

    #: The module under `inference_server.parts` that holds its backend.
    module: str
    #: Libraries the backend imports and the image must carry.
    libraries: tuple[str, ...]
    #: Programs it runs and the image must carry on its path.
    programs: tuple[str, ...]
    #: Weights it reads, resolved against this container's configuration.
    files: Callable[[ServerConfig], tuple[Path, ...]]


def _embedding_files(config: ServerConfig) -> tuple[Path, ...]:
    return (config.model_dir / config.embedding_file,) if config.embedding_file else ()


#: One row per part. The module names are the files `inference_server/parts/` gains as each part
#: is built; a row naming a module that is not there yet is reported by `readiness_gaps` as that.
NEEDS: Final[dict[str, PartNeeds]] = {
    "embedding": PartNeeds(
        module="embedding",
        libraries=("llama_cpp",),
        programs=(),
        files=_embedding_files,
    ),
    "layout": PartNeeds(
        module="layout",
        libraries=("docling",),
        programs=(),
        files=lambda config: (config.model_dir / "docling",),
    ),
    "ocr": PartNeeds(
        module="ocr",
        libraries=("pytesseract", "pypdfium2"),
        programs=("tesseract",),
        files=lambda config: (config.model_dir / "tessdata" / "eng.traineddata",),
    ),
    "tika": PartNeeds(
        module="tika",
        libraries=(),
        programs=("java",),
        files=lambda config: (config.model_dir / "tika" / "tika-server.jar",),
    ),
    "entities": PartNeeds(
        module="entities",
        libraries=("gliner",),
        programs=(),
        files=lambda config: (config.model_dir / "gliner",),
    ),
}


def _importable(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def readiness_gaps(config: ServerConfig) -> tuple[str, ...]:
    """Everything a chosen part is missing, in words naming the thing, or nothing if none is."""
    gaps: list[str] = []
    for part in config.parts:
        needs = NEEDS[part]
        if not _importable(f"inference_server.parts.{needs.module}"):
            gaps.append(f"the {part} part is not in this image")
            continue
        gaps.extend(
            f"the {part} part needs the library {name}, which this image does not carry"
            for name in needs.libraries
            if not _importable(name)
        )
        gaps.extend(
            f"the {part} part needs the program {name}, which is not on this image's path"
            for name in needs.programs
            if shutil.which(name) is None
        )
        gaps.extend(
            f"the {part} part's weights are not at {path}, and the volume is mounted read-only"
            for path in needs.files(config)
            if not path.exists()
        )
    return tuple(gaps)
