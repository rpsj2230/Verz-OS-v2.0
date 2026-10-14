"""`python -m inference_server.fetch <part>...`: put a part's weights in the volume, once.

The model server itself has no route off the host, on purpose (`docker-compose.inference.yml`: the
network is internal, and the weights volume is mounted read-only), so the weights cannot be pulled
by the server. They are put in the volume by this, run by the release's own step before the server
starts (`ops/deploy/overlays/modelserver.prepare.sh`) as a one-shot container that has a route out
and holds nothing but this program and a volume. **It sends nothing of the install's anywhere**: it
asks a public address for a public file, and it is never handed a document, a credential or a
setting beyond the names of the parts.

**A file is checked against a digest where one is known, and a digest that is not known says so.**
Every source below carries `sha256`, and for a file nobody has downloaded to read its digest it is
empty and `pinned` is False. An unpinned file is still fetched, because an install that cannot be
given a model is an install that cannot use the feature, but the digest it actually got is written
to `fetched.json` beside it and printed, so the first install produces the value that should be
pinned and a second install is held to it. That is trust on first use, and the module is plain about
it: it is weaker than a pinned digest, and the person who pins one closes the gap.
`THE_FIRST_FETCH_IS_TRUSTED_UNTIL_SOMEBODY_PINS_IT` is the sentence, and a test holds the table
to it.

**A file already in the volume is not fetched again** when its size and digest still say what was
recorded. A restart of the release must not become a download of a gigabyte, and an install without
a route out at that moment must keep working.

**Atomic.** The file is written under a temporary name in the same directory and moved into place
when its digest has been taken, so a connection that dies half way leaves no file the server would
mistake for weights.

Task ids: M7.3.3, M7.2.1
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: The sentence for every source whose digest is empty. See the module docstring.
THE_FIRST_FETCH_IS_TRUSTED_UNTIL_SOMEBODY_PINS_IT: Final = (
    "No digest is pinned for this file because nobody working on this product has downloaded it to "
    "read one. The first install records the digest it received in fetched.json and prints it; "
    "pinning that value in this table is what turns trust on first use into a check."
)

#: What the volume records about each file it holds.
RECORD: Final = "fetched.json"

CHUNK: Final = 1024 * 1024


@dataclass(frozen=True)
class Source:
    """One file a part needs, where it comes from, and the digest it must have when one is known."""

    part: str
    #: The path under the model directory the server reads it from.
    name: str
    url: str
    sha256: str = ""

    @property
    def pinned(self) -> bool:
        """Whether a digest is known, and so the file is held to one."""
        return bool(self.sha256)


#: Every file the parts need. A part with no entry here has nothing to fetch, or its fetch is built
#: with the part. The embedding model is Qwen3-Embedding-0.6B quantised to 8 bits (a GGUF file).
SOURCES: Final[tuple[Source, ...]] = (
    Source(
        part="embedding",
        name="Qwen3-Embedding-0.6B-Q8_0.gguf",
        url="https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/main/Qwen3-Embedding-0.6B-Q8_0.gguf",
    ),
)


class FetchError(Exception):
    """A file could not be fetched, or arrived with a digest that is not the one pinned."""


def sources_for(parts: list[str]) -> tuple[Source, ...]:
    """The files these parts need, in the order the table lists them."""
    return tuple(one for one in SOURCES if one.part in parts)


def digest_of(path: Path) -> str:
    """The SHA-256 of a file, read in pieces so a large model is never held whole."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            hasher.update(chunk)
    return hasher.hexdigest()


def _record(directory: Path) -> dict[str, dict[str, object]]:
    try:
        loaded = json.loads((directory / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def fetch_one(source: Source, directory: Path, *, opener: object = None) -> str:
    """Make this file present and checked, and say what was done in a sentence.

    `opener` is how a test stands in for the network; in the image it is `urllib.request.urlopen`.
    """
    target = directory / source.name
    held = _record(directory).get(source.name)
    if target.exists() and held is not None and held.get("bytes") == target.stat().st_size:
        recorded = str(held.get("sha256", ""))
        # Hashed again, not trusted by its size: a file of the same length with other bytes in it is
        # a different model under the same name, which is the change that has no symptom. A second
        # of reading is the price, paid at a deploy and not at a request.
        agrees = recorded and (not source.pinned or recorded == source.sha256)
        if agrees and digest_of(target) == recorded:
            return f"{source.name} is already here and unchanged"
    open_url = opener or urllib.request.urlopen
    temporary = target.with_name(f"{target.name}.part")
    hasher = hashlib.sha256()
    size = 0
    try:
        with open_url(source.url, timeout=60) as response, temporary.open("wb") as out:  # type: ignore[operator]
            while chunk := response.read(CHUNK):
                hasher.update(chunk)
                size += len(chunk)
                out.write(chunk)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        msg = f"{source.name} could not be fetched: {error.__class__.__name__}"
        raise FetchError(msg) from error
    received = hasher.hexdigest()
    if source.pinned and received != source.sha256:
        temporary.unlink(missing_ok=True)
        msg = f"{source.name} arrived with a digest that is not the pinned one; it was thrown away"
        raise FetchError(msg)
    temporary.replace(target)
    record = _record(directory)
    record[source.name] = {
        "sha256": received,
        "bytes": size,
        "url": source.url,
        "pinned": source.pinned,
    }
    (directory / RECORD).write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    if source.pinned:
        return f"{source.name} fetched ({size} bytes) and matches its pinned digest"
    return (
        f"{source.name} fetched ({size} bytes). Its digest is {received}, recorded here and not "
        f"pinned: {THE_FIRST_FETCH_IS_TRUSTED_UNTIL_SOMEBODY_PINS_IT}"
    )


def main(argv: list[str]) -> int:
    """Fetch every file the named parts need into the model directory. Exit 0 if all are there."""
    directory = Path(os.environ.get("INFERENCE_MODEL_DIR", "/models"))
    parts = [one for one in argv[1:] if one]
    if not parts:
        print("usage: python -m inference_server.fetch <part>...", file=sys.stderr)
        return 64
    directory.mkdir(parents=True, exist_ok=True)
    failed = False
    for source in sources_for(parts):
        try:
            print(fetch_one(source, directory))
        except FetchError as error:
            print(str(error), file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
