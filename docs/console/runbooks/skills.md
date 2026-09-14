# Skills and templates

What agents can be taught to do, with the review queue for anything proposed.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `skills` |
| Title | Skills and templates |
| Group | `govern` |
| Tool | `console.skills` |
| Needs | `read:skill` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, agent` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

What agents can be taught to do, with the review queue: what is waiting, what is an edit to an approved skill, and what has gone stale (`govern_estate.skill_queue`).

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.skills` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:skill` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Entries are narrowed to your `read:skill` scope, and the summary counts only what is shown.

## When it is empty or refuses

An entry out of your reach is absent.

## When it shows an alarm

An entry older than `STALE_AFTER` is stale: review it or reject it. `Review.CHANGED` means an approved skill's contents changed after approval and it will not run until reviewed again.
