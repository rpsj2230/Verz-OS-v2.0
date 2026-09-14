# Artifacts

What the system produced: documents, exports, reports, with what each was built from and when it will be deleted.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `artifacts` |
| Title | Artifacts |
| Group | `govern` |
| Tool | `console.artifacts` |
| Needs | `read:artifact` |
| Console plane | `read:console.existence` |
| Narrowed by | `department, person, agent, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

What the system produced: documents, exports and reports, with what each was built from, its size and when it will be deleted, plus a storage summary.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.artifacts` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:artifact` and `read:console.existence`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Your own always, and others when your `read:artifact` scope matches the agent, the kind, the caller and the state.

## When it is empty or refuses

An artifact past its retention is dropped before anything else, and looks exactly like one that never existed.

## When it shows an alarm

`retention_enforcement_gaps` reports today that nothing deletes an artifact when its window ends: the storage has no lifecycle rule and nothing sweeps it. Watch the soonest expiry in the summary and treat retention as not enforced.
