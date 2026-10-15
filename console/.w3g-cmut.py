"""Console mutations, run in my own worktree and restored from git, with an md5 check."""

import hashlib
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV = dict(os.environ, PATH="/opt/homebrew/bin:" + os.environ["PATH"], NODE_OPTIONS="--no-experimental-webstorage")
SWEEP = ["tests/explanations.test.ts"]
COMP = ["tests/explanation-component.test.tsx"]
LISTS = ["tests/empty-lists.test.tsx"]

MUTATIONS = [
    ("an inert control drawn by a page", "src/pages/agents/AgentLeash.tsx",
     '<Button type="submit" size="xs" variant="outline" disabled={to === chosen.rung}>',
     '<Button type="submit" size="xs" variant="outline" aria-disabled="true" disabled={to === chosen.rung}>', SWEEP),
    ("an act that nobody registered", "src/pages/agents/AgentAbout.tsx",
     'act="agent.overview"', 'act="agent.overveiw"', SWEEP),
    ("a sentence typed into the page", "src/pages/agents/AutomationAuthoring.tsx",
     'told={one.notOffered}', 'told="Not offered"', SWEEP),
    ("a Note that leads with not available yet", "src/pages/models/RoutingPage.tsx",
     'kind="attention"', 'kind="not-yet"', SWEEP),
    ("a stand-in component for an unavailable act", "src/pages/agents/AgentAbout.tsx",
     'function SubHeading(', 'function NotOffered() { return <i />; }\nfunction SubHeading(', SWEEP),
    ("a disabled control for a reason nobody listed", "src/pages/agents/AgentLeash.tsx",
     'disabled={to === chosen.rung}>', 'disabled={to === chosen.rung || !leash.mayMove}>', SWEEP),
    ("an act drawn in a form it is not registered in", "src/pages/agents/AgentProfile.tsx",
     '<Explanation form="note" act="agent.browser" />', '<Explanation form="line" act="agent.browser" />', SWEEP),
    ("a registered sentence that no page draws", "src/pages/tools/ToolDetailPage.tsx",
     'act="tool.no_longer_offered"', 'act="agent.overview"', SWEEP),
    ("the control loses its mark", "src/components/kit/explanation.tsx",
     '            data-unavailable=""\n', '', SWEEP + COMP),
    ("the control loses aria-disabled", "src/components/kit/explanation.tsx",
     '            aria-disabled="true"\n', '', SWEEP + COMP),
    ("an unreadable sentence leaves the page saying nothing", "src/components/kit/explanation.tsx",
     'return { sentence: EXPLANATION_NOT_READ, lead: "" };', 'return { sentence: null, lead: "" };', COMP),
    ("a told sentence is asked for again", "src/components/kit/explanation.tsx",
     'if ("told" in words) {\n    return { sentence: words.told, lead: own ?? "not-yet" };\n  }',
     'if (false as boolean) {\n    return { sentence: null, lead: own ?? "not-yet" };\n  }', COMP),
    ("a note forgets its lead", "src/components/kit/explanation.tsx",
     '{heard.lead === "" ? null : <span className="font-semibold">{EXPLANATION_LEADS[heard.lead]}</span>}', '', COMP),
    ("a not-offered sentence drawn as a control", "src/components/kit/explanation.tsx",
     '      <Ban aria-hidden className="mt-0.5 size-3.5 shrink-0" />\n      <span>{sentence}</span>',
     '      <Ban aria-hidden className="mt-0.5 size-3.5 shrink-0" />\n      <button type="button">{sentence}</button>', COMP),
    ("a stale entry on the list of disabled controls", "tests/explanations.test.ts",
     '  "src/pages/FirstRun.tsx::at === 0": DISABLED_BECAUSE.EDGE,',
     '  "src/pages/FirstRun.tsx::at === 0": DISABLED_BECAUSE.EDGE,\n  "src/pages/FirstRun.tsx::at === 99": DISABLED_BECAUSE.EDGE,', SWEEP),
    ("the failover matrix's own cell drawn as an empty list again", "src/pages/models/FailoverMatrixCard.tsx",
     '{NO_STEP_FOR_THE_LEVEL}', '<p>{NO_STEP_FOR_THE_LEVEL}</p>', ["tests/models-module.test.tsx"]),
]


def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def failing(output):
    return sorted({re.sub(r"\s+", " ", m.group(1)).strip() for m in re.finditer(r"^ FAIL  (.*)$", output, re.M)})


def run(tests):
    out = subprocess.run(["npx", "vitest", "run", *tests, "--maxWorkers=3"], cwd=ROOT, env=ENV, capture_output=True, text=True)
    return out.stdout + out.stderr


# The named tests are run before mutating, so a row cannot be caught by a test that was already red.
before = run(sorted({t for m in MUTATIONS for t in m[4]}))
print("BEFORE", failing(before) or "clean", flush=True)
if failing(before):
    sys.exit(1)

for label, rel, old, new, tests in MUTATIONS:
    path = os.path.join(ROOT, rel)
    original = md5(path)
    text = open(path).read()
    if text.count(old) != 1:
        print("SKIPPED", label, "match count", text.count(old), flush=True)
        continue
    open(path, "w").write(text.replace(old, new))
    try:
        found = failing(run(tests))
    finally:
        subprocess.run(["git", "checkout", "--", rel], cwd=ROOT, check=True)
    restored = md5(path) == original
    print(("CAUGHT  " if found else "SURVIVED") + " | " + label + " | " + "; ".join(found)[:600] + ("" if restored else " | NOT RESTORED"), flush=True)
print("DONE", flush=True)
