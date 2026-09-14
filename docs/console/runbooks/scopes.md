# Scopes and departments

The row filters a grant can carry, and the departments they are usually written against.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `scopes` |
| Title | Scopes and departments |
| Group | `govern` |
| Tool | `console.scopes` |
| Needs | `read:scope` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin, auditor` |
| Can be opened today | `no` |

## What it is for

The row filters a grant can carry, and the departments they are usually written against (`govern_surfaces.scope_rows`, `departments_offered`).

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.scopes` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:scope` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

A scope is listed only when it sits inside your own grant. The test for that is sound and incomplete, so it can leave out a scope you could in fact have written, and never the other way round.

## When it is empty or refuses

Holding nothing offers no departments. Nothing raises.

## When it shows an alarm

No alarm.
