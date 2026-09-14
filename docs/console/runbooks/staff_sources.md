# Staff sources

Where the staff list is linked from: a spreadsheet, Google Workspace, Microsoft, Lark or a directory. What each source is trusted to assert, and when it last ran.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `staff_sources` |
| Title | Staff sources |
| Group | `govern` |
| Tool | `console.staff_sources` |
| Needs | `read:staff_source` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin` |
| Can be opened today | `no` |

## What it is for

Where the staff list comes from: each source, what it is trusted to assert, whether it promised a complete list, and when it last ran (`StaffSourceRow`), with the setup choices and a dry-run trial.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.staff_sources` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:staff_source` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Every source belongs to no department, so only a company-wide `read:staff_source` grant sees any; a department admin opens the screen and correctly sees it empty. The trial also needs the content plane.

## When it is empty or refuses

Empty at a department's scope is the correct answer rather than a gap. A blank last run does not mean the source never ran. Without permission the choices, the selection and the trial each come back empty, the same as having nothing to show.

## When it shows an alarm

`source_gaps` warns about three things: a source that did not promise a complete list, so nobody may be removed on the strength of its run; a source not trusted to assert that people exist; and more than one source asserting roles, which lets a role survive removal from a group. A selection with a refusal, or a trial with refusals or not safe to apply, must not be applied.
