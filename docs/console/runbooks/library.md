# Knowledge library

Every document the system can draw on, with the visibility scope on each. Existence plane: this screen says a document is there, never what is in it.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `library` |
| Title | Knowledge library |
| Group | `govern` |
| Tool | `console.library` |
| Needs | `read:document` |
| Console plane | `read:console.existence` |
| Narrowed by | `department, person, connector` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

Every document the system can draw on, with the visibility level on each (`LibraryRow`). It says a document is there and never what is in it.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.library` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:document` and `read:console.existence`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Narrowed by where each document sits. The breakdown by department is shown only when you may see every department.

## When it is empty or refuses

A document out of your reach is absent, and the department breakdown is withheld rather than shortened on a narrower basis.

## When it shows an alarm

No alarm. Making a document visible more widely is proposed and approved on the Approvals screen, never done by viewing it here.
