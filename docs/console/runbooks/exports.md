# Exports

What left the building, who took it and under whose reach. The largest exfiltration channel any permission system has, and the one least often watched.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `exports` |
| Title | Exports |
| Group | `govern` |
| Tool | `console.exports` |
| Needs | `read:export` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin, auditor` |
| Can be opened today | `no` |

## What it is for

What left the building: each export with who took it, when, why, from which stores, about whom and how many items (`ExportAudit`).

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.exports` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:export` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

A row is shown when you are one of the people it was about, or when it sits inside your `read:export` reach.

## When it is empty or refuses

Anything else is absent, with no count. Export records are not written to the audit ledger yet, and the registry's promise of whose reach an export ran under has no field behind it.

## When it shows an alarm

Nothing is computed as an alarm. Read the reason on each row, and look hardest at exports about everybody, which are the widest there are.
