# Retention and erasure

How long each kind of thing is kept, what is due for deletion, and the queue of erasure requests.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `retention` |
| Title | Retention and erasure |
| Group | `govern` |
| Tool | `console.retention` |
| Needs | `read:retention_policy` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin` |
| Can be opened today | `no` |

## What it is for

How long each kind of thing is kept, what is due for deletion in each store, and the queue of erasure requests (`govern_surfaces.retention_view`, `DeletionRow`).

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.retention` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:retention_policy` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

The retention report is shown only to a company-wide grant and is never narrowed. An erasure request is shown to the person it is about, or inside your reach.

## When it is empty or refuses

A narrower grant sees no report. A request with no completion time is the ordinary state.

## When it shows an alarm

`drain_gaps` reports today that nothing carries out an erasure or a sweep: requests are recorded and not acted on. A report marked incomplete did not reach every store. `enforcement_gaps` flags a store with no census, items past their horizon in a class that is never deleted, and everything past its horizon being under legal hold.
