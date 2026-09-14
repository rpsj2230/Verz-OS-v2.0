# Capabilities

The vocabulary itself: everything that can be granted at all, and what each one unlocks. Read before writing a grant, not after wondering why one did nothing.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `capabilities` |
| Title | Capabilities |
| Group | `govern` |
| Tool | `console.capabilities` |
| Needs | `read:capability` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin, auditor` |
| Can be opened today | `no` |

## What it is for

The vocabulary: everything that can be granted at all (`govern.catalogue`). Read it before writing a grant, alongside the grant and scope cookbook in `docs/guides/grants-and-scopes.md`.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.capabilities` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:capability` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

The whole vocabulary or nothing. It is never filtered to what you hold, because a catalogue filtered to the reader is only their own access relabelled. The same capability also lets you see capability names on People and ceilings on Agents.

## When it is empty or refuses

Empty means you do not hold `read:capability`. The registry says the screen shows what each capability unlocks; the catalogue returns names only today.

## When it shows an alarm

No alarm. A grant that seems to do nothing is usually a column granted without its row: see the cookbook.
