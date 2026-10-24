"""The console says in English what the catalogue says in English, and uses every key it holds.

Each wired sentence in the console is `msg("<key>", "<English>")`. The English is written at the
call so that a page and every test that names its constants render what they always did with
nothing served; the catalogue (`brain.console_messages`) holds the same English beside the
Chinese. Two copies of one sentence is the drift this file exists to refuse: it reads every call
out of `console/src`, resolves the English, and holds it to the catalogue in both directions, so a
sentence edited in one place is a red build and not a screen that says two things depending on the
language chosen.

Task ids: M35.1.1.1
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from brain.console_messages import CONSOLE_KEYS, CONSOLE_MESSAGES

SRC = Path(__file__).resolve().parents[2] / "console" / "src"

#: A JavaScript double-quoted string, escapes included.
STRING = r'"(?:[^"\\]|\\.)*"'

#: `msg("key", "a" + "b")`, across lines: the key, then one or more literals joined by plus.
CALL = re.compile(rf"\bmsg\(\s*({STRING})\s*,\s*({STRING}(?:\s*\+\s*{STRING})*)\s*\)")


def calls() -> list[tuple[str, str, Path]]:
    """Every `msg` call in the console as (key, English, file). A call whose English is not made of
    literals is not matched, and `test_every_call_in_the_console_gives_its_english_as_literals`
    counts them against the calls of any shape so one cannot hide."""
    found: list[tuple[str, str, Path]] = []
    for path in sorted(SRC.rglob("*.ts*")):
        if "generated" in path.parts:
            continue
        for matched in CALL.finditer(path.read_text(encoding="utf-8")):
            key = json.loads(matched.group(1))
            english = "".join(json.loads(part) for part in re.findall(STRING, matched.group(2)))
            found.append((key, english, path))
    return found


def test_every_english_sentence_in_the_console_is_the_catalogues_english() -> None:
    """The words written at the call and the words in the catalogue are the same words. Delete this
    and one of them is edited alone, and an English reader and a Chinese reader are told different
    things by the same sentence."""
    differing = [
        (key, path.name)
        for key, english, path in calls()
        if CONSOLE_MESSAGES.get(key, {}).get("en") != english
    ]
    assert differing == []


def test_every_key_the_console_asks_for_is_in_the_catalogue_and_every_key_in_it_is_asked_for() -> (
    None
):
    """Both directions. Delete this and a typo in a key quietly serves English for ever, or the
    catalogue carries translations of sentences no page draws and the document is longer for it."""
    used = {key for key, _, _ in calls()}
    assert sorted(used - set(CONSOLE_KEYS)) == []
    assert sorted(set(CONSOLE_KEYS) - used) == []


def test_a_key_is_used_with_one_english_everywhere() -> None:
    """A key written twice carries the same English both times. Delete this and two pages share a
    key and say different things in English while saying one thing in Chinese."""
    seen: dict[str, set[str]] = defaultdict(set)
    for key, english, _ in calls():
        seen[key].add(english)
    assert [key for key, found in seen.items() if len(found) > 1] == []


def test_every_call_in_the_console_gives_its_english_as_literals() -> None:
    """A `msg(` whose English is built from something else is not read by this file and so is not
    held to the catalogue. Delete this and a sentence assembled at the call escapes the check that
    exists for it."""
    anywhere = 0
    for path in sorted(SRC.rglob("*.ts*")):
        if "generated" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        anywhere += len(re.findall(r'(?<![A-Za-z_.])msg\(\s*"', text))
    assert anywhere == len(calls())
