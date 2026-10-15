"""Add needs items 187 (held chat progress question) and 188 (five console leaves) to the page.

Run inside a worktree on top of the train. Rewrites the header count, the header list and the
architecture word to match.
"""
import re
from pathlib import Path

SCRATCH = Path("/private/tmp/claude-501/-Users-rupash-Claude-Verz-OS-v2-0-brain--scratch-wt-cg-governance/0c352820-7ea6-4c17-be4f-1f3d73ae9161/scratchpad")
page = Path("docs/needs-rupash.md")
text = page.read_text()

held = (SCRATCH / "item178.md").read_text().rstrip("\n") + "\n\n"
held = held.replace("## 178.", "## 187.").replace('"178: ', '"187: ')
assert "178" not in held.replace("1780", ""), held

five = """## 188. Five console tasks ask for something the design deliberately does not do: narrow each?

**In plain terms:** while proving the console tasks on your install, five of them turned out to ask for
a thing the product was built not to do. Each is listed with what is built and what the task text asks.
I recommend narrowing every one to what is built, and saying so on the task, rather than building the
thing, because each would weaken a rule you set.

1. **Who can see a named record (task 15.62).** The task says no screen may answer "who can see this
   record". Your 2026-09-18 decision added a record access view, shown only to a person who can already
   see that record. The task text is stale. Recommendation: narrow the task to the view that exists.
2. **Identity provider and embedding size (tasks 15.49 and 11.4).** Both are read-only in Settings,
   because changing either from a browser can lock every person out. The tasks ask for a console change
   that updates redirect addresses. Recommendation: keep them read-only and move the change to the
   installer's own command.
3. **Switching modules on (task 8.10).** Modules cannot be enabled from Features; only flags can.
   Recommendation: narrow the task to flags.
4. **A service account's owner (task 15.26).** A service account's owner is always the person who
   created it, never a field someone can edit. The task asks for owner and expiry to change from the
   console. Recommendation: allow the expiry to change and keep the owner fixed.
5. **Resolving an unknown side effect (tasks 13.3 and 15.46).** An action whose result is unknown can
   leave that state only by being verified with the outside system. The tasks ask for a person to mark
   it resolved, and for a button that re-sends a failed message. Recommendation: keep verification as
   the only way out, and add the re-send button as a separate, smaller task.

Budget stopping (tasks 12.5 and 7.15) waits on item 169 and is not repeated here.

**Option A: narrow all five as recommended.** The tasks then close on what is built and proved.

**Option B: build any of them as written.** Tell me which; each is a design change and a migration or a
route, and 5 in particular needs your sign-off because a person's word would replace a check.

**What I need from you:** reply "188: A", or "188: B" with the numbers you want built.

"""

# Place both above the current top item.
top = re.search(r"^## (\d+)\.", text, re.M)
assert top and int(top.group(1)) == 186, top.group(1)
text = text[: top.start()] + held + five + text[top.start():]

# Header: count and list.
m = re.search(r"\*\*(\d+) items are open: ", text)
count = int(m.group(1)) + 2
text = text.replace(
    m.group(0),
    f"**{count} items are open: 188,** whether five console tasks that ask for what the design does not do are narrowed, "
    f"**187,** whether the chat tools show progress while an answer is made, ",
    1,
)
page.write_text(text, newline="\n")

words = {64: "Sixty-four"}
arch = Path("docs/architecture.html")
a = arch.read_text()
a2 = re.sub(r'(<span data-open-questions="">)[A-Za-z-]+(</span>)', lambda mm: mm.group(1) + words[count] + mm.group(2), a, count=1)
assert a2 != a
arch.write_text(a2, newline="\n")
print("count", count)
