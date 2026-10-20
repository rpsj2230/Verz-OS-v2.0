"""Hand mutation of console guards in this worktree, which no other agent reads.

Each mutation: copy the file aside, break it, run the named vitest file, record which tests failed
by name, put the file back, and check the md5 is the original's.
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONSOLE = ROOT / "console"
BAK = Path("/tmp/pgs36/bak")
BAK.mkdir(parents=True, exist_ok=True)
ENV = {**os.environ, "PATH": "/opt/homebrew/bin:" + os.environ["PATH"], "NODE_OPTIONS": "--no-experimental-webstorage"}

REF = "tests/reference-screens.test.ts"
FONT = "tests/font-licences.test.ts"


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def run(test: str) -> tuple[list[str], str]:
    done = subprocess.run(
        ["npx", "vitest", "run", test, "--reporter=verbose"],
        cwd=CONSOLE, env=ENV, capture_output=True, text=True,
    )
    out = done.stdout + done.stderr
    failed = sorted({m.group(1).strip() for m in re.finditer(r"^\s*(?:FAIL|×)\s+\S+\s*>\s*(.+?)(?:\s+\d+ms)?$", out, re.M)})
    return failed, out


def mutate(label: str, file: str, before: str, after: str, test: str, root: Path = CONSOLE) -> None:
    path = root / file
    original = md5(path)
    backup = BAK / (file.replace("/", "__") + ".orig")
    shutil.copy2(path, backup)
    text = path.read_text(encoding="utf-8")
    if before not in text:
        print(f"| {label} | NOT APPLIED (before text not found in {file}) |")
        return
    try:
        path.write_text(text.replace(before, after, 1), encoding="utf-8", newline="\n")
        failed, out = run(test)
    finally:
        shutil.copy2(backup, path)
    restored = md5(path) == original
    verdict = "CAUGHT" if failed else "SURVIVED"
    print(f"| {label} | {verdict} | {'; '.join(failed) if failed else '-'} | restored byte-identically: {restored} |")
    sys.stdout.flush()
    assert restored, f"{file} was not restored"


if __name__ == "__main__":
    # Baseline: both files green before anything is broken.
    for test in (REF, FONT):
        failed, out = run(test)
        assert not failed, (test, failed, out[-2000:])
        print(f"baseline {test}: green")

    prof = "src/pages/agents/AgentProfile.tsx"
    mem = "src/pages/agents/AgentMemory.tsx"
    mutate("a switch is added to the Profile's learning section", prof,
           '      title={LEARNING_HEADING}\n      lede="What it may learn from answered questions, ordered by how far a change would reach."\n      action={<Brain aria-hidden className="size-4 text-dim" />}\n      footer={\n        <>',
           '      title={LEARNING_HEADING}\n      lede="What it may learn from answered questions, ordered by how far a change would reach."\n      action={<Switch id="agent-learning" />}\n      footer={\n        <>',
           REF)
    mutate("a checkbox is added to Memory's tiers", mem,
           '      action={<Brain aria-hidden className="size-4 text-dim" />}\n      footer={\n        <Link to={WORKS_AT.learning}',
           '      action={<input type="checkbox" aria-label="Allow learning" />}\n      footer={\n        <Link to={WORKS_AT.learning}',
           REF)
    mutate("the tiers shrink to three", prof,
           '    ["4", "Needs a person", "Would change who may see what. A person decides."],\n', '',
           REF)
    mutate("a learning switch appears on another page", "src/pages/agents/AgentGroups.tsx",
           "export function AgentGroups(", 'export function LearningFlag() {\n  return <Switch aria-label="Adaptive learning" />;\n}\n\nexport function AgentGroups(',
           REF)
    mutate("the computer-use card gets a switch", prof,
           '    <SectionCard title={COMPUTER_HEADING} action={<MonitorX aria-hidden className="size-4 text-dim" />}>',
           '    <SectionCard title={COMPUTER_HEADING} action={<Switch id="agent-computer" />}>',
           REF)
    mutate("the browsing card describes the person's own browser", prof,
           'lede="Using a web browser for a task, in a sealed browser thrown away afterwards."',
           'lede="Using your own browser session for a task."',
           REF)
    mutate("a route for operating a computer is added", "src/pages/AgentTemplates.route.tsx",
           '{ path: "agent-templates", element: <AgentTemplates /> }',
           '{ path: "agent-templates", element: <AgentTemplates /> },\n  { path: "computer-use", element: <AgentTemplates /> }',
           REF)
    mutate("the Profile record drops a rejection", "../docs/reference-screens/index.json",
           '"rejections": [\n        "no-single-learning-toggle",\n        "no-browser-operator-on-the-users-session"\n      ]',
           '"rejections": [\n        "no-single-learning-toggle"\n      ]', REF, root=CONSOLE)
    idx = "../docs/reference-screens/index.json"
    mutate("a covered page loses its record (connectors)", idx, '"address": "/connectors",\n      "section": null,', '"address": "/connectorz",\n      "section": null,', REF)
    mutate("a record names a section the agent page lacks", idx, '"section": "memory",', '"section": "memry",', REF)
    mutate("a record names no refusal", idx,
           '"refused": [\n        "A count of connected or available sources: the list draws the rows it was sent and no total.",\n        "A source the reader may not be told is connected reading differently from one that is not: both read Not connected, in the same words."\n      ]',
           '"refused": []', REF)
    mutate("a record cites a screenshot that does not cover it", idx,
           '"screenshots": ["image-1788498419735"],\n      "requirements": ["ANY-019", "ANY-020", "ANY-023"]',
           '"screenshots": ["image-1788498391599"],\n      "requirements": ["ANY-019", "ANY-020", "ANY-023"]', REF)
    mutate("a requirement is answered by the wrong screenshot's record", idx,
           '"requirements": ["ANY-050", "ANY-051"', '"requirements": ["ANY-001", "ANY-051"', REF)
    mutate("a screenshot the register names is dropped from the index", idx,
           '"id": "image-1788498446827",\n      "named_by_register": true,', '"id": "image-9999999999999",\n      "named_by_register": false,', REF)
    mutate("a screenshot is said to be held and is not", idx,
           '"id": "image-1788498391599",\n      "named_by_register": true,\n      "shows": "A catalogue of skills as cards with a use count, categories and a way to try or share one, beside a task and thread history for the member application.",\n      "pages": [\n        "/skills"\n      ],\n      "file": null,',
           '"id": "image-1788498391599",\n      "named_by_register": true,\n      "shows": "A catalogue of skills as cards with a use count, categories and a way to try or share one, beside a task and thread history for the member application.",\n      "pages": [\n        "/skills"\n      ],\n      "file": "skills-catalogue.webp",', REF)
    mutate("an empty page list loses its excuse", idx,
           '"no_page_because": "A member application screen (M40). The console\'s Ask page has not been held against it, so there is no record to make yet.",', '', REF)

    lic = "scripts/font-licences.mjs"
    mutate("the plugin is left out of the build", "vite.config.ts", "react(), fontLicences()]", "react()]", FONT)
    mutate("the notice is emitted under another name", lic, 'export const FONT_LICENCES_FILE = "font-licences.txt";', 'export const FONT_LICENCES_FILE = "licences.txt";', FONT)
    mutate("a package with no licence file is noticed anyway", lic, "if (!existsSync(file)) {", "if (false) {", FONT)
    mutate("a package under another licence is noticed as the OFL", lic, "if (!OFL.test(text)) {", "if (false) {", FONT)
    mutate("a console with no font package writes an empty notice", lic, "if (packages.length === 0) {", "if (false) {", FONT)
    mutate("a non-font package gets a section", lic, 'filter((name) => name.startsWith(SCOPE))', 'filter((name) => name.length > 0)', FONT)
